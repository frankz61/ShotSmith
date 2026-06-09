"""访问鉴权：密码换签名令牌 + 请求令牌校验。

无状态方案——令牌为 `exp.hmac_sha256(secret, exp)`，服务端不存会话：
- /auth/login 校验密码后用 make_token 签发；
- 受保护路由用 require_auth 依赖校验 Bearer 令牌（或 ?token= 查询参数，
  供 <a> 下载、<img> 等无法设置请求头的场景）。

仅依赖标准库 hmac/hashlib，不引入额外依赖。
"""
import base64
import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Query

from app.core.config import settings


def _sign(msg: str) -> str:
    digest = hmac.new(settings.auth_secret.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def make_token(ttl: int | None = None) -> tuple[str, int]:
    """签发令牌，返回 (token, expires_in_seconds)。"""
    ttl = int(ttl or settings.auth_token_ttl)
    exp = int(time.time()) + ttl
    payload = str(exp)
    return f"{payload}.{_sign(payload)}", ttl


def verify_token(token: str) -> bool:
    """校验签名与有效期；任一不符返回 False（不抛异常）。"""
    try:
        payload, sig = token.rsplit(".", 1)
        exp = int(payload)
    except (ValueError, AttributeError):
        return False
    if not hmac.compare_digest(sig, _sign(payload)):
        return False
    return exp > int(time.time())


def check_password(password: str) -> bool:
    """常量时间比对访问密码。"""
    return hmac.compare_digest(password or "", settings.access_password)


def require_auth(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    """FastAPI 依赖：校验 Bearer 令牌或 ?token= 查询参数。"""
    if not settings.auth_enabled:
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    candidate = bearer or (token or "")
    if not candidate or not verify_token(candidate):
        raise HTTPException(status_code=401, detail="未授权或登录已过期")
