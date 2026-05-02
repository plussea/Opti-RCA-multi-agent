"""实体/关系解析器 — 结构化快速通道 + LLM 回退"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from omniops.knowledge.neo4j_client import (
    REL_IS_CAUSED_BY,
    REL_TRIGGERS,
    REL_IS_LOCATED_AT,
    REL_CONNECTED_UPSTREAM,
    REL_BELONGS_TO_LINK,
    REL_HAS_ALERT,
)

logger = logging.getLogger(__name__)


# ============================================================
# 同义词归一化映射
# ============================================================
ALIAS_MAP: Dict[str, str] = {
    "R_LOS": "R_LOS",
    "LOS": "R_LOS",
    "信号丢失": "R_LOS",
    "收无光": "R_LOS",
    "MUT_LOS": "MUT_LOS",
    "MS_RDI": "MS_RDI",
    "IN_PWR_LOW": "IN_PWR_LOW",
    "光功率异常低": "IN_PWR_LOW",
    "输入光功率低": "IN_PWR_LOW",
    "OTU": "OTU单板",
    "OTU单板": "OTU单板",
    "OLP": "OLP板",
    "OLP板": "OLP板",
    "光纤断纤": "光纤断纤",
    "光纤断裂": "光纤断纤",
    "线路衰减过大": "线路衰减过大",
    "连接器污损": "连接器污损",
}


def normalize_entity(entity: str) -> str:
    """归一化实体名称，同义词合并"""
    return ALIAS_MAP.get(entity.strip(), entity.strip())


# ============================================================
# 结构化表格解析（正则）
# ============================================================

# 告警表行：| R_LOS | 信号丢失 | 紧急 | 光口号 | OTU单板 |
ALARM_TABLE_ROW_RE = re.compile(
    r"^\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|"
    r"\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|"
)

# 故障行：| FAULT-001 | 光纤断纤 | 物理层故障 | R_LOS, MUT_LOS |
FAULT_TABLE_ROW_RE = re.compile(
    r"^\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|"
)

# 设备行：| OTU-A | OTU单板 | 电层 | 波分侧光口/FEC模式 |
DEVICE_TABLE_ROW_RE = re.compile(
    r"^\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|\s*([^\s|]+)\s*\|"
)

# 三元组格式：R_LOS --IS_CAUSED_BY--> 光纤断纤
TRIPLE_RE = re.compile(
    r"^\s*(.+?)\s*(?:--|->|→)\s*(IS_CAUSED_BY|TRIGGERS|IS_LOCATED_AT|"
    r"CONNECTED_UPSTREAM|BELONGS_TO_LINK|HAS_ALERT|APPLIES_TO)\s*"
    r"(?:--|->|→)\s*(.+?)\s*$"
)


def parse_alarm_table_row(line: str) -> Optional[Dict[str, Any]]:
    """解析告警表行，返回 Alarm 节点数据"""
    m = ALARM_TABLE_ROW_RE.match(line)
    if not m:
        return None
    code, name, level, key_params, device_type = m.groups()
    return {
        "label": "Alarm",
        "primary_key": "code",
        "code": code.strip(),
        "name": name.strip(),
        "level": level.strip(),
        "key_params": [p.strip() for p in key_params.split(",") if p.strip()],
        "device_type": device_type.strip(),
    }


def parse_fault_table_row(line: str) -> Optional[Dict[str, Any]]:
    """解析故障表行，返回 Fault 节点数据"""
    m = FAULT_TABLE_ROW_RE.match(line)
    if not m:
        return None
    fid, name, category, common_alarms = m.groups()
    return {
        "label": "Fault",
        "primary_key": "id",
        "id": fid.strip(),
        "name": name.strip(),
        "category": category.strip(),
        "common_alarms": [a.strip() for a in common_alarms.split(",") if a.strip()],
    }


def parse_device_table_row(line: str) -> Optional[Dict[str, Any]]:
    """解析设备表行，返回 Device 节点数据"""
    m = DEVICE_TABLE_ROW_RE.match(line)
    if not m:
        return None
    did, dtype, layer, key_attrs = m.groups()
    return {
        "label": "Device",
        "primary_key": "id",
        "id": did.strip(),
        "type": dtype.strip(),
        "layer": layer.strip(),
        "key_attrs": key_attrs.strip(),
    }


def parse_triple_line(line: str) -> Optional[Tuple[str, str, str, str]]:
    """解析三元组行：src --rel--> tgt"""
    m = TRIPLE_RE.match(line)
    if not m:
        return None
    src, rel, tgt = m.groups()
    src_norm = normalize_entity(src.strip())
    tgt_norm = normalize_entity(tgt.strip())
    return src_norm, tgt_norm, rel.strip(), ""


# ============================================================
# 主解析入口
# ============================================================

def parse_document(content: str, domain: str = "optical_network") -> Dict[str, Any]:
    """
    解析知识文档，返回 {nodes: [], relations: []}

    支持格式：
    - Markdown 表格（| 格式）
    - 三元组行（X --rel--> Y）
    - 结构化章节（## 告警、## 故障 等）
    """
    lines = content.split("\n")

    nodes: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    in_alarm_section = False
    in_fault_section = False
    in_device_section = False

    for line in lines:
        stripped = line.strip()

        # 章节检测
        if "## 告警" in stripped or "## Alarm" in stripped or "## 告警实例" in stripped:
            in_alarm_section = True
            in_fault_section = False
            in_device_section = False
            continue
        if "## 故障" in stripped or "## Fault" in stripped or "## 故障类型" in stripped:
            in_alarm_section = False
            in_fault_section = True
            in_device_section = False
            continue
        if "## 设备" in stripped or "## Device" in stripped or "## 网元设备" in stripped:
            in_alarm_section = False
            in_fault_section = False
            in_device_section = True
            continue

        # 三元组解析（通用，所有节都适用）
        triple = parse_triple_line(stripped)
        if triple:
            src, tgt, rel, _ = triple
            relations.append({
                "src": src,
                "tgt": tgt,
                "rel": rel,
                "domain": domain,
            })
            continue

        # 表格行解析
        if in_alarm_section:
            alarm = parse_alarm_table_row(stripped)
            if alarm:
                alarm["domain"] = domain
                nodes.append(alarm)

        if in_fault_section:
            fault = parse_fault_table_row(stripped)
            if fault:
                fault["domain"] = domain
                nodes.append(fault)

        if in_device_section:
            device = parse_device_table_row(stripped)
            if device:
                device["domain"] = domain
                nodes.append(device)

    return {"nodes": nodes, "relations": relations}


def extract_seed_entities(alarm_codes: List[str], alarm_names: List[str]) -> List[str]:
    """从告警列表中提取种子实体（用于 KG 查询）"""
    entities = []
    for code in alarm_codes:
        if code:
            entities.append(normalize_entity(code))
    for name in alarm_names:
        if name:
            entities.append(normalize_entity(name))
    return list(dict.fromkeys(entities))  # 去重保留顺序