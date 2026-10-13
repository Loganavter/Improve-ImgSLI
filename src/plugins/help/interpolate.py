"""Resolve Help markdown placeholders.

- ``{{tr:dotted.key}}`` → UI / tab i18n string for the active language

Images are plain body-relative paths (web canon) — no slot registry.

See docs/dev/HELP_SYSTEM.md § Language keys.
"""

from __future__ import annotations

import re

from resources.translations import tr

_TR_PLACEHOLDER_RE = re.compile(r"\{\{tr:([a-zA-Z0-9_.]+)\}\}")


def interpolate_help_markdown(text: str, language: str) -> str:
    """Replace ``{{tr:…}}`` placeholders in a Help body."""

    def _replace_tr(match: re.Match[str]) -> str:
        key = match.group(1)
        value = tr(key, language=language)
        if not value or value == key:
            return key
        return value

    return _TR_PLACEHOLDER_RE.sub(_replace_tr, text)
