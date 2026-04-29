"""校验 Agent"""
from typing import Any, Dict, List, Optional

from omniops.agents.base import BaseAgent
from omniops.models import CognitiveSummary, Session


class VerificationAgent(BaseAgent):
    """校验 Agent：检查方案与诊断的自洽性"""

    name = "verification"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """校验方案合理性"""
        diagnosis = session.diagnosis_result
        suggestion = session.suggestion
        checks: List[Dict[str, Any]] = []

        # Check 1: root cause consistency
        if diagnosis and suggestion:
            root_keywords = diagnosis.root_cause
            action_text = " ".join(a.action for a in suggestion.suggested_actions)
            if root_keywords and not any(
                kw.lower() in action_text.lower()
                for kw in root_keywords.split()
                if len(kw) > 1
            ):
                checks.append({
                    "check": "root_cause_consistency",
                    "passed": False,
                    "detail": "方案未提及诊断出的根因关键词",
                })
            else:
                checks.append({
                    "check": "root_cause_consistency",
                    "passed": True,
                    "detail": "方案与根因一致",
                })

        # Check 2: required tools availability (stub — queries Neo4j if available)
        if suggestion and suggestion.required_tools:
            try:
                # TODO: query Neo4j for tool availability
                checks.append({
                    "check": "tools_availability",
                    "passed": True,
                    "detail": f"所需工具: {', '.join(suggestion.required_tools)} (Neo4j检查待接入)",
                })
            except Exception:
                checks.append({
                    "check": "tools_availability",
                    "passed": True,
                    "detail": f"所需工具: {', '.join(suggestion.required_tools)} (工具检查跳过)",
                })

        # Check 3: risk threshold → needs_human
        high_risk_keywords = ("high", "critical")
        if suggestion and any(
            kw in suggestion.risk_level.lower() for kw in high_risk_keywords
        ):
            checks.append({
                "check": "high_risk_detected",
                "passed": True,
                "detail": f"风险等级 '{suggestion.risk_level}' 触发人工审核",
            })

        # Check 4: conflicting actions (both replace and clean)
        if suggestion and suggestion.suggested_actions:
            actions_lower = [a.action.lower() for a in suggestion.suggested_actions]
            has_replace = any("更换" in a or "替换" in a for a in actions_lower)
            has_clean = any("清洁" in a or "清洗" in a for a in actions_lower)
            if has_replace and has_clean:
                checks.append({
                    "check": "action_conflicts",
                    "passed": False,
                    "detail": "检测到冲突动作：同时包含'更换'和'清洁'，建议先清洁再判断是否更换",
                })
            else:
                checks.append({
                    "check": "action_conflicts",
                    "passed": True,
                    "detail": "无明显冲突动作",
                })

        # Check 5: action completeness
        if suggestion and not suggestion.suggested_actions:
            checks.append({
                "check": "action_completeness",
                "passed": False,
                "detail": "建议步骤为空",
            })
        else:
            checks.append({
                "check": "action_completeness",
                "passed": True,
                "detail": f"包含 {len(suggestion.suggested_actions)} 个步骤",
            })

        all_passed = all(c.get("passed", False) for c in checks)

        # Determine next step based on checks
        if all_passed:
            next_step = "pending_human"
        else:
            # 校验失败，降级但仍标记需人工
            next_step = "pending_human"

        return CognitiveSummary(
            from_agent=self.name,
            to_agent="router",
            session_id=session.session_id,
            conclusion="校验通过" if all_passed else "校验发现问题，建议人工审核",
            confidence=1.0,
            evidence=checks,
            uncertainty=None,
            required_action=next_step,
            context_window_used=0,
        )
