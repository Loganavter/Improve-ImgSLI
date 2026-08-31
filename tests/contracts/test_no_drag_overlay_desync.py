"""Image Compare DnD desync guard — Phase 1.

Dogma source: docs/dev/plan_image_compare_dnd_tiles.md Phase 1:
- ``canvas/texture_parts/layers.clear()`` must NOT reset ``_drag_overlay_*`` (DnD UI,
  not texture). Resetting only canvas → ``canvas False / overlay True`` desync
  blocks new input (plan §2.1 Clear desync).
- ``widget.update_drag_overlays`` must forward its ``visible`` param to the
  canvas (``visible=visible``), not hardcode ``visible=False`` (plan §2.1 Hardcode).

This AST dogma scans source so a regression fails CI instead of silently
reintroducing the 1.48s blocking / hit-test bug.

See: src/tabs/image_compare/canvas/texture_parts/layers.py:100,
     src/tabs/image_compare/widget.py:378,
     src/tabs/image_compare/tests/render/test_canvas_clear_state_contracts.py:91
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import SRC, read

LAYERS_PATH = SRC / "tabs" / "image_compare" / "canvas" / "texture_parts" / "layers.py"
WIDGET_PATH = SRC / "tabs" / "image_compare" / "widget.py"

# All DnD overlay state fields that must NOT be touched by texture clear.
_DRAG_FIELDS = {
    "_drag_overlay_visible",
    "_drag_overlay_horizontal",
    "_drag_overlay_texts",
    "_drag_overlay_cache_key",
    "_drag_overlay_cached_image",
}


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    # also search nested (in case of class)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _layers_clear_assigns_drag_overlay() -> list[str]:
    text = read(LAYERS_PATH)
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [f"{LAYERS_PATH}:{e}"]
    fn = _find_function(tree, "clear")
    if fn is None:
        return [f"def clear not found in {LAYERS_PATH}"]
    offenders: list[str] = []
    # Walk only inside clear() — texture clear must not touch drag fields.
    for node in ast.walk(fn):
        # Assignments: state._drag_overlay_* = ...  or  self._drag_overlay_*
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                if node.target is not None:
                    targets = [node.target]
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Attribute) and sub.attr in _DRAG_FIELDS:
                        try:
                            src = ast.unparse(node).strip()  # type: ignore
                        except Exception:
                            src = sub.attr
                        offenders.append(f"{LAYERS_PATH}:{node.lineno} clear() touches {sub.attr}: {src}")
        # Also catch Attribute nodes that are set via e.g. state._drag_overlay_visible = False
        # The above already covers, but also ensure any standalone store doesn't slip.
    return offenders


def _widget_hardcodes_visible_false() -> list[str]:
    text = read(WIDGET_PATH)
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [f"{WIDGET_PATH}:{e}"]
    fn = _find_function(tree, "update_drag_overlays")
    if fn is None:
        return [f"def update_drag_overlays not found in {WIDGET_PATH}"]
    offenders: list[str] = []

    # Build parent map to allow exemption for `if not self.image_label.isVisible():` guard.
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent

    def _is_inside_isvisible_guard(node: ast.AST) -> bool:
        cur: ast.AST | None = node
        while cur is not None:
            parent = parent_map.get(cur)
            if parent is not None and isinstance(parent, ast.If):
                try:
                    cond_src = ast.unparse(parent.test).strip()  # type: ignore
                except Exception:
                    cond_src = ""
                # Guard is `if not self.image_label.isVisible():` — this hide path
                # legitimately uses visible=False to force-hide when canvas not visible.
                if "isVisible" in cond_src and "not" in cond_src:
                    return True
            cur = parent
        return False

    # Find all calls to set_drag_overlay_state inside update_drag_overlays
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        # Detect set_drag_overlay_state calls
        func_name = ""
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id
        if func_name != "set_drag_overlay_state":
            continue
        # Inspect keywords for visible=False hardcode
        for kw in node.keywords:
            if kw.arg == "visible" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                if _is_inside_isvisible_guard(node):
                    # Allowed: early-return hide when canvas not visible
                    continue
                try:
                    src = ast.unparse(node).strip()  # type: ignore
                except Exception:
                    src = "set_drag_overlay_state(visible=False,...)"
                offenders.append(
                    f"{WIDGET_PATH}:{node.lineno} update_drag_overlays hardcodes visible=False: {src} "
                    f"(must forward visible=visible — see plan_image_compare_dnd_tiles.md §2.1 Hardcode)"
                )
        # Also catch positional False that would map to visible (unlikely but guard)
        # set_drag_overlay_state(self.image_label, False) not used — keywords only in codebase.
    return offenders


def test_clear_does_not_reset_drag_overlay():
    offenders = _layers_clear_assigns_drag_overlay()
    assert not offenders, (
        "layers.clear() must not reset _drag_overlay_* (DnD UI state, not texture) — "
        "resetting only canvas causes canvas False / widget overlay True desync and blocks "
        "new DnD until next load (plan_image_compare_dnd_tiles.md §2.1 Clear desync). "
        f"Remove those assignments, leave DnD untouched:\n  - " + "\n  - ".join(offenders)
    )


def test_widget_does_not_hardcode_visible_false():
    offenders = _widget_hardcodes_visible_false()
    assert not offenders, (
        "widget.update_drag_overlays must forward visible=visible to canvas, not hardcode "
        "visible=False (plan_image_compare_dnd_tiles.md §2.1 Hardcode, Phase 1 step 2). "
        "Hardcoding makes SHOW_FAILED / BLOCKING desync:\n  - " + "\n  - ".join(offenders)
    )
