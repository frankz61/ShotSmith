from pathlib import Path

import httpx
from PIL import Image

from app.core.constants import MIN_SOURCE_SIZE


def run(task, storage) -> Path:
    tid = str(task.id)
    if task.source_type == "upload":
        p = storage.find_source(tid)
        if p is None:
            raise ValueError("未找到上传的源图")
    elif task.source_type == "oss":
        p = _from_oss(task.source_ref, storage.task_dir(tid))
    else:
        p = _download(task.source_ref, storage.task_dir(tid))
    _validate(p)
    return p


def _from_oss(key: str, out_dir: Path) -> Path:
    """前端直传 OSS 的源图：按 key 拉到本地任务目录供流水线处理。"""
    from app.storage import oss

    ext = Path(key).suffix.lower() or ".png"
    p = Path(out_dir) / f"00_source{ext}"
    oss.download_file(key, p)
    return p


def _download(url: str, out_dir: Path) -> Path:
    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    ext = ".png"
    ct = r.headers.get("content-type", "")
    low = url.lower()
    if "jpeg" in ct or low.endswith((".jpg", ".jpeg")):
        ext = ".jpg"
    elif "webp" in ct or low.endswith(".webp"):
        ext = ".webp"
    p = Path(out_dir) / f"00_source{ext}"
    p.write_bytes(r.content)
    return p


def _validate(p: Path) -> None:
    try:
        with Image.open(p) as im:
            im.verify()
    except Exception as e:
        raise ValueError(f"无法识别的图片：{e}") from e
    with Image.open(p) as im:
        w, h = im.size
    if min(w, h) < MIN_SOURCE_SIZE:
        raise ValueError(f"图片分辨率过低（{w}x{h}），最短边需 ≥ {MIN_SOURCE_SIZE}")
