"""用 Qwen-VL 多模态大模型「看图写提示词」。

在调用通义万相·背景生成之前，先让 Qwen-VL 结合「去背景后的商品图」理解分析，
产出一段只描述背景场景的中文提示词，作为 aliyun_bg 的 ref_prompt。

为什么：固定模板提示词无法贴合具体商品；让 VLM 看图后生成的场景描述更契合
商品的品类/材质/调性，从而提升场景图质量。本步骤失败由调用方回落到模板提示词，
不阻断主流程（见 services.prompt.resolve_scene_prompt）。

实现走 DashScope 的 OpenAI 兼容端点：图片以 base64 data URI 内联，只依赖 httpx，
无需 dashscope SDK，也不必把抠图上传 OSS。
"""
import base64
import io
import time

import httpx
from PIL import Image

from app.core.config import settings

_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
_VLM_MAX_SIDE = 1024   # 喂给 VLM 前把长边缩到此值以内，省 token / 降延迟
_PROMPT_MAX = 120      # 与 aliyun_bg 的 ref_prompt 上限对齐（中文≤120 字符）
# qwen3.7-plus 为思考型模型、响应偏慢，易踩传输层瞬断；仅重试瞬断，不碰 HTTP 4xx/5xx
_RETRIABLE = (httpx.TransportError,)

_SYSTEM = (
    "你是资深电商视觉设计师。用户会给你一张『已抠图、透明背景』的商品图。"
    "请观察商品的品类、材质、颜色与风格，构思一个最适合该商品的电商主图『背景场景』，"
    "并输出一段中文提示词用于 AI 背景生成。要求："
    "1) 只描述背景场景、光线、氛围、道具与构图，绝不描述或改动商品本身；"
    "2) 风格简洁高级、贴合商品调性，适合电商主图；"
    "3) 不超过 60 个汉字，输出纯文本，不要引号、不要解释、不要换行。"
)


def _encode_data_uri(cutout_path: str) -> str:
    """把抠图（RGBA PNG）等比缩到 _VLM_MAX_SIDE 内，编码为 base64 data URI。"""
    img = Image.open(cutout_path)
    img.thumbnail((_VLM_MAX_SIDE, _VLM_MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def _extract_text(data: dict) -> str:
    """兼容 content 为 str 或 [{type,text}] 两种返回形态。"""
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") for p in content if isinstance(p, dict)
        )
    return (content or "").strip()


def generate_scene_prompt(cutout_path: str, description: str | None, opts: dict) -> str:
    """看图生成场景提示词；任何异常向上抛出，由调用方负责回落。"""
    key = settings.dashscope_api_key or settings.imagegen_api_key
    if not key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法调用 Qwen-VL。")

    hints: list[str] = []
    if opts.get("category_hint"):
        hints.append(f"商品品类：{opts['category_hint']}")
    if (description or "").strip():
        hints.append(f"用户期望：{description.strip()}")
    user_text = "；".join(hints) if hints else "请根据图片自行判断商品。"
    user_text += " 请直接给出背景场景提示词。"

    body = {
        "model": settings.vlm_model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": _encode_data_uri(cutout_path)}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=settings.vlm_timeout) as client:
        data = None
        for i in range(3):
            try:
                r = client.post(_CHAT_URL, json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
                break
            except _RETRIABLE:
                if i == 2:
                    raise
                time.sleep(2.0)

    text = _extract_text(data)
    # 去掉模型（尤其思考型）可能附带的 markdown 粗体/标题、引号、换行与句末标点
    text = text.replace("*", "").replace("#", "")
    text = " ".join(text.split())            # 折叠空白/换行
    text = text.strip("“”\"'`。.： ").strip()
    if not text:
        raise RuntimeError(f"Qwen-VL 返回空提示词：{str(data)[:200]}")
    return text[:_PROMPT_MAX]
