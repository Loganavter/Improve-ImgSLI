"""Multi-compare navigation registration + lifecycle (keyboard-nav plan D1).

Pins the host contract the keyboard-navigation guide documents for
multi_compare (§6D) but no test covered: ``on_activated`` registers ONE
``ToolbarRowsSection`` over the rows ``[toolbar, footer]`` (tag
``multi-compare``) with the shell widget as owner, and both
``on_deactivated`` and ``dispose`` unregister it.

Introspection is public wherever the toolkit offers it —
``nav_graph.snapshot()`` for graph membership, ``NavigationManager``
``should_intercept`` for row ownership — plus one isolated private access
for the tag/rows identity (the public snapshot carries neither). The rows
ORDER (toolbar above footer) is proven behaviorally: a real Down-traversal
from a toolbar button must land in the footer.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.managers import NavigationManager, nav_graph

from tabs.multi_compare.tab import MultiCompareTab
from tabs.multi_compare.tests.runtime._session_harness import FakeCoreStore


class _FakeQSettings:
    """In-memory QSettings so session seeding never touches user config."""

    def __init__(self, *_args):
        self._mem: dict = {}

    def value(self, key, default=None):
        return self._mem.get(key, default)

    def setValue(self, key, value):
        self._mem[key] = value

    def sync(self):
        pass


def _memory_qsettings(monkeypatch):
    from tabs.use_cases import session_state as _mod

    fake = _FakeQSettings()
    monkeypatch.setattr(_mod, "QSettings", lambda *_a: fake)


def _context(core):
    return SimpleNamespace(
        store=core,
        _tr=lambda key, default=None: default or key,
        main_window=None,
        call_service=lambda *_a, **_k: None,
        settings=None,
    )


def _toolbar_rows_section(graph):
    return [n for n in graph.nodes if n.section == "ToolbarRowsSection"]


def _registered_spec(manager, owner):
    """Isolated private access: the public ``nav_graph.snapshot()`` carries
    neither the section tag nor its rows provider, so pin those identity
    facts here. Single seam — everything else in this module is public API.
    """
    for owner_obj, spec in manager._sections:
        if owner_obj is owner:
            return spec
    return None


def test_activation_registers_toolbar_and_footer_section(qapp, monkeypatch):
    _memory_qsettings(monkeypatch)
    core = FakeCoreStore(["mc-nav"])
    core.ensure_slot("mc-nav")
    tab = MultiCompareTab()
    page = tab.create_page(None, _context(core))
    tab.on_activated(_context(core))
    # The host shows the page when the tab becomes current; ownership lookups
    # (ToolbarRowsSection.owns) filter on row visibility, so mirror that.
    page.show()
    QTest.qWait(50)
    try:
        widget = tab._widget
        manager = NavigationManager.get_instance()

        nodes = _toolbar_rows_section(nav_graph.snapshot())
        assert len(nodes) == 1
        assert nodes[0].owner == "MultiCompareWidget"
        assert nodes[0].visible is True

        # Row ownership via the public should_intercept (the section's
        # extra_keys are Left/Right): the section owns both the toolbar row
        # and the footer row — including the buttons inside them.
        assert manager.should_intercept(Qt.Key.Key_Right, widget.toolbar)
        assert manager.should_intercept(Qt.Key.Key_Right, widget.footer)
        assert manager.should_intercept(Qt.Key.Key_Right, widget.toolbar.btn_add)
        assert manager.should_intercept(Qt.Key.Key_Right, widget.footer.btn_save)

        # Tag + rows identity (private seam — see _registered_spec).
        spec = _registered_spec(manager, widget)
        assert spec is not None
        assert spec._tag == "multi-compare"
        assert list(spec._rows_provider()) == [widget.toolbar, widget.footer]
    finally:
        tab.on_deactivated(_context(core))
        tab.dispose()


def test_section_rows_order_toolbar_above_footer(qapp, monkeypatch):
    """Rows order [toolbar, footer] proven by real traversal, not internals."""
    _memory_qsettings(monkeypatch)
    core = FakeCoreStore(["mc-nav"])
    core.ensure_slot("mc-nav")
    tab = MultiCompareTab()
    page = tab.create_page(None, _context(core))
    tab.on_activated(_context(core))
    page.show()
    QTest.qWait(50)
    try:
        widget = tab._widget
        manager = NavigationManager.get_instance()
        spec = _registered_spec(manager, widget)
        assert spec is not None

        widget.toolbar.btn_add.setFocus(Qt.FocusReason.OtherFocusReason)
        QTest.qWait(20)
        assert spec.navigate(Qt.Key.Key_Down, widget.toolbar.btn_add) is True
        QTest.qWait(20)
        assert QApplication.focusWidget() is widget.footer.btn_save

        # And back up out of the footer into the toolbar row.
        assert spec.navigate(Qt.Key.Key_Up, widget.footer.btn_save) is True
        QTest.qWait(20)
        focused = QApplication.focusWidget()
        assert focused is not None
        assert focused is not widget.footer.btn_save
        assert widget.toolbar.isAncestorOf(focused)
    finally:
        tab.on_deactivated(_context(core))
        tab.dispose()


def test_deactivation_unregisters_section(qapp, monkeypatch):
    _memory_qsettings(monkeypatch)
    core = FakeCoreStore(["mc-nav"])
    core.ensure_slot("mc-nav")
    tab = MultiCompareTab()
    page = tab.create_page(None, _context(core))
    tab.on_activated(_context(core))
    page.show()
    QTest.qWait(50)
    widget = tab._widget
    manager = NavigationManager.get_instance()
    assert manager.should_intercept(Qt.Key.Key_Right, widget.toolbar)  # precondition

    tab.on_deactivated(_context(core))
    assert not manager.should_intercept(Qt.Key.Key_Right, widget.toolbar)
    assert not manager.should_intercept(Qt.Key.Key_Right, widget.footer)
    assert _toolbar_rows_section(nav_graph.snapshot()) == []
    tab.dispose()


def test_dispose_unregisters_section(qapp, monkeypatch):
    _memory_qsettings(monkeypatch)
    core = FakeCoreStore(["mc-nav"])
    core.ensure_slot("mc-nav")
    tab = MultiCompareTab()
    page = tab.create_page(None, _context(core))
    tab.on_activated(_context(core))
    page.show()
    QTest.qWait(50)
    widget = tab._widget
    manager = NavigationManager.get_instance()
    assert manager.should_intercept(Qt.Key.Key_Right, widget.toolbar)  # precondition

    tab.dispose()
    assert not manager.should_intercept(Qt.Key.Key_Right, widget.toolbar)
    assert not manager.should_intercept(Qt.Key.Key_Right, widget.footer)
    assert _toolbar_rows_section(nav_graph.snapshot()) == []
