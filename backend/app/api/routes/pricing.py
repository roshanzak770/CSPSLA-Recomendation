"""
GET  /api/pricing/compare    — side-by-side pricing across providers
GET  /api/pricing/services   — list services with pricing
POST /api/pricing/refresh    — trigger manual pricing refresh
GET  /api/pricing/apis       — show which free APIs are available
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_db
from app.models.models import Provider, PricingCache

router = APIRouter(prefix="/pricing", tags=["pricing"])


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


@router.post("/refresh")
async def trigger_pricing_refresh():
    """Trigger pricing refresh from all free cloud provider APIs (Celery task)."""
    from app.tasks.sla_tasks import refresh_pricing
    task = refresh_pricing.delay()
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Pricing refresh queued for Azure, AWS, GCP, IBM, Oracle.",
    }


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