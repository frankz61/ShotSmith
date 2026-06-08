from PIL import Image, ImageChops, ImageStat


class SimpleFidelity:
    """商品还原度：仅在商品不透明区域比对原图与生成图，返回 0~1（越高越还原）。"""

    def score(self, original: str, generated: str, bbox: tuple | None = None) -> float:
        prod = Image.open(original).convert("RGBA")
        alpha = prod.split()[3]
        pb = alpha.getbbox()
        if pb is None:
            return 0.0
        crop = prod.crop(pb)
        prod_rgb = crop.convert("RGB")
        mask = crop.split()[3]

        gen = Image.open(generated).convert("RGB")
        gen_crop = gen.crop(tuple(bbox)) if bbox else gen
        gen_crop = gen_crop.resize(prod_rgb.size)

        diff = ImageChops.difference(prod_rgb, gen_crop)
        mean = sum(ImageStat.Stat(diff, mask).mean) / 3
        return max(0.0, 1.0 - mean / 255.0)
