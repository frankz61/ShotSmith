"""阿里云 OSS 适配：服务端签名（V4）直传 + 预签名访问 + worker 产物同步。

object key 与本地相对路径一致（tasks/<task_id>/…），DB 只存 key，
预签名 URL 有时效、按需实时生成，不落库。
oss2 延迟导入：storage_backend=local 时无需安装该依赖。
"""
import functools
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return settings.storage_backend == "oss"


@functools.lru_cache(maxsize=2)
def _bucket(internal: bool = False):
    import oss2

    auth = oss2.AuthV4(settings.oss_access_key_id, settings.oss_access_key_secret)
    endpoint = (settings.oss_internal_endpoint if internal else "") or settings.oss_endpoint
    # 绑定自有域名（CNAME）时 host 不带 bucket 前缀，须告知 SDK，否则会签出
    # https://<bucket>.<自有域名>/ 这种不存在的地址
    is_cname = "aliyuncs.com" not in endpoint
    return oss2.Bucket(
        auth, endpoint, settings.oss_bucket, region=settings.oss_region, is_cname=is_cname
    )


def sign_get(key: str, thumb: bool = False) -> str:
    """预签名 GET 地址（直连 OSS，绕过应用服务器）。

    thumb=True 附带 x-oss-process 实时缩放参数（参数纳入签名），列表场景省流量提速。
    """
    params = {"x-oss-process": settings.oss_thumb_process} if thumb else None
    return _bucket().sign_url("GET", key, settings.oss_url_ttl, slash_safe=True, params=params)


def sign_put(key: str, content_type: str) -> str:
    """预签名 PUT 地址（服务端签名直传）；前端 PUT 时必须携带相同 Content-Type 头。"""
    return _bucket().sign_url(
        "PUT", key, settings.oss_url_ttl, slash_safe=True, headers={"Content-Type": content_type}
    )


def upload_file(key: str, local_path) -> None:
    _bucket(internal=True).put_object_from_file(key, str(local_path))


def download_file(key: str, local_path) -> None:
    p = Path(local_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    _bucket(internal=True).get_object_to_file(key, str(p))


def delete_key(key: str) -> None:
    _bucket(internal=True).delete_object(key)


def delete_prefix(prefix: str) -> None:
    import oss2

    b = _bucket(internal=True)
    keys = [o.key for o in oss2.ObjectIterator(b, prefix=prefix)]
    for i in range(0, len(keys), 1000):     # batch_delete 单次上限 1000
        b.batch_delete_objects(keys[i : i + 1000])


def sync_task_dir(task_dir, base) -> None:
    """任务目录产物整体上传 OSS（key=相对 storage 根的路径）；跳过下载时才生成的 zip。"""
    base = Path(base).resolve()
    for p in Path(task_dir).rglob("*"):
        if p.is_file() and p.name != "package.zip":
            upload_file(p.resolve().relative_to(base).as_posix(), p)


def restore_task_dir(prefix: str, base) -> None:
    """从 OSS 拉回任务目录中本地缺失的文件（API 与 worker 不共享磁盘时打包用）。"""
    import oss2

    b = _bucket(internal=True)
    for o in oss2.ObjectIterator(b, prefix=prefix):
        dest = Path(base) / o.key
        if not dest.exists():
            download_file(o.key, dest)
