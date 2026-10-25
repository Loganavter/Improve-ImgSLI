"""The image_compare toolbar's mode variants are built on first use.

Six controls (``btn_orientation_simple``, ``btn_divider_visible``,
``btn_magnifier_orientation_simple``, ``btn_magnifier_divider_visible``,
``btn_magnifier_guides_simple``, ``btn_magnifier_color_settings_beginner``)
belong to the ``beginner``/``expert``/``advanced`` toolbar layouts only, and no
layout mode is applied while the page is being built. They used to be
constructed in ``ImageComparePrimitivesFactory.build`` and hidden by the first
``apply_mode`` — ~8 ms of the ~30 ms ``tab.page.primitives`` slice (offscreen,
warm: six ``Button.__init__``) spent on widgets nothing had asked for yet. The
second ``ColorSettingsButton`` left that slice too, but an out-of-scope hover
controller still builds it later in ``assemble`` (see
``EAGER_BY_HOVER_CONTROLLER``).

What these tests pin:

* a fresh factory builds none of them (no widget, not merely "hidden");
* the tree a mode switch produces is byte-identical to the pre-change tree —
  same widgets, same parentage, same visibility, same geometry, same child
  counts — for all four modes (``fixtures/ic_mode_layout_baseline.txt`` was
  captured from the eager factory at the parent commit);
* creation order is irrelevant: forcing every variant to exist *before*
  ``apply_mode`` and building them lazily during it produce the same dump;
* switching modes repeatedly neither duplicates nor re-creates a variant;
* the ``tab.page.primitives.<slice>`` marks appear only with
  ``IMGSLI_STARTUP_TRACE=1`` and start no clock when it is off.

Regenerate the baseline after an intentional toolbar change::

    PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 \\
        src/tabs/image_compare/tests/runtime/test_ic_lazy_mode_variants.py
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QStackedWidget, QWidget

from core.log_names import APP_LOGGER_NAME
from core import startup_trace
from tabs.contract import TabContext
from tabs.image_compare.tab import ImageCompareTab
from tabs.image_compare.ui.layout_definitions import (
    ALL_KNOWN_WIDGETS,
    LAYOUT_DEFINITIONS,
)
from tabs.image_compare.ui.layout_manager import ImageCompareLayoutManager
from tabs.image_compare.ui.primitives import (
    _MODE_VARIANT_BUILDERS,
    _MODE_VARIANT_PARENT,
    _MODE_VARIANT_STORE,
    ImageComparePrimitivesFactory,
)
from tabs.image_compare.widget import ImageCompareWidget
from tabs.registry import TabRegistry
from tabs.use_cases import pages as pages_use_cases

SPAN_LOGGER = f"{APP_LOGGER_NAME}.startup"
SLICE_SPANS = (
    "tab.page.primitives.static_widgets",
    "tab.page.primitives.selection_controls",
    "tab.page.primitives.view_controls",
    "tab.page.primitives.video_controls",
    "tab.page.primitives.slider_controls",
    "tab.page.primitives.text_and_status_widgets",
)
GROUPS = (
    "line_group_container",
    "view_group_container",
    "magnifier_group_container",
    "record_group_container",
)
MODES = tuple(LAYOUT_DEFINITIONS)
BASELINE = Path(__file__).parent / "fixtures" / "ic_mode_layout_baseline.txt"

#: The one variant an out-of-scope consumer still builds during ``assemble``:
#: ``MagnifierSettingsHoverController._wire`` links the color-options flyout of
#: both color buttons (``transient_magnifier_settings.py``), so the beginner
#: composite cannot stay lazy until that wiring moves to its first ``_show``.
EAGER_BY_HOVER_CONTROLLER = "btn_magnifier_color_settings_beginner"

#: Pages/hosts built by these tests are held, never ``deleteLater``-ed: a
#: ``ScrollableComboBox`` (or any toolkit widget with a queued width-adjust
#: timer) deleted while that timer is pending fires it against a dead C++
#: object, and pytest-qt blames whichever test is running then.
_HOLD: list[object] = []


# ---------------------------------------------------------------------------
# production page build + mode path
# ---------------------------------------------------------------------------


def _new_registry() -> TabRegistry:
    """Isolated registry instance — no page leaks into other tests."""
    previous = TabRegistry._instance
    TabRegistry._instance = None
    try:
        return TabRegistry()
    finally:
        TabRegistry._instance = previous


@pytest.fixture
def fresh_registry():
    return _new_registry()


def _build_page(registry: TabRegistry) -> tuple[ImageCompareWidget, QStackedWidget]:
    """Drive the production page-build chain (same fake host as
    ``test_page_build_spans``), so nothing here substitutes for the code under
    test: ``_create_and_assemble_page`` runs the primitives factory and
    ``ImageCompareWidget.assemble``."""
    tab = ImageCompareTab()
    registry._tabs = {tab.session_type: tab}
    registry._pages = {}
    registry._pending_pages = {tab.session_type: tab}
    stack = QStackedWidget()
    registry._stack = stack
    registry._context = TabContext(
        store=None,
        event_bus=SimpleNamespace(emit=lambda *_a, **_k: None),
        main_window=None,
    )
    registry._ui = SimpleNamespace(
        _current_language=lambda: "en",
        main_window=None,
        store=None,
        legacy_tab_widgets={},
    )
    page = pages_use_cases._create_and_assemble_page(registry, tab.session_type, tab)
    assert isinstance(page, ImageCompareWidget)
    stack.addWidget(page)
    _HOLD.append(stack)
    return page, stack


def _apply(page: ImageCompareWidget, mode: str, qapp) -> None:
    ImageCompareLayoutManager(page, None).apply_mode(mode)
    qapp.processEvents()


def _created_variants(page: ImageCompareWidget) -> dict:
    return dict(page.__dict__.get(_MODE_VARIANT_STORE) or {})


# ---------------------------------------------------------------------------
# offscreen layout dump (the pre-change baseline format)
# ---------------------------------------------------------------------------


def _name_map(page: ImageCompareWidget) -> dict[int, str]:
    names: dict[int, str] = {id(page): "<page>"}
    for attr, value in list(vars(page).items()):
        if attr.startswith("_ic_mode_variants"):
            continue
        if isinstance(value, QWidget):
            names.setdefault(id(value), attr)
    for attr, value in _created_variants(page).items():
        if isinstance(value, QWidget):
            names.setdefault(id(value), attr)
    return names


def _widget_line(name: str, widget: QWidget, names: dict[int, str]) -> str:
    parent = widget.parentWidget()
    if parent is None:
        parent_name = "<none>"
    else:
        parent_name = names.get(id(parent), f"<foreign:{type(parent).__name__}>")
    geom = widget.geometry()
    return (
        f"known {name} {type(widget).__name__} parent={parent_name} "
        f"hidden={int(widget.isHidden())} "
        f"geom={geom.x()},{geom.y()},{geom.width()},{geom.height()}"
    )


def dump_layout(page: ImageCompareWidget) -> str:
    """Stable text dump: inventory, parentage, visibility, geometry, counts."""
    names = _name_map(page)
    lines: list[str] = []
    for name in sorted(ALL_KNOWN_WIDGETS):
        widget = getattr(page, name, None)
        if widget is None:
            lines.append(f"known {name} <missing>")
            continue
        lines.append(_widget_line(name, widget, names))
    for group in GROUPS:
        container = getattr(page, group)
        layout = container.layout()
        order: list[str] = []
        for index in range(layout.count() if layout is not None else 0):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            order.append(
                names.get(id(widget), f"<unnamed:{type(widget).__name__}>")
                if widget is not None
                else "<empty>"
            )
        geom = container.geometry()
        lines.append(
            f"group {group} order={','.join(order)} "
            f"hidden={int(container.isHidden())} "
            f"geom={geom.x()},{geom.y()},{geom.width()},{geom.height()}"
        )
    counts: dict[str, int] = {}
    for child in page.findChildren(QWidget):
        counts[type(child).__name__] = counts.get(type(child).__name__, 0) + 1
    lines.append("counts " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


def _dump_all_modes(qapp, registry: TabRegistry | None = None) -> dict[str, str]:
    registry = registry if registry is not None else _new_registry()
    dumps: dict[str, str] = {}
    for mode in MODES:
        page, stack = _build_page(registry)
        _apply(page, mode, qapp)
        dumps[mode] = dump_layout(page)
        qapp.processEvents()
        registry._pages.clear()
        registry._pending_pages = {}
    return dumps


def _render_baseline(dumps: dict[str, str]) -> str:
    blocks = [f"== {mode}\n{dumps[mode]}" for mode in MODES]
    return "\n\n".join(blocks) + "\n"


def _parse_baseline(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("== "):
            current = line[3:].strip()
            parsed[current] = ""
            continue
        if current is not None and line.strip():
            parsed[current] += (line + "\n")
    return {mode: block.rstrip("\n") for mode, block in parsed.items()}


def main() -> int:  # pragma: no cover - regeneration entry point
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(_render_baseline(_dump_all_modes(app)), encoding="utf-8")
    print(f"wrote {BASELINE}")
    return 0


# ---------------------------------------------------------------------------
# (a) a fresh factory builds none of them
# ---------------------------------------------------------------------------


def test_factory_build_creates_no_mode_variant(qapp):
    """``build()`` alone must not construct any of the six widgets."""
    host = QWidget()
    page = ImageCompareWidget()
    _HOLD.extend((host, page))

    for name in _MODE_VARIANT_BUILDERS:
        assert not hasattr(page, name), (
            f"{name} must not resolve before the page is built — a probe on an "
            "unbuilt page must not create a parentless widget"
        )

    ImageComparePrimitivesFactory(
        page, SimpleNamespace(_current_language=lambda: "en")
    ).build(host)

    created = _created_variants(page)
    assert created == {}, (
        "the primitives build constructed mode variants eagerly: "
        f"{sorted(created)} — they belong to a toolbar mode that is not "
        "applied until after the page is built"
    )
    assert page.__dict__[_MODE_VARIANT_PARENT] is host
    qapp.processEvents()


def test_access_creates_each_variant_once(qapp):
    """Every consumer reads the same attribute name; it must materialise once."""
    host = QWidget()
    page = ImageCompareWidget()
    _HOLD.extend((host, page))
    ImageComparePrimitivesFactory(
        page, SimpleNamespace(_current_language=lambda: "en")
    ).build(host)

    for name in _MODE_VARIANT_BUILDERS:
        first = getattr(page, name)
        second = getattr(page, name)
        assert first is second, f"{name} was rebuilt on second access"
        assert first.parentWidget() is host
        # Implicitly hidden (the host is not shown), exactly like the eager
        # build's widgets were before ``apply_mode`` hid them explicitly.
        assert not first.isVisible(), f"{name} must not be visible yet"
    qapp.processEvents()


def test_full_page_build_creates_only_the_hover_controller_composite(fresh_registry, qapp):
    """The production chain builds at most the one variant an out-of-scope
    consumer (the magnifier hover controller's flyout link) asks for."""
    page, _stack = _build_page(fresh_registry)
    qapp.processEvents()

    created = sorted(_created_variants(page))
    assert created in ([], [EAGER_BY_HOVER_CONTROLLER]), (
        "the page build constructed mode variants eagerly: "
        f"{created} — they belong to a toolbar mode applied after the build "
        "(see _MODE_VARIANT_BUILDERS in primitives.py)"
    )


# ---------------------------------------------------------------------------
# (b) inventory + geometry identical to the pre-change tree
# ---------------------------------------------------------------------------


def test_mode_layout_matches_the_pre_change_baseline(qapp, fresh_registry):
    expected = _parse_baseline(BASELINE.read_text(encoding="utf-8"))
    assert tuple(expected) == MODES, f"baseline modes {tuple(expected)} != {MODES}"

    actual = _dump_all_modes(qapp, fresh_registry)
    for mode in MODES:
        assert actual[mode] == expected[mode], (
            f"the {mode!r} toolbar tree differs from the pinned pre-change "
            "baseline (fixtures/ic_mode_layout_baseline.txt). If the toolbar "
            "changed on purpose, regenerate it with the module docstring's "
            f"command. Got:\n{actual[mode]}"
        )


def test_creation_order_does_not_change_the_tree(qapp, fresh_registry):
    """Eager (all six forced before ``apply_mode``) vs lazy: same dump.

    This is the risk the change introduces — the widgets are now created in a
    different order relative to the containers, so their parentage/geometry
    could drift. Forcing them up front reproduces the pre-change build.
    """
    registry = fresh_registry
    for mode in MODES:
        eager, _eager_stack = _build_page(registry)
        for name in _MODE_VARIANT_BUILDERS:
            getattr(eager, name)  # pre-change: constructed in build()
        _apply(eager, mode, qapp)
        eager_dump = dump_layout(eager)

        registry._pages.clear()
        registry._pending_pages = {}

        lazy, _lazy_stack = _build_page(registry)
        _apply(lazy, mode, qapp)
        lazy_dump = dump_layout(lazy)

        assert lazy_dump == eager_dump, (
            f"{mode!r}: the lazily built tree differs from the eagerly built "
            f"one.\neager:\n{eager_dump}\nlazy:\n{lazy_dump}"
        )

        registry._pages.clear()
        registry._pending_pages = {}


# ---------------------------------------------------------------------------
# (c) toggling modes duplicates nothing
# ---------------------------------------------------------------------------


def test_toggling_modes_keeps_one_widget_per_name(qapp, fresh_registry):
    page, _stack = _build_page(fresh_registry)
    qapp.processEvents()

    _apply(page, "beginner", qapp)
    first = {name: getattr(page, name) for name in _MODE_VARIANT_BUILDERS}
    beginner_counts = dump_layout(page).splitlines()[-1]
    beginner_orders = [
        line for line in dump_layout(page).splitlines() if line.startswith("group ")
    ]

    for mode in ("expert", "beginner", "expert", "beginner", "minimal", "beginner"):
        _apply(page, mode, qapp)
        for name, widget in first.items():
            assert getattr(page, name) is widget, (
                f"{name} was re-created while switching to {mode!r} — "
                "a mode toggle must reuse the existing widget"
            )
        names = _name_map(page)
        for name in _MODE_VARIANT_BUILDERS:
            widget = getattr(page, name)
            impostors = [
                child
                for child in page.findChildren(QWidget)
                if names.get(id(child)) == name and child is not widget
            ]
            assert not impostors, f"{name} has a duplicate in the tree"

    final = dump_layout(page).splitlines()
    assert final[-1] == beginner_counts, "a mode round trip changed the child counts"
    assert [line for line in final if line.startswith("group ")] == beginner_orders


# ---------------------------------------------------------------------------
# (d) the per-slice spans: present with the trace, absent (and free) without
# ---------------------------------------------------------------------------


def _span_names(records) -> list[str]:
    names: list[str] = []
    for record in records:
        if record.name != SPAN_LOGGER:
            continue
        message = record.getMessage()
        if message.startswith("startup +"):
            names.append(message.rsplit("  ", 1)[-1])
    return names


def test_primitives_slices_are_emitted_in_order(fresh_registry, caplog, monkeypatch, qapp):
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    caplog.set_level(logging.INFO, logger=SPAN_LOGGER)

    page, _stack = _build_page(fresh_registry)
    qapp.processEvents()
    assert page is not None

    names = _span_names(caplog.records)
    present = [name for name in names if name in SLICE_SPANS]
    assert present == list(SLICE_SPANS), (
        f"expected the six primitives slices in build order, got {present}"
    )
    # Each slice must sit inside the enclosing ``tab.page.primitives`` span.
    assert names.index("tab.page.create") < names.index(SLICE_SPANS[0])
    assert names.index(SLICE_SPANS[-1]) < names.index("tab.page.primitives")


def test_primitives_slices_cost_nothing_when_the_trace_is_off(
    fresh_registry, caplog, monkeypatch, qapp
):
    monkeypatch.delenv("IMGSLI_STARTUP_TRACE", raising=False)
    monkeypatch.delenv("BLINKTABLE_STARTUP_TRACE", raising=False)
    caplog.set_level(logging.INFO, logger=SPAN_LOGGER)
    startup_trace.reset_startup_trace()

    page, _stack = _build_page(fresh_registry)
    qapp.processEvents()
    assert page is not None

    assert not [n for n in _span_names(caplog.records) if n.startswith("tab.page.")]
    assert startup_trace._origin is None and startup_trace._last is None, (
        "the trace clock started with the flag off — startup_mark must return "
        "before touching the clock"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
