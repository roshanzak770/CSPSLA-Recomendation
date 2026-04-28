"""
Celery ML tasks — XGBoost retraining trigger.
"""

from app.celery_app import celery_app


@celery_app.task(name="tasks.retrain_xgboost")
def retrain_xgboost():
    """Rebuild XGBoost model from accumulated feedback signals."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.models.models import Feedback, Ranking
    from app.services.ranker import retrain, SIGNAL_WEIGHTS

    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        feedbacks = session.query(Feedback).all()
        if not feedbacks:
            return {"status": "no_data"}

        # Build training records keyed by (query_id, provider_id)
        records_map = {}
        for fb in feedbacks:
            key = (str(fb.query_id), str(fb.provider_id))
            records_map.setdefault(key, {"relevance_score": 0.0})
            records_map[key]["relevance_score"] += SIGNAL_WEIGHTS.get(fb.signal_type, 0.0)

        # Enrich with ranking features
        training_data = []
        for (query_id, provider_id), rec in records_map.items():
            ranking = session.query(Ranking).filter_by(
                query_id=query_id, provider_id=provider_id
            ).first()
            if ranking:
                rec.update({
                    "topsis_score": ranking.topsis_score or 0.0,
                    "cosine_similarity_score": 0.0,
                    "uptime_delta": 0.0,
                    "rto_meets_requirement": 0,
                    "region_match": 0,
                    "compliance_overlap_pct": 0.0,
                    "cost_efficiency_score": 0.5,
                    "query_category_encoded": 0,
                    "group_size": len(records_map),
                })
                training_data.append(rec)

        success = retrain(training_data)
        return {"status": "retrained" if success else "failed", "records": len(training_data)}
