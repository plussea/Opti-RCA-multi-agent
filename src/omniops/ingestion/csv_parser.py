"""CSV 摄取与标准化"""
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from omniops.core.encoding import detect_encoding
from omniops.models import AlarmRecord, Severity

# 表头标准化映射
HEADER_MAPPINGS: Dict[str, str] = {
    # 网元名称变体
    r"网元名[称]?": "ne_name",
    r"ne[_]?name": "ne_name",
    r"网元": "ne_name",
    r"设备名": "ne_name",
    r"device[_]?name": "ne_name",
    # 告警码变体
    r"告警码": "alarm_code",
    r"alarm[_]?code": "alarm_code",
    r"告警编号": "alarm_code",
    r"告警ID": "alarm_code",
    # 告警名称变体
    r"告警名[称]?": "alarm_name",
    r"告警$": "alarm_name",        # 仅"告警"本身，不含后缀
    r"alarm[_]?name": "alarm_name",
    # 级别变体（精确匹配，避免被"告警级别"误匹配）
    r"告警级别$": "severity",
    r"^级别$": "severity",
    r"severity": "severity",
    r"优先级": "severity",
    # 时间变体（精确匹配，避免被"告警时间"误匹配）
    r"告警时间$": "occur_time",
    r"发生时间": "occur_time",
    r"occur[_]?time": "occur_time",
    r"^时间$": "occur_time",
    r"时间戳": "occur_time",
    # 槽位
    r"槽位": "slot",
    r"slot": "slot",
    # 机架
    r"机架": "shelf",
    r"shelf": "shelf",
    r"机框": "shelf",
    # 板卡类型
    r"板卡类型": "board_type",
    r"board[_]?type": "board_type",
    r"板卡型号": "board_type",
}

# 告警级别标准化映射
SEVERITY_MAPPINGS: Dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "危急": Severity.CRITICAL,
    "严重": Severity.CRITICAL,
    "major": Severity.MAJOR,
    "重要": Severity.MAJOR,
    "minor": Severity.MINOR,
    "次要": Severity.MINOR,
    "warning": Severity.WARNING,
    "警告": Severity.WARNING,
    "低": Severity.WARNING,
    "提示": Severity.WARNING,
}


def normalize_header(header: str) -> Optional[str]:
    """将异构表头标准化"""
    header_lower = header.lower().strip()
    for pattern, standard_name in HEADER_MAPPINGS.items():
        if re.search(pattern, header_lower):
            return standard_name
    return None


def normalize_severity(value: Any) -> Optional[Severity]:
    """标准化告警级别"""
    if value is None or pd.isna(value):
        return None
    value_str = str(value).lower().strip()
    return SEVERITY_MAPPINGS.get(value_str)


def parse_time(value: Any) -> Optional[datetime]:
    """解析时间字段为 ISO 8601 格式"""
    if value is None or pd.isna(value):
        return None

    value_str = str(value).strip()

    time_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]

    for fmt in time_formats:
        try:
            return datetime.strptime(value_str, fmt)
        except ValueError:
            continue

    return None


def ingest_csv(content: bytes) -> Tuple[List[AlarmRecord], List[Dict[Any, Any]]]:
    """摄取并标准化 CSV 内容

    Returns:
        (records, uncertain_fields): 标准化记录列表 + 低置信度字段列表
    """
    encoding = detect_encoding(content)
    df = pd.read_csv(BytesIO(content), encoding=encoding)

    # 标准化表头
    new_columns = {}
    uncertain_fields = []

    for col in df.columns:
        standard = normalize_header(col)
        if standard:
            new_columns[col] = standard
        else:
            # 无法识别的列，记录但不阻塞
            uncertain_fields.append({
                "type": "unknown_column",
                "original": col,
                "note": "无法识别该表头，将被跳过",
            })

    df = df.rename(columns=new_columns)

    # 标准化数据行
    records = []
    for idx, row in df.iterrows():
        record_dict = {}

        # 逐字段处理
        if "ne_name" in df.columns:
            record_dict["ne_name"] = str(row["ne_name"]).strip()
        elif df.shape[0] > 0:
            record_dict["ne_name"] = str(row.iloc[0]).strip()

        if "alarm_code" in df.columns:
            code = str(row["alarm_code"]).strip()
            record_dict["alarm_code"] = code if code and code != "nan" else None

        if "alarm_name" in df.columns:
            name = str(row["alarm_name"]).strip()
            record_dict["alarm_name"] = name if name and name != "nan" else None

        if "severity" in df.columns:
            record_dict["severity"] = normalize_severity(row["severity"])

        if "occur_time" in df.columns:
            record_dict["occur_time"] = parse_time(row["occur_time"])

        if "slot" in df.columns:
            record_dict["slot"] = str(row["slot"]).strip() if not pd.isna(row["slot"]) else None

        if "shelf" in df.columns:
            record_dict["shelf"] = str(row["shelf"]).strip() if not pd.isna(row["shelf"]) else None

        if "board_type" in df.columns:
            record_dict["board_type"] = str(row["board_type"]).strip() if not pd.isna(row["board_type"]) else None

        # 原始数据备份
        record_dict["raw_data"] = row.to_dict()

        # 检查空值标记
        if not record_dict.get("alarm_code") and not record_dict.get("alarm_name"):
            uncertain_fields.append({
                "type": "missing_alarm_info",
                "row": idx,
                "data": record_dict,
            })

        records.append(AlarmRecord(**record_dict))

    return records, uncertain_fields
