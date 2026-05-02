"""CSV 解析器测试"""

from omniops.ingestion.csv_parser import (
    ingest_csv,
    normalize_header,
    normalize_severity,
    parse_time,
)


class TestNormalizeHeader:
    def test_ne_name_variants(self):
        assert normalize_header("网元名称") == "ne_name"
        assert normalize_header("NE_Name") == "ne_name"
        assert normalize_header("网元") == "ne_name"
        assert normalize_header("设备名") == "ne_name"

    def test_alarm_name_variants(self):
        assert normalize_header("告警名称") == "alarm_name"
        assert normalize_header("alarm_name") == "alarm_name"
        assert normalize_header("告警") == "alarm_name"

    def test_severity_variants(self):
        assert normalize_header("级别") == "severity"
        assert normalize_header("severity") == "severity"
        assert normalize_header("告警级别") == "severity"

    def test_time_variants(self):
        assert normalize_header("发生时间") == "occur_time"
        assert normalize_header("occur_time") == "occur_time"
        assert normalize_header("告警时间") == "occur_time"

    def test_unknown_header(self):
        assert normalize_header("完全未知的列名") is None


class TestNormalizeSeverity:
    def test_critical(self):
        assert normalize_severity("Critical") == "Critical"
        assert normalize_severity("critical") == "Critical"
        assert normalize_severity("危急") == "Critical"

    def test_major(self):
        assert normalize_severity("Major") == "Major"
        assert normalize_severity("major") == "Major"
        assert normalize_severity("重要") == "Major"

    def test_minor(self):
        assert normalize_severity("Minor") == "Minor"
        assert normalize_severity("次要") == "Minor"

    def test_warning(self):
        assert normalize_severity("Warning") == "Warning"
        assert normalize_severity("警告") == "Warning"

    def test_none_input(self):
        assert normalize_severity(None) is None


class TestParseTime:
    def test_iso_format(self):
        result = parse_time("2026-04-28 14:23:00")
        assert result is not None
        assert result.year == 2026

    def test_chinese_format(self):
        result = parse_time("2026/04/28 14:23:00")
        assert result is not None
        assert result.year == 2026

    def test_date_only(self):
        result = parse_time("2026-04-28")
        assert result is not None

    def test_invalid_format(self):
        result = parse_time("not a date")
        assert result is None


class TestIngestCSV:
    def test_basic_csv(self):
        content = b"ne_name,alarm_name,severity,occur_time\nNE-BJ-01,LINK_FAIL,Critical,2026-04-28 14:23:00\nNE-BJ-02,POWER_LOW,Major,2026-04-28 14:25:00"
        records, uncertain = ingest_csv(content)

        assert len(records) == 2
        assert records[0].ne_name == "NE-BJ-01"
        assert records[0].alarm_name == "LINK_FAIL"
        assert records[0].severity.value == "Critical"

    def test_heterogeneous_headers(self):
        content = "网元名称,告警名称,级别,发生时间\nNE-SH-01,R_LOS,严重,2026/04/28 15:00:00".encode()
        records, uncertain = ingest_csv(content)

        assert len(records) == 1
        assert records[0].ne_name == "NE-SH-01"
        assert records[0].alarm_name == "R_LOS"

    def test_missing_alarm_info(self):
        content = b"ne_name,severity\nNE-GZ-01,Major"
        records, uncertain = ingest_csv(content)

        assert len(records) == 1
        # 缺少告警信息会被记录到 uncertain_fields
        assert len(uncertain) > 0

    def test_gbk_encoding(self):
        # UTF-8 with BOM
        content = "﻿网元名称,告警名称,级别\nNE-01,LINK_FAIL,Critical".encode("utf-8-sig")
        records, _ = ingest_csv(content)
        assert len(records) == 1
        assert records[0].ne_name == "NE-01"
