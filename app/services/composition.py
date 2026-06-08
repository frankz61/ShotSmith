"""纯 Pillow 图像合成：抠图后把商品贴到白底/场景背景，并加投影。

商品像素原样粘贴，从机制上保证『只换背景、不改商品』。
"""
from PIL import Image, ImageDraw, ImageFilter

Bbox = tuple[int, int, int, int]


def _trim(img: Image.Image) -> Image.Image:
    bb = img.split()[3].getbbox()
    return img.crop(bb) if bb else img


def _fit(cutout: Image.Image, cw: int, ch: int, ratio: float) -> tuple[Image.Image, Bbox]:
    pw, ph = cutout.size
    if pw == 0 or ph == 0:
        return cutout, (0, 0, cw, ch)
    scale = min(cw * ratio / pw, ch * ratio / ph)
    nw, nh = max(1, int(pw * scale)), max(1, int(ph * scale))
    resized = cutout.resize((nw, nh), Image.LANCZOS)
    x, y = (cw - nw) // 2, (ch - nh) // 2
    return resized, (x, y, x + nw, y + nh)


def _gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    base = Image.new("RGB", (w, h), top)
    draw = ImageDraw.Draw(base)
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=col)
    return base


def _paste(canvas: Image.Image, product: Image.Image, bbox: Bbox, shadow: bool = True) -> None:
    x, y, x2, y2 = bbox
    if shadow:
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        ew, eh = int((x2 - x) * 0.92), max(8, int((y2 - y) * 0.12))
        cx, ey = (x + x2) // 2, y2 - eh // 2
        d.ellipse([cx - ew // 2, ey - eh // 2, cx + ew // 2, ey + eh // 2], fill=(0, 0, 0, 90))
        layer = layer.filter(ImageFilter.GaussianBlur(max(4, eh // 2)))
        canvas.alpha_composite(layer)
    canvas.alpha_composite(product, (x, y))


def white_bg(cutout_path: str, w: int, h: int, ratio: float = 0.82) -> tuple[Image.Image, Bbox]:
    cut = _trim(Image.open(cutout_path).convert("RGBA"))
    canvas = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    prod, bbox = _fit(cut, w, h, ratio)
    _paste(canvas, prod, bbox, shadow=True)
    return canvas.convert("RGB"), bbox


def scene(cutout_path: str, w: int, h: int, preset: dict, ratio: float = 0.70) -> tuple[Image.Image, Bbox]:
    cut = _trim(Image.open(cutout_path).convert("RGBA"))
    canvas = _gradient(w, h, preset["top"], preset["bottom"]).convert("RGBA")
    prod, bbox = _fit(cut, w, h, ratio)
    _paste(canvas, prod, bbox, shadow=True)
    return canvas.convert("RGB"), bbox


def place_on_transparent(cutout_path: str, w: int, h: int, ratio: float = 0.72) -> tuple[Image.Image, Bbox]:
    """把商品按目标尺寸居中放到透明画布上，返回 RGBA 图与商品 bbox。

    用作背景生成 API 的 base_image：API 只在透明区域生成背景、保留前景商品，
    因此这里确定的 bbox 即生成结果中商品所在区域，可直接用于还原度校验。
    """
    cut = _trim(Image.open(cutout_path).convert("RGBA"))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    prod, bbox = _fit(cut, w, h, ratio)
    canvas.alpha_composite(prod, (bbox[0], bbox[1]))
    return canvas, bbox
