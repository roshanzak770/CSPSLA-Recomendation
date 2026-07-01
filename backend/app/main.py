from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import query, providers, feedback, alerts, admin, ask, pricing, search, services
from app.core.config import settings
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="SLAwise API",
    description="AI-powered cloud SLA intelligence and provider recommendation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(query.router, prefix="/api", tags=["query"])
app.include_router(providers.router, prefix="/api", tags=["providers"])
app.include_router(feedback.router, prefix="/api", tags=["feedback"])
app.include_router(alerts.router, prefix="/api", tags=["alerts"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
app.include_router(ask.router, prefix="/api", tags=["ask"])
app.include_router(pricing.router, prefix="/api", tags=["pricing"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(services.router, prefix="/api", tags=["services"])
