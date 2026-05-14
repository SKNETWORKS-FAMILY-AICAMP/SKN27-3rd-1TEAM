"""에이전트 응답 텍스트(간이 마크다운) → 채팅 버블 HTML 변환기.

전체 마크다운 스펙을 따르지 않고, 챗봇 답변에서 자주 쓰이는 요소만 처리한다:
- 헤딩 (#, ##, ###)
- 순서/비순서 리스트
- 코드 블록 (``` ... ```)
- 인라인 코드 (`code`)
- 링크, 볼드(**), 이탤릭(*)
- 일반 단락 (빈 줄로 구분)
"""

from __future__ import annotations

from html import escape
import re


# 인라인 코드: `text` → <code>text</code>
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
# 링크: [라벨](https://... 또는 mailto:...)
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|mailto:[^)\s]+)\)")


def markdown_to_html(markdown: str) -> str:
    """Convert common markdown answer text into safe bubble HTML."""
    # 앞뒤 개행 제거 후 라인 단위로 처리
    lines = str(markdown).strip("\n").splitlines()

    html_parts: list[str] = []          # 최종 HTML 조각들 누적
    paragraph_lines: list[str] = []     # 단락에 누적 중인 라인들
    list_tag: str | None = None         # 현재 열려있는 리스트 태그 (ul/ol)
    code_lines: list[str] = []          # 코드 블록 내부 라인 누적
    in_code_block = False               # ``` 코드 블록 안에 있는지 여부

    def inline_html(text: str) -> str:
        """한 줄 내 인라인 마크업(링크/코드/볼드/이탤릭)을 HTML 로 변환."""
        # 1) 가장 먼저 HTML 이스케이프(XSS 방지)
        text = escape(text)
        # 2) [label](url) → <a href="url" target="_blank">label</a>
        text = LINK_RE.sub(
            lambda match: (
                f'<a href="{match.group(2)}" target="_blank" '
                f'rel="noopener noreferrer">{match.group(1)}</a>'
            ),
            text,
        )
        # 3) `code` → <code>code</code>
        text = INLINE_CODE_RE.sub(r"<code>\1</code>", text)
        # 4) **bold** → <strong>
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        # 5) *italic* → <em>  (양옆이 * 가 아닐 때만)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
        return text

    def flush_paragraph() -> None:
        """누적된 단락 라인들을 <p> 태그로 출력하고 버퍼 비우기."""
        if not paragraph_lines:
            return
        # 단락 내 줄바꿈은 <br> 로 표현
        html_parts.append(f"<p>{'<br>'.join(inline_html(line) for line in paragraph_lines)}</p>")
        paragraph_lines.clear()

    def close_list() -> None:
        """열려있는 <ul>/<ol> 가 있으면 닫는다."""
        nonlocal list_tag
        if list_tag:
            html_parts.append(f"</{list_tag}>")
            list_tag = None

    for line in lines:
        stripped = line.strip()

        # === 코드 블록 시작/종료(```) 처리 ===
        if stripped.startswith("```"):
            if in_code_block:
                # 닫는 ``` → 코드 라인들을 <pre><code> 로 출력
                html_parts.append(f"<pre><code>{escape('\n'.join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code_block = False
                continue

            # 여는 ``` → 진행 중인 단락/리스트 먼저 마무리
            flush_paragraph()
            close_list()
            in_code_block = True
            continue

        # 코드 블록 내부는 마크다운 해석하지 않고 그대로 누적
        if in_code_block:
            code_lines.append(line)
            continue

        # === 빈 줄 → 단락 구분 ===
        if not stripped:
            flush_paragraph()
            close_list()
            continue

        # === 헤딩 (#, ##, ###) ===
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))  # 1~3 단계
            html_parts.append(f"<h{level}>{inline_html(heading.group(2))}</h{level}>")
            continue

        # === 리스트 항목 ===
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)        # 비순서: -, *
        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)      # 순서: 1. 2. ...
        if bullet or ordered:
            flush_paragraph()
            next_list_tag = "ul" if bullet else "ol"
            # 리스트 종류가 바뀌면 기존 리스트를 닫고 새로 연다
            if list_tag != next_list_tag:
                close_list()
                list_tag = next_list_tag
                html_parts.append(f"<{list_tag}>")
            html_parts.append(f"<li>{inline_html((bullet or ordered).group(1))}</li>")
            continue

        # === 일반 텍스트 라인 → 단락 버퍼에 누적 ===
        close_list()
        paragraph_lines.append(line)

    # === 루프 종료 후 잔여 처리 ===
    # 닫히지 않은 코드 블록이 있다면 마저 출력
    if in_code_block:
        html_parts.append(f"<pre><code>{escape('\n'.join(code_lines))}</code></pre>")

    flush_paragraph()
    close_list()
    return "".join(html_parts)
