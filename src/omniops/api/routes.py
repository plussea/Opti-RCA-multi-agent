"""API 路由（异步版本）"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from omniops.agents import (
    DiagnosisAgent,
    ImpactAgent,
    PerceptionAgent,
    PlanningAgent,
    VerificationAgent,
)
from omniops.core.file_storage import get_file_storage
from omniops.events.publisher import get_publisher
from omniops.ingestion.csv_parser import ingest_csv
from omniops.memory.redis_store import get_redis_session_store
from omniops.memory.store import generate_session_id
from omniops.models import (
    FeedbackRequest,
    InputType,
    Session,
    SessionCreateResponse,
    SessionStatus,
    StructuredInput,
)
from omniops.router.context_router import AgentMode, ContextRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["sessions"])


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(file: Optional[UploadFile] = None) -> SessionCreateResponse:
    """创建新诊断会话"""
    if file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is required")
    storage = get_file_storage()

    content = await file.read()
    session_id = generate_session_id()

    # 判断输入类型
    filename = file.filename or ""
    if filename.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
        input_type = InputType.IMAGE if filename.lower().endswith((".png", ".jpg", ".jpeg")) else InputType.PDF
        # 保存图片/PDF 用于 OCR 处理
        await storage.save_upload(content, filename, session_id)
        return SessionCreateResponse(
            session_id=session_id,
            status=SessionStatus.ANALYZING,
            estimated_seconds=90,
        )
    else:
        input_type = InputType.CSV

    # 解析 CSV
    try:
        records, uncertain_fields = ingest_csv(content)
    except Exception as e:
        logger.error(f"CSV parsing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV 解析失败: {str(e)}",
        ) from e

    if not records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV 中未提取到有效告警记录",
        )

    # 创建会话
    session = Session(
        session_id=session_id,
        input_type=input_type,
        structured_data=records,
        status=SessionStatus.ANALYZING,
        current_step="init",
    )

    # 预处理：感知 Agent（同步执行，保持冷启动简单）
    perception = PerceptionAgent()
    await perception.process(session)

    # 感知完成 → 状态机推进
    session.status = SessionStatus.PERCEIVED
    session.current_step = "perceived"

    # 路由决策
    router_instance = ContextRouter()
    mode = router_instance.decide_mode(session)

    # 存储会话（优先 Redis，备选内存）
    try:
        redis_store = await get_redis_session_store()
        await redis_store.create(session)
        logger.info(f"Session {session_id} stored in Redis, status=PERCEIVED")
    except Exception as e:
        logger.warning(f"Redis storage failed, using in-memory: {e}")
        from omniops.memory.store import get_session_store
        memory_store = get_session_store()
        memory_store.create(session)

    # 发布诊断事件（异步链路从这里开始）
    try:
        publisher = await get_publisher()
        await publisher.publish_diagnosis_requested(session)
    except Exception as pub_err:
        logger.warning(f"Event publish failed, falling back to in-process chain: {pub_err}")
        # 降级：同步执行剩余链路
        await _run_agent_chain_sync(session, mode, router_instance)

    # 估算时间
    estimated = 30 if mode == AgentMode.SINGLE else 60

    return SessionCreateResponse(
        session_id=session_id,
        status=SessionStatus.PERCEIVED,
        estimated_seconds=estimated,
    )


async def _run_agent_chain_sync(
    session: Session,
    mode: AgentMode,
    router: ContextRouter,
) -> None:
    """同步执行剩余 Agent 链路（RabbitMQ 不可用时的降级路径）"""
    chain = router.build_agent_chain(mode)

    for agent_name in chain:
        if agent_name == "perception":
            continue  # 已执行

        agent: Any = None  # type: ignore[no-redef]
        if agent_name == "diagnosis":
            agent = DiagnosisAgent()
        elif agent_name == "impact":
            agent = ImpactAgent()
        elif agent_name == "planning":
            agent = PlanningAgent()
        elif agent_name == "verification":
            agent = VerificationAgent()
        else:
            continue

        await agent.process(session)

        # 状态机推进
        router.route_after_agent(session, agent_name)

        # 持久化中间状态
        try:
            redis_store = await get_redis_session_store()
            await redis_store.update(
                session.session_id,
                status=session.status,
                current_step=session.current_step,
                diagnosis_result=session.diagnosis_result,
                impact=session.impact,
                suggestion=session.suggestion,
            )
        except Exception:
            pass

        if session.status in (SessionStatus.COMPLETED, SessionStatus.RESOLVED):
            break


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> Session:
    """获取会话详情"""
    # 尝试 Redis
    try:
        redis_store = await get_redis_session_store()
        session = await redis_store.get(session_id)
        if session:
            return session
    except Exception:
        pass

    # 降级到内存存储
    from omniops.memory.store import get_session_store
    memory_store = get_session_store()
    session = memory_store.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在",
        )

    return session


@router.get("/sessions/{session_id}/result")
async def get_session_result(session_id: str) -> Dict[str, Any]:
    """获取诊断结果"""
    # 尝试 Redis
    try:
        redis_store = await get_redis_session_store()
        session = await redis_store.get(session_id)
        if session:
            return _build_result_response(session)
    except Exception:
        pass

    # 降级到内存存储
    from omniops.memory.store import get_session_store
    memory_store = get_session_store()
    session = memory_store.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在",
        )

    return _build_result_response(session)


def _build_result_response(session: Session) -> Dict:
    """构建诊断结果响应"""
    structured_input = StructuredInput(
        source=session.input_type,
        rows_extracted=len(session.structured_data),
        uncertain_fields=[],
    )

    return {
        "session_id": session.session_id,
        "status": session.status,
        "structured_input": structured_input.model_dump(),
        "diagnosis": session.diagnosis_result.model_dump() if session.diagnosis_result else None,
        "impact": session.impact.model_dump() if session.impact else None,
        "suggestion": session.suggestion.model_dump() if session.suggestion else None,
        "similar_cases": [],  # TODO: 从 RAG 检索
    }


@router.post("/sessions/{session_id}/feedback")
async def submit_feedback(session_id: str, feedback: FeedbackRequest) -> Dict[str, Any]:
    """提交工程师反馈"""
    # 尝试 Redis
    try:
        redis_store = await get_redis_session_store()
        session = await redis_store.get(session_id)
        if session:
            # 更新反馈
            session.human_feedback = feedback.model_dump()

            if feedback.decision.value == "adopted":
                session.status = SessionStatus.APPROVED
            elif feedback.decision.value == "rejected":
                session.status = SessionStatus.REJECTED
            else:
                session.status = SessionStatus.COMPLETED

            await redis_store.update(
                session_id,
                status=session.status,
                human_feedback=session.human_feedback,
            )

            # 保存反馈记录
            from omniops.memory.db_store import get_db_session_store
            try:
                db_store = await get_db_session_store()
                await db_store.save_feedback(
                    session_id=session_id,
                    decision=feedback.decision.value,
                    actual_action=feedback.actual_action,
                    effectiveness=feedback.effectiveness.value,
                )
            except Exception as e:
                logger.warning(f"DB feedback save failed: {e}")

            # 发布反馈事件（触发知识闭环）
            try:
                publisher = await get_publisher()
                await publisher.publish_human_feedback_received(
                    session_id=session_id,
                    decision=feedback.decision.value,
                    actual_action=feedback.actual_action,
                    effectiveness=feedback.effectiveness.value,
                )
            except Exception as pub_err:
                logger.warning(f"Feedback event publish failed: {pub_err}")

            return {"message": "反馈已提交", "status": session.status}
    except Exception:
        pass

    # 降级到内存存储
    from omniops.memory.store import get_session_store
    memory_store = get_session_store()
    session = memory_store.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在",
        )

    if session.status not in (SessionStatus.COMPLETED, SessionStatus.NEEDS_REVIEW):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {session.status} 不允许提交反馈",
        )

    session.human_feedback = feedback.model_dump()

    if feedback.decision.value == "adopted":
        session.status = SessionStatus.APPROVED
    elif feedback.decision.value == "rejected":
        session.status = SessionStatus.REJECTED
    else:
        session.status = SessionStatus.COMPLETED

    memory_store.update(session_id, **session.model_dump())

    return {"message": "反馈已提交", "status": session.status}


@router.get("/sessions")
async def list_sessions() -> List[Dict[str, Any]]:
    """List all active sessions for the frontend sidebar."""
    try:
        store = await get_redis_session_store()
        sessions = await store.list_active()
    except Exception:
        from omniops.memory.store import get_session_store
        memory_store = get_session_store()
        sessions = memory_store.list_active()

    return [
        {
            "session_id": s.session_id,
            "status": s.status.value,
            "current_step": s.current_step,
            "created_at": s.created_at.isoformat(),
            "input_type": s.input_type.value,
            "ne_count": len(s.structured_data),
            "root_cause": (
                s.diagnosis_result.root_cause
                if s.diagnosis_result else None
            ),
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str) -> StreamingResponse:
    """Server-Sent Events stream for real-time session status updates.

    Frontend consumes with:
        const es = new EventSource('/v1/sessions/{session_id}/stream')
        es.addEventListener('status', (e) => { const data = JSON.parse(e.data) })
    """
    async def event_generator() -> Any:
        poll_interval = 1.5
        terminal = {"approved", "rejected", "resolved", "completed", "failed", "escalated"}
        poll_count = 0

        while True:
            poll_count += 1

            # Heartbeat comment to prevent Nginx/browser timeouts every ~30s
            if poll_count % 20 == 0:
                yield ""
                await asyncio.sleep(0.01)
                continue

            # Load session from Redis (fast path)
            session: Any = None  # type: ignore[no-redef]
            try:
                store = await get_redis_session_store()
                session = await store.get(session_id)
            except Exception:
                pass

            # Fallback to in-memory store
            if session is None:
                from omniops.memory.store import get_session_store
                memory_store = get_session_store()
                session = memory_store.get(session_id)

            if session is None:
                payload = json.dumps({"session_id": session_id, "error": "not_found"})
                yield f"event: error\ndata: {payload}\n\n"
                break

            payload_data: Dict[str, Any] = {
                "session_id": session.session_id,
                "status": session.status.value if hasattr(session.status, "value") else str(session.status),
                "current_step": session.current_step,
                "diagnosis_result": (
                    session.diagnosis_result.model_dump() if session.diagnosis_result else None
                ),
                "impact": session.impact.model_dump() if session.impact else None,
                "suggestion": session.suggestion.model_dump() if session.suggestion else None,
                "human_feedback": session.human_feedback,
                "created_at": session.created_at.isoformat(),
            }

            # Terminal statuses — send final event then close
            if session.status.value in terminal:
                yield f"event: status\ndata: {json.dumps(payload_data)}\n\n"
                yield "event: close\ndata: {}\n\n"
                break

            yield f"event: status\ndata: {json.dumps(payload_data)}\n\n"
            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    health_info: Dict[str, Any] = {
        "status": "healthy",
        "version": "0.1.0",
        "components": {},
    }

    # 检查 Redis
    try:
        redis_store = await get_redis_session_store()
        await redis_store.client.ping()
        health_info["components"]["redis"] = "connected"  # type: ignore[index]
    except Exception:
        health_info["components"]["redis"] = "disconnected"  # type: ignore[index]

    # 检查数据库
    try:
        from omniops.core.database import async_session_maker
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))  # type: ignore[call-overload]
        health_info["components"]["database"] = "connected"  # type: ignore[index]
    except Exception:
        health_info["components"]["database"] = "disconnected"  # type: ignore[index]

    # 检查向量存储
    try:
        from omniops.rag.chroma_store import get_vector_store
        count = get_vector_store().get_count()
        health_info["components"]["vector_store"] = f"connected ({count} entries)"
    except Exception:
        health_info["components"]["vector_store"] = "disconnected"

    return health_info
