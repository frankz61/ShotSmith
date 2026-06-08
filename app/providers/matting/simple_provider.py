from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from app.providers.base import CutoutResult


class SimpleMattingProvider:
    """角点取色的近似抠图：取四角平均色作背景，按色差阈值生成 alpha。

    仅适合纯/近纯色背景（如多数 1688 白底主图）；复杂背景请用 rembg。纯 Pillow，离线可跑。
    """

    def __init__(self, threshold: int = 32) -> None:
        self.threshold = threshold

    def cutout(self, image_path: str, out_dir: str) -> CutoutResult:
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        corners = [img.getpixel((0, 0)), img.getpixel((w - 1, 0)),
                   img.getpixel((0, h - 1)), img.getpixel((w - 1, h - 1))]
        bg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))

        diff = ImageChops.difference(img, Image.new("RGB", (w, h), bg)).convert("L")
        thr = self.threshold
        mask = diff.point(lambda v: 255 if v > thr else 0)
        mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1))

        rgba = img.convert("RGBA")
        rgba.putalpha(mask)

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        rgba_path = out / "product.png"
        mask_path = out / "mask.png"
        rgba.save(rgba_path)
        mask.save(mask_path)
        return CutoutResult(rgba_path=str(rgba_path), mask_path=str(mask_path))
