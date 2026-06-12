import logging

from app.core.config import settings
from app.core.constants import TEXT_LANGS

logger = logging.getLogger(__name__)

DEFAULT_SCENE = "摆放在简洁明亮的生活场景中，自然光，柔和阴影，真实生活方式"

# 模板回落时的多样化场景变化：保证 5 张场景图方向各异（与 VLM 创意路径对齐）
_FALLBACK_STYLES = [
    "背景是明亮客厅的木质桌面与落地窗自然光",
    "背景是大理石台面搭配绿植与柔和晨光",
    "背景是户外木桌与阳光草地的虚化光斑",
    "背景是极简纯色摄影棚的专业柔光",
    "背景是温馨暖色调台面与浅景深氛围光",
]


def build_prompt(description: str | None, opts: dict) -> str:
    base = (description or "").strip()
    if base:
        return base
    cat = opts.get("category_hint")
    return f"{cat}，{DEFAULT_SCENE}" if cat else DEFAULT_SCENE


def _lang_suffix(text_lang: str | None) -> str:
    """图中文字语言的硬指令，追加在每条生图提示词末尾（VLM/模板两条路径双保险）。"""
    if not text_lang or text_lang == "none":
        return ""
    lang = TEXT_LANGS.get(text_lang, text_lang)
    return (
        f"，画面可在商品之外的标牌、包装等场景承载物上自然融入简短贴合商品的{lang}文字，"
        f"文字必须是{lang}中真实存在的单词或短语、语法正确、拼写准确无误、清晰可读，"
        f"不得出现其他语言的文字；商品本体上原有的文字、logo、标签必须原样保留，"
        f"不得翻译、替换、覆盖或修改"
    )


def _wrap(scene: str) -> str:
    """把场景描述包装成与 VLM 创意路径同款的完整生图提示词。"""
    return (
        f"保持参考图中的商品不变，{scene}，"
        "商品与场景光影自然融合，真实摄影风格，电商详情页场景图"
    )


def resolve_scene_prompts(
    cutout_path: str, description: str | None, opts: dict, count: int
) -> tuple[list[str], str]:
    """决定送给图像生成的提示词列表（每张一条、方向各异），返回 (prompts, source)。

    source ∈ {"vlm", "user", "template"}：
    - 开启 prompt_vlm 且需要场景图、且引擎非 local 时，先经 OpenRouter 两段式
      （视觉识图 + 文本模型创意）生成 count 条不同提示词；
    - VLM 不可用/报错时回落到「模板 + 风格变化」组合，不阻断主流程。
    local 引擎用纯渐变背景、不消费 prompt，故跳过 VLM 以免无谓调用。
    """
    want_scene = "scene" in (opts.get("image_types") or [])
    online_engine = (opts.get("scene_engine") or settings.imagegen_provider) != "local"
    suffix = _lang_suffix(opts.get("text_lang"))
    if settings.prompt_vlm_enabled and want_scene and online_engine:
        # 卖家给了货源参考链接（如 1688 详情页）时，尽力抓取标题/描述约束 VLM 判断
        if opts.get("product_url") and not opts.get("product_info"):
            from app.services import product_info
            opts["product_info"] = product_info.fetch_product_hint(opts["product_url"])
        try:
            from app.services import prompt_vlm
            prompts = prompt_vlm.generate_scene_prompts(cutout_path, description, opts, count)
            logger.info("[Prompt] source=vlm，共 %d 条提示词", len(prompts))
            return [p + suffix for p in prompts], "vlm"
        except Exception as e:  # 看图失败不影响出图，回落模板
            logger.warning("VLM 提示词生成失败，回落模板提示词：%s", e)

    base = build_prompt(description, opts)
    prompts = [
        _wrap(f"{base}，{_FALLBACK_STYLES[i % len(_FALLBACK_STYLES)]}") + suffix
        for i in range(count)
    ]
    source = "user" if (description or "").strip() else "template"
    logger.info("[Prompt] source=%s，共 %d 条提示词，基底: %r", source, count, base)
    return prompts, source
