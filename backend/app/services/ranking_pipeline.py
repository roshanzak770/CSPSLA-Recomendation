"""
Ranking Pipeline — orchestrates all 6 stages end-to-end.

Stage 1: Query Understanding  (Qwen2.5-7B)
Stage 2: Semantic Retrieval   (multilingual-e5 + ChromaDB)
Stage 3: Metrics Extraction   (Llama-3.1-8B) — uses cached DB metrics
Stage 4: TOPSIS Scoring       (NumPy — local)
Stage 5: XGBoost Re-ranking   (local, cold-start safe)
Stage 6: LLM Explanation      (Qwen2.5-7B)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.services.topsis import ProviderMetrics, TOPSISResult, topsis_rank, DEFAULT_WEIGHTS
from app.services.ranker import predict

logger = logging.getLogger(__name__)


@dataclass
class QueryRequirements:
    uptime_required_pct: Optional[float] = None
    rto_hours: Optional[float] = None
    rpo_hours: Optional[float] = None
    region: Optional[str] = None
    country: Optional[str] = None
    compliance: List[str] = field(default_factory=list)
    category: Optional[str] = None
    sensitivity: str = "MEDIUM"
    budget_usd_monthly: Optional[float] = None


@dataclass
class ProviderResult:
    provider_id: str
    provider_name: str
    rank_position: int
    final_score: float          # 0–100
    topsis_score: float
    xgb_score: float
    cosine_score: float
    xgb_cold_start: bool
    cost_usd: Optional[float]
    value_score: Optional[float]
    explanation: Optional[str]
    meets_uptime: Optional[bool]
    meets_rto: Optional[bool]
    meets_region: Optional[bool]
    compliance_tags: List[str] = field(default_factory=list)
    sla_uptime_pct: Optional[float] = None
    sla_rto_hours: Optional[float] = None
    sla_url: Optional[str] = None
    # When the request specified a service_category, these capture which
    # specific service this row represents (e.g. "Amazon S3 Standard"
    # instead of just "AWS") and its actual published SLA values.
    service_name:       Optional[str]   = None
    service_uptime_pct: Optional[float] = None
    service_rto_hours:  Optional[float] = None
    service_rpo_hours:  Optional[float] = None
    service_category:   Optional[str]   = None


@dataclass
class PipelineResult:
    requirements: QueryRequirements
    provider_results: List[ProviderResult]
    detected_lang: str
    english_query: str


# ---------------------------------------------------------------------------
# Weight key mapping — frontend slider keys → TOPSIS criteria keys
# ---------------------------------------------------------------------------

_WEIGHT_KEY_MAP = {
    "uptime":      "uptime_sla_pct",
    "support":     "support_response_min",
    "penalties":   "penalty_credit_pct",
    "geographic":  "region_coverage",
    "security":    "penalty_credit_pct",   # no direct security criterion; proxy via penalties
}


def _map_weights(frontend_weights: dict) -> dict:
    """Convert frontend slider keys to TOPSIS criteria keys, merging duplicates by max."""
    from app.services.topsis import DEFAULT_WEIGHTS
    result = dict(DEFAULT_WEIGHTS)          # start from defaults so all keys present
    for fk, value in frontend_weights.items():
        tk = _WEIGHT_KEY_MAP.get(fk)
        if tk:
            result[tk] = max(result.get(tk, 0.0), float(value))
    # Re-normalise so weights sum to 1.0
    total = sum(result.values()) or 1.0
    return {k: v / total for k, v in result.items()}


# ---------------------------------------------------------------------------
# Stage 1 — Query Understanding
# ---------------------------------------------------------------------------

def stage1_understand_query(english_query: str) -> QueryRequirements:
    from app.services.llm_router import llm_router
    try:
        parsed = llm_router.understand_query(english_query)
    except Exception as e:
        logger.warning("LLM query understanding failed: %s", e)
        parsed = {}

    return QueryRequirements(
        uptime_required_pct=parsed.get("uptime_required_pct"),
        rto_hours=parsed.get("rto_hours"),
        rpo_hours=parsed.get("rpo_hours"),
        region=parsed.get("region"),
        country=parsed.get("country"),
        compliance=[c for c in (parsed.get("compliance") or [])],
        category=parsed.get("category"),
        sensitivity=parsed.get("sensitivity") or "MEDIUM",
        budget_usd_monthly=parsed.get("budget_usd_monthly"),
    )


# ---------------------------------------------------------------------------
# Stage 2 — Semantic Retrieval
# ---------------------------------------------------------------------------

def stage2_retrieve_chunks(english_query: str, provider_names: List[str]) -> dict[str, float]:
    """Returns {provider_name: best_cosine_score}, filtered per-provider in ChromaDB."""
    from app.services.ingestion import search_sla
    scores: dict[str, float] = {}
    for name in provider_names:
        try:
            chunks = search_sla(english_query, provider_filter=[name], top_k=5)
            for chunk in chunks:
                score = chunk.get("score", 0.0)
                if name not in scores or score > scores[name]:
                    scores[name] = score
        except Exception as e:
            logger.warning("ChromaDB retrieval failed for %s: %s", name, e)
    return scores


# ---------------------------------------------------------------------------
# Stage 3 — Use cached SLA metrics (already extracted by ingestion pipeline)
# ---------------------------------------------------------------------------

def _build_topsis_input(provider_id: str, provider_name: str, metrics) -> ProviderMetrics:
    region_count = float(len(metrics.regions or []))
    return ProviderMetrics(
        provider_id=provider_id,
        provider_name=provider_name,
        uptime_sla_pct=metrics.uptime_sla_pct or 99.9,
        rto_hours=metrics.rto_hours or 24.0,
        rpo_hours=metrics.rpo_hours or 24.0,
        support_response_min=float(metrics.support_response_min or 60),
        penalty_credit_pct=float(metrics.penalty_credit_pct or 10),
        region_coverage=region_count if region_count > 0 else 1.0,
    )


# ---------------------------------------------------------------------------
# Stage 5 — Build XGBoost feature records
# ---------------------------------------------------------------------------

def _build_xgb_record(
    tr: TOPSISResult,
    cosine_scores: dict,
    req: QueryRequirements,
    metrics,
) -> dict:
    provider_regions = [r.lower() for r in (metrics.regions or [])] if metrics else []
    provider_compliance = [c.lower() for c in (metrics.compliance or [])] if metrics else []
    required_compliance = [c.lower() for c in req.compliance]

    compliance_overlap = (
        len(set(required_compliance) & set(provider_compliance)) / len(required_compliance)
        if required_compliance else 1.0
    )
    region_match = (
        int(any((req.region or "").lower() in r for r in provider_regions))
        if req.region else 1
    )

    category_map = {"database": 0, "compute": 1, "storage": 2, "network": 3}
    category_encoded = category_map.get(req.category or "", 0)

    return {
        "cosine_similarity_score": cosine_scores.get(tr.provider_name, 0.0),
        "topsis_score": tr.topsis_score,
        "uptime_delta": ((metrics.uptime_sla_pct or 0) - (req.uptime_required_pct or 99.9)) if metrics else 0.0,
        "rto_meets_requirement": int((metrics.rto_hours or 99) <= (req.rto_hours or 24)) if metrics else 0,
        "region_match": region_match,
        "compliance_overlap_pct": compliance_overlap,
        "cost_efficiency_score": 0.5,  # updated after pricing fetch
        "query_category_encoded": category_encoded,
    }


# ---------------------------------------------------------------------------
# Stage 6 — LLM Explanation (one per provider)
# ---------------------------------------------------------------------------

def stage6_explain(
    english_query: str,
    top_results: List[ProviderResult],
    lang: str = "English",
) -> List[str]:
    """Returns a list of explanations, one per result in top_results.

    Each provider's dict bundles the full SLA profile that drove its rank —
    uptime, RTO, RPO, support response, penalty credit, region count,
    compliance count, plus the service name when in service-category mode.
    The LLM uses this to produce comparative, metric-specific reasoning
    instead of generic "ranked because of strong SLA" filler.
    """
    from app.services.llm_router import llm_router

    def _profile(r: ProviderResult) -> dict:
        # Compact comparable profile. Keep keys short so the LLM has more
        # tokens to spend on the actual reasoning rather than parsing.
        return {
            "rank":             r.rank_position,
            "name":             r.provider_name,
            "service":          r.service_name,                                  # None in legacy mode
            "final_score":      round(r.final_score, 1),
            "topsis":           round(r.topsis_score, 3),
            "semantic":         round(r.cosine_score, 3),
            # Prefer service-level values when available, fall back to
            # provider-level so the prompt always sees real numbers.
            "uptime_pct":       r.service_uptime_pct if r.service_uptime_pct is not None else r.sla_uptime_pct,
            "rto_hours":        r.service_rto_hours  if r.service_rto_hours  is not None else r.sla_rto_hours,
            "rpo_hours":        r.service_rpo_hours,
            "compliance_count": len(r.compliance_tags or []),
            "meets_uptime":     r.meets_uptime,
            "meets_rto":        r.meets_rto,
        }

    all_provider_data = [_profile(r) for r in top_results]
    winner = all_provider_data[0] if all_provider_data else None

    explanations: List[str] = []
    for r in top_results:
        try:
            this_provider = _profile(r)
            # Gap-to-winner gives the LLM something concrete to anchor the
            # explanation against — "ranked #3 with final 46.4, which is 6.9
            # points behind Azure (53.2)" reads sharper than "ranked third".
            gap = round((winner["final_score"] - this_provider["final_score"]), 1) if winner else 0.0
            this_provider["gap_vs_winner"] = gap
            this_provider["winner_name"]   = winner["name"]    if winner else None
            this_provider["winner_service"] = winner.get("service") if winner else None

            explanation = llm_router.generate_explanation(
                english_query, this_provider, all_provider_data, lang
            )
            explanations.append(explanation)
        except Exception as e:
            logger.warning("LLM explanation failed for %s: %s", r.provider_name, e)
            explanations.append("")
    return explanations


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    raw_query: str,
    providers_with_metrics: list,          # list of (provider_id, provider_name, metrics_obj | None)
    weights: dict | None = None,
    lang: str = "English",                 # user-chosen response language
    service_category: str | None = None,   # if set, rank per-service in this category
) -> PipelineResult:
    """
    Run all 6 stages and return a PipelineResult.

    providers_with_metrics: list of tuples
        (provider_id: str, provider_name: str, metrics: SLAMetrics | None)

    service_category: when supplied, each provider is **expanded** into one
        entry per service it offers in this category (see service_catalog.py).
        Rankings then operate at the (provider, service) level — e.g. for
        category="database" you get rows for DynamoDB Global, Cosmos DB,
        Cloud Spanner, etc., each scored on its own published SLA. Set to
        None for the legacy monolithic-per-provider behaviour.
    """
    from app.services.translation import to_english
    from app.services.service_catalog import services_for

    # Translate frontend weight keys to TOPSIS criteria keys
    topsis_weights = _map_weights(weights) if weights else None

    # Translate to English
    english_query, detected_lang = to_english(raw_query)

    # Stage 1
    req = stage1_understand_query(english_query)

    # ─── Service-category expansion ──────────────────────────────────────
    # When a category is requested, fan each provider out into N entries —
    # one per service the provider offers in that category. Each entry uses
    # the service's specific SLA values via a SimpleNamespace shim shaped
    # like the existing SLAMetrics objects. This keeps the rest of the
    # pipeline (TOPSIS / XGB / explanation) completely unchanged.
    service_meta: dict[str, dict] = {}    # synthetic_id -> {name, uptime, rto, rpo, url, category}
    if service_category:
        from types import SimpleNamespace
        expanded: list = []
        for provider_id, provider_name, metrics in providers_with_metrics:
            for svc in services_for(service_category, provider_name):
                # Synthetic ID stays a valid UUID string so persistence /
                # downstream UUID conversion still works. We add a stable
                # suffix derived from the service name so each (provider,
                # service) row has its own identity.
                synth_id = f"{provider_id}::{svc['name']}"
                # Carry over regions + compliance from the provider-level
                # metrics so the geographic-coverage and compliance-overlap
                # criteria still contribute meaningfully.
                regions    = list(getattr(metrics, "regions", []) or []) if metrics else []
                compliance = list(getattr(metrics, "compliance", []) or []) if metrics else []
                svc_metrics = SimpleNamespace(
                    uptime_sla_pct       = svc.get("uptime_sla_pct"),
                    rto_hours            = svc.get("rto_hours"),
                    rpo_hours            = svc.get("rpo_hours"),
                    support_response_min = svc.get("support_response_min"),
                    penalty_credit_pct   = svc.get("penalty_credit_pct"),
                    regions              = regions,
                    compliance           = compliance,
                )
                # Composite name shown in TOPSIS output and the rank card
                composite_name = f"{provider_name} — {svc['name']}"
                expanded.append((synth_id, composite_name, svc_metrics))
                service_meta[synth_id] = {
                    "real_provider_id":   provider_id,
                    "real_provider_name": provider_name,
                    "service_name":       svc["name"],
                    "service_uptime_pct": svc.get("uptime_sla_pct"),
                    "service_rto_hours":  svc.get("rto_hours"),
                    "service_rpo_hours":  svc.get("rpo_hours"),
                    "sla_url":            svc.get("sla_url"),
                    "service_category":   service_category,
                }
        # Only switch to expanded view if the catalog had entries for the
        # requested category. Empty catalog → fall back to monolithic.
        if expanded:
            providers_with_metrics = expanded

    # Stage 2 — semantic retrieval keyed by *real* provider name. In
    # monolithic mode the composite name == real name. In service-category
    # mode (e.g. "AWS — Amazon S3 Standard"), we look up cosine_scores by
    # the underlying provider name; the helper below resolves either case.
    def _real_name(synth_or_real_id: str, composite: str) -> str:
        if synth_or_real_id in service_meta:
            return service_meta[synth_or_real_id]["real_provider_name"]
        return composite

    cosine_query_names = [
        _real_name(p[0], p[1]) for p in providers_with_metrics
    ]
    cosine_scores = stage2_retrieve_chunks(english_query, list(set(cosine_query_names)))

    # Stage 3 — filter to providers that have metrics
    topsis_inputs = []
    metrics_map: dict[str, object] = {}
    for provider_id, provider_name, metrics in providers_with_metrics:
        if metrics:
            metrics_map[provider_id] = metrics
            topsis_inputs.append(_build_topsis_input(provider_id, provider_name, metrics))

    if not topsis_inputs:
        return PipelineResult(
            requirements=req,
            provider_results=[],
            detected_lang=detected_lang,
            english_query=english_query,
        )

    # Stage 4 — TOPSIS
    topsis_results = topsis_rank(topsis_inputs, weights=topsis_weights or DEFAULT_WEIGHTS)

    # Stage 5 — XGBoost re-ranking. Cosine score lookup must resolve
    # composite (provider, service) names back to the real provider name
    # whose chunks were embedded in ChromaDB.
    def _cosine_for(tr) -> float:
        real = _real_name(tr.provider_id, tr.provider_name)
        return cosine_scores.get(real, 0.0)

    xgb_records = [
        _build_xgb_record(tr, {tr.provider_name: _cosine_for(tr)}, req, metrics_map.get(tr.provider_id))
        for tr in topsis_results
    ]
    xgb_scores, xgb_cold_start = predict(xgb_records)

    # Compute final scores and sort
    scored = []
    for tr, xgb_s in zip(topsis_results, xgb_scores):
        cosine_s = _cosine_for(tr)
        final = (0.50 * tr.topsis_score) + (0.20 * cosine_s) + (0.30 * xgb_s)
        scored.append((tr, xgb_s, cosine_s, final))

    scored.sort(key=lambda x: -x[3])

    # Build intermediate results (no explanation yet)
    results: List[ProviderResult] = []
    for rank_pos, (tr, xgb_s, cosine_s, final) in enumerate(scored, start=1):
        m = metrics_map.get(tr.provider_id)
        provider_regions = [r.lower() for r in (m.regions or [])] if m else []
        # Service-mode bookkeeping: pull the curated service metadata, and
        # collapse the synthetic "<uuid>::service" id back to the real
        # provider UUID so downstream code (Ranking inserts, UUID parsing
        # in query.py) keeps working unchanged.
        svc_meta = service_meta.get(tr.provider_id)
        if svc_meta:
            real_provider_id   = svc_meta["real_provider_id"]
            real_provider_name = svc_meta["real_provider_name"]
            service_url        = svc_meta.get("sla_url")
        else:
            real_provider_id   = tr.provider_id
            real_provider_name = tr.provider_name
            service_url        = None

        results.append(ProviderResult(
            provider_id=real_provider_id,
            provider_name=real_provider_name,
            rank_position=rank_pos,
            final_score=round(final * 100, 1),
            topsis_score=tr.topsis_score,
            xgb_score=xgb_s,
            cosine_score=cosine_s,
            xgb_cold_start=xgb_cold_start,
            cost_usd=None,
            value_score=None,
            explanation=None,
            meets_uptime=bool((m.uptime_sla_pct or 0) >= (req.uptime_required_pct or 0)) if m and req.uptime_required_pct else None,
            meets_rto=bool((m.rto_hours or 99) <= (req.rto_hours or 99)) if m and req.rto_hours else None,
            meets_region=bool(any((req.region or "").lower() in r for r in provider_regions)) if (req.region and m) else None,
            compliance_tags=list(m.compliance or []) if m else [],
            sla_uptime_pct=m.uptime_sla_pct if m else None,
            sla_rto_hours=m.rto_hours if m else None,
            sla_url=service_url,
            # Service-level fields populated only when in service mode
            service_name=svc_meta["service_name"]       if svc_meta else None,
            service_uptime_pct=svc_meta["service_uptime_pct"] if svc_meta else None,
            service_rto_hours=svc_meta["service_rto_hours"]   if svc_meta else None,
            service_rpo_hours=svc_meta["service_rpo_hours"]   if svc_meta else None,
            service_category=svc_meta["service_category"]     if svc_meta else None,
        ))

    # Stage 6 — explain ONE row per provider, picking the best-ranked row for
    # each. In legacy mode this is identical to "top 3 results" because each
    # provider appears exactly once. In service mode (e.g. 13 storage rows
    # spread across 5 providers), this guarantees every provider gets an
    # explanation on its strongest service — so AWS / Oracle / IBM rows
    # aren't left blank just because Azure happens to occupy ranks 1-3.
    # We also keep an absolute ceiling of 6 explanations to bound LLM cost.
    explained: dict[str, "ProviderResult"] = {}
    for r in results:
        if r.provider_name not in explained:
            explained[r.provider_name] = r
        if len(explained) >= 6:
            break
    to_explain = list(explained.values())
    explanations = stage6_explain(english_query, to_explain, lang)
    for r, expl in zip(to_explain, explanations):
        if expl:
            r.explanation = expl

    return PipelineResult(
        requirements=req,
        provider_results=results,
        detected_lang=detected_lang,
        english_query=english_query,
    )
