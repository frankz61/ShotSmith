"""统一产物访问地址：oss → 预签名 URL（直连 OSS 提速）；local → /files 静态路径。"""
from app.storage import oss


def file_url(rel_path: str, thumb: bool = False) -> str:
    if oss.enabled():
        return oss.sign_get(rel_path, thumb=thumb)
    return f"/files/{rel_path}"
