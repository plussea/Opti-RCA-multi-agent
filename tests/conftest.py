"""pytest-asyncio Windows event loop workaround.

Root cause: pytest-asyncio creates a new event loop per test (function scope) in `asyncio_mode="auto"`.
SQLAlchemy's async engine holds a connection pool that fires background tasks (pool cleanup)
after a test finishes. These tasks try to run on the now-closed event loop, causing
"Event loop is closed" at the next test's setup.

Fix: hold one persistent event loop for the entire test session so the engine
never has to deal with a stale loop. Engine cleanup happens once at session exit.
"""
import asyncio
import sys

import pytest

# Workaround must run at conftest load time, before pytest-asyncio creates loops.
if sys.platform == "win32":
    _orig_loop_close = asyncio.AbstractEventLoop.close

    def _safe_close(self):
        try:
            _orig_loop_close(self)
        except RuntimeError:
            pass

    asyncio.AbstractEventLoop.close = _safe_close


# ─────────────────────────────────────────────────────────────────────────────
# Session-scoped event loop shared by all async tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """One event loop for the entire session — avoids loop-closed errors across tests."""
    policy = asyncio.DefaultEventLoopPolicy()
    loop = policy.new_event_loop()
    yield loop
    loop.run_until_complete(loop.shutdown_asyncgens() if hasattr(loop, "shutdown_asyncgens") else asyncio.sleep(0))
    loop.close()