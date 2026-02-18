"""FastAPI 엔트리포인트 — API + 정적 파일 서빙.

실행: uvicorn server.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from server.routers import ideas, feedback, health

_START_TIME = time.monotonic()

app = FastAPI(title="API Ideation Engine v6.0", version="6.0.0")

# 라우터 등록
app.include_router(ideas.router, prefix="/api")
app.include_router(feedback.router, prefix="/api")
app.include_router(health.router, prefix="/api")

# 루트 → 대시보드 리다이렉트
@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard/")


# 정적 파일 서빙 (대시보드)
_STATIC_DIR = Path(__file__).parent / "static" / "dashboard"
if _STATIC_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_STATIC_DIR), html=True), name="dashboard")


def get_uptime() -> float:
    return time.monotonic() - _START_TIME
