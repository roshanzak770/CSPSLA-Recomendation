"""
TOPSIS multi-criteria ranking.
Ranks cloud providers based on extracted SLA metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np


# Default criteria weights (user-adjustable via API)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "uptime_sla_pct": 0.30,
    "rto_hours": 0.20,
    "rpo_hours": 0.15,
    "support_response_min": 0.15,
    "penalty_credit_pct": 0.10,
    "region_coverage": 0.10,
}

# "benefit" = higher is better, "cost" = lower is better
CRITERION_TYPE: Dict[str, str] = {
    "uptime_sla_pct": "benefit",
    "rto_hours": "cost",
    "rpo_hours": "cost",
    "support_response_min": "cost",
    "penalty_credit_pct": "benefit",
    "region_coverage": "benefit",
}


@dataclass
class ProviderMetrics:
    provider_id: str
    provider_name: str
    uptime_sla_pct: float = 99.9
    rto_hours: float = 24.0
    rpo_hours: float = 24.0
    support_response_min: float = 60.0
    penalty_credit_pct: float = 10.0
    region_coverage: float = 1.0  # number of matching regions


@dataclass
class TOPSISResult:
    provider_id: str
    provider_name: str
    topsis_score: float
    rank: int


def topsis_rank(
    providers: List[ProviderMetrics],
    weights: Dict[str, float] | None = None,
) -> List[TOPSISResult]:
    """
    Run TOPSIS on a list of providers.
    Returns results sorted by rank (best first).
    """
    if not providers:
        return []

    w = weights or DEFAULT_WEIGHTS
    criteria = list(DEFAULT_WEIGHTS.keys())

    # Build decision matrix [n_providers × n_criteria]
    matrix = np.array([
        [getattr(p, c) for c in criteria]
        for p in providers
    ], dtype=float)

    # Avoid division by zero
    norms = np.sqrt((matrix ** 2).sum(axis=0))
    norms = np.where(norms == 0, 1e-10, norms)

    # Step 1: Weighted normalised matrix
    weight_vec = np.array([w.get(c, 0.0) for c in criteria])
    v = (matrix / norms) * weight_vec

    # Step 2: Ideal best (A+) and worst (A-)
    a_plus = np.where(
        [CRITERION_TYPE[c] == "benefit" for c in criteria],
        v.max(axis=0),
        v.min(axis=0),
    )
    a_minus = np.where(
        [CRITERION_TYPE[c] == "benefit" for c in criteria],
        v.min(axis=0),
        v.max(axis=0),
    )

    # Step 3: Euclidean distances
    d_plus = np.sqrt(((v - a_plus) ** 2).sum(axis=1))
    d_minus = np.sqrt(((v - a_minus) ** 2).sum(axis=1))

    # Step 4: Relative closeness
    denom = d_plus + d_minus
    denom = np.where(denom == 0, 1e-10, denom)
    scores = d_minus / denom

    # Rank highest-score first
    ranked_idx = np.argsort(-scores)
    results = []
    for rank, idx in enumerate(ranked_idx, start=1):
        results.append(TOPSISResult(
            provider_id=providers[idx].provider_id,
            provider_name=providers[idx].provider_name,
            topsis_score=float(scores[idx]),
            rank=rank,
        ))
    return results
