from __future__ import annotations

import os

import streamlit as st

from app.common.youtube_embed import render_youtube_embed


DEFAULT_YOUTUBE_BGM = "VtvcSMZcEdE"


def get_youtube_bgm_video_id() -> str | None:
    env_bgm = os.environ.get("MAPLE_YOUTUBE_BGM")
    if env_bgm is None:
        return DEFAULT_YOUTUBE_BGM
    return env_bgm.strip() or None


def render_bgm_sidebar() -> None:
    video_id = get_youtube_bgm_video_id()
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


def render_global_bgm() -> None:
    """Render hidden autoplay BGM on every page that calls the shared layout."""
    video_id = get_youtube_bgm_video_id()
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
