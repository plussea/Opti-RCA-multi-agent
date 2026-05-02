"""拓扑管理器 — 加载 Mesh 拓扑 JSON 文件，提供图查询"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# 拓扑文件根目录（相对于项目根）
TOPOLOGY_DIR = Path(__file__).parent.parent.parent.parent / "input" / "data" / "topology"

# 全局拓扑缓存
_topo_cache: Dict[str, Dict[str, Any]] = {}


def _load_topology(topo_id: str) -> Optional[Dict[str, Any]]:
    """从 JSON 文件加载拓扑，不重复读取"""
    if topo_id in _topo_cache:
        return _topo_cache[topo_id]

    topo_file = TOPOLOGY_DIR / f"{topo_id}.json"
    if not topo_file.exists():
        logger.warning(f"Topology file not found: {topo_file}")
        return None

    try:
        with open(topo_file, encoding="utf-8") as f:
            data = json.load(f)
        _topo_cache[topo_id] = data
        return data
    except Exception as e:
        logger.error(f"Failed to load topology {topo_id}: {e}")
        return None


def get_topology(topo_id: str) -> Optional[Dict[str, Any]]:
    """获取拓扑元数据（topology_id, type, node_num, nodes, edges）"""
    return _load_topology(topo_id)


def get_nodes(topo_id: str) -> List[str]:
    """获取拓扑中所有节点名"""
    topo = _load_topology(topo_id)
    if not topo:
        return []
    return topo.get("nodes", [])


def get_edges(topo_id: str) -> List[List[str]]:
    """获取拓扑中所有边（[nodeA, nodeB]）"""
    topo = _load_topology(topo_id)
    if not topo:
        return []
    return topo.get("edges", [])


def get_neighbors(topo_id: str, ne_name: str) -> List[str]:
    """获取与指定网元相邻的所有网元"""
    topo = _load_topology(topo_id)
    if not topo:
        return []
    neighbors: List[str] = []
    for edge in topo.get("edges", []):
        if len(edge) != 2:
            continue
        a, b = edge[0], edge[1]
        if a == ne_name:
            neighbors.append(b)
        elif b == ne_name:
            neighbors.append(a)
    return neighbors


def get_adjacent_edges(topo_id: str, ne_names: List[str]) -> List[str]:
    """获取与受影响网元列表相连的所有链路名称

    链路命名规则：<nodeA>-<nodeB>（字典序，保证双向唯一）
    例如：["N1", "N2"] → "N1-N2"
    """
    topo = _load_topology(topo_id)
    if not topo:
        return []
    ne_set = set(ne_names)
    links: List[str] = []
    for edge in topo.get("edges", []):
        if len(edge) != 2:
            continue
        a, b = edge[0], edge[1]
        if a in ne_set or b in ne_set:
            link_name = "-".join(sorted([a, b]))
            links.append(link_name)
    return links


def get_affected_links(topo_id: str, alarm_ne_names: List[str]) -> List[str]:
    """获取因告警网元故障而受影响的链路

    策略：
    - 告警网元本身直接相连的链路必然中断
    - 如果告警网元是关键节点（度≥3），其邻居也可能受影响
    """
    links = get_adjacent_edges(topo_id, alarm_ne_names)

    # 额外检查：告警网元是否为关键节点，若是则包含其二阶邻居链路
    critical_nes: Set[str] = set()
    for ne in alarm_ne_names:
        nbrs = get_neighbors(topo_id, ne)
        if len(nbrs) >= 3:  # 度≥3 的节点视为关键节点
            critical_nes.add(ne)

    # 关键节点故障会波及其二阶邻居链路
    for ne in critical_nes:
        second_hop = get_neighbors(topo_id, ne)
        for nbr in second_hop:
            links.extend(get_adjacent_edges(topo_id, [nbr]))

    # 去重并保持顺序
    seen: Set[str] = set()
    unique_links: List[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)
    return unique_links


def get_topology_type(topo_id: str) -> Optional[str]:
    """获取拓扑类型（MESH / CHAIN / RING 等）"""
    topo = _load_topology(topo_id)
    if not topo:
        return None
    return topo.get("type")


def get_node_degree(topo_id: str, ne_name: str) -> int:
    """获取指定网元在拓扑中的度（连接数）"""
    return len(get_neighbors(topo_id, ne_name))


def list_available_topologies() -> List[str]:
    """返回 input/data/topology/ 下所有可用的拓扑 ID"""
    if not TOPOLOGY_DIR.exists():
        return []
    return [p.stem for p in TOPOLOGY_DIR.glob("Topology_*.json")]
