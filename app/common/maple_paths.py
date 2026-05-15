"""Shared ``sys.path`` bootstrap for Streamlit entrypoints under ``app/``."""

# - Streamlit 페이지(``app/`` 하위)들은 각각이 독립적인 진입점이라
#   PYTHONPATH 가 자동으로 잡히지 않는 경우가 많다.
# - 이 모듈은 모든 페이지에서 호출해 ``app.*`` / ``src.*`` import 가
#   안정적으로 동작하도록 sys.path 를 보정한다.

from __future__ import annotations

import sys
from pathlib import Path


def ensure_app_import_paths() -> None:
    """Register project root and ``src`` so ``app.*`` and ``src.*`` imports work."""
    # 현재 파일 기준 두 단계 상위 디렉터리 = 프로젝트 루트
    # (app/common/maple_paths.py → parents[2] = project root)
    project_root = Path(__file__).resolve().parents[2]
    # src 디렉터리(에이전트, RAG 등 핵심 로직)도 import 가능하게 만든다
    src_root = project_root / "src"
    # 이미 등록되어 있다면 건너뛰고, 없으면 sys.path 맨 앞에 삽입
    # (맨 앞에 두어야 다른 패키지 충돌이 있을 때 우선순위를 가진다)
    for path in (project_root, src_root):
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)
