from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
ASSISTANT_AVATAR_PATH = ASSET_DIR / "assistant_avatar.png"
USER_AVATAR_PATH = ASSET_DIR / "user_avatar.png"
SEND_ICON_PATH = ASSET_DIR / "send_icon.png"
BACKGROUND_PATH = ASSET_DIR / "background_home.png"
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
    send_icon = image_to_data_uri(SEND_ICON_PATH)
    background_image = image_to_data_uri(BACKGROUND_PATH)
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

html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

.stApp,
.stApp *,
[data-testid="stAppViewContainer"] * {
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
}

[data-testid="stAppViewContainer"]::before {
    /* Home background: height controls image coverage; background gradients/image position control tone and crop. */
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

.block-container {
    max-width: none !important;
    padding: 0 !important;
}

header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
#MainMenu,
footer {
    display: none !important;
}

[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div {
    background: transparent !important;
    box-shadow: none !important;
}

.st-emotion-cache-1dp5vir,
.st-emotion-cache-10trblm,
.st-emotion-cache-zt5igj {
    display: none !important;
}

.maple-shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    color: var(--text);
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-weight: normal;
}

.maple-nav-bg {
    /* Top menu backdrop: change height/background/z-index to alter the menu bar frame. */
    position: fixed;
    top: 1px;
    left: 1px;
    right: 1px;
    height: 4.1rem;
    background: linear-gradient(180deg, rgba(18, 15, 13, 0.98), rgba(8, 7, 6, 0.94));
    z-index: 20;
}

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

.st-key-maple-nav-bar {
    /* Top menu group: change top/width to move or stretch the menu items. */
    position: fixed !important;
    top: 0.55rem !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    width: 24rem !important;
    z-index: 40 !important;
}

.st-key-maple-brand-bar {
    /* Main home logo image group: change top/width to move or resize the large center image. */
    position: fixed !important;
    top: 39vh !important;
    left: 50% !important;
    width: min(56rem, calc(100vw - 2rem)) !important;
    transform: translate(-50%, -50%) !important;
    z-index: 45 !important;
}

.st-key-maple-home-badge {
    /* Small home icon: change top/left/width to position and size the clickable home icon. */
    position: fixed !important;
    top: 0.24rem !important;
    left: 0.58rem !important;
    width: 1.45rem !important;
    z-index: 90 !important;
}

.st-key-maple-nav-bar [data-testid="stHorizontalBlock"],
.st-key-maple-brand-bar [data-testid="stHorizontalBlock"] {
    gap: 0.4rem !important;
}

.st-key-maple-nav-bar button,
.st-key-maple-brand-bar button {
    /* Shared menu/logo button reset: change height/padding/font-size for global button sizing. */
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

.st-key-maple-home-badge button {
    /* Small home icon button image: change width/height/background-size for the leaf button. */
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

.st-key-maple-nav-bar button *,
.st-key-maple-brand-bar button * {
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

.st-key-maple-brand-bar button {
    /* Large home logo image: change width/height/background-size to resize the central logo. */
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

.st-key-maple-brand-bar button * {
    color: transparent !important;
    font-size: 0 !important;
}

.st-key-maple-nav-bar button:hover {
    color: var(--orange-strong) !important;
}

.st-key-maple-nav-bar .st-key-nav_chat button,
.st-key-maple-nav-bar button[kind="primary"] {
    color: var(--orange-strong) !important;
    position: relative;
}

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

.maple-hero {
    min-height: calc(100vh - 6.1rem);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4.1rem 1.25rem 8.1rem;
    transform: none;
}

.maple-title {
    display: none;
}

.maple-title::before {
    content: none;
}

.maple-input-space {
    /* Home input spacer: reserves visual space around the home input area. */
    width: min(47rem, calc(100vw - 2rem));
    height: 4.3rem;
}

div[data-testid="stChatInput"] {
    position: relative !important;
    top: auto !important;
    left: auto !important;
    bottom: auto !important;
    transform: none !important;
    width: 100% !important;
    z-index: 120 !important;
}

div[data-testid="stChatInput"] > div {
    /* Default/home input shell: change border/radius/background/glow for the main page input. */
    border: 1px solid rgba(255, 255, 255, 0.04) !important;
    border-radius: 8px !important;
    background: rgba(31, 29, 28, 0.98) !important;
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.03),
        0 0 18px rgba(255, 178, 107, 0.16) !important;
}

div[data-testid="stChatInput"] textarea {
    /* Default/home input text field: change height, padding, text size, and placeholder spacing. */
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

div[data-testid="stChatInput"] textarea::placeholder {
    color: #6f6864 !important;
    opacity: 1 !important;
}

div[data-testid="stChatInput"] textarea::-webkit-scrollbar {
    display: none !important;
}

div[data-testid="stChatInput"] button {
    /* Home input send button: adjust size/position/icon for the main page here. */
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

div[data-testid="stChatInput"] button svg {
    opacity: 0 !important;
}

.st-key-maple-chip-row {
    /* Home prompt chips container: change top/width to move or stretch the 3 prompt buttons. */
    position: fixed !important;
    top: calc(75vh - 37px) !important;
    left: 50% !important;
    bottom: auto !important;
    transform: translateX(-50%) !important;
    width: min(47rem, calc(100vw - 2rem)) !important;
    z-index: 110 !important;
}

.st-key-maple-chip-row [data-testid="stHorizontalBlock"] {
    gap: 1rem !important;
}

.st-key-maple-chip-row button {
    /* Home prompt chip shape: change height/padding/radius/font-size for chip appearance. */
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

.st-key-maple-chip-row button * {
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

.maple-message,
.maple-message * {
    font-family: "MaplestoryLight", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

.st-key-chip_story button {
    color: #ffadc6 !important;
    border: 1px solid rgba(255, 137, 177, 0.55) !important;
    box-shadow: 0 0 12px rgba(255, 137, 177, 0.17) !important;
}

.st-key-chip_debug button {
    color: #1ffa4f !important;
    border: 1px solid rgba(27, 240, 83, 0.55) !important;
    box-shadow: 0 0 12px rgba(27, 240, 83, 0.17) !important;
}

.st-key-chip_quantum button {
    color: #ffcb81 !important;
    border: 1px solid rgba(255, 189, 103, 0.55) !important;
    box-shadow: 0 0 12px rgba(255, 189, 103, 0.17) !important;
}

.maple-message-panel {
    /* Home message preview panel: change top/width/max-height if previews are ever shown on home. */
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

.maple-message {
    /* Home message preview bubble: change padding/radius/background/font-size here. */
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

.maple-message.user {
    margin-left: auto;
    border-color: rgba(255, 189, 103, 0.45);
    background: rgba(53, 36, 24, 0.9);
}

.maple-message.assistant {
    margin-right: auto;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker)::before {
    display: none;
}

[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker)::before {
    display: none;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .st-key-maple-brand-bar {
    display: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-brand-bar {
    display: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .st-key-maple-home-badge {
    display: block !important;
}

[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-home-badge {
    display: block !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .maple-chat-page {
    /* Chat page canvas: change top/bottom/padding/background to resize the chat area. */
    position: fixed;
    top: 4.1rem;
    left: 0;
    right: 0;
    bottom: 5.8rem;
    z-index: 12;
    padding: 1.25rem max(1rem, calc((100vw - 52rem) / 2));
    overflow: hidden;
    background:
        radial-gradient(circle at 50% 0%, rgba(255, 180, 105, 0.08), transparent 26rem),
        #020202;
}

.maple-chat-thread {
    /* Chat stack behavior: justify-content controls bottom-up messages; padding controls inner spacing. */
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    overflow-y: auto;
    padding: 0.25rem 0 1rem;
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 189, 103, 0.45) transparent;
}

.maple-chat-row {
    /* Chat row spacing: gap is avatar-to-bubble distance; margin is distance between messages. */
    display: flex;
    align-items: flex-end;
    gap: 0.55rem;
    margin: 0.55rem 0;
}

.maple-chat-row.user {
    flex-direction: row-reverse;
    justify-content: flex-start;
}

.maple-chat-row.assistant {
    justify-content: flex-start;
}

.maple-chat-avatar {
    /* Chat profile avatar: change width/height/radius/border to style profile images. */
    width: 2.15rem;
    height: 2.15rem;
    flex: 0 0 2.15rem;
    border-radius: 8px;
    object-fit: cover;
    border: 1px solid rgba(255, 190, 125, 0.25);
    background: rgba(255, 255, 255, 0.05);
}

.maple-chat-bubble {
    /* Chat bubble body: change max-width/padding/radius/background/font-size for message bubbles. */
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

.maple-chat-bubble.user {
    border-color: rgba(33, 230, 83, 0.28);
    background: rgba(19, 44, 29, 0.9);
}

.maple-chat-bubble.assistant {
    border-color: rgba(255, 190, 125, 0.28);
}

.maple-chat-empty {
    margin-top: 28vh;
    color: rgba(245, 240, 234, 0.55);
    text-align: center;
    font-size: 0.9rem;
}

@media (max-width: 640px) {
    .maple-brand-label {
        left: 0.8rem;
        font-size: 0.82rem;
    }

    .st-key-maple-nav-bar {
        width: 17.5rem !important;
        top: 0.72rem !important;
    }

    .st-key-maple-nav-bar button {
        font-size: 0.56rem !important;
        padding: 0 0.16rem !important;
    }

    .maple-title {
        margin-bottom: 2rem;
    }

    .st-key-maple-chip-row [data-testid="stHorizontalBlock"] {
        gap: 0.35rem !important;
    }

    .st-key-maple-chip-row button {
        padding: 0 0.45rem !important;
        font-size: 0.52rem !important;
    }
}

[data-testid="stBottom"] {
    position: fixed !important;
    top: calc(75vh - 131px) !important;
    bottom: auto !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 120 !important;
    transform: none !important;
}

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

[data-testid="stBottomBlockContainer"] > div {
    width: 100% !important;
    max-width: none !important;
    padding: 0 !important;
}

[data-testid="stBottom"] div[data-testid="stChatInput"],
div[data-testid="stChatInput"] {
    position: relative !important;
    top: auto !important;
    bottom: auto !important;
    left: auto !important;
    width: 100% !important;
    transform: none !important;
}

.st-key-maple-chip-row {
    position: fixed !important;
    top: calc(75vh - 37px) !important;
    bottom: auto !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
}

.maple-title,
.maple-title *,
.st-key-maple-brand-bar button,
.st-key-maple-brand-bar button *,
.st-key-maple-nav-bar button,
.st-key-maple-nav-bar button * {
    font-family: "MaplestoryBold", Inter, ui-sans-serif, system-ui, sans-serif !important;
    font-weight: normal !important;
}

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

.st-key-maple-brand-bar button,
.st-key-maple-brand-bar button *,
.st-key-maple-brand-bar button p,
.st-key-maple-brand-bar button span {
    color: transparent !important;
    font-size: 0 !important;
}

.st-key-maple-brand-bar button {
    background-image: url("__HOME_BUTTON__") !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    background-size: contain !important;
}

.st-key-maple-home-badge button,
.st-key-maple-home-badge button *,
.st-key-maple-home-badge button p,
.st-key-maple-home-badge button span {
    color: transparent !important;
    font-size: 0 !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottom"],
[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) [data-testid="stBottomBlockContainer"] {
    /* Chat page input wrapper: adjust the whole input bar width and bottom position here. */
    position: fixed !important;
    top: auto !important;
    bottom: 1rem !important;
    left: 50% !important;
    right: auto !important;
    width: min(calc(36rem + 30px), calc(100vw - 3rem)) !important;
    max-width: min(calc(36rem + 30px), calc(100vw - 3rem)) !important;
    padding: 0 !important;
    transform: translateX(-50%) !important;
    z-index: 130 !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] {
    position: relative !important;
    width: 100% !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] > div {
    /* Chat page input border/background: adjust outline, glow, and bar height here. */
    min-height: 3.07rem !important;
    border: 2px solid rgba(255, 176, 111, 0.68) !important;
    border-radius: 999px !important;
    background: transparent !important;
    box-shadow:
        0 0 0 1px rgba(255, 210, 160, 0.1),
        0 0 14px rgba(255, 176, 111, 0.26) !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] textarea {
    /* Chat page text field: adjust placeholder/text size and inner padding here. */
    min-height: 3rem !important;
    height: 3rem !important;
    padding: 0.74rem 1.2rem 0.55rem 0.9rem !important;
    color: #eee8ea !important;
    font-size: 0.82rem !important;
    line-height: 1.4 !important;
    caret-color: #ffc889 !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] textarea::placeholder {
    color: rgba(128, 106, 148, 0.72) !important;
    font-size: 0.82rem !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] button {
    /* Chat page send button: adjust outside position, width/height, and icon size here. */
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

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] button::before {
    content: none;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) div[data-testid="stChatInput"] button svg {
    display: none !important;
}

[data-testid="stAppViewContainer"]:has(.maple-chat-page-marker) .maple-chat-page {
    bottom: 6.4rem;
}

[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) [data-testid="stBottom"],
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) [data-testid="stBottomBlockContainer"],
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .st-key-maple-chip-row,
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .maple-hero,
[data-testid="stAppViewContainer"]:has(.maple-sub-page-marker) .maple-message-panel {
    display: none !important;
}
</style>
""".replace("__SEND_ICON__", send_icon).replace("__BACKGROUND_IMAGE__", background_image).replace("__HOME_BUTTON__", home_button).replace("__HOME_BADGE__", home_badge).replace("__MAPLE_LIGHT__", maple_light).replace("__MAPLE_BOLD__", maple_bold)


def render_style() -> None:
    st.markdown(get_maple_chat_css(), unsafe_allow_html=True)
