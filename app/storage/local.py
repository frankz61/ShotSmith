import shutil
from pathlib import Path

from app.core.config import settings


class LocalStorage:
    """MVP 本地文件存储；上量后替换为 OSS/S3 适配。路径以 storage_dir 为根。"""

    def __init__(self, base: str | None = None) -> None:
        self.base = Path(base or settings.storage_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def task_dir(self, task_id: str) -> Path:
        d = self.base / "tasks" / str(task_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def rel(self, p) -> str:
        return Path(p).resolve().relative_to(self.base).as_posix()

    def abs(self, rel: str) -> Path:
        return self.base / rel

    def save_upload(self, task_id: str, filename: str, data: bytes) -> Path:
        ext = Path(filename).suffix.lower() or ".png"
        p = self.task_dir(task_id) / f"00_source{ext}"
        p.write_bytes(data)
        return p

    def find_source(self, task_id: str):
        for p in sorted(self.task_dir(task_id).glob("00_source.*")):
            return p
        return None

    def remove_task_dir(self, task_id: str) -> None:
        """删除整个任务目录（原图 + 全部生成素材）。目录不存在则静默跳过。"""
        d = self.base / "tasks" / str(task_id)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
