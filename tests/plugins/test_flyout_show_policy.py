"""App flyout show policy: context menus coexist; pickers stay exclusive."""

from __future__ import annotations

from sli_ui_toolkit.managers import FlyoutManager, GroupShowPolicy

from ui.flyout_policy import install_flyout_show_policy
from ui.widgets.font_settings_flyout import FontSettingsFlyout
from ui.widgets.glass_hud import InfoHUD


def test_install_flyout_show_policy_configures_context_menu_coexistence():
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        policy = install_flyout_show_policy()
        assert isinstance(policy, GroupShowPolicy)
        assert manager.show_policy() is policy

        menu = type("M", (), {"flyout_group": "context_menu"})()
        listing = type("L", (), {"flyout_group": "unified_list"})()
        options = type("O", (), {"flyout_group": "options"})()
        font = type("F", (), {"flyout_group": "font_settings"})()

        assert policy.should_dismiss(menu, listing) is False
        assert policy.should_claim_active(menu, listing) is False
        # List refresh/open must not dismiss an open context menu.
        assert policy.should_dismiss(listing, menu) is False
        # Interp / font flyouts dismiss the list and each other.
        assert policy.should_dismiss(options, listing) is True
        assert policy.should_dismiss(font, options) is True
        assert policy.should_dismiss(listing, font) is True
    finally:
        manager.set_show_policy(previous)


def test_info_hud_is_tagged_and_never_a_dismiss_target():
    """Resolution/filename corner chips must survive every other flyout opening."""
    manager = FlyoutManager.get_instance()
    previous_policy = manager.show_policy()
    previous_stack = manager.layer_stack()
    try:
        assert InfoHUD.flyout_group == "info_hud"

        policy = install_flyout_show_policy()
        hud = type("H", (), {"flyout_group": "info_hud"})()
        listing = type("L", (), {"flyout_group": "unified_list"})()
        options = type("O", (), {"flyout_group": "options"})()
        font = type("F", (), {"flyout_group": "font_settings"})()
        toggle = type("T", (), {"flyout_group": "toggle"})()
        actions = type("A", (), {"flyout_group": "actions"})()
        menu = type("M", (), {"flyout_group": "context_menu"})()

        # None of the ordinary exclusive groups (nor the context menu) may
        # ever dismiss the info HUD.
        for other_showing in (listing, options, font, toggle, actions, menu):
            assert policy.should_dismiss(other_showing, hud) is False

        # The HUD itself never dismisses anything and never steals "active"
        # (defensive -- it's also pinned=True, which already covers this in
        # practice, see _configure_info_hud_rules docstring).
        assert policy.should_dismiss(hud, listing) is False
        assert policy.should_claim_active(hud, None) is False
    finally:
        manager.set_show_policy(previous_policy)
        manager.set_layer_stack(previous_stack)


def test_every_flyout_group_is_policy_known():
    """Guard: no flyout may rely on the exclusive "default" fallback.

    Regression rationale: ``gallery_selection`` + ``gallery_card`` were
    unconfigured, so the exclusive fallback killed the selection HUD on
    every hover. Every ``flyout_group`` literal in app code must be
    explicitly configured in the host policy (``src/ui/flyout_policy.py``),
    and every bare ``BaseFlyout(...)`` / ``IconActionFlyout(...)`` call
    must carry a resolvable explicit tag in its own function (module
    constant, string literal, or ``self.X`` backed by a class literal) —
    otherwise it lands in "default" and dismisses everything on show.

    Pure ``ast`` scan (no Qt, no imports): fails CI instead of HUDs in prod.
    """
    import ast
    from pathlib import Path

    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        policy = install_flyout_show_policy()
        known: set[str] = set()
        for table in (
            "_group_dismisses",
            "_group_claim_active",
            "_group_coexist",
            "_group_parent",
        ):
            try:
                known.update(getattr(policy, table, {}) or {})
            except Exception:
                continue
        assert known, "policy exposes no configured groups"

        src_root = Path(__file__).resolve().parents[2] / "src"
        assert src_root.is_dir(), f"app src not found at {src_root}"

        literals: set[str] = set()
        bare_call_sites: list[tuple[str, int, str]] = []

        def _resolve_tag(value: ast.expr, tree: ast.Module,
                         parents: dict[ast.AST, ast.AST],
                         call: ast.Call) -> str | None:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            if isinstance(value, ast.Name):
                for node in tree.body:
                    if (
                        isinstance(node, ast.Assign)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                        and any(isinstance(t, ast.Name) and t.id == value.id
                                for t in node.targets)
                    ):
                        return node.value.value
                return None
            if (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "self"
            ):
                owner: ast.AST | None = call
                while owner is not None and not isinstance(owner, ast.ClassDef):
                    owner = parents.get(owner)
                if owner is None:
                    return None
                for stmt in owner.body:
                    targets = (
                        stmt.targets
                        if isinstance(stmt, ast.Assign)
                        else [stmt.target]
                        if isinstance(stmt, ast.AnnAssign)
                        else []
                    )
                    if stmt.value is None:
                        continue
                    if (
                        isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)
                        and any(isinstance(t, ast.Name) and t.id == value.attr
                                for t in targets)
                    ):
                        return stmt.value.value
            return None

        offenders: list[str] = []
        for path in sorted(src_root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            parents: dict[ast.AST, ast.AST] = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parents[child] = node
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = (
                        node.targets
                        if isinstance(node, ast.Assign)
                        else [node.target]
                    )
                    if node.value is None:
                        continue
                    for target in targets:
                        is_tag = (
                            isinstance(target, ast.Name)
                            and target.id == "flyout_group"
                        ) or (
                            isinstance(target, ast.Attribute)
                            and target.attr == "flyout_group"
                        )
                        if is_tag and isinstance(node.value, ast.Constant) \
                                and isinstance(node.value.value, str):
                            literals.add(node.value.value)
                elif isinstance(node, ast.Call):
                    func = node.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else func.attr
                        if isinstance(func, ast.Attribute)
                        else ""
                    )
                    if name in ("BaseFlyout", "IconActionFlyout"):
                        bare_call_sites.append((str(path), node.lineno, name))
                        owner: ast.AST | None = node
                        while owner is not None and not isinstance(
                            owner, ast.FunctionDef
                        ):
                            owner = parents.get(owner)
                        resolved: set[str] = set()
                        if owner is not None:
                            for sub in ast.walk(owner):
                                if not isinstance(sub, (ast.Assign, ast.AnnAssign)):
                                    continue
                                sub_targets = (
                                    sub.targets
                                    if isinstance(sub, ast.Assign)
                                    else [sub.target]
                                )
                                if sub.value is None:
                                    continue
                                if any(
                                    isinstance(t, ast.Attribute)
                                    and t.attr == "flyout_group"
                                    for t in sub_targets
                                ):
                                    tag = _resolve_tag(sub.value, tree, parents, node)
                                    if tag is not None:
                                        resolved.add(tag)
                        if not resolved or not resolved <= known or "default" in resolved:
                            offenders.append(
                                f"{path}:{node.lineno}: bare {name}(...) tags "
                                f"{sorted(resolved) or 'UNRESOLVED'} — give it an "
                                f"explicit policy-known flyout_group"
                            )

        unknown = {lit for lit in literals if lit not in known}
        assert not unknown, (
            "flyout_group literals without policy rules (exclusive fallback "
            f"would dismiss HUDs): {sorted(unknown)} — configure them in "
            "src/ui/flyout_policy.py"
        )
        assert "default" not in literals, "explicit 'default' group tag found"
        assert not offenders, "untagged bare flyout constructions:\n" + "\n".join(offenders)
    finally:
        manager.set_show_policy(previous)


def test_native_title_bar_resize_keeps_pinned_flyouts(qapp):
    """CustomTitleBar's Resize/Move sweep must not close pinned flyouts.

    Regression for the info HUD closing whenever the loupe/text-settings
    panels (or a context menu attach/detach) triggered a host Resize/Move:
    ``_hide_active_flyouts`` special-cased ``context_menu`` but hid every
    other visible flyout unconditionally, ignoring ``pinned`` entirely.
    """
    from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar

    class _FakeFlyout:
        def __init__(self, *, group: str | None = None, pinned: bool = False) -> None:
            self.flyout_group = group
            self.pinned = pinned
            self._visible = True

        def isVisible(self) -> bool:
            return self._visible

        def hide(self) -> None:
            self._visible = False

    manager = FlyoutManager.get_instance()
    previous_registered = set(getattr(manager, "_registered_flyouts", ()))
    previous_active = getattr(manager, "_active_flyout", None)
    try:
        pinned_hud = _FakeFlyout(group="info_hud", pinned=True)
        ordinary = _FakeFlyout(group="options")
        manager._registered_flyouts = {pinned_hud, ordinary}
        manager._active_flyout = None

        CustomTitleBar()._hide_active_flyouts()

        assert pinned_hud.isVisible()
        assert not ordinary.isVisible()
    finally:
        manager._registered_flyouts = previous_registered
        manager._active_flyout = previous_active


def test_title_bar_resize_keeps_context_menu_flyouts(qapp):
    """Host Resize must not close File/Help (context_menu) after policy install."""
    from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar
    from ui import flyout_policy

    class _FakeFlyout:
        def __init__(self, group: str) -> None:
            self.flyout_group = group
            self._visible = True

        def isVisible(self) -> bool:
            return self._visible

        def hide(self) -> None:
            self._visible = False

    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    previous_hide = CustomTitleBar._hide_active_flyouts
    previous_patched = flyout_policy._TITLE_BAR_RESIZE_PATCHED
    previous_registered = set(getattr(manager, "_registered_flyouts", ()))
    previous_active = getattr(manager, "_active_flyout", None)
    try:
        # Force re-eval: simulate stock 3.1.1 close_all Resize path.
        def _stock_close_all(self) -> None:
            FlyoutManager.get_instance().close_all()

        CustomTitleBar._hide_active_flyouts = _stock_close_all
        flyout_policy._TITLE_BAR_RESIZE_PATCHED = False
        install_flyout_show_policy()
        assert flyout_policy._TITLE_BAR_RESIZE_PATCHED is True

        menu = _FakeFlyout("context_menu")
        other = _FakeFlyout("options")
        manager._registered_flyouts = {menu, other}
        manager._active_flyout = menu

        CustomTitleBar()._hide_active_flyouts()

        assert menu.isVisible()
        assert not other.isVisible()
        assert manager._active_flyout is menu
    finally:
        manager.set_show_policy(previous)
        CustomTitleBar._hide_active_flyouts = previous_hide
        flyout_policy._TITLE_BAR_RESIZE_PATCHED = previous_patched
        manager._registered_flyouts = previous_registered
        manager._active_flyout = previous_active


def test_button_suppress_click_clears_context_menu_flag(qapp):
    """Suppressed click must not leave ``_suppress_next_context_menu`` for next open."""
    from sli_ui_toolkit.ui.widgets.buttons.button import Button
    from ui import flyout_policy

    previous_emit = Button._emit_click_signals
    previous_patched = flyout_policy._BUTTON_SUPPRESS_PATCHED
    try:
        # Simulate stock 3.1.1 emit that only clears the click flag.
        def _stock_emit(self) -> None:
            if getattr(self, "_suppress_next_click", False):
                self._suppress_next_click = False
                return
            self.clicked.emit()

        Button._emit_click_signals = _stock_emit
        flyout_policy._BUTTON_SUPPRESS_PATCHED = False
        install_flyout_show_policy()
        assert flyout_policy._BUTTON_SUPPRESS_PATCHED is True

        button = Button("File")
        button._suppress_next_click = True
        button._suppress_next_context_menu = True
        clicks: list[int] = []
        button.clicked.connect(lambda: clicks.append(1))

        button._emit_click_signals()
        assert clicks == []
        assert getattr(button, "_suppress_next_click", False) is False
        assert getattr(button, "_suppress_next_context_menu", False) is False

        button._emit_click_signals()
        assert clicks == [1]
    finally:
        button.hide()
        button.close()
        button.deleteLater()
        qapp.processEvents()
        Button._emit_click_signals = previous_emit
        flyout_policy._BUTTON_SUPPRESS_PATCHED = previous_patched


def test_font_settings_flyout_group_and_registration(qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QWidget

    assert FontSettingsFlyout.flyout_group == "font_settings"
    manager = FlyoutManager.get_instance()
    host = QWidget()
    host.resize(320, 240)
    host.show()
    flyout = FontSettingsFlyout(host)
    try:
        assert flyout in manager._registered_flyouts
    finally:
        flyout.hide()
        flyout.close()
        flyout.deleteLater()
        host.hide()
        host.close()
        host.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()