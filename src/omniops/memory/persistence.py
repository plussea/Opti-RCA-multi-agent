"""会话持久化 — 双写模式统一抽象（Redis 实时 + PostgreSQL 持久化）"""
import logging
from typing import Any, Dict, List, Optional

from omniops.memory.db_store import get_db_session_store
from omniops.memory.redis_store import get_redis_session_store

logger = logging.getLogger(__name__)


class SessionPersistence:
    """双写模式封装：Redis 写实时状态，PostgreSQL 写持久状态。

    所有错误均以 best-effort 方式吞掉（non-fatal），任一层失败不影响链路。
    新增 Consumer 只需继承 `PersistenceConsumer` mixin，无需重复双写逻辑。
    """

    @staticmethod
    async def dual_write(session_id: str, **updates: Any) -> None:
        """将 updates 同时写入 Redis 和 PostgreSQL"""
        try:
            redis_store = await get_redis_session_store()
            await redis_store.update(session_id, **updates)
        except Exception as e:
            logger.warning(f"Redis update failed (non-fatal): {e}")

        try:
            db_store = await get_db_session_store()
            await db_store.update(session_id, **updates)
        except Exception as e:
            logger.warning(f"PostgreSQL persist failed (non-fatal): {e}")

    @staticmethod
    async def save_conversation(
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
        """记录 Agent 对话历史到 PostgreSQL"""
        try:
            db_store = await get_db_session_store()
            await db_store.save_conversation(
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
        except Exception as e:
            logger.warning(f"Conversation persist failed (non-fatal): {e}")


# 语义化别名，供 Consumer 直接调用
persist = SessionPersistence.dual_write
save_conv = SessionPersistence.save_conversation
