"""光网络告警格式解析单元测试"""
import asyncio
from pathlib import Path

import pytest

from omniops.ingestion.csv_parser import ingest_csv, normalize_header, normalize_severity
from omniops.models import Severity
from omniops.core.topology_manager import (
    get_topology,
    get_nodes,
    get_edges,
    get_neighbors,
    get_adjacent_edges,
    get_affected_links,
    get_topology_type,
    get_node_degree,
    list_available_topologies,
)

# tests/unit/test_alarm_parsing.py → tests/unit/ → tests/ → project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
ALARM_DIR = PROJECT_ROOT / "input" / "data" / "alarm_datasets"
TOPO_DIR = PROJECT_ROOT / "input" / "data" / "topology"


# ─────────────────────────────────────────────────────────────────────────────
# CSV 解析测试
# ─────────────────────────────────────────────────────────────────────────────

class TestCsvHeaderMappings:
    """表头标准化映射"""

    def test_光网络_设备_映射到_ne_name(self):
        assert normalize_header("设备") == "ne_name"

    def test_光网络_定位信息_映射到_location(self):
        assert normalize_header("定位信息") == "location"

    def test_光网络_拓扑_id_映射到_topology_id(self):
        assert normalize_header("拓扑 id") == "topology_id"

    def test_光网络_告警级别_映射到_severity(self):
        assert normalize_header("告警级别") == "severity"

    def test_光网络_告警名称_映射到_alarm_name(self):
        assert normalize_header("告警名称") == "alarm_name"


class TestSeverityNormalization:
    """告警级别标准化"""

    def test_紧急_映射到_Critical(self):
        assert normalize_severity("紧急") == Severity.CRITICAL

    def test_重要_映射到_Major(self):
        assert normalize_severity("重要") == Severity.MAJOR

    def test_次要_映射到_Minor(self):
        assert normalize_severity("次要") == Severity.MINOR

    def test_未知_级别_返回_None(self):
        assert normalize_severity("未知") is None

    def test_None_输入_返回_None(self):
        assert normalize_severity(None) is None


class TestAlarmDatasetParsing:
    """alarm_datasets 目录下的真实样本解析"""

    @pytest.fixture
    def ep1_step1_csv(self) -> bytes:
        return (ALARM_DIR / "alarm_ep1_step1.csv").read_bytes()

    @pytest.fixture
    def ep1_step5_csv(self) -> bytes:
        return (ALARM_DIR / "alarm_ep1_step5.csv").read_bytes()

    @pytest.fixture
    def ep2_step1_csv(self) -> bytes:
        return (ALARM_DIR / "alarm_ep2_step1.csv").read_bytes()

    def test_ep1_step1_解析出_8条记录(self, ep1_step1_csv):
        records, uncertain = ingest_csv(ep1_step1_csv)
        assert len(records) == 8

    def test_ep1_step1_网元名正确(self, ep1_step1_csv):
        records, _ = ingest_csv(ep1_step1_csv)
        ne_names = {r.ne_name for r in records}
        assert ne_names == {"N7", "N3"}

    def test_ep1_step1_严重级别正确(self, ep1_step1_csv):
        records, _ = ingest_csv(ep1_step1_csv)
        severities = {r.severity for r in records}
        assert Severity.CRITICAL in severities
        assert Severity.MINOR in severities

    def test_ep1_step1_topology_id_正确(self, ep1_step1_csv):
        records, _ = ingest_csv(ep1_step1_csv)
        topo_ids = {r.topology_id for r in records}
        assert topo_ids == {"Topology_mesh10_1"}

    def test_ep1_step1_location_解析正确(self, ep1_step1_csv):
        records, _ = ingest_csv(ep1_step1_csv)
        locations = [r.location for r in records if r.location]
        assert len(locations) == 8  # 8 条记录
        assert all("subrack" in loc for loc in locations)

    def test_ep1_step5_重要告警(self, ep1_step5_csv):
        records, _ = ingest_csv(ep1_step5_csv)
        major = [r for r in records if r.severity == Severity.MAJOR]
        # N6:LSR_WILL_DIE, N3:N8:N5:OCH_LOS_P 都是重要级别
        assert len(major) >= 3

    def test_ep1_step5_topology_id_一致(self, ep1_step5_csv):
        records, _ = ingest_csv(ep1_step5_csv)
        topo_ids = {r.topology_id for r in records}
        assert topo_ids == {"Topology_mesh10_1"}

    def test_ep2_step1_属于不同拓扑(self, ep2_step1_csv):
        records, _ = ingest_csv(ep2_step1_csv)
        topo_ids = {r.topology_id for r in records}
        assert "Topology_mesh13_1" in topo_ids

    def test_ep2_step1_多网元(self, ep2_step1_csv):
        records, _ = ingest_csv(ep2_step1_csv)
        ne_names = {r.ne_name for r in records}
        assert len(ne_names) >= 10  # ep2_step1 有很多网元


# ─────────────────────────────────────────────────────────────────────────────
# 拓扑管理器测试
# ─────────────────────────────────────────────────────────────────────────────

class TestTopologyManager:
    """拓扑图查询"""

    def test_get_topology_返回正确结构(self):
        topo = get_topology("Topology_mesh10_1")
        assert topo is not None
        assert topo["topology_id"] == "Topology_mesh10_1"
        assert topo["type"] == "MESH"
        assert topo["node_num"] == 10

    def test_get_nodes_返回10个节点(self):
        nodes = get_nodes("Topology_mesh10_1")
        assert len(nodes) == 10
        assert "N1" in nodes
        assert "N9" in nodes

    def test_get_edges_返回正确的边数(self):
        edges = get_edges("Topology_mesh10_1")
        assert len(edges) == 17  # Mesh10_1 边数

    def test_get_neighbors_N7(self):
        nbrs = get_neighbors("Topology_mesh10_1", "N7")
        assert "N3" in nbrs
        assert "N8" in nbrs
        assert "N9" in nbrs

    def test_get_adjacent_edges_单网元(self):
        links = get_adjacent_edges("Topology_mesh10_1", ["N7"])
        assert len(links) >= 3  # N7 与 N3, N8, N9 相连

    def test_get_adjacent_edges_多网元(self):
        links = get_adjacent_edges("Topology_mesh10_1", ["N7", "N3"])
        link_set = set(links)
        # N7-N3, N7-N8, N7-N9, N3-N6, N3-N8 都应该在
        assert any("N3" in link and "N7" in link for link in links)

    def test_get_affected_links_alarm_n7(self):
        links = get_affected_links("Topology_mesh10_1", ["N7"])
        assert len(links) >= 3

    def test_get_affected_links_关键节点(self):
        links = get_affected_links("Topology_mesh10_1", ["N7"])
        assert len(links) >= 2  # N7 与多个邻居相连，至少 2 条链路

    def test_get_topology_type(self):
        assert get_topology_type("Topology_mesh10_1") == "MESH"

    def test_get_node_degree_n7(self):
        degree = get_node_degree("Topology_mesh10_1", "N7")
        assert degree == 4  # N7-N3, N6-N7, N7-N8, N7-N9

    def test_get_node_degree_n1(self):
        degree = get_node_degree("Topology_mesh10_1", "N1")
        assert degree == 4  # N1-N2, N1-N4, N1-N6, N1-N8

    def test_list_available_topologies(self):
        topos = list_available_topologies()
        assert "Topology_mesh10_1" in topos
        assert "Topology_mesh13_1" in topos

    def test_nonexistent_topology_returns_none(self):
        topo = get_topology("Topology_nonexistent")
        assert topo is None


# ─────────────────────────────────────────────────────────────────────────────
# 端到端流程测试（使用真实 CSV 文件）
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEndParsing:
    """从 CSV 到感知元数据的完整流程"""

    @pytest.mark.asyncio
    async def test_ep1_step5_端到端_光链路故障(self):
        from omniops.ingestion.csv_parser import ingest_csv
        from omniops.agents.perception import PerceptionAgent
        from omniops.models import Session, SessionStatus, InputType
        from datetime import datetime

        content = (ALARM_DIR / "alarm_ep1_step5.csv").read_bytes()
        records, uncertain = ingest_csv(content)

        session = Session(
            session_id="test_e2e_001",
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
            created_at=datetime.utcnow(),
        )

        agent = PerceptionAgent()
        summary = await agent.process(session)

        assert summary.conclusion is not None
        assert session.perception_metadata is not None
        assert session.perception_metadata["topology_id"] == "Topology_mesh10_1"
        assert session.perception_metadata["alarm_count"] == 5
        assert session.perception_metadata["ne_count"] >= 4

    @pytest.mark.asyncio
    async def test_ep2_step1_端到端_不同拓扑(self):
        from omniops.ingestion.csv_parser import ingest_csv
        from omniops.agents.perception import PerceptionAgent
        from omniops.models import Session, SessionStatus, InputType
        from datetime import datetime

        content = (ALARM_DIR / "alarm_ep2_step1.csv").read_bytes()
        records, uncertain = ingest_csv(content)

        session = Session(
            session_id="test_e2e_002",
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
            created_at=datetime.utcnow(),
        )

        agent = PerceptionAgent()
        summary = await agent.process(session)

        assert session.perception_metadata["topology_id"] == "Topology_mesh13_1"


class TestImpactWithTopology:
    """拓扑感知的影响评估"""

    @pytest.mark.asyncio
    async def test_n7告警_影响链路推理(self):
        from omniops.core.topology_manager import get_adjacent_edges
        from omniops.agents.impact import ImpactAgent
        from omniops.ingestion.csv_parser import ingest_csv
        from omniops.models import Session, SessionStatus, InputType, DiagnosisResult, Evidence
        from datetime import datetime

        content = (ALARM_DIR / "alarm_ep1_step1.csv").read_bytes()
        records, _ = ingest_csv(content)

        session = Session(
            session_id="test_impact_001",
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
            created_at=datetime.utcnow(),
        )
        session.diagnosis_result = DiagnosisResult(
            root_cause="测试根因",
            confidence=0.85,
            evidence=[Evidence(type="test", source="test")],
        )

        agent = ImpactAgent()
        summary = await agent.process(session)

        assert session.impact is not None
        assert "N7" in session.impact.affected_ne
        assert len(session.impact.affected_links) >= 3  # N7 度=3
        assert "Mesh 骨干传输业务" in session.impact.affected_services


class TestDiagnosisWithNewPatterns:
    """新告警模式的诊断"""

    @pytest.mark.asyncio
    async def test_och_los_p_诊断(self):
        from omniops.agents.diagnosis import DiagnosisAgent
        from omniops.models import Session, SessionStatus, InputType, AlarmRecord
        from datetime import datetime

        records = [
            AlarmRecord(ne_name="N3", alarm_name="OCH_LOS_P", severity=None, topology_id="Topology_mesh10_1"),
            AlarmRecord(ne_name="N8", alarm_name="OCH_LOS_P", severity=None, topology_id="Topology_mesh10_1"),
        ]
        session = Session(
            session_id="test_diag_001",
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
            created_at=datetime.utcnow(),
        )

        agent = DiagnosisAgent()
        summary = await agent.process(session)

        assert session.diagnosis_result is not None
        # 无告警码时按 alarm_name 匹配 OCH_LOS_P fallback，confidence=0.83
        assert session.diagnosis_result.confidence >= 0.83

    @pytest.mark.asyncio
    async def test_ets_los_ots_los_诊断(self):
        from omniops.agents.diagnosis import DiagnosisAgent
        from omniops.models import Session, SessionStatus, InputType, AlarmRecord
        from datetime import datetime

        records = [
            AlarmRecord(ne_name="N4", alarm_name="OTS_LOS", severity=None, topology_id="Topology_mesh10_1"),
            AlarmRecord(ne_name="N4", alarm_name="OMS_LOS_P", severity=None, topology_id="Topology_mesh10_1"),
            AlarmRecord(ne_name="N1", alarm_name="OCH_LOS_P", severity=None, topology_id="Topology_mesh10_1"),
        ]
        session = Session(
            session_id="test_diag_002",
            input_type=InputType.CSV,
            structured_data=records,
            status=SessionStatus.ANALYZING,
            created_at=datetime.utcnow(),
        )

        agent = DiagnosisAgent()
        summary = await agent.process(session)

        assert session.diagnosis_result is not None
        # OTS_LOS + OMS_LOS_P + OCH_LOS_P 三者并存时，匹配最强模式
        assert session.diagnosis_result.confidence >= 0.89
