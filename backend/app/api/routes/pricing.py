"""
GET  /api/pricing/live      — fetch all cached pricing (auto-populates on first call)
GET  /api/pricing/compare   — side-by-side pricing across providers
GET  /api/pricing/services  — list services with pricing (aggregate stats)
POST /api/pricing/refresh   — synchronously refresh pricing from all free APIs
GET  /api/pricing/apis      — show which free APIs are available
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete

from app.db.session import get_db
from app.models.models import Provider, PricingCache

router = APIRouter(prefix="/pricing", tags=["pricing"])


# ── Shared helper ─────────────────────────────────────────────────────────────

async def _rows_to_items(db: AsyncSession, limit: int = 5000) -> list[dict]:
    """Return flat list of PricingCache rows joined with Provider name (price_usd > 0)."""
    result = await db.execute(
        select(Provider.name.label("provider"), PricingCache)
        .join(Provider, Provider.id == PricingCache.provider_id)
        .where(PricingCache.price_usd > 0)
        .order_by(Provider.name, PricingCache.service)
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "provider": row.provider,
            "service": row.PricingCache.service,
            "sku": row.PricingCache.sku,
            "region": row.PricingCache.region,
            "price_usd": row.PricingCache.price_usd,
            "unit": row.PricingCache.unit,
            "fetched_at": (
                row.PricingCache.fetched_at.isoformat()
                if row.PricingCache.fetched_at
                else None
            ),
        }
        for row in rows
    ]


async def _insert_provider_items(
    db: AsyncSession, all_data: dict[str, list[dict]]
) -> None:
    """Upsert providers and insert pricing items from fetch_all_providers() result."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for prov_name, items in all_data.items():
        # Get or create the Provider row
        prov_result = await db.execute(
            select(Provider).where(Provider.name.ilike(prov_name))
        )
        provider = prov_result.scalar_one_or_none()
        if not provider:
            provider = Provider(
                id=uuid.uuid4(),
                name=prov_name,
            )
            db.add(provider)
            await db.flush()

        # Insert pricing rows (skip zero-price index entries)
        for item in items:
            price = item.get("price_usd", 0.0)
            if not price or price <= 0.0:
                continue
            db.add(
                PricingCache(
                    id=uuid.uuid4(),
                    provider_id=provider.id,
                    service=item.get("service", ""),
                    sku=item.get("sku"),
                    region=item.get("region", "global"),
                    price_usd=float(price),
                    unit=item.get("unit"),
                    fetched_at=now,
                )
            )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/live")
async def get_live_pricing(db: AsyncSession = Depends(get_db)):
    """
    Return all cached pricing data as a flat list.
    If the cache is empty, synchronously fetches from all free public APIs first
    (self-healing on first visit — no manual refresh required).
    """
    count_result = await db.execute(select(func.count(PricingCache.id)))
    count = count_result.scalar() or 0

    if count == 0:
        from app.services.pricing import fetch_all_providers
        all_data: dict = await asyncio.to_thread(fetch_all_providers)
        await _insert_provider_items(db, all_data)
        await db.commit()

    items = await _rows_to_items(db)
    return {"items": items, "total": len(items)}


@router.post("/refresh")
async def trigger_pricing_refresh(db: AsyncSession = Depends(get_db)):
    """
    Synchronously re-fetch pricing from all free cloud APIs, replace cached data,
    and return the fresh results immediately.
    """
    from app.services.pricing import fetch_all_providers

    all_data: dict = await asyncio.to_thread(fetch_all_providers)

    # Wipe old cache
    await db.execute(sa_delete(PricingCache))
    await db.flush()

    await _insert_provider_items(db, all_data)
    await db.commit()

    items = await _rows_to_items(db)
    return {"status": "ok", "items": items, "total": len(items)}


@router.get("/compare")
async def compare_pricing(
    providers: str = Query(
        ..., description="Comma-separated provider names, e.g. AWS,Azure,GCP",
    ),
    service: Optional[str] = Query(
        None, description="Filter by service name (partial match)",
    ),
    region: Optional[str] = Query(
        None, description="Filter by region, e.g. us-east-1 or westeurope",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Side-by-side pricing comparison. Data from free public APIs."""
    names = [p.strip() for p in providers.split(",")]
    result = {}

    for name in names:
        prov_result = await db.execute(
            select(Provider).where(Provider.name.ilike(f"%{name}%"))
        )
        provider = prov_result.scalar_one_or_none()
        if not provider:
            continue

        q = select(PricingCache).where(PricingCache.provider_id == provider.id)
        if service:
            q = q.where(PricingCache.service.ilike(f"%{service}%"))
        if region:
            q = q.where(PricingCache.region.ilike(f"%{region}%"))
        q = q.order_by(PricingCache.fetched_at.desc()).limit(50)

        pricing_result = await db.execute(q)
        items = pricing_result.scalars().all()
        result[provider.name] = {
            "provider_id": str(provider.id),
            "item_count": len(items),
            "pricing": [
                {
                    "service": p.service,
                    "sku": p.sku,
                    "region": p.region,
                    "price_usd": p.price_usd,
                    "unit": p.unit,
                    "fetched_at": p.fetched_at.isoformat() if p.fetched_at else None,
                }
                for p in items
            ],
        }

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No pricing found for: {providers}. Run POST /api/pricing/refresh first.",
        )
    return {"comparison": result}


@router.get("/services")
async def list_priced_services(db: AsyncSession = Depends(get_db)):
    """List all services that have pricing data, grouped by provider."""
    result = await db.execute(
        select(
            Provider.name,
            PricingCache.service,
            func.count(PricingCache.id).label("cnt"),
            func.min(PricingCache.price_usd).label("min_p"),
            func.max(PricingCache.price_usd).label("max_p"),
        )
        .join(Provider, Provider.id == PricingCache.provider_id)
        .group_by(Provider.name, PricingCache.service)
        .order_by(Provider.name, PricingCache.service)
    )
    rows = result.all()
    services: dict = {}
    for row in rows:
        pname = row[0]
        if pname not in services:
            services[pname] = []
        services[pname].append({
            "service": row[1],
            "sku_count": row[2],
            "min_price_usd": row[3],
            "max_price_usd": row[4],
        })
    return {"services_by_provider": services}


@router.get("/apis")
async def list_pricing_apis():
    """Show which free pricing APIs are integrated."""
    apis = [
        {
            "provider": "Azure",
            "api": "Azure Retail Prices API",
            "url": "https://prices.azure.com/api/retail/prices",
            "auth_required": False,
            "free": True,
            "data_quality": "Excellent",
        },
        {
            "provider": "AWS",
            "api": "AWS Bulk Pricing JSON",
            "url": "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json",
            "auth_required": False,
            "free": True,
            "data_quality": "Excellent",
        },
        {
            "provider": "GCP",
            "api": "GCP Pricing Calculator JSON",
            "url": "https://cloudpricingcalculator.appspot.com/static/data/pricelist.json",
            "auth_required": False,
            "free": True,
            "data_quality": "Good",
        },
        {
            "provider": "IBM Cloud",
            "api": "IBM Global Catalog API",
            "url": "https://globalcatalog.cloud.ibm.com/api/v1",
            "auth_required": False,
            "free": True,
            "data_quality": "Moderate",
        },
        {
            "provider": "Oracle Cloud",
            "api": "Static/curated pricing",
            "url": "https://www.oracle.com/cloud/pricing/",
            "auth_required": False,
            "free": True,
            "data_quality": "Curated",
        },
    ]
    return {
        "pricing_apis": apis,
        "note": "All APIs are completely free. No paid keys or cloud accounts required.",
    }
