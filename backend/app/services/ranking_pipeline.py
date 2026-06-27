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
    """Returns a list of explanations, one per result in top_results."""
    from app.services.llm_router import llm_router
    explanations = []
    all_provider_data = [
        {
            "rank": r.rank_position,
            "name": r.provider_name,
            "final_score": round(r.final_score, 1),
            "topsis_score": round(r.topsis_score, 3),
            "semantic_score": round(r.cosine_score, 3),
            "uptime": r.sla_uptime_pct,
            "rto_hours": r.sla_rto_hours,
            "compliance": r.compliance_tags,
            "meets_uptime": r.meets_uptime,
            "meets_rto": r.meets_rto,
        }
        for r in top_results
    ]
    for r in top_results:
        try:
            this_provider = {
                "rank": r.rank_position,
                "name": r.provider_name,
                "final_score": round(r.final_score, 1),
                "topsis_score": round(r.topsis_score, 3),
                "semantic_score": round(r.cosine_score, 3),
                "uptime": r.sla_uptime_pct,
                "rto_hours": r.sla_rto_hours,
                "compliance": r.compliance_tags,
                "meets_uptime": r.meets_uptime,
                "meets_rto": r.meets_rto,
            }
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
) -> PipelineResult:
    """
    Run all 6 stages and return a PipelineResult.

    providers_with_metrics: list of tuples
        (provider_id: str, provider_name: str, metrics: SLAMetrics | None)
    """
    from app.services.translation import to_english

    # Translate frontend weight keys to TOPSIS criteria keys
    topsis_weights = _map_weights(weights) if weights else None

    # Translate to English
    english_query, detected_lang = to_english(raw_query)

    # Stage 1
    req = stage1_understand_query(english_query)

    # Stage 2
    provider_names = [p[1] for p in providers_with_metrics]
    cosine_scores = stage2_retrieve_chunks(english_query, provider_names)

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

    # Stage 5 — XGBoost re-ranking
    xgb_records = [
        _build_xgb_record(tr, cosine_scores, req, metrics_map.get(tr.provider_id))
        for tr in topsis_results
    ]
    xgb_scores, xgb_cold_start = predict(xgb_records)

    # Compute final scores and sort
    scored = []
    for tr, xgb_s in zip(topsis_results, xgb_scores):
        cosine_s = cosine_scores.get(tr.provider_name, 0.0)
        final = (0.50 * tr.topsis_score) + (0.20 * cosine_s) + (0.30 * xgb_s)
        scored.append((tr, xgb_s, cosine_s, final))

    scored.sort(key=lambda x: -x[3])

    # Build intermediate results (no explanation yet)
    results: List[ProviderResult] = []
    for rank_pos, (tr, xgb_s, cosine_s, final) in enumerate(scored, start=1):
        m = metrics_map.get(tr.provider_id)
        provider_regions = [r.lower() for r in (m.regions or [])] if m else []

        results.append(ProviderResult(
            provider_id=tr.provider_id,
            provider_name=tr.provider_name,
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
        ))

    # Stage 6 — individual explanation per provider
    explanations = stage6_explain(english_query, results[:3], lang)
    for r, expl in zip(results[:3], explanations):
        if expl:
            r.explanation = expl

    return PipelineResult(
        requirements=req,
        provider_results=results,
        detected_lang=detected_lang,
        english_query=english_query,
    )
