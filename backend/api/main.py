from __future__ import annotations
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from api.routes.health import router as health_router
from api.routes.metrics import router as metrics_router
from api.routes.scores import router as scores_router
from api.routes.sources import router as sources_router
from api.routes.stage import router as stage_router
from config.settings import get_settings
from scheduler.jobs import bootstrap_phase1, init_scheduler, shutdown_scheduler

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])


def _bootstrap_runner() -> None:
    try:
        bootstrap_phase1()
    except Exception:  # noqa: BLE001
        logger.exception("bootstrap_phase1_failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("app_startup")
    init_scheduler()
    if settings.backfill_on_startup:
        thread = threading.Thread(target=_bootstrap_runner, daemon=True, name="bootstrap_phase1")
        thread.start()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Bitcoin capital flow and stage dashboard backend",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disclaimer_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Disclaimer"] = settings.disclaimer_text
    response.headers["X-Data-Policy"] = "Informational only; not investment advice"
    return response


@app.get("/")
def root() -> dict:
    return {
        "data": {
            "service": settings.app_name,
            "status": "running",
            "disclaimer": settings.disclaimer_text,
        },
        "meta": {
            "source": "system",
            "delay": "0",
            "unit": None,
            "version": 1,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


app.include_router(health_router)
app.include_router(sources_router)
app.include_router(metrics_router)
app.include_router(scores_router)
app.include_router(stage_router)
