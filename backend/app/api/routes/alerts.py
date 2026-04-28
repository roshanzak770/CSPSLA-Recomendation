"""
GET  /api/alerts        — all alerts (admin)
GET  /api/alerts/user   — alerts for current user
POST /api/alerts/subscribe
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.models import SLAAlert, Provider
from app.core.schemas import AlertSchema

router = APIRouter()


@router.get("/alerts", response_model=list[AlertSchema])
async def get_all_alerts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SLAAlert, Provider.name)
        .join(Provider, SLAAlert.provider_id == Provider.id)
        .order_by(SLAAlert.detected_at.desc())
    )
    rows = result.all()
    alerts = []
    for alert, provider_name in rows:
        a = AlertSchema(
            id=alert.id,
            provider_id=alert.provider_id,
            provider_name=provider_name,
            change_type=alert.change_type,
            old_value=alert.old_value,
            new_value=alert.new_value,
            affected_clause=alert.affected_clause,
            severity=alert.severity,
            detected_at=alert.detected_at,
        )
        alerts.append(a)
    return alerts


@router.get("/alerts/user")
async def get_user_alerts(db: AsyncSession = Depends(get_db)):
    # Placeholder: return all alerts until auth is added
    return await get_all_alerts(db=db)


@router.post("/alerts/subscribe")
async def subscribe_alerts(payload: dict, db: AsyncSession = Depends(get_db)):
    # Placeholder: will tie to user account when auth is added
    return {"subscribed": True, "provider_ids": payload.get("provider_ids", [])}
