from PIL import Image, ImageDraw

from app.providers.fidelity.simple import SimpleFidelity
from app.services import composition


def _make_cutout(path) -> None:
    cut = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    ImageDraw.Draw(cut).ellipse([80, 80, 320, 320], fill=(200, 40, 40, 255))
    cut.save(path)


def test_white_bg_keeps_product(tmp_path):
    cp = tmp_path / "product.png"
    _make_cutout(cp)
    img, bbox = composition.white_bg(str(cp), 1000, 1000)
    assert img.size == (1000, 1000)
    gp = tmp_path / "white.png"
    img.save(gp)
    assert SimpleFidelity().score(str(cp), str(gp), bbox) > 0.95


def test_scene_keeps_product(tmp_path):
    cp = tmp_path / "product.png"
    _make_cutout(cp)
    preset = {"name": "t", "top": (240, 240, 240), "bottom": (200, 200, 200)}
    img, bbox = composition.scene(str(cp), 900, 1200, preset)
    gp = tmp_path / "scene.png"
    img.save(gp)
    assert SimpleFidelity().score(str(cp), str(gp), bbox) > 0.9
