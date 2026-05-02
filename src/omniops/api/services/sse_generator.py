"""SSE 流生成器"""
import asyncio
import json
from fastapi.responses import StreamingResponse
from typing import Any, Dict

from omniops.memory.redis_store import get_redis_session_store
from omniops.models import Session

TERMINAL_STATUSES = {"approved", "rejected", "resolved", "completed", "failed", "escalated"}


async def sse_stream(session_id: str) -> StreamingResponse:
    """Server-Sent Events stream for real-time session status updates.

    Frontend consumes with:
        const es = new EventSource('/v1/sessions/{session_id}/stream')
        es.addEventListener('status', (e) => { const data = JSON.parse(e.data) })
    """
    async def event_generator() -> Any:
        poll_interval = 1.5
        poll_count = 0

        while True:
            poll_count += 1

            # Heartbeat to prevent Nginx/browser timeouts every ~30s
            if poll_count % 20 == 0:
                yield ""
                await asyncio.sleep(0.01)
                continue

            session: Any = None  # type: ignore[no-redef]
            try:
                store = await get_redis_session_store()
                session = await store.get(session_id)
            except Exception:
                pass

            if session is None:
                from omniops.memory.store import get_session_store
                session = get_session_store().get(session_id)

            if session is None:
                payload = json.dumps({"session_id": session_id, "error": "not_found"})
                yield f"event: error\ndata: {payload}\n\n"
                break

            payload_data: Dict[str, Any] = {
                "session_id": session.session_id,
                "status": session.status.value if hasattr(session.status, "value") else str(session.status),
                "current_step": session.current_step,
                "diagnosis_result": (
                    session.diagnosis_result.model_dump() if session.diagnosis_result else None
                ),
                "impact": session.impact.model_dump() if session.impact else None,
                "suggestion": session.suggestion.model_dump() if session.suggestion else None,
                "human_feedback": session.human_feedback,
                "created_at": session.created_at.isoformat(),
            }

            if session.status.value in TERMINAL_STATUSES:
                yield f"event: status\ndata: {json.dumps(payload_data)}\n\n"
                yield "event: close\ndata: {}\n\n"
                break

            yield f"event: status\ndata: {json.dumps(payload_data)}\n\n"
            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
