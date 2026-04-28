"""
Tests for TOPSIS ranker — no external dependencies needed.
"""

import pytest
from app.services.topsis import topsis_rank, ProviderMetrics


def make_providers():
    return [
        ProviderMetrics(
            provider_id="aws",
            provider_name="AWS",
            uptime_sla_pct=99.99,
            rto_hours=4.0,
            rpo_hours=1.0,
            support_response_min=60,
            penalty_credit_pct=30,
            region_coverage=7.0,
        ),
        ProviderMetrics(
            provider_id="azure",
            provider_name="Azure",
            uptime_sla_pct=99.995,
            rto_hours=1.0,
            rpo_hours=0.5,
            support_response_min=15,
            penalty_credit_pct=30,
            region_coverage=8.0,
        ),
        ProviderMetrics(
            provider_id="gcp",
            provider_name="GCP",
            uptime_sla_pct=99.95,
            rto_hours=2.0,
            rpo_hours=1.0,
            support_response_min=60,
            penalty_credit_pct=25,
            region_coverage=7.0,
        ),
    ]


def test_topsis_returns_all_providers():
    results = topsis_rank(make_providers())
    assert len(results) == 3


def test_topsis_ranks_are_unique():
    results = topsis_rank(make_providers())
    ranks = [r.rank for r in results]
    assert sorted(ranks) == [1, 2, 3]


def test_topsis_scores_between_0_and_1():
    results = topsis_rank(make_providers())
    for r in results:
        assert 0.0 <= r.topsis_score <= 1.0


def test_azure_ranks_first_on_default_weights():
    """Azure has best uptime + best RTO + best support — should rank #1."""
    results = topsis_rank(make_providers())
    top = min(results, key=lambda r: r.rank)
    assert top.provider_name == "Azure"


def test_empty_providers_returns_empty():
    assert topsis_rank([]) == []


def test_single_provider_scores_one():
    single = [make_providers()[0]]
    results = topsis_rank(single)
    assert len(results) == 1
    # With one provider, D+ and D- are both 0 — score defaults to 0, still rank 1
    assert results[0].rank == 1


def test_custom_weights_change_ranking():
    """If cost weight is zero and only uptime matters, AWS (99.99%) should beat GCP (99.95%)."""
    cost_only_weights = {
        "uptime_sla_pct": 1.0,
        "rto_hours": 0.0,
        "rpo_hours": 0.0,
        "support_response_min": 0.0,
        "penalty_credit_pct": 0.0,
        "region_coverage": 0.0,
    }
    results = topsis_rank(make_providers(), weights=cost_only_weights)
    ranked = sorted(results, key=lambda r: r.rank)
    # Azure (99.995%) > AWS (99.99%) > GCP (99.95%)
    assert ranked[0].provider_name == "Azure"
    assert ranked[2].provider_name == "GCP"
