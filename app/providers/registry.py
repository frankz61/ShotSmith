"""按配置选择具体 Provider 实现；业务层只依赖抽象，换厂商=改配置。"""
from app.core.config import settings
from app.providers.base import FidelityProvider, ImageGenProvider, MattingProvider
from app.providers.fidelity.dinov2 import DinoV2Provider
from app.providers.fidelity.simple import SimpleFidelity
from app.providers.imagegen.local import LocalImageGenProvider
from app.providers.imagegen.openrouter_image import OpenRouterImageProvider
from app.providers.imagegen.vendor_a import VendorAProvider
from app.providers.matting.rembg_provider import RembgProvider
from app.providers.matting.simple_provider import SimpleMattingProvider

_MATTING = {"rembg": RembgProvider, "simple": SimpleMattingProvider}
_IMAGEGEN = {
    "local": LocalImageGenProvider,
    "openrouter_image": OpenRouterImageProvider,
    "vendor_a": VendorAProvider,
}
_FIDELITY = {"simple": SimpleFidelity, "dinov2": DinoV2Provider}


def get_matting() -> MattingProvider:
    return _MATTING[settings.matting_provider]()


def get_imagegen(name: str | None = None) -> ImageGenProvider:
    """name 为空时用全局默认；按任务可传 'local' / 'openrouter_image' 覆盖，非法值回落默认。"""
    key = name if name in _IMAGEGEN else settings.imagegen_provider
    return _IMAGEGEN[key]()


def get_fidelity() -> FidelityProvider:
    return _FIDELITY[settings.fidelity_provider]()
