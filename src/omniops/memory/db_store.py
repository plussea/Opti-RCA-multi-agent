"""异步会话存储（PostgreSQL）"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from omniops.core.database import async_session_maker, init_db
from omniops.models import Session, SessionStatus
from omniops.models.database import AlarmRecordModel, SessionModel

logger = logging.getLogger(__name__)


class DBSessionStore:
    """PostgreSQL 异步会话存储"""

    def __init__(self) -> None:
        self._initialized = False

    async def ensure_init(self) -> None:
        """确保数据库已初始化"""
        if not self._initialized:
            await init_db()
            self._initialized = True

    async def _to_session(self, model: SessionModel) -> Session:
        """将数据库模型转换为 Session"""
        # 转换告警记录
        records = []
        for r in model.alarm_records:

            from omniops.models import AlarmRecord, Severity

            alarm_record = AlarmRecord(
                ne_name=r.ne_name,
                alarm_name=r.alarm_name,
                severity=Severity(r.severity) if r.severity else None,
                occur_time=r.occur_time,
                shelf=r.shelf,
                slot=r.slot,
                board_type=r.board_type,
                topology_id=r.topology_id,
                location=r.location,
                raw_data=r.raw_data or {},
            )
            records.append(alarm_record)

        # 转换诊断结果
        diagnosis_result = None
        if model.diagnosis_result:
            from omniops.models import DiagnosisResult, Evidence
            dr = model.diagnosis_result
            diagnosis_result = DiagnosisResult(
                root_cause=dr.get("root_cause", ""),
                confidence=dr.get("confidence", 0.0),
                evidence=[Evidence(**e) for e in dr.get("evidence", [])],
                uncertainty=dr.get("uncertainty"),
                agent_chain=dr.get("agent_chain", []),
            )

        # 转换影响范围
        impact = None
        if model.impact:
            from omniops.models import Impact
            impact = Impact(**model.impact)

        # 转换建议
        suggestion = None
        if model.suggestion:
            from omniops.models import Suggestion, SuggestionAction
            sug = model.suggestion
            suggestion = Suggestion(
                root_cause=sug.get("root_cause", ""),
                suggested_actions=[SuggestionAction(**a) for a in sug.get("suggested_actions", [])],
                required_tools=sug.get("required_tools", []),
                fallback_plan=sug.get("fallback_plan"),
                risk_level=sug.get("risk_level", "low"),
                needs_approval=sug.get("needs_approval", False),
            )

        return Session(
            session_id=model.session_id,  # type: ignore[arg-type]
            input_type=model.input_type,  # type: ignore[arg-type]
            structured_data=records,
            diagnosis_result=diagnosis_result,
            impact=impact,
            suggestion=suggestion,
            human_feedback=model.human_feedback,  # type: ignore[arg-type]
            perception_metadata=model.perception_metadata,  # type: ignore[arg-type]
            status=SessionStatus(model.status),
            created_at=model.created_at,  # type: ignore[arg-type]
        )

    async def _to_model(self, session: Session) -> Dict[str, Any]:
        """将会话转换为数据库模型数据"""
        # 告警记录
        records_json = []
        for r in session.structured_data:
            records_json.append({
                "ne_name": r.ne_name,
                "alarm_name": r.alarm_name,
                "severity": r.severity.value if r.severity else None,
                "occur_time": r.occur_time.isoformat() if r.occur_time else None,
                "shelf": r.shelf,
                "slot": r.slot,
                "board_type": r.board_type,
                "topology_id": r.topology_id,
                "location": r.location,
                "raw_data": r.raw_data,
            })

        # 诊断结果
        diagnosis_json = None
        if session.diagnosis_result:
            dr = session.diagnosis_result
            diagnosis_json = {
                "root_cause": dr.root_cause,
                "confidence": dr.confidence,
                "evidence": [e.model_dump() for e in dr.evidence],
                "uncertainty": dr.uncertainty,
                "agent_chain": dr.agent_chain,
            }

        # 影响范围
        impact_json = None
        if session.impact:
            impact_json = session.impact.model_dump()

        # 建议
        suggestion_json = None
        if session.suggestion:
            sug = session.suggestion
            suggestion_json = {
                "root_cause": sug.root_cause,
                "suggested_actions": [a.model_dump() for a in sug.suggested_actions],
                "required_tools": sug.required_tools,
                "fallback_plan": sug.fallback_plan,
                "risk_level": sug.risk_level,
                "needs_approval": sug.needs_approval,
            }

        return {
            "session_id": session.session_id,
            "input_type": session.input_type.value if hasattr(session.input_type, 'value') else str(session.input_type),
            "status": session.status.value if hasattr(session.status, 'value') else str(session.status),
            "structured_data": records_json,
            "diagnosis_result": diagnosis_json,
            "impact": impact_json,
            "suggestion": suggestion_json,
            "human_feedback": session.human_feedback,
            "perception_metadata": session.perception_metadata,
            "created_at": session.created_at,
            "updated_at": datetime.utcnow(),
        }

    async def create(self, session: Session) -> Session:
        """创建新会话（幂等：删除已存在记录后重新插入）"""
        await self.ensure_init()

        async with async_session_maker() as db:
            # 先删除已存在的记录（幂等支持，允许重复运行测试）
            delete_stmt = SessionModel.__table__.delete().where(
                SessionModel.session_id == session.session_id
            )
            await db.execute(delete_stmt)

            # 创建会话记录
            session_data = await self._to_model(session)

            # 插入会话主记录
            stmt = SessionModel.__table__.insert().values(**session_data)
            await db.execute(stmt)

            # 插入告警记录
            for r in session.structured_data:
                alarm = AlarmRecordModel(
                    session_id=session.session_id,
                    ne_name=r.ne_name,
                    alarm_name=r.alarm_name,
                    severity=r.severity.value if r.severity else None,
                    occur_time=r.occur_time,
                    shelf=r.shelf,
                    slot=r.slot,
                    board_type=r.board_type,
                    topology_id=r.topology_id,
                    location=r.location,
                    raw_data=r.raw_data or {},
                )
                db.add(alarm)

            await db.commit()

        return session

    async def get(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        await self.ensure_init()

        async with async_session_maker() as db:
            stmt = (
                select(SessionModel)
                .options(joinedload(SessionModel.alarm_records))
                .where(SessionModel.session_id == session_id)
            )
            result = await db.execute(stmt)
            model = result.unique().scalar_one_or_none()

            if not model:
                return None

            return await self._to_session(model)

    async def update(self, session_id: str, **updates: Any) -> Optional[Session]:
        """更新会话字段"""
        await self.ensure_init()

        async with async_session_maker() as db:
            update_data = {}
            if "status" in updates:
                status = updates["status"]
                update_data["status"] = status.value if hasattr(status, 'value') else str(status)
            if "diagnosis_result" in updates:
                dr = updates["diagnosis_result"]
                if dr:
                    update_data["diagnosis_result"] = {
                        "root_cause": dr.root_cause,
                        "confidence": dr.confidence,
                        "evidence": [e.model_dump() for e in dr.evidence],
                        "uncertainty": dr.uncertainty,
                        "agent_chain": dr.agent_chain,
                    }
            if "impact" in updates:
                update_data["impact"] = updates["impact"].model_dump() if updates["impact"] else None
            if "suggestion" in updates:
                sug = updates["suggestion"]
                if sug:
                    update_data["suggestion"] = {
                        "root_cause": sug.root_cause,
                        "suggested_actions": [a.model_dump() for a in sug.suggested_actions],
                        "required_tools": sug.required_tools,
                        "fallback_plan": sug.fallback_plan,
                        "risk_level": sug.risk_level,
                        "needs_approval": sug.needs_approval,
                    }
            if "human_feedback" in updates:
                update_data["human_feedback"] = updates["human_feedback"]
            if "perception_metadata" in updates:
                update_data["perception_metadata"] = updates["perception_metadata"]
            # current_step 是内存状态，不持久化
            if "current_step" in update_data:
                del update_data["current_step"]

            update_data["updated_at"] = datetime.utcnow()

            stmt = (
                update(SessionModel)
                .where(SessionModel.session_id == session_id)
                .values(**update_data)
            )
            await db.execute(stmt)
            await db.commit()

        return await self.get(session_id)

    async def delete(self, session_id: str) -> bool:
        """删除会话"""
        await self.ensure_init()

        async with async_session_maker() as db:
            stmt = SessionModel.__table__.delete().where(
                SessionModel.session_id == session_id
            )
            result = await db.execute(stmt)
            await db.commit()
            rowcount = getattr(result, "rowcount", 0) or 0
            return int(rowcount) > 0

    async def list_active(self) -> List[Session]:
        """列出所有活跃会话"""
        await self.ensure_init()

        active = {"analyzing", "perceived", "diagnosing", "planning", "verifying", "pending_human", "needs_review"}
        async with async_session_maker() as db:
            stmt = select(SessionModel).options(joinedload(SessionModel.alarm_records)).where(SessionModel.status.in_(active))
            result = await db.execute(stmt)
            models = result.unique().scalars().all()

            sessions = []
            for model in models:
                sessions.append(await self._to_session(model))

            return sessions

    async def save_conversation(
        self,
        session_id: str,
        agent_name: str,
        step_order: int,
        llm_input: Optional[Dict[str, Any]] = None,
        llm_output: Optional[Dict[str, Any]] = None,
        cognitive_summary: Optional[Dict[str, Any]] = None,
        tokens_used: Optional[int] = None,
        model_name: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """保存 Agent 对话记录"""
        await self.ensure_init()
        from omniops.models.database import AgentConversationModel
        async with async_session_maker() as db:
            conv = AgentConversationModel(
                session_id=session_id,
                agent_name=agent_name,
                step_order=step_order,
                llm_input=llm_input,
                llm_output=llm_output,
                cognitive_summary=cognitive_summary,
                tokens_used=tokens_used,
                model_name=model_name,
                duration_ms=duration_ms,
                error_message=error_message,
            )
            db.add(conv)
            await db.commit()

    async def get_conversations(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话的所有 Agent 对话记录"""
        await self.ensure_init()
        from omniops.models.database import AgentConversationModel
        async with async_session_maker() as db:
            stmt = (
                select(AgentConversationModel)
                .where(AgentConversationModel.session_id == session_id)
                .order_by(AgentConversationModel.step_order)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "agent_name": r.agent_name,
                    "step_order": r.step_order,
                    "llm_input": r.llm_input,
                    "llm_output": r.llm_output,
                    "cognitive_summary": r.cognitive_summary,
                    "tokens_used": r.tokens_used,
                    "model_name": r.model_name,
                    "duration_ms": r.duration_ms,
                    "error_message": r.error_message,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    async def save_feedback(
        self,
        session_id: str,
        decision: str,
        actual_action: str,
        effectiveness: str,
    ) -> bool:
        """保存反馈记录"""
        await self.ensure_init()
        from omniops.models.database import FeedbackModel

        async with async_session_maker() as db:
            feedback = FeedbackModel(
                session_id=session_id,
                decision=decision,
                actual_action=actual_action,
                effectiveness=effectiveness,
            )
            db.add(feedback)
            await db.commit()

        return True


# 全局单例
_db_session_store: Optional[DBSessionStore] = None


async def get_db_session_store() -> DBSessionStore:
    """获取数据库会话存储单例"""
    global _db_session_store
    if _db_session_store is None:
        _db_session_store = DBSessionStore()
    return _db_session_store
