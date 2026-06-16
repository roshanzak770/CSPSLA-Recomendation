"""
Celery application instance.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "cloudsla",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.ml_tasks",
        "app.tasks.sla_tasks",
    ],
)

celery_app.conf.beat_schedule = {
    "refresh-pricing-daily": {
        "task": "tasks.refresh_pricing",
        "schedule": crontab(hour=2, minute=0),
    },
    "refresh-sla-weekly": {
        "task": "tasks.refresh_all_sla_documents",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Sunday
    },
    "discover-new-slas-weekly": {
        "task": "tasks.discover_and_ingest_new_slas",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),  # Monday
    },
    "retrain-xgboost-weekly": {
        "task": "tasks.retrain_xgboost",
        "schedule": crontab(hour=4, minute=0, day_of_week=2),  # Tuesday
    },
}

celery_app.conf.timezone = "UTC"
