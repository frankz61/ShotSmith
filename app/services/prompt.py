import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SCENE = "商品摆放在简洁生活场景中，自然光，柔和阴影，电商主图风格"


def build_prompt(description: str | None, opts: dict) -> str:
    base = (description or "").strip()
    if base:
        return base
    cat = opts.get("category_hint")
    return f"{cat}，{DEFAULT_SCENE}" if cat else DEFAULT_SCENE


def resolve_scene_prompt(
    cutout_path: str, description: str | None, opts: dict
) -> tuple[str, str]:
    """决定送给图像生成的提示词，返回 (prompt, source)。

    source ∈ {"vlm", "user", "template"}：
    - 开启 prompt_vlm 且需要场景图、且引擎非 local 时，先让 Qwen-VL 看抠图写提示词；
    - VLM 不可用/报错时回落到模板提示词，不阻断主流程。
    local 引擎用纯渐变背景、不消费 prompt，故跳过 VLM 以免无谓调用。
    """
    want_scene = "scene" in (opts.get("image_types") or [])
    online_engine = (opts.get("scene_engine") or settings.imagegen_provider) != "local"
    if settings.prompt_vlm_enabled and want_scene and online_engine:
        try:
            from app.services import prompt_vlm
            return prompt_vlm.generate_scene_prompt(cutout_path, description, opts), "vlm"
        except Exception as e:  # 看图失败不影响出图，回落模板
            logger.warning("Qwen-VL 提示词生成失败，回落模板提示词：%s", e)

    base = build_prompt(description, opts)
    return base, ("user" if (description or "").strip() else "template")
