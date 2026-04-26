"""Strip markdown / social-style markers for TTS. Keep in sync with subtitles/src/clean-script-text.ts."""

from __future__ import annotations

import re


def clean_for_narration(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""

    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n#{1,6}\s+", "\n", s)

    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)

    s = re.sub(r"(^|[\s([{<'\"])#([A-Za-z][A-Za-z0-9_-]*)", r"\1\2", s)

    s = re.sub(r"\bhashtag\b", "", s, flags=re.IGNORECASE)

    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)

    s = re.sub(r"^-{3,}\s*$", "", s, flags=re.MULTILINE)

    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_skippable_script_line(raw: str) -> bool:
    s = str(raw or "").strip()
    if not s:
        return True
    if re.match(r"^#{1,6}\s*seg_\d+\s*$", s, re.I):
        return True
    if re.match(r"^#{1,6}\s*walrus", s, re.I) and re.search(r"script", s, re.I):
        return True
    c = clean_for_narration(s)
    if re.match(r"^seg_\d+$", c, re.I):
        return True
    if len(c) < 22 and not re.search(r"[.!?]", c):
        return True
    return False
