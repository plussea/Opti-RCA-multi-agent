"""OCR 路由 — 调用 OpenRouter 多模态模型提取告警表格"""
import base64
import json as _json
import logging
import os
import re
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, status

from omniops.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["ocr"])


def _b64_image(file_content: bytes) -> str:
    """将图片内容转为 data URI"""
    import mimetypes
    mime, _ = mimetypes.guess_type(None, file_content)
    mime = mime or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(file_content).decode()}"


@router.post("/ocr/extract")
async def ocr_extract(file: UploadFile) -> Dict[str, Any]:
    """上传网管截图/PDF，调用多模态 LLM 提取告警表格数据。

    支持格式: PNG, JPG, JPEG, PDF
    返回结构化告警记录列表，供后续诊断链路使用。
    """
    settings = get_settings()
    if not settings.ocr_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR_API_KEY not configured",
        )

    content = await file.read()

    # 构建多模态消息
    image_uri = _b64_image(content)
    messages: List[Dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_uri},
                },
                {
                    "type": "text",
                    "text": (
                        "这是一张网络告警截图，请提取其中所有告警记录，"
                        "以 JSON 数组格式输出，每条记录包含以下字段：\n"
                        "  - ne_name: 网元名称\n"
                        "  - alarm_name: 告警名称（如 R_LOS, DBMS_ERROR）\n"
                        "  - severity: 告警级别（Critical/Major/Minor/Warning）\n"
                        "  - occur_time: 发生时间（YYYY-MM-DD HH:MM:SS）\n"
                        "  - location: 定位信息（如光口号、槽位）\n"
                        "  - topology_id: 拓扑 ID（如有）\n\n"
                        "只输出 JSON 数组，不要其他文字。"
                    ),
                },
            ],
        }
    ]

    try:
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": settings.ocr_model,
                    "messages": messages,
                    "max_tokens": 4096,
                    "temperature": 0.1,
                },
                headers={
                    "Authorization": f"Bearer {settings.ocr_api_key}",
                    "HTTP-Referer": "https://omniops.ai",
                    "X-Title": "OmniOps",
                },
                proxy=proxy,
            )
            resp.raise_for_status()
            data = resp.json()
            content_text = (
                data["choices"][0]["message"].get("content") or
                data["choices"][0]["message"].get("reasoning") or
                ""
            )
    except httpx.HTTPStatusError as e:
        logger.error(f"[OCR] HTTP error: {e.response.status_code} — {e.response.text[:200]}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OCR model call failed: {e.response.status_code}",
        )
    except Exception as e:
        logger.error(f"[OCR] call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OCR call failed: {e}",
        )

    # 解析 JSON
    try:
        text = content_text.strip()
        try:
            records = _json.loads(text)
        except _json.JSONDecodeError:
            # 尝试 markdown code block
            match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
            if match:
                records = _json.loads(match.group(1))
            else:
                # 尝试找到第一个 [...] 包裹的内容
                match = re.search(r"(\[[\s\S]*\])", text)
                if match:
                    records = _json.loads(match.group(1))
                else:
                    raise ValueError(f"Cannot parse JSON from OCR response: {text[:200]}")

        if not isinstance(records, list):
            raise ValueError(f"OCR returned non-array: {type(records)}")

        logger.info(f"[OCR] extracted {len(records)} alarm records from {file.filename}")
        return {
            "records": records,
            "filename": file.filename,
            "count": len(records),
            "raw_text": content_text[:500],
        }

    except Exception as e:
        logger.error(f"[OCR] parse failed: {e}\nResponse: {content_text[:300]}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR result parse failed: {e}",
        )
