"""Guard: QSS must not set color/font on QLabel (bypasses UiFont / setFont)."""

from __future__ import annotations

import re
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[2]

_LABEL_SELECTOR = re.compile(
    r"(?P<head>^|\n)\s*(?P<sel>[^{};\n]*\bQLabel\b[^{]*)\{(?P<body>[^}]*)\}",
    re.MULTILINE,
)
_FORBIDDEN_IN_BODY = re.compile(
    r"\b(color|font|font-family|font-size|font-weight|font-style)\s*:",
    re.IGNORECASE,
)


def _iter_qss_files() -> list[Path]:
    roots = (
        _APP_ROOT / "src" / "resources" / "styles",
        _APP_ROOT / "src" / "shared_toolkit" / "ui" / "resources" / "styles",
    )
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(root.glob("*.qss"))
    return sorted({p.resolve() for p in files})


def test_no_qlabel_color_or_font_in_app_qss():
    offenders: list[str] = []
    for path in _iter_qss_files():
        text = path.read_text(encoding="utf-8")
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        for match in _LABEL_SELECTOR.finditer(stripped):
            sel = match.group("sel").strip()
            body = match.group("body")
            if _FORBIDDEN_IN_BODY.search(body):
                offenders.append(f"{path.relative_to(_APP_ROOT)}: {sel}")
    assert not offenders, (
        "QLabel QSS color/font rules bypass UiFont (Qt ignores setFont):\n"
        + "\n".join(offenders)
    )
