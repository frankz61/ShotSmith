"""商品参考链接信息抓取（best-effort，自动化约束的一部分）。

卖家选品通常有货源链接（如 1688 详情页）。尽力抓取页面标题与 meta 描述，
作为 VLM 生成提示词时的品类约束，避免看图误判跑偏。

1688 / 亚马逊等站点反爬严格（需登录、滑块验证），裸 HTTP 抓不到属常态：
失败一律 fail-soft 返回 None，由人工填写的描述/品类提示兜底，不阻断主流程。
"""
import html as _html
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HINT_MAX = 120  # 抓到的信息只作提示，截断防止挤占 VLM 上下文

# 反爬拦截页的典型标题，视为抓取失败
_BLOCKED_TITLES = ("验证", "登录", "captcha", "robot", "access denied", "404")


def _meta(html: str, attr: str, name: str) -> str | None:
    m = re.search(
        rf'<meta[^>]+{attr}=["\']{name}["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.I,
    ) or re.search(
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+{attr}=["\']{name}["\']',
        html, re.I,
    )
    return _html.unescape(m.group(1)).strip() if m else None


def _title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return _html.unescape(m.group(1)).strip() if m else None


def fetch_product_hint(url: str) -> str | None:
    """抓取商品页标题/描述，拼成一句话提示；任何失败返回 None。"""
    try:
        with httpx.Client(
            timeout=8.0, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            r = client.get(url)
            r.raise_for_status()
            page = r.text[:200_000]
    except Exception as e:
        logger.warning("[ProductInfo] 抓取商品链接失败（fail-soft）：%s（%s）", url, e)
        return None

    title = _meta(page, "property", "og:title") or _title(page)
    desc = _meta(page, "property", "og:description") or _meta(page, "name", "description")

    if title and any(k in title.lower() for k in _BLOCKED_TITLES):
        logger.warning("[ProductInfo] 命中反爬/无效页面，忽略：%s（title=%r）", url, title)
        return None

    parts = [p for p in (title, desc) if p]
    if not parts:
        return None
    hint = " ".join("；".join(parts).split())[:_HINT_MAX]
    logger.info("[ProductInfo] 商品链接信息：%r", hint)
    return hint
