"""工具注册表"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from omniops.core.config import get_settings

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表（YAML 配置驱动）"""

    def __init__(self, config_path: Optional[str] = None):
        settings = get_settings()
        self.config_path = config_path or str(
            Path(settings.project_root) / "tools" / "registry.yaml"
        )
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._load_tools()

    def _load_tools(self):
        """从 YAML 文件加载工具注册表"""
        config_path = Path(self.config_path)
        if not config_path.exists():
            logger.warning(f"Tool registry not found: {self.config_path}, using empty registry")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self._tools = data.get("tools", {})
                logger.info(f"Loaded {len(self._tools)} tools from registry")
        except Exception as e:
            logger.error(f"Failed to load tool registry: {e}")

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """获取工具定义"""
        return self._tools.get(name)

    def list_tools(self, risk_level: Optional[str] = None) -> List[str]:
        """列出所有工具"""
        if risk_level:
            return [
                name for name, tool in self._tools.items()
                if tool.get("risk_level") == risk_level
            ]
        return list(self._tools.keys())

    def register_tool(self, name: str, tool_def: Dict[str, Any]):
        """注册工具（运行时）"""
        self._tools[name] = tool_def
        logger.info(f"Tool registered: {name}")

    def unregister_tool(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Tool unregistered: {name}")
            return True
        return False

    def get_all_tools(self) -> Dict[str, Dict[str, Any]]:
        """获取所有工具定义"""
        return self._tools.copy()


# 默认工具注册表 YAML 内容
DEFAULT_TOOLS_REGISTRY = """# OmniOps 工具注册表

tools:
  query_topology:
    name: 查询拓扑
    description: 查询网元间的拓扑连接关系
    endpoint: http://localhost:8080/v1/topology/query
    method: POST
    risk_level: read
    permissions: []
    rate_limit: 100
    timeout: 30
    schema:
      input:
        type: object
        properties:
          ne_name:
            type: string
            description: 网元名称
        required: [ne_name]
      output:
        type: object
        properties:
          links:
            type: array
            description: 连接的链路列表

  query_alarm_history:
    name: 查询告警历史
    description: 查询网元的历史告警记录
    endpoint: http://localhost:8080/v1/alarms/history
    method: GET
    risk_level: read
    permissions: []
    rate_limit: 50
    timeout: 60
    schema:
      input:
        type: object
        properties:
          ne_name:
            type: string
          start_time:
            type: string
            format: date-time
          end_time:
            type: string
            format: date-time
        required: [ne_name]

  execute_health_check:
    name: 执行健康检查
    description: 在网元上执行健康检查命令
    endpoint: http://localhost:8080/v1/ne/health-check
    method: POST
    risk_level: medium
    permissions: ["engineer"]
    rate_limit: 20
    timeout: 120
    schema:
      input:
        type: object
        properties:
          ne_name:
            type: string
          check_type:
            type: string
            enum: [basic, extended, full]
        required: [ne_name]
"""


def ensure_tools_registry():
    """确保工具注册表文件存在"""
    settings = get_settings()
    registry_path = Path(settings.project_root) / "tools" / "registry.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    if not registry_path.exists():
        registry_path.write_text(DEFAULT_TOOLS_REGISTRY, encoding="utf-8")
        logger.info(f"Created default tool registry at {registry_path}")


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表单例"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry