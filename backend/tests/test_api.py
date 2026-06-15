"""
API layer integration tests.

Uses a fresh SQLite database per session for isolation (no Postgres needed locally).
In CI, DATABASE_URL is set to the real Postgres service container.
"""

import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import get_db
from app.main import app
from app.models.models import Base

_raw_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./test_slawise.db")
if _raw_url.startswith("postgresql://"):
    _TEST_DB_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://")
elif _raw_url.startswith("postgresql+asyncpg://"):
    _TEST_DB_URL = _raw_url
else:
    _TEST_DB_URL = _raw_url  # sqlite+aiosqlite or other


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(_TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_engine):
    SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()

    # Truncate all tables between tests for isolation
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_list_providers_returns_empty_list_on_fresh_db(client):
    resp = await client.get("/api/providers")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_query_with_no_docs_returns_auto_fetch_flag(client):
    resp = await client.post("/api/query", json={"text": "I need 99.99% uptime"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_fetch_available"] is True
    assert body["rankings"] == []


@pytest.mark.asyncio
async def test_compare_unknown_providers_returns_404(client):
    resp = await client.get("/api/compare?providers=NonExistentProvider")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_ingest_text_requires_key(client):
    resp = await client.post(
        "/api/admin/ingest-text",
        json={"provider": "TestCo", "text": "x" * 200, "title": "Test SLA"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_ingest_text_succeeds_with_key(client):
    with patch("app.api.routes.admin.embed_and_store", return_value=["chunk_0", "chunk_1"]):
        resp = await client.post(
            "/api/admin/ingest-text",
            json={"provider": "TestCo", "text": "x" * 300, "title": "Test SLA"},
            headers={"X-Admin-Key": "dev-admin-key"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["chunks_created"] == 2
