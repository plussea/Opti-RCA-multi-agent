"""会话存储 — 内存实现（接口预留，后续可替换为 Redis）"""
import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from omniops.models import Session, SessionStatus


class InMemorySessionStore:
    """线程安全的内存会话存储

    接口设计参考 Redis 存储，但实现为内存字典。
    后续可透明替换为 Redis 存储，无需修改调用方代码。
    """

    def __init__(self, ttl_seconds: int = 14400):
        self._store: Dict[str, Session] = {}
        self._lock = threading.RLock()
        self._ttl = timedelta(seconds=ttl_seconds)

    def create(self, session: Session) -> Session:
        """创建新会话"""
        with self._lock:
            self._store[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        with self._lock:
            return self._store.get(session_id)

    def update(self, session_id: str, **updates) -> Optional[Session]:
        """更新会话字段"""
        with self._lock:
            if session_id not in self._store:
                return None
            session = self._store[session_id]
            for key, value in updates.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            return session

    def delete(self, session_id: str) -> bool:
        """删除会话"""
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]
                return True
            return False

    def list_active(self) -> List[Session]:
        """列出所有活跃会话"""
        with self._lock:
            return [
                s for s in self._store.values()
                if s.status in (SessionStatus.ANALYZING, SessionStatus.NEEDS_REVIEW)
            ]

    def cleanup_expired(self) -> int:
        """清理过期会话，返回清理数量"""
        cutoff = datetime.utcnow() - self._ttl
        removed = 0
        with self._lock:
            expired_ids = [
                sid for sid, s in self._store.items()
                if s.created_at < cutoff
            ]
            for sid in expired_ids:
                del self._store[sid]
                removed += 1
        return removed


# 全局单例
_session_store: Optional[InMemorySessionStore] = None


def get_session_store() -> InMemorySessionStore:
    """获取会话存储单例"""
    global _session_store
    if _session_store is None:
        from omniops.core.config import get_settings
        settings = get_settings()
        _session_store = InMemorySessionStore(ttl_seconds=settings.working_memory_ttl)
    return _session_store


def generate_session_id() -> str:
    """生成唯一会话 ID"""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:6]
    return f"sess_{timestamp}_{uid}"
