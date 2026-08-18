import html
import re
from typing import Any


def strip_html(value: str) -> str:
    """Convert RSS HTML summary or content to clean readable text."""
    if not value:
        return ""

    value = str(value)
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    value = re.sub(r"(?i)</div\s*>", "\n", value)
    value = re.sub(r"(?i)</li\s*>", "\n", value)
    value = re.sub(r"(?i)</h[1-6]\s*>", "\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)

    lines = [line.strip() for line in value.splitlines() if line.strip()]
    value = "\n".join(lines)
    value = re.sub(r"[^\S\n]+", " ", value)
    return value.strip()


def format_entry(
    feed_name: str, entry: Any, summary_max_chars: int = 500
) -> tuple[str, str]:
    title = strip_html(str(getattr(entry, "title", "Untitled")))
    link = str(getattr(entry, "link", "") or "")
    summary_raw = (
        getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
    )
    summary = strip_html(str(summary_raw))

    if summary_max_chars > 0 and len(summary) > summary_max_chars:
        summary = summary[: max(summary_max_chars - 3, 0)] + "..."

    body_parts = [f"[{feed_name}] {title}"]
    if link:
        body_parts.append(link)
    if summary:
        body_parts.append(summary)
    body = "\n\n".join(body_parts)

    safe_feed = html.escape(feed_name)
    safe_title = html.escape(title)
    safe_link = html.escape(link)
    safe_summary = html.escape(summary).replace("\n", "<br>")

    if link:
        formatted_body = (
            f'<strong>[{safe_feed}]</strong> <a href="{safe_link}">{safe_title}</a>'
        )
    else:
        formatted_body = f"<strong>[{safe_feed}]</strong> {safe_title}"

    if safe_summary:
        formatted_body += f"<br><br>{safe_summary}"
    return body, formatted_body
