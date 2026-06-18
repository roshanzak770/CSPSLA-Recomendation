"""
POST /api/query  — main recommendation endpoint
GET  /api/compare — side-by-side comparison
"""

import uuid
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.schemas import QueryRequest, QueryResponse, ProviderRanking, ParsedRequirements
from app.db.session import get_db
from app.models.models import Provider, SLADocument, SLAMetrics, Query, Ranking, PricingCache
from app.services.ranking_pipeline import run_pipeline

router = APIRouter()

_LOW_CONFIDENCE_THRESHOLD = 30.0  # final_score out of 100


@router.post("/query", response_model=QueryResponse)
async def run_query(req: QueryRequest, db: AsyncSession = Depends(get_db)):
    # Check if ANY SLA documents have been ingested
    doc_count_result = await db.execute(select(func.count()).select_from(SLADocument))
    doc_count = doc_count_result.scalar() or 0

    if doc_count == 0:
        # No docs at all — signal frontend to offer auto-fetch
        return QueryResponse(
            query_id=uuid.uuid4(),
            detected_lang=None,
            parsed_requirements=None,
            rankings=[],
            auto_fetch_available=True,
            message=(
                "No SLA documents have been ingested yet. "
                "Click 'Auto-fetch SLA Docs' to automatically retrieve official SLA documents "
                "from cloud provider websites, or use the Discover tab to search and select manually."
            ),
        )

    # Load all providers + latest SLA metrics
    providers_result = await db.execute(select(Provider))
    providers = providers_result.scalars().all()

    providers_with_metrics = []
    for provider in providers:
        metrics_result = await db.execute(
            select(SLAMetrics)
            .where(SLAMetrics.provider_id == provider.id)
            .order_by(SLAMetrics.extracted_at.desc())
            .limit(1)
        )
        metrics = metrics_result.scalar_one_or_none()

        # Fall back to curated public SLA values when no extracted metrics exist
        if metrics is None:
            curated = _curated_for(provider.name)
            if curated:
                metrics = SimpleNamespace(
                    uptime_sla_pct=curated.get("uptime_sla_pct"),
                    rto_hours=curated.get("rto_hours"),
                    rpo_hours=curated.get("rpo_hours"),
                    support_response_min=curated.get("support_response_min"),
                    penalty_credit_pct=curated.get("penalty_credit_pct"),
                    regions=curated.get("regions", []),
                    compliance=curated.get("compliance", []),
                )

        providers_with_metrics.append((str(provider.id), provider.name, metrics))

    # Run the full 6-stage pipeline
    pipeline_result = run_pipeline(
        raw_query=req.text,
        providers_with_metrics=providers_with_metrics,
        weights=req.weights,
        lang=req.lang,
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
            xgb_cold_start=r.xgb_cold_start,
            cosine_score=r.cosine_score,
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

    # Detect low-confidence: top result scored under threshold
    max_score = max((r.final_score for r in pipeline_result.provider_results), default=0)
    low_confidence = max_score < _LOW_CONFIDENCE_THRESHOLD
    suggestion = (
        "No SLA content strongly matched your query. "
        "Consider fetching updated documents — click 'Fetch Updated SLAs' below."
        if low_confidence else None
    )

    return QueryResponse(
        query_id=query_id,
        detected_lang=pipeline_result.detected_lang,
        parsed_requirements=parsed,
        rankings=rankings,
        low_confidence=low_confidence or None,
        suggestion=suggestion,
        lang=req.lang,
    )


# Curated public SLA values for major CSPs (used when no extracted metrics exist)
_CURATED: dict[str, dict] = {
    "aws": {
        "uptime_sla_pct": 99.99,
        "rto_hours": 4.0,
        "rpo_hours": 1.0,
        "support_response_min": 60,
        "penalty_credit_pct": 10,
        "regions": ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1", "ap-southeast-1",
                    "sa-east-1", "af-south-1", "me-south-1"],
        "compliance": ["SOC2", "ISO27001", "PCI-DSS", "HIPAA", "GDPR", "FedRAMP", "FIPS 140-2"],
    },
    "azure": {
        "uptime_sla_pct": 99.995,
        "rto_hours": 1.0,
        "rpo_hours": 0.5,
        "support_response_min": 15,
        "penalty_credit_pct": 30,
        "regions": ["eastus", "westus2", "westeurope", "northeurope", "southeastasia",
                    "centralindia", "southindia", "brazilsouth", "australiaeast"],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS", "FedRAMP", "CCPA"],
    },
    "gcp": {
        "uptime_sla_pct": 99.95,
        "rto_hours": 2.0,
        "rpo_hours": 1.0,
        "support_response_min": 60,
        "penalty_credit_pct": 25,
        "regions": ["us-central1", "us-east1", "europe-west1", "europe-west4", "asia-south1",
                    "asia-southeast1", "southamerica-east1", "australia-southeast1"],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS", "FedRAMP"],
    },
    "google": {
        "uptime_sla_pct": 99.95,
        "rto_hours": 2.0,
        "rpo_hours": 1.0,
        "support_response_min": 60,
        "penalty_credit_pct": 25,
        "regions": ["us-central1", "europe-west1", "asia-south1"],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS"],
    },
    "oracle": {
        "uptime_sla_pct": 99.95,
        "rto_hours": 4.0,
        "rpo_hours": 2.0,
        "support_response_min": 120,
        "penalty_credit_pct": 25,
        "regions": ["ap-mumbai-1", "ap-hyderabad-1", "us-ashburn-1", "eu-frankfurt-1",
                    "ap-tokyo-1", "ap-sydney-1"],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS", "FedRAMP"],
    },
    "ibm": {
        "uptime_sla_pct": 99.9,
        "rto_hours": 8.0,
        "rpo_hours": 4.0,
        "support_response_min": 120,
        "penalty_credit_pct": 10,
        "regions": ["us-south", "us-east", "eu-de", "eu-gb", "jp-tok", "in-che"],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "FedRAMP"],
    },
}


def _curated_for(name: str) -> dict:
    k = name.lower()
    for key, data in _CURATED.items():
        if key in k:
            return data
    return {}


@router.get("/compare")
async def compare_providers(
    providers: str,
    metrics: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    GET /api/compare?providers=AWS,Azure,GCP&metrics=uptime_sla_pct,rto_hours
    Returns a pivoted comparison table (one row per metric), trophies, and advantages.
    If no extracted metrics exist for a provider, falls back to curated public SLA values.
    """
    names = [p.strip() for p in providers.split(",") if p.strip()]
    metric_filter = {m.strip() for m in metrics.split(",")} if metrics else None

    METRIC_DEFS = [
        {"field": "uptime_sla_pct",       "label": "Uptime SLA (%)",        "unit": "%",    "higher": True},
        {"field": "rto_hours",            "label": "RTO",                   "unit": "h",    "higher": False},
        {"field": "rpo_hours",            "label": "RPO",                   "unit": "h",    "higher": False},
        {"field": "support_response_min", "label": "Support Response",      "unit": "min",  "higher": False},
        {"field": "penalty_credit_pct",   "label": "SLA Credit (%)",        "unit": "%",    "higher": True},
        {"field": "region_count",         "label": "Regions Covered",       "unit": "",     "higher": True},
        {"field": "compliance_count",     "label": "Compliance Standards",  "unit": "",     "higher": True},
        {"field": "min_compute_usd",      "label": "Min Compute Price",     "unit": "$/hr", "higher": False},
    ]

    if metric_filter:
        METRIC_DEFS = [m for m in METRIC_DEFS if m["field"] in metric_filter]

    # Gather data per provider
    provider_data: dict[str, dict] = {}
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
        fallback = _curated_for(provider.name)

        def _v(extracted, key):
            return extracted if extracted is not None else fallback.get(key)

        regions = (m.regions if m and m.regions else None) or fallback.get("regions", [])
        compliance = (m.compliance if m and m.compliance else None) or fallback.get("compliance", [])

        # Cheapest compute price from PricingCache
        pricing_result = await db.execute(
            select(func.min(PricingCache.price_usd))
            .where(
                PricingCache.provider_id == provider.id,
                PricingCache.service.ilike("%compute%") | PricingCache.service.ilike("%EC2%")
                | PricingCache.service.ilike("%virtual%") | PricingCache.service.ilike("%instance%"),
                PricingCache.price_usd > 0,
            )
        )
        min_compute = pricing_result.scalar()

        # Cheapest overall if no compute found
        if min_compute is None:
            overall_result = await db.execute(
                select(func.min(PricingCache.price_usd))
                .where(PricingCache.provider_id == provider.id, PricingCache.price_usd > 0)
            )
            min_compute = overall_result.scalar()

        provider_data[provider.name] = {
            "uptime_sla_pct":       _v(m.uptime_sla_pct if m else None,       "uptime_sla_pct"),
            "rto_hours":            _v(m.rto_hours if m else None,             "rto_hours"),
            "rpo_hours":            _v(m.rpo_hours if m else None,             "rpo_hours"),
            "support_response_min": _v(m.support_response_min if m else None,  "support_response_min"),
            "penalty_credit_pct":   _v(m.penalty_credit_pct if m else None,    "penalty_credit_pct"),
            "region_count":         len(regions),
            "compliance_count":     len(compliance),
            "compliance_list":      compliance,
            "regions_list":         regions,
            "min_compute_usd":      round(min_compute, 6) if min_compute else None,
            "has_extracted_metrics": m is not None,
        }

    if not provider_data:
        raise HTTPException(status_code=404, detail="None of the requested providers found.")

    prov_names = list(provider_data.keys())

    # Build pivoted rows + determine trophies
    rows = []
    trophies: dict[str, str] = {}

    for md in METRIC_DEFS:
        field = md["field"]
        row: dict = {"field": field, "label": md["label"], "unit": md["unit"]}

        numeric_vals: dict[str, float] = {}
        for pname in prov_names:
            v = provider_data[pname].get(field)
            if field == "min_compute_usd" and v is not None:
                row[pname] = v          # raw float kept for frontend formatting
            elif field in ("region_count", "compliance_count"):
                row[pname] = int(v) if v is not None else None
            else:
                row[pname] = v
            if v is not None:
                numeric_vals[pname] = float(v)

        if numeric_vals:
            winner = (max if md["higher"] else min)(numeric_vals, key=numeric_vals.get)
            trophies[field] = winner

        rows.append(row)

    # Advantages: label each provider's wins
    advantages: dict[str, list[str]] = {}
    for field, winner in trophies.items():
        label = next((m["label"] for m in METRIC_DEFS if m["field"] == field), field)
        advantages.setdefault(winner, []).append(label)

    # Per-provider details (compliance list, regions, data source tag)
    details: dict[str, dict] = {}
    for pname, data in provider_data.items():
        details[pname] = {
            "compliance": data["compliance_list"],
            "regions":    data["regions_list"],
            "data_source": "extracted" if data["has_extracted_metrics"] else "curated",
        }

    return {
        "providers": prov_names,
        "comparison": rows,
        "trophies":   trophies,
        "advantages": advantages,
        "details":    details,
    }
