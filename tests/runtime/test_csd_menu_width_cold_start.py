"""Cold-start cost of the CSD menu trigger width estimate.

SYMPTOM (investigation, cold launch on the owner's Windows build): the GUI
blocks 2.9-5.7 s inside ``csd_menu_strip._estimate_menu_button_width``
(``fm.horizontalAdvance(label)`` — the first text advance in the process, so
the first trigger pays the whole process's initialisation there). Three
mechanisms still fit:
(1) one-time font engine init (Windows/DirectWrite), (2) glyph fallback across
the font database for non-primary script labels, (3) N per-trigger
``QFontMetrics`` constructions.

These three tests pin the *shape* of the cost — not a fix — so a later
"speed up the estimator" patch cannot be mistaken for a fix of the wrong
layer. Each names what it would catch at review time.

Raw numbers behind the budgets (this cell: Linux/fontconfig, offscreen,
PySide6 6.11.2 — INDICATIVE ONLY, the owner's cold path is Windows/DirectWrite;
``REPORT.md`` carries the probe output): first advance in a fresh interpreter
39-49 ms before the startup modules are imported, 31-35 ms after, and
script-independent either way; the same advance repeated 0.01-0.2 ms; with the
engine warm, the first label of a non-primary script costs ru 5.5-7.8 ms /
zh 10.8-20.8 ms while en/pt_BR cost 0.03-0.08 ms; 200 warm estimates 2.1 ms.

Verdict these tests encode: mechanism (1) dominates (a primary-script advance
with no fallback work pays the same tens of ms), (2) is real but one to two
orders of magnitude smaller and one-time per script, (3) is refuted as a cost
contributor (2 constructions per strip build, ~10 us/call warm).

Cold-launch A/B build (``w2-fontwarm``, P1 lane startup)
-------------------------------------------------------
Two instruments were added so ONE owner run can say where a cold launch's 3-4 s
lands, plus the caching the strip should have had anyway:

* ``CsdMenuStrip`` keeps ONE ``QFontMetrics`` per strip instance (shared with
  the dropdown rows it builds) instead of constructing one per call site; every
  metrics-change path (``connect_ui_metrics`` font/scale, ``FontChange``) drops
  it. The tests below pin that the cached path returns the SAME width as the
  uncached estimator (the pre-change code path, kept as its own oracle) and
  that the cache is rebuilt on a live font/scale change;
* ``src/__main__.py`` pre-warms the engine right after ``QApplication`` when
  ``IMGSLI_FONT_PREWARM`` is truthy and records ``font.prewarm cost_ms=…`` in
  ``startup_early.log``. That is an instrument, NOT the shipped fix: the
  measured ``xfail`` in ``test_first_advance_is_prewarmed`` stays until the
  owner's A/B says the pre-warm actually covers the stall.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtGui import QFontMetrics

from sli_ui_toolkit.managers import UiScale, scaled_px, ui_font
from ui.main_window.csd_menu_strip import _estimate_menu_button_width

REPO_ROOT = Path(__file__).resolve().parents[2]

# The shipped UI locales (``src/resources/i18n/<code>``); their trigger labels
# are what ``_estimate_menu_button_width`` actually measures at startup.
_SHIPPED_LOCALES = ("en", "ru", "zh", "pt_BR")
# The shipped CSD menu set: File + Help (``MainWindowMenuController.build_menus``).
_TRIGGER_KEYS = ("menu.file", "menu.help")

_ESTIMATE_CALLS = 200
# Warm batch budget. Measured 2.1 ms after every script is primed; 50 ms leaves
# >20x for a loaded ``-n 4`` worker and still fails if a per-call cost appears.
_ESTIMATE_BUDGET_MS = 50.0
# Cached-metrics budget: ONE shared QFontMetrics for the whole strip (every
# trigger, and the dropdown rows the strip builds from it) — rebuilt only when
# the UI font or scale actually changes.
_CONSTRUCTIONS_PER_STRIP = 1
# A scale the strip's live-refresh test moves to: text advances scale with it,
# so a cache that did NOT refresh would keep the old widths.
_CACHE_PROBE_SCALE = 1.5
# A pre-warmed engine answers in ~0.02 ms; the cold first advance measured
# 26-54 ms here. 5 ms is far above jitter and far below the cold cost.
_COLD_ADVANCE_BUDGET_MS = 5.0

# Fresh-interpreter probe. Order matters: the cold-path modules are imported
# BEFORE the measurement, so the numbers describe the state the title bar is
# built in (a pre-warm wired at import time, or exposed as
# ``prewarm_font_engine()`` on a startup module, therefore counts as startup
# work — that is what flips this test green).
_CHILD_PROBE = r'''
import json, os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from PySide6.QtWidgets import QApplication

app = QApplication([])
from PySide6.QtGui import QFontMetrics
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from resources.translations import tr

language = sys.argv[1]
label = tr("menu.file", language)
if not label or label == "menu.file":
    print(json.dumps({"error": "missing catalog entry menu.file for " + language}))
    raise SystemExit(2)

import ui.main_window.startup  # noqa: F401  (cold path module chain)
import ui.main_window.menu_controller  # noqa: F401
for module in (
    sys.modules["ui.main_window.startup"],
    sys.modules["ui.main_window.menu_controller"],
):
    hook = getattr(module, "prewarm_font_engine", None)
    if callable(hook):
        hook()

fm = QFontMetrics(ui_font())
started = time.perf_counter()
engine_advance = fm.horizontalAdvance("Aa")
engine_cold_ms = (time.perf_counter() - started) * 1000.0
started = time.perf_counter()
label_advance = fm.horizontalAdvance(label)
label_first_ms = (time.perf_counter() - started) * 1000.0
started = time.perf_counter()
label_repeat = fm.horizontalAdvance(label)
label_repeat_ms = (time.perf_counter() - started) * 1000.0
print(json.dumps({
    "language": language,
    "label": label,
    "engine_advance": engine_advance,
    "engine_cold_ms": engine_cold_ms,
    "label_advance": label_advance,
    "label_first_ms": label_first_ms,
    "label_repeat": label_repeat,
    "label_repeat_ms": label_repeat_ms,
}))
'''


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    """``_estimate_menu_button_width`` reads the process-wide UiScale factor."""
    yield
    UiScale.get_instance().set_factor(1.0)


def _shipped_trigger_labels() -> list[str]:
    """Real trigger labels of every shipped locale (asserts the catalogs)."""
    from resources.translations import tr

    labels: list[str] = []
    for language in _SHIPPED_LOCALES:
        for key in _TRIGGER_KEYS:
            value = tr(key, language)
            assert value and value != key, (
                f"catalog gap: {key!r} missing for {language!r} — the strip would "
                "measure the raw key instead of a shipped label"
            )
            labels.append(value)
    return labels


def test_menu_width_estimate_is_cheap_after_warmup(qapp):
    """A cold launch's cost is the FIRST advance per script, not the estimate.

    Catches at review time: a change that adds real per-call work to
    ``_estimate_menu_button_width`` (per-call font construction, theme lookup,
    string formatting). Warm, 200 calls over the real labels of all four
    shipped locales cost 2.1 ms here.

    The warm-up calls the estimator once per label on purpose: the first call
    for a script pays the font-engine/glyph-database init (measured: the first
    200-call batch cost 34.8 ms, the identical batch afterwards 2.1 ms). That
    one-time cost is what ``test_first_advance_is_prewarmed`` measures — it
    must not leak into this pin, or the budget would measure engine init on
    every host.
    """
    labels = _shipped_trigger_labels()
    assert len(labels) == len(_SHIPPED_LOCALES) * len(_TRIGGER_KEYS)

    for label in labels:  # prime the engine/glyph cache per script, once
        _estimate_menu_button_width(label, 26)

    started = time.perf_counter()
    widths = [
        _estimate_menu_button_width(labels[index % len(labels)], 26)
        for index in range(_ESTIMATE_CALLS)
    ]
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert all(width > 0 for width in widths), "an estimate returned a non-positive width"
    assert elapsed_ms < _ESTIMATE_BUDGET_MS, (
        f"{_ESTIMATE_CALLS} warm estimates took {elapsed_ms:.1f} ms (budget "
        f"{_ESTIMATE_BUDGET_MS:.0f} ms; measured 2.1 ms on the investigation "
        "host) — the per-call path grew a real cost; the cold-start stall is "
        "one-time engine/glyph work, not this loop"
    )


def _counting_font_metrics(monkeypatch) -> list[int]:
    """Patch ``csd_menu_strip.QFontMetrics`` and return the construction log."""
    import ui.main_window.csd_menu_strip as csd_menu_strip

    real_font_metrics = csd_menu_strip.QFontMetrics
    constructed: list[int] = []

    class _CountingFontMetrics(real_font_metrics):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            constructed.append(1)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(csd_menu_strip, "QFontMetrics", _CountingFontMetrics)
    return constructed


def test_title_bar_builds_one_font_metrics(qapp, monkeypatch):
    """One ``QFontMetrics`` for the whole strip, not one per trigger.

    Budget choice, not the stall: the strip keeps a single instance (shared
    with the dropdown rows it builds) so the cold first advance is paid once
    instead of at every call site. Pinned as
    ``_CONSTRUCTIONS_PER_STRIP == 1`` x one strip = 1 construction — a change
    that raises it is a review event (it re-introduces per-call site
    construction); the live-refresh test below proves the cache is not stale.
    """
    constructed = _counting_font_metrics(monkeypatch)

    from types import SimpleNamespace

    from ui.main_window.menu_controller import MainWindowMenuController

    window = SimpleNamespace(
        windowTitle=lambda: "Improve ImgSLI",
        store=SimpleNamespace(settings=SimpleNamespace(current_language="en")),
        presenter=None,
    )
    controller = MainWindowMenuController(window)
    strip = controller.build_menus()
    try:
        trigger_count = len(strip.buttons())
        assert trigger_count == len(_TRIGGER_KEYS), (
            f"the shipped menu set is File + Help, strip built {trigger_count} triggers"
        )
        assert len(constructed) == _CONSTRUCTIONS_PER_STRIP, (
            f"the strip build constructed {len(constructed)} QFontMetrics for "
            f"{trigger_count} triggers; budget is {_CONSTRUCTIONS_PER_STRIP} "
            "per strip instance (one shared cache, not one per trigger). The "
            "cold-start cost is the first advance, so a per-trigger "
            "construction here is the regression this pins."
        )
    finally:
        controller.shutdown()
        strip.deleteLater()


# -------- cached metrics: width-neutral, refreshed on a metrics change --------


def _build_strip():
    """A File(icon) + Help(label-only) strip — both estimator branches."""
    from sli_ui_toolkit.widgets import ContextMenuAction

    from ui.icon_manager import get_app_icon
    from ui.main_window.csd_menu_strip import CsdMenuSpec, CsdMenuStrip

    specs = [
        CsdMenuSpec(
            label="File",
            entries=[ContextMenuAction("open", "Open")],
            on_triggered=lambda *_: None,
            icon=get_app_icon("folder_open.svg"),
        ),
        CsdMenuSpec(
            label="Help",
            entries=[ContextMenuAction("about", "About")],
            on_triggered=lambda *_: None,
        ),
    ]
    return CsdMenuStrip(specs), specs


def _measure_args(strip, spec) -> dict[str, object]:
    """The per-spec estimator kwargs ``_build_trigger``/``remeasure`` derive.

    Taken from the strip's own public constants + the real spec, so no expected
    number is pasted into a test — the oracle is the *uncached* estimator call
    below, i.e. exactly the pre-cache code path.
    """
    trigger_height = max(20, strip._height - 2 * strip.V_INSET)
    has_icon = spec.icon is not None
    return {
        "height": trigger_height,
        "has_icon": has_icon,
        "icon_size": max(12, min(spec.icon_size, trigger_height - 4)),
        "gap": strip.GAP if has_icon else 0,
        "content_pad": strip.CONTENT_PAD if has_icon else 0,
    }


def _legacy_width(spec, strip) -> int:
    """Width from the pre-cache path (``metrics=None`` builds its own)."""
    return _estimate_menu_button_width(spec.label, **_measure_args(strip, spec))


@pytest.mark.parametrize("factor", (1.0, _CACHE_PROBE_SCALE))
def test_cached_metrics_do_not_change_trigger_widths(qapp, factor):
    """Caching is width-neutral: cached == uncached at the same font/scale.

    ``_estimate_menu_button_width(..., metrics=None)`` is the pre-change code
    path (it constructs ``QFontMetrics(ui_font())`` itself), so comparing the
    strip's pinned button width against it proves the cache changes no number.
    Applies to both branches (icon trigger and label-only trigger) and to a
    non-default scale.
    """
    UiScale.get_instance().set_factor(factor)
    from tests.helpers.drain_until_stable import drain_until_stable

    strip, specs = _build_strip()
    try:
        strip.remeasure()
        # The factor change goes through the coalesced metrics channel; drain
        # it (and any deferred layout turn) before reading pinned widths.
        widths = drain_until_stable(
            qapp, lambda: [button.width() for button in strip.buttons()]
        )
        assert widths  # the drain must have seen the strip
        for spec, button in zip(specs, strip.buttons()):
            legacy = _legacy_width(spec, strip)
            cached = _estimate_menu_button_width(
                spec.label,
                metrics=strip._font_metrics(),
                **_measure_args(strip, spec),
            )
            assert cached == legacy, (
                f"factor {factor}: cached metrics give {cached}px, the uncached "
                f"estimator gives {legacy}px for {spec.label!r} — the cache "
                "changed a width"
            )
            assert button.width() == scaled_px(legacy), (
                f"factor {factor}: strip pinned {button.width()}px for "
                f"{spec.label!r}; the uncached formula + scale gives "
                f"{scaled_px(legacy)}px"
            )
    finally:
        strip.deleteLater()


def test_strip_reuses_its_cache_and_refreshes_on_a_scale_change(qapp, monkeypatch):
    """The strip constructs metrics once; a scale change rebuilds them.

    Two regressions this pins:

    * a remeasure at unchanged metrics must NOT rebuild ``QFontMetrics`` (the
      per-call-site construction this cache replaced);
    * a real scale change must rebuild it, because ``QFontMetrics`` is bound to
      the font it was built from — a stale instance would keep the old advance
      and the strip would paint the previous scale's width.
    """
    from tests.helpers.ui_metrics_parity import _flush_metrics_channel

    constructed = _counting_font_metrics(monkeypatch)
    strip, specs = _build_strip()
    try:
        assert len(constructed) == _CONSTRUCTIONS_PER_STRIP
        widths_before = [button.width() for button in strip.buttons()]
        for _ in range(3):
            strip.remeasure()
        assert len(constructed) == _CONSTRUCTIONS_PER_STRIP, (
            f"{len(constructed)} QFontMetrics after four remeasures at the same "
            "metrics — remeasure must reuse the strip's cache"
        )
        assert [button.width() for button in strip.buttons()] == widths_before

        UiScale.get_instance().set_factor(_CACHE_PROBE_SCALE)
        _flush_metrics_channel(qapp)  # the coalesced connect_ui_metrics channel
        assert len(constructed) == _CONSTRUCTIONS_PER_STRIP + 1, (
            "a scale change must rebuild the cached metrics exactly once"
        )
        widths_after = [button.width() for button in strip.buttons()]
        assert widths_after != widths_before, (
            "the strip kept the old widths after a scale change — stale cache"
        )
        for spec, button in zip(specs, strip.buttons()):
            assert button.width() == scaled_px(_legacy_width(spec, strip)), (
                f"{spec.label!r} was not re-measured under the new scale"
            )
    finally:
        strip.deleteLater()


def test_strip_cache_refreshes_on_a_font_change(qapp):
    """A live UI-face change must re-measure the triggers (no stale metrics).

    The current face is swapped through the production lever (``UiFont``
    family override), i.e. the same path the settings dialog drives. If the
    machine has no alternate family with different advances the lever skips —
    an honest skip, not a silent pass.
    """
    from tests.helpers.ui_metrics_parity import _flush_metrics_channel, _font_lever

    strip, specs = _build_strip()
    apply_font, restore_font = _font_lever()
    try:
        widths_before = [button.width() for button in strip.buttons()]
        apply_font()
        _flush_metrics_channel(qapp)
        widths_after = [button.width() for button in strip.buttons()]
        assert widths_after != widths_before, (
            "the strip kept the previous face's trigger widths — the cached "
            "metrics were not invalidated on the font change"
        )
        for spec, button in zip(specs, strip.buttons()):
            assert button.width() == scaled_px(_legacy_width(spec, strip)), (
                f"{spec.label!r} was not re-measured under the new face"
            )
    finally:
        restore_font()
        _flush_metrics_channel(qapp)
        strip.deleteLater()


# -------- IMGSLI_FONT_PREWARM: gated instrument, inert by default --------

_APP_MAIN_MODULE_NAME = "_imgsli_app_main_for_tests"


@pytest.fixture(scope="module")
def app_main():
    """The real early-boot module (``src/__main__.py``), imported by path.

    A private module name keeps it from shadowing pytest's ``__main__``;
    module scope keeps the one-time heavy import out of the per-test cost.
    """
    import importlib.util

    path = REPO_ROOT / "src" / "__main__.py"
    spec = importlib.util.spec_from_file_location(_APP_MAIN_MODULE_NAME, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_APP_MAIN_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", ("0", "false", "no", "off", "", "   "))
def test_font_prewarm_is_off_for_falsy_values(app_main, monkeypatch, value):
    """Permissive flag vocabulary: only a truthy value turns the pre-warm on."""
    monkeypatch.delenv("BLINKTABLE_FONT_PREWARM", raising=False)
    monkeypatch.setenv("IMGSLI_FONT_PREWARM", value)
    assert app_main._font_prewarm_requested() is False


@pytest.mark.parametrize("value", ("1", "yes", "on", "true"))
def test_font_prewarm_is_on_for_truthy_values(app_main, monkeypatch, value):
    monkeypatch.delenv("BLINKTABLE_FONT_PREWARM", raising=False)
    monkeypatch.setenv("IMGSLI_FONT_PREWARM", value)
    assert app_main._font_prewarm_requested() is True


def test_unset_font_prewarm_does_no_work_and_emits_no_mark(app_main, monkeypatch):
    """With the env unset: no warm-up call, no Qt work, no trace line.

    This is the "zero behaviour change" half of the diagnostic build — the
    default run must be byte-identical to before the instrument existed.
    """
    monkeypatch.delenv("BLINKTABLE_FONT_PREWARM", raising=False)
    monkeypatch.delenv("IMGSLI_FONT_PREWARM", raising=False)
    calls: list[int] = []
    marks: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        app_main,
        "_prewarm_font_metrics",
        lambda: calls.append(1) or (0.0, "unused"),
    )
    monkeypatch.setattr(
        app_main,
        "early_mark",
        lambda name, **fields: marks.append((name, fields)),
    )

    app_main._maybe_prewarm_font_metrics()

    assert calls == [], "the pre-warm ran with IMGSLI_FONT_PREWARM unset"
    assert marks == [], "the pre-warm emitted a startup mark with the env unset"


def test_truthy_font_prewarm_runs_once_and_records_its_cost(app_main, monkeypatch):
    """With the env on: one warm-up, one mark carrying its measured cost."""
    monkeypatch.delenv("BLINKTABLE_FONT_PREWARM", raising=False)
    monkeypatch.setenv("IMGSLI_FONT_PREWARM", "1")
    calls: list[int] = []
    marks: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        app_main,
        "_prewarm_font_metrics",
        lambda: calls.append(1) or (12.5, "DejaVu Sans"),
    )
    monkeypatch.setattr(
        app_main,
        "early_mark",
        lambda name, **fields: marks.append((name, fields)),
    )

    app_main._maybe_prewarm_font_metrics()

    assert calls == [1], "the pre-warm did not run exactly once"
    assert marks == [
        ("font.prewarm", {"cost_ms": "12.5", "family": "DejaVu Sans"})
    ], (
        "the A/B reads the cost from this one early mark; a missing/renamed "
        f"field makes the instrument unreadable (got {marks!r})"
    )


def test_prewarm_measures_a_real_first_advance(app_main, qapp):
    """The real warm-up returns ``(cost_ms, family)`` on a live QApplication."""
    result = app_main._prewarm_font_metrics()
    assert result is not None, "the warm-up could not measure an advance"
    cost_ms, family = result
    assert cost_ms >= 0.0
    assert family, "the mark would not let an A/B compare the warmed face"


def _cold_first_advance(language: str) -> dict[str, object]:
    """Run the probe in a fresh interpreter and return its measurement dict."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_PROBE, language],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, (
        f"fresh-interpreter probe for {language!r} failed: "
        f"{completed.stderr.strip()[-2000:]}"
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert "error" not in payload, payload["error"]
    return payload


def test_first_advance_is_prewarmed():
    """The first advance must already be warm when the title bar builds.

    Catches at review time / when someone adds the fix: today a fresh
    interpreter pays the one-time font-engine init on the first advance, so a
    cold launch pays it inside ``_estimate_menu_button_width``. A startup
    pre-warm — ``QFontMetrics(ui_font())`` advanced once with ``"Aa"`` and once
    per shipped script, before the title bar builds — makes this pass without
    touching the test (the probe imports the cold-path modules and calls a
    ``prewarm_font_engine()`` hook if a startup module exposes one).

    Known-red marker (acceptance allows exactly one): the suite reports
    ``xfailed`` with the measured per-locale numbers in the reason. The
    numbers also discriminate the three mechanisms: en/pt_BR advance with no
    glyph-fallback work yet pay the same engine cost, so the stall is
    mechanism (1) init — not the per-script fallback (2) or the construction
    count (3). Keep this test environment-generic: it asserts a 5 ms budget,
    not the owner's Windows milliseconds.
    """
    samples = {language: _cold_first_advance(language) for language in _SHIPPED_LOCALES}

    for language, sample in samples.items():
        assert sample["label_advance"], f"{language}: no glyphs measured ({sample})"
        assert sample["label_advance"] == sample["label_repeat"], (
            f"{language}: advance changed between calls ({sample}) — a font was "
            "swapped under the measurement"
        )
        assert sample["engine_advance"], f"{language}: empty 'Aa' advance"

    engine_cold_ms = {language: float(s["engine_cold_ms"]) for language, s in samples.items()}
    label_first_ms = {language: float(s["label_first_ms"]) for language, s in samples.items()}
    label_repeat_ms = {language: float(s["label_repeat_ms"]) for language, s in samples.items()}

    worst_engine = max(engine_cold_ms.values())
    if worst_engine <= _COLD_ADVANCE_BUDGET_MS:
        return  # pre-warmed by startup: nothing blocks the cold title bar

    detail = ", ".join(
        f"{language}: engine {engine_cold_ms[language]:.1f} ms / first label "
        f"{label_first_ms[language]:.1f} ms / repeat {label_repeat_ms[language]:.2f} ms"
        for language in _SHIPPED_LOCALES
    )
    pytest.xfail(
        "no font pre-warm before the title bar builds: the first advance in a "
        f"fresh interpreter costs up to {worst_engine:.1f} ms (budget "
        f"{_COLD_ADVANCE_BUDGET_MS:.0f} ms). Per locale — {detail}. "
        "The primary-script 'Aa' advance pays it too, so this is one-time "
        "font-engine init (mechanism 1), not per-script glyph fallback. "
        "Fix: pre-warm QFontMetrics(ui_font()) with 'Aa' plus one label per "
        "shipped script before build_menus() (or expose prewarm_font_engine() "
        "on ui.main_window.startup — this test calls it), then drop this "
        "xfail branch."
    )
