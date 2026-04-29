"""异步会话存储（PostgreSQL）"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omniops.core.database import async_session_maker, init_db
from omniops.models import Session, SessionStatus
from omniops.models.database import AlarmRecordModel, SessionModel

logger = logging.getLogger(__name__)


class DBSessionStore:
    """PostgreSQL 异步会话存储"""

    def __init__(self):
        self._initialized = False

    async def ensure_init(self):
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
            from dateutil.parser import parse as parse_date

            alarm_record = AlarmRecord(
                ne_name=r.ne_name,
                alarm_code=r.alarm_code,
                alarm_name=r.alarm_name,
                severity=Severity(r.severity) if r.severity else None,
                occur_time=r.occur_time,
                shelf=r.shelf,
                slot=r.slot,
                board_type=r.board_type,
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
            session_id=model.session_id,
            input_type=model.input_type,
            structured_data=records,
            diagnosis_result=diagnosis_result,
            impact=impact,
            suggestion=suggestion,
            human_feedback=model.human_feedback,
            perception_metadata=model.perception_metadata,
            status=SessionStatus(model.status),
            created_at=model.created_at,
        )

    async def _to_model(self, session: Session) -> Dict[str, Any]:
        """将会话转换为数据库模型数据"""
        # 告警记录
        records_json = []
        for r in session.structured_data:
            records_json.append({
                "ne_name": r.ne_name,
                "alarm_code": r.alarm_code,
                "alarm_name": r.alarm_name,
                "severity": r.severity.value if r.severity else None,
                "occur_time": r.occur_time.isoformat() if r.occur_time else None,
                "shelf": r.shelf,
                "slot": r.slot,
                "board_type": r.board_type,
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
        """创建新会话"""
        await self.ensure_init()

        async with async_session_maker() as db:
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
                    alarm_code=r.alarm_code,
                    alarm_name=r.alarm_name,
                    severity=r.severity.value if r.severity else None,
                    occur_time=r.occur_time,
                    shelf=r.shelf,
                    slot=r.slot,
                    board_type=r.board_type,
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
                .options()  # 加载关联
                .where(SessionModel.session_id == session_id)
            )
            result = await db.execute(stmt)
            model = result.scalar_one_or_none()

            if not model:
                return None

            # 重新加载告警记录
            from sqlalchemy import select as sa_select
            from omniops.models.database import AlarmRecordModel

            alarm_stmt = sa_select(AlarmRecordModel).where(
                AlarmRecordModel.session_id == session_id
            )
            alarm_result = await db.execute(alarm_stmt)
            model.alarm_records = alarm_result.scalars().all()

            return await self._to_session(model)

    async def update(self, session_id: str, **updates) -> Optional[Session]:
        """更新会话字段"""
        await self.ensure_init()

        async with async_session_maker() as db:
            # 构建更新数据
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
            return result.rowcount > 0

    async def list_active(self) -> List[Session]:
        """列出所有活跃会话"""
        await self.ensure_init()

        async with async_session_maker() as db:
            stmt = select(SessionModel).where(
                SessionModel.status.in_(["analyzing", "needs_review"])
            )
            result = await db.execute(stmt)
            models = result.scalars().all()

            sessions = []
            for model in models:
                # 加载告警记录
                alarm_stmt = select(AlarmRecordModel).where(
                    AlarmRecordModel.session_id == model.session_id
                )
                alarm_result = await db.execute(alarm_stmt)
                model.alarm_records = alarm_result.scalars().all()
                sessions.append(await self._to_session(model))

            return sessions

    async def save_feedback(
        self,
        session_id: str,
        decision: str,
        actual_action: str,
        effectiveness: str,
    ) -> bool:
        """保存反馈记录"""
        await self.ensure_init()

        async with async_session_maker() as db:
            from omniops.models.database import FeedbackModel

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