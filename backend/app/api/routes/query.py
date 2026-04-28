"""
POST /api/query  — main recommendation endpoint
GET  /api/compare — side-by-side comparison
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.schemas import QueryRequest, QueryResponse, ProviderRanking, ParsedRequirements
from app.db.session import get_db
from app.models.models import Provider, SLAMetrics, Query, Ranking, PricingCache
from app.services.ranking_pipeline import run_pipeline

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def run_query(req: QueryRequest, db: AsyncSession = Depends(get_db)):
    # Load all providers + latest SLA metrics
    providers_result = await db.execute(select(Provider))
    providers = providers_result.scalars().all()

    if not providers:
        raise HTTPException(
            status_code=404,
            detail="No providers found. Run POST /api/admin/ingest first.",
        )

    providers_with_metrics = []
    for provider in providers:
        metrics_result = await db.execute(
            select(SLAMetrics)
            .where(SLAMetrics.provider_id == provider.id)
            .order_by(SLAMetrics.extracted_at.desc())
            .limit(1)
        )
        metrics = metrics_result.scalar_one_or_none()
        providers_with_metrics.append((str(provider.id), provider.name, metrics))

    # Run the full 6-stage pipeline
    pipeline_result = run_pipeline(
        raw_query=req.text,
        providers_with_metrics=providers_with_metrics,
        weights=req.weights,
    )

    if not pipeline_result.provider_results:
        raise HTTPException(
            status_code=404,
            detail="No SLA metrics found. Ingest SLA documents first.",
        )

    # Persist query
    query_id = uuid.uuid4()
    req_data = pipeline_result.requirements
    db.add(Query(
        id=query_id,
        raw_input=req.text,
        detected_lang=pipeline_result.detected_lang,
        parsed_json={
            "uptime_required_pct": req_data.uptime_required_pct,
            "rto_hours": req_data.rto_hours,
            "region": req_data.region,
            "compliance": req_data.compliance,
            "category": req_data.category,
            "sensitivity": req_data.sensitivity,
        },
    ))

    # Persist rankings
    for r in pipeline_result.provider_results:
        db.add(Ranking(
            query_id=query_id,
            provider_id=uuid.UUID(r.provider_id),
            topsis_score=r.topsis_score,
            xgb_score=r.xgb_score,
            final_score=r.final_score / 100,  # store as 0-1
            explanation=r.explanation,
            rank_position=r.rank_position,
        ))

    await db.commit()

    # Build response
    rankings = [
        ProviderRanking(
            provider_id=uuid.UUID(r.provider_id),
            provider_name=r.provider_name,
            rank_position=r.rank_position,
            final_score=r.final_score,
            topsis_score=r.topsis_score,
            xgb_score=r.xgb_score,
            cost_usd=r.cost_usd,
            value_score=r.value_score,
            explanation=r.explanation,
            meets_uptime=r.meets_uptime,
            meets_rto=r.meets_rto,
            meets_region=r.meets_region,
            compliance_tags=r.compliance_tags,
        )
        for r in pipeline_result.provider_results
    ]

    parsed = ParsedRequirements(
        uptime_required_pct=req_data.uptime_required_pct,
        rto_hours=req_data.rto_hours,
        rpo_hours=req_data.rpo_hours,
        region=req_data.region,
        country=req_data.country,
        compliance=req_data.compliance,
        category=req_data.category,
        sensitivity=req_data.sensitivity,
        budget_usd_monthly=req_data.budget_usd_monthly,
    )

    return QueryResponse(
        query_id=query_id,
        detected_lang=pipeline_result.detected_lang,
        parsed_requirements=parsed,
        rankings=rankings,
    )


@router.get("/compare")
async def compare_providers(
    providers: str,
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/compare?providers=AWS,Azure,GCP
    Returns side-by-side SLA metrics and pricing for named providers.
    """
    names = [p.strip() for p in providers.split(",")]
    result = []
    for name in names:
        prov_result = await db.execute(
            select(Provider).where(Provider.name.ilike(name))
        )
        provider = prov_result.scalar_one_or_none()
        if not provider:
            continue
        metrics_result = await db.execute(
            select(SLAMetrics)
            .where(SLAMetrics.provider_id == provider.id)
            .order_by(SLAMetrics.extracted_at.desc())
            .limit(1)
        )
        m = metrics_result.scalar_one_or_none()

        # Fetch latest pricing for this provider
        pricing_result = await db.execute(
            select(PricingCache)
            .where(PricingCache.provider_id == provider.id)
            .order_by(PricingCache.fetched_at.desc())
            .limit(10)
        )
        pricing_items = pricing_result.scalars().all()

        result.append({
            "provider": provider.name,
            "metrics": {
                "uptime_sla_pct": m.uptime_sla_pct if m else None,
                "rto_hours": m.rto_hours if m else None,
                "rpo_hours": m.rpo_hours if m else None,
                "support_response_min": m.support_response_min if m else None,
                "penalty_credit_pct": m.penalty_credit_pct if m else None,
                "regions": m.regions if m else [],
                "compliance": m.compliance if m else [],
                "source_clause": m.source_clause if m else None,
            },
            "pricing": [
                {
                    "service": p.service,
                    "sku": p.sku,
                    "region": p.region,
                    "price_usd": p.price_usd,
                    "unit": p.unit,
                }
                for p in pricing_items
            ],
        })
    return {"comparison": result}