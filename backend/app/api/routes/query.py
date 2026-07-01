"""
POST /api/query  — main recommendation endpoint
GET  /api/compare — side-by-side comparison
"""

import logging
import re
import uuid
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.schemas import QueryRequest, QueryResponse, ProviderRanking, ParsedRequirements
from app.db.session import get_db
from app.models.models import Provider, SLADocument, SLAMetrics, Query, Ranking, PricingCache
from app.services.ranking_pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

_LOW_CONFIDENCE_THRESHOLD = 30.0  # final_score out of 100

# Official SLA page per canonical provider name (fallback when no ingested URL exists)
_OFFICIAL_SLA_URL: dict[str, str] = {
    "AWS":    "https://aws.amazon.com/legal/service-level-agreements/",
    "Azure":  "https://azure.microsoft.com/en-us/support/legal/sla/summary/",
    "GCP":    "https://cloud.google.com/terms/sla",
    "Oracle": "https://www.oracle.com/cloud/sla/",
    "IBM":    "https://www.ibm.com/support/customer/csol/terms/?id=i126-6605&lc=en",
}


def _provider_sla_url(provider_name: str, doc_file_path: str | None) -> str | None:
    """Return the best SLA URL: ingested URL first, then curated fallback."""
    if doc_file_path and doc_file_path.startswith("http"):
        return doc_file_path
    key = provider_name.strip()
    return _OFFICIAL_SLA_URL.get(key)


# Patterns that indicate the LLM extracted a header/phrase as if it were a
# region name. Anything matching these gets dropped before unioning with the
# curated list — without this, garbage like "AWS Region" or "Cloud Regions
# (excluding Mexico and Stockholm)" pollutes the region count and crowds out
# real entries.
_REGION_NOISE_PATTERNS = [
    re.compile(r"\bregion\b",            re.IGNORECASE),    # "Region" / "AWS Region"
    re.compile(r"\bavailability\s*zone", re.IGNORECASE),    # "AWS Availability Zone (AZ)"
    re.compile(r"\bcloud\s+regions?\b",  re.IGNORECASE),    # "Cloud Regions ..."
    re.compile(r"\bzone\b",              re.IGNORECASE),    # bare "Zone"
    re.compile(r"^\s*$"),                                    # empty / whitespace
]


def _looks_like_real_region(s: str | None) -> bool:
    """Reject extraction noise. A real region ID is short, contains no spaces
    in its core token, and doesn't match the noise patterns above."""
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if not s or len(s) > 60:           # real region IDs are well under this
        return False
    for pat in _REGION_NOISE_PATTERNS:
        if pat.search(s):
            return False
    return True


def _merge_regions(extracted: list | None, curated: list | None) -> list:
    """Union extracted (after noise filtering) with curated, de-duplicated,
    order-preserving — curated first, then any new real regions from
    extraction. Curated stays the trustworthy baseline; extraction can only
    ADD regions, never erase the baseline."""
    out: dict[str, None] = {}
    for r in (curated or []):
        if _looks_like_real_region(r):
            out.setdefault(r.strip(), None)
    for r in (extracted or []):
        if _looks_like_real_region(r):
            out.setdefault(r.strip(), None)
    return list(out.keys())


def _merge_compliance(extracted: list | None, curated: list | None) -> list:
    """Union extracted with curated, de-duplicated, order-preserving. Less
    noise-prone than regions, so we keep almost everything — just drop empty
    strings and obvious junk."""
    out: dict[str, None] = {}
    for c in (curated or []):
        if isinstance(c, str) and c.strip():
            out.setdefault(c.strip(), None)
    for c in (extracted or []):
        if isinstance(c, str) and c.strip() and len(c) < 80:
            out.setdefault(c.strip(), None)
    return list(out.keys())


# Aggregation direction per metric for the "best-of" rollup. Each ingested SLA
# document yields one SLAMetrics row; when a provider has multiple (e.g. EC2 +
# S3 + RDS), we collapse them into a single representative row by picking the
# best value for each field rather than the most-recent. Compare/Recommend
# stop oscillating as new docs arrive, and the provider is judged on its
# strongest commitments across everything ingested.
_METRIC_AGGREGATIONS = {
    "uptime_sla_pct":       "max",   # higher uptime = better
    "rto_hours":            "min",   # lower recovery time = better
    "rpo_hours":            "min",   # lower data-loss window = better
    "support_response_min": "min",   # faster support = better
    "penalty_credit_pct":   "max",   # higher credit = better
}


def _aggregate_metrics(rows: list) -> "SimpleNamespace | None":
    """
    Roll all SLAMetrics rows for one provider into a single representative row
    using best-of-each-metric aggregation. Region/compliance are unioned so
    coverage grows monotonically as more docs are ingested.

    Returns None if `rows` is empty so the caller can fall back to curated data.
    """
    if not rows:
        return None

    agg: dict = {}
    for field, op in _METRIC_AGGREGATIONS.items():
        values = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        if values:
            agg[field] = max(values) if op == "max" else min(values)
        else:
            agg[field] = None

    # Union region and compliance lists across all documents (de-duplicated,
    # order-preserving so the UI shows a stable list).
    seen_regions: dict[str, None] = {}
    seen_compliance: dict[str, None] = {}
    for r in rows:
        for region in (r.regions or []):
            seen_regions.setdefault(region, None)
        for tag in (r.compliance or []):
            seen_compliance.setdefault(tag, None)
    agg["regions"] = list(seen_regions.keys())
    agg["compliance"] = list(seen_compliance.keys())

    return SimpleNamespace(**agg)


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

    # Load all providers + latest SLA metrics + latest doc URL
    providers_result = await db.execute(select(Provider))
    providers = providers_result.scalars().all()

    providers_with_metrics = []
    provider_urls: dict[str, str | None] = {}   # provider_id → best SLA URL
    for provider in providers:
        # Pull every metrics row for this provider, then aggregate best-of
        # across them. With multiple ingested SLAs (e.g. EC2 + S3) the
        # provider is judged on its strongest commitments overall rather
        # than whichever document happened to be ingested last.
        metrics_result = await db.execute(
            select(SLAMetrics).where(SLAMetrics.provider_id == provider.id)
        )
        all_rows = list(metrics_result.scalars().all())
        metrics = _aggregate_metrics(all_rows)

        # Latest ingested document path/URL for this provider
        doc_result = await db.execute(
            select(SLADocument.file_path)
            .where(SLADocument.provider_id == provider.id)
            .order_by(SLADocument.ingested_at.desc())
            .limit(1)
        )
        latest_doc_path = doc_result.scalar_one_or_none()
        provider_urls[str(provider.id)] = _provider_sla_url(provider.name, latest_doc_path)

        # Merge extracted metrics with curated public SLA values.
        # The LLM extraction is best-effort and often leaves critical fields
        # (uptime/RTO/RPO/support) as None when the document text doesn't
        # surface them clearly. Without a per-field merge, a provider whose
        # extraction came back mostly empty would be scored on pipeline
        # safety defaults (uptime=99.9, rto=24h, ...) — which silently
        # tanks its ranking below providers that have no extracted row at
        # all and therefore use the full curated values. Per-field fill
        # below makes extracted + curated additive rather than mutually
        # exclusive: any extracted value wins, anything missing falls back
        # to the curated public commitment for that provider.
        curated = _curated_for(provider.name)
        if metrics is None:
            metrics = SimpleNamespace(
                uptime_sla_pct=curated.get("uptime_sla_pct"),
                rto_hours=curated.get("rto_hours"),
                rpo_hours=curated.get("rpo_hours"),
                support_response_min=curated.get("support_response_min"),
                penalty_credit_pct=curated.get("penalty_credit_pct"),
                regions=curated.get("regions", []),
                compliance=curated.get("compliance", []),
            )
        elif curated:
            for field in ("uptime_sla_pct", "rto_hours", "rpo_hours",
                          "support_response_min", "penalty_credit_pct"):
                if getattr(metrics, field, None) is None:
                    setattr(metrics, field, curated.get(field))
            if not getattr(metrics, "regions", None):
                metrics.regions = curated.get("regions", [])
            if not getattr(metrics, "compliance", None):
                metrics.compliance = curated.get("compliance", [])

        # Floor pass — an extracted value must never make a provider rank
        # worse than pure curated would have. Take the better of
        # (extracted, curated) per field: max for benefit metrics (where
        # higher is better) and min for cost metrics (where lower is
        # better). Without this, a provider whose LLM extraction returned
        # one weak number (e.g. AWS extracted uptime=99.9 vs its curated
        # 99.99) is silently penalised below a provider whose extraction
        # failed completely and got full curated values. See plan:
        # /Users/i769765/.claude/plans/add-this-functionality-and-concurrent-steele.md
        if curated:
            _BENEFIT_FIELDS = ("uptime_sla_pct", "penalty_credit_pct")
            _COST_FIELDS    = ("rto_hours", "rpo_hours", "support_response_min")
            trace: list[str] = []
            for f in _BENEFIT_FIELDS:
                ev = getattr(metrics, f, None)
                cv = curated.get(f)
                if ev is not None and cv is not None and cv > ev:
                    setattr(metrics, f, cv)
                    trace.append(f"{f}: extracted={ev} curated={cv} -> {cv} (curated won)")
                elif ev is not None and cv is not None:
                    trace.append(f"{f}: extracted={ev} curated={cv} -> {ev} (extracted kept)")
            for f in _COST_FIELDS:
                ev = getattr(metrics, f, None)
                cv = curated.get(f)
                if ev is not None and cv is not None and cv < ev:
                    setattr(metrics, f, cv)
                    trace.append(f"{f}: extracted={ev} curated={cv} -> {cv} (curated won)")
                elif ev is not None and cv is not None:
                    trace.append(f"{f}: extracted={ev} curated={cv} -> {ev} (extracted kept)")
            if trace:
                logger.info("Floor pass for %s: %s", provider.name, "; ".join(trace))

        providers_with_metrics.append((str(provider.id), provider.name, metrics))

    # Run the full 6-stage pipeline
    pipeline_result = run_pipeline(
        raw_query=req.text,
        providers_with_metrics=providers_with_metrics,
        weights=req.weights,
        lang=req.lang,
        service_category=req.service_category,
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
            # In service-category mode each row carries a service-specific
            # sla_url. Fall back to the provider-level URL otherwise.
            sla_url=(r.sla_url or provider_urls.get(r.provider_id)),
            service_name=r.service_name,
            service_uptime_pct=r.service_uptime_pct,
            service_rto_hours=r.service_rto_hours,
            service_rpo_hours=r.service_rpo_hours,
            service_category=r.service_category,
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


# Curated public SLA values for major CSPs (used when no extracted metrics exist).
# `regions` lists are the vendor's full publicly-announced general-availability
# regions as of 2026, taken from each provider's public regions/locations page.
# These are NOT availability zones — only top-level geographic regions. We use
# vendor-native region IDs (e.g. AWS "us-east-1", Azure "eastus", GCP
# "us-central1") because that's what the LLM extraction produces, and we want
# extracted+curated values to unify cleanly in _aggregate_metrics.
_CURATED: dict[str, dict] = {
    "aws": {
        "uptime_sla_pct": 99.99,
        "rto_hours": 4.0,
        "rpo_hours": 1.0,
        "support_response_min": 60,
        "penalty_credit_pct": 10,
        "regions": [
            # Americas
            "us-east-1", "us-east-2", "us-west-1", "us-west-2",
            "us-gov-east-1", "us-gov-west-1",
            "ca-central-1", "ca-west-1",
            "sa-east-1", "mx-central-1",
            # Europe
            "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-central-2",
            "eu-north-1", "eu-south-1", "eu-south-2",
            # Asia Pacific
            "ap-south-1", "ap-south-2", "ap-southeast-1", "ap-southeast-2",
            "ap-southeast-3", "ap-southeast-4", "ap-southeast-5", "ap-southeast-7",
            "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
            "ap-east-1",
            # Middle East & Africa
            "me-south-1", "me-central-1", "il-central-1",
            "af-south-1",
        ],
        "compliance": ["SOC2", "ISO27001", "PCI-DSS", "HIPAA", "GDPR", "FedRAMP", "FIPS 140-2"],
    },
    "azure": {
        "uptime_sla_pct": 99.995,
        "rto_hours": 1.0,
        "rpo_hours": 0.5,
        "support_response_min": 15,
        "penalty_credit_pct": 30,
        "regions": [
            # Americas
            "eastus", "eastus2", "eastus3", "centralus", "northcentralus",
            "southcentralus", "westcentralus", "westus", "westus2", "westus3",
            "canadacentral", "canadaeast",
            "brazilsouth", "brazilsoutheast", "mexicocentral",
            # Europe
            "northeurope", "westeurope",
            "uksouth", "ukwest",
            "francecentral", "francesouth",
            "germanywestcentral", "germanynorth",
            "swedencentral", "swedensouth",
            "switzerlandnorth", "switzerlandwest",
            "norwayeast", "norwaywest",
            "polandcentral", "italynorth", "spaincentral",
            # Asia Pacific
            "southeastasia", "eastasia",
            "japaneast", "japanwest",
            "koreacentral", "koreasouth",
            "australiaeast", "australiasoutheast", "australiacentral", "australiacentral2",
            "centralindia", "southindia", "westindia", "jioindiawest", "jioindiacentral",
            # Middle East & Africa
            "uaenorth", "uaecentral", "qatarcentral", "israelcentral",
            "southafricanorth", "southafricawest",
        ],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS", "FedRAMP", "CCPA"],
    },
    "gcp": {
        "uptime_sla_pct": 99.95,
        "rto_hours": 2.0,
        "rpo_hours": 1.0,
        "support_response_min": 60,
        "penalty_credit_pct": 25,
        "regions": [
            # Americas
            "us-central1", "us-east1", "us-east4", "us-east5", "us-south1",
            "us-west1", "us-west2", "us-west3", "us-west4",
            "northamerica-northeast1", "northamerica-northeast2", "northamerica-south1",
            "southamerica-east1", "southamerica-west1",
            # Europe
            "europe-central2", "europe-north1",
            "europe-southwest1",
            "europe-west1", "europe-west2", "europe-west3", "europe-west4",
            "europe-west6", "europe-west8", "europe-west9", "europe-west10", "europe-west12",
            # Asia Pacific
            "asia-east1", "asia-east2",
            "asia-northeast1", "asia-northeast2", "asia-northeast3",
            "asia-south1", "asia-south2",
            "asia-southeast1", "asia-southeast2",
            "australia-southeast1", "australia-southeast2",
            # Middle East & Africa
            "me-central1", "me-central2", "me-west1",
            "africa-south1",
        ],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS", "FedRAMP"],
    },
    "google": {
        # Alias for "gcp" — kept for back-compat when LLM extracts the name as "Google"
        "uptime_sla_pct": 99.95,
        "rto_hours": 2.0,
        "rpo_hours": 1.0,
        "support_response_min": 60,
        "penalty_credit_pct": 25,
        "regions": [
            "us-central1", "us-east1", "us-east4", "us-east5", "us-south1",
            "us-west1", "us-west2", "us-west3", "us-west4",
            "northamerica-northeast1", "northamerica-northeast2", "northamerica-south1",
            "southamerica-east1", "southamerica-west1",
            "europe-central2", "europe-north1", "europe-southwest1",
            "europe-west1", "europe-west2", "europe-west3", "europe-west4",
            "europe-west6", "europe-west8", "europe-west9", "europe-west10", "europe-west12",
            "asia-east1", "asia-east2",
            "asia-northeast1", "asia-northeast2", "asia-northeast3",
            "asia-south1", "asia-south2",
            "asia-southeast1", "asia-southeast2",
            "australia-southeast1", "australia-southeast2",
            "me-central1", "me-central2", "me-west1",
            "africa-south1",
        ],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS"],
    },
    "oracle": {
        "uptime_sla_pct": 99.95,
        "rto_hours": 4.0,
        "rpo_hours": 2.0,
        "support_response_min": 120,
        "penalty_credit_pct": 25,
        "regions": [
            # Americas
            "us-ashburn-1", "us-phoenix-1", "us-chicago-1", "us-sanjose-1",
            "us-gov-ashburn-1", "us-gov-chicago-1", "us-gov-phoenix-1",
            "ca-toronto-1", "ca-montreal-1",
            "sa-saopaulo-1", "sa-vinhedo-1", "sa-santiago-1", "sa-bogota-1", "sa-valparaiso-1",
            "mx-queretaro-1", "mx-monterrey-1",
            # Europe
            "uk-london-1", "uk-cardiff-1", "uk-gov-london-1", "uk-gov-cardiff-1",
            "eu-frankfurt-1", "eu-zurich-1", "eu-amsterdam-1",
            "eu-stockholm-1", "eu-paris-1", "eu-milan-1", "eu-madrid-1", "eu-marseille-1",
            "eu-jovanovac-1",
            # Asia Pacific
            "ap-mumbai-1", "ap-hyderabad-1",
            "ap-tokyo-1", "ap-osaka-1",
            "ap-seoul-1", "ap-chuncheon-1",
            "ap-singapore-1", "ap-singapore-2",
            "ap-sydney-1", "ap-melbourne-1",
            # Middle East & Africa
            "me-dubai-1", "me-jeddah-1", "me-abudhabi-1", "me-riyadh-1",
            "il-jerusalem-1",
            "af-johannesburg-1",
        ],
        "compliance": ["GDPR", "HIPAA", "SOC2", "ISO27001", "PCI-DSS", "FedRAMP"],
    },
    "ibm": {
        "uptime_sla_pct": 99.9,
        "rto_hours": 8.0,
        "rpo_hours": 4.0,
        "support_response_min": 120,
        "penalty_credit_pct": 10,
        "regions": [
            # Multi-zone regions
            "us-south", "us-east", "ca-tor", "br-sao",
            "eu-de", "eu-gb", "eu-es", "eu-fr2",
            "jp-tok", "jp-osa", "au-syd", "in-che",
            # Single-zone / classic data-center regions
            "wdc04", "wdc06", "wdc07", "dal10", "dal12", "dal13", "sjc03", "sjc04",
            "tor01", "mon01", "mex01", "sao01",
            "lon02", "lon04", "lon05", "lon06", "fra02", "fra04", "fra05",
            "ams03", "mil01", "par01", "osl01", "sng01",
            "tok02", "tok04", "tok05", "osa21", "hkg02", "seo01",
            "syd01", "syd04", "syd05",
            "che01", "mum01",
        ],
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

        # Aggregate best-of across every ingested SLAMetrics row for this
        # provider (see _aggregate_metrics). Falls back to curated values per
        # missing field via _v() below.
        metrics_result = await db.execute(
            select(SLAMetrics).where(SLAMetrics.provider_id == provider.id)
        )
        all_rows = list(metrics_result.scalars().all())
        m = _aggregate_metrics(all_rows)
        fallback = _curated_for(provider.name)

        def _v(extracted, key):
            return extracted if extracted is not None else fallback.get(key)

        regions = _merge_regions(m.regions if m else None, fallback.get("regions", []))
        compliance = _merge_compliance(m.compliance if m else None, fallback.get("compliance", []))

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
