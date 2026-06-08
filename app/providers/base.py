from dataclasses import dataclass
from typing import Protocol


@dataclass
class CutoutResult:
    rgba_path: str
    mask_path: str | None = None


@dataclass
class GeneratedImage:
    path: str
    size_label: str
    seed: int | None = None
    meta: dict | None = None


class MattingProvider(Protocol):
    """抠图/分割：把商品主体抠出，写入 out_dir，返回透明底图路径。"""

    def cutout(self, image_path: str, out_dir: str) -> CutoutResult: ...


class ImageGenProvider(Protocol):
    """背景/场景生成：必须保持商品主体，返回 N 张候选图。"""

    def generate(self, product_cutout: str, prompt: str, params: dict) -> list[GeneratedImage]: ...


class FidelityProvider(Protocol):
    """还原度校验：比对生成图与原图商品区域，返回 0~1 相似度。"""

    def score(self, original: str, generated: str, bbox: tuple | None = None) -> float: ...
