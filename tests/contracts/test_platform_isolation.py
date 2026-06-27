"""Platform isolation dogma.

The platform (``src/core/``, ``src/ui/`` except ``src/ui/widgets/canvas``
which is the shared QRhi backend, ``src/services/``, ``src/plugins/``,
``src/events/``) MUST NOT mention specific tab names like ``image_compare``
or ``image_session``. Tabs live under ``src/tabs/`` and the host platform
discovers them via :class:`tabs.registry.TabRegistry`.

Allowlist: a small set of compat-bridge files registered here may still
contain the literal until the corresponding migration steps land. New
violations outside the allowlist should fail this test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

PLATFORM_ROOTS = (
    SRC / "core",
    SRC / "ui" / "main_window",
    SRC / "ui" / "presenters" / "main_window",
    SRC / "ui" / "presenters" / "image_canvas",
    SRC / "ui" / "canvas_features",
    SRC / "ui" / "canvas_infra",
    SRC / "ui" / "widgets" / "canvas",
    SRC / "ui" / "context_menu",
    SRC / "services",
    SRC / "plugins",
    SRC / "events",
)

FORBIDDEN_PATTERNS = (
    re.compile(r"\bimage_compare\b"),
    re.compile(r"\bimage_session\b"),
)

# Compat-bridge files explicitly tracked in MIGRATION_PLAN.md. Each entry is a
# repo-relative path.
#
# These three modules are the legacy pre-tab paths that still register a
# parallel ``comparison`` plugin / context-menu / GL canvas widget. The host
# also wires the modern ``tabs.image_compare.*`` paths next to them; the
# legacy paths persist until the ``ui/widgets/gl_canvas`` → ``ui/widgets/canvas``
# migration finishes, at which point all three drop out.
ALLOWLIST: frozenset[str] = frozenset(
    {
        # Legacy parallel ``comparison`` plugin / host-side context-menu / GL
        # canvas widget. Drop out once ``ui/widgets/gl_canvas`` →
        # ``ui/widgets/canvas`` migration finishes.
        "src/plugins/comparison/plugin.py",
        "src/ui/context_menu/image_compare.py",
        "src/ui/widgets/gl_canvas/widget.py",
        # ``LayoutComposer`` still calls ``tab.widget.assemble(ui)`` because
        # image_compare primitive widgets (buttons/sliders) are built by the
        # host's ``Ui_ImageComparisonApp._create_*`` methods and bound into
        # the tab's layout tree. Moving primitive ownership into the tab is
        # tracked as a remaining migration step (see MIGRATION_PLAN.md).
        "src/ui/main_window/layouts.py",
        "src/ui/main_window/ui.py",
        # Host-side fallbacks that still default to ``image_compare`` when
        # there is no active workspace session, or special-case image_compare
        # cache invalidation. Will go away with full step 9/24 closure.
        "src/core/store_workspace.py",
        "src/ui/presenters/main_window/state.py",
        "src/ui/presenters/main_window/workspace.py",
        # Settings page that still gates resolution/interactive-optimization/
        # video-recording groups by ``active_tab == "image_compare"``. Tab
        # contribute hook is in place; group relocation is structural debt.
        "src/plugins/settings/pages/performance.py",
        # ``video_editor.open_image_compare()`` survives as a cross-tab launch
        # helper. Replacing it with an EventBus message is tracked separately.
        "src/plugins/video_editor/model.py",
    }
)


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in PLATFORM_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return sorted(files)


@pytest.mark.parametrize("py_file", _iter_py_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_platform_file_does_not_mention_image_compare(py_file: Path):
    rel = str(py_file.relative_to(ROOT))
    if rel in ALLOWLIST:
        pytest.skip(f"allowlisted compat bridge: {rel}")
    text = py_file.read_text(encoding="utf-8")
    hits = []
    for pattern in FORBIDDEN_PATTERNS:
        for match in pattern.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            hits.append((line_no, pattern.pattern, match.group(0)))
    assert not hits, (
        f"{rel} mentions tab-specific names — platform code must stay tab-agnostic:\n"
        + "\n".join(f"  line {ln}: pattern {pat!r} matched {tok!r}" for ln, pat, tok in hits)
    )
