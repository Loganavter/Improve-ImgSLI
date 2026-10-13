"""Leading page frontmatter: card ``description`` and ``icon``.

A help body may open with a minimal, YAML-like block::

    ---
    description: One short card line, no markup
    icon: settings.svg
    ---
    ## Title

Only ``description`` (plain text, no inline markup) and ``icon`` (a name the
package icon resolver understands) are recognised; unknown keys are ignored
so the block can grow later without breaking older readers. The block must be
the very first thing in the file and must close with a line that is exactly
``---``.

CRLF, a missing block, missing keys and an unterminated block are all
tolerated — in those cases the body is returned unchanged, so the
"verbatim body" render contract holds for bodies authored before the
frontmatter wave.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Recognised frontmatter keys (frozen authoring interface).
_FRONTMATTER_KEYS = ("description", "icon")

_DELIM = "---"


@dataclass(frozen=True, slots=True)
class PageMeta:
    """Presentation carried by a page's leading frontmatter block."""

    description: str = ""
    icon: str = ""


def split_frontmatter(markdown: str) -> tuple[PageMeta, str]:
    """Split a leading frontmatter block off ``markdown``.

    Returns ``(meta, body)`` where ``body`` is ``markdown`` with the block and
    its delimiter lines removed. When there is no valid block the original
    text is returned verbatim with an empty meta.
    """
    if not markdown or not markdown.startswith(_DELIM):
        return PageMeta(), markdown
    lines = markdown.splitlines(keepends=True)
    if not lines or lines[0].strip() != _DELIM:
        return PageMeta(), markdown
    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIM:
            return _parse_block(lines[1:index]), "".join(lines[index + 1 :])
    # Unterminated block: not frontmatter — keep the body untouched.
    return PageMeta(), markdown


def parse_page_meta(markdown: str) -> PageMeta:
    """Return just the frontmatter presentation for ``markdown``."""
    return split_frontmatter(markdown)[0]


def _parse_block(block_lines: list[str]) -> PageMeta:
    values: dict[str, str] = {}
    for raw in block_lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip().lower()
        if key in _FRONTMATTER_KEYS:
            values[key] = _unquote(value.strip())
    return PageMeta(
        description=values.get("description", ""),
        icon=values.get("icon", ""),
    )


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value
