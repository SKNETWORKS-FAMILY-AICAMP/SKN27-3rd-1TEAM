from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import streamlit.components.v1 as components


def extract_youtube_video_id(source: str) -> str:
    source = source.strip()
    if not source:
        return ""

    parsed = urlparse(source)
    if not parsed.netloc:
        return source

    host = parsed.netloc.lower().removeprefix("www.")
    if host == "youtu.be":
        return parsed.path.strip("/")
    if "youtube.com" in host:
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/", 1)[1].split("/", 1)[0]
        query_video_id = parse_qs(parsed.query).get("v", [""])[0]
        if query_video_id:
            return query_video_id

    return source


def youtube_embed_url(
    video_source: str,
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
    video_id = extract_youtube_video_id(video_source)
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
        "enablejsapi=1",
    ]
    if loop:
        q.extend(["loop=1", f"playlist={video_id}"])
    return f"https://www.youtube.com/embed/{video_id}?{'&'.join(q)}"


def render_youtube_embed(
    video_source: str,
    *,
    height: int = 88,
    autoplay: bool = True,
    muted: bool = True,
    loop: bool = False,
    controls: bool = False,
    hidden: bool = False,
    unlock_on_interaction: bool = False,
) -> None:
    """Embed YouTube in the page; autoplay on load when ``muted`` is True."""
    start_muted = muted or unlock_on_interaction
    src = youtube_embed_url(
        video_source,
        autoplay=autoplay,
        muted=start_muted,
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
    unlock_script = ""
    if unlock_on_interaction:
        unlock_script = """
<script>
(() => {
  const parentWindow = window.parent;
  const parentDocument = parentWindow.document;
  const player = document.querySelector("iframe");
  const stateKey = "__mapleBgmUnlock";

  if (parentWindow[stateKey]?.cleanup) {
    parentWindow[stateKey].cleanup();
  }

  const command = (func, args = []) => {
    if (!player?.contentWindow) return;
    player.contentWindow.postMessage(JSON.stringify({
      event: "command",
      func,
      args,
    }), "*");
  };

  let warmupCount = 0;
  const warmupTimer = window.setInterval(() => {
    warmupCount += 1;
    command("mute");
    command("playVideo");
    if (warmupCount >= 8) {
      window.clearInterval(warmupTimer);
    }
  }, 600);

  const unlock = () => {
    command("unMute");
    command("setVolume", [80]);
    command("playVideo");
    window.setTimeout(() => {
      command("unMute");
      command("playVideo");
    }, 250);
    cleanup();
  };

  const cleanup = () => {
    window.clearInterval(warmupTimer);
    parentDocument.removeEventListener("pointerdown", unlock, true);
    parentDocument.removeEventListener("keydown", unlock, true);
    parentWindow.removeEventListener("pointerdown", unlock, true);
    parentWindow.removeEventListener("keydown", unlock, true);
    if (parentWindow[stateKey]?.cleanup === cleanup) {
      parentWindow[stateKey] = null;
    }
  };

  parentDocument.addEventListener("pointerdown", unlock, true);
  parentDocument.addEventListener("keydown", unlock, true);
  parentWindow.addEventListener("pointerdown", unlock, true);
  parentWindow.addEventListener("keydown", unlock, true);
  parentWindow[stateKey] = { cleanup };
})();
</script>
"""
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
{unlock_script}
"""
    components.html(html, height=component_height, scrolling=False)
