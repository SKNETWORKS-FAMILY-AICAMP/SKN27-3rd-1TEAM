"""앱 전역에서 사용되는 BGM(배경음악) 재생 모듈.

YouTube 영상을 숨겨진 iframe 으로 임베드하여 페이지별 배경음악을 재생합니다.
사이드바용 임베드, 페이지 전역 BGM 플레이어, 그리고 우상단 재생/일시정지 토글 버튼을
렌더링하는 함수들을 제공합니다. 재생 상태는 브라우저의 ``sessionStorage`` 에 저장되어
페이지 전환 시에도 유지됩니다.
"""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from app.common.youtube_embed import render_youtube_embed, youtube_embed_url


# === BGM 소스 설정 ===

# 페이지별 매핑이 없을 때 사용할 기본 YouTube BGM URL
DEFAULT_YOUTUBE_BGM_URL = "https://www.youtube.com/watch?v=VtvcSMZcEdE"

# 페이지별 YouTube URL 또는 video id를 여기에 직접 넣습니다.
# 키는 페이지 식별자(page_key) 이며, 값은 해당 페이지에서 재생할 BGM URL.
PAGE_YOUTUBE_BGM_URLS = {
    "home": "https://www.youtube.com/watch?v=iHFSl7p9ajE",
    "chat": "https://www.youtube.com/watch?v=FcgCvoXQXTQ",
    "starforce": "https://www.youtube.com/watch?v=tRPnNoCth2c&list=RDtRPnNoCth2c&start_radio=1",
    "game": "https://www.youtube.com/watch?v=qE2Cwbzqvww&list=RDqE2Cwbzqvww&start_radio=1",
}


# === BGM 소스 선택 ===


def get_youtube_bgm_source(page_key: str | None = None) -> str | None:
    """주어진 페이지 키에 해당하는 YouTube BGM URL 을 반환한다.

    페이지별 매핑(``PAGE_YOUTUBE_BGM_URLS``)에 값이 있으면 이를 우선 사용하고,
    값이 비어 있거나 매핑이 없으면 기본 BGM URL 로 폴백한다.
    """
    if page_key:
        # 페이지별 매핑 우선 조회
        page_bgm = PAGE_YOUTUBE_BGM_URLS.get(page_key)
        if page_bgm is not None:
            # 공백만 있는 값은 ``None`` 으로 취급하여 BGM 비활성화
            return page_bgm.strip() or None

    # 매핑이 없는 페이지는 기본 BGM 사용
    return DEFAULT_YOUTUBE_BGM_URL


# === 사이드바 BGM 렌더링 ===


def render_bgm_sidebar(page_key: str | None = None) -> None:
    """사이드바에 보이는 작은 BGM 플레이어를 렌더링한다.

    사용자가 직접 컨트롤할 수 있는 일반 YouTube 임베드 형태이며,
    BGM 소스가 없으면 아무것도 출력하지 않는다.
    """
    video_source = get_youtube_bgm_source(page_key)
    if not video_source:
        # BGM 이 비활성화된 페이지에서는 사이드바 위젯도 생략
        return

    st.caption("BGM")
    # 사이드바용 플레이어는 사용자가 직접 조작하도록 컨트롤을 표시
    render_youtube_embed(
        video_source,
        height=120,
        muted=False,
        loop=True,
        controls=True,
    )


# === 페이지 전역 BGM 플레이어 ===


def render_page_bgm(page_key: str | None = None) -> None:
    """Prepare the page BGM player and keep it paused until the user presses play."""
    # 페이지 전역에서 단 하나의 숨겨진 iframe 을 생성해두고, 사용자가 재생 버튼을 누를 때까지
    # 일시정지 상태로 대기시킨다. 브라우저 자동재생 정책 회피를 위해 초기에는 mute=true 사용.
    video_source = get_youtube_bgm_source(page_key)
    if not video_source:
        return

    # 일시정지 상태에서 사용할 임베드 URL (autoplay 꺼짐, 음소거)
    paused_src = youtube_embed_url(
        video_source,
        autoplay=False,
        muted=True,
        loop=True,
        controls=False,
    )
    # 재생 상태에서 사용할 임베드 URL (autoplay 켜짐, 사운드 ON)
    playing_src = youtube_embed_url(
        video_source,
        autoplay=True,
        muted=False,
        loop=True,
        controls=False,
    )

    # 부모 문서(Streamlit 메인 페이지)에 숨겨진 iframe 을 주입하는 자바스크립트 블록.
    # ``components.html`` 의 sandbox iframe 안에서 ``window.parent`` 를 통해 접근한다.
    components.html(
        f"""
<script>
(() => {{
  // 부모(Streamlit) 문서와 윈도우 객체 - 숨겨진 iframe 을 메인 페이지에 부착하기 위함
  const parentDoc = window.parent.document;
  const parentWin = window.parent;
  // sessionStorage 키: 페이지 이동 후에도 재생 상태가 유지되도록 함
  const STORAGE_KEY = "mapleBgmState";
  const WRAP_ID = "maple-bgm-player-wrap";
  const IFRAME_ID = "maple-bgm-player";
  // 일시정지/재생 두 가지 src 를 미리 준비해두고 상태에 따라 교체 사용
  const pausedSrc = {json.dumps(paused_src)};
  const playingSrc = {json.dumps(playing_src)};
  const isPlaying = parentWin.sessionStorage.getItem(STORAGE_KEY) === "playing";
  const currentSrc = isPlaying ? playingSrc : pausedSrc;

  // 화면에서 보이지 않는 1x1 픽셀 래퍼 div 생성 (이미 있다면 재사용)
  let wrapper = parentDoc.getElementById(WRAP_ID);
  if (!wrapper) {{
    wrapper = parentDoc.createElement("div");
    wrapper.id = WRAP_ID;
    // 화면 밖으로 밀어내고 pointer-events 도 차단하여 UI 에 영향이 없도록 함
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

  // 실제 YouTube 임베드 iframe (페이지당 1개만 유지하여 끊김 없는 재생)
  let iframe = parentDoc.getElementById(IFRAME_ID);
  if (!iframe) {{
    iframe = parentDoc.createElement("iframe");
    iframe.id = IFRAME_ID;
    iframe.width = "1";
    iframe.height = "1";
    iframe.title = "BGM";
    iframe.frameBorder = "0";
    // YouTube 자동재생을 위해 autoplay/encrypted-media 권한 부여
    iframe.allow = "autoplay; encrypted-media";
    iframe.referrerPolicy = "strict-origin-when-cross-origin";
    iframe.style.display = "block";
    wrapper.appendChild(iframe);
  }}

  // 토글 버튼(``render_bgm_control_button``)에서 src 를 교체할 수 있도록 dataset 에 저장
  iframe.dataset.pausedSrc = pausedSrc;
  iframe.dataset.playingSrc = playingSrc;
  if (iframe.src !== currentSrc) {{
    iframe.src = currentSrc;
  }}

  // YouTube IFrame API 의 postMessage 프로토콜로 재생 제어 명령 전송
  const sendCommand = (func, args = []) => {{
    if (!iframe.contentWindow) return;
    iframe.contentWindow.postMessage(
      JSON.stringify({{ event: "command", func, args }}),
      "*"
    );
  }};

  // 저장된 상태에 따라 재생 또는 일시정지 명령을 일괄 전송
  const applyState = () => {{
    if (parentWin.sessionStorage.getItem(STORAGE_KEY) === "playing") {{
      sendCommand("unMute");
      sendCommand("setVolume", [80]);
      sendCommand("playVideo");
    }} else {{
      sendCommand("pauseVideo");
    }}
  }};

  // iframe 로딩 타이밍이 일정하지 않으므로 여러 시점에 반복 호출해 안정적으로 상태 적용
  [250, 900, 1900, 3500].forEach((delay) => {{
    parentWin.setTimeout(applyState, delay);
  }});
}})();
</script>
""",
        height=0,
    )


# === 하위 호환 별칭 ===


def render_global_bgm() -> None:
    """Backward-compatible alias for older page code."""
    # 기존 페이지 코드에서 ``render_global_bgm()`` 으로 호출하던 부분을 깨지 않기 위한 래퍼
    render_page_bgm()


# === BGM 재생/일시정지 토글 버튼 ===


def render_bgm_control_button() -> None:
    """Render the fixed BGM play/pause button shared by non-game pages."""
    # 화면 우상단에 고정된 원형 토글 버튼을 주입한다.
    # ``render_page_bgm`` 이 만든 숨겨진 iframe(``maple-bgm-player``)을 찾아 제어한다.
    components.html(
        """
<script>
(() => {
  const parentDoc = window.parent.document;
  const parentWin = window.parent;
  // 재생 상태 공유용 키 - render_page_bgm 과 동일한 값을 사용해야 동기화됨
  const STORAGE_KEY = "mapleBgmState";
  const BTN_ID = "maple-bgm-toggle";
  const IFRAME_ID = "maple-bgm-player";

  // 버튼 라벨 - 현재 상태에 따라 교체 표시
  const ICON_PLAY = "▶";
  const ICON_PAUSE = "⏸";

  // sessionStorage 기반 상태 getter/setter (기본값은 "paused")
  const getState = () => parentWin.sessionStorage.getItem(STORAGE_KEY) || "paused";
  const setState = (state) => parentWin.sessionStorage.setItem(STORAGE_KEY, state);
  // render_page_bgm 이 생성한 BGM iframe 을 ID 로 찾는다
  const findBgmIframe = () => parentDoc.getElementById(IFRAME_ID);

  // YouTube IFrame API 로 명령 전송. iframe 이 없거나 실패하면 false 반환.
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

  // 현재 저장된 상태를 iframe 에 실제로 반영한다
  const applyState = () => {
    const iframe = findBgmIframe();
    if (!iframe) return;

    if (getState() === "playing") {
      // 일시정지 src 상태였다면 재생용 src 로 교체 후, 로드 대기를 위해 잠시 후 재시도
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

  // Streamlit 리렌더 시 버튼이 중복 생성되지 않도록 기존 버튼 제거
  const existing = parentDoc.getElementById(BTN_ID);
  if (existing) existing.remove();

  // 우상단 고정 버튼 생성
  const btn = parentDoc.createElement("button");
  btn.id = BTN_ID;
  btn.type = "button";
  btn.setAttribute("aria-label", "BGM 재생/일시정지");
  // 메이플 테마 컬러(주황 톤)와 둥근 형태로 스타일링
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

  // 상태에 맞게 아이콘(▶ / ⏸) 갱신
  const updateButtonUi = () => {
    btn.textContent = getState() === "playing" ? ICON_PAUSE : ICON_PLAY;
  };

  // 클릭 시 상태 토글 → UI 갱신 → 실제 재생 제어 적용
  btn.addEventListener("click", () => {
    const next = getState() === "playing" ? "paused" : "playing";
    setState(next);
    updateButtonUi();
    applyState();
  });

  // 호버 시 살짝 밝아지는 인터랙션
  btn.addEventListener("mouseenter", () => {
    btn.style.background = "rgba(70, 43, 18, 0.78)";
  });
  btn.addEventListener("mouseleave", () => {
    btn.style.background = "rgba(0, 0, 0, 0.55)";
  });

  parentDoc.body.appendChild(btn);
  updateButtonUi();

  // BGM iframe 이 늦게 마운트될 수 있으므로 여러 시점에 상태를 재적용
  [250, 900, 1900, 3500].forEach((delay) => {
    parentWin.setTimeout(applyState, delay);
  });
})();
</script>
""",
        height=0,
    )
