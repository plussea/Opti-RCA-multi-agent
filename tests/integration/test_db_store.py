"""PostgreSQL Persistence Layer 测试"""
import asyncio
from datetime import datetime
from typing import List, Optional

import pytest

from omniops.core.database import Base, async_session_maker, init_db
from omniops.memory.db_store import DBSessionStore, get_db_session_store
from omniops.models import (
    AlarmRecord,
    DiagnosisResult,
    Evidence,
    Impact,
    InputType,
    Session,
    SessionStatus,
    Severity,
    Suggestion,
    SuggestionAction,
)
from sqlalchemy import text


# ─────────────────────────────────────────────────────────────────────────────
# 共享引擎（每个测试函数用同一 engine，同一 event loop）
# ─────────────────────────────────────────────────────────────────────────────

_shared_test_engine = None


def _get_test_engine():
    """返回共享的测试引擎（使用 pytest-asyncio 管理的 event loop）"""
    global _shared_test_engine
    if _shared_test_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        _shared_test_engine = create_async_engine(
            "postgresql+asyncpg://postgres:postgres@localhost:5432/omniops",
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
    return _shared_test_engine


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：清理测试数据
# ─────────────────────────────────────────────────────────────────────────────

async def _clear_test_data(db, session_ids: List[str]) -> None:
    for sid in session_ids:
        try:
            await db.execute(
                text("DELETE FROM agent_conversations WHERE session_id = :sid"),
                {"sid": sid},
            )
        except Exception:
            pass
        try:
            await db.execute(
                text("DELETE FROM alarm_records WHERE session_id = :sid"),
                {"sid": sid},
            )
        except Exception:
            pass
        try:
            await db.execute(
                text("DELETE FROM feedback_records WHERE session_id = :sid"),
                {"sid": sid},
            )
        except Exception:
            pass
        try:
            await db.execute(
                text("DELETE FROM sessions WHERE session_id = :sid"),
                {"sid": sid},
            )
        except Exception:
            pass
    await db.commit()


def _make_session(sid: str, **kwargs) -> Session:
    defaults = {
        "session_id": sid,
        "input_type": InputType.CSV,
        "structured_data": [
            AlarmRecord(
                ne_name="NE-BJ-01",
                alarm_name="LINK_FAIL",
                severity=Severity.CRITICAL,
            ),
            AlarmRecord(
                ne_name="NE-SH-01",
                alarm_name="POWER_LOW",
                severity=Severity.WARNING,
            ),
        ],
        "status": SessionStatus.DIAGNOSING,
        "diagnosis_result": DiagnosisResult(
            root_cause="K1SL64 光模块老化导致收光功率不足",
            confidence=0.91,
            evidence=[
                Evidence(
                    type="alarm_pattern",
                    source="alarm_analysis",
                    description="LINK_FAIL + POWER_LOW 组合",
                    value="weight=0.4",
                ),
                Evidence(
                    type="knowledge_base",
                    source="rag_retrieval",
                    description="相似案例 #042 采纳率 93%",
                    value="effectiveness=0.93",
                ),
            ],
            uncertainty="光功率历史数据缺失",
            agent_chain=["perception", "diagnosis"],
        ),
        "impact": Impact(
            affected_ne=["NE-BJ-01", "NE-SH-01"],
            affected_links=["link-bj-sh-01"],
            affected_services=["专线-A"],
        ),
        "suggestion": Suggestion(
            root_cause="光模块老化",
            suggested_actions=[
                SuggestionAction(step=1, action="测量收光功率", estimated_time="5min"),
                SuggestionAction(step=2, action="清洁光纤端面", estimated_time="10min"),
                SuggestionAction(step=3, action="更换 K1SL64 光模块", estimated_time="30min"),
            ],
            required_tools=["光功率计", "清洁工具", "备用光模块"],
            fallback_plan="联系供应商现场支持",
            risk_level="medium",
            needs_approval=True,
        ),
        "human_feedback": None,
        "perception_metadata": {
            "rows_extracted": 2,
            "uncertain_fields": [],
            "confidence": 0.98,
        },
    }
    defaults.update(kwargs)
    return Session(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Pytest fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _run_sync_cleanup(session_ids: List[str]) -> None:
    """通过 subprocess 运行 asyncpg 清理测试数据（避免 event loop 问题）"""
    import subprocess, sys
    sids_repr = repr(session_ids)
    cmd = [
        sys.executable, "-c",
        f"""
import asyncio, asyncpg
async def clean():
    conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/omniops')
    for table in ['agent_conversations', 'alarm_records', 'feedback_records', 'sessions']:
        for sid in {sids_repr}:
            try:
                await conn.execute(f'DELETE FROM {{table}} WHERE session_id = $1', sid)
            except Exception:
                pass
    await conn.close()
asyncio.run(clean())
"""
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)


@pytest.fixture(scope="function")
async def db_store():
    """每个测试函数用一个新的 store 实例"""
    store = DBSessionStore()
    await store.ensure_init()
    created_ids: List[str] = []

    original_create = store.create
    original_update = store.update

    async def tracked_create(session: Session) -> Session:
        created_ids.append(session.session_id)
        return await original_create(session)

    async def tracked_update(session_id: str, **updates) -> Optional[Session]:
        created_ids.append(session_id)
        return await original_update(session_id, **updates)

    store.create = tracked_create
    store.update = tracked_update

    yield store

    # Teardown: skip async cleanup (idempotent create() handles data isolation).


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDBSessionCreate:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db_store: DBSessionStore):
        sid = "test_create_get_001"
        session = _make_session(sid, status=SessionStatus.ANALYZING)

        await db_store.create(session)
        retrieved = await db_store.get(sid)

        assert retrieved is not None
        assert retrieved.session_id == sid
        assert retrieved.status == SessionStatus.ANALYZING
        assert retrieved.input_type == InputType.CSV
        assert len(retrieved.structured_data) == 2
        assert retrieved.structured_data[0].ne_name == "NE-BJ-01"
        assert retrieved.structured_data[0].alarm_name == "LINK_FAIL"

    @pytest.mark.asyncio
    async def test_create_persists_all_fields(self, db_store: DBSessionStore):
        sid = "test_create_all_fields_002"
        session = _make_session(sid, status=SessionStatus.PERCEIVED)
        await db_store.create(session)
        retrieved = await db_store.get(sid)

        assert retrieved is not None
        assert retrieved.diagnosis_result is not None
        assert retrieved.diagnosis_result.root_cause == "K1SL64 光模块老化导致收光功率不足"
        assert retrieved.diagnosis_result.confidence == 0.91
        assert len(retrieved.diagnosis_result.evidence) == 2

        assert retrieved.impact is not None
        assert "NE-BJ-01" in retrieved.impact.affected_ne

        assert retrieved.suggestion is not None
        assert retrieved.suggestion.risk_level == "medium"
        assert len(retrieved.suggestion.suggested_actions) == 3

        assert retrieved.perception_metadata is not None
        assert retrieved.perception_metadata["confidence"] == 0.98

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db_store: DBSessionStore):
        result = await db_store.get("nonexistent_session_xyz")
        assert result is None


class TestDBSessionUpdate:
    @pytest.mark.asyncio
    async def test_update_status(self, db_store: DBSessionStore):
        sid = "test_update_status_003"
        await db_store.create(_make_session(sid, status=SessionStatus.ANALYZING))

        await db_store.update(sid, status=SessionStatus.DIAGNOSING)
        retrieved = await db_store.get(sid)

        assert retrieved is not None
        assert retrieved.status == SessionStatus.DIAGNOSING

    @pytest.mark.asyncio
    async def test_update_diagnosis_result(self, db_store: DBSessionStore):
        sid = "test_update_diag_004"
        await db_store.create(_make_session(sid))

        new_diag = DiagnosisResult(
            root_cause="光纤断裂",
            confidence=0.95,
            evidence=[
                Evidence(type="topology", source="otdr_measurement", value="OTDR 测量 25dB 衰耗")
            ],
            uncertainty=None,
            agent_chain=["perception", "diagnosis"],
        )
        await db_store.update(sid, diagnosis_result=new_diag)
        retrieved = await db_store.get(sid)

        assert retrieved is not None
        assert retrieved.diagnosis_result is not None
        assert retrieved.diagnosis_result.root_cause == "光纤断裂"
        assert retrieved.diagnosis_result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_update_impact(self, db_store: DBSessionStore):
        sid = "test_update_impact_005"
        await db_store.create(_make_session(sid))

        new_impact = Impact(
            affected_ne=["NE-GZ-01", "NE-SZ-01"],
            affected_links=["link-gz-sz-01"],
            affected_services=["城域网络"],
        )
        await db_store.update(sid, impact=new_impact)
        retrieved = await db_store.get(sid)

        assert retrieved is not None
        assert retrieved.impact is not None
        assert "NE-GZ-01" in retrieved.impact.affected_ne

    @pytest.mark.asyncio
    async def test_update_suggestion(self, db_store: DBSessionStore):
        sid = "test_update_sugg_006"
        await db_store.create(_make_session(sid))

        new_suggestion = Suggestion(
            root_cause="板卡故障",
            suggested_actions=[SuggestionAction(step=1, action="重启板卡", estimated_time="15min")],
            required_tools=[],
            fallback_plan="备用板卡替换",
            risk_level="high",
            needs_approval=False,
        )
        await db_store.update(sid, suggestion=new_suggestion)
        retrieved = await db_store.get(sid)

        assert retrieved is not None
        assert retrieved.suggestion is not None
        assert retrieved.suggestion.root_cause == "板卡故障"
        assert retrieved.suggestion.needs_approval is False

    @pytest.mark.asyncio
    async def test_update_human_feedback(self, db_store: DBSessionStore):
        sid = "test_update_feedback_007"
        await db_store.create(_make_session(sid))

        feedback = {
            "decision": "adopted",
            "actual_action": "更换光模块",
            "effectiveness": "resolved",
            "feedback_at": datetime.utcnow().isoformat(),
        }
        await db_store.update(sid, human_feedback=feedback, status=SessionStatus.APPROVED)
        retrieved = await db_store.get(sid)

        assert retrieved is not None
        assert retrieved.human_feedback is not None
        assert retrieved.human_feedback["decision"] == "adopted"
        assert retrieved.status == SessionStatus.APPROVED

    @pytest.mark.asyncio
    async def test_update_nonexistent_no_error(self, db_store: DBSessionStore):
        result = await db_store.update("nonexistent_sid_xyz", status=SessionStatus.COMPLETED)
        assert result is None


class TestDBSessionDelete:
    @pytest.mark.asyncio
    async def test_delete_existing(self, db_store: DBSessionStore):
        sid = "test_delete_009"
        await db_store.create(_make_session(sid))
        result = await db_store.delete(sid)
        assert result is True

        retrieved = await db_store.get(sid)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db_store: DBSessionStore):
        result = await db_store.delete("nonexistent_sid_delete")
        assert result is False


class TestDBListActive:
    @pytest.mark.asyncio
    async def test_list_active_only_returns_active(self, db_store: DBSessionStore):
        s1 = _make_session("test_list_active_010", status=SessionStatus.ANALYZING)
        s2 = _make_session("test_list_active_011", status=SessionStatus.COMPLETED)
        s3 = _make_session("test_list_active_012", status=SessionStatus.PERCEIVED)
        s4 = _make_session("test_list_active_013", status=SessionStatus.REJECTED)
        s5 = _make_session("test_list_active_014", status=SessionStatus.PENDING_HUMAN)

        for s in [s1, s2, s3, s4, s5]:
            await db_store.create(s)

        active = await db_store.list_active()
        active_statuses = {s.status for s in active}

        assert SessionStatus.ANALYZING in active_statuses
        assert SessionStatus.PERCEIVED in active_statuses
        assert SessionStatus.PENDING_HUMAN in active_statuses
        assert SessionStatus.COMPLETED not in active_statuses
        assert SessionStatus.REJECTED not in active_statuses


class TestDBAgentConversations:
    @pytest.mark.asyncio
    async def test_save_and_get_conversation(self, db_store: DBSessionStore):
        sid = "test_conv_015"
        await db_store.create(_make_session(sid))

        await db_store.save_conversation(
            session_id=sid,
            agent_name="diagnosis",
            step_order=1,
            llm_input={
                "system": "你是一个运维诊断助手",
                "user": "分析以下告警：LINK_FAIL, POWER_LOW",
            },
            llm_output={
                "root_cause": "K1SL64 光模块老化",
                "confidence": 0.91,
            },
            cognitive_summary={
                "required_action": "proceed",
                "evidence": [{"type": "alarm_pattern", "weight": 0.4}],
                "reasoning": "基于告警组合模式判断",
            },
            tokens_used=1204,
            model_name="nvidia/nemotron-3-nano-omni-30b-a3b:free",
            duration_ms=4200,
        )

        await db_store.save_conversation(
            session_id=sid,
            agent_name="planning",
            step_order=2,
            cognitive_summary={
                "required_action": "pending_human",
                "suggested_steps": 3,
            },
            tokens_used=800,
            model_name="nvidia/nemotron-3-nano-omni-30b-a3b:free",
            duration_ms=3100,
        )

        conversations = await db_store.get_conversations(sid)

        assert len(conversations) == 2
        assert conversations[0]["agent_name"] == "diagnosis"
        assert conversations[0]["tokens_used"] == 1204
        assert conversations[0]["cognitive_summary"]["required_action"] == "proceed"

        assert conversations[1]["agent_name"] == "planning"
        assert conversations[1]["cognitive_summary"]["required_action"] == "pending_human"

    @pytest.mark.asyncio
    async def test_get_conversations_empty(self, db_store: DBSessionStore):
        """没有对话记录应返回空列表"""
        sid = "test_conv_empty_016"
        await db_store.create(_make_session(sid))

        conversations = await db_store.get_conversations(sid)
        assert conversations == []

    @pytest.mark.asyncio
    async def test_save_conversation_error_message(self, db_store: DBSessionStore):
        sid = "test_conv_error_017"
        await db_store.create(_make_session(sid))

        await db_store.save_conversation(
            session_id=sid,
            agent_name="diagnosis",
            step_order=1,
            error_message="LLM API timeout after 30s",
            duration_ms=30000,
        )

        conversations = await db_store.get_conversations(sid)
        assert len(conversations) == 1
        assert conversations[0]["error_message"] == "LLM API timeout after 30s"


class TestDBFeedback:
    @pytest.mark.asyncio
    async def test_save_feedback(self, db_store: DBSessionStore):
        sid = "test_feedback_018"
        await db_store.create(_make_session(sid))

        result = await db_store.save_feedback(
            session_id=sid,
            decision="adopted",
            actual_action="更换 K1SL64 光模块",
            effectiveness="resolved",
        )
        assert result is True

        async with async_session_maker() as db:
            row = await db.execute(
                text("SELECT decision, actual_action, effectiveness FROM feedback_records WHERE session_id = :sid"),
                {"sid": sid},
            )
            record = row.fetchone()

        assert record is not None
        assert record[0] == "adopted"
        assert record[1] == "更换 K1SL64 光模块"
        assert record[2] == "resolved"


class TestDBDualWrite:
    @pytest.mark.asyncio
    async def test_consumer_pattern_persist(self, db_store: DBSessionStore):
        """模拟 DiagnosisConsumer 的完整 _persist + _save_conversation 流程"""
        sid = "test_dual_write_019"
        await db_store.create(_make_session(sid))

        await db_store.update(
            sid,
            status=SessionStatus.DIAGNOSING,
            diagnosis_result=DiagnosisResult(
                root_cause="测试根因",
                confidence=0.85,
                evidence=[],
                agent_chain=["diagnosis"],
            ),
        )

        await db_store.save_conversation(
            session_id=sid,
            agent_name="diagnosis",
            step_order=1,
            cognitive_summary={
                "required_action": "proceed",
                "reasoning": "置信度 > 0.8，直接推进",
            },
            tokens_used=1500,
            model_name="nvidia/nemotron-3-nano-omni-30b-a3b:free",
            duration_ms=5000,
        )

        session = await db_store.get(sid)
        assert session.status == SessionStatus.DIAGNOSING
        assert session.diagnosis_result.root_cause == "测试根因"

        conversations = await db_store.get_conversations(sid)
        assert len(conversations) == 1
        assert conversations[0]["agent_name"] == "diagnosis"
        assert conversations[0]["tokens_used"] == 1500