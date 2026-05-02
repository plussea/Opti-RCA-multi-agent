"""诊断 Agent（LLM 增强版 + 知识图谱感知）"""
import logging
from typing import Any, Dict, List, Optional

from omniops.agents.base import BaseAgent
from omniops.core.prompts import (
    DIAGNOSIS_SYSTEM_PROMPT,
    DIAGNOSIS_USER_TEMPLATE,
    get_alarm_dict_text,
)
from omniops.models import CognitiveSummary, DiagnosisResult, Evidence, Session
from omniops.rag import search_similar_cases

logger = logging.getLogger(__name__)


class DiagnosisAgent(BaseAgent):
    """诊断 Agent：基于 LLM + 规则 + RAG 进行根因分析"""

    name = "diagnosis"

    async def process(
        self,
        session: Session,
        context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveSummary:
        """分析告警表，输出根因假设（优先规则，辅以 LLM）"""
        records = session.structured_data

        # 规则推理：基于已知告警码模式
        alarm_codes = []
        for r in records:
            if r.alarm_code:
                alarm_codes.append(r.alarm_code)

        # 搜索相似案例
        similar_cases = []
        if alarm_codes:
            try:
                case_results = await search_similar_cases(
                    query=" ".join(alarm_codes),
                    alarm_codes=list(set(alarm_codes)),
                    top_k=3,
                )
                similar_cases = case_results
            except Exception as e:
                logger.warning(f"RAG search failed: {e}")

        # 知识图谱查询（诊断 Agent 专用，<500ms 目标）
        kg_context: Dict[str, Any] = {"subgraph_paths": [], "community_summaries": [], "rules": []}
        try:
            from omniops.knowledge.neo4j_client import get_neo4j_client
            client = get_neo4j_client()
            kg_result = await client.query_session(
                structured_data=records,
                hops=2,
                top_k=5,
            )
            kg_context = {
                "subgraph_paths": kg_result.get("subgraph_paths", []),
                "community_summaries": kg_result.get("community_summaries", []),
                "rules": kg_result.get("rules", []),
            }
            logger.info(f"[Diagnosis] KG query done, latency={kg_result.get('query_latency_ms', 0)}ms, "
                        f"paths={len(kg_context['subgraph_paths'])}, "
                        f"communities={len(kg_context['community_summaries'])}")
        except Exception as e:
            logger.warning(f"[Diagnosis] KG query failed, falling back to pure RAG: {e}")

        # 尝试规则匹配
        root_cause, confidence, evidence = self._rule_based_diagnosis(records, alarm_codes)

        # 如果配置了 LLM provider，尝试 LLM 增强
        try:
            from omniops.core.providers import get_provider
            get_provider()
            try:
                llm_result = await self._llm_diagnosis(
                    records=records,
                    similar_cases=similar_cases,
                    kg_context=kg_context,
                )
                # 融合 LLM 结果和规则结果
                if llm_result and llm_result.get("confidence", 0) > confidence:
                    root_cause = llm_result["root_cause"]
                    confidence = llm_result["confidence"]
                    if llm_result.get("evidence"):
                        evidence = [Evidence(**e) for e in llm_result["evidence"]]
            except Exception as e:
                logger.warning(f"LLM diagnosis failed, falling back to rules: {e}")
        except Exception:
            pass  # No LLM provider configured, skip

        # 构建诊断结果
        diagnosis = DiagnosisResult(
            root_cause=root_cause,
            confidence=confidence,
            evidence=evidence,
            uncertainty=self._assess_uncertainty(records),
            agent_chain=[self.name],
        )

        session.diagnosis_result = diagnosis

        return CognitiveSummary(
            from_agent=self.name,
            to_agent="impact",
            session_id=session.session_id,
            conclusion=root_cause,
            confidence=confidence,
            evidence=[e.model_dump() for e in evidence],
            uncertainty=diagnosis.uncertainty,
            required_action="根据根因评估影响范围",
            context_window_used=len(records),
        )

    async def _llm_diagnosis(
        self,
        records: List[Any],
        similar_cases: List[Dict[str, Any]],
        kg_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """使用 LLM 进行诊断（注入图谱知识）"""
        try:
            # 构建告警表文本
            alarms_text = "\n".join([
                f"- {r.ne_name}: {r.alarm_code or r.alarm_name or 'unknown'} "
                f"({r.severity.value if r.severity else 'unknown'}) "
                f"at {r.occur_time or 'unknown'}"
                for r in records
            ])

            # 构建相似案例文本
            cases_text = "\n".join([
                f"- [{c['metadata'].get('root_cause', 'unknown')}] "
                f"(相似度: {c['similarity']:.2f})"
                for c in similar_cases[:3]
            ]) if similar_cases else "无相似案例"

            # 构建图谱知识文本
            kg_text = ""
            if kg_context:
                paths = kg_context.get("subgraph_paths", [])
                communities = kg_context.get("community_summaries", [])
                rules = kg_context.get("rules", [])
                if paths:
                    kg_text += f"\n【图谱关联路径】\n" + "\n".join(f"  • {p}" for p in paths[:5])
                if communities:
                    kg_text += f"\n【相关社区】\n"
                    for c in communities[:3]:
                        kg_text += f"  • {c.get('name','?')}: {c.get('summary','')[:80]}\n"
                if rules:
                    kg_text += f"\n【适用规则】\n"
                    for r in rules[:3]:
                        kg_text += f"  • {r.get('name','?')}: {r.get('content','')[:80]}\n"

            user_message = DIAGNOSIS_USER_TEMPLATE.format(
                alarms=alarms_text,
                similar_cases=cases_text,
                alarm_dict=get_alarm_dict_text(),
                kg_context=kg_text or "（图谱暂无可用知识）",
            )

            from omniops.core.providers import get_provider
            provider = get_provider()
            result = await provider.generate_json(
                system=DIAGNOSIS_SYSTEM_PROMPT,
                user_message=user_message,
            )

            return result

        except Exception as e:
            logger.error(f"LLM diagnosis failed: {e}")
            return None

    def _rule_based_diagnosis(
        self,
        records: List[Any],
        alarm_codes: List[str],
    ) -> tuple:
        """基于规则的诊断逻辑 — 支持光网络告警码和告警名称"""
        alarm_names: List[str] = []
        for r in records:
            if r.alarm_name:
                alarm_names.append(r.alarm_name)

        all_codes = set(alarm_codes)
        all_names = set(alarm_names)

        # 光网络告警模式（优先级从高到低）
        patterns = [
            # ---- 光链路中断类 ----
            ({"OTS_LOS", "OMS_LOS_P", "OCH_LOS_P"}, 0.92, "光链路信号丢失（OTS/OMS/OCH LOS）", "link_los"),
            ({"OCH_LOS_P"}, 0.90, "光通道信号丢失（OCH_LOS_P）", "och_los"),
            ({"OTS_LOS"}, 0.91, "光发送段信号丢失（OTS_LOS）", "ots_los"),
            ({"OMS_LOS_P"}, 0.89, "光复用段信号丢失（OMS_LOS_P）", "oms_los"),
            # ---- 以太网/数据平面故障 ----
            ({"ETHOAM_SELF_LOOP"}, 0.88, "以太网 OAM 自环（ETHOAM_SELF_LOOP）", "eth_loop"),
            ({"PORT_EXC_TRAFFIC", "STORM_CUR_QUENUM_OVER", "FLOW_OVER"}, 0.87, "端口流量异常或广播风暴", "traffic"),
            ({"STORM_CUR_QUENUM_OVER"}, 0.86, "广播风暴（STORM_CUR_QUENUM_OVER）", "storm"),
            ({"FLOW_OVER"}, 0.85, "流量溢出（FLOW_OVER）", "flow"),
            # ---- 光模块/硬件故障 ----
            ({"LSR_WILL_DIE"}, 0.85, "光模块即将失效（LSR_WILL_DIE）", "module"),
            ({"LASER_MODULE_MISMATCH"}, 0.84, "光模块型号不匹配", "module_mismatch"),
            # ---- 数据库/配置类 ----
            ({"DBMS_ERROR"}, 0.82, "数据库故障（DBMS_ERROR）", "db"),
            ({"DB_MEM_DIFF"}, 0.78, "数据库内存状态不一致（DB_MEM_DIFF）", "db"),
            ({"CFG_DATASAVE_FAIL"}, 0.76, "配置保存失败（CFG_DATASAVE_FAIL）", "config"),
            # ---- 告警名称匹配（备用） ----
            (set(), 0.83, "光链路信号丢失", "och_los_fallback", {"OCH_LOS_P"}),
            (set(), 0.82, "光模块老化或故障", "module_fallback", {"LSR_WILL_DIE"}),
            (set(), 0.87, "以太网 OAM 自环故障", "eth_loop_fallback", {"ETHOAM_SELF_LOOP"}),
            (set(), 0.86, "端口流量异常", "traffic_fallback", {"PORT_EXC_TRAFFIC"}),
            (set(), 0.83, "广播风暴", "storm_fallback", {"STORM_CUR_QUENUM_OVER"}),
            (set(), 0.88, "光链路断路故障", "los_fallback", {"OTS_LOS"}),
        ]

        for pattern in patterns:
            codes_to_match = pattern[0]
            conf = pattern[1]
            cause = pattern[2]
            fallback_names = pattern[4] if len(pattern) > 4 else set()

            matched = False
            if codes_to_match:
                # 非空码集合：要求所有码都出现在告警码中
                matched = codes_to_match.issubset(all_codes)
            elif fallback_names:
                # 空码集合 + 告警名称回退：当告警码全为空时才按名称匹配
                matched = not all_codes and fallback_names.issubset(all_names)

            if matched:
                evidence = []
                for r in records:
                    if r.alarm_code and r.alarm_code in codes_to_match:
                        evidence.append(Evidence(type="alarm", source=r.ne_name, code=r.alarm_code))
                    elif r.alarm_name and fallback_names and r.alarm_name in fallback_names:
                        evidence.append(Evidence(type="alarm", source=r.ne_name, code=r.alarm_name))
                return cause, conf, evidence

        # 默认诊断
        top_code = max(set(alarm_codes), key=lambda x: alarm_codes.count(x), default=None)
        if not top_code and alarm_names:
            top_name = max(alarm_names, key=lambda x: alarm_names.count(x))
            return (
                f"初步判定：{top_name} 告警为主，需进一步分析",
                0.60,
                [
                    Evidence(type="alarm", source=r.ne_name, code=r.alarm_name)
                    for r in records[:3]
                    if r.alarm_name == top_name
                ],
            )

        return (
            f"初步判定：{top_code or '未知'} 告警为主，需进一步分析",
            0.60,
            [
                Evidence(type="alarm", source=r.ne_name, code=top_code)
                for r in records[:3]
                if r.alarm_code == top_code
            ],
        )

    def _assess_uncertainty(self, records: List[Any]) -> Optional[str]:
        """评估诊断不确定性"""
        if not records:
            return "无告警数据，无法诊断"

        has_unknown_code = any(not r.alarm_code for r in records)

        if has_unknown_code:
            return "部分告警缺少告警码，影响诊断准确率，建议补充完整信息"

        return None
