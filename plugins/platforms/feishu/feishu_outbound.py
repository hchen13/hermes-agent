"""Feishu schema-2 cards and configurable markdown table rendering."""

import json
import re
from typing import Any, Dict, List

_CARD_CONFIG: Dict[str, Any] = {"width_mode": "fill", "enable_forward_interaction": True}
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*){1,}\|?\s*$")


def _build_markdown_card_payload(content: str) -> str:
    """Build a schema 2.0 interactive-card payload carrying free-form markdown."""
    return json.dumps(
        {
            "schema": "2.0",
            "config": _CARD_CONFIG,
            "body": {"elements": [{"tag": "markdown", "content": content}]},
        },
        ensure_ascii=False,
    )


def _build_image_card_payload(*, caption: str, image_key: str) -> str:
    """Build a schema 2.0 card combining a markdown caption with an image."""
    elements: List[Dict[str, Any]] = []
    caption_text = (caption or "").strip()
    if caption_text:
        elements.append({"tag": "markdown", "content": caption_text})
    elements.append(
        {
            "tag": "img",
            "img_key": image_key,
            "alt": {"tag": "plain_text", "content": ""},
        }
    )
    return json.dumps(
        {
            "schema": "2.0",
            "config": _CARD_CONFIG,
            "body": {"elements": elements},
        },
        ensure_ascii=False,
    )


def _split_pipe_row(row: str) -> List[str]:
    """Split a GFM table row on '|', stripping the outer empty cells."""
    parts = row.split("|")
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return parts


def _convert_markdown_tables(content: str, mode: str) -> str:
    """Pre-process GFM pipe tables in *content* according to *mode*."""
    if not content or mode in ("native", "off"):
        return content
    if "|" not in content or "-" not in content:
        return content

    lines = content.split("\n")
    out: List[str] = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            i += 1
            continue

        if (
            "|" in line
            and i + 1 < len(lines)
            and _TABLE_SEPARATOR_RE.match(lines[i + 1])
        ):
            header_row = line
            delimiter_row = lines[i + 1]
            body_rows: List[str] = []
            j = i + 2
            while j < len(lines):
                candidate = lines[j]
                if not candidate.strip() or "|" not in candidate:
                    break
                body_rows.append(candidate)
                j += 1

            if mode == "code":
                out.append("```")
                out.append(header_row)
                out.append(delimiter_row)
                out.extend(body_rows)
                out.append("```")
            elif mode == "bullets":
                headers = [c.strip() for c in _split_pipe_row(header_row)]
                for row in body_rows:
                    cells = [c.strip() for c in _split_pipe_row(row)]
                    if not cells:
                        continue
                    pieces: List[str] = []
                    for idx, cell in enumerate(cells):
                        header = headers[idx] if idx < len(headers) else ""
                        pieces.append(f"{header}: {cell}" if header else cell)
                    out.append("- " + ", ".join(pieces))
            else:
                out.append(header_row)
                out.append(delimiter_row)
                out.extend(body_rows)
            i = j
            continue

        out.append(line)
        i += 1

    return "\n".join(out)


def _content_has_markdown_table(content: str) -> bool:
    """Return True if *content* contains a GFM pipe table outside fenced code."""
    if "|" not in content or "-" not in content:
        return False
    lines = content.split("\n")
    in_fence = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if (
            "|" in line
            and i + 1 < len(lines)
            and _TABLE_SEPARATOR_RE.match(lines[i + 1])
        ):
            return True
    return False
