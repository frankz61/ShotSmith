import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    size_label: str | None
    path: str
    fidelity_score: float | None
    qc_status: str
    selected: bool
    # 可直接展示的地址：oss → 预签名 URL（有时效，每次查询实时生成）；local → /files/…
    url: str | None = None
    thumb_url: str | None = None  # 缩略图（OSS x-oss-process 实时缩放），网格/列表用


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    current_stage: str | None
    progress: int
    description: str | None
    error_message: str | None
    created_at: datetime
    source_image: str | None = None  # 原图可展示地址（本地 /files/… 或外链 URL）
    assets: list[AssetOut] = []


class TaskSummary(BaseModel):
    """历史列表用的轻量摘要（不含素材）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    current_stage: str | None
    progress: int
    description: str | None
    created_at: datetime
    source_image: str | None = None  # 原图可展示地址（本地 /files/… 或外链 URL）


class SelectIn(BaseModel):
    selected: bool


class LoginIn(BaseModel):
    password: str


class PresignIn(BaseModel):
    """服务端签名直传：前端拿预签名 PUT 地址后直接上传 OSS，不经应用服务器中转。"""

    filename: str
    content_type: str = "image/png"


class PresignOut(BaseModel):
    key: str                  # OSS object key，直传成功后随建任务请求回传
    url: str                  # 预签名 PUT 地址
    headers: dict[str, str]   # 直传时必须携带的请求头（Content-Type 已纳入签名）
    expires_in: int


class TokenOut(BaseModel):
    token: str
    expires_in: int
