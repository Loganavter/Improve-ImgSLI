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

from sli_ui_toolkit.managers import UiScale, ui_font
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
# Target: ONE shared QFontMetrics per strip build. Today it is one per trigger
# (see ``test_title_bar_builds_one_font_metrics``).
_CONSTRUCTIONS_PER_TRIGGER = 1
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


def test_title_bar_builds_one_font_metrics(qapp, monkeypatch):
    """One ``QFontMetrics`` per trigger today; the target budget is ONE.

    Catches at review time: a strip build that constructs font metrics per
    row/per label (mechanism 3 in the investigation) or leaks an extra
    construction into the cold path. Cost measured: ~10 us per construction +
    advance warm, so the count is pinned as a *budget choice*, not because it
    is the stall — a change that raises it is a review event; a change that
    lowers it to one shared instance should update the constant and this
    docstring in the same commit.

    Pinned budget: ``_CONSTRUCTIONS_PER_TRIGGER == 1`` x 2 shipped triggers
    = 2 constructions. Keep this equal to what ``build_menus`` really does —
    do not "fix" the test to a new number without updating the constant and
    the target note above.
    """
    import ui.main_window.csd_menu_strip as csd_menu_strip

    real_font_metrics = csd_menu_strip.QFontMetrics
    constructed: list[int] = []

    class _CountingFontMetrics(real_font_metrics):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            constructed.append(1)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(csd_menu_strip, "QFontMetrics", _CountingFontMetrics)

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
        assert len(constructed) == trigger_count * _CONSTRUCTIONS_PER_TRIGGER, (
            f"the strip build constructed {len(constructed)} QFontMetrics for "
            f"{trigger_count} triggers; budget is "
            f"{_CONSTRUCTIONS_PER_TRIGGER} per trigger (target: one shared "
            "instance for the whole build). This is not the cold-start stall — "
            "it is the budget the strip is allowed to spend"
        )
    finally:
        controller.shutdown()
        strip.deleteLater()


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
