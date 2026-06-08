import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import AssetOut, SelectIn, TaskOut, TaskSummary
from app.models.db import get_db
from app.models.task import Asset, Task
from app.services import packaging
from app.storage.local import LocalStorage
from app.tasks.jobs import run_pipeline

router = APIRouter(prefix="/api/v1", tags=["tasks"])
storage = LocalStorage()


@router.post("/tasks", response_model=TaskOut, status_code=202)
async def create_task(
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    description: str | None = Form(default=None),
    options: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Task:
    if not file and not url:
        raise HTTPException(400, "需要上传图片或提供图片 URL")
    opts: dict = {}
    if options:
        try:
            opts = json.loads(options)
        except json.JSONDecodeError as e:
            raise HTTPException(400, "options 不是合法 JSON") from e

    task = Task(
        source_type="upload" if file else "url",
        source_ref=(file.filename if file else url) or "",
        description=description,
        options=opts,
    )
    db.add(task)
    db.flush()
    if file:
        storage.save_upload(str(task.id), file.filename or "upload.png", await file.read())
    db.commit()
    db.refresh(task)
    run_pipeline.delay(str(task.id))
    return task


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = (
        select(Task)
        .order_by(Task.created_at.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    return db.execute(stmt).scalars().all()


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.get("/tasks/{task_id}/assets", response_model=list[AssetOut])
def list_assets(task_id: uuid.UUID, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.assets


@router.post("/tasks/{task_id}/regenerate", response_model=TaskOut, status_code=202)
def regenerate(task_id: uuid.UUID, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    task.status, task.current_stage, task.progress, task.error_message = "pending", None, 0, None
    db.commit()
    db.refresh(task)
    run_pipeline.delay(str(task.id))
    return task


@router.post("/assets/{asset_id}/select", response_model=AssetOut)
def select_asset(asset_id: uuid.UUID, body: SelectIn, db: Session = Depends(get_db)) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在")
    asset.selected = body.selected
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/tasks/{task_id}/package")
def download_package(task_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status not in ("success", "partial"):
        raise HTTPException(409, "任务尚未完成")
    zip_path = packaging.make_zip(str(storage.task_dir(str(task.id))))
    return FileResponse(zip_path, filename=f"shotsmith_{task.id}.zip", media_type="application/zip")
