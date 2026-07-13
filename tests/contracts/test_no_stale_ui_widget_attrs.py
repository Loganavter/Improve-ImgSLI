"""No reads of image_compare widget-only attributes through ``.ui``.

Dogma source: docs/dev/TAB_CONTRACT.md "Dependency Wiring Rule: No Implied
Lookups". ``ImageComparePrimitivesFactory`` (tabs/image_compare/ui/primitives.py)
is the sole owner of the image_compare tab's widgets: every one of them is
assigned as ``target.<attr> = ...`` where ``target`` is the tab-owned
``ImageCompareWidget``. ``Ui_ImageComparisonApp`` (ui/main_window/ui.py) never
declares any of these attributes itself.

This makes the attribute set a closed, mechanically derivable list: if a name
in that set is read off something spelled ``...ui.<attr>`` (or
``getattr(<ui-like>, "<attr>", ...)``) anywhere else in the tree, that is not
a coincidence — it is exactly the "reach through a side channel instead of
receiving the widget explicitly" anti-pattern this repo keeps reintroducing,
regardless of what the lookup happens to be named this time (``ui``,
``presenter.ui``, ``window.ui``, ...).

This generalizes test_no_implied_widget_lookup.py: that test hard-codes one
known side channel (``legacy_tab_widgets``); this one derives the forbidden
name set from the actual ownership assignment, so it also catches lookups
that don't literally mention the tab's name.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import SRC, iter_py, read, rel

PRIMITIVES_FILE = SRC / "tabs" / "image_compare" / "ui" / "primitives.py"

OWNER_FILES = {
    Path("tabs/image_compare/ui/primitives.py"),
}


def _widget_owned_attrs() -> set[str]:
    tree = ast.parse(read(PRIMITIVES_FILE))
    attrs: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "target"
            ):
                attrs.add(target.attr)
    attrs.discard("_image_compare_primitives_built")
    return attrs


WIDGET_OWNED_ATTRS = _widget_owned_attrs()


def _is_ui_like(node: ast.AST) -> bool:
    """True for ``x.ui``, ``x.y.ui`` — an attribute access ending in ``.ui``.

    Deliberately NOT true for a bare ``Name`` spelled ``ui`` — several
    already-correct call sites do ``ui = presenter.widget`` (or
    ``ui = self.target`` inside the primitives/layout factories) and then use
    the local variable ``ui`` as a plain alias for the widget. Flagging every
    local named ``ui`` produced hundreds of false positives from that
    pattern. The actual bug shape is specifically reading the attribute off
    something that is still the *host* (``Ui_ImageComparisonApp``), which is
    always reached through an attribute access — ``presenter.ui``,
    ``window.ui``, ``self.ui`` — never a bare local.
    """
    return isinstance(node, ast.Attribute) and node.attr == "ui"


def test_widget_owned_attrs_are_not_read_through_ui():
    assert WIDGET_OWNED_ATTRS, "expected to derive a non-empty attr set from primitives.py"

    offenders: list[str] = []
    for py in iter_py(SRC):
        rel_path = py.relative_to(SRC)
        if rel_path in OWNER_FILES:
            continue
        try:
            tree = ast.parse(read(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in WIDGET_OWNED_ATTRS
                and _is_ui_like(node.value)
            ):
                offenders.append(f"{rel(py)}:{node.lineno}: ...ui.{node.attr}")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and _is_ui_like(node.args[0])
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in WIDGET_OWNED_ATTRS
            ):
                offenders.append(
                    f"{rel(py)}:{node.lineno}: getattr(<ui-like>, {node.args[1].value!r}, ...)"
                )
    assert not offenders, (
        "Found widget-only attributes read through a '.ui'-shaped reference. "
        "Ui_ImageComparisonApp never owns these — the widget must be passed "
        "explicitly instead:\n  - " + "\n  - ".join(offenders)
    )
