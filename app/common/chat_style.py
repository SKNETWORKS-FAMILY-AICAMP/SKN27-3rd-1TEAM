from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
ASSISTANT_AVATAR_PATH = ASSET_DIR / "assistant_avatar.png"
USER_AVATAR_PATH = ASSET_DIR / "user_avatar.png"
BACKGROUND_PATH = ASSET_DIR / "background_home.png"
CHAT_BACKGROUND_PATH = ASSET_DIR / "chat_background.png"
CHAT_BACKGROUND_OVERLAY_PATH = ASSET_DIR / "chat_background2.png"
HOME_BUTTON_PATH = ASSET_DIR / "home_button.png"
HOME_BADGE_PATH = ASSET_DIR / "home_button2.png"
MAPLESTORY_BOLD_PATH = ASSET_DIR / "Maplestory-Bold.ttf"
MAPLESTORY_LIGHT_PATH = ASSET_DIR / "Maplestory-Light.ttf"


def image_to_data_uri(path: Path) -> str:
    if not path.exists():
        return ""

    suffix = path.suffix.lower()
    if suffix == ".png":
        mime = "image/png"
    elif suffix in {".ttf", ".otf"}:
        mime = "font/ttf"
    else:
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


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
    --chat-overlay-ratio: 1.789157;
    --chat-overlay-h: min(calc(100vh - 5.4rem), calc(100vw / var(--chat-overlay-ratio) * 0.9));
    --chat-overlay-w: calc(var(--chat-overlay-h) * var(--chat-overlay-ratio));
    --chat-overlay-left: calc((100vw - var(--chat-overlay-w)) / 2);
    --chat-overlay-top: calc(4.1rem + ((100vh - 4.1rem - var(--chat-overlay-h)) / 2));
    --chat-panel-left: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.593);
    --chat-panel-right: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.966);
    --chat-panel-top: calc(var(--chat-overlay-top) + var(--chat-overlay-h) * 0.125);
    --chat-panel-bottom: calc(var(--chat-overlay-top) + var(--chat-overlay-h) * 0.895);
    --chat-input-left: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.596);
    --chat-input-right: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.886);
    --chat-input-top: calc(var(--chat-overlay-top) + var(--chat-overlay-h) * 0.887);
    --chat-input-h: calc(var(--chat-overlay-h) * 0.043);
    --chat-enter-left: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.899);
    --chat-enter-right: calc(var(--chat-overlay-left) + var(--chat-overlay-w) * 0.958);
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
        linear-gradient(180deg, rgba(0, 0, 0, 0.06), rgba(0, 0, 0, 0.58)),
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
    width: 24rem !important;
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
    top: 39vh !important;
    left: 50% !important;
    width: min(56rem, calc(100vw - 2rem)) !important;
    transform: translate(-50%, -50%) !important;
    z-index: 45 !important;
}

.st-key-maple-brand-bar button {
    width: min(56rem, calc(100vw - 2rem)) !important;
    min-height: 16rem !important;
    height: 16rem !important;
    color: transparent !important;
    font-size: 0 !important;
    border: 0 !important;
    background: url("__HOME_BUTTON__") center / contain no-repeat !important;
    box-shadow: none !important;
}

.st-key-maple-brand-bar button * {
    color: transparent !important;
    font-size: 0 !important;
}

.maple-hero {
    min-height: calc(100vh - 4.1rem);
}

.maple-title,
.maple-input-space,
.st-key-maple-chip-row,
.maple-message-panel {
    display: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker)::before,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker)::before {
    display: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .st-key-maple-brand-bar,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .st-key-maple-brand-bar,
[data-testid="stAppViewContainer"]:has(.maple-game-page-marker) .st-key-maple-home-badge {
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
    bottom: calc(100vh - var(--chat-input-top) + var(--chat-overlay-h) * 0.01);
    z-index: 20;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    overflow-y: auto;
    padding: calc(var(--chat-overlay-h) * 0.012) calc(var(--chat-overlay-w) * 0.012);
    outline: 2px dashed rgba(100, 200, 255, 0.9);
    outline-offset: 0;
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
    width: calc(var(--chat-overlay-h) * 0.03);
    height: calc(var(--chat-overlay-h) * 0.03);
    flex: 0 0 calc(var(--chat-overlay-h) * 0.03);
    border-radius: 5px;
    object-fit: cover;
}

.maple-chat-bubble {
    width: fit-content;
    max-width: min(24rem, 86%);
    margin: 0;
    padding: calc(var(--chat-overlay-h) * 0.007) calc(var(--chat-overlay-w) * 0.007);
    border: 1px solid rgba(125, 125, 125, 0.24);
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.48);
    color: #3d3b39;
    font-size: calc(var(--chat-overlay-h) * 0.014);
    line-height: 1.45;
}

.maple-chat-bubble.user {
    background: rgba(222, 244, 218, 0.56);
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
    background: transparent !important;
    box-shadow: none !important;
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
    border: 1px solid rgba(0, 0, 0, 0.12) !important;
    border-radius: 6px !important;
    background: rgba(252, 248, 242, 0.9) !important;
    box-shadow: none !important;
    overflow: hidden !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] div,
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: transparent !important;
    box-shadow: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] textarea {
    min-height: var(--chat-input-h) !important;
    height: var(--chat-input-h) +50px !important;
    max-height: var(--chat-input-h) !important;
    padding: calc(var(--chat-input-h) * 0.22) calc(var(--chat-overlay-w) * 0.001) 15 !important;
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
    top: var(--chat-input-top) -50px !important;
    width: calc(var(--chat-enter-right) - var(--chat-enter-left)) !important;
    min-width: calc(var(--chat-enter-right) - var(--chat-enter-left)) !important;
    height: var(--chat-input-h) !important;
    min-height: var(--chat-input-h) !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 8px !important;
    background: transparent !important;
    box-shadow: none !important;
    opacity: 1 !important;
    outline: 2px dashed rgba(255, 55, 55, 0.95) !important;
    outline-offset: 0 !important;
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
        --chat-overlay-h: min(calc(100vh - 5.4rem), calc(100vw / var(--chat-overlay-ratio) * 1.18));
    }

    .st-key-maple-nav-bar {
        width: 18rem !important;
    }

    .st-key-maple-nav-bar button {
        font-size: 0.58rem !important;
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
