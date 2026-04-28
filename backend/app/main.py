from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import query, providers, feedback, alerts, admin, ask, pricing
from app.db.init_db import init_db

app = FastAPI(
    title="CloudSLA Recommender API",
    description="NLP-based cloud service provider recommendation using SLA documents",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await init_db()


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