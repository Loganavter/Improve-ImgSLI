"""Ratchet: no unconditional window activation (Wayland busy-cursor flash).

Every ``QWidget.activateWindow()`` is an xdg-activation request on Wayland
and Mutter answers each with busy/loading cursor feedback until the next
present. Kicking an already-active window — typical in hide/close/
focus-restore/timer/eventFilter paths — flashes busy for a frame per call
(X11 never shows it; caught live via an ``[activate-probe]`` sweep on kbd
flyout toggles: ``SimpleOptionsFlyout.hide``, Help ``hideEvent``, the color
picker ``on_finished`` — all fixed to route through the rate-limited
helper).

A call site complies when its enclosing function either
  (a) checks ``isActiveWindow`` (guard pattern), or
  (b) routes through ``request_window_activation`` (rate-limited helper), or
  (c) is an explicit user-foreground flow listed in ``ALLOWLIST`` below
      (dialog/window show, open, bring-to-front — activation is the point).

Adding a new raw call fails loudly: route it via (a)/(b), or justify it in
``ALLOWLIST`` with a reason. Scans the app tree plus the toolkit checkout
(sibling ``../sli-ui-toolkit`` or ``$SLI_TOOLKIT_DIR``) when resolvable.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from tests.contracts._framework import ROOT

APP_SRC = ROOT / "src"


def _toolkit_base() -> Path | None:
    override = os.environ.get("SLI_TOOLKIT_DIR", "").strip()
    candidates = [Path(override)] if override else []
    candidates.append(ROOT.parent / "sli-ui-toolkit")
    for base in candidates:
        if (base / "src" / "sli_ui_toolkit" / "__init__.py").exists():
            return base
    return None


# (tree, relpath, funcname): reason. Explicit user-foreground flows only —
# reactive paths (hide/close/restore/filter/timer/deferred) must use the
# guard or the helper instead.
ALLOWLIST = {
    ("app", "src/plugins/onboarding/pages.py", "_show_color_dialog"):
        "bring existing color dialog to front on user click",
    ("app", "src/plugins/onboarding/overlay.py", "showEvent"):
        "overlay show",
    ("app", "src/plugins/help/plugin.py", "show_dialog"):
        "explicit Help open",
    ("app", "src/tabs/image_compare/ui/settings_color_pickers.py",
     "apply_smart_magnifier_colors"):
        "bring existing color dialog to front on user action",
    ("app", "src/tabs/image_compare/ui/settings_color_pickers.py", "_show_dialog"):
        "color dialog show + bring existing front",
    ("app", "src/tabs/multi_compare/controller.py",
     "_on_divider_color_picker_requested"):
        "bring existing picker dialog to front on user action",
    ("app", "src/ui/main_window/actions.py", "toggle_main_window_visibility"):
        "unminimize/show main window on user action",
    ("app", "src/shared_toolkit/ui/message_dialog.py", "open_non_modal_message"):
        "message dialog show",
    ("app", "src/ui/managers/dialog_manager.py", "show_settings_dialog"):
        "settings dialog show",
    ("app", "src/ui/widgets/color/swatch.py", "_open_dialog"):
        "bring existing color dialog to front on user click",
    ("app", "src/tabs/image_compare/plugins/video_editor/plugin.py", "open_editor"):
        "video editor dialog show",
    ("app", "src/tabs/image_compare/plugins/video_editor/plugin.py",
     "_show_editor_dialog"):
        "video editor dialog show (deferred-activation guard)",
    ("app", "src/ui/canvas_infra/rhi/rhi_present_sync.py",
     "ensure_window_active_for_qrhi"):
        "own 500ms cooldown + application-state check",
    ("toolkit", "src/sli_ui_toolkit/ui/inspector/controller.py", "_do_activate"):
        "dev-only UI inspector activation retry",
    ("toolkit", "src/sli_ui_toolkit/ui/widgets/composite/help_document/image_lightbox.py",
     "show_pixmap"):
        "explicit lightbox open (show + raise + focus)",
}

_MARKERS = ("isActiveWindow", "request_window_activation")


def _walk_with_owner(tree: ast.AST):
    """Yield (node, innermost enclosing def or None) for every node."""
    out: list[tuple[ast.AST, ast.AST | None]] = []

    def rec(node: ast.AST, owner: ast.AST | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rec(child, child)
            else:
                out.append((child, owner))
                rec(child, owner)

    rec(tree, None)
    return out


def _subtree_has_marker(func_node: ast.AST) -> bool:
    for node in ast.walk(func_node):
        if isinstance(node, ast.Name) and node.id in _MARKERS:
            return True
        if isinstance(node, ast.Attribute) and node.attr in _MARKERS:
            return True
    return False


def _collect_offenders(tag: str, root: Path, anchor: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node, owner in _walk_with_owner(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "activateWindow"
            ):
                continue
            func_name = (
                owner.name  # type: ignore[union-attr]
                if owner is not None
                else "<module>"
            )
            if owner is not None and _subtree_has_marker(owner):
                continue
            rel = path.relative_to(anchor).as_posix()
            if (tag, rel, func_name) in ALLOWLIST:
                continue
            offenders.append(
                f"{tag}:{rel}:{node.lineno} in {func_name}() — raw "
                "activateWindow() with no isActiveWindow guard, no "
                "request_window_activation, and no ALLOWLIST entry"
            )
    return offenders


def test_no_unconditional_window_activation():
    offenders: list[str] = []
    offenders.extend(_collect_offenders("app", APP_SRC, ROOT))
    toolkit_base = _toolkit_base()
    if toolkit_base is not None:
        offenders.extend(
            _collect_offenders("toolkit", toolkit_base / "src", toolkit_base)
        )
    assert not offenders, (
        "Unconditional activateWindow() calls (Wayland busy-cursor flash — "
        "each kick on an already-active window costs a frame of spinner):\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\nComply via isActiveWindow guard, request_window_activation, "
        "or a reasoned ALLOWLIST entry in this file."
    )
