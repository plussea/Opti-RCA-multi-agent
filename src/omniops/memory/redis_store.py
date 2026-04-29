"""Redis 会话存储（缓存层）"""
import json
import logging
from datetime import timedelta
from typing import List, Optional

import redis.asyncio as redis

from omniops.core.config import get_settings
from omniops.models import Session

logger = logging.getLogger(__name__)


class RedisSessionStore:
    """Redis 异步会话存储（缓存层）"""

    SESSION_PREFIX = "session:"
    LOCK_PREFIX = "lock:"

    def __init__(self):
        settings = get_settings()
        self.redis_url = settings.redis_url
        self.ttl = timedelta(seconds=settings.working_memory_ttl)
        self._client: Optional[redis.Redis] = None

    async def connect(self):
        """建立 Redis 连接"""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info(f"Redis connected to {self.redis_url}")

    async def close(self):
        """关闭 Redis 连接"""
        if self._client:
            await self._client.close()
            self._client = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not connected, call connect() first")
        return self._client

    def _session_key(self, session_id: str) -> str:
        return f"{self.SESSION_PREFIX}{session_id}"

    def _lock_key(self, session_id: str) -> str:
        return f"{self.LOCK_PREFIX}{session_id}"

    async def create(self, session: Session) -> Session:
        """创建会话（写入 Redis）"""
        await self.connect()

        session_data = {
            "session_id": session.session_id,
            "input_type": session.input_type.value if hasattr(session.input_type, 'value') else str(session.input_type),
            "status": session.status.value if hasattr(session.status, 'value') else str(session.status),
            "structured_data": json.dumps([
                {
                    "ne_name": r.ne_name,
                    "alarm_code": r.alarm_code,
                    "alarm_name": r.alarm_name,
                    "severity": r.severity.value if r.severity else None,
                    "occur_time": r.occur_time.isoformat() if r.occur_time else None,
                    "shelf": r.shelf,
                    "slot": r.slot,
                    "board_type": r.board_type,
                    "raw_data": r.raw_data,
                }
                for r in session.structured_data
            ]),
            "diagnosis_result": json.dumps(session.diagnosis_result.model_dump()) if session.diagnosis_result else None,
            "impact": json.dumps(session.impact.model_dump()) if session.impact else None,
            "suggestion": json.dumps(session.suggestion.model_dump()) if session.suggestion else None,
            "human_feedback": json.dumps(session.human_feedback) if session.human_feedback else None,
            "perception_metadata": json.dumps(session.perception_metadata) if session.perception_metadata else None,
            "current_step": session.current_step,
            "created_at": session.created_at.isoformat(),
        }

        await self.client.hset(self._session_key(session.session_id), mapping=session_data)
        await self.client.expire(self._session_key(session.session_id), int(self.ttl.total_seconds()))

        logger.info(f"Session {session.session_id} created in Redis")
        return session

    async def get(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        await self.connect()

        data = await self.client.hgetall(self._session_key(session_id))
        if not data:
            return None

        from dateutil.parser import parse as parse_date

        from omniops.models import (
            AlarmRecord,
            DiagnosisResult,
            Evidence,
            Impact,
            InputType,
            SessionStatus,
            Severity,
            Suggestion,
            SuggestionAction,
        )
        from omniops.models import (
            Session as SessionModel,
        )

        # 解析告警记录
        records = []
        structured_data = json.loads(data.get("structured_data", "[]"))
        for r in structured_data:
            records.append(AlarmRecord(
                ne_name=r["ne_name"],
                alarm_code=r.get("alarm_code"),
                alarm_name=r.get("alarm_name"),
                severity=Severity(r["severity"]) if r.get("severity") else None,
                occur_time=parse_date(r["occur_time"]) if r.get("occur_time") else None,
                shelf=r.get("shelf"),
                slot=r.get("slot"),
                board_type=r.get("board_type"),
                raw_data=r.get("raw_data", {}),
            ))

        # 解析诊断结果
        diagnosis_result = None
        if data.get("diagnosis_result"):
            dr_data = json.loads(data["diagnosis_result"])
            diagnosis_result = DiagnosisResult(
                root_cause=dr_data["root_cause"],
                confidence=dr_data["confidence"],
                evidence=[Evidence(**e) for e in dr_data.get("evidence", [])],
                uncertainty=dr_data.get("uncertainty"),
                agent_chain=dr_data.get("agent_chain", []),
            )

        # 解析影响范围
        impact = None
        if data.get("impact"):
            impact = Impact(**json.loads(data["impact"]))

        # 解析建议
        suggestion = None
        if data.get("suggestion"):
            sug_data = json.loads(data["suggestion"])
            suggestion = Suggestion(
                root_cause=sug_data["root_cause"],
                suggested_actions=[SuggestionAction(**a) for a in sug_data.get("suggested_actions", [])],
                required_tools=sug_data.get("required_tools", []),
                fallback_plan=sug_data.get("fallback_plan"),
                risk_level=sug_data.get("risk_level", "low"),
                needs_approval=sug_data.get("needs_approval", False),
            )

        return SessionModel(
            session_id=data["session_id"],
            input_type=InputType(data["input_type"]),
            structured_data=records,
            diagnosis_result=diagnosis_result,
            impact=impact,
            suggestion=suggestion,
            human_feedback=json.loads(data["human_feedback"]) if data.get("human_feedback") else None,
            perception_metadata=json.loads(data["perception_metadata"]) if data.get("perception_metadata") else None,
            status=SessionStatus(data["status"]),
            current_step=data.get("current_step", "init"),
            created_at=parse_date(data["created_at"]),
        )

    async def update(self, session_id: str, **updates) -> Optional[Session]:
        """更新会话字段"""
        await self.connect()

        update_data = {}
        if "status" in updates:
            status = updates["status"]
            update_data["status"] = status.value if hasattr(status, 'value') else str(status)
        if "current_step" in updates:
            update_data["current_step"] = updates["current_step"]
        if "diagnosis_result" in updates:
            update_data["diagnosis_result"] = json.dumps(updates["diagnosis_result"].model_dump()) if updates["diagnosis_result"] else None
        if "impact" in updates:
            update_data["impact"] = json.dumps(updates["impact"].model_dump()) if updates["impact"] else None
        if "suggestion" in updates:
            update_data["suggestion"] = json.dumps(updates["suggestion"].model_dump()) if updates["suggestion"] else None
        if "human_feedback" in updates:
            update_data["human_feedback"] = json.dumps(updates["human_feedback"])
        if "perception_metadata" in updates:
            update_data["perception_metadata"] = json.dumps(updates["perception_metadata"])

        if update_data:
            await self.client.hset(self._session_key(session_id), mapping=update_data)
            await self.client.expire(self._session_key(session_id), int(self.ttl.total_seconds()))

        return await self.get(session_id)

    async def delete(self, session_id: str) -> bool:
        """删除会话"""
        await self.connect()
        result = await self.client.delete(self._session_key(session_id))
        return result > 0

    async def list_active(self) -> List[Session]:
        """列出所有活跃会话（不常用，Redis 适合按需查询）"""
        await self.connect()
        keys = await self.client.keys(f"{self.SESSION_PREFIX}*")
        sessions = []
        for key in keys:
            sid = key.replace(self.SESSION_PREFIX, "")
            session = await self.get(sid)
            if session and session.status.value in (
                "analyzing", "perceived", "diagnosing", "planning",
                "verifying", "pending_human",
            ):
                sessions.append(session)
        return sessions

    async def acquire_lock(self, session_id: str, timeout: int = 30) -> bool:
        """获取会话锁（用于分布式操作）"""
        await self.connect()
        return await self.client.set(
            self._lock_key(session_id),
            "locked",
            nx=True,
            ex=timeout,
        )

    async def release_lock(self, session_id: str) -> bool:
        """释放会话锁"""
        await self.connect()
        return await self.client.delete(self._lock_key(session_id)) > 0


# 全局单例
_redis_store: Optional[RedisSessionStore] = None


async def get_redis_session_store() -> RedisSessionStore:
    """获取 Redis 会话存储单例"""
    global _redis_store
    if _redis_store is None:
        _redis_store = RedisSessionStore()
        await _redis_store.connect()
    return _redis_store
