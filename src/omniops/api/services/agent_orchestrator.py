"""Agent 链路同步编排器 — 从 routes.py 中提取"""
import logging
from typing import Any

from omniops.agents import (
    DiagnosisAgent,
    ImpactAgent,
    PlanningAgent,
    VerificationAgent,
)
from omniops.memory.persistence import SessionPersistence
from omniops.models import Session, SessionStatus
from omniops.router.context_router import AgentMode, ContextRouter

logger = logging.getLogger(__name__)


async def run_agent_chain_sync(
    session: Session,
    mode: AgentMode,
    router: ContextRouter,
) -> None:
    """同步执行剩余 Agent 链路（RabbitMQ 不可用时的降级路径）"""
    chain = router.build_agent_chain(mode)
    logger.info(f"[sync-chain] starting chain={chain} for session={session.session_id}")

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

        try:
            logger.info(f"[sync-chain] executing {agent_name}...")
            await agent.process(session)
            logger.info(f"[sync-chain] {agent_name} done, status={session.status}, step={session.current_step}")
        except Exception as e:
            logger.error(f"[sync-chain] {agent_name} failed: {e}", exc_info=True)

        router.route_after_agent(session, agent_name)

        await SessionPersistence.dual_write(
            session.session_id,
            status=session.status,
            current_step=session.current_step,
            diagnosis_result=session.diagnosis_result,
            impact=session.impact,
            suggestion=session.suggestion,
        )

        if session.status in (SessionStatus.COMPLETED, SessionStatus.RESOLVED, SessionStatus.PENDING_HUMAN):
            logger.info(f"[sync-chain] terminal status reached ({session.status}), stopping")
            break
