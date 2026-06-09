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


class TokenOut(BaseModel):
    token: str
    expires_in: int
