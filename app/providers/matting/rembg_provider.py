import logging
from pathlib import Path

from app.core.config import settings
from app.providers.base import CutoutResult

logger = logging.getLogger(__name__)

_session = None  # 缓存 rembg 模型 session，避免每个任务重复加载

# GPU 执行后端优先级：CUDA(NVIDIA) > ROCm(AMD Linux) > DirectML(Windows 任意 DX12 显卡)
_GPU_PROVIDERS = ("CUDAExecutionProvider", "ROCMExecutionProvider", "DmlExecutionProvider")


def _providers() -> list[str]:
    """按 matting_device 选推理后端。rembg 自动逻辑只认 CUDA/ROCm，DirectML 须显式指定。"""
    import onnxruntime as ort

    available = ort.get_available_providers()
    if settings.matting_device != "cpu":
        for p in _GPU_PROVIDERS:
            if p in available:
                return [p, "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def _get_session():
    global _session
    if _session is None:
        from rembg import new_session
        providers = _providers()
        _session = new_session(settings.matting_model, providers=providers)
        logger.info("[Matting] rembg session 就绪：model=%s providers=%s",
                    settings.matting_model, _session.inner_session.get_providers())
    return _session


class RembgProvider:
    """基于 rembg 的高质量抠图，默认 BiRefNet（当前 SOTA）。首次运行会下载模型权重。"""

    def cutout(self, image_path: str, out_dir: str) -> CutoutResult:
        try:
            from PIL import Image
            from rembg import remove
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未安装 rembg。请 `pip install -e '.[matting]'`，或将 MATTING_PROVIDER 设为 simple。"
            ) from e

        img = Image.open(image_path).convert("RGBA")
        cut = remove(img, session=_get_session())

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        rgba_path = out / "product.png"
        mask_path = out / "mask.png"
        cut.save(rgba_path)
        cut.split()[3].save(mask_path)
        return CutoutResult(rgba_path=str(rgba_path), mask_path=str(mask_path))
