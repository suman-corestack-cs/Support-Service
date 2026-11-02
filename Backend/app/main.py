import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.router import router

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Comma-separated list of origins allowed to call this API, e.g.
# "https://app.example.com" or "https://app.example.com,http://localhost:5173"
# for local dev alongside a deployed frontend. Deliberately no "*" fallback —
# an empty/unset value means no browser origin is allowed, which is the safe
# failure mode for an API that handles real cloud credentials, rather than
# silently defaulting back to wide open.
_allowed_origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGIN", "").split(",") if origin.strip()]

# Several scripts print emoji (✅, ❌, ...) for readability when run standalone.
# On Windows, the console's default stdout encoding can't represent those
# characters and print() raises UnicodeEncodeError, killing the script thread
# outright. Reconfiguring here is encoding-only — no script logic changes.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


class CatchAllExceptionsMiddleware(BaseHTTPMiddleware):
    # A bare `@app.exception_handler(Exception)` runs outside CORSMiddleware in
    # Starlette's stack, so unhandled errors would otherwise reach the browser
    # as an opaque CORS failure instead of the actual error. Catching here,
    # before CORSMiddleware wraps this middleware, keeps the CORS headers intact.
    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            return JSONResponse(status_code=500, content={"detail": str(exc)})


app = FastAPI(title="Service Support Project - Backend", version="1.0.0")

app.add_middleware(CatchAllExceptionsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
