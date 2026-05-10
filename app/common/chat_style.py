from __future__ import annotations

import base64
from pathlib import Path


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
ASSISTANT_AVATAR_PATH = ASSET_DIR / "assistant_avatar.png"
USER_AVATAR_PATH = ASSET_DIR / "user_avatar.png"
INPUT_PET_PATH = ASSET_DIR / "input_pet.png"


def image_to_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime_type = "image/svg+xml" if suffix == ".svg" else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def get_maple_chat_css() -> str:
    return f"""
<style>
:root {{
    --bg: #0b0b0f;
    --panel: rgba(18, 18, 20, 0.88);
    --panel-soft: rgba(31, 31, 34, 0.9);
    --line: rgba(218, 82, 132, 0.36);
    --line-soft: rgba(255, 255, 255, 0.08);
    --text: #e8e3e7;
    --muted: #777580;
    --gold: #f6c94e;
    --green: #28d59f;
    --pink: #cc6d91;
}}

#MainMenu,
header,
footer,
[data-testid="stSidebar"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] {{
    display: none !important;
}}

html,
body,
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {{
    overflow: hidden !important;
    background: var(--bg) !important;
}}

.stApp {{
    min-height: 100vh;
    color: var(--text);
    background:
        radial-gradient(circle at 42% 12%, rgba(255, 171, 104, 0.035), transparent 24rem),
        radial-gradient(circle at 70% 18%, rgba(233, 89, 151, 0.04), transparent 18rem),
        #0b0b0f !important;
}}

.block-container {{
    max-width: none;
    padding: 0;
}}

[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div,
[data-testid="stChatInput"] {{
    z-index: 60 !important;
    background: transparent !important;
    background-color: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
}}

.maple-home {{
    position: fixed;
    top: 0.9rem;
    left: 1.25rem;
    z-index: 30;
    display: grid;
    width: 78px;
    height: 78px;
    place-items: center;
    align-content: center;
    gap: 0.12rem;
    border: 1px solid rgba(232, 105, 151, 0.55);
    border-radius: 16px;
    background: linear-gradient(180deg, rgba(34, 34, 37, 0.96), rgba(18, 18, 20, 0.96));
    box-shadow: inset 0 1px 0 rgba(255,255,255,.08), 0 12px 28px rgba(0,0,0,.42);
    color: #f6edf0;
    font-size: 0.86rem;
    font-weight: 900;
}}

.maple-home::after {{
    content: "✿";
    position: absolute;
    right: -8px;
    bottom: 8px;
    color: #e47fa2;
    font-size: 1.25rem;
    text-shadow: 0 0 10px rgba(228, 127, 162, .7);
}}

.maple-home-icon {{
    width: 44px;
    height: 44px;
    border-radius: 12px;
    object-fit: cover;
}}

.maple-topbar {{
    position: fixed;
    top: 0.9rem;
    left: 7.4rem;
    z-index: 28;
    width: min(650px, calc(100vw - 17rem));
    height: 60px;
    border: 1px solid rgba(255, 255, 255, 0.13);
    border-radius: 14px;
    background: linear-gradient(180deg, rgba(31,31,33,.95), rgba(20,20,22,.94));
    box-shadow: inset 0 1px 0 rgba(255,255,255,.08), 0 14px 34px rgba(0,0,0,.42);
}}

.maple-menu {{
    display: grid;
    height: 100%;
    grid-template-columns: repeat(5, 1fr);
    align-items: center;
}}

.maple-menu-item {{
    position: relative;
    display: flex;
    height: 34px;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: #b9b5bd;
    font-size: 0.86rem;
    font-weight: 900;
}}

.maple-menu-item + .maple-menu-item {{
    border-left: 1px solid rgba(255,255,255,.1);
}}

.maple-menu-item.is-active {{
    color: #ffffff;
}}

.maple-menu-item.is-active::after {{
    content: "";
    position: absolute;
    bottom: -12px;
    left: 50%;
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: #ffb06f;
    transform: translateX(-50%);
    box-shadow: 0 0 12px rgba(255, 176, 111, .75);
}}

.maple-menu-icon,
.maple-menu-emoji {{
    display: grid;
    width: 30px;
    height: 30px;
    place-items: center;
    border-radius: 999px;
    object-fit: cover;
    font-size: 1.35rem;
    background: rgba(255,255,255,.06);
}}

.maple-actions {{
    position: fixed;
    top: 1.55rem;
    right: 2rem;
    z-index: 28;
    display: flex;
    gap: 1.25rem;
}}

.maple-action-icon {{
    position: relative;
    color: #b9b5bd;
    font-size: 1.55rem;
    line-height: 1;
}}

.maple-action-icon:first-child::after {{
    content: "";
    position: absolute;
    top: -0.18rem;
    right: -0.1rem;
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: #d46f98;
}}

.st-key-chat-shell {{
    position: fixed;
    top: 6.1rem;
    left: 1.25rem;
    right: 1.25rem;
    bottom: 9.3rem;
    z-index: 10;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 0;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: rgba(13, 13, 15, 0.9);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 16px 36px rgba(0,0,0,.38);
}}

.st-key-chat-shell [data-testid="stVerticalBlock"] {{
    gap: 0;
}}

.maple-room-notice {{
    position: sticky;
    top: 0;
    z-index: 3;
    padding: 0.9rem 1rem 0.7rem;
    border-bottom: 1px solid rgba(255,255,255,.05);
    background: linear-gradient(180deg, rgba(13,13,15,.96), rgba(13,13,15,.82));
    color: #c6c1c7;
    text-align: center;
    font-size: 0.9rem;
    font-weight: 800;
}}

.maple-room-notice b {{
    color: var(--gold);
}}

.maple-message-row {{
    display: flex;
    gap: 0.75rem;
    align-items: flex-start;
    margin: 0.8rem 0;
    padding: 0 0.8rem;
}}

.maple-message-row.is-user {{
    justify-content: flex-end;
    align-items: center;
}}

.maple-message-avatar {{
    width: 40px;
    height: 40px;
    flex: 0 0 auto;
    border: 1px solid rgba(255,255,255,.09);
    border-radius: 10px;
    object-fit: cover;
    background: rgba(255,255,255,.05);
}}

.maple-message-body {{
    max-width: min(520px, 70vw);
}}

.maple-message-name {{
    margin-bottom: 0.35rem;
    color: #fff;
    font-size: 0.9rem;
    font-weight: 900;
}}

.maple-message-name span,
.maple-message-meta {{
    margin-left: 0.45rem;
    color: var(--muted);
    font-size: 0.72rem;
    font-weight: 700;
}}

.maple-message-bubble {{
    max-width: min(520px, 70vw);
    padding: 0.8rem 1rem;
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 12px;
    background: var(--panel-soft);
    color: #eeeaf0;
    font-size: 0.92rem;
    font-weight: 700;
    line-height: 1.55;
}}

.maple-message-row.is-user .maple-message-bubble {{
    border-color: rgba(218, 82, 132, 0.28);
    background: rgba(52, 43, 48, 0.95);
}}

.maple-message-row.is-user .maple-message-meta {{
    align-self: flex-start;
    margin-top: 0.2rem;
}}

.maple-input-pet {{
    position: fixed !important;
    left: 2.8rem;
    bottom: 4.35rem;
    z-index: 2147483647 !important;
    pointer-events: none;
    isolation: isolate;
    transform: translateZ(0);
}}

.maple-input-pet img {{
    position: relative;
    z-index: 2147483647 !important;
    width: 260px;
    height: auto;
    border-radius: 0;
    object-fit: contain;
    filter: drop-shadow(0 10px 14px rgba(0,0,0,.58));
}}

div[data-testid="stChatInput"] {{
    position: fixed !important;
    left: 2.25rem;
    right: 2.25rem;
    bottom: 1.15rem;
    z-index: 70;
    width: auto !important;
    transform: none !important;
    padding: 0 !important;
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
}}

div[data-testid="stChatInput"] *,
div[data-testid="stChatInput"] > div {{
    background: transparent !important;
    background-color: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
}}

div[data-testid="stChatInput"] form {{
    position: relative !important;
    display: flex !important;
    align-items: center !important;
    min-height: 78px !important;
    padding: 0 !important;
}}

div[data-testid="stChatInput"] textarea {{
    min-height: 78px !important;
    height: 78px !important;
    padding: 1.35rem 13.5rem 1.35rem 7.2rem !important;
    border: 2px solid rgba(226, 128, 164, 0.55) !important;
    border-radius: 999px !important;
    background: linear-gradient(180deg, rgba(31,31,34,.96), rgba(19,19,21,.96)) !important;
    color: #e9e4e8 !important;
    font-size: 1.45rem !important;
    font-weight: 800;
    resize: none !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.08),
        inset 0 -18px 26px rgba(0,0,0,.18),
        0 0 0 1px rgba(255, 181, 207, .14),
        0 12px 32px rgba(0,0,0,.5);
}}

div[data-testid="stChatInput"] textarea::placeholder {{
    color: #5f5c66;
}}

div[data-testid="stChatInput"] form::before {{
    content: "+";
    position: absolute;
    left: 1.3rem;
    top: 50%;
    z-index: 2;
    display: grid;
    width: 56px;
    height: 56px;
    place-items: center;
    border: 1.5px solid rgba(226, 128, 164, 0.72);
    border-radius: 999px;
    color: #f6a0bf;
    font-size: 3rem;
    transform: translateY(-50%);
}}

div[data-testid="stChatInput"] form::after {{
    content: "⌣";
    position: absolute;
    right: 12rem;
    top: 50%;
    z-index: 2;
    display: grid;
    width: 54px;
    height: 54px;
    place-items: center;
    border: 1.5px solid rgba(226, 128, 164, 0.72);
    color: #ffd8de;
    font-size: 2.45rem;
    transform: translateY(-50%);
}}

div[data-testid="stChatInput"] button {{
    position: absolute !important;
    right: 1.4rem !important;
    top: 50% !important;
    width: 144px !important;
    height: 58px !important;
    min-width: 144px !important;
    min-height: 58px !important;
    margin: 0 !important;
    padding: 0 !important;
    transform: translateY(-50%) !important;
    border-radius: 999px !important;
    background: linear-gradient(180deg, #e8a1b8 0%, #c66888 100%) !important;
    border: 1.5px solid rgba(255, 208, 222, 0.72) !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.35), 0 6px 14px rgba(0,0,0,.3);
}}

div[data-testid="stChatInput"] button::before {{
    content: "전송 ›";
    color: #fff3f5;
    font-size: 1.45rem;
    font-weight: 900;
}}

div[data-testid="stChatInput"] button svg {{
    display: none !important;
}}

@media (max-width: 760px) {{
    .maple-home {{
        width: 62px;
        height: 62px;
        left: 0.7rem;
    }}
    .maple-home-icon {{
        width: 34px;
        height: 34px;
    }}
    .maple-topbar {{
        left: 5rem;
        right: 0.7rem;
        width: auto;
        height: 62px;
    }}
    .maple-menu-item {{
        gap: 0.1rem;
        font-size: 0.68rem;
    }}
    .maple-menu-icon,
    .maple-menu-emoji {{
        width: 26px;
        height: 26px;
        font-size: 1.2rem;
    }}
    .maple-actions,
    .maple-input-pet {{
        display: none;
    }}
    .st-key-chat-shell {{
        left: 0.7rem;
        right: 0.7rem;
        top: 5.5rem;
        bottom: 6rem;
    }}
    div[data-testid="stChatInput"] {{
        left: 0.7rem;
        right: 0.7rem;
        bottom: 0.85rem;
    }}
    div[data-testid="stChatInput"] textarea {{
        min-height: 58px !important;
        height: 58px !important;
        padding: 0.9rem 6.7rem 0.9rem 3.8rem !important;
        font-size: 0.95rem !important;
    }}
    div[data-testid="stChatInput"] form {{
        min-height: 58px !important;
    }}
    div[data-testid="stChatInput"] form::before {{
        left: 0.75rem;
        width: 36px;
        height: 36px;
        font-size: 1.8rem;
    }}
    div[data-testid="stChatInput"] form::after {{
        right: 5.35rem;
        width: 34px;
        height: 34px;
        font-size: 1.45rem;
    }}
    div[data-testid="stChatInput"] button {{
        right: 0.55rem !important;
        width: 72px !important;
        height: 40px !important;
        min-width: 72px !important;
        min-height: 40px !important;
    }}
    div[data-testid="stChatInput"] button::before {{
        font-size: 0.9rem;
    }}
}}
</style>
"""
