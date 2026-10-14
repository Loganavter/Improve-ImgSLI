"""Contract: widgets must not cache theme-derived state at build time.

Why (2026-10-14, inv-theme-recolor-offbyone): the session-picker shelf pushed
chrome-derived colours to its children *before* recomputing its own chrome
(children lagged one theme), and the recent cards froze their badge ``QIcon``
at build. Both were invisible until a live theme switch. This gate stops the
class from returning:

- icon art must be a lazy handle (``sli_ui_toolkit.icons.lazy_icon``) or an
  enum resolved at paint time — not an eagerly-resolved ``QIcon`` stored in
  ``__init__`` / a build helper;
- token colours cached in an attribute at build must be re-read in a theme
  hook (a method whose name mentions ``theme``/``recolor``/``sync``).

The audit is static (AST) — it flags the *shape*, not behaviour. Exemptions
below are verified-safe call sites with the reason recorded.
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, parse, rel

# (repo-relative path, class name) -> why the hit is safe.
_EXEMPT: dict[tuple[str, str], str] = {
    (
        "src/ui/main_window/csd_menu_strip.py",
        "CsdMenuRow",
    ): "rows are rebuilt on every menu open (_show_options -> _build_rows); the "
    "icon pixmap resolves the current theme at open",
    (
        "src/ui/widgets/color/picker_dialog.py",
        "_PreviewChip",
    ): "_before/_after are the user-chosen comparison colours (set_before/"
    "set_after), not theme state; the themed initial value is a placeholder",
    (
        "src/ui/widgets/scroll_value_button.py",
        "ScrollValueButton",
    ): "region icons are enum handles resolved at paint time via resolve_icon",
    (
        "src/ui/managers/tray_manager.py",
        "TrayManager",
    ): "QSystemTrayIcon is not an icon resolver; the OS tray icon is not app chrome",
}

# Theme-derived call names.
_ASSET_TOKENS = ("get_icon", "get_app_icon", "get_themed_icon", "resolve_icon",
                 "get_icon_by_path", "get_icon_by_name", "get_tab_icon")
_COLOR_TOKENS = ("resolve_theme_color", "try_resolve_theme_color", "get_color",
                 "try_get_color", "_themed_or_fallback")
_THEME_HOOK = ("theme", "recolor", "sync_icon", "repolish", "apply_style")


def _cname(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _is_theme_derived(name: str) -> bool:
    if name == "lazy_icon":  # the fix, not the problem
        return False
    low = name.lower()
    return name in _ASSET_TOKENS or name in _COLOR_TOKENS or "icon" in low


def _methods(cls: ast.ClassDef):
    return [m for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _calls(func: ast.AST) -> set[str]:
    return {_cname(n) for n in ast.walk(func) if isinstance(n, ast.Call)}


def _reachable_from_init(cls: ast.ClassDef) -> set[str]:
    methods = {m.name: m for m in _methods(cls)}
    reach = {"__init__"}
    changed = True
    while changed:
        changed = False
        for name in list(reach):
            m = methods.get(name)
            if m is None:
                continue
            for c in _calls(m):
                if c in methods and c not in reach:
                    reach.add(c)
                    changed = True
    return reach


def _derived_keys(methods, reachable) -> set[tuple[str, str]]:
    """Keys: ("attr", name) | ("kw", "icon"/"pixmap") assigned in reachable methods."""
    keys: set[tuple[str, str]] = set()
    for m in methods:
        if m.name not in reachable:
            continue
        for node in ast.walk(m):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                if _is_theme_derived(_cname(node.value)):
                    for tgt in node.targets:
                        if (isinstance(tgt, ast.Attribute)
                                and isinstance(tgt.value, ast.Name)
                                and tgt.value.id == "self"):
                            keys.add(("attr", tgt.attr))
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg in ("icon", "pixmap") and isinstance(kw.value, ast.Call):
                        if _is_theme_derived(_cname(kw.value)):
                            keys.add(("kw", kw.arg))
    return keys


def _findings() -> list[str]:
    out: list[str] = []
    for path in iter_py(SRC):
        tree = parse(path)
        if tree is None:
            continue
        relpath = rel(path)
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            if (relpath, cls.name) in _EXEMPT:
                continue
            methods = _methods(cls)
            reach = _reachable_from_init(cls)
            built = _derived_keys(methods, reach)
            if not built:
                continue
            hooks = {m.name for m in methods
                     if any(h in m.name.lower() for h in _THEME_HOOK)}
            rehooked = _derived_keys(methods, hooks) if hooks else set()
            for key in sorted(built - rehooked):
                out.append(f"{relpath}::{cls.name} caches theme-derived {key[0]} {key[1]!r} at build")
    return out


def test_no_widget_caches_theme_derived_state_at_build():
    findings = _findings()
    assert not findings, (
        "Theme-derived state cached at build without a theme-hook re-derive "
        "(use `lazy_icon(...)` for icons, or re-read the token in a theme hook; "
        "add a verified exemption with a reason if genuinely safe):\n  "
        + "\n  ".join(findings)
    )
