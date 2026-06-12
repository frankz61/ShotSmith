import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AssetOut,
    LoginIn,
    PresignIn,
    PresignOut,
    SelectIn,
    TaskOut,
    TaskSummary,
    TokenOut,
)
from app.core.config import settings
from app.core.security import check_password, make_token, require_auth
from app.models.db import get_db
from app.models.task import Asset, Task
from app.services import packaging
from app.storage import oss, urls
from app.storage.local import LocalStorage
from app.tasks.jobs import run_pipeline

logger = logging.getLogger(__name__)

# 登录路由不鉴权；其余业务路由统一挂 require_auth 依赖
auth_router = APIRouter(prefix="/api/v1", tags=["auth"])
router = APIRouter(prefix="/api/v1", tags=["tasks"], dependencies=[Depends(require_auth)])
storage = LocalStorage()


@auth_router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn) -> TokenOut:
    if not check_password(body.password):
        raise HTTPException(401, "密码错误")
    token, ttl = make_token()
    return TokenOut(token=token, expires_in=ttl)


def _source_image(task: Task) -> str | None:
    """原图展示地址：oss 直传任务用预签名缩略图；其余本地 00_source.* 优先，URL 回退外链。"""
    if task.source_type == "oss" and task.source_ref:
        return oss.sign_get(task.source_ref, thumb=True)
    src = storage.find_source(str(task.id))
    if src:
        return f"/files/{storage.rel(src)}"
    if task.source_type == "url" and task.source_ref:
        return task.source_ref
    return None


def _with_urls(asset: Asset) -> Asset:
    """补充可展示地址：预签名 URL 有时效，DB 只存 key，每次返回时实时签名。"""
    asset.url = urls.file_url(asset.path)
    asset.thumb_url = urls.file_url(asset.path, thumb=True)
    return asset


@router.post("/uploads/presign", response_model=PresignOut)
def presign_upload(body: PresignIn) -> PresignOut:
    """服务端签名直传：签发 OSS 预签名 PUT 地址，前端直传后凭 key 创建任务。"""
    if not oss.enabled():
        raise HTTPException(409, "未启用 OSS，请用 multipart 上传")
    if not body.content_type.startswith("image/"):
        raise HTTPException(400, "仅支持图片直传")
    ext = Path(body.filename).suffix.lower() or ".png"
    key = f"uploads/{datetime.now():%Y%m}/{uuid.uuid4().hex}{ext}"
    return PresignOut(
        key=key,
        url=oss.sign_put(key, body.content_type),
        headers={"Content-Type": body.content_type},
        expires_in=settings.oss_url_ttl,
    )


@router.post("/tasks", response_model=TaskOut, status_code=202)
async def create_task(
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    source_key: str | None = Form(default=None),  # OSS 直传后的 object key
    description: str | None = Form(default=None),
    options: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Task:
    if not file and not url and not source_key:
        raise HTTPException(400, "需要上传图片或提供图片 URL")
    if source_key:
        if not oss.enabled():
            raise HTTPException(400, "未启用 OSS，不支持 source_key")
        if not source_key.startswith("uploads/"):
            raise HTTPException(400, "source_key 不合法")
    opts: dict = {}
    if options:
        try:
            opts = json.loads(options)
        except json.JSONDecodeError as e:
            raise HTTPException(400, "options 不是合法 JSON") from e

    if file:
        source_type, source_ref = "upload", file.filename or ""
    elif source_key:
        source_type, source_ref = "oss", source_key
    else:
        source_type, source_ref = "url", url or ""
    task = Task(
        source_type=source_type,
        source_ref=source_ref,
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
    tasks = db.execute(stmt).scalars().all()
    for t in tasks:
        t.source_image = _source_image(t)
    return tasks


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    task.source_image = _source_image(task)
    for a in task.assets:
        _with_urls(a)
    return task


@router.get("/tasks/{task_id}/assets", response_model=list[AssetOut])
def list_assets(task_id: uuid.UUID, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return [_with_urls(a) for a in task.assets]


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


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    source_key = task.source_ref if task.source_type == "oss" else None
    db.delete(task)            # assets 经 delete-orphan 级联删除
    db.commit()
    storage.remove_task_dir(str(task_id))   # 同步清理磁盘文件
    if oss.enabled():          # 清理 OSS 上的产物与直传原图；失败不影响删除结果
        try:
            oss.delete_prefix(f"tasks/{task_id}/")
            if source_key:
                oss.delete_key(source_key)
        except Exception:
            logger.exception("清理 OSS 文件失败 task=%s", task_id)


@router.post("/assets/{asset_id}/select", response_model=AssetOut)
def select_asset(asset_id: uuid.UUID, body: SelectIn, db: Session = Depends(get_db)) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在")
    asset.selected = body.selected
    db.commit()
    db.refresh(asset)
    return _with_urls(asset)


@router.get("/tasks/{task_id}/package")
def download_package(task_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status not in ("success", "partial"):
        raise HTTPException(409, "任务尚未完成")
    if oss.enabled():   # API 与 worker 不共享磁盘时，先把本地缺失的产物从 OSS 拉回
        oss.restore_task_dir(f"tasks/{task.id}/", storage.base)
    zip_path = packaging.make_zip(str(storage.task_dir(str(task.id))))
    return FileResponse(zip_path, filename=f"shotsmith_{task.id}.zip", media_type="application/zip")
