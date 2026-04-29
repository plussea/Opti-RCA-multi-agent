"""OmniOps Multi-Agent 系统全流程 Demo

运行方式:
    uv run python demo.py

功能:
    1. 构造模拟告警数据（模拟 CSV 摄取）
    2. 展示事件驱动状态机：perception → diagnosis → impact → planning
    3. 全程打印每个 Agent 的输入/输出 + 状态转换
    4. 所有存储使用内存实现，无需 Redis/PostgreSQL
    5. LLM 使用 OpenRouter（已在 .env 配置）
    6. 展示 VerificationAgent 校验结果
"""
import asyncio
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# ── path & env ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:7897")
os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:7897")

env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    from dotenv import load_dotenv
    load_dotenv(env_path)
    os.environ["LLM_PROVIDER"] = "openrouter"

# Clear caches
from omniops.core.config import get_settings
get_settings.cache_clear()
from omniops.core.providers import _cache
_cache.clear()

# ── imports ───────────────────────────────────────────────────────────────────
from omniops.agents import (
    DiagnosisAgent, ImpactAgent, PerceptionAgent, PlanningAgent, VerificationAgent,
)
from omniops.core.providers import get_provider
from omniops.memory.store import generate_session_id, get_session_store
from omniops.models import AlarmRecord, InputType, Severity, Session, SessionStatus
from omniops.router.context_router import AgentMode, ContextRouter

# ── mock alarm data ───────────────────────────────────────────────────────────
DEMO_ALARMS: List[Dict[str, Any]] = [
    {
        "ne_name": "NE-BJ-CORE-01",
        "alarm_code": "LOS",
        "alarm_name": "光信号丢失",
        "severity": Severity.CRITICAL,
        "occur_time": datetime(2026, 4, 29, 8, 15, 0),
        "shelf": "SHELF-A",
        "slot": "SLOT-03",
        "board_type": "OTU-100G",
    },
    {
        "ne_name": "NE-BJ-CORE-01",
        "alarm_code": "OTU_LOF",
        "alarm_name": "光通道帧丢失",
        "severity": Severity.CRITICAL,
        "occur_time": datetime(2026, 4, 29, 8, 15, 3),
        "shelf": "SHELF-A",
        "slot": "SLOT-03",
        "board_type": "OTU-100G",
    },
    {
        "ne_name": "NE-SH-METRO-02",
        "alarm_code": "LINK_FAIL",
        "alarm_name": "链路故障",
        "severity": Severity.MAJOR,
        "occur_time": datetime(2026, 4, 29, 8, 16, 0),
        "shelf": "SHELF-B",
        "slot": "SLOT-07",
        "board_type": "FOIC-10G",
    },
    {
        "ne_name": "NE-SZ-AGG-03",
        "alarm_code": "BER_HIGH",
        "alarm_name": "误码率高",
        "severity": Severity.MAJOR,
        "occur_time": datetime(2026, 4, 29, 8, 20, 0),
        "shelf": "SHELF-A",
        "slot": "SLOT-01",
        "board_type": "OTU-10G",
    },
    {
        "ne_name": "NE-GZ-EDGE-04",
        "alarm_code": "BD_STATUS",
        "alarm_name": "板卡状态异常",
        "severity": Severity.MINOR,
        "occur_time": datetime(2026, 4, 29, 8, 22, 0),
        "shelf": "SHELF-C",
        "slot": "SLOT-02",
        "board_type": "MSTP-STM1",
    },
]


def print_banner(title: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_section(title: str) -> None:
    print()
    print(f"─── {title} ───")


async def run_demo() -> None:
    print_banner("OmniOps Multi-Agent System — Demo")

    # 0. Provider info
    print_section("LLM Provider")
    provider = get_provider("openrouter")
    print(f"  Provider  : {type(provider).__name__}")
    print(f"  Model    : {provider.config.model}")
    print(f"  Base URL : {provider.config.base_url}")
    print(f"  API Key  : {provider.config.api_key[:12]}***")

    # 1. Create session
    print_section("Step 1 — 创建会话 (Session)")
    session_id = generate_session_id()
    records = [AlarmRecord(**d) for d in DEMO_ALARMS]
    session = Session(
        session_id=session_id,
        input_type=InputType.CSV,
        structured_data=records,
        status=SessionStatus.ANALYZING,
        current_step="init",
    )
    print(f"  session_id : {session_id}")
    print(f"  input_type : {session.input_type.value}")
    print(f"  alarms     : {len(records)} 条")
    for r in records:
        print(f"    [{r.severity.value:8s}] {r.ne_name:20s} {r.alarm_code:12s} {r.alarm_name}")

    # 2. Perception Agent
    print_section("Step 2 — Perception Agent (感知)")
    perception = PerceptionAgent()
    p_result = await perception.process(session)
    # 状态机推进
    router = ContextRouter()
    router.route_after_agent(session, "perception")
    print(f"  conclusion  : {p_result.conclusion}")
    print(f"  confidence : {p_result.confidence}")
    print(f"  metadata   : {session.perception_metadata}")
    print(f"  [状态机] current_step={session.current_step} status={session.status.value}")

    # 3. Context Router
    print_section("Step 3 — Context Router (路由决策)")
    mode = router.decide_mode(session)
    chain = router.build_agent_chain(mode)
    hitl = router.should_trigger_hitl(session)
    print(f"  mode     : {mode.value}")
    print(f"  chain    : {' → '.join(chain)}")
    print(f"  HITL     : {'是 (Critical告警，触发人工审核)' if hitl else '否'}")
    print(f"  reason   : 告警数量={len(records)}, 阈值={router.settings.single_agent_threshold}")

    # 4. Agent chain with state machine
    print_section("Step 4 — Agent Chain 执行 (事件驱动)")

    for agent_name in chain:
        if agent_name == "perception":
            continue  # 已执行

        print(f"\n  [{agent_name.upper()}]")

        if agent_name == "diagnosis":
            router.route_after_agent(session, agent_name)
            print(f"  [状态机] → {agent_name}: current_step={session.current_step}")
            print("  > 调用 LLM 进行根因分析 (OpenRouter)...")
            diag_agent = DiagnosisAgent()
            d_result = await diag_agent.process(session)
            print(f"  > conclusion : {d_result.conclusion}")
            print(f"  > confidence : {d_result.confidence}")
            print(f"  > evidence   : {len(d_result.evidence)} 条")
            if session.diagnosis_result:
                print(f"  > root_cause : {session.diagnosis_result.root_cause}")
                print(f"  > uncertainty: {session.diagnosis_result.uncertainty}")
            # 路由决定下一步
            next_step = router.decide_next_agent_after_completion(session)
            print(f"  [Router] 下一步: {next_step}")

        elif agent_name == "impact":
            router.route_after_agent(session, agent_name)
            print(f"  [状态机] → {agent_name}: current_step={session.current_step}")
            imp_agent = ImpactAgent()
            i_result = await imp_agent.process(session)
            print(f"  > conclusion : {i_result.conclusion}")
            if session.impact:
                print(f"  > affected_ne       : {session.impact.affected_ne}")
                print(f"  > affected_links    : {session.impact.affected_links}")
                print(f"  > affected_services : {session.impact.affected_services}")
            next_step = router.decide_next_agent_after_completion(session)
            print(f"  [Router] 下一步: {next_step}")

        elif agent_name == "planning":
            router.route_after_agent(session, agent_name)
            print(f"  [状态机] → {agent_name}: current_step={session.current_step}")
            print("  > 调用 LLM 生成修复方案 (OpenRouter)...")
            plan_agent = PlanningAgent()
            pl_result = await plan_agent.process(session)
            print(f"  > conclusion : {pl_result.conclusion}")
            if session.suggestion:
                print(f"  > risk_level    : {session.suggestion.risk_level}")
                print(f"  > needs_approval: {session.suggestion.needs_approval}")
                print(f"  > actions       :")
                for act in session.suggestion.suggested_actions:
                    print(f"      Step {act.step}: {act.action} ({act.estimated_time})")
                print(f"  > required_tools: {session.suggestion.required_tools}")
                print(f"  > fallback_plan  : {session.suggestion.fallback_plan}")
            next_step = router.decide_next_agent_after_completion(session)
            print(f"  [Router] 下一步: {next_step}")

    # 5. Verification Agent
    print_section("Step 5 — Verification Agent (校验)")
    router.route_after_agent(session, "planning")
    print(f"  [状态机] → verification: current_step={session.current_step}")
    verify_agent = VerificationAgent()
    v_result = await verify_agent.process(session)
    print(f"  > conclusion : {v_result.conclusion}")
    print(f"  > checks     :")
    for ev in v_result.evidence:
        icon = "[PASS]" if ev.get("passed") else "[FAIL]"
        print(f"      {icon} {ev['check']}: {ev['detail']}")
    print(f"  > next_action: {v_result.required_action}")
    router.route_after_agent(session, "verification")
    print(f"  [状态机] → {session.current_step}: status={session.status.value}")

    # 6. Session storage (in-memory)
    print_section("Step 6 — 会话存储 (内存)")
    store = get_session_store()
    store.create(session)
    retrieved = store.get(session_id)
    print(f"  stored     : {session_id}")
    print(f"  retrieved  : {retrieved is not None}")
    print(f"  status     : {session.status.value}")
    print(f"  current_step: {session.current_step}")

    # 7. Final result
    print_section("Step 7 — 最终输出")
    print(f"  session_id    : {session.session_id}")
    print(f"  status       : {session.status.value}")
    print(f"  current_step : {session.current_step}")
    print(f"  root_cause   : {session.diagnosis_result.root_cause if session.diagnosis_result else 'N/A'}")
    print(f"  confidence   : {session.diagnosis_result.confidence if session.diagnosis_result else 0:.2f}")
    print(f"  risk_level   : {session.suggestion.risk_level if session.suggestion else 'N/A'}")
    print(f"  action_count : {len(session.suggestion.suggested_actions) if session.suggestion else 0}")
    print(f"  HITL         : {'是 (需人工审核)' if hitl else '否'}")

    print_banner("Demo 完成")


if __name__ == "__main__":
    asyncio.run(run_demo())
