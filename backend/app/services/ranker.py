"""
XGBoost LambdaMART re-ranker.
Wraps training and inference, with cold-start bootstrap from TOPSIS scores.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import List

import numpy as np

MODEL_PATH = Path("./models/xgb_ranker.pkl")

# Signal type → weight mapping
SIGNAL_WEIGHTS = {
    "clicked_provider": 0.3,
    "accepted_recommendation": 1.0,
    "thumbs_up": 1.5,
    "thumbs_down": -1.5,
    "ignored_top_result": -0.5,
}


def _feature_vector(record: dict) -> List[float]:
    """Build feature vector for a (query, provider) pair."""
    return [
        record.get("cosine_similarity_score", 0.0),
        record.get("topsis_score", 0.0),
        record.get("uptime_delta", 0.0),
        float(record.get("rto_meets_requirement", 0)),
        float(record.get("region_match", 0)),
        record.get("compliance_overlap_pct", 0.0),
        record.get("cost_efficiency_score", 0.5),
        record.get("query_category_encoded", 0),
    ]


def predict(records: List[dict]) -> List[float]:
    """
    Re-rank using XGBoost if a trained model exists.
    Falls back to TOPSIS score if no model is available yet (cold start).
    """
    if not MODEL_PATH.exists():
        # Cold start: return TOPSIS scores directly
        return [r.get("topsis_score", 0.0) for r in records]

    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    X = np.array([_feature_vector(r) for r in records])
    return model.predict(X).tolist()


def retrain(training_data: List[dict]) -> bool:
    """
    Retrain XGBoost LambdaMART from accumulated feedback.
    training_data: list of feature dicts with 'relevance_score' key.
    Returns True on success.
    """
    try:
        import xgboost as xgb
    except ImportError:
        return False

    if len(training_data) < 10:
        return False

    X = np.array([_feature_vector(r) for r in training_data])
    y = np.array([r.get("relevance_score", 0.0) for r in training_data])
    groups = np.array([r.get("group_size", len(training_data))])

    model = xgb.XGBRanker(
        objective="rank:ndcg",
        learning_rate=0.1,
        n_estimators=100,
        max_depth=6,
        verbosity=0,
    )
    model.fit(X, y, group=groups)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    return True
