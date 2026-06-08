import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Numeric, SmallInteger, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.db import Base


class Task(Base):
    """生成任务，对应 docs/数据库设计.md 的 task 表。"""

    __tablename__ = "task"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    current_stage: Mapped[str | None] = mapped_column(String(16))
    progress: Mapped[int] = mapped_column(SmallInteger, default=0)
    source_type: Mapped[str] = mapped_column(String(8))
    source_ref: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    assets: Mapped[list["Asset"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Asset(Base):
    """生成素材，对应 docs/数据库设计.md 的 asset 表。"""

    __tablename__ = "asset"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16))
    size_label: Mapped[str | None] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(Text)
    fidelity_score: Mapped[float | None] = mapped_column(Numeric(4, 3))
    qc_status: Mapped[str] = mapped_column(String(16), default="pending")
    selected: Mapped[bool] = mapped_column(default=False)
    gen_params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="assets")
