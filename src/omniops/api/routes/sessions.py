"""Session 相关路由"""
from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import text
from typing import Any, Dict, List, Optional

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
from omniops.memory.db_store import get_db_session_store
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
from omniops.api.services.agent_orchestrator import run_agent_chain_sync  # noqa: E402
from omniops.api.services.sse_generator import sse_stream  # noqa: E402

router = APIRouter(prefix="/v1", tags=["sessions"])


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(file: Optional[UploadFile] = None) -> SessionCreateResponse:
    """创建新诊断会话"""
    if file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is required")
    storage = get_file_storage()

    content = await file.read()
    session_id = generate_session_id()

    filename = file.filename or ""
    if filename.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
        input_type = InputType.IMAGE if filename.lower().endswith((".png", ".jpg", ".jpeg")) else InputType.PDF
        await storage.save_upload(content, filename, session_id)
        return SessionCreateResponse(
            session_id=session_id,
            status=SessionStatus.ANALYZING,
            estimated_seconds=90,
        )
    else:
        input_type = InputType.CSV

    try:
        records, uncertain_fields = ingest_csv(content)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"CSV 解析失败: {str(e)}") from e

    if not records:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV 中未提取到有效告警记录")

    session = Session(
        session_id=session_id,
        input_type=input_type,
        structured_data=records,
        status=SessionStatus.ANALYZING,
        current_step="init",
    )

    perception = PerceptionAgent()
    await perception.process(session)

    session.status = SessionStatus.PERCEIVED
    session.current_step = "perceived"

    router_instance = ContextRouter()
    mode = router_instance.decide_mode(session)

    try:
        redis_store = await get_redis_session_store()
        await redis_store.create(session)

        from omniops.memory.db_store import get_db_session_store
        try:
            db_store = await get_db_session_store()
            await db_store.create(session)
        except Exception as db_err:
            import logging
            logging.getLogger(__name__).warning(f"PostgreSQL persist failed (non-fatal): {db_err}")

        import logging
        logging.getLogger(__name__).info(f"Session {session_id} stored in Redis, status=PERCEIVED")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Redis storage failed, using in-memory: {e}")
        from omniops.memory.store import get_session_store
        get_session_store().create(session)

    try:
        publisher = await get_publisher()
        await publisher.publish_diagnosis_requested(session)
    except Exception as pub_err:
        import logging
        logging.getLogger(__name__).warning(f"Event publish failed: {pub_err}")

    await run_agent_chain_sync(session, mode, router_instance)

    estimated = 30 if mode == AgentMode.SINGLE else 60
    final_status = session.status
    if final_status not in (SessionStatus.COMPLETED, SessionStatus.RESOLVED, SessionStatus.PENDING_HUMAN):
        final_status = SessionStatus.PERCEIVED

    return SessionCreateResponse(
        session_id=session_id,
        status=final_status,
        estimated_seconds=estimated,
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> Session:
    """获取会话详情"""
    try:
        redis_store = await get_redis_session_store()
        session = await redis_store.get(session_id)
        if session:
            return session
    except Exception:
        pass

    from omniops.memory.store import get_session_store
    session = get_session_store().get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"会话 {session_id} 不存在")
    return session


@router.get("/sessions/{session_id}/conversations")
async def get_session_conversations(session_id: str) -> List[Dict[str, Any]]:
    """获取会话的所有 Agent 对话记录"""
    db_store = await get_db_session_store()
    conversations = await db_store.get_conversations(session_id)
    if not conversations:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"会话 {session_id} 无对话记录")
    return conversations


@router.get("/sessions/{session_id}/result")
async def get_session_result(session_id: str) -> Dict[str, Any]:
    """获取诊断结果"""
    try:
        redis_store = await get_redis_session_store()
        session = await redis_store.get(session_id)
        if session:
            return _build_result_response(session)
    except Exception:
        pass

    from omniops.memory.store import get_session_store
    session = get_session_store().get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"会话 {session_id} 不存在")
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
        "status": session.status.value,
        "structured_input": structured_input.model_dump(),
        "diagnosis": session.diagnosis_result.model_dump() if session.diagnosis_result else None,
        "impact": session.impact.model_dump() if session.impact else None,
        "suggestion": session.suggestion.model_dump() if session.suggestion else None,
        "similar_cases": [],
    }


@router.post("/sessions/{session_id}/feedback")
async def submit_feedback(session_id: str, feedback: FeedbackRequest) -> Dict[str, Any]:
    """提交工程师反馈"""
    try:
        redis_store = await get_redis_session_store()
        session = await redis_store.get(session_id)
        if session:
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
                import logging
                logging.getLogger(__name__).warning(f"DB feedback save failed: {e}")

            try:
                publisher = await get_publisher()
                await publisher.publish_human_feedback_received(
                    session_id=session_id,
                    decision=feedback.decision.value,
                    actual_action=feedback.actual_action,
                    effectiveness=feedback.effectiveness.value,
                )
            except Exception as pub_err:
                import logging
                logging.getLogger(__name__).warning(f"Feedback event publish failed: {pub_err}")

            return {"message": "反馈已提交", "status": session.status}
    except Exception:
        pass

    from omniops.memory.store import get_session_store
    session = get_session_store().get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"会话 {session_id} 不存在")

    if session.status not in (SessionStatus.COMPLETED, SessionStatus.NEEDS_REVIEW):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {session.status} 不允许提交反馈")

    session.human_feedback = feedback.model_dump()
    if feedback.decision.value == "adopted":
        session.status = SessionStatus.APPROVED
    elif feedback.decision.value == "rejected":
        session.status = SessionStatus.REJECTED
    else:
        session.status = SessionStatus.COMPLETED

    get_session_store().update(session_id, **session.model_dump())
    return {"message": "反馈已提交", "status": session.status}


@router.get("/sessions")
async def list_sessions() -> List[Dict[str, Any]]:
    """List all active sessions for the frontend sidebar."""
    try:
        store = await get_redis_session_store()
        sessions = await store.list_active()
    except Exception:
        from omniops.memory.store import get_session_store
        sessions = get_session_store().list_active()

    return [
        {
            "session_id": s.session_id,
            "status": s.status.value,
            "current_step": s.current_step,
            "created_at": s.created_at.isoformat(),
            "input_type": s.input_type.value,
            "ne_count": len(s.structured_data),
            "root_cause": s.diagnosis_result.root_cause if s.diagnosis_result else None,
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str):
    """SSE stream"""
    return await sse_stream(session_id)
