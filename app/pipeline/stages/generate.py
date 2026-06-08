from pathlib import Path

from app.core.config import settings
from app.core.constants import SIZE_PRESETS
from app.services import composition


def run(cutout_path: str, storage, task_id: str, imagegen, opts: dict, prompt: str) -> list[dict]:
    sizes = [(label, *SIZE_PRESETS[label]) for label in opts["sizes"] if label in SIZE_PRESETS]
    items: list[dict] = []

    if "white_bg" in opts["image_types"]:
        wb = storage.task_dir(task_id) / "04_white_bg"
        wb.mkdir(parents=True, exist_ok=True)
        for label, w, h in sizes:
            img, bbox = composition.white_bg(cutout_path, w, h)
            fp = wb / f"main_{label.replace(':', 'x')}.png"
            img.save(fp)
            items.append({
                "type": "white_bg", "size_label": label, "path": storage.rel(fp),
                "gen_params": {"provider": "composition", "bbox": list(bbox)},
            })

    if "scene" in opts["image_types"]:
        sd = storage.task_dir(task_id) / "05_scene"
        gens = imagegen.generate(cutout_path, prompt, {
            "out_dir": str(sd), "sizes": sizes, "variants": opts["scene_variants"],
        })
        for g in gens:
            items.append({
                "type": "scene", "size_label": g.size_label, "path": storage.rel(Path(g.path)),
                "gen_params": {"provider": opts.get("scene_engine") or settings.imagegen_provider,
                               "prompt": prompt, "seed": g.seed, **(g.meta or {})},
            })
    return items
