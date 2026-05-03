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

        # 收集告警名称用于 RAG 检索
        alarm_names: List[str] = [r.alarm_name for r in records if r.alarm_name]

        # 搜索相似案例（RAG）
        similar_cases = []
        if alarm_names:
            try:
                case_results = await search_similar_cases(
                    query=" ".join(alarm_names),
                    alarm_codes=list(set(alarm_names)),
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

        # 规则匹配
        root_cause, confidence, evidence = self._rule_based_diagnosis(records, alarm_names)

        # 如果配置了 LLM provider，尝试 LLM 增强
        provider = None
        try:
            from omniops.core.providers import get_provider
            provider = get_provider()
        except Exception as e:
            logger.warning(f"[Diagnosis] LLM provider unavailable: {e}")

        if provider:
            try:
                logger.info(f"[Diagnosis] calling LLM for session={session.session_id}, alarm_count={len(records)}")
                llm_result = await self._llm_diagnosis(
                    records=records,
                    similar_cases=similar_cases,
                    kg_context=kg_context,
                )
                if llm_result and llm_result.get("confidence", 0) > confidence:
                    root_cause = llm_result["root_cause"]
                    confidence = llm_result["confidence"]
                    if llm_result.get("evidence"):
                        try:
                            evidence = [Evidence(**e) for e in llm_result["evidence"]]
                        except Exception as ev_err:
                            logger.warning(f"[Diagnosis] evidence parse failed: {ev_err}, keeping rule evidence")
                    logger.info(f"[Diagnosis] LLM accepted (confidence={confidence:.2f}) over rules (confidence=0.85)")
                elif llm_result:
                    logger.info(f"[Diagnosis] LLM result not better than rules, keeping rules")
                else:
                    logger.warning(f"[Diagnosis] LLM returned None, using rules")
            except Exception as e:
                logger.error(f"[Diagnosis] LLM call failed, falling back to rules: {e}")

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
                f"- {r.ne_name}: {r.alarm_name or 'unknown'} "
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
        alarm_names: List[str],
    ) -> tuple:
        """基于规则的诊断逻辑 — 基于告警名称交集匹配"""
        all_names = set(alarm_names)

        # 光网络告警模式（优先级从高到低）
        patterns = [
            # ---- 光链路中断类 ----
            ({"OTS_LOS", "OMS_LOS_P", "OCH_LOS_P"}, 0.92, "光链路信号丢失（OTS/OMS/OCH LOS）"),
            ({"OCH_LOS_P"}, 0.83, "光通道信号丢失（OCH_LOS_P）"),
            ({"OTS_LOS"}, 0.91, "光发送段信号丢失（OTS_LOS）"),
            ({"OMS_LOS_P"}, 0.89, "光复用段信号丢失（OMS_LOS_P）"),
            # ---- 以太网/数据平面故障 ----
            ({"ETHOAM_SELF_LOOP"}, 0.88, "以太网 OAM 自环（ETHOAM_SELF_LOOP）"),
            ({"PORT_EXC_TRAFFIC", "STORM_CUR_QUENUM_OVER", "FLOW_OVER"}, 0.87, "端口流量异常或广播风暴"),
            ({"STORM_CUR_QUENUM_OVER"}, 0.86, "广播风暴（STORM_CUR_QUENUM_OVER）"),
            ({"FLOW_OVER"}, 0.85, "流量溢出（FLOW_OVER）"),
            # ---- 光模块/硬件故障 ----
            ({"LSR_WILL_DIE"}, 0.86, "光模块即将失效（LSR_WILL_DIE）"),
            ({"LASER_MODULE_MISMATCH"}, 0.84, "光模块型号不匹配"),
            # ---- 数据库/配置类 ----
            ({"DBMS_ERROR"}, 0.82, "数据库故障（DBMS_ERROR）"),
            ({"DB_MEM_DIFF"}, 0.78, "数据库内存状态不一致（DB_MEM_DIFF）"),
            ({"CFG_DATASAVE_FAIL"}, 0.76, "配置保存失败（CFG_DATASAVE_FAIL）"),
            # ---- R_LOS / MUT_LOS（标准光链路告警）----
            ({"R_LOS", "MUT_LOS"}, 0.90, "光纤断纤或光链路衰减过大"),
            # ---- 交集中间匹配规则 ----
            ({"R_LOS"}, 0.85, "光纤断纤（收无光）"),
            ({"MUT_LOS"}, 0.88, "多方向光信号丢失（MUT_LOS）"),
            ({"OA_LOW_GAIN"}, 0.87, "光放大器增益异常"),
            ({"HARD_BAD", "HARD_ERR"}, 0.86, "单板硬件故障"),
            ({"CLIENT_PORT_PS", "ODU_SNCP_PS"}, 0.85, "保护倒换事件"),
            ({"SWDL_FAIL", "SWDL_TIMEOUT"}, 0.83, "软件/固件下载失败"),
            ({"WRG_BD_TYPE", "SUBRACK_ID_CONFLICT"}, 0.81, "配置/单板类型不匹配"),
            ({"FAN_FAIL", "FAN_FAULT"}, 0.84, "风扇故障"),
            ({"TEMP_OVER"}, 0.83, "温度超限"),
            ({"LINK_ERR", "LOCAL_FAULT"}, 0.82, "以太网链路故障"),
        ]

        for codes_to_match, conf, cause in patterns:
            if codes_to_match.issubset(all_names):
                evidence = [
                    Evidence(type="alarm", source=r.ne_name, alarm_name=r.alarm_name)
                    for r in records
                    if r.alarm_name
                ]
                return cause, conf, evidence

        # 默认诊断：取最频繁告警
        if alarm_names:
            top_name = max(alarm_names, key=lambda x: alarm_names.count(x))
            return (
                f"初步判定：{top_name} 告警为主，需进一步分析",
                0.60,
                [
                    Evidence(type="alarm", source=r.ne_name, alarm_name=r.alarm_name)
                    for r in records[:3]
                    if r.alarm_name == top_name
                ],
            )

        return ("无法确定根因，需补充告警信息", 0.50, [])

    def _assess_uncertainty(self, records: List[Any]) -> Optional[str]:
        """评估诊断不确定性"""
        if not records:
            return "无告警数据，无法诊断"

        has_unknown_name = any(not r.alarm_name for r in records)

        if has_unknown_name:
            return "部分告警缺少告警名称，影响诊断准确率，建议补充完整信息"

        return None