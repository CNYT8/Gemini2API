"""AI 生成图片的本地托管存储。

生成的图片字节存到 data/generated_images/，通过 /images/{id} 路由对外提供，
让对话接口能返回可被客户端渲染的真实 URL（base64 在多数 CLI 客户端无法显示）。
data/ 是容器的 bind-mount 持久目录，重启不丢。
"""
import os
import time
import uuid
import logging

logger = logging.getLogger(__name__)

STORE_DIR = os.path.join("data", "generated_images")
RETENTION_SECONDS = 7 * 24 * 3600  # 默认保留 7 天

_EXT_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _ensure_dir():
    os.makedirs(STORE_DIR, exist_ok=True)


def save_image(data: bytes, mime: str = "image/png") -> str:
    """保存图片字节，返回带扩展名的文件 id（如 'a1b2c3.png'）。失败抛异常。"""
    _ensure_dir()
    ext = _EXT_BY_MIME.get(mime, "png")
    fid = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(STORE_DIR, fid)
    with open(path, "wb") as f:
        f.write(data)
    return fid


def get_image_path(fid: str) -> str | None:
    """按 id 取本地路径；做基本的路径穿越防护。不存在返回 None。"""
    # 只允许文件名本身，禁止路径分隔符
    if not fid or "/" in fid or "\\" in fid or ".." in fid:
        return None
    path = os.path.join(STORE_DIR, fid)
    return path if os.path.isfile(path) else None


def content_type_for(fid: str) -> str:
    ext = fid.rsplit(".", 1)[-1].lower() if "." in fid else "png"
    for mime, e in _EXT_BY_MIME.items():
        if e == ext:
            return mime
    return "image/png"


def cleanup_old(retention_seconds: int = RETENTION_SECONDS) -> int:
    """删除超过保留期的图片，返回删除数量。"""
    if not os.path.isdir(STORE_DIR):
        return 0
    now = time.time()
    removed = 0
    for name in os.listdir(STORE_DIR):
        path = os.path.join(STORE_DIR, name)
        try:
            if os.path.isfile(path) and now - os.path.getmtime(path) > retention_seconds:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info(f"[image_store] 清理了 {removed} 张过期生成图片")
    return removed
