DEFAULT_SCENE = "商品摆放在简洁生活场景中，自然光，柔和阴影，电商主图风格"


def build_prompt(description: str | None, opts: dict) -> str:
    base = (description or "").strip()
    if base:
        return base
    cat = opts.get("category_hint")
    return f"{cat}，{DEFAULT_SCENE}" if cat else DEFAULT_SCENE
