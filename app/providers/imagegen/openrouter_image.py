"""OpenRouter 生图 Provider（imagegen_provider=openrouter_image）。

经 OpenRouter 网关调用图像生成模型（默认 google/gemini-3.1-flash-image-preview，
即 Nano Banana 2）：走 chat/completions + modalities=["image","text"]，
输入「商品贴在透明画布上的 RGBA PNG」+ 场景提示词，让模型保留商品主体、补全背景。

要点：
- 同步接口，结果以 base64 data URI 内嵌在 message.images 里，无需建任务轮询；
- 尺寸经 image_config 控制 aspect_ratio（恰好与本项目 1:1/3:4/4:5 标签一致）
  和 image_size 档位（0.5K/1K/2K/4K），输出分辨率非精确值，下载后缩放到目标尺寸；
- 一次响应通常返回 1 张图，多变体靠多次请求实现；
- 商品保持依赖提示词约束 + 后置还原度校验（quality 阶段）兜底。

接入参考：https://openrouter.ai/docs/guides/overview/multimodal/image-generation
"""
import base64
import io
import logging
import time
from pathlib import Path

import httpx
from PIL import Image

from app.core.config import settings
from app.providers.base import GeneratedImage
from app.services import composition

logger = logging.getLogger(__name__)

_RETRIABLE = (httpx.TransportError,)


class OpenRouterImageProvider:
    """OpenRouter·Gemini 生图适配。换厂商只需实现 ImageGenProvider.generate。"""

    def generate(self, product_cutout: str, prompt: str, params: dict) -> list[GeneratedImage]:
        key = settings.openrouter_api_key
        if not key:
            raise RuntimeError("未配置 OPENROUTER_API_KEY，无法调用 OpenRouter 生图。")

        out = Path(params["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        sizes: list[tuple] = params["sizes"]                 # [(label, w, h), ...]
        n = max(1, min(4, int(params.get("variants", 3))))
        seq = int(params.get("seq", 0))                      # 全局序号：用于结果命名
        # 提示词由上游（VLM 创意/模板）产出完整自然语句，已含商品保持指令，不再拼前缀
        full_prompt = (prompt or "").strip()
        logger.info(
            "[OpenRouterImage] 开始生成：model=%s，image_size=%s，n=%d，sizes=%s\n"
            "[OpenRouterImage] prompt: %r",
            settings.openrouter_image_model, settings.openrouter_image_size,
            n, [s[0] for s in sizes], full_prompt,
        )

        url = f"{settings.openrouter_api_base.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        # 构图布局按全局序号轮换（位置/大小各不相同），并把实际摆放位置写进提示词，
        # 要求模型围绕该位置造景、做接触阴影与光线统一——这是"贴图感"的主要解药
        layout = composition.SCENE_LAYOUTS[max(seq - 1, 0) % len(composition.SCENE_LAYOUTS)]
        logger.info("[OpenRouterImage] 构图布局：%s（ratio=%.2f）", layout["desc"], layout["ratio"])
        grounding = (
            f"。商品位于{layout['desc']}，保持其位置与大小不变，围绕它构建完整场景："
            "商品必须自然放置或依托在场景中真实的承托面/支撑物上，底部接触处有贴合的"
            "接触阴影，投影方向与场景主光源一致，商品周围的环境光、色温、透视与整体"
            "场景完全统一，使商品看起来是实拍于场景之中，而非后期贴图"
        )
        results: list[GeneratedImage] = []
        with httpx.Client(timeout=settings.openrouter_image_timeout) as client:
            for label, w, h in sizes:
                base_img, bbox = composition.place_on_transparent(product_cutout, w, h,
                                                                  layout=layout)
                buf = io.BytesIO()
                base_img.save(buf, format="PNG")
                data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

                # 该接口一次通常返回 1 张图，多变体逐次请求
                for i in range(n):
                    t0 = time.monotonic()
                    images = self._create(client, url, headers, data_uri,
                                          full_prompt + grounding, label)
                    logger.info(
                        "[OpenRouterImage] 尺寸 %s 第 %d/%d 张完成，耗时 %.1fs",
                        label, i + 1, n, time.monotonic() - t0,
                    )
                    idx = (seq + i) if seq else (i + 1)
                    fp = out / f"scene_{idx}_{label.replace(':', 'x')}.png"
                    img = images[0].convert("RGB")
                    if img.size != (w, h):  # 输出分辨率由档位决定，统一缩放到目标尺寸
                        img = img.resize((w, h), Image.LANCZOS)
                    img.save(fp)
                    logger.info("[OpenRouterImage] 结果图已保存：%s", fp)
                    results.append(
                        GeneratedImage(
                            path=str(fp),
                            size_label=label,
                            # 输入画布与输出同比例，缩放后 bbox 在目标坐标系下仍近似有效
                            meta={
                                "bbox": list(bbox),
                                "preset": "openrouter_image",
                                "model": settings.openrouter_image_model,
                            },
                        )
                    )
        return results

    @staticmethod
    def _create(client: httpx.Client, url: str, headers: dict,
                data_uri: str, prompt: str, aspect_ratio: str) -> list[Image.Image]:
        """单次生图请求，返回解码后的 PIL 图列表；仅重试传输层瞬断。"""
        body = {
            "model": settings.openrouter_image_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }],
            "modalities": ["image", "text"],
            "image_config": {
                "aspect_ratio": aspect_ratio,        # 与尺寸标签 1:1/3:4/4:5 一致
                "image_size": settings.openrouter_image_size,
            },
        }
        data = None
        for i in range(3):
            try:
                r = client.post(url, json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
                break
            except _RETRIABLE as e:
                logger.warning("[OpenRouterImage] 第 %d 次请求瞬断（%s），重试中…", i + 1, e)
                if i == 2:
                    raise
                time.sleep(2.0)

        msg = data["choices"][0]["message"]
        images = []
        for item in msg.get("images") or []:
            uri = item.get("image_url", {}).get("url", "")
            if "base64," in uri:
                images.append(Image.open(io.BytesIO(base64.b64decode(uri.split("base64,", 1)[1]))))
        if not images:
            raise RuntimeError(
                f"OpenRouter 生图未返回图片：{str(msg.get('content', ''))[:300]}"
            )
        return images
