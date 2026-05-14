from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.common.assets import asset_path, path_to_data_uri


ASSISTANT_AVATAR_PATH = asset_path("assistant_avatar.png")
USER_AVATAR_PATH = asset_path("user_avatar.png")
BACKGROUND_PATH = asset_path("background_home.png")
CHAT_BACKGROUND_PATH = asset_path("chat_background.png")
CHAT_BACKGROUND_OVERLAY_PATH = asset_path("chat_background2.png")
HOME_BUTTON_PATH = asset_path("home_button.png")
HOME_BADGE_PATH = asset_path("home_button2.png")
MAPLESTORY_BOLD_PATH = asset_path("Maplestory-Bold.ttf")
MAPLESTORY_LIGHT_PATH = asset_path("Maplestory-Light.ttf")


def image_to_data_uri(path: Path) -> str:
    return path_to_data_uri(path, default_mime="image/jpeg")


def get_maple_chat_css() -> str:
    background_image = image_to_data_uri(BACKGROUND_PATH)
    chat_background_image = image_to_data_uri(CHAT_BACKGROUND_PATH)
    home_button = image_to_data_uri(HOME_BUTTON_PATH)
    home_badge = image_to_data_uri(HOME_BADGE_PATH)
    maple_bold = image_to_data_uri(MAPLESTORY_BOLD_PATH)
    maple_light = image_to_data_uri(MAPLESTORY_LIGHT_PATH)

    return """
<style>
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

:root {
    --bg: #020202;
    --orange: #ffc889;
    --muted: #8d8580;
    --violet: #7869ff;
    --chat-bg-ratio: 1.982438;
    --chat-bg-w: max(100vw, calc(100vh * var(--chat-bg-ratio)));
    --chat-bg-h: max(100vh, calc(100vw / var(--chat-bg-ratio)));
    --chat-bg-left: calc((100vw - var(--chat-bg-w)) / 2);
    --chat-bg-top: calc((100vh - var(--chat-bg-h)) / 2 - 1rem);
    --home-title-w: min(56rem, calc(100vw - 2rem));
    --home-input-w: min(46rem, calc(100vw - 3.5rem));
    --home-title-center-y: 37vh;
    --home-title-h: 16rem;
    --chat-overlay-ratio: 1.789157;
    --chat-page-pad: 1rem;
    --chat-overlay-h: min(calc(100vh - 5.4rem), calc((100vw - var(--chat-page-pad)) / var(--chat-overlay-ratio)));
    --chat-overlay-w: calc(var(--chat-overlay-h) * var(--chat-overlay-ratio));
    --chat-overlay-left: calc((100vw - var(--chat-overlay-w)) / 2);
    --chat-overlay-top: calc(4.1rem + ((100vh - 4.1rem - var(--chat-overlay-h)) / 2));
    /* 우측 흰 패널 - 가장 큰 첫번째 박스 (채팅창 영역) */
    --chat-panel-left: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.595);
    --chat-panel-right: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.984 - 7px);
    --chat-panel-top: calc(var(--chat-overlay-top) + var(--chat-overlay-h) * 0.128);
    --chat-panel-bottom: calc(var(--chat-overlay-top) + var(--chat-overlay-h) * 0.890);
    /* 두번째 박스 - 채팅창 바로 아래, ENTER 왼쪽의 입력창 */
    --chat-input-left: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.595);
    --chat-input-right: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.875);
    --chat-input-top: calc(var(--chat-overlay-top) + var(--chat-overlay-h) * 0.902 - 10px);
    --chat-input-h: calc(var(--chat-overlay-h) * 0.052);
    /* ENTER 회색 사각형 (전송 버튼 클릭 영역) */
    --chat-enter-left: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.880);
    --chat-enter-right: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.948);
    --chat-enter-top: calc(var(--chat-overlay-top) + var(--chat-overlay-h) * 0.908);
    --chat-enter-h: calc(var(--chat-overlay-h) * 0.046);
}

html,
body,
.stApp,
[data-testid="stAppViewContainer"] {
    margin: 0 !important;
    width: 100vw !important;
    min-width: 100vw !important;
    min-height: 100vh !important;
    background: var(--bg) !important;
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    overflow-x: hidden !important;
}

.stApp *,
[data-testid="stAppViewContainer"] * {
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
}

.block-container {
    max-width: none !important;
    padding: 0 !important;
}

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

[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"] > div {
    background: transparent !important;
    box-shadow: none !important;
}

[data-testid="stAppViewContainer"]::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background:
        linear-gradient(
            180deg,
            rgba(0, 0, 0, 0.08) 0%,
            rgba(0, 0, 0, 0.16) 45%,
            rgba(0, 0, 0, 0.72) 68%,
            rgba(0, 0, 0, 0.96) 100%
        ),
        url("__BACKGROUND_IMAGE__") center / cover no-repeat;
    z-index: 0;
}

[data-testid="stAppViewContainer"]::after {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    border: 1.5px solid var(--violet);
    border-radius: 6px;
    z-index: 9999;
}

.maple-nav-bg {
    position: fixed;
    top: 1px;
    left: 1px;
    right: 1px;
    height: 4.1rem;
    background: linear-gradient(180deg, rgba(18, 15, 13, 0.98), rgba(8, 7, 6, 0.94));
    z-index: 80;
}

.st-key-maple-nav-bar {
    position: fixed !important;
    top: 0.55rem !important;
    left: 50% !important;
    width: 30rem !important;
    transform: translateX(-50%) !important;
    z-index: 100 !important;
}

.st-key-maple-nav-bar [data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 0.4rem !important;
}

.st-key-maple-nav-bar button {
    min-height: 2.2rem !important;
    height: 2.2rem !important;
    padding: 0 0.35rem !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    color: var(--muted) !important;
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-size: 0.66rem !important;
    white-space: nowrap !important;
}

.st-key-maple-nav-bar button[kind="primary"] {
    color: var(--orange) !important;
    position: relative;
}

.st-key-maple-nav-bar button[kind="primary"]::after {
    content: "";
    position: absolute;
    left: 50%;
    bottom: 0.18rem;
    width: 2rem;
    height: 2px;
    transform: translateX(-50%);
    border-radius: 999px;
    background: var(--orange);
}

.st-key-maple-home-badge {
    position: fixed !important;
    top: 0.24rem !important;
    left: 0.58rem !important;
    width: 1.45rem !important;
    z-index: 120 !important;
}

.st-key-maple-home-badge button {
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

.st-key-maple-home-badge button * {
    color: transparent !important;
    font-size: 0 !important;
}

.st-key-maple-brand-bar {
    position: fixed !important;
    top: var(--home-title-center-y) !important;
    left: 50% !important;
    width: var(--home-title-w) !important;
    transform: translate(-50%, -50%) !important;
    z-index: 45 !important;
}

.st-key-maple-brand-bar .maple-brand-logo {
    display: block;
    width: var(--home-title-w) !important;
    min-height: var(--home-title-h) !important;
    height: var(--home-title-h) !important;
    background: url("__HOME_BUTTON__") center / contain no-repeat !important;
    pointer-events: none;
}

.st-key-maple-brand-bar [data-testid="stMarkdownContainer"] {
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
}

.maple-hero {
    min-height: calc(100vh - 4.1rem);
}

.maple-title,
.maple-input-space,
.maple-message-panel {
    display: none !important;
}

.st-key-maple-home-input {
    position: fixed !important;
    left: 50% !important;
    right: auto !important;
    top: calc(var(--home-title-center-y) + (var(--home-title-h) / 2) - 0.25rem) !important;
    bottom: auto !important;
    width: var(--home-input-w) !important;
    max-width: var(--home-input-w) !important;
    padding: 0 !important;
    transform: translateX(-50%) !important;
    z-index: 65 !important;
}

.st-key-maple-home-input [data-testid="stVerticalBlock"],
.st-key-maple-home-input [data-testid="stElementContainer"],
.st-key-maple-home-input div[data-testid="stTextInput"] {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
}

.st-key-maple-home-input [data-testid="stTextInputRootElement"] {
    min-height: 3.1rem !important;
    border: 1px solid rgba(255, 200, 137, 0.62) !important;
    border-radius: 8px !important;
    background: rgba(0, 0, 0, 0.39) !important;
    background-color: rgba(0, 0, 0, 0.39) !important;
    box-shadow: none !important;
    backdrop-filter: none;
}

.st-key-maple-home-input [data-baseweb="input"],
.st-key-maple-home-input [data-testid="stTextInputRootElement"] > div {
    background: transparent !important;
    background-color: transparent !important;
    box-shadow: none !important;
}

.st-key-maple-home-input input {
    background: transparent !important;
    background-color: transparent !important;
    color: #fff7e8 !important;
    caret-color: var(--orange) !important;
    font-size: 0.92rem !important;
}

.st-key-maple-home-input input::placeholder {
    color: rgba(255, 247, 232, 0.78) !important;
}

.st-key-maple-chip-row {
    position: fixed !important;
    left: 50% !important;
    top: calc(var(--home-title-center-y) + (var(--home-title-h) / 2) + 3.65rem) !important;
    bottom: auto !important;
    width: min(44rem, calc(100vw - 3rem)) !important;
    transform: translateX(-50%) !important;
    z-index: 60 !important;
}

.st-key-maple-chip-row [data-testid="stHorizontalBlock"] {
    gap: 0.7rem !important;
}

.st-key-maple-chip-row button {
    min-height: 2.7rem !important;
    height: 2.7rem !important;
    padding: 0 0.8rem !important;
    border: 1px solid rgba(255, 200, 137, 0.42) !important;
    border-radius: 8px !important;
    background: rgba(0, 0, 0, 0.42) !important;
    color: #ffe8c6 !important;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28) !important;
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-size: 0.78rem !important;
    white-space: nowrap !important;
}

.st-key-maple-chip-row button:hover {
    border-color: rgba(255, 200, 137, 0.72) !important;
    background: rgba(70, 43, 18, 0.58) !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker)::before,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker)::before {
    display: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .st-key-maple-brand-bar,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .st-key-maple-brand-bar,
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-brand-bar,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .st-key-maple-home-badge {
    display: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-home-input,
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-chip-row,
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .maple-hero,
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .st-key-maple-home-input,
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .st-key-maple-chip-row,
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .maple-hero,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .st-key-maple-home-input,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .st-key-maple-chip-row,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .maple-hero {
    display: none !important;
}

.maple-chat-page {
    position: fixed;
    inset: 0;
    z-index: 10;
    overflow: hidden;
    background:
        linear-gradient(180deg, rgba(0, 0, 0, 0) 68%, rgba(0, 0, 0, 0.3)),
        url("__CHAT_BACKGROUND_IMAGE__") center calc(50% - 1rem) / cover no-repeat,
        #020202;
}

.maple-portal-canvas {
    position: fixed;
    left: calc(var(--chat-bg-left) + var(--chat-bg-w) * 0.140);
    top: calc(var(--chat-bg-top) + var(--chat-bg-h) * 0.724);
    width: calc(var(--chat-bg-w) * 0.064);
    height: calc(var(--chat-bg-h) * 0.180);
    pointer-events: none;
    z-index: 11;
    border-radius: 50%;
    opacity: 0.74;
    transform: translate(-50%, -50%) translateZ(0);
    filter: saturate(1.02) brightness(1.01);
    mask-image: radial-gradient(ellipse at center, black 40%, rgba(0, 0, 0, 0.58) 63%, transparent 92%);
    -webkit-mask-image: radial-gradient(ellipse at center, black 40%, rgba(0, 0, 0, 0.58) 63%, transparent 92%);
}

.maple-chat-overlay {
    position: fixed;
    left: var(--chat-overlay-left);
    top: var(--chat-overlay-top);
    width: var(--chat-overlay-w);
    height: var(--chat-overlay-h);
    object-fit: contain;
    pointer-events: none;
    z-index: 12;
}

.maple-chat-thread {
    position: fixed;
    left: var(--chat-panel-left);
    right: calc(100vw - var(--chat-panel-right));
    top: var(--chat-panel-top);
    bottom: calc(100vh - var(--chat-panel-bottom));
    z-index: 20;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    overflow-y: auto;
    padding: calc(var(--chat-overlay-h) * 0.012) calc(var(--chat-overlay-w) * 0.012);
    scrollbar-width: thin;
    scrollbar-color: rgba(105, 105, 105, 0.45) transparent;
}

.maple-chat-row {
    display: flex;
    align-items: flex-end;
    gap: calc(var(--chat-overlay-w) * 0.004);
    margin: calc(var(--chat-overlay-h) * 0.005) 0;
}

.maple-chat-row.user {
    flex-direction: row-reverse;
}

.maple-chat-avatar {
    width: calc(var(--chat-overlay-h) * 0.05);
    height: calc(var(--chat-overlay-h) * 0.05);
    flex: 0 0 calc(var(--chat-overlay-h) * 0.05);
    border-radius: 6px;
    object-fit: cover;
}

.maple-chat-bubble {
    width: fit-content;
    max-width: min(24rem, 86%);
    margin: 0;
    padding: calc(var(--chat-overlay-h) * 0.009) calc(var(--chat-overlay-w) * 0.008);
    border: 1px solid rgba(125, 125, 125, 0.24);
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.48);
    color: #3d3b39;
    font-size: calc(var(--chat-overlay-h) * 0.02);
    line-height: 1.5;
}

.maple-chat-bubble.user {
    background: rgba(222, 244, 218, 0.56);
}

.maple-chat-bubble p,
.maple-chat-bubble ul,
.maple-chat-bubble ol,
.maple-chat-bubble pre,
.maple-chat-bubble h1,
.maple-chat-bubble h2,
.maple-chat-bubble h3 {
    margin: 0 0 0.45rem;
}

.maple-chat-bubble > :last-child {
    margin-bottom: 0;
}

.maple-chat-bubble h1,
.maple-chat-bubble h2,
.maple-chat-bubble h3 {
    color: #2f2c2a;
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-size: 1em;
    line-height: 1.35;
}

.maple-chat-bubble ul,
.maple-chat-bubble ol {
    padding-left: 1.05rem;
}

.maple-chat-bubble code {
    padding: 0.05rem 0.22rem;
    border-radius: 4px;
    background: rgba(47, 44, 42, 0.12);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
    font-size: 0.92em;
}

.maple-chat-bubble pre {
    overflow-x: auto;
    padding: 0.45rem 0.55rem;
    border-radius: 6px;
    background: rgba(47, 44, 42, 0.12);
}

.maple-chat-bubble pre code {
    padding: 0;
    background: transparent;
    white-space: pre;
}

.maple-chat-bubble a {
    color: #255f9f;
    text-decoration: underline;
}

.maple-chat-thinking {
    display: inline-flex;
    align-items: center;
    gap: calc(var(--chat-overlay-w) * 0.006);
    color: #3d3b39;
}

.maple-thinking-spinner {
    width: calc(var(--chat-overlay-h) * 0.024);
    height: calc(var(--chat-overlay-h) * 0.024);
    border: 2px solid rgba(90, 164, 214, 0.28);
    border-top-color: rgba(90, 164, 214, 0.96);
    border-radius: 50%;
    animation: maple-thinking-spin 0.8s linear infinite;
    flex: 0 0 auto;
}

@keyframes maple-thinking-spin {
    to {
        transform: rotate(360deg);
    }
}

.maple-chat-scroll-anchor {
    flex: 0 0 1px;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottom"],
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottomBlockContainer"] {
    position: fixed !important;
    left: var(--chat-input-left) !important;
    right: auto !important;
    top: var(--chat-input-top) !important;
    bottom: auto !important;
    width: calc(var(--chat-input-right) - var(--chat-input-left)) !important;
    max-width: calc(var(--chat-input-right) - var(--chat-input-left)) !important;
    padding: 0 !important;
    transform: none !important;
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    backdrop-filter: none;
    z-index: 30 !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottomBlockContainer"] > div {
    width: 100% !important;
    max-width: none !important;
    padding: 0 !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] {
    width: 100% !important;
    background: transparent !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] > div {
    min-height: var(--chat-input-h) !important;
    height: var(--chat-input-h) !important;
    max-height: var(--chat-input-h) !important;
    border: 0 !important;
    border-radius: 6px !important;
    background: transparent !important;
    box-shadow: none !important;
    overflow: hidden !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: transparent !important;
    box-shadow: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] textarea {
    min-height: var(--chat-input-h) !important;
    height: var(--chat-input-h) !important;
    max-height: var(--chat-input-h) !important;
    padding: calc(var(--chat-input-h) * 0.22) calc(var(--chat-overlay-w) * 0.005) !important;
    color: #2f2c2a !important;
    font-size: calc(var(--chat-overlay-h) * 0.02) !important;
    line-height: calc(var(--chat-overlay-h) * 0.019) !important;
    caret-color: #2f2c2a !important;
    overflow: hidden !important;
    resize: none !important;
    white-space: nowrap !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] textarea::placeholder {
    color: rgba(70, 70, 70, 0.8) !important;
    font-size: calc(var(--chat-overlay-h) * 0.02) !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] button {
    position: fixed !important;
    left: var(--chat-enter-left) !important;
    top: var(--chat-enter-top) !important;
    width: calc(var(--chat-enter-right) - var(--chat-enter-left)) !important;
    min-width: calc(var(--chat-enter-right) - var(--chat-enter-left)) !important;
    height: var(--chat-enter-h) !important;
    min-height: var(--chat-enter-h) !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 8px !important;
    background: transparent !important;
    box-shadow: none !important;
    opacity: 1 !important;
    cursor: pointer !important;
    z-index: 40 !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] button svg {
    opacity: 0 !important;
}

[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) [data-testid="stBottom"],
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) [data-testid="stBottomBlockContainer"],
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .maple-hero,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .maple-message-panel {
    display: none !important;
}

@media (max-width: 760px) {
    :root {
        --home-input-w: calc(100vw - 2rem);
        --home-title-center-y: 34vh;
        --home-title-h: 12rem;
        --chat-page-pad: 0.5rem;
    }

    .st-key-maple-nav-bar {
        width: 22rem !important;
    }

    .st-key-maple-nav-bar button {
        font-size: 0.54rem !important;
    }

    .st-key-maple-chip-row {
        top: calc(var(--home-title-center-y) + (var(--home-title-h) / 2) + 3.45rem) !important;
        bottom: auto !important;
        width: calc(100vw - 2rem) !important;
    }

    .st-key-maple-chip-row [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 0.45rem !important;
    }

    .st-key-maple-chip-row button {
        height: 2.35rem !important;
        min-height: 2.35rem !important;
        font-size: 0.68rem !important;
    }
}
</style>
""".replace("__BACKGROUND_IMAGE__", background_image).replace(
        "__CHAT_BACKGROUND_IMAGE__", chat_background_image
    ).replace("__HOME_BUTTON__", home_button).replace("__HOME_BADGE__", home_badge).replace(
        "__MAPLE_LIGHT__", maple_light
    ).replace("__MAPLE_BOLD__", maple_bold)


def render_style() -> None:
    st.markdown(get_maple_chat_css(), unsafe_allow_html=True)
