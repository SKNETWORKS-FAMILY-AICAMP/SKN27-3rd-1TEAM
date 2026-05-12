from __future__ import annotations

import os

from app.common.youtube_embed import render_youtube_embed


DEFAULT_YOUTUBE_BGM = "https://www.youtube.com/watch?v=VtvcSMZcEdE"
PAGE_YOUTUBE_BGM = {
    "home": "https://www.youtube.com/watch?v=iHFSl7p9ajE",
    "chat": "https://www.youtube.com/watch?v=FcgCvoXQXTQ",
    "lounge": DEFAULT_YOUTUBE_BGM,
    "models": DEFAULT_YOUTUBE_BGM,
    "history": DEFAULT_YOUTUBE_BGM,
    "party": DEFAULT_YOUTUBE_BGM,
    "quest": DEFAULT_YOUTUBE_BGM,
    "settings": DEFAULT_YOUTUBE_BGM,
}


def get_youtube_bgm_source(page_key: str | None = None) -> str | None:
    normalized_key = (page_key or "home").strip().lower()
    page_env_key = f"MAPLE_YOUTUBE_BGM_{normalized_key.upper()}"
    page_env_bgm = os.environ.get(page_env_key)
    if page_env_bgm is not None:
        return page_env_bgm.strip() or None

    env_bgm = os.environ.get("MAPLE_YOUTUBE_BGM")
    if env_bgm is not None:
        return env_bgm.strip() or None

    return PAGE_YOUTUBE_BGM.get(normalized_key, DEFAULT_YOUTUBE_BGM)


def render_page_bgm(page_key: str | None = None) -> None:
    source = get_youtube_bgm_source(page_key)
    if not source:
        return

    render_youtube_embed(
        source,
        height=1,
        muted=True,
        loop=True,
        controls=False,
        hidden=True,
        unlock_on_interaction=True,
    )


def render_bgm_sidebar(page_key: str | None = None) -> None:
    render_page_bgm(page_key)


def render_global_bgm(page_key: str | None = None) -> None:
    render_page_bgm(page_key)
