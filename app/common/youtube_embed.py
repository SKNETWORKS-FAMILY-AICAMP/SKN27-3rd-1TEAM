from __future__ import annotations

import streamlit.components.v1 as components


def youtube_embed_url(
    video_id: str,
    *,
    autoplay: bool = True,
    muted: bool = True,
    controls: bool = False,
    loop: bool = False,
) -> str:
    """Build a YouTube embed URL for Streamlit iframe.

    Browsers typically block autoplay with sound; keep ``muted=True`` for reliable
    autoplay on page load. Users can unmute from the player if YouTube shows it;
    with ``controls=False`` the UI is minimal (no control bar).
    """
    q = [
        f"autoplay={1 if autoplay else 0}",
        f"mute={1 if muted else 0}",
        f"controls={1 if controls else 0}",
        "modestbranding=1",
        "playsinline=1",
        "rel=0",
        "fs=0",
        "disablekb=1",
        "iv_load_policy=3",
    ]
    if loop:
        q.extend(["loop=1", f"playlist={video_id}"])
    return f"https://www.youtube.com/embed/{video_id}?{'&'.join(q)}"


def render_youtube_embed(
    video_id: str,
    *,
    height: int = 88,
    muted: bool = True,
    loop: bool = False,
    controls: bool = False,
) -> None:
    """Embed YouTube in the page; autoplay on load when ``muted`` is True."""
    src = youtube_embed_url(
        video_id,
        autoplay=True,
        muted=muted,
        controls=controls,
        loop=loop,
    )
    html = f"""
<div style="overflow:hidden;border-radius:8px;line-height:0;">
  <iframe
    width="100%"
    height="{height}"
    src="{src}"
    title="YouTube"
    frameborder="0"
    loading="eager"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
    referrerpolicy="strict-origin-when-cross-origin"
    style="display:block;"
  ></iframe>
</div>
"""
    components.html(html, height=height + 8, scrolling=False)
