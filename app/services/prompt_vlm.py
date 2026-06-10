"""「看图写提示词」（经 OpenRouter 网关）：为每张场景图产出一条不同的创意提示词。

自适应单段/两段：
- 创意模型（settings.openrouter_text_model，如 openai/gpt-5.5）支持图片输入时，
  **单段**完成：直接看「去背景后的商品图」+ 平台/品类/链接约束，一次产出
  N 条方向各异、细节具体的中文场景提示词（JSON 数组）——看图直出细节最忠实；
- 创意模型为纯文本（如 deepseek 系列，带图请求被 OpenRouter 以 404 拒绝）时，
  自动回落**两段式**：先用视觉模型（settings.openrouter_vlm_model）识图输出
  商品细节描述，再交给创意模型纯文本创作。

本步骤任何失败由调用方回落到模板提示词，不阻断主流程
（见 services.prompt.resolve_scene_prompts）。
"""
import base64
import io
import json
import logging
import re
import time

import httpx
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

_VLM_MAX_SIDE = 1024   # 喂给 VLM 前把长边缩到此值以内，省 token / 降延迟
_PROMPT_MAX = 150      # 单条提示词长度保底截断（中文≤150 字符）
# 仅重试传输层瞬断，不碰 HTTP 4xx/5xx
_RETRIABLE = (httpx.TransportError,)

# 两段式第一段：看图客观描述商品（不发挥，只陈述，细节尽量具体）
_DESCRIBE_SYSTEM = (
    "你是电商商品图像识别助手。用户会给你一张『已抠图、透明背景』的商品图。"
    "请用两三句中文客观、具体地描述该商品：品类与形态、主体颜色与配色、"
    "材质与表面质感（如哑光/亮面/纹理）、显著细节特征（部件/图案/工艺）、"
    "风格调性与典型使用场景。只描述看到的事实，不要建议、不要发挥，"
    "不超过 100 个汉字，输出纯文本。"
)

# 创意场景提示词：每条都是给图像生成模型的完整自然语句（含商品保持指令）
_CREATIVE_SYSTEM = (
    "你是资深跨境电商视觉设计师与创意总监。用户是电商卖家，从批发平台（如 1688）选品，"
    "将商品发布到海外零售平台（如亚马逊、Walmart）销售。"
    "请基于给定的商品信息，为 AI 图像生成写场景提示词。每条提示词必须是一段自然流畅的"
    "中文完整描述，参照这个范例的口吻与结构："
    "『保持参考图中的双筒望远镜不变，放置在森林木桩或户外桌面上，"
    "背景有绿色树林、阳光光斑和远处小鸟虚化元素，表现观鸟、自然观察、户外探索，"
    "产品镜片反射蓝紫光，真实摄影风格，电商详情页场景图。』"
    "结构要素依次为："
    "① 以『保持参考图中的{具体商品名}不变』开头；"
    "② 放置位置（台面/地面/手边等具体可视的承托物）；"
    "③ 背景环境元素（道具、光线、色调、虚化元素，写具体不空泛）；"
    "④ 表现的用途、生活方式或情绪；"
    "⑤ 商品与光影的互动细节（如镜片反光、金属高光、织物纹理受光、瓷面柔光）；"
    "⑥ 以『真实摄影风格，电商详情页场景图』结尾。"
    "硬性要求："
    "1) 绝不改动商品本身的形状、颜色、材质与文字细节，互动只限光影层面；"
    "2) 每条的场景方向必须明显不同（家居生活、户外自然、节日氛围、极简棚拍、质感特写等），"
    "且都贴合商品真实用途；"
    "3) 场景元素符合目标市场消费者的生活方式与审美；"
    "4) 画面中不得出现任何文字、品牌 logo、水印、价签、人脸；"
    "5) 每条 50~100 个汉字；"
    "6) 只输出 JSON 字符串数组（如 [\"…\",\"…\"]），不要其他解释。"
)

# 目标平台风格约束：作为 user 消息的一部分注入，约束输出范围避免跑偏
_PLATFORM_STYLE = {
    "amazon": (
        "目标平台：亚马逊（Amazon）。场景图用于 listing 副图/生活方式图，"
        "面向欧美消费者：真实自然的使用环境、明亮通透光线、欧美家居或户外风格，"
        "干净不杂乱，突出商品使用情境。"
    ),
    "walmart": (
        "目标平台：Walmart。面向美国大众家庭消费者：场景务实亲民、明亮整洁，"
        "典型美式家庭/日常生活环境，避免过度奢华或小众风格。"
    ),
    "generic": (
        "目标平台：通用零售电商。场景简洁高级、贴合商品调性，适合电商场景图。"
    ),
}


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


def _chat(client: httpx.Client, model: str, messages: list, key: str) -> dict:
    """单次 chat/completions 调用；仅重试传输层瞬断。"""
    url = f"{settings.openrouter_api_base.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": messages}
    for i in range(3):
        try:
            r = client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return r.json()
        except _RETRIABLE as e:
            logger.warning("[VLM] 第 %d 次请求瞬断（%s），重试中…", i + 1, e)
            if i == 2:
                raise
            time.sleep(2.0)
    raise RuntimeError("unreachable")


def _clean(text: str) -> str:
    """去掉 markdown 符号/引号/多余空白，截断到上限。"""
    text = text.replace("*", "").replace("#", "")
    text = " ".join(text.split())
    text = text.strip("“”\"'`。.： ").strip()
    return text[:_PROMPT_MAX]


def _describe_product(client: httpx.Client, key: str, cutout_path: str) -> str:
    """第一段：视觉模型看图，输出一句客观商品描述。"""
    model = settings.openrouter_vlm_model
    t0 = time.monotonic()
    data = _chat(client, model, [
        {"role": "system", "content": _DESCRIBE_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请描述这件商品。"},
                {"type": "image_url",
                 "image_url": {"url": _encode_data_uri(cutout_path)}},
            ],
        },
    ], key)
    desc = _clean(_extract_text(data))
    if not desc:
        raise RuntimeError(f"视觉识别返回空描述：{str(data)[:200]}")
    logger.info(
        "[VLM·识图] %s 耗时 %.1fs，商品描述: %r",
        model, time.monotonic() - t0, desc,
    )
    return desc


def _parse_prompts(raw: str) -> list[str]:
    """从模型输出解析 JSON 字符串数组；带 markdown 围栏或前后缀时尽力提取。"""
    m = re.search(r"\[.*\]", raw, re.S)
    if m:
        try:
            arr = json.loads(m.group(0))
            return [_clean(str(p)) for p in arr if str(p).strip()]
        except json.JSONDecodeError:
            pass
    # 兜底：按行拆（去序号/列表符）
    lines = [re.sub(r"^[\s\d\.\-\*、)）]+", "", ln).strip() for ln in raw.splitlines()]
    return [_clean(ln) for ln in lines if len(ln) >= 8]


def _build_user_text(opts: dict, description: str | None, count: int,
                     product_desc: str | None) -> str:
    platform = (opts.get("target_platform") or "generic").lower()
    hints: list[str] = [_PLATFORM_STYLE.get(platform, _PLATFORM_STYLE["generic"])]
    if product_desc:
        hints.append(f"商品描述（来自看图识别）：{product_desc}")
    if opts.get("category_hint"):
        hints.append(f"商品品类：{opts['category_hint']}")
    if opts.get("product_info"):
        # 来自商品参考链接（如 1688 详情页）抓取的标题/描述，用于约束品类判断
        hints.append(f"商品链接信息：{opts['product_info']}")
    if (description or "").strip():
        hints.append(f"用户期望：{description.strip()}")
    return (
        "；".join(hints)
        + f" 请为这件商品输出 {count} 条场景方向各不相同、按范例结构写的完整场景提示词，"
          "以 JSON 字符串数组返回。"
    )


def generate_scene_prompts(
    cutout_path: str, description: str | None, opts: dict, count: int
) -> list[str]:
    """生成 count 条互不相同的场景提示词；任何异常向上抛出，由调用方回落。"""
    key = settings.openrouter_api_key
    if not key:
        raise RuntimeError("未配置 OPENROUTER_API_KEY，无法调用 OpenRouter。")

    model = settings.openrouter_text_model
    with httpx.Client(timeout=settings.vlm_timeout) as client:
        # 优先单段：创意模型直接看图（细节最忠实）；纯文本模型带图会 404，回落两段式
        user_text = _build_user_text(opts, description, count, None)
        logger.info("[VLM·创意] 调用 openrouter/%s（带图），user_text=%r", model, user_text)
        t0 = time.monotonic()
        try:
            data = _chat(client, model, [
                {"role": "system", "content": _CREATIVE_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url",
                         "image_url": {"url": _encode_data_uri(cutout_path)}},
                    ],
                },
            ], key)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise
            logger.info("[VLM·创意] %s 不支持图片输入，回落两段式（先识图再创作）", model)
            product_desc = _describe_product(client, key, cutout_path)
            user_text = _build_user_text(opts, description, count, product_desc)
            t0 = time.monotonic()
            data = _chat(client, model, [
                {"role": "system", "content": _CREATIVE_SYSTEM},
                {"role": "user", "content": user_text},
            ], key)

    raw = _extract_text(data)
    prompts = [p for p in _parse_prompts(raw) if p]
    if not prompts:
        raise RuntimeError(f"创意提示词解析失败：{raw[:300]}")
    # 不足 count 条时循环补齐，多则截断
    prompts = (prompts * ((count // len(prompts)) + 1))[:count]
    logger.info(
        "[VLM·创意] 耗时 %.1fs，usage=%s，%d 条提示词:\n%s",
        time.monotonic() - t0, data.get("usage"), len(prompts),
        "\n".join(f"  {i + 1}. {p}" for i, p in enumerate(prompts)),
    )
    return prompts
