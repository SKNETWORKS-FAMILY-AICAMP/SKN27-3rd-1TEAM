from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from app.common.youtube_embed import render_youtube_embed, youtube_embed_url


DEFAULT_YOUTUBE_BGM_URL = "https://www.youtube.com/watch?v=VtvcSMZcEdE"

# 페이지별 YouTube URL 또는 video id를 여기에 직접 넣습니다.
PAGE_YOUTUBE_BGM_URLS = {
    "home": "https://www.youtube.com/watch?v=iHFSl7p9ajE",
    "chat": "https://www.youtube.com/watch?v=FcgCvoXQXTQ",
    "starforce": "https://www.youtube.com/watch?v=tRPnNoCth2c&list=RDtRPnNoCth2c&start_radio=1",
    "game": "https://www.youtube.com/watch?v=qE2Cwbzqvww&list=RDqE2Cwbzqvww&start_radio=1",
    "lounge": DEFAULT_YOUTUBE_BGM_URL,
    "models": DEFAULT_YOUTUBE_BGM_URL,
    "history": DEFAULT_YOUTUBE_BGM_URL,
    "party": DEFAULT_YOUTUBE_BGM_URL,
    "quest": DEFAULT_YOUTUBE_BGM_URL,
    "settings": DEFAULT_YOUTUBE_BGM_URL,
}


def get_youtube_bgm_source(page_key: str | None = None) -> str | None:
    if page_key:
        page_bgm = PAGE_YOUTUBE_BGM_URLS.get(page_key)
        if page_bgm is not None:
            return page_bgm.strip() or None

    return DEFAULT_YOUTUBE_BGM_URL


def render_bgm_sidebar(page_key: str | None = None) -> None:
    video_source = get_youtube_bgm_source(page_key)
    if not video_source:
        return

    st.caption("BGM")
    render_youtube_embed(
        video_source,
        height=120,
        muted=False,
        loop=True,
        controls=True,
    )


def render_page_bgm(page_key: str | None = None) -> None:
    """Prepare the page BGM player and keep it paused until the user presses play."""
    video_source = get_youtube_bgm_source(page_key)
    if not video_source:
        return

    paused_src = youtube_embed_url(
        video_source,
        autoplay=False,
        muted=True,
        loop=True,
        controls=False,
    )
    playing_src = youtube_embed_url(
        video_source,
        autoplay=True,
        muted=False,
        loop=True,
        controls=False,
    )

    components.html(
        f"""
<script>
(() => {{
  const parentDoc = window.parent.document;
  const parentWin = window.parent;
  const STORAGE_KEY = "mapleBgmState";
  const WRAP_ID = "maple-bgm-player-wrap";
  const IFRAME_ID = "maple-bgm-player";
  const pausedSrc = {json.dumps(paused_src)};
  const playingSrc = {json.dumps(playing_src)};
  const isPlaying = parentWin.sessionStorage.getItem(STORAGE_KEY) === "playing";
  const currentSrc = isPlaying ? playingSrc : pausedSrc;

  let wrapper = parentDoc.getElementById(WRAP_ID);
  if (!wrapper) {{
    wrapper = parentDoc.createElement("div");
    wrapper.id = WRAP_ID;
    Object.assign(wrapper.style, {{
      position: "fixed",
      left: "-9999px",
      bottom: "0",
      width: "1px",
      height: "1px",
      overflow: "hidden",
      opacity: "0",
      pointerEvents: "none",
    }});
    parentDoc.body.appendChild(wrapper);
  }}

  let iframe = parentDoc.getElementById(IFRAME_ID);
  if (!iframe) {{
    iframe = parentDoc.createElement("iframe");
    iframe.id = IFRAME_ID;
    iframe.width = "1";
    iframe.height = "1";
    iframe.title = "BGM";
    iframe.frameBorder = "0";
    iframe.allow = "autoplay; encrypted-media";
    iframe.referrerPolicy = "strict-origin-when-cross-origin";
    iframe.style.display = "block";
    wrapper.appendChild(iframe);
  }}

  iframe.dataset.pausedSrc = pausedSrc;
  iframe.dataset.playingSrc = playingSrc;
  if (iframe.src !== currentSrc) {{
    iframe.src = currentSrc;
  }}

  const sendCommand = (func, args = []) => {{
    if (!iframe.contentWindow) return;
    iframe.contentWindow.postMessage(
      JSON.stringify({{ event: "command", func, args }}),
      "*"
    );
  }};

  const applyState = () => {{
    if (parentWin.sessionStorage.getItem(STORAGE_KEY) === "playing") {{
      sendCommand("unMute");
      sendCommand("setVolume", [80]);
      sendCommand("playVideo");
    }} else {{
      sendCommand("pauseVideo");
    }}
  }};

  [250, 900, 1900, 3500].forEach((delay) => {{
    parentWin.setTimeout(applyState, delay);
  }});
}})();
</script>
""",
        height=0,
    )


def render_global_bgm() -> None:
    """Backward-compatible alias for older page code."""
    render_page_bgm()


def render_bgm_control_button() -> None:
    """Render the fixed BGM play/pause button shared by non-game pages."""
    components.html(
        """
<script>
(() => {
  const parentDoc = window.parent.document;
  const parentWin = window.parent;
  const STORAGE_KEY = "mapleBgmState";
  const BTN_ID = "maple-bgm-toggle";
  const IFRAME_ID = "maple-bgm-player";

  const ICON_PLAY = "▶";
  const ICON_PAUSE = "⏸";

  const getState = () => parentWin.sessionStorage.getItem(STORAGE_KEY) || "paused";
  const setState = (state) => parentWin.sessionStorage.setItem(STORAGE_KEY, state);
  const findBgmIframe = () => parentDoc.getElementById(IFRAME_ID);

  const sendCommand = (func, args = []) => {
    const iframe = findBgmIframe();
    if (!iframe?.contentWindow) return false;
    try {
      iframe.contentWindow.postMessage(
        JSON.stringify({ event: "command", func, args }),
        "*"
      );
      return true;
    } catch (e) {
      return false;
    }
  };

  const applyState = () => {
    const iframe = findBgmIframe();
    if (!iframe) return;

    if (getState() === "playing") {
      if (iframe.dataset.playingSrc && iframe.src !== iframe.dataset.playingSrc) {
        iframe.src = iframe.dataset.playingSrc;
        parentWin.setTimeout(applyState, 350);
        return;
      }
      sendCommand("unMute");
      sendCommand("setVolume", [80]);
      sendCommand("playVideo");
    } else {
      sendCommand("pauseVideo");
    }
  };

  const existing = parentDoc.getElementById(BTN_ID);
  if (existing) existing.remove();

  const btn = parentDoc.createElement("button");
  btn.id = BTN_ID;
  btn.type = "button";
  btn.setAttribute("aria-label", "BGM 재생/일시정지");
  Object.assign(btn.style, {
    position: "fixed",
    top: "0.55rem",
    right: "1rem",
    width: "2.1rem",
    height: "2.1rem",
    border: "1px solid rgba(255, 200, 137, 0.55)",
    borderRadius: "999px",
    background: "rgba(0, 0, 0, 0.55)",
    color: "#ffc889",
    cursor: "pointer",
    zIndex: "200",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "0.95rem",
    fontFamily: "MaplestoryBold, Inter, ui-sans-serif, system-ui, sans-serif",
    padding: "0",
    boxShadow: "0 6px 18px rgba(0, 0, 0, 0.35)",
    lineHeight: "1",
  });

  const updateButtonUi = () => {
    btn.textContent = getState() === "playing" ? ICON_PAUSE : ICON_PLAY;
  };

  btn.addEventListener("click", () => {
    const next = getState() === "playing" ? "paused" : "playing";
    setState(next);
    updateButtonUi();
    applyState();
  });

  btn.addEventListener("mouseenter", () => {
    btn.style.background = "rgba(70, 43, 18, 0.78)";
  });
  btn.addEventListener("mouseleave", () => {
    btn.style.background = "rgba(0, 0, 0, 0.55)";
  });

  parentDoc.body.appendChild(btn);
  updateButtonUi();

  [250, 900, 1900, 3500].forEach((delay) => {
    parentWin.setTimeout(applyState, delay);
  });
})();
</script>
""",
        height=0,
    )
