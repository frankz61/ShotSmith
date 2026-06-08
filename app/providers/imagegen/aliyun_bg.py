"""阿里通义万相·背景生成 Provider（imagegen_provider=aliyun_bg）。

只换背景、保留商品主体——契合本项目"AI 不得篡改商品本体"的第一约束。

流程（每个尺寸一个异步任务）：
1. 把抠图按目标尺寸放到透明画布上 → RGBA 主体图（背景生成要求 RGBA PNG、长边≤2048）；
2. 用 dashscope SDK 的 OssUtils 上传得到 oss:// URL（解决"本地图如何让阿里访问"）；
3. POST 创建异步任务（X-DashScope-Async: enable），n=variants 一次返回多张候选；
4. 轮询 GET /tasks/{id} 直到 SUCCEEDED，下载结果图；
5. 商品位置 bbox 随结果一起返回，供还原度校验只比对商品区域。

接入参考：阿里云百炼·图像背景生成 API
https://help.aliyun.com/zh/model-studio/wanx-background-generation-api-reference
"""
import time
from pathlib import Path

import httpx
from PIL import Image

from app.core.config import settings
from app.providers.base import GeneratedImage
from app.services import composition

_CREATE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/background-generation/generation/"
_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
_DONE = {"SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}
_REF_PROMPT_MAX = 120  # 中文≤120字符（英文≤150词），统一按字符截断保底
# 仅重试传输层瞬断（含 SSL EOF；requests/ssl 错误均为 OSError 子类），不碰 HTTP 4xx/5xx
_RETRIABLE = (httpx.TransportError, OSError)


def _retry(fn, attempts: int = 3, delay: float = 2.0):
    for i in range(attempts):
        try:
            return fn()
        except _RETRIABLE:
            if i == attempts - 1:
                raise
            time.sleep(delay)


class AliyunBackgroundProvider:
    """通义万相·背景生成适配。换厂商只需实现 ImageGenProvider.generate。"""

    def generate(self, product_cutout: str, prompt: str, params: dict) -> list[GeneratedImage]:
        key = settings.dashscope_api_key or settings.imagegen_api_key
        if not key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法调用阿里背景生成。")

        out = Path(params["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        sizes: list[tuple] = params["sizes"]                 # [(label, w, h), ...]
        n = max(1, min(4, int(params.get("variants", 3))))   # 接口 n 取值 1~4
        ref_prompt = (prompt or "").strip()[:_REF_PROMPT_MAX]

        results: list[GeneratedImage] = []
        with httpx.Client(timeout=60.0) as client:
            for label, w, h in sizes:
                base_img, bbox = composition.place_on_transparent(product_cutout, w, h)
                base_fp = out / f"_base_{label.replace(':', 'x')}.png"
                base_img.save(base_fp)

                oss_url = _retry(lambda: self._upload(str(base_fp), key))
                task_id = _retry(lambda: self._create(client, oss_url, ref_prompt, n, key))
                urls = self._wait(client, task_id, key)

                for i, url in enumerate(urls):
                    fp = out / f"scene_{i + 1}_{label.replace(':', 'x')}.png"
                    _retry(lambda u=url, f=fp: self._download(client, u, f, w, h))
                    results.append(
                        GeneratedImage(
                            path=str(fp),
                            size_label=label,
                            meta={
                                "bbox": list(bbox),
                                "preset": "aliyun_bg",
                                "model": settings.aliyun_bg_model,
                                "task_id": task_id,
                            },
                        )
                    )
        return results

    @staticmethod
    def _upload(file_path: str, key: str) -> str:
        try:
            from dashscope.utils.oss_utils import OssUtils
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未安装 dashscope。请 `pip install -e '.[aliyun]'`，"
                "或将 IMAGEGEN_PROVIDER 设回 local。"
            ) from e
        oss_url = OssUtils.upload(
            model=settings.aliyun_bg_model, file_path=file_path, api_key=key
        )
        if isinstance(oss_url, (tuple, list)):  # 新版 SDK 返回 (oss_url, policy)
            oss_url = oss_url[0] if oss_url else None
        if not oss_url:
            raise RuntimeError(f"主体图上传 OSS 失败：{file_path}")
        return oss_url

    @staticmethod
    def _create(client: httpx.Client, base_url: str, ref_prompt: str, n: int, key: str) -> str:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
            "X-DashScope-OssResourceResolve": "enable",  # base_image_url 为 oss:// 时必带
        }
        body = {
            "model": settings.aliyun_bg_model,
            "input": {"base_image_url": base_url, "ref_prompt": ref_prompt},
            "parameters": {
                "n": n,
                "model_version": settings.aliyun_bg_model_version,
                "noise_level": settings.aliyun_bg_noise_level,
                "ref_prompt_weight": settings.aliyun_bg_ref_prompt_weight,
            },
        }
        r = client.post(_CREATE_URL, json=body, headers=headers)
        r.raise_for_status()
        task_id = r.json().get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"创建背景生成任务失败：{r.text[:300]}")
        return task_id

    @staticmethod
    def _wait(client: httpx.Client, task_id: str, key: str) -> list[str]:
        headers = {"Authorization": f"Bearer {key}"}
        url = _TASK_URL.format(task_id=task_id)
        deadline = time.monotonic() + settings.aliyun_poll_timeout
        while True:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            output = r.json().get("output", {})
            status = output.get("task_status")
            if status == "SUCCEEDED":
                urls = [it["url"] for it in output.get("results", []) if it.get("url")]
                if not urls:
                    raise RuntimeError(f"任务 {task_id} 成功但无结果图")
                return urls
            if status in _DONE:  # FAILED / CANCELED / UNKNOWN
                raise RuntimeError(
                    f"背景生成任务 {task_id} 状态 {status}：{output.get('message', '')}"
                )
            if time.monotonic() > deadline:
                raise RuntimeError(f"背景生成任务 {task_id} 等待超时（{settings.aliyun_poll_timeout}s）")
            time.sleep(settings.aliyun_poll_interval)

    @staticmethod
    def _download(client: httpx.Client, url: str, fp: Path, w: int, h: int) -> None:
        r = client.get(url)
        r.raise_for_status()
        tmp = fp.with_suffix(".dl")
        tmp.write_bytes(r.content)
        img = Image.open(tmp).convert("RGB")
        if img.size != (w, h):  # 结果若与目标尺寸不一致则统一缩放
            img = img.resize((w, h), Image.LANCZOS)
        img.save(fp)
        tmp.unlink(missing_ok=True)
