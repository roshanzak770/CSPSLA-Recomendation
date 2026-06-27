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

# The frontend Recommend tab sends short signal names ('up' / 'down') from the
# thumbs buttons, but SIGNAL_WEIGHTS uses the canonical training-friendly
# names ('thumbs_up' / 'thumbs_down'). Without this alias map, every thumbs
# click was stored with weight=0 AND counted under the wrong key in the
# Model Training tab's signal breakdown — making it look like no feedback
# was being collected.
_SIGNAL_ALIASES = {
    "up":             "thumbs_up",
    "down":           "thumbs_down",
    "thumb_up":       "thumbs_up",
    "thumb_down":     "thumbs_down",
    "click":          "clicked_provider",
    "accept":         "accepted_recommendation",
    "ignore":         "ignored_top_result",
}


def _canonical_signal(raw: str) -> str:
    """Map any frontend short-form signal onto the canonical name used by
    SIGNAL_WEIGHTS and the feedback-stats group-by. Unknown values pass
    through unchanged so future signal types don't silently disappear."""
    if not raw:
        return raw
    return _SIGNAL_ALIASES.get(raw.strip().lower(), raw.strip())


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    signal = _canonical_signal(req.signal)
    weight = SIGNAL_WEIGHTS.get(signal, 0.0)
    feedback = Feedback(
        query_id=req.query_id,
        provider_id=req.provider_id,
        signal_type=signal,
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
