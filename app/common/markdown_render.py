from __future__ import annotations

from html import escape
import re


INLINE_CODE_RE = re.compile(r"`([^`]+)`")
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|mailto:[^)\s]+)\)")


def markdown_to_html(markdown: str) -> str:
    """Convert common markdown answer text into safe bubble HTML."""
    lines = str(markdown).strip("\n").splitlines()
    html_parts = []
    paragraph_lines = []
    list_tag = None
    code_lines = []
    in_code_block = False

    def inline_html(text: str) -> str:
        text = escape(text)
        text = LINK_RE.sub(
            lambda match: (
                f'<a href="{match.group(2)}" target="_blank" '
                f'rel="noopener noreferrer">{match.group(1)}</a>'
            ),
            text,
        )
        text = INLINE_CODE_RE.sub(r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
        return text

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        html_parts.append(f"<p>{'<br>'.join(inline_html(line) for line in paragraph_lines)}</p>")
        paragraph_lines.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            html_parts.append(f"</{list_tag}>")
            list_tag = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                html_parts.append(f"<pre><code>{escape('\n'.join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code_block = False
            else:
                flush_paragraph()
                close_list()
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            close_list()
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            html_parts.append(f"<h{level}>{inline_html(heading.group(2))}</h{level}>")
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if bullet or ordered:
            flush_paragraph()
            next_list_tag = "ul" if bullet else "ol"
            if list_tag != next_list_tag:
                close_list()
                list_tag = next_list_tag
                html_parts.append(f"<{list_tag}>")
            html_parts.append(f"<li>{inline_html((bullet or ordered).group(1))}</li>")
            continue

        close_list()
        paragraph_lines.append(line)

    if in_code_block:
        html_parts.append(f"<pre><code>{escape('\n'.join(code_lines))}</code></pre>")

    flush_paragraph()
    close_list()
    return "".join(html_parts)
