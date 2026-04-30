"""编码检测工具"""
import chardet


def detect_encoding(content: bytes) -> str:
    """检测字节流的编码"""
    result = chardet.detect(content)
    encoding = result.get("encoding")
    confidence = result.get("confidence", 0)

    if encoding and confidence > 0.7:
        return str(encoding)

    return "utf-8"


def read_csv_auto_encoding(file_path: str) -> str:
    """自动检测编码后读取 CSV 文件内容"""
    with open(file_path, "rb") as f:
        raw = f.read()

    encoding = detect_encoding(raw)
    return raw.decode(encoding)
