"""生成流水线编排：ingest → preprocess → matting → generate → qc → package。

逐阶段更新 task 状态/进度，产物落库 asset，异常记录 error_message。
"""
import uuid

from app.core.config import settings
from app.core.constants import DEFAULT_SCENE_COUNT, DEFAULT_SIZES
from app.models.db import SessionLocal
from app.models.task import Asset, Task
from app.pipeline.stages import generate, ingest, matting, preprocess, quality
from app.providers import registry
from app.services import packaging
from app.services.prompt import resolve_scene_prompts
from app.storage.local import LocalStorage


def _opts(raw: dict | None) -> dict:
    raw = raw or {}
    return {
        "sizes": raw.get("sizes") or DEFAULT_SIZES,
        "image_types": raw.get("image_types") or ["white_bg", "scene"],
        "scene_count": int(raw.get("scene_count") or DEFAULT_SCENE_COUNT),
        "category_hint": raw.get("category_hint"),
        # 场景图引擎：local(纯色合成) / openrouter_image(OpenRouter·Gemini)；缺省回落全局默认
        "scene_engine": raw.get("scene_engine") or settings.imagegen_provider,
        # 跨境卖家约束：货源参考链接(如 1688 详情页) + 目标零售平台(amazon/walmart/generic)
        "product_url": (raw.get("product_url") or "").strip() or None,
        "target_platform": raw.get("target_platform") or "generic",
    }


def _set(db, task, status, stage, progress) -> None:
    task.status, task.current_stage, task.progress = status, stage, progress
    db.commit()


def run(task_id: str) -> None:
    storage = LocalStorage()
    db = SessionLocal()
    task = None
    try:
        task = db.get(Task, uuid.UUID(str(task_id)))
        if task is None:
            return
        for a in list(task.assets):      # 清理旧素材（regenerate 场景）
            db.delete(a)
        db.commit()

        opts = _opts(task.options)
        _set(db, task, "processing", "ingest", 5)
        src = ingest.run(task, storage)
        _set(db, task, "processing", "preprocess", 15)
        prep = preprocess.run(src, storage, str(task.id))
        _set(db, task, "processing", "matting", 35)
        cutout = matting.run(prep, storage, str(task.id), registry.get_matting())
        _set(db, task, "processing", "generate", 55)
        # 在线生图前：先经 OpenRouter 两段式（识图+创意）为每张场景图各写一条提示词
        prompts, opts["prompt_source"] = resolve_scene_prompts(
            cutout, task.description, opts, opts["scene_count"]
        )
        imagegen = registry.get_imagegen(opts["scene_engine"])
        items = generate.run(cutout, storage, str(task.id), imagegen, opts, prompts)
        _set(db, task, "processing", "qc", 80)
        quality.run(cutout, items, registry.get_fidelity(), storage)

        db.add(Asset(task_id=task.id, type="cutout", path=storage.rel(cutout),
                     qc_status="passed", gen_params={"provider": settings.matting_provider}))
        for it in items:
            db.add(Asset(task_id=task.id, type=it["type"], size_label=it["size_label"],
                         path=it["path"], fidelity_score=it.get("fidelity_score"),
                         qc_status=it.get("qc_status", "pending"), gen_params=it["gen_params"]))
        db.commit()

        _set(db, task, "processing", "package", 95)
        packaging.write_metadata(str(storage.task_dir(str(task.id))), task, items)
        has_review = any(i.get("qc_status") == "needs_review" for i in items)
        task.status = "partial" if has_review else "success"
        task.current_stage, task.progress = "package", 100
        db.commit()
    except Exception as e:
        db.rollback()
        if task is not None:
            task.status = "failed"
            task.error_message = str(e)[:500]
            db.commit()
        raise
    finally:
        db.close()
