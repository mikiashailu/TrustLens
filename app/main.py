""" Main module. """

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes_auth import router as auth_router
from app.api.routes_health import router as health_router
from app.api.routes_identity import router as identity_router
from app.api.routes_profile import router as profile_router
from app.api.routes_trust import router as trust_router
from app.api.routes_stats import router as stats_router
from app.api.routes_trust_card import router as trust_card_router
from app.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Path("data").mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="TrustLens AI API",
    description="Intelligent eKYC + Behavioral Trust Scoring backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(identity_router)
app.include_router(trust_router)
app.include_router(trust_card_router)
app.include_router(stats_router)
