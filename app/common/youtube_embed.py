"""유튜브 영상을 Streamlit 페이지에 iframe 으로 임베드하는 유틸.

주된 용도는 페이지 BGM. 영상은 화면 밖에 숨긴 채 음악만 재생한다.
브라우저 자동재생 정책상 ``muted`` 상태일 때만 자동재생이 허용되므로,
사용자의 첫 클릭/키 입력을 기다렸다가 ``unMute`` 호출로 소리를 켠다.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import streamlit.components.v1 as components


def extract_youtube_video_id(source: str) -> str:
    """다양한 형태의 유튜브 URL/ID 입력에서 11자리 video_id 를 추출."""
    source = source.strip()
    if not source:
        return ""

    parsed = urlparse(source)
    # URL 이 아니라 그냥 video_id 만 들어온 경우 그대로 반환
    if not parsed.netloc:
        return source

    # 도메인의 'www.' 접두사는 제거하고 소문자로 통일
    host = parsed.netloc.lower().removeprefix("www.")
    # 단축 URL 형태: https://youtu.be/VIDEO_ID
    if host == "youtu.be":
        return parsed.path.strip("/")
    # 일반 URL 형태: https://www.youtube.com/watch?v=VIDEO_ID 또는 /embed/VIDEO_ID
    if "youtube.com" in host:
        if parsed.path.startswith("/embed/"):
            # /embed/{id}/... 형태에서 id 만 추출
            return parsed.path.split("/embed/", 1)[1].split("/", 1)[0]
        # 쿼리스트링의 v 파라미터 사용
        query_video_id = parse_qs(parsed.query).get("v", [""])[0]
        if query_video_id:
            return query_video_id

    # 매칭이 안되면 원문을 그대로 반환(예외 케이스)
    return source


def youtube_embed_url(
    video_source: str,
    *,
    autoplay: bool = True,
    muted: bool = True,
    controls: bool = False,
    loop: bool = False,
) -> str:
    """Streamlit iframe에 넣을 YouTube embed URL을 만든다.

    브라우저는 소리가 켜진 자동재생을 대부분 차단하므로,
    페이지 로드 시 자동재생이 필요하면 muted=True가 안정적이다.
    """
    video_id = extract_youtube_video_id(video_source)
    # iframe URL 쿼리 파라미터 구성
    q = [
        f"autoplay={1 if autoplay else 0}",          # 자동재생 여부
        f"mute={1 if muted else 0}",                 # 음소거 여부(자동재생 허용 조건)
        f"controls={1 if controls else 0}",          # 재생 컨트롤 표시 여부
        "modestbranding=1",                          # 유튜브 로고 최소화
        "playsinline=1",                             # 모바일에서 인라인 재생
        "rel=0",                                     # 끝난 후 관련 영상 노출 안함
        "fs=0",                                      # 전체화면 버튼 비활성
        "disablekb=1",                               # 키보드 컨트롤 비활성
        "iv_load_policy=3",                          # 어노테이션 비표시
        "enablejsapi=1",                             # JS API 활성(외부에서 postMessage 제어용)
    ]
    if loop:
        # 단일 영상을 반복재생하려면 playlist 파라미터에 자기 자신을 지정해야 함(유튜브 사양)
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
    """YouTube iframe을 Streamlit 컴포넌트로 주입한다."""
    # hidden + unlock_on_interaction 조합이면 화면에는 안 보이지만 BGM 재생만 노린 케이스
    start_muted = muted or unlock_on_interaction
    src = youtube_embed_url(
        video_source,
        autoplay=autoplay,
        muted=start_muted,
        controls=controls,
        loop=loop,
    )

    # 숨김 모드: 화면 밖으로 보내고 1x1 픽셀로 만든다 (오디오만 재생용)
    # 표시 모드: 둥근 모서리 카드 형태로 표시
    wrapper_style = (
        "position:fixed;left:-9999px;bottom:0;width:1px;height:1px;"
        "overflow:hidden;opacity:0;pointer-events:none;"
        if hidden
        else "overflow:hidden;border-radius:8px;line-height:0;"
    )
    iframe_width = "1" if hidden else "100%"
    iframe_height = "1" if hidden else str(height)
    # Streamlit components 컨테이너 높이(여유 8px)
    component_height = 1 if hidden else height + 8

    # === 자동재생 사운드 해제 스크립트 ===
    # 브라우저는 사용자 상호작용 없이 소리가 나오는 자동재생을 차단한다.
    # 따라서 처음에는 muted 로 시작하고, 첫 클릭/키 입력이 발생하면
    # postMessage 로 unMute + playVideo 를 호출해 소리를 켠다.
    unlock_script = ""
    if unlock_on_interaction:
        unlock_script = """
<script>
(() => {
  const parentWindow = window.parent;
  const parentDocument = parentWindow.document;
  const player = document.querySelector("iframe");
  // 페이지 이동 후 중복 등록을 막기 위해 전역 상태 키를 사용
  const stateKey = "__mapleBgmUnlock";

  // 이전 페이지에서 등록된 리스너가 있으면 먼저 정리
  if (parentWindow[stateKey]?.cleanup) {
    parentWindow[stateKey].cleanup();
  }

  // iframe 의 YouTube 플레이어에 명령 전송하는 헬퍼
  const command = (func, args = []) => {
    if (!player?.contentWindow) return;
    player.contentWindow.postMessage(JSON.stringify({
      event: "command",
      func,
      args,
    }), "*");
  };

  // 페이지 로드 직후엔 iframe 이 아직 준비 안된 경우가 많아
  // 짧은 주기로 mute+playVideo 를 반복 호출해 워밍업 한다.
  let warmupCount = 0;
  const warmupTimer = window.setInterval(() => {
    warmupCount += 1;
    command("mute");
    command("playVideo");
    if (warmupCount >= 8) {
      window.clearInterval(warmupTimer);
    }
  }, 600);

  // 사용자 상호작용 시 호출: 소리 켜고 볼륨 80 으로 설정
  const unlock = () => {
    command("unMute");
    command("setVolume", [80]);
    command("playVideo");
    // 일부 브라우저에서 한 번에 안 풀리는 경우가 있어 짧은 지연 후 재시도
    window.setTimeout(() => {
      command("unMute");
      command("playVideo");
    }, 250);
    cleanup();
  };

  // 리스너 해제 + 워밍업 중단
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

  // 캡처 단계에서 가장 먼저 잡기 위해 capture=true
  parentDocument.addEventListener("pointerdown", unlock, true);
  parentDocument.addEventListener("keydown", unlock, true);
  parentWindow.addEventListener("pointerdown", unlock, true);
  parentWindow.addEventListener("keydown", unlock, true);
  parentWindow[stateKey] = { cleanup };
})();
</script>
"""
    # 최종 HTML: iframe + (옵션) 자동 해제 스크립트
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
    # Streamlit components 로 HTML 주입(스크롤 비활성)
    components.html(html, height=component_height, scrolling=False)
