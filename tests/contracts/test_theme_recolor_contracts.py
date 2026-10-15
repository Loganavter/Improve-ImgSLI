"""Contract: widgets must not cache theme-derived state at build time.

Why (2026-10-14/15, inv-theme-recolor-offbyone + gallery settings-section icons):
theme state (icon art, token colours) captured eagerly at build stays frozen at
the theme active then, so a live switch leaves it stale. Two shapes are banned:

- an attribute/region assigned a theme-derived value in ``__init__``/a build
  helper, with no re-derivation in a theme hook;
- an ``icon=<icon-ish call>`` / ``setIcon(<icon-ish call>)`` anywhere (class
  method OR module-level builder) outside a theme hook.

Icon art must be a lazy handle (``sli_ui_toolkit.icons.lazy_icon``) or an enum
resolved at paint time; token colours cached in an attribute must be re-read in
a theme hook. ``ICON_CALL_ALLOWLIST`` lists call sites that legitimately build an
eager icon because they are rebuilt at open (context menus, popups) or are not
app chrome (OS tray) — each with a reason.
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, parse, rel

# No hand allowlist: the rule bans the eager icon FACTORIES as an icon source.
# Brand/OS art that is genuinely theme-invariant is produced by a helper
# (e.g. ``_app_icon()`` -> QIcon(icon.png), the OS tray) — those are not factory
# call sites and are intentionally out of scope. Helper wrappers around a
# factory (``_menu_icon(...)``) are a known static-detection gap: make the
# helper return a ``lazy_icon`` handle instead of an eager QIcon.
ICON_CALL_ALLOWLIST: dict[tuple[str, str], str] = {}

# (repo-relative path, class name) -> why the class-level hit is safe.
CLASS_EXEMPT: dict[tuple[str, str], str] = {
    ("src/ui/main_window/csd_menu_strip.py", "CsdMenuRow"): "rows rebuilt on every menu open",
    ("src/ui/widgets/color/picker_dialog.py", "_PreviewChip"): "_before/_after are user-chosen colours, not theme state",
    ("src/ui/widgets/scroll_value_button.py", "ScrollValueButton"): "region icons are enum handles resolved at paint",
    ("src/ui/managers/tray_manager.py", "TrayManager"): "OS tray icon, not app chrome",
}

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


# Eager icon factories — banned as an ``icon=`` / ``setIcon()`` source. Icon
# art must be a lazy handle (`sli_ui_toolkit.icons.lazy_icon`, e.g. via
# `ui.icon_manager.themed_icon`) or an enum/handle resolved at paint time.
_EAGER_FACTORIES = {
    "get_app_icon", "get_icon", "get_themed_icon",
    "get_icon_by_path", "get_icon_by_name",
}


def _is_iconish(name: str) -> bool:
    return name in _EAGER_FACTORIES


def _is_theme_derived(name: str) -> bool:
    if name == "lazy_icon":
        return False
    return name in _ASSET_TOKENS or name in _COLOR_TOKENS or "icon" in name.lower()


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
    keys: set[tuple[str, str]] = set()
    for m in methods:
        if m.name not in reachable:
            continue
        for node in ast.walk(m):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                if _is_theme_derived(_cname(node.value)):
                    for tgt in node.targets:
                        if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                                and tgt.value.id == "self"):
                            keys.add(("attr", tgt.attr))
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg in ("icon", "pixmap") and isinstance(kw.value, ast.Call):
                        if _is_theme_derived(_cname(kw.value)):
                            keys.add(("kw", kw.arg))
    return keys


def _icon_call_hits(fn: ast.AST, relpath: str) -> list[str]:
    """icon=<iconish call> / setIcon(<iconish call>) inside one function."""
    hits: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "icon" and isinstance(kw.value, ast.Call) and _is_iconish(_cname(kw.value)):
                hits.append(f"icon={_cname(kw.value)}")
        if _cname(node) in ("setIcon", "set_icon") and node.args and isinstance(node.args[0], ast.Call) \
                and _is_iconish(_cname(node.args[0])):
            hits.append(f"setIcon({_cname(node.args[0])})")
    return hits


def _findings() -> list[str]:
    out: list[str] = []
    for path in iter_py(SRC):
        tree = parse(path)
        if tree is None:
            continue
        relpath = rel(path)

        # Class-level cached theme state (existing rule).
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            if (relpath, cls.name) in CLASS_EXEMPT:
                continue
            methods = _methods(cls)
            reach = _reachable_from_init(cls)
            built = _derived_keys(methods, reach)
            if not built:
                continue
            hooks = {m.name for m in methods if any(h in m.name.lower() for h in _THEME_HOOK)}
            rehooked = _derived_keys(methods, hooks) if hooks else set()
            for key in sorted(built - rehooked):
                out.append(f"{relpath}::{cls.name} caches theme-derived {key[0]} {key[1]!r} at build")

        # Function-level eager icon calls (class methods + module functions).
        scopes: list[tuple[str, ast.AST]] = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                scopes += [(node.name, m) for m in _methods(node)]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scopes.append(("<module>", node))
        for _owner, fn in scopes:
            if any(h in fn.name.lower() for h in _THEME_HOOK):
                continue
            if (relpath, fn.name) in ICON_CALL_ALLOWLIST:
                continue
            hits = _icon_call_hits(fn, relpath)
            if hits:
                out.append(f"{relpath}:{fn.lineno} {fn.name} eager icon call ({', '.join(sorted(set(hits)))}) — use lazy_icon/enum")
    return out


def test_no_widget_caches_theme_derived_state_at_build():
    findings = _findings()
    assert not findings, (
        "Theme-derived state captured eagerly (use `lazy_icon(...)`/enums for icons, "
        "re-read tokens in a theme hook; add a reasoned allowlist entry if genuinely "
        "safe — e.g. a menu rebuilt per open):\n  " + "\n  ".join(findings)
    )
