"""
POST /api/feedback — collect user signals
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import FeedbackRequest, FeedbackResponse
from app.db.session import get_db
from app.models.models import Feedback
from app.services.ranker import SIGNAL_WEIGHTS

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    weight = SIGNAL_WEIGHTS.get(req.signal, 0.0)
    feedback = Feedback(
        query_id=req.query_id,
        provider_id=req.provider_id,
        signal_type=req.signal,
        weight=weight,
    )
    db.add(feedback)
    await db.commit()

    # Check if retraining should be triggered (every 100 feedback entries)
    from sqlalchemy import func, select
    count_result = await db.execute(select(func.count(Feedback.id)))
    total = count_result.scalar_one()
    if total % 100 == 0:
        from app.tasks.ml_tasks import retrain_xgboost
        retrain_xgboost.delay()

    return FeedbackResponse(success=True)
