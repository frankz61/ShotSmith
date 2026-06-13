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
_PROMPT_MAX = 200      # 单条提示词长度保底截断（中文≤200 字符）
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

# 通用风格基调（不再按平台区分）：作为 user 消息的一部分注入，约束输出范围避免跑偏
_STYLE_HINT = (
    "场景图用于电商 listing 副图/生活方式图：真实自然的使用环境、明亮通透光线、"
    "干净不杂乱、简洁高级、贴合商品调性，突出商品使用情境。"
)


def _creative_system(text_lang: str) -> str:
    """创意场景提示词的系统指令；图中文字规则按所选语言动态生成。

    text_lang="none" 时画面禁文字；否则要求结合商品与场景，在画面合理位置
    融入贴合的该语言文字，并在提示词中写明具体文字内容与位置。
    """
    from app.core.constants import LANG_TYPO_HINTS, TEXT_LANGS

    if text_lang != "none" and text_lang in TEXT_LANGS:
        lang = TEXT_LANGS[text_lang]
        typo = LANG_TYPO_HINTS.get(text_lang, "简洁现代的属性标签文字，可配细线或小图标点缀")
        text_rule = (
            f"4) 在画面留白处以电商主图卖点标注的版式加入 1~3 条简短的{lang}产品属性词条"
            f"（每条 1~3 个单词，如『舒适透气』『大容量』对应的{lang}说法）。"
            f"文字样式必须美观时尚、贴合该国消费者审美：{typo}，"
            f"可配细线、小图标点缀，与场景色调和谐；"
            f"属性必须有依据：只能从商品图可见特征、商品描述或链接信息中提炼，"
            f"绝不臆造商品看不出来或未提及的功能（如看不出电池就不得写续航）；"
            f"词条必须是{lang}中真实存在的词，语法正确、拼写准确无误；"
            f"每条提示词必须用引号写明具体词条内容及摆放方位，且不遮挡商品主体；"
            f"不要在场景道具上加文字（招牌、标牌、包装等场景内文字一律不要）；"
            f"商品本体上原有的文字、logo、标签原样保留，不得翻译、替换、覆盖或修改；"
            f"除卖点词条外不得出现其他文字、品牌 logo、水印、价签、人脸；"
        )
    else:
        text_rule = "4) 画面中不得出现任何文字、品牌 logo、水印、价签、人脸；"
    return (
        "你是资深跨境电商视觉设计师与创意总监。用户是电商卖家，从批发平台（如 1688）选品，"
        "将商品发布到海外零售平台销售。"
        "请基于给定的商品信息，为 AI 图像生成写场景提示词。每条提示词必须是一段自然流畅的"
        "中文完整描述，参照这个范例的口吻与结构："
        "『保持参考图中的双筒望远镜不变，稳放在森林木桩上，镜身底部与粗糙树皮自然贴合，"
        "背景有绿色树林、阳光光斑和远处小鸟虚化元素，旁边搭一条摊开的地图与皮质背带，"
        "表现观鸟与户外探索的旅途瞬间，低角度平视、浅景深，暖金色侧光从左上方照来，"
        "镜片反射蓝紫光、底部投下柔和接触阴影，真实摄影风格，电商详情页场景图。』"
        "结构要素依次为："
        "① 以『保持参考图中的{具体商品名}不变』开头；"
        "② 明确的物理依托关系（稳放在/挂在/靠在哪个具体承托物上，接触处如何贴合）；"
        "③ 背景环境元素 + 1~2 件有生活气息的叙事道具（摊开的书、咖啡杯、织物、绿植等，"
        "写具体不空泛），营造『有人刚刚用过』的故事感；"
        "④ 表现的用途、生活方式或情绪；"
        "⑤ 拍摄视角与景深（平视/45°俯拍/低角度/特写微距，浅景深虚化等）；"
        "⑥ 光线方案（主光方向、色温、时段，如清晨侧光/黄金时刻暖光/柔光箱），"
        "以及商品受光细节与接触阴影（镜片反光、金属高光、织物纹理受光、底部投影）；"
        "⑦ 以『真实摄影风格，电商详情页场景图』结尾。"
        "硬性要求："
        "1) 绝不改动商品本身的形状、颜色、材质与文字细节，互动只限光影层面；"
        "2) 每条的场景方向、拍摄视角、光线方案必须明显不同（家居生活、户外自然、"
        "节日氛围、极简棚拍、质感特写、清晨窗边、黄金时刻、旅途场景、季节主题等"
        "任选组合），大胆有创意但必须贴合商品真实用途与使用情境；"
        "3) 场景元素必须贴近目标市场消费者熟悉与喜爱的生活方式、文化习惯与审美"
        "（用户给定市场偏好时务必充分体现，道具、建筑、节日、配色都要地道），"
        "环境透视、商品比例符合真实逻辑；"
        f"{text_rule}"
        "5) 每条 60~120 个汉字；"
        "6) 只输出 JSON 字符串数组（如 [\"…\",\"…\"]），不要其他解释。"
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
    from app.core.constants import LANG_MARKET_HINTS

    hints: list[str] = [_STYLE_HINT]
    # 选了图中文字语言即指向对应国家市场：场景须贴近该市场消费者熟悉喜爱的生活环境
    market = LANG_MARKET_HINTS.get(opts.get("text_lang") or "")
    if market:
        hints.append(
            f"目标市场偏好（场景选择必须充分体现）：{market}"
        )
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
    creative_system = _creative_system(opts.get("text_lang") or "none")
    with httpx.Client(timeout=settings.vlm_timeout) as client:
        # 优先单段：创意模型直接看图（细节最忠实）；纯文本模型带图会 404，回落两段式
        user_text = _build_user_text(opts, description, count, None)
        logger.info("[VLM·创意] 调用 openrouter/%s（带图），user_text=%r", model, user_text)
        t0 = time.monotonic()
        try:
            data = _chat(client, model, [
                {"role": "system", "content": creative_system},
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
                {"role": "system", "content": creative_system},
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
