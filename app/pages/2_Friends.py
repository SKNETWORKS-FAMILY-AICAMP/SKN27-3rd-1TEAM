from __future__ import annotations

from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

from app.common.maple_stub_page import render_stub_page  # noqa: E402


render_stub_page(
    page_title="Models",
    page_icon="AI",
    title="Models",
    body="Maple Guide에서 사용할 상담 모델과 안내 모드를 준비하는 페이지입니다.",
    active_menu_key="models",
)
