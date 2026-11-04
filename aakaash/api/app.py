# SOURCE: NOT IN PAPERS. Standalone app for local use; the team can instead include `router`.
"""Run from the aakaash folder:  python -m uvicorn api.app:app --port 8000"""
import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import auth, db
from .config import get_settings, load_env_file
from .router import router
from .services import datasets, ddi, retrieval

log = logging.getLogger("uvicorn.error")

load_env_file()  # once, at server startup, before anything reads the environment


def _warm_ddi_cache() -> None:
    """Parsing the DDI corpus takes a few seconds; do it in the background at startup so the
    first dashboard request does not wait. Failures are logged, not hidden."""
    try:
        datasets.load_ddi(get_settings())
    except Exception:  # noqa: BLE001
        log.exception("DDI cache warm-up failed")


def _load_models() -> None:
    """Load the sbert model and the DDI classifier before the first request, in parallel. A failure is
    logged and the app still starts: sbert falls back to TF-IDF (named in every answer), the classifier
    reports its error on the first request as before."""
    s = get_settings()

    def sbert() -> None:
        t = time.perf_counter()
        used = retrieval.warm_up(s)
        log.info("Label search encoder: %s (configured %s), ready in %.1f s", used, s.encoder_name, time.perf_counter() - t)

    def classifier() -> None:
        t = time.perf_counter()
        try:
            if ddi.preload(s):
                log.info("DDI classifier loaded in %.1f s", time.perf_counter() - t)
        except Exception:  # noqa: BLE001
            log.exception("DDI classifier preload failed; the first request will try again")

    workers = [threading.Thread(target=f) for f in (sbert, classifier)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.session_maker(get_settings())  # creates artifacts/app.db and its tables if they are missing
    auth.session_secret()  # warns once if SESSION_SECRET is not set
    threading.Thread(target=_warm_ddi_cache, daemon=True).start()
    await asyncio.to_thread(_load_models)
    yield


app = FastAPI(title="Medopic",
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
