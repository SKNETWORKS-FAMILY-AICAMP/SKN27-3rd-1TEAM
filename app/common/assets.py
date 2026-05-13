from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"

MIME_TYPES = {
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".mp3": "audio/mpeg",
    ".otf": "font/otf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".webp": "image/webp",
}


def asset_path(filename: str) -> Path:
    return ASSET_DIR / filename


@lru_cache(maxsize=64)
def _cached_path_to_data_uri(
    path: str,
    mtime_ns: int,
    default_mime: str,
) -> str:
    file_path = Path(path)
    mime_type = MIME_TYPES.get(file_path.suffix.lower(), default_mime)
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def path_to_data_uri(
    path: Path,
    default_mime: str = "application/octet-stream",
) -> str:
    if not path.exists():
        return ""

    stat = path.stat()
    return _cached_path_to_data_uri(str(path), stat.st_mtime_ns, default_mime)
