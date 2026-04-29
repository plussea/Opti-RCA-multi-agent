"""会话存储测试"""
import threading
from datetime import datetime, timedelta

from omniops.memory.store import (
    InMemorySessionStore,
    generate_session_id,
)
from omniops.models import AlarmRecord, InputType, Session, SessionStatus


class TestInMemorySessionStore:
    def setup_method(self):
        self.store = InMemorySessionStore(ttl_seconds=2)

    def _create_session(self, **kwargs) -> Session:
        defaults = {
            "session_id": generate_session_id(),
            "input_type": InputType.CSV,
            "structured_data": [AlarmRecord(ne_name="NE-01", alarm_code="LINK_FAIL")],
            "status": SessionStatus.ANALYZING,
        }
        defaults.update(kwargs)
        return Session(**defaults)

    def test_create_and_get(self):
        session = self._create_session()
        self.store.create(session)

        retrieved = self.store.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_get_nonexistent(self):
        result = self.store.get("nonexistent_id")
        assert result is None

    def test_update(self):
        session = self._create_session()
        self.store.create(session)

        updated = self.store.update(
            session.session_id,
            status=SessionStatus.COMPLETED,
        )
        assert updated is not None
        assert updated.status == SessionStatus.COMPLETED

    def test_update_nonexistent(self):
        result = self.store.update("nonexistent_id", status=SessionStatus.COMPLETED)
        assert result is None

    def test_delete(self):
        session = self._create_session()
        self.store.create(session)

        assert self.store.delete(session.session_id) is True
        assert self.store.get(session.session_id) is None

    def test_delete_nonexistent(self):
        assert self.store.delete("nonexistent_id") is False

    def test_list_active(self):
        session1 = self._create_session(status=SessionStatus.ANALYZING)
        session2 = self._create_session(status=SessionStatus.COMPLETED)
        session3 = self._create_session(status=SessionStatus.REJECTED)

        self.store.create(session1)
        self.store.create(session2)
        self.store.create(session3)

        active = self.store.list_active()
        assert len(active) == 1
        assert active[0].status == SessionStatus.ANALYZING

    def test_cleanup_expired(self):
        session = self._create_session()
        session.created_at = datetime.utcnow() - timedelta(seconds=5)
        self.store.create(session)

        removed = self.store.cleanup_expired()
        assert removed == 1
        assert self.store.get(session.session_id) is None

    def test_thread_safety(self):
        errors = []

        def worker():
            try:
                for _ in range(100):
                    session = self._create_session()
                    self.store.create(session)
                    self.store.get(session.session_id)
                    self.store.delete(session.session_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestGenerateSessionId:
    def test_format(self):
        sid = generate_session_id()
        assert sid.startswith("sess_")
        parts = sid.split("_")
        # sess_YYYYMMDD_HHMMSS_uid → 4 parts (underscore in timestamp)
        assert len(parts) >= 4
        # Date part (parts[1]) should be 8 chars
        assert len(parts[1]) == 8
        # Time part (parts[2]) should be 6 chars
        assert len(parts[2]) == 6
        # UID (last part) should be 6 chars
        assert len(parts[-1]) == 6

    def test_uniqueness(self):
        ids = {generate_session_id() for _ in range(100)}
        assert len(ids) == 100
