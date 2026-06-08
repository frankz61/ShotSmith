from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "shotsmith",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.jobs"],   # 让 worker 注册 run_pipeline 任务
)
celery_app.conf.task_track_started = True
