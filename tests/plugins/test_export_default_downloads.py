"""Source gate: export defaults resolve the OS Downloads folder through Qt.

Root-level (tab-free) half of the export-default contract: it reads the three
call-site modules as text/AST and asserts the shape, without importing any
tab internals (the behavioural fake-``QStandardPaths`` proof lives in
``src/tabs/image_compare/tests/plugins/test_export_default_downloads.py``,
where deep tab imports belong).

What it pins:
- the dead ``_get_os_default_downloads`` app-side probe is gone (no attribute
  access, no ``hasattr`` string literal);
- ``~/Downloads`` survives only as the single fallback inside the resolver;
- the resolver actually asks ``QStandardPaths`` for ``DownloadLocation``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SOURCE_FILES = {
    "state.py": "src/tabs/image_compare/services/image_export/state.py",
    "common.py": (
        "src/tabs/image_compare/plugins/video_editor/presenter_parts/common.py"
    ),
    "persistence.py": (
        "src/tabs/image_compare/plugins/video_editor/dialog/persistence.py"
    ),
}
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOWNLOADS_LITERAL = 'Path.home() / "Downloads"'


def _sources() -> dict[str, str]:
    return {
        name: (_REPO_ROOT / relative).read_text(encoding="utf-8")
        for name, relative in _SOURCE_FILES.items()
    }


def test_no_dead_probe_and_single_home_downloads_literal():
    sources = _sources()

    tree = ast.parse(sources["state.py"])
    probe_attributes = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "_get_os_default_downloads"
    ]
    probe_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "_get_os_default_downloads"
    ]
    assert not probe_attributes, "the dead app-side hook must not be called"
    assert not probe_literals, "the dead hasattr probe must not survive"

    occurrences = sum(
        source.count(_DOWNLOADS_LITERAL) for source in sources.values()
    )
    assert occurrences == 1, (
        "the home Downloads literal must exist only as the resolver fallback; "
        f"found {occurrences}"
    )
    assert _DOWNLOADS_LITERAL in sources["state.py"]
    assert "QStandardPaths.StandardLocation.DownloadLocation" in sources["state.py"]
