"""
GET  /api/alerts                    — all SLA change alerts
GET  /api/alerts/user               — alias
POST /api/alerts/subscribe          — placeholder
GET  /api/alerts/thresholds         — list all threshold rules
POST /api/alerts/thresholds         — create a threshold rule
DELETE /api/alerts/thresholds/{id}  — delete a threshold rule
PATCH /api/alerts/thresholds/{id}   — toggle active/inactive
POST /api/alerts/thresholds/check   — manually trigger threshold check now
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.models import SLAAlert, Provider, SLAMetrics, AlertThreshold
from app.core.schemas import AlertSchema, AlertThresholdCreate, AlertThresholdSchema

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_METRICS   = {"uptime_sla_pct", "rto_hours", "rpo_hours", "penalty_credit_pct"}
VALID_OPERATORS = {"below", "above"}


# ---------------------------------------------------------------------------
# SLA change alerts
# ---------------------------------------------------------------------------

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
        alerts.append(AlertSchema(
            id=alert.id,
            provider_id=alert.provider_id,
            provider_name=provider_name,
            change_type=alert.change_type,
            old_value=alert.old_value,
            new_value=alert.new_value,
            affected_clause=alert.affected_clause,
            severity=alert.severity,
            detected_at=alert.detected_at,
        ))
    return alerts


@router.get("/alerts/user")
async def get_user_alerts(db: AsyncSession = Depends(get_db)):
    return await get_all_alerts(db=db)


@router.post("/alerts/subscribe")
async def subscribe_alerts(payload: dict, db: AsyncSession = Depends(get_db)):
    return {"subscribed": True, "provider_ids": payload.get("provider_ids", [])}


# ---------------------------------------------------------------------------
# Threshold rules
# ---------------------------------------------------------------------------

@router.get("/alerts/thresholds", response_model=list[AlertThresholdSchema])
async def list_thresholds(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AlertThreshold, Provider.name)
        .outerjoin(Provider, AlertThreshold.provider_id == Provider.id)
        .order_by(AlertThreshold.created_at.desc())
    )
    out = []
    for t, pname in result.all():
        out.append(AlertThresholdSchema(
            id=t.id, email=t.email, provider_id=t.provider_id,
            provider_name=pname, metric=t.metric, operator=t.operator,
            threshold_value=t.threshold_value, active=t.active,
            created_at=t.created_at, last_triggered_at=t.last_triggered_at,
        ))
    return out


@router.post("/alerts/thresholds", response_model=AlertThresholdSchema)
async def create_threshold(req: AlertThresholdCreate, db: AsyncSession = Depends(get_db)):
    if req.metric not in VALID_METRICS:
        raise HTTPException(status_code=400, detail=f"metric must be one of {sorted(VALID_METRICS)}")
    if req.operator not in VALID_OPERATORS:
        raise HTTPException(status_code=400, detail="operator must be 'below' or 'above'")

    provider_name = None
    if req.provider_id:
        prov = await db.get(Provider, req.provider_id)
        if not prov:
            raise HTTPException(status_code=404, detail="Provider not found")
        provider_name = prov.name

    t = AlertThreshold(
        email=req.email, provider_id=req.provider_id,
        metric=req.metric, operator=req.operator,
        threshold_value=req.threshold_value,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)

    return AlertThresholdSchema(
        id=t.id, email=t.email, provider_id=t.provider_id,
        provider_name=provider_name, metric=t.metric, operator=t.operator,
        threshold_value=t.threshold_value, active=t.active,
        created_at=t.created_at, last_triggered_at=t.last_triggered_at,
    )


@router.delete("/alerts/thresholds/{threshold_id}")
async def delete_threshold(threshold_id: UUID, db: AsyncSession = Depends(get_db)):
    t = await db.get(AlertThreshold, threshold_id)
    if not t:
        raise HTTPException(status_code=404, detail="Threshold not found")
    await db.delete(t)
    await db.commit()
    return {"deleted": True}


@router.patch("/alerts/thresholds/{threshold_id}")
async def toggle_threshold(threshold_id: UUID, db: AsyncSession = Depends(get_db)):
    t = await db.get(AlertThreshold, threshold_id)
    if not t:
        raise HTTPException(status_code=404, detail="Threshold not found")
    t.active = not t.active
    await db.commit()
    return {"id": str(threshold_id), "active": t.active}


@router.post("/alerts/thresholds/check")
async def check_thresholds_now(db: AsyncSession = Depends(get_db)):
    """Manually trigger threshold check against latest SLA metrics."""
    from app.services.email_service import send_threshold_alert
    from datetime import datetime, timezone

    thresholds_result = await db.execute(
        select(AlertThreshold).where(AlertThreshold.active == True)
    )
    thresholds = thresholds_result.scalars().all()
    logger.info("Threshold check invoked — %d active threshold(s)", len(thresholds))

    triggered = 0
    for t in thresholds:
        q = (
            select(SLAMetrics, Provider.name)
            .join(Provider, SLAMetrics.provider_id == Provider.id)
            .order_by(SLAMetrics.extracted_at.desc())
        )
        if t.provider_id:
            q = q.where(SLAMetrics.provider_id == t.provider_id)

        rows = (await db.execute(q)).all()

        # Walk the rows for THIS provider (or all providers if unscoped),
        # keeping the freshest non-null value of the target metric per
        # provider. Previously the code did DISTINCT-ON-latest-row and
        # skipped the whole check when the latest row happened to have
        # metric=None — which is exactly what was silently swallowing
        # every Azure alert because the last-ingested Azure row had
        # uptime_sla_pct=NULL. Scanning per-provider fixes that.
        freshest_by_provider: dict = {}   # provider_id -> (actual, pname)
        for metrics, pname in rows:
            if metrics.provider_id in freshest_by_provider:
                continue
            actual = getattr(metrics, t.metric, None)
            if actual is None:
                # Keep walking older rows for this provider — don't lock in
                # a None just because the freshest row has it. Only record
                # this provider once we find a real value or exhaust rows.
                continue
            freshest_by_provider[metrics.provider_id] = (actual, pname)

        for actual, pname in freshest_by_provider.values():
            breached = (
                (t.operator == "below" and actual < t.threshold_value) or
                (t.operator == "above" and actual > t.threshold_value)
            )
            if breached:
                logger.info(
                    "Threshold BREACH: %s %s %s (actual=%s) — emailing %s",
                    pname, t.metric, t.operator, actual, t.email,
                )
                sent = send_threshold_alert(
                    to_email=t.email, provider_name=pname,
                    metric=t.metric, operator=t.operator,
                    threshold_value=t.threshold_value, actual_value=actual,
                )
                if sent:
                    # Column is TIMESTAMP WITHOUT TIME ZONE — asyncpg raises
                    # DataError if we pass an aware datetime. Build a
                    # tz-aware UTC value (utcnow() is deprecated in 3.12+)
                    # and strip the tzinfo before writing to match the
                    # schema's naive-UTC convention used everywhere else.
                    t.last_triggered_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    triggered += 1
                else:
                    logger.warning(
                        "Threshold breach detected but email FAILED for %s → %s",
                        pname, t.email,
                    )

    await db.commit()
    logger.info("Threshold check done — %d email(s) sent", triggered)
    return {"triggered": triggered, "checked": len(thresholds)}
