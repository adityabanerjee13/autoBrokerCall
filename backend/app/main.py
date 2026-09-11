"""FastAPI application: CORS, routers, index setup at startup."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import broker, calls, client, dograh, manager, messages
from app.config import settings
from app.db import ensure_indexes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("brokeragent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    log.info(
        "brokeragent up | transport=%s orchestrator=%s mock_outbound=%s azure=%s",
        settings.transport,
        "dograh" if settings.dograh_configured else "NOT configured",
        settings.mock_outbound,
        "configured" if settings.llm_configured else "NOT configured (offline fallbacks)",
    )
    if settings.call_transport == "dograh" and settings.transport != "dograh":
        # Asking for the orchestrator and silently getting a scripted lead is
        # the kind of thing that is only noticed when nothing dials.
        log.warning(
            "CALL_TRANSPORT=dograh but Dograh is not fully configured "
            "(api base, api key, workflow uuid and shared secret are all "
            "required) - falling back to the scripted runner"
        )
    yield

    from app.dograh import client as dograh_client

    await dograh_client.aclose()


app = FastAPI(title="brokerAgent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (calls, dograh, broker, client, manager, messages):
    app.include_router(module.router)


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "transport": settings.transport,
        "orchestrator": "dograh" if settings.dograh_configured else None,
        "mock_outbound": settings.mock_outbound,
        "llm_configured": settings.llm_configured,
        "dograh_configured": settings.dograh_configured,
    }
