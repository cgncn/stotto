from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "stotto",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Istanbul",
    enable_utc=True,
    task_track_started=True,
    worker_redirect_stdouts_level="INFO",
)

celery_app.conf.beat_schedule = {
    # Daily refresh: 4 times per day at 08:00, 12:00, 17:00, 21:00 Istanbul
    "daily-refresh-08": {
        "task": "app.workers.tasks.task_daily_refresh",
        "schedule": crontab(hour=8, minute=0),
    },
    "daily-refresh-12": {
        "task": "app.workers.tasks.task_daily_refresh",
        "schedule": crontab(hour=12, minute=0),
    },
    "daily-refresh-17": {
        "task": "app.workers.tasks.task_daily_refresh",
        "schedule": crontab(hour=17, minute=0),
    },
    "daily-refresh-21": {
        "task": "app.workers.tasks.task_daily_refresh",
        "schedule": crontab(hour=21, minute=0),
    },
    # Pre-kickoff refreshes every 15 minutes (task filters internally)
    "pre-kickoff-check": {
        "task": "app.workers.tasks.task_pre_kickoff_check",
        "schedule": crontab(minute="*/15"),
    },
    # Settlement check every 5 minutes
    "settlement-check": {
        "task": "app.workers.tasks.task_settle_check",
        "schedule": crontab(minute="*/5"),
    },
}
