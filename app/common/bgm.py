from __future__ import annotations

import os

import streamlit as st

from app.common.youtube_embed import render_youtube_embed


DEFAULT_YOUTUBE_BGM = "VtvcSMZcEdE"


def get_youtube_bgm_video_id(page_key: str | None = None) -> str | None:
    if page_key:
        page_env_key = f"MAPLE_YOUTUBE_BGM_{page_key.upper()}"
        page_bgm = os.environ.get(page_env_key)
        if page_bgm is not None:
            return page_bgm.strip() or None

    env_bgm = os.environ.get("MAPLE_YOUTUBE_BGM")
    if env_bgm is None:
        return DEFAULT_YOUTUBE_BGM
    return env_bgm.strip() or None


def render_bgm_sidebar(page_key: str | None = None) -> None:
    video_id = get_youtube_bgm_video_id(page_key)
    if not video_id:
        return

    st.caption("BGM")
    render_youtube_embed(
        video_id,
        height=120,
        muted=False,
        loop=True,
        controls=True,
    )


def render_page_bgm(page_key: str | None = None) -> None:
    """Render hidden autoplay BGM for pages that use the shared layout."""
    video_id = get_youtube_bgm_video_id(page_key)
    if not video_id:
        return

    render_youtube_embed(
        video_id,
        height=1,
        muted=True,
        loop=True,
        controls=False,
        hidden=True,
    )


def render_global_bgm() -> None:
    """Backward-compatible alias for older page code."""
    render_page_bgm()
