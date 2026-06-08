from app.pipeline import orchestrator
from app.tasks.celery_app import celery_app


@celery_app.task(name="run_pipeline", bind=True, max_retries=2)
def run_pipeline(self, task_id: str) -> None:  # noqa: ANN001
    orchestrator.run(task_id)
