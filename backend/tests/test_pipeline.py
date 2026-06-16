"""
Tests for the ranking pipeline using mocked LLM and ChromaDB calls.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.ranking_pipeline import (
    run_pipeline,
    stage1_understand_query,
    stage2_retrieve_chunks,
    QueryRequirements,
)


# --- Stage 1 tests ---

def test_stage1_returns_requirements_on_llm_success():
    mock_parsed = {
        "uptime_required_pct": 99.99,
        "rto_hours": 2.0,
        "region": "eu-west",
        "compliance": ["HIPAA", "GDPR"],
        "category": "database",
        "sensitivity": "HIGH",
    }
    with patch("app.services.llm_router.llm_router") as mock_llm:
        mock_llm.understand_query.return_value = mock_parsed
        req = stage1_understand_query("I need 99.99% uptime in Germany with HIPAA")

    assert req.uptime_required_pct == 99.99
    assert req.rto_hours == 2.0
    assert "HIPAA" in req.compliance
    assert req.sensitivity == "HIGH"


def test_stage1_returns_empty_requirements_on_llm_failure():
    with patch("app.services.llm_router.llm_router") as mock_llm:
        mock_llm.understand_query.side_effect = Exception("API error")
        req = stage1_understand_query("some query")

    assert isinstance(req, QueryRequirements)
    assert req.uptime_required_pct is None


# --- Stage 2 tests ---

def test_stage2_returns_best_score_per_provider():
    mock_chunks = [
        {"provider": "AWS", "score": 0.85},
        {"provider": "AWS", "score": 0.91},
        {"provider": "Azure", "score": 0.78},
    ]
    with patch("app.services.ingestion.search_sla", return_value=mock_chunks):
        scores = stage2_retrieve_chunks("test query", ["AWS", "Azure"])

    assert scores["AWS"] == 0.91   # best of two
    assert scores["Azure"] == 0.78


def test_stage2_returns_empty_on_failure():
    with patch("app.services.ingestion.search_sla", side_effect=Exception("chroma down")):
        scores = stage2_retrieve_chunks("test query", ["AWS"])
    assert scores == {}


# --- Full pipeline tests ---

def _make_mock_metrics(name: str):
    m = MagicMock()
    defaults = {
        "AWS":   (99.99,  4.0, 1.0, 60,  30, ["eu-west-1"],           ["GDPR", "HIPAA"]),
        "Azure": (99.995, 1.0, 0.5, 15,  30, ["germanywestcentral"],   ["GDPR", "HIPAA"]),
        "GCP":   (99.95,  2.0, 1.0, 60,  25, ["europe-west3"],         ["GDPR", "HIPAA"]),
    }
    uptime, rto, rpo, support, penalty, regions, compliance = defaults.get(
        name, (99.9, 24.0, 24.0, 60, 10, [], [])
    )
    m.uptime_sla_pct = uptime
    m.rto_hours = rto
    m.rpo_hours = rpo
    m.support_response_min = support
    m.penalty_credit_pct = penalty
    m.regions = regions
    m.compliance = compliance
    return m


def test_pipeline_returns_all_providers():
    providers = [
        ("id-aws",   "AWS",   _make_mock_metrics("AWS")),
        ("id-azure", "Azure", _make_mock_metrics("Azure")),
        ("id-gcp",   "GCP",   _make_mock_metrics("GCP")),
    ]
    with patch("app.services.translation.to_english", return_value=("test query", "en")), \
         patch("app.services.llm_router.llm_router") as mock_llm, \
         patch("app.services.ingestion.search_sla", return_value=[]):

        mock_llm.understand_query.return_value = {}
        mock_llm.generate_explanation.return_value = "Test explanation"

        result = run_pipeline("test query", providers)

    assert len(result.provider_results) == 3


def test_pipeline_ranks_are_unique_and_sequential():
    providers = [
        ("id-aws",   "AWS",   _make_mock_metrics("AWS")),
        ("id-azure", "Azure", _make_mock_metrics("Azure")),
        ("id-gcp",   "GCP",   _make_mock_metrics("GCP")),
    ]
    with patch("app.services.translation.to_english", return_value=("test query", "en")), \
         patch("app.services.llm_router.llm_router") as mock_llm, \
         patch("app.services.ingestion.search_sla", return_value=[]):

        mock_llm.understand_query.return_value = {}
        mock_llm.generate_explanation.return_value = ""

        result = run_pipeline("test query", providers)

    ranks = sorted(r.rank_position for r in result.provider_results)
    assert ranks == [1, 2, 3]


def test_pipeline_empty_when_no_metrics():
    providers = [("id-aws", "AWS", None)]
    with patch("app.services.translation.to_english", return_value=("test query", "en")), \
         patch("app.services.llm_router.llm_router") as mock_llm:
        mock_llm.understand_query.return_value = {}
        result = run_pipeline("test query", providers)

    assert result.provider_results == []


def test_pipeline_final_scores_in_range():
    providers = [
        ("id-aws",   "AWS",   _make_mock_metrics("AWS")),
        ("id-azure", "Azure", _make_mock_metrics("Azure")),
    ]
    with patch("app.services.translation.to_english", return_value=("test query", "en")), \
         patch("app.services.llm_router.llm_router") as mock_llm, \
         patch("app.services.ingestion.search_sla", return_value=[]):

        mock_llm.understand_query.return_value = {}
        mock_llm.generate_explanation.return_value = ""

        result = run_pipeline("test query", providers)

    for r in result.provider_results:
        assert 0 <= r.final_score <= 100
