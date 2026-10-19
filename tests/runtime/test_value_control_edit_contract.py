"""App-side value-edit contract: Enter gates the arrows on every value control.

Owner rule (plan-nav-coverage-2026-10-19 § Value-edit contract): "слайдеров у
нас немало по всей аппе — все должны получать режим правки по Enter". The
toolkit half (`Slider`) already implements it; this file is the APP half — it
pins that every app value control follows the same user-visible behaviour and
that a NEW value control cannot ship uncovered.

The contract (identical to the toolkit `Slider`):

1. while merely navigating, arrows do NOT change the value — they navigate
   (the toolkit sections consult ``value_control_is_editing`` /
   ``arrow_gate_open``, so a control that exposes ``is_editing()`` only gets
   the arrows while it reports ``True``);
2. ``Enter`` enters edit mode;
3. arrows and WASD change the value in edit mode;
4. ``Enter`` commits — the adjusted value stays, edit mode ends;
5. ``Esc`` reverts to the value captured on entry and ends edit mode.

Real ``QTest.keyClick`` presses are used so the app-wide ``NavigationManager``
filter decides, exactly as in the running app (guide §11) — a direct
``keyPressEvent`` call would bypass the section gate this file exists to pin.

Coverage guard: ``VALUE_CONTROLS`` is the explicit registry (module:Class ->
reason + factory). ``test_every_app_value_control_is_registered`` scans the
source tree for classes that subclass ``Slider``/``ScrollValueButton`` or
define ``is_editing`` and fails when one is missing from the registry, so a
new value control that is not covered by the behavioural test is red.
"""

from __future__ import annotations

import ast
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import dataclass
from typing import Callable

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import NavigationManager, declare_navigation_rows
from sli_ui_toolkit.widgets import Button
from tests.contracts._framework import SRC, parse
from ui.widgets.scroll_value_button import ScrollValueButton
from ui.widgets.slider_hint import ValueSlider


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# --------------------------------------------------------------------------
# Registry — every app-side value control, with the reason it is in the list.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValueControl:
    """One app value control under the edit-mode contract."""

    module: str
    qualname: str
    factory: Callable[[], QWidget]
    reason: str

    @property
    def key(self) -> str:
        return f"{self.module}:{self.qualname}"


def _build_value_slider() -> QWidget:
    slider = ValueSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    return slider


def _build_scroll_value_button() -> QWidget:
    return ScrollValueButton(icon=None, min_value=0, max_value=10, start=5)



VALUE_CONTROLS: dict[str, ValueControl] = {
    control.key: control
    for control in (
        ValueControl(
            module="ui/widgets/slider_hint.py",
            qualname="ValueSlider",
            factory=_build_value_slider,
            reason=(
                "toolkit Slider subclass — inherits the Enter edit-mode "
                "contract (it only adds the hover value flyout)"
            ),
        ),
        ValueControl(
            module="ui/widgets/scroll_value_button.py",
            qualname="ScrollValueButton",
            factory=_build_scroll_value_button,
            reason=(
                "button-based value control with app-owned key handling — "
                "aligned to the same contract (Enter edit, Enter commit, "
                "Esc revert, is_editing() exposed for the section gate)"
            ),
        ),
    )
}

# Base class names whose app subclasses are inherently value controls: if a
# new ``FooSlider(Slider)`` appears anywhere under ``src/`` it must be listed
# above. ``is_editing`` is the contract marker itself — any app class that
# defines it is a value-edit control by definition and must be covered too.
_VALUE_BASE_NAMES = {"Slider", "ScrollValueButton", "ValueSlider"}

#: Discovered value controls whose Enter/WASD/Esc contract is pinned by a
#: DEDICATED file (the scalar harness below reads one number; a 2-D surface
#: cannot be driven by ``entry + 1`` arithmetic). Exemptions are recorded, not
#: silent: a new entry needs a named covering test.
_COVERED_ELSEWHERE: dict[str, str] = {
    "ui/widgets/color/picker_dialog.py:_SVSquare": (
        "2-D colour surface — pinned by tests/runtime/test_color_picker_navigation.py "
        "(reach + Enter edit + WASD + Enter commit + Esc revert)"
    ),
}
_CONTRACT_METHOD = "is_editing"


def _discovered_value_controls() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        tree = parse(path)
        if tree is None:
            continue
        module = path.relative_to(SRC).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {
                base.attr if isinstance(base, ast.Attribute) else
                base.id if isinstance(base, ast.Name) else ""
                for base in node.bases
            }
            methods = {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if bases & _VALUE_BASE_NAMES or _CONTRACT_METHOD in methods:
                found.add(f"{module}:{node.name}")
    return found


# --------------------------------------------------------------------------
# Host: one navigation row holding the control + a neighbour.
# --------------------------------------------------------------------------


@dataclass
class _Host:
    host: QWidget
    control: QWidget
    neighbour: QWidget
    row: QWidget


def _value(widget: QWidget) -> int:
    getter = getattr(widget, "get_value", None)
    if callable(getter):
        return int(getter())
    return int(widget.value())  # type: ignore[attr-defined]


@pytest.fixture
def make_host(qtbot):
    """Build ``[control][neighbour]`` as one declared navigation row.

    The neighbour gives Left/Right a real navigation target, so
    "arrows while navigating must not change the value" asserts that focus
    actually moved instead of the key being silently dropped.
    """
    hosts: list[_Host] = []

    def _make(key: str) -> _Host:
        control = VALUE_CONTROLS[key].factory()
        neighbour = Button(icon=None, text="x")
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(control)
        row_layout.addWidget(neighbour)

        host = QWidget()
        host.resize(360, 160)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(row)
        qtbot.addWidget(host)
        host.show()
        qtbot.waitExposed(host)
        declare_navigation_rows(host, [row], tag=f"value-edit-{key}")
        built = _Host(host=host, control=control, neighbour=neighbour, row=row)
        hosts.append(built)
        return built

    try:
        yield _make
    finally:
        manager = NavigationManager.get_instance()
        for built in hosts:
            manager.unregister(built.host)


def _kbd_focus(widget: QWidget, qapp) -> None:
    """Grant keyboard (arrow-style) focus: modality comes from the last input
    device, not the FocusReason (guide §7)."""
    widget.clearFocus()
    QTest.keyClick(widget, Qt.Key.Key_F1)
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()


def _press(widget: QWidget, key: Qt.Key, qapp) -> None:
    QTest.keyClick(widget, key)
    qapp.processEvents()


# --------------------------------------------------------------------------
# Coverage guard
# --------------------------------------------------------------------------


def test_every_app_value_control_is_registered():
    """A new value control must be added to ``VALUE_CONTROLS`` (with a reason).

    Red when a class subclasses a value base or defines ``is_editing`` and is
    not listed — that is exactly the "new control slipped past the contract"
    case this guard exists for.
    """
    discovered = _discovered_value_controls() - set(_COVERED_ELSEWHERE)
    registered = set(VALUE_CONTROLS)
    assert not discovered - registered, (
        "app value control(s) not covered by the value-edit contract test — "
        "add them to VALUE_CONTROLS with a reason and a factory:\n"
        + "\n".join(sorted(discovered - registered))
    )
    assert not registered - discovered, (
        "VALUE_CONTROLS lists classes the source scan no longer finds "
        "(stale registry entry):\n" + "\n".join(sorted(registered - discovered))
    )


def test_registry_keys_are_importable_and_expose_is_editing(qapp):
    """Every registered class exposes ``is_editing()`` and starts idle.

    ``is_editing`` is what the toolkit sections duck-type to decide whether
    arrows belong to the control (``arrow_gate_open``). A class that does not
    expose it never receives arrows in edit mode.
    """
    import importlib

    for key, control in VALUE_CONTROLS.items():
        module_name = control.module.removesuffix(".py").replace("/", ".")
        cls = getattr(importlib.import_module(module_name), control.qualname)
        query = getattr(cls, _CONTRACT_METHOD, None)
        assert callable(query), (
            f"{key} must expose is_editing() -> bool (the section gate reads it)"
        )
        instance = control.factory()
        assert instance.is_editing() is False, f"{key} must start out of edit mode"


# --------------------------------------------------------------------------
# Behavioural contract
# --------------------------------------------------------------------------


@pytest.mark.parametrize("control_key", sorted(VALUE_CONTROLS))
def test_arrows_navigate_while_not_editing(control_key, make_host, qapp):
    built = make_host(control_key)
    control = built.control

    _kbd_focus(control, qapp)
    assert control.is_editing() is False
    entry = _value(control)

    _press(control, Qt.Key.Key_Right, qapp)

    assert _value(control) == entry, (
        "an arrow while merely navigating must never change the value"
    )
    assert QApplication.focusWidget() is built.neighbour, (
        "Right must navigate to the neighbouring control, not be swallowed"
    )


@pytest.mark.parametrize("control_key", sorted(VALUE_CONTROLS))
def test_enter_adjust_commit_and_escape_revert(control_key, make_host, qapp):
    built = make_host(control_key)
    control = built.control

    _kbd_focus(control, qapp)
    entry = _value(control)

    # Enter enters edit mode.
    _press(control, Qt.Key.Key_Return, qapp)
    assert control.is_editing() is True, "Enter must enter edit mode"

    # Arrows adjust in edit mode (not navigate): the neighbour must not take
    # focus and the value must move.
    _press(control, Qt.Key.Key_Right, qapp)
    assert _value(control) == entry + 1
    assert QApplication.focusWidget() is control
    _press(control, Qt.Key.Key_Left, qapp)
    assert _value(control) == entry

    # WASD is the same 2-D-surface convention the toolkit slider uses.
    for key, expected in (
        (Qt.Key.Key_D, entry + 1),
        (Qt.Key.Key_A, entry),
        (Qt.Key.Key_W, entry + 1),
        (Qt.Key.Key_Up, entry + 2),
        (Qt.Key.Key_S, entry + 1),
        (Qt.Key.Key_Down, entry),
    ):
        _press(control, key, qapp)
        assert _value(control) == expected, f"{key} must adjust the value in edit mode"

    # Enter commits: the adjusted value stays and edit mode ends.
    _press(control, Qt.Key.Key_D, qapp)
    committed = _value(control)
    assert committed != entry
    _press(control, Qt.Key.Key_Return, qapp)
    assert control.is_editing() is False, "Enter must commit and leave edit mode"
    assert _value(control) == committed, "Enter must keep the adjusted value"

    # Arrows navigate again after the commit.
    _press(control, Qt.Key.Key_Right, qapp)
    assert _value(control) == committed
    assert QApplication.focusWidget() is built.neighbour

    # Esc reverts to the value captured when edit mode was entered.
    _kbd_focus(control, qapp)
    _press(control, Qt.Key.Key_Return, qapp)
    assert control.is_editing() is True
    _press(control, Qt.Key.Key_Right, qapp)
    _press(control, Qt.Key.Key_Right, qapp)
    assert _value(control) == committed + 2
    _press(control, Qt.Key.Key_Escape, qapp)
    assert control.is_editing() is False, "Esc must leave edit mode"
    assert _value(control) == committed, "Esc must revert to the entry value"


def test_scroll_value_button_enter_does_not_mirror_right_click(make_host, qapp):
    """Enter belongs to the value-edit contract now, not to ``rightClicked``.

    Owner contract (plan-nav-coverage-2026-10-19): Enter enters editing on
    every value control. ``rightClicked`` stays the mouse right-button signal
    (its colour/context menus are still reached with an actual right click).
    """
    built = make_host(
        "ui/widgets/scroll_value_button.py:ScrollValueButton"
    )
    control = built.control
    seen: list[bool] = []
    control.rightClicked.connect(lambda: seen.append(True))

    _kbd_focus(control, qapp)
    _press(control, Qt.Key.Key_Return, qapp)

    assert seen == [], "Enter must enter edit mode, not emit the RMB signal"
    assert control.is_editing() is True
