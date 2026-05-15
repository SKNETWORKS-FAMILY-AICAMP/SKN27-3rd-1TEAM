"""정적 에셋(이미지/폰트/오디오)을 data URI 로 변환해 캐싱하는 유틸."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path


# 에셋 파일들이 위치한 디렉터리: ``app/assets``
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"

# 파일 확장자 → MIME 타입 매핑 테이블
# HTML 안에서 data URI 로 임베드할 때 올바른 MIME 을 지정하기 위함
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
    """에셋 디렉터리 기준 절대 경로 반환."""
    return ASSET_DIR / filename


@lru_cache(maxsize=64)
def _cached_path_to_data_uri(
    path: str,
    mtime_ns: int,
    default_mime: str,
) -> str:
    """파일 내용을 base64 로 인코딩한 data URI 를 반환(LRU 캐싱).

    mtime_ns 를 캐시 키에 포함시켜 파일이 수정되면 자동으로 새 결과를 만든다.
    """
    file_path = Path(path)
    # 확장자 기반으로 MIME 추정, 못 찾으면 호출자가 준 기본값 사용
    mime_type = MIME_TYPES.get(file_path.suffix.lower(), default_mime)
    # 바이너리 → base64 ASCII 문자열로 변환
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def path_to_data_uri(
    path: Path,
    default_mime: str = "application/octet-stream",
) -> str:
    """파일 경로를 받아 data URI 문자열로 변환.

    파일이 존재하지 않으면 빈 문자열 반환.
    내부적으로는 ``_cached_path_to_data_uri`` 를 통해 캐싱된다.
    """
    if not path.exists():
        return ""

    # mtime 을 캐시 키에 함께 넣어 파일 갱신 시 캐시가 무효화되도록 함
    stat = path.stat()
    return _cached_path_to_data_uri(str(path), stat.st_mtime_ns, default_mime)
