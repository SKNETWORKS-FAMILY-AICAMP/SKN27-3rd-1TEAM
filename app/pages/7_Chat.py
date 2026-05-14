"""Chat 탭 페이지: 메인 채팅 화면을 사이드바 메뉴에서도 진입 가능하게 노출."""

from __future__ import annotations

import streamlit as st

# app 패키지 import 가능하도록 sys.path 보정
from app.common.maple_paths import ensure_app_import_paths

ensure_app_import_paths()

# 메인 챗 페이지의 설정(PAGE_CONFIG)과 렌더 함수를 가져온다
from app.maple_chat import (  # noqa: E402
    PAGE_CONFIG,
    render_chat_app,
)

# 사이드바를 항상 접힌 상태로 시작하도록 PAGE_CONFIG 를 일부 덮어쓴다
st.set_page_config(**{**PAGE_CONFIG, "initial_sidebar_state": "collapsed"})
# 실제 채팅 UI 렌더링
render_chat_app()
