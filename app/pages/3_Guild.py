from __future__ import annotations

from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

from app.common.maple_stub_page import render_stub_page  # noqa: E402


render_stub_page(
    page_title="History",
    page_icon="H",
    title="History",
    body="최근 상담 기록과 추천 흐름을 확인하는 페이지입니다.",
    active_menu_key="history",
)
