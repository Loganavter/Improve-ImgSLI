"""Startup-trace spans for the tab-page build chain (S3 of
``plan-startup-first-open-perf-2026-10-24``).

The owner-host first open of Image Compare spends ~22 s inside
``registry.activate → _ensure_page → _create_and_assemble_page →
assemble_host_page → widget.assemble → ui/layout.py build_into``. These tests
pin the instrument that ranks those slices, and pin its falsifiability:

* the spans exist, in build order, only when ``IMGSLI_STARTUP_TRACE`` is on —
  the default path logs nothing and creates no timer;
* the event-loop turn probe *can* observe a turn it pumps (a probe that always
  answered 0 would prove nothing about the build);
* the real page build processes zero event-loop turns; a non-zero count means
  the build re-enters user code while the page is still half-assembled.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QStackedWidget

from core.startup_trace import reset_startup_trace
from tabs.contract import TabContext
from tabs.image_compare.tab import ImageCompareTab
from tabs.registry import TabRegistry
from tabs.use_cases import pages as pages_use_cases

SPAN_LOGGER = "ImproveImgSLI.startup"

# ``startup +   123ms (+   45ms)  <phase>`` / ``startup +     0ms  <phase>``
_SPAN_LINE = re.compile(
    r"^startup \+\s*\d+ms(?:\s*\(\+\s*\d+ms\))?\s+(?P<phase>\S.*)$"
)

# Build order. ``tab.page.loop_turns=<n>`` closes the chain, asserted apart
# because its name carries the counter value.
EXPECTED_SPANS = (
    "tab.page.build.begin",
    "tab.page.create",
    "tab.page.primitives",
    "tab.page.toolbar",
    "tab.page.panels",
    "tab.page.canvas",
    "tab.page.layout",
    "tab.page.wiring",
    "tab.page.assemble",
    "tab.page.polish",
    "tab.page.routing",
)


@pytest.fixture
def fresh_registry():
    """Isolated ``TabRegistry`` instance — no page leaks into other tests."""
    previous = TabRegistry._instance
    TabRegistry._instance = None
    try:
        yield TabRegistry()
    finally:
        TabRegistry._instance = previous


@pytest.fixture(autouse=True)
def _trace_clock():
    reset_startup_trace()
    yield
    reset_startup_trace()


def _build_page(registry: TabRegistry) -> tuple[object, QStackedWidget]:
    """Drive the production page-build chain with a minimal fake host ``ui``.

    Mirrors ``TabRegistry.activate``'s page path: the tab is registered, the
    host exposes only the two things the tab reads while building
    (``_current_language`` and ``legacy_tab_widgets``), so nothing here
    substitutes for the code under test.
    """
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
    page = pages_use_cases._create_and_assemble_page(
        registry, tab.session_type, tab
    )
    return page, stack


def _span_names(records) -> list[str]:
    names: list[str] = []
    for record in records:
        message = record.getMessage()
        if record.name != SPAN_LOGGER:
            continue
        match = _SPAN_LINE.match(message)
        if match:
            names.append(match.group(1))
    return names


def test_page_build_emits_the_ranked_spans(qtbot, fresh_registry, caplog, monkeypatch):
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    caplog.set_level(logging.INFO, logger=SPAN_LOGGER)

    page, stack = _build_page(fresh_registry)
    qtbot.addWidget(stack)
    assert page is not None and page._assembled

    names = _span_names(caplog.records)
    missing = [span for span in EXPECTED_SPANS if span not in names]
    assert not missing, f"missing startup spans: {missing} (got {names})"
    present = [name for name in names if name in EXPECTED_SPANS]
    assert present == sorted(present, key=EXPECTED_SPANS.index), (
        "spans must be emitted in build order, got " f"{present}"
    )


def test_page_build_processes_no_event_loop_turns(
    qtbot, fresh_registry, caplog, monkeypatch
):
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    caplog.set_level(logging.INFO, logger=SPAN_LOGGER)

    page, stack = _build_page(fresh_registry)
    qtbot.addWidget(stack)
    assert page is not None

    turns = [n for n in _span_names(caplog.records) if n.startswith("tab.page.loop_turns=")]
    assert turns, "the build must report an event-loop turn count"
    assert turns[-1] == "tab.page.loop_turns=0", (
        "the synchronous page build re-entered the event loop ("
        f"{turns[-1]}); user code ran against a half-built page"
    )


def test_event_loop_turn_probe_observes_a_turn_it_pumps(qapp):
    """Falsifiability: the probe detects an event-loop turn when one happens."""
    probe = pages_use_cases.EventLoopTurnProbe()
    probe.start()
    QTest.qWait(10)  # pumps the loop, so the 0 ms timer must fire
    assert probe.stop() >= 1


def test_event_loop_turn_probe_reports_zero_without_a_loop_turn(qapp):
    """The same probe, over synchronous work that never yields, reports 0."""
    probe = pages_use_cases.EventLoopTurnProbe()
    probe.start()
    total = sum(range(10000))  # pure computation, no loop entry
    assert total == 49995000
    assert probe.stop() == 0


def test_spans_are_off_by_default(qtbot, fresh_registry, caplog, monkeypatch):
    monkeypatch.delenv("IMGSLI_STARTUP_TRACE", raising=False)
    caplog.set_level(logging.INFO, logger=SPAN_LOGGER)

    created: list[object] = []

    class _SpyProbe(pages_use_cases.EventLoopTurnProbe):
        def __init__(self) -> None:
            super().__init__()
            created.append(self)

    monkeypatch.setattr(pages_use_cases, "EventLoopTurnProbe", _SpyProbe)

    page, stack = _build_page(fresh_registry)
    qtbot.addWidget(stack)
    assert page is not None
    assert not [n for n in _span_names(caplog.records) if n.startswith("tab.page.")]
    assert not created, "the turn probe must not be created when the trace is off"
