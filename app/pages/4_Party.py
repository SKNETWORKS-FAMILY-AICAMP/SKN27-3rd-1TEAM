from __future__ import annotations

from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

from app.common.maple_stub_page import render_stub_page  # noqa: E402


render_stub_page(
    page_title="Party",
    page_icon="🐧",
    title="Party",
    body="상단 메뉴에서 다른 탭이나 Maple Guide 로 채팅 홈으로 이동할 수 있습니다.",
    active_menu_key="party",
)
