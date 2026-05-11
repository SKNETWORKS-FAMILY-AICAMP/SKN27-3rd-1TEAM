from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


# CSS와 커스텀 HTML 렌더러에서 함께 사용하는 이미지/폰트 경로입니다.
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
ASSISTANT_AVATAR_PATH = ASSET_DIR / "assistant_avatar.png"
USER_AVATAR_PATH = ASSET_DIR / "user_avatar.png"
SEND_ICON_PATH = ASSET_DIR / "send_icon.png"
BACKGROUND_PATH = ASSET_DIR / "background_home.png"
CHAT_BACKGROUND_PATH = ASSET_DIR / "chat_background.png"
ITEM_BOX_PATH = ASSET_DIR / "item_box.png"
HOME_BUTTON_PATH = ASSET_DIR / "home_button.png"
HOME_BADGE_PATH = ASSET_DIR / "home_button2.png"
MAPLESTORY_BOLD_PATH = ASSET_DIR / "Maplestory-Bold.ttf"
MAPLESTORY_LIGHT_PATH = ASSET_DIR / "Maplestory-Light.ttf"


def image_to_data_uri(path: Path) -> str:
    """로컬 asset을 CSS/HTML에 바로 넣을 수 있는 data URI로 변환합니다."""
    # 이미지나 폰트가 없어도 Streamlit 앱이 죽지 않도록 빈 값을 반환합니다.
    # 이 경우 CSS에는 비어 있는 url 값이 들어갑니다.
    if not path.exists():
        return ""

    # 파일 확장자를 기준으로 간단한 MIME 타입을 정합니다.
    suffix = path.suffix.lower()
    if suffix == ".png":
        mime = "image/png"
    elif suffix in {".ttf", ".otf"}:
        mime = "font/ttf"
    else:
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def get_maple_chat_css() -> str:
    """이미지/폰트 치환값이 들어간 전체 CSS 문자열을 만듭니다."""
    # Streamlit에서 별도 정적 파일 라우팅 없이 렌더링할 수 있도록
    # 로컬 이미지와 폰트를 data URI로 변환합니다.
    send_icon = image_to_data_uri(SEND_ICON_PATH)
    background_image = image_to_data_uri(BACKGROUND_PATH)
    chat_background_image = image_to_data_uri(CHAT_BACKGROUND_PATH)
    home_button = image_to_data_uri(HOME_BUTTON_PATH)
    home_badge = image_to_data_uri(HOME_BADGE_PATH)
    maple_bold = image_to_data_uri(MAPLESTORY_BOLD_PATH)
    maple_light = image_to_data_uri(MAPLESTORY_LIGHT_PATH)
    return """
<style>
/* 폰트 선언: 앱 전체에서 사용할 번들 MapleStory 폰트를 불러옵니다. */
@font-face {
    font-family: "MaplestoryLight";
    src: url("__MAPLE_LIGHT__") format("truetype");
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}

@font-face {
    font-family: "MaplestoryBold";
    src: url("__MAPLE_BOLD__") format("truetype");
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}

/* 디자인 토큰: 홈, 채팅, 내비게이션에서 함께 쓰는 색상입니다. */
:root {
    --bg: #020202;
    --panel: rgba(26, 24, 23, 0.95);
    --panel-soft: rgba(33, 31, 30, 0.86);
    --text: #f5f0ea;
    --muted: #847d78;
    --orange: #ffbd7a;
    --orange-strong: #ffc889;
    --green: #21e653;
    --pink: #f096b6;
    --line: rgba(255, 190, 125, 0.42);
    --violet: #7869ff;
}

/* Streamlit 앱 기본값: 전체 배경과 기본 폰트를 지정합니다. */
html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

/* 중첩된 Streamlit 요소도 MapleStory 기본 폰트를 따르도록 강제합니다. */
.stApp,
.stApp *,
[data-testid="stAppViewContainer"] * {
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
}

/* 홈 화면 배경 이미지 레이어입니다. 채팅/서브 페이지에서는 아래 규칙으로 숨깁니다. */
[data-testid="stAppViewContainer"]::before {
    /* 홈 배경: height는 이미지 노출 높이, gradient와 position은 톤과 크롭을 조정합니다. */
    content: "";
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 78vh;
    pointer-events: none;
    background:
        linear-gradient(180deg, rgba(0, 0, 0, 0.18) 0%, rgba(0, 0, 0, 0.24) 32%, rgba(2, 2, 2, 0.92) 100%),
        linear-gradient(90deg, rgba(0, 0, 0, 0.68) 0%, rgba(0, 0, 0, 0.08) 28%, rgba(0, 0, 0, 0.1) 72%, rgba(0, 0, 0, 0.7) 100%),
        url("__BACKGROUND_IMAGE__") center 42px / cover no-repeat;
    z-index: 0;
}

/* 앱 화면 전체를 감싸는 보라색 테두리입니다. */
[data-testid="stAppViewContainer"]::after {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    border: 1.5px solid var(--violet);
    border-radius: 6px;
    box-shadow: inset 0 0 0 1px rgba(120, 105, 255, 0.2);
    z-index: 9999;
}

/* Streamlit 페이지 컨테이너 초기화: 전체 화면 기준 커스텀 배치를 가능하게 합니다. */
.block-container {
    max-width: none !important;
    padding: 0 !important;
}

/* 커스텀 UI와 겹칠 수 있는 Streamlit 기본 UI를 숨깁니다. */
header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="collapsedControl"],
#MainMenu,
footer {
    display: none !important;
}

/* Streamlit 고정 하단 입력 영역의 기본 배경을 제거합니다. */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div {
    background: transparent !important;
    box-shadow: none !important;
}

/* 이 앱에서 보이는 Streamlit 생성 제목/장식 캐시 클래스를 숨깁니다. */
.st-emotion-cache-1dp5vir,
.st-emotion-cache-10trblm,
.st-emotion-cache-zt5igj {
    display: none !important;
}

/* 전체 높이 레이아웃이 필요한 페이지에서 쓰는 선택적 앱 기본 래퍼입니다. */
.maple-shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    color: var(--text);
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-weight: normal;
}

/* 고정 상단 내비게이션 배경 띠입니다. */
.maple-nav-bg {
    /* 상단 메뉴 배경: height/background/z-index로 메뉴 바 프레임을 조정합니다. */
    position: fixed;
    top: 1px;
    left: 1px;
    right: 1px;
    height: 4.1rem;
    background: linear-gradient(180deg, rgba(18, 15, 13, 0.98), rgba(8, 7, 6, 0.94));
    z-index: 20;
}

/* 페이지에서 렌더링할 경우 표시되는 작은 브랜드 텍스트입니다. */
.maple-brand-label {
    position: fixed;
    top: 1.14rem;
    left: 1.55rem;
    z-index: 35;
    color: var(--orange);
    font-size: 0.98rem;
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal;
    text-shadow: 0 0 10px rgba(255, 178, 107, 0.35);
}

/* 중앙 메뉴 버튼을 감싸는 Streamlit key 기반 내비게이션 컨테이너입니다. */
.st-key-maple-nav-bar {
    /* 상단 메뉴 그룹: top/width로 메뉴 항목 위치와 폭을 조정합니다. */
    position: fixed !important;
    top: 0.55rem !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    width: 24rem !important;
    z-index: 40 !important;
}

/* 큰 홈 로고 버튼을 감싸는 Streamlit key 기반 컨테이너입니다. */
.st-key-maple-brand-bar {
    /* 메인 홈 로고 이미지 그룹: top/width로 중앙 로고 위치와 크기를 조정합니다. */
    position: fixed !important;
    top: 39vh !important;
    left: 50% !important;
    width: min(56rem, calc(100vw - 2rem)) !important;
    transform: translate(-50%, -50%) !important;
    z-index: 45 !important;
}

/* 좌상단 작은 홈 배지를 감싸는 Streamlit key 기반 컨테이너입니다. */
.st-key-maple-home-badge {
    /* 작은 홈 아이콘: top/left/width로 클릭 가능한 홈 아이콘 위치와 크기를 조정합니다. */
    position: fixed !important;
    top: 0.24rem !important;
    left: 0.58rem !important;
    width: 1.45rem !important;
    z-index: 90 !important;
}

/* 내비게이션/로고 버튼 컬럼 간격을 촘촘하게 유지합니다. */
.st-key-maple-nav-bar [data-testid="stHorizontalBlock"],
.st-key-maple-brand-bar [data-testid="stHorizontalBlock"] {
    gap: 0.4rem !important;
}

/* 상단 메뉴 버튼과 홈 로고 버튼에 공통으로 적용하는 초기화입니다. */
.st-key-maple-nav-bar button,
.st-key-maple-brand-bar button {
    /* 메뉴/로고 버튼 공통 초기화: height/padding/font-size로 전체 버튼 크기를 조정합니다. */
    min-height: 2.2rem !important;
    height: 2.2rem !important;
    padding: 0 0.38rem !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    color: #8c8580 !important;
    font-size: 0.66rem !important;
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

/* 홈 배지 버튼의 텍스트를 이미지로 대체합니다. */
.st-key-maple-home-badge button {
    /* 작은 홈 아이콘 버튼 이미지: width/height/background-size로 버튼 이미지를 조정합니다. */
    width: 1.45rem !important;
    min-width: 1.45rem !important;
    height: 1.45rem !important;
    min-height: 1.45rem !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 0 !important;
    color: transparent !important;
    font-size: 0 !important;
    background: url("__HOME_BADGE__") center / contain no-repeat !important;
    box-shadow: none !important;
}

/* 이미지만 보이는 홈 배지 내부 텍스트를 숨깁니다. */
.st-key-maple-home-badge button * {
    color: transparent !important;
    font-size: 0 !important;
}

/* 이미지/메뉴 버튼 내부에는 굵은 폰트를 사용합니다. */
.st-key-maple-nav-bar button *,
.st-key-maple-brand-bar button * {
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

/* 큰 홈 로고 버튼의 텍스트를 이미지로 대체합니다. */
.st-key-maple-brand-bar button {
    /* 큰 홈 로고 이미지: width/height/background-size로 중앙 로고 크기를 조정합니다. */
    justify-content: center !important;
    width: min(56rem, calc(100vw - 2rem)) !important;
    min-height: 16rem !important;
    height: 16rem !important;
    color: transparent !important;
    font-size: 0 !important;
    font-weight: normal !important;
    text-shadow: none !important;
    background-image: url("__HOME_BUTTON__") !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    background-size: contain !important;
}

/* 큰 로고 버튼 내부 텍스트를 숨깁니다. */
.st-key-maple-brand-bar button * {
    color: transparent !important;
    font-size: 0 !important;
}

/* 내비게이션 마우스 오버 색상입니다. */
.st-key-maple-nav-bar button:hover {
    color: var(--orange-strong) !important;
}

/* 활성 내비게이션 상태입니다. */
.st-key-maple-nav-bar .st-key-nav_chat button,
.st-key-maple-nav-bar button[kind="primary"] {
    color: var(--orange-strong) !important;
    position: relative;
}

/* 활성 내비게이션 밑줄입니다. */
.st-key-maple-nav-bar .st-key-nav_chat button::after,
.st-key-maple-nav-bar button[kind="primary"]::after {
    content: "";
    position: absolute;
    left: 50%;
    bottom: 0.18rem;
    width: 2rem;
    height: 2px;
    transform: translateX(-50%);
    border-radius: 999px;
    background: var(--orange-strong);
}

/* 홈 화면에서 입력 영역을 시각적으로 중앙에 맞추는 hero 영역입니다. */
.maple-hero {
    min-height: calc(100vh - 6.1rem);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4.1rem 1.25rem 8.1rem;
    transform: none;
}

/* 홈 제목은 현재 숨겨져 있으며, 클래스는 레이아웃 기준점으로 남겨둡니다. */
.maple-title {
    display: none;
}

/* 제목에 생성될 수 있는 pseudo-content를 비활성화합니다. */
.maple-title::before {
    content: none;
}

/* 고정 입력창이 보이는 위치에 확보해두는 보이지 않는 공간입니다. */
.maple-input-space {
    /* 홈 입력창 spacer: 홈 입력 영역 주변의 시각적 공간을 확보합니다. */
    width: min(47rem, calc(100vw - 2rem));
    height: 4.3rem;
}

/* 홈과 채팅에서 함께 쓰는 Streamlit 채팅 입력창 기본 래퍼입니다. */
div[data-testid="stChatInput"] {
    position: relative !important;
    top: auto !important;
    left: auto !important;
    bottom: auto !important;
    transform: none !important;
    width: 100% !important;
    z-index: 120 !important;
}

/* 홈/기본 입력창 외곽: 테두리와 은은한 투명 빛 효과를 담당합니다. */
div[data-testid="stChatInput"] > div {
    /* 기본/홈 입력창 외곽: 테두리/둥근 정도/배경/빛 효과로 메인 입력창 외형을 조정합니다. */
    border: 1px solid rgba(255, 255, 255, 0.04) !important;
    border-radius: 8px !important;
    background: rgba(2, 2, 2, 0.08) !important;
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.03),
        0 0 18px rgba(255, 178, 107, 0.16) !important;
}

/* 입력창 내부의 Streamlit/BaseWeb 중첩 배경을 투명하게 제거합니다. */
div[data-testid="stChatInput"] div,
div[data-testid="stChatInput"] [data-baseweb="textarea"],
div[data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: transparent !important;
}

/* 홈/기본 입력창 textarea 크기와 타이포그래피입니다. */
div[data-testid="stChatInput"] textarea {
    /* 기본/홈 입력 텍스트 영역: height, padding, 글자 크기, placeholder 간격을 조정합니다. */
    min-height: 3.15rem !important;
    height: 3.15rem !important;
    padding: 0.95rem 4.1rem 0.7rem 1.35rem !important;
    color: #efe9e5 !important;
    font-size: 0.83rem !important;
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
    background: transparent !important;
    scrollbar-width: none !important;
}

/* 홈/기본 placeholder 색상입니다. */
div[data-testid="stChatInput"] textarea::placeholder {
    color: #6f6864 !important;
    opacity: 1 !important;
}

/* 작은 입력창 디자인을 위해 textarea 스크롤바를 숨깁니다. */
div[data-testid="stChatInput"] textarea::-webkit-scrollbar {
    display: none !important;
}

/* 홈/기본 전송 버튼 이미지와 클릭 영역입니다. */
div[data-testid="stChatInput"] button {
    /* 홈 입력창 전송 버튼: 메인 페이지의 크기, 위치, 아이콘을 여기서 조정합니다. */
    position: relative !important;
    width: 3.02rem !important;
    height: 2.42rem !important;
    margin: 0.33rem 0.42rem 0 0 !important;
    border: 0 !important;
    border-radius: 6px !important;
    background-color: transparent !important;
    background-image: url("__SEND_ICON__") !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    background-size: 2rem 2rem !important;
    box-shadow: none !important;
    cursor: pointer !important;
    pointer-events: auto !important;
    z-index: 125 !important;
}

/* 커스텀 이미지가 보이도록 Streamlit 기본 전송 아이콘을 숨깁니다. */
div[data-testid="stChatInput"] button svg {
    opacity: 0 !important;
}

/* 홈 프롬프트 칩 행 컨테이너입니다. */
.st-key-maple-chip-row {
    /* 홈 프롬프트 칩 컨테이너: top/width로 3개 프롬프트 버튼 위치와 폭을 조정합니다. */
    position: fixed !important;
    top: calc(75vh - 37px) !important;
    left: 50% !important;
    bottom: auto !important;
    transform: translateX(-50%) !important;
    width: min(47rem, calc(100vw - 2rem)) !important;
    z-index: 110 !important;
}

/* 홈 프롬프트 칩 3개 사이의 간격입니다. */
.st-key-maple-chip-row [data-testid="stHorizontalBlock"] {
    gap: 1rem !important;
}

/* 프롬프트 칩 버튼의 공통 형태와 텍스트 동작입니다. */
.st-key-maple-chip-row button {
    /* 홈 프롬프트 칩 형태: height/padding/radius/font-size로 칩 외형을 조정합니다. */
    min-height: 1.72rem !important;
    height: 1.72rem !important;
    padding: 0 0.72rem !important;
    border-radius: 999px !important;
    background: rgba(15, 14, 14, 0.78) !important;
    font-size: 0.56rem !important;
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
    letter-spacing: 0.02em !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}

/* 프롬프트 칩 내부 텍스트 폰트입니다. */
.st-key-maple-chip-row button * {
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

/* 홈 미리보기 메시지 폰트 초기화입니다. */
.maple-message,
.maple-message * {
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

/* Story 칩 강조 색상입니다. */
.st-key-chip_story button {
    color: #ffadc6 !important;
    border: 1px solid rgba(255, 137, 177, 0.55) !important;
    box-shadow: 0 0 12px rgba(255, 137, 177, 0.17) !important;
}

/* Debug 칩 강조 색상입니다. */
.st-key-chip_debug button {
    color: #1ffa4f !important;
    border: 1px solid rgba(27, 240, 83, 0.55) !important;
    box-shadow: 0 0 12px rgba(27, 240, 83, 0.17) !important;
}

/* Quantum 칩 강조 색상입니다. */
.st-key-chip_quantum button {
    color: #ffcb81 !important;
    border: 1px solid rgba(255, 189, 103, 0.55) !important;
    box-shadow: 0 0 12px rgba(255, 189, 103, 0.17) !important;
}

/* 선택적으로 표시할 수 있는 홈 메시지 미리보기 패널입니다. */
.maple-message-panel {
    /* 홈 메시지 미리보기 패널: 홈에서 미리보기를 표시할 때 top/width/max-height를 조정합니다. */
    position: fixed;
    left: 50%;
    top: 4.7rem;
    transform: translateX(-50%);
    width: min(47rem, calc(100vw - 2rem));
    max-height: calc(50vh - 7.5rem);
    overflow: auto;
    z-index: 18;
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 189, 103, 0.4) transparent;
}

/* 선택적으로 표시할 수 있는 홈 메시지 미리보기 말풍선입니다. */
.maple-message {
    /* 홈 메시지 미리보기 말풍선: padding/radius/background/font-size를 여기서 조정합니다. */
    width: fit-content;
    max-width: min(37rem, 88%);
    margin: 0.4rem 0;
    padding: 0.72rem 0.9rem;
    border: 1px solid rgba(255, 189, 103, 0.25);
    border-radius: 8px;
    background: rgba(20, 19, 18, 0.86);
    color: #e8e1dd;
    line-height: 1.55;
    font-size: 0.86rem;
}

/* 사용자 미리보기 메시지 정렬과 색상입니다. */
.maple-message.user {
    margin-left: auto;
    border-color: rgba(255, 189, 103, 0.45);
    background: rgba(53, 36, 24, 0.9);
}

/* 어시스턴트 미리보기 메시지 정렬입니다. */
.maple-message.assistant {
    margin-right: auto;
}

/* 채팅 페이지에서는 홈 배경 레이어를 숨깁니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker)::before {
    display: none;
}

/* 서브 페이지에서는 홈 배경 레이어를 숨깁니다. */
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker)::before {
    display: none;
}

/* 채팅 페이지에서는 큰 홈 로고를 숨깁니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .st-key-maple-brand-bar {
    display: none !important;
}

/* 서브 페이지에서는 큰 홈 로고를 숨깁니다. */
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-brand-bar {
    display: none !important;
}

/* 채팅 페이지에서는 작은 홈 배지를 보이게 유지합니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .st-key-maple-home-badge {
    display: block !important;
}

/* 서브 페이지에서는 작은 홈 배지를 보이게 유지합니다. */
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-home-badge {
    display: block !important;
}

/* 채팅 페이지의 고정 배경 캔버스와 대화 영역입니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .maple-chat-page {
    /* 채팅 페이지 캔버스: top/bottom/padding/background로 채팅 영역 크기를 조정합니다. */
    position: fixed;
    top: 4.1rem;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 12;
    padding: 1.25rem max(1rem, calc((100vw - 52rem) / 2));
    overflow: hidden;
    background:
        radial-gradient(circle at 50% 0%, rgba(255, 180, 105, 0.08), transparent 26rem),
        linear-gradient(180deg, rgba(2, 2, 2, 0.1) 0%, rgba(2, 2, 2, 0.44) 100%),
        url("__CHAT_BACKGROUND_IMAGE__") center / cover no-repeat,
        #020202;
}

.maple-chat-thread {
    /* 채팅 스택 동작: justify-content는 메시지 하단 정렬, padding은 내부 여백을 조정합니다. */
    position: relative;
    z-index: 14;
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    overflow-y: auto;
    padding: 0.25rem 0 7.2rem;
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 189, 103, 0.45) transparent;
}

/* 아바타와 말풍선을 함께 담는 채팅 메시지 한 줄입니다. */
.maple-chat-row {
    /* 채팅 행 간격: gap은 아바타와 말풍선 사이, margin은 메시지 사이 거리입니다. */
    display: flex;
    align-items: flex-end;
    gap: 0.55rem;
    margin: 0.55rem 0;
}

/* 사용자 메시지는 행 방향을 뒤집어 오른쪽에 표시합니다. */
.maple-chat-row.user {
    flex-direction: row-reverse;
    justify-content: flex-start;
}

/* 어시스턴트 메시지는 왼쪽 정렬을 유지합니다. */
.maple-chat-row.assistant {
    justify-content: flex-start;
}

/* 각 채팅 말풍선 옆에 표시되는 아바타 이미지입니다. */
.maple-chat-avatar {
    /* 채팅 프로필 아바타: width/height/radius/border로 프로필 이미지를 스타일링합니다. */
    width: 2.15rem;
    height: 2.15rem;
    flex: 0 0 2.15rem;
    border-radius: 8px;
    object-fit: cover;
    border: 1px solid rgba(255, 190, 125, 0.25);
    background: rgba(255, 255, 255, 0.05);
}

/* 채팅 말풍선의 공통 타이포그래피와 형태입니다. */
.maple-chat-bubble {
    /* 채팅 말풍선 본문: max-width/padding/radius/background/font-size를 조정합니다. */
    width: fit-content;
    max-width: min(38rem, 86%);
    margin: 0;
    padding: 0.78rem 0.95rem;
    border: 1px solid rgba(255, 190, 125, 0.28);
    border-radius: 8px;
    background: rgba(22, 20, 20, 0.9);
    color: #f3eee9;
    line-height: 1.55;
    font-size: 0.9rem;
}

/* 사용자 말풍선 색상 처리입니다. */
.maple-chat-bubble.user {
    border-color: rgba(33, 230, 83, 0.28);
    background: rgba(19, 44, 29, 0.9);
}

/* 어시스턴트 말풍선 색상 처리입니다. */
.maple-chat-bubble.assistant {
    border-color: rgba(255, 190, 125, 0.28);
}

/* 표시할 대화가 없을 때 보여주는 빈 상태 문구입니다. */
.maple-chat-empty {
    margin-top: 28vh;
    color: rgba(245, 240, 234, 0.55);
    text-align: center;
    font-size: 0.9rem;
}

/* 채팅 페이지에서만 보이는 장식용 item box 오버레이입니다. */
.maple-chat-item-box {
    position: fixed;
    right: max(-7rem, calc((100vw - 72rem) / 2));
    bottom: 5.15rem;
    width: min(42rem, 58vw);
    max-height: calc(100vh - 10rem);
    object-fit: contain;
    object-position: right bottom;
    pointer-events: none;
    z-index: 13;
}

/* 모바일 화면의 내비게이션, 칩, 홈 제목 간격 보정입니다. */
@media (max-width: 640px) {
    /* 좁은 화면에서도 브랜드 라벨을 읽을 수 있게 조정합니다. */
    .maple-brand-label {
        left: 0.8rem;
        font-size: 0.82rem;
    }

    /* 모바일에서 중앙 내비게이션 그룹 폭을 줄입니다. */
    .st-key-maple-nav-bar {
        width: 17.5rem !important;
        top: 0.72rem !important;
    }

    /* 모든 메뉴 항목이 들어가도록 내비게이션 버튼을 줄입니다. */
    .st-key-maple-nav-bar button {
        font-size: 0.56rem !important;
        padding: 0 0.16rem !important;
    }

    /* 제목을 다시 표시할 경우를 위한 기존 제목 간격 기준점입니다. */
    .maple-title {
        margin-bottom: 2rem;
    }

    /* 작은 화면에서 칩 사이 간격을 줄입니다. */
    .st-key-maple-chip-row [data-testid="stHorizontalBlock"] {
        gap: 0.35rem !important;
    }

    /* 작은 화면에서 칩 텍스트와 패딩을 더 작게 만듭니다. */
    .st-key-maple-chip-row button {
        padding: 0 0.45rem !important;
        font-size: 0.52rem !important;
    }

    /* 좁은 화면에서는 말풍선을 가리지 않도록 item box를 숨깁니다. */
    .maple-chat-item-box {
        display: none;
    }
}

/* 홈 화면의 고정 Streamlit 하단 영역 위치입니다. */
[data-testid="stBottom"] {
    position: fixed !important;
    top: calc(75vh - 131px) !important;
    bottom: auto !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 120 !important;
    transform: none !important;
}

/* 홈 화면 고정 입력창의 폭과 중앙 정렬입니다. */
[data-testid="stBottomBlockContainer"] {
    position: fixed !important;
    top: calc(75vh - 131px) !important;
    bottom: auto !important;
    left: 50% !important;
    right: auto !important;
    width: min(47rem, calc(100vw - 2rem)) !important;
    max-width: min(47rem, calc(100vw - 2rem)) !important;
    padding: 0 !important;
    transform: translateX(-50%) !important;
    z-index: 130 !important;
}

/* Streamlit 하단 블록이 입력창 폭을 제한하지 않도록 합니다. */
[data-testid="stBottomBlockContainer"] > div {
    width: 100% !important;
    max-width: none !important;
    padding: 0 !important;
}

/* 하단에 붙는 채팅 입력창의 공통 위치 초기화입니다. */
[data-testid="stBottom"] div[data-testid="stChatInput"],
div[data-testid="stChatInput"] {
    position: relative !important;
    top: auto !important;
    bottom: auto !important;
    left: auto !important;
    width: 100% !important;
    transform: none !important;
}

/* Streamlit CSS보다 우선 적용되도록 뒤쪽에 한 번 더 둔 칩 위치 규칙입니다. */
.st-key-maple-chip-row {
    position: fixed !important;
    top: calc(75vh - 37px) !important;
    bottom: auto !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
}

/* 제목/로고/내비게이션 요소에 굵은 폰트를 적용하는 덮어쓰기 규칙입니다. */
.maple-title,
.maple-title *,
.st-key-maple-brand-bar button,
.st-key-maple-brand-bar button *,
.st-key-maple-nav-bar button,
.st-key-maple-nav-bar button * {
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

/* 일반 앱 텍스트와 칩 라벨에 얇은 폰트를 적용하는 덮어쓰기 규칙입니다. */
.stApp textarea,
.stApp input,
.stApp p,
.stApp span,
.maple-message,
.maple-message *,
.st-key-maple-chip-row button,
.st-key-maple-chip-row button * {
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

/* 이미지 기반 큰 홈 로고 버튼 내부 텍스트를 숨깁니다. */
.st-key-maple-brand-bar button,
.st-key-maple-brand-bar button *,
.st-key-maple-brand-bar button p,
.st-key-maple-brand-bar button span {
    color: transparent !important;
    font-size: 0 !important;
}

/* 큰 홈 로고 이미지에 대한 후순위 덮어쓰기 규칙입니다. */
.st-key-maple-brand-bar button {
    background-image: url("__HOME_BUTTON__") !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    background-size: contain !important;
}

/* 이미지 기반 작은 홈 배지 내부 텍스트를 숨깁니다. */
.st-key-maple-home-badge button,
.st-key-maple-home-badge button *,
.st-key-maple-home-badge button p,
.st-key-maple-home-badge button span {
    color: transparent !important;
    font-size: 0 !important;
}

/* 채팅 페이지 입력창 래퍼: 입력창을 하단 중앙 근처에 배치합니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottom"],
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottomBlockContainer"] {
    /* 채팅 페이지 입력창 래퍼: 전체 입력 바 폭과 하단 위치를 여기서 조정합니다. */
    position: fixed !important;
    top: auto !important;
    bottom: 1rem !important;
    left: 50% !important;
    right: auto !important;
    width: min(calc(36rem + 30px), calc(100vw - 3rem)) !important;
    max-width: min(calc(36rem + 30px), calc(100vw - 3rem)) !important;
    padding: 0 !important;
    transform: translateX(-50%) !important;
    background: transparent !important;
    box-shadow: none !important;
    z-index: 130 !important;
}

/* 채팅 입력창 주변 Streamlit 래퍼의 그림자를 제거합니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottom"] *,
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottomBlockContainer"] * {
    box-shadow: none !important;
}

/* 채팅 페이지 입력창 최상위 요소를 배경 이미지 위에서 투명하게 유지합니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] {
    position: relative !important;
    width: 100% !important;
    background: transparent !important;
}

/* 채팅 페이지 둥근 입력창 테두리와 glow입니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] > div {
    /* 채팅 페이지 입력창 테두리/배경: outline, glow, 바 높이를 여기서 조정합니다. */
    min-height: 3.07rem !important;
    border: 2px solid rgba(255, 176, 111, 0.68) !important;
    border-radius: 999px !important;
    background: rgba(2, 2, 2, 0.08) !important;
    box-shadow:
        0 0 0 1px rgba(255, 210, 160, 0.1),
        0 0 14px rgba(255, 176, 111, 0.26) !important;
}

/* 채팅 페이지 textarea 간격, 글자 크기, caret 색상입니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] textarea {
    /* 채팅 페이지 텍스트 필드: placeholder/글자 크기와 내부 패딩을 여기서 조정합니다. */
    min-height: 3rem !important;
    height: 3rem !important;
    padding: 0.74rem 1.2rem 0.55rem 0.9rem !important;
    color: #eee8ea !important;
    font-size: 0.82rem !important;
    line-height: 1.4 !important;
    caret-color: #ffc889 !important;
    background: transparent !important;
}

/* 채팅 페이지 입력창 내부의 Streamlit/BaseWeb 중첩 배경을 제거합니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] div,
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: transparent !important;
}

/* 채팅 페이지 placeholder 색상입니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] textarea::placeholder {
    color: rgba(128, 106, 148, 0.72) !important;
    font-size: 0.82rem !important;
}

/* 채팅 페이지 전송 버튼은 알약 모양 입력창 오른쪽에 떠 있도록 배치합니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] button {
    /* 채팅 페이지 전송 버튼: 바깥 위치, width/height, 아이콘 크기를 여기서 조정합니다. */
    position: absolute !important;
    top: 50% !important;
    right: -4.25rem !important;
    width: calc(3.1rem + 20px) !important;
    min-width: calc(3.1rem + 20px) !important;
    height: 3rem !important;
    min-height: 3rem !important;
    margin: 0 !important;
    transform: translateY(-50%) !important;
    border: 0 !important;
    border-radius: 999px !important;
    background-color: transparent !important;
    background-image: url("__SEND_ICON__") !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    background-size: 2.45rem 2.45rem !important;
    box-shadow: none !important;
}

/* Streamlit 전송 버튼에 붙을 수 있는 가상 요소를 비활성화합니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] button::before {
    content: none;
}

/* 채팅 전송 버튼의 Streamlit 기본 SVG 아이콘을 숨깁니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] button svg {
    display: none !important;
}

/* 배경이 화면 하단 끝까지 닿도록 채팅 캔버스 bottom을 후순위로 보정합니다. */
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .maple-chat-page {
    bottom: 0;
}

/* 서브 페이지에서는 홈 입력창, 칩, 히어로 영역, 미리보기 패널을 표시하지 않습니다. */
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) [data-testid="stBottom"],
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) [data-testid="stBottomBlockContainer"],
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-chip-row,
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .maple-hero,
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .maple-message-panel {
    display: none !important;
}
</style>
""".replace("__SEND_ICON__", send_icon).replace("__BACKGROUND_IMAGE__", background_image).replace("__CHAT_BACKGROUND_IMAGE__", chat_background_image).replace("__HOME_BUTTON__", home_button).replace("__HOME_BADGE__", home_badge).replace("__MAPLE_LIGHT__", maple_light).replace("__MAPLE_BOLD__", maple_bold)


def render_style() -> None:
    """생성한 CSS를 현재 Streamlit 페이지에 주입합니다."""
    st.markdown(get_maple_chat_css(), unsafe_allow_html=True)
