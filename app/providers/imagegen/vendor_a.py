from app.providers.base import GeneratedImage


class VendorAProvider:
    """商用『商品图』API 适配（保持商品主体）。接入真实厂商时实现本类。"""

    def generate(self, product_cutout: str, prompt: str, params: dict) -> list[GeneratedImage]:
        raise NotImplementedError(
            "TODO: 调用商用图像 API；用 settings.imagegen_api_key / imagegen_api_base 鉴权"
        )
