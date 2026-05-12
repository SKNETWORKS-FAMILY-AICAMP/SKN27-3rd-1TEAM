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
    hidden: bool = False,
) -> None:
    """Embed YouTube in the page; autoplay on load when ``muted`` is True."""
    src = youtube_embed_url(
        video_id,
        autoplay=True,
        muted=muted,
        controls=controls,
        loop=loop,
    )
    wrapper_style = (
        "position:fixed;left:-9999px;bottom:0;width:1px;height:1px;"
        "overflow:hidden;opacity:0;pointer-events:none;"
        if hidden
        else "overflow:hidden;border-radius:8px;line-height:0;"
    )
    iframe_width = "1" if hidden else "100%"
    iframe_height = "1" if hidden else str(height)
    component_height = 1 if hidden else height + 8
    html = f"""
<div style="{wrapper_style}">
  <iframe
    width="{iframe_width}"
    height="{iframe_height}"
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
    components.html(html, height=component_height, scrolling=False)
