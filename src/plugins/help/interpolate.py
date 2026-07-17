"""Resolve ``{{tr:dotted.key}}`` placeholders against app/tab i18n packs.

See docs/dev/HELP_SYSTEM.md § Language keys for the authoring contract.
"""

from __future__ import annotations

import re

from resources.translations import tr

_TR_PLACEHOLDER_RE = re.compile(r"\{\{tr:([a-zA-Z0-9_.]+)\}\}")


def interpolate_help_markdown(text: str, language: str) -> str:
    """Replace ``{{tr:key}}`` with ``tr(key)`` for ``language``."""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = tr(key, language=language)
        if not value or value == key:
            return key
        return value

    return _TR_PLACEHOLDER_RE.sub(_replace, text)
