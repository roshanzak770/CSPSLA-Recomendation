"""
GET  /api/providers
GET  /api/providers/{id}/sla
GET  /api/providers/{id}/cost
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.models import Provider, SLAMetrics, PricingCache
from app.core.schemas import ProviderSchema, SLAMetricsSchema

router = APIRouter()


@router.get("/providers", response_model=list[ProviderSchema])
async def list_providers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Provider))
    return result.scalars().all()


@router.get("/providers/ingested")
async def list_ingested_providers(db: AsyncSession = Depends(get_db)):
    """Returns only providers that have at least one ingested SLA document."""
    from sqlalchemy import func
    from app.models.models import SLADocument
    result = await db.execute(
        select(
            Provider,
            func.count(SLADocument.id).label("doc_count"),
        )
        .join(SLADocument, SLADocument.provider_id == Provider.id)
        .group_by(Provider.id)
        .order_by(Provider.name)
    )
    rows = result.all()
    return [
        {
            "id": str(row.Provider.id),
            "name": row.Provider.name,
            "doc_count": row.doc_count,
            "website": row.Provider.website,
        }
        for row in rows
    ]


@router.get("/providers/{provider_id}/sla", response_model=SLAMetricsSchema)
async def get_provider_sla(provider_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SLAMetrics)
        .where(SLAMetrics.provider_id == provider_id)
        .order_by(SLAMetrics.extracted_at.desc())
        .limit(1)
    )
    metrics = result.scalar_one_or_none()
    if not metrics:
        raise HTTPException(status_code=404, detail="No SLA metrics found for this provider")
    return metrics


@router.get("/providers/{provider_id}/cost")
async def get_provider_cost(provider_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PricingCache)
        .where(PricingCache.provider_id == provider_id)
        .order_by(PricingCache.fetched_at.desc())
        .limit(50)
    )
    pricing = result.scalars().all()
    return {"pricing": [
        {
            "service": p.service,
            "sku": p.sku,
            "region": p.region,
            "price_usd": p.price_usd,
            "unit": p.unit,
            "fetched_at": p.fetched_at,
        }
        for p in pricing
    ]}