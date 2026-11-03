# SOURCE: NOT IN PAPERS. Standalone app for local use; the team can instead include `router`.
"""Run from the aakaash folder:  python -m uvicorn api.app:app --port 8000"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import auth, db
from .config import get_settings
from .router import router
from .services import datasets

log = logging.getLogger("uvicorn.error")


def _warm_ddi_cache() -> None:
    """Parsing the DDI corpus takes a few seconds; do it in the background at startup so the
    first dashboard request does not wait. Failures are logged, not hidden."""
    try:
        datasets.load_ddi(get_settings())
    except Exception:  # noqa: BLE001
        log.exception("DDI cache warm-up failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.session_maker(get_settings())  # creates artifacts/app.db and its tables if they are missing
    auth.session_secret()  # warns once if SESSION_SECRET is not set
    threading.Thread(target=_warm_ddi_cache, daemon=True).start()
    yield


app = FastAPI(title="Medication safety: subareas A and B",
              description="Decision support only. Not medical advice.",
              lifespan=lifespan)
app.add_middleware(  # the Vite dev server
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["*"])
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 as FastAPI sends it, minus the `input` and `ctx` fields: `input` would echo what was sent,
    which for the login form is the password."""
    return JSONResponse({"detail": [{"type": e["type"], "loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]},
                        status_code=422)


@app.middleware("http")
async def _api_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response
