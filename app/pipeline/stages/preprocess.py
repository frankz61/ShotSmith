from pathlib import Path

from PIL import Image, ImageOps

from app.core.constants import MAX_SIDE


def run(src: Path, storage, task_id: str) -> Path:
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = storage.task_dir(task_id) / "02_input.png"
        im.save(out)
    return out
