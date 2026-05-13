
from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

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


def render_bgm_control_button() -> None:
    """페이지 상단 우측에 BGM 재생/일시정지 버튼을 띄웁니다.

    버튼 상태는 sessionStorage("mapleBgmState")에 저장되므로 페이지를
    이동해도 동일한 재생/일시정지 상태가 유지됩니다.
    """
    components.html(
        """
<script>
(() => {
  const parentDoc = window.parent.document;
  const parentWin = window.parent;
  const STORAGE_KEY = "mapleBgmState";
  const BTN_ID = "maple-bgm-toggle";

  const ICON_PLAY = "▶";
  const ICON_PAUSE = "⏸";

  const getState = () => parentWin.sessionStorage.getItem(STORAGE_KEY) || "paused";
  const setState = (state) => parentWin.sessionStorage.setItem(STORAGE_KEY, state);

  const findBgmIframe = () => {
    const iframes = parentDoc.querySelectorAll('iframe[src*="youtube.com/embed"]');
    for (const frame of iframes) {
      const wrapper = frame.parentElement;
      const style = wrapper ? wrapper.getAttribute("style") || "" : "";
      if (style.includes("-9999")) return frame;
    }
    return iframes[iframes.length - 1] || null;
  };

  const sendCommand = (func, args = []) => {
    const iframe = findBgmIframe();
    if (!iframe || !iframe.contentWindow) return false;
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
    if (getState() === "playing") {
      sendCommand("unMute");
      sendCommand("setVolume", [80]);
      sendCommand("playVideo");
    } else {
      sendCommand("pauseVideo");
    }
  };

  // 기존 버튼 제거(재실행 시 중복 방지)
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

  // 새 iframe 로딩 타이밍을 고려해 상태를 여러 번 적용합니다.
  [250, 900, 1900, 3500].forEach((delay) => {
    parentWin.setTimeout(applyState, delay);
  });
})();
</script>
""",
        height=0,
    )
