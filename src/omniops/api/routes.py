"""API 路由"""
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from omniops.agents import DiagnosisAgent, ImpactAgent, PerceptionAgent, PlanningAgent
from omniops.core.config import get_settings
from omniops.ingestion.csv_parser import ingest_csv
from omniops.memory.store import generate_session_id, get_session_store
from omniops.models import (
    FeedbackRequest,
    InputType,
    Session,
    SessionCreateResponse,
    SessionStatus,
    StructuredInput,
)
from omniops.router.context_router import AgentMode, ContextRouter

router = APIRouter(prefix="/v1", tags=["sessions"])


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(file: UploadFile = File(...)):
    """创建新诊断会话"""
    settings = get_settings()
    store = get_session_store()

    content = await file.read()
    session_id = generate_session_id()

    # 判断输入类型
    filename = file.filename or ""
    if filename.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
        input_type = InputType.IMAGE if filename.lower().endswith((".png", ".jpg", ".jpeg")) else InputType.PDF
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV 解析失败: {str(e)}",
        )

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
    )

    # 预处理：感知 Agent
    perception = PerceptionAgent()
    await perception.process(session)

    # 路由决策
    router_instance = ContextRouter()
    mode = router_instance.decide_mode(session)
    agent_chain = router_instance.build_agent_chain(mode)

    # 执行 Agent 链路
    for agent_name in agent_chain:
        if agent_name == "perception":
            continue  # 已执行

        elif agent_name == "diagnosis":
            agent = DiagnosisAgent(model_name=settings.anthropic_model)
            await agent.process(session)

        elif agent_name == "impact":
            agent = ImpactAgent()
            await agent.process(session)

        elif agent_name == "planning":
            agent = PlanningAgent()
            await agent.process(session)

        # 记录链路
        if session.diagnosis_result:
            session.diagnosis_result.agent_chain.append(agent_name)

    # 更新会话状态
    if router_instance.should_trigger_hitl(session):
        session.status = SessionStatus.NEEDS_REVIEW
    else:
        session.status = SessionStatus.COMPLETED

    store.create(session)

    # 估算时间
    estimated = 30 if mode == AgentMode.SINGLE else 60

    return SessionCreateResponse(
        session_id=session_id,
        status=session.status,
        estimated_seconds=estimated,
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    store = get_session_store()
    session = store.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在",
        )

    return session


@router.get("/sessions/{session_id}/result")
async def get_session_result(session_id: str):
    """获取诊断结果"""
    store = get_session_store()
    session = store.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在",
        )

    # 构建结构化输入信息
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
        "similar_cases": [],
    }


@router.post("/sessions/{session_id}/feedback")
async def submit_feedback(session_id: str, feedback: FeedbackRequest):
    """提交工程师反馈"""
    store = get_session_store()
    session = store.get(session_id)

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

    # 更新反馈
    session.human_feedback = feedback.model_dump()

    if feedback.decision.value == "adopted":
        session.status = SessionStatus.APPROVED
    elif feedback.decision.value == "rejected":
        session.status = SessionStatus.REJECTED
    else:
        session.status = SessionStatus.COMPLETED

    store.update(session_id, **session.model_dump())

    return {"message": "反馈已提交", "status": session.status}


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "version": "0.1.0"}