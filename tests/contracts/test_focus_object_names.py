"""Focus-attribution objectName discipline for tracer-logged widgets.

Dogma source: focus-debug attribution — every widget that gains keyboard
focus in the 7 tracer-visible areas must carry a stable ``objectName`` so
``SLI_FOCUS_DEBUG`` lines never read ``<noname>``. Pairing rule: each
listed file must contain ``setObjectName`` calls with the expected stable
names (literals, or f-string prefixes for per-record/per-index names).
Tight to the 7 areas only — no repo-wide dragnet.
"""

from __future__ import annotations

import ast

from ._framework import SRC, parse, read

#: file (relative to src/) -> expected stable names. A name matches when it
#: appears as a string literal inside a ``setObjectName(...)`` call, or as a
#: literal fragment of an f-string ``setObjectName`` call (per-record names
#: like ``recent-card-<stem>`` / ``onboarding-mode-<key>`` / crumbs).
EXPECTED_NAMES: dict[str, set[str]] = {
    "ui/actions/palette/dialog.py": {"palette-search"},
    "plugins/help/back_bar.py": {"help-nav-back", "help-nav-crumb-"},
    "plugins/help/dialog.py": {
        "help-sidebar-column",
        "help-content-host",
        "help-nav-list",
    },
    "tabs/session_picker/recent/header_bar.py": {
        "recent-sort-button",
        "recent-sort-order-button",
        "recent-view-button",
    },
    "tabs/session_picker/recent/panel.py": {"RecentProjectsPanel"},
    "tabs/session_picker/recent/items_view.py": {
        "RecentItemsView",
        "recent-scroll-area",
        "recent-items-host",
    },
    "ui/widgets/shelf/widget.py": {
        "shelf-header-host",
        "shelf-content-host",
        "shelf-title",
    },
    "plugins/onboarding/overlay.py": {
        "onboarding-overlay",
        "onboarding-start",
        "onboarding-mode-",
    },
    "plugins/export/dialog_sections.py": {
        "export-width",
        "export-height",
        "export-comment",
    },
    "plugins/export/dialog.py": {"export-dir", "export-name"},
    "ui/widgets/form_controls.py": {"output-dir", "output-filename"},
    "shared_toolkit/ui/text_input_dialog.py": {"text-input-field"},
}

#: cards build/update per-record names dynamically — checked structurally.
CARD_FUNCS = {
    "build_grid_card",
    "build_list_card",
    "update_grid_card",
    "update_list_card",
}


def _object_name_fragments(tree: ast.Module) -> set[str]:
    """All literal fragments passed to ``setObjectName`` (incl. f-strings).

    Walks each call's argument subtree so conditional names
    (``f".." if .. else ".."``) and helper-built names still match.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setObjectName"
            and node.args
        ):
            continue
        for sub in ast.walk(node.args[0]):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                found.add(sub.value)
    return found


def _module_string_fragments(tree: ast.Module) -> set[str]:
    """Every string literal fragment in the module (for helper-built names)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


def test_expected_object_names_present():
    missing: list[str] = []
    for rel_path, expected in EXPECTED_NAMES.items():
        path = SRC / rel_path
        assert path.is_file(), f"scoped file moved: {rel_path}"
        tree = parse(path)
        if tree is None:
            raise AssertionError(f"{rel_path} does not parse")
        found = _object_name_fragments(tree)
        haystack = "\n".join(sorted(found))
        for name in sorted(expected):
            if not any(name in fragment or fragment in name for fragment in found) and name not in haystack:
                missing.append(f"{rel_path}: missing setObjectName({name!r})")
    assert not missing, (
        "Focus-gaining widgets without stable objectName (tracer would log "
        "<noname>):\n  - " + "\n  - ".join(missing)
    )


def test_cards_name_each_built_card():
    path = SRC / "tabs" / "session_picker" / "recent" / "cards.py"
    tree = parse(path)
    assert tree is not None, f"unparsable {path}"
    funcs = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    offenders: list[str] = []
    for func_name in sorted(CARD_FUNCS):
        func = funcs.get(func_name)
        if func is None:
            offenders.append(f"cards.py: missing function {func_name}()")
            continue
        has_naming = any(
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "setObjectName"
            for sub in ast.walk(func)
        )
        if not has_naming:
            offenders.append(f"cards.py:{func.lineno}: {func_name}() never calls setObjectName")
    fragments = _module_string_fragments(tree)
    if not any("recent-card-" in fragment for fragment in fragments):
        offenders.append("cards.py: no 'recent-card-' objectName prefix found")
    assert not offenders, (
        "Session-picker cards must carry per-record objectNames:\n  - "
        + "\n  - ".join(offenders)
    )


def test_no_empty_object_name_in_scope():
    offenders: list[str] = []
    for rel_path in EXPECTED_NAMES:
        tree = parse(SRC / rel_path)
        assert tree is not None, f"unparsable {rel_path}"
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setObjectName"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == ""
            ):
                offenders.append(f"{rel_path}:{node.lineno}: setObjectName('')")
    assert not offenders, "Empty objectNames defeat focus attribution:\n  - " + "\n  - ".join(offenders)
