"""Wave 2 of the ONE-scope unification: the switch's cap and the reset's store scope.

Wave 1 (``9b005c08c``) created ``use_cases/action_scope.py`` and moved the
domain switch's card pick onto ``resolve_scope`` — with two selected cards of a
twenty-card viewport the AI tail already analyzes exactly those two (asserted
here as a guard: that count was fixed by wave 1, so it cannot be a red-before
for this wave). What wave 1 left SILENT is the part the owner reported:

* **the cap** — flipping to AI with an empty selection analyzes 12 of the 20
  visible cards, and ``Scope.reason`` (``cap=12 available=20``) only reached
  ``logger.debug``: log.txt at the default INFO level said nothing, which is
  the "выбрал 100 — те же 12, молча" half of the report.
* **the reset's store scope** — a two-card "Reset metrics cache" clears the two
  cards' item state, but the MEASURED stores (scorecards / metric profiles /
  metrics / ranks / pins) are keyed by series/pair/content identity, so an
  adapter sweep drops them for the WHOLE pool. Nothing in the summary or the
  log said so; "выбрал 2 — обработалось 100" was readable only from the code.

Falsification: the log/summary assertions below fail on ``9b005c08c`` (no INFO
line is emitted for either action and the summary carries no store-scope
field), so the tests are not restatements of the implementation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.models import AnalysisStatus
from tabs.image_gallery.use_cases import action_scope, ai_analysis, cache_reset


# -- the domain switch --------------------------------------------------------


def _switch_paths(count: int) -> list[Path]:
    return [Path(f"/img/{i:03d}.png") for i in range(count)]


class _Grid:
    """Grid double: ``visible_paths_strict`` is what the resolver reads."""

    def __init__(self, paths) -> None:
        self._paths = list(paths)

    def visible_paths_strict(self):
        return list(self._paths)

    def visible_paths(self):
        return list(self._paths)


class _Widget:
    def __init__(self, grid) -> None:
        self._grid_view = grid

    def refresh_cards(self, items) -> None:
        pass

    def refresh_card(self, item) -> None:
        pass


def _switch_owner(*, selected=(), visible=20, cap=12):
    """A controller-shaped owner: real ``_run_ai_for_visible``, capturing ``analyze``."""
    paths = _switch_paths(visible)
    items = [
        SimpleNamespace(path=p, analysis_status=AnalysisStatus.NOT_ANALYZED)
        for p in paths
    ]
    analyzed: list[Path] = []
    owner = SimpleNamespace(
        state=SimpleNamespace(
            selected_paths={Path(p) for p in selected},
            selected_order=[Path(p) for p in selected],
            items=items,
            filter_text="",
        ),
        widget=_Widget(_Grid(paths)),
        _judgment_domain="algorithms",
        _AI_VISIBLE_CAP=cap,
        _folder_gen=1,
        _run_series_priority=lambda: None,
    )
    owner.analyze = lambda ctx: analyzed.extend(ctx.targets)
    owner._run_ai_for_visible = lambda **kw: ai_analysis._run_ai_for_visible(
        owner, **kw
    )
    return owner, analyzed


def test_switch_analyzes_the_selection_not_the_viewport() -> None:
    """Rule 7: two selected cards of twenty visible → exactly two analyzed.

    Guard, not a red-before: wave 1 already routes ``_run_ai_for_visible``
    through the ONE resolver (kind selection_else_visible), so this pins the
    behaviour against a future regression rather than proving the fix.
    """
    selected = _switch_paths(2)
    owner, analyzed = _switch_owner(selected=selected, visible=20)

    ai_analysis.activate_judgment_domain(owner, "ai")

    assert [str(p) for p in analyzed] == [str(p) for p in selected]


def test_switch_names_the_cap_and_what_it_dropped(caplog) -> None:
    """RED BEFORE: the capped visible branch was silent at the INFO log level.

    An empty selection with twenty visible cards analyzes the owner's cap (12);
    the owner must be able to read "12 of 20, 8 dropped because of the cap"
    from log.txt without ``--debug``.
    """
    owner, analyzed = _switch_owner(visible=20, cap=12)

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        ai_analysis.activate_judgment_domain(owner, "ai")

    assert len(analyzed) == 12, "the capped viewport pass no longer runs"
    lines = [
        r.getMessage()
        for r in caplog.records
        if "AI pass" in r.getMessage() and r.levelno == logging.INFO
    ]
    assert lines, (
        "the switch logged nothing at INFO — a capped pass is exactly the "
        "silent truncation the owner reported"
    )
    line = "\n".join(lines)
    assert "cap=12" in line and "available=20" in line, line
    assert "dropped=8" in line, line


def test_switch_logs_why_nothing_ran(caplog) -> None:
    """A refusal is a fact, not a silent no-op: the log names it at INFO."""
    owner, analyzed = _switch_owner(visible=20)
    owner.widget = _Widget(None)  # no viewport at all
    owner.state.items = []

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        ai_analysis.activate_judgment_domain(owner, "ai")

    assert analyzed == []
    messages = [r.getMessage() for r in caplog.records if "AI pass" in r.getMessage()]
    assert messages and "refused=" in "\n".join(messages), messages


def test_settle_uses_the_same_scope() -> None:
    """The settle tail is the same trigger: the selection wins there too."""
    from tabs.image_gallery.use_cases import triage_run

    selected = _switch_paths(2)
    owner, analyzed = _switch_owner(selected=selected, visible=20)
    owner._judgment_domain = "ai"

    triage_run._run_ai_on_settle(owner)

    assert [str(p) for p in analyzed] == [str(p) for p in selected]


# -- the metrics reset --------------------------------------------------------


def _reset_pool(count: int):
    items = []
    for i in range(count):
        items.append(
            SimpleNamespace(
                path=Path(f"/pool/{i:03d}.png"),
                metrics={"sharpness": 100.0 + i},
                artifacts={},
                artifact_maps={},
                analysis=None,
                analysis_status=AnalysisStatus.DONE,
                analysis_error=None,
                analysis_records=(),
                rank=i + 1,
                crown_rank=i + 1,
                is_best=bool(i == 0),
                triage_best=False,
                triage_rank=None,
                badge="",
                badge_kind=None,
                badge_source="",
                vlm_tie_result=None,
                vlm_tie_pending=False,
                vlm_tie_error=None,
                vlm_brief=None,
                vlm_brief_status="none",
                vlm_brief_error=None,
            )
        )
    return items


def _reset_owner(count: int):
    items = _reset_pool(count)
    owner = SimpleNamespace(
        state=SimpleNamespace(
            items=items,
            folder=Path("/pool"),
            algorithms_profile=None,
            ai_profile=None,
        ),
        _last_analysis_fingerprint=("stale",),
    )
    return owner, items


def test_reset_summary_names_the_store_scope(monkeypatch) -> None:
    """RED BEFORE: the summary never said the measured stores were swept whole.

    Two selected cards of a hundred: the CARD state of two goes, the measured
    stores go for the pool (an adapter owns a namespace, not a card). The
    result must say both, or "выбрал 2 — обработалось 100" stays unexplained.
    """
    monkeypatch.setattr(cache_reset, "_gallery_backends", lambda: ())
    owner, items = _reset_owner(100)
    targets = [items[0].path, items[1].path]

    summary = cache_reset.reset_metrics_caches(owner, paths=targets)

    assert summary["items"] == 2, "the card scope regressed to the pool"
    assert summary["targets"] == 2
    assert summary["pool"] == 100
    assert summary["target_scope"] == "targets"
    assert summary["stores_scope"] == "global", (
        "the summary hides that the measured stores are swept for the whole pool"
    )
    assert set(summary["stores"]) == {
        "scorecards",
        "metric_profiles",
        "metrics",
        "ranks",
        "pins",
    }, summary["stores"]


def test_reset_pool_scope_is_named_too(monkeypatch) -> None:
    """A maintenance reset (``paths=None``) is pool-scoped, and says so."""
    monkeypatch.setattr(cache_reset, "_gallery_backends", lambda: ())
    owner, items = _reset_owner(3)

    summary = cache_reset.reset_metrics_caches(owner)

    assert summary["target_scope"] == "pool"
    assert summary["targets"] == 3
    assert summary["pool"] == 3


def test_reset_logs_the_store_sweep_in_one_line(monkeypatch, caplog) -> None:
    """RED BEFORE: nothing reached log.txt at INFO about the global store sweep."""
    monkeypatch.setattr(cache_reset, "_gallery_backends", lambda: ())
    owner, items = _reset_owner(100)
    targets = [items[0].path, items[1].path]

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        cache_reset.reset_metrics_caches(owner, paths=targets)

    lines = [
        r.getMessage()
        for r in caplog.records
        if "metrics reset" in r.getMessage() and r.levelno == logging.INFO
    ]
    assert lines, "the reset logged nothing at INFO about its scope"
    assert len(lines) == 1, f"the store-scope report is ONE line, got {lines}"
    line = lines[0]
    assert "2 of 100" in line, line
    for word in ("scorecards", "metrics", "ranks", "pins"):
        assert word in line, f"the store scope does not name {word!r}: {line}"


def test_reset_items_and_stores_differ_in_the_same_result(monkeypatch) -> None:
    """The two scopes stay distinct: 2 cards cleared, the pool's stores swept."""
    monkeypatch.setattr(cache_reset, "_gallery_backends", lambda: ())
    owner, items = _reset_owner(100)
    targets = [items[0].path, items[1].path]

    summary = cache_reset.reset_metrics_caches(owner, paths=targets)

    assert summary["items"] == 2
    assert [it.metrics for it in items] == [
        {} if i < 2 else {"sharpness": 100.0 + i} for i in range(100)
    ]
    assert summary["stores_scope"] == "global"
    assert action_scope.ACTION_SCOPE_POLICY["gallery.card.reset_metrics"] == (
        action_scope.SCOPE_SELECTION_OR_CARD
    )
