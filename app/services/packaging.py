import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# 打包时纳入的输出目录
_KEEP = {"03_cutout", "04_white_bg", "05_scene"}


def write_metadata(task_dir: str, task, items: list[dict]) -> str:
    meta = {
        "task_id": str(task.id),
        "description": task.description,
        "options": task.options,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assets": [
            {
                "type": it["type"],
                "size": it.get("size_label"),
                "path": it["path"],
                "fidelity_score": it.get("fidelity_score"),
                "qc_status": it.get("qc_status"),
            }
            for it in items
        ],
    }
    p = Path(task_dir) / "metadata.json"
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def make_zip(task_dir: str) -> str:
    src = Path(task_dir)
    out = src / "package.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(src)
            if rel.parts[0] in _KEEP or p.name == "metadata.json":
                zf.write(p, rel)
    return str(out)
