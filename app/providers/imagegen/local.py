from pathlib import Path

from app.core.constants import SCENE_PRESETS
from app.providers.base import GeneratedImage
from app.services import composition


class LocalImageGenProvider:
    """离线场景图：把商品贴到预设渐变背景上。商品像素原样保留，还原度天然≈1。

    这是『抠图 + 商品保持』路线的最小实现；换成商用 API 只需替换本类。
    """

    def generate(self, product_cutout: str, prompt: str, params: dict) -> list[GeneratedImage]:
        out = Path(params["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        sizes: list[tuple] = params["sizes"]          # [(label, w, h), ...]
        variants = int(params.get("variants", 3))

        results: list[GeneratedImage] = []
        for i in range(variants):
            preset = SCENE_PRESETS[i % len(SCENE_PRESETS)]
            for label, w, h in sizes:
                img, bbox = composition.scene(product_cutout, w, h, preset)
                name = f"scene_{i + 1}_{label.replace(':', 'x')}.png"
                fp = out / name
                img.save(fp)
                results.append(
                    GeneratedImage(
                        path=str(fp),
                        size_label=label,
                        meta={"bbox": list(bbox), "preset": preset["name"]},
                    )
                )
        return results
