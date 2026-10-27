"""Gallery action scope: one target-resolution mechanism for every action.

Regression for the owner report (2026-10-20): context-menu **Analyze** acted
on ONE image of a selected group. Pre-fix that handler did
``next(iter(state.selected_paths))`` — set iteration order, not a scope
decision — so with three selected cards exactly **one arbitrary** path
reached ``analyze_item_by_path``. That red behaviour is asserted here as
"all three" (the pre-fix body fails `test_analyze_applies_to_every_selected_target`
with a call list of length 1; no re-run of the old commit is needed).

Covers the resolver precedence (``use_cases.action_scope``) and the migrated
call sites: popup Analyze, reset-metrics, and the selection read that carry /
keyboard already consume. No app boot: a ``SimpleNamespace`` owner plus the
real popup handler, with the menu-open seam monkeypatched (same seam
``test_card_selection_menu`` uses).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, Qt

from tabs.image_gallery.use_cases import action_scope
from core.log_names import APP_LOGGER_NAME


def _owner(selected, order=None, items=None, **extra):
    st = SimpleNamespace(
        selected_paths={Path(p) for p in selected},
        selected_order=[Path(p) for p in (order or [])],
        items=list(items or []),
    )
    # The action context carries the backend; these doubles are the
    # algorithms domain unless a test says otherwise.
    extra.setdefault("_judgment_domain", "algorithms")
    ns = SimpleNamespace(state=st, **extra)
    return ns


def _record_analyze(sink):
    """A controller-shaped ``analyze(ctx)`` double (one call, loops contexts)."""
    return lambda ctx: sink.extend(ctx.targets)


def _capture_menu(monkeypatch):
    """Capture menu entries + on_triggered without showing UI."""
    import sli_ui_toolkit.widgets as _w
    import ui.context_menu.manager as _mgr

    captured: dict = {}

    class _FakeMenu:
        def __init__(self, parent, *, entries=(), on_triggered=None, **kwargs):
            captured["entries"] = tuple(entries)
            captured["on_triggered"] = on_triggered

        def popup_at(self, pos):
            captured["popup_at"] = pos

        def show(self):
            captured["shown"] = True

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None, **_kwargs):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        return _FakeMenu(source_widget, entries=entries, on_triggered=on_triggered)

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)
    monkeypatch.setattr(_w, "ContextMenu", _FakeMenu)
    return captured


def _open_menu(monkeypatch, owner, path, **kwargs):
    """Open the real card context menu without showing UI; return the capture."""
    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    captured = _capture_menu(monkeypatch)
    kwargs.setdefault("selection_count", len(owner.state.selected_paths))
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, path, global_pos=QPoint(0, 0), **kwargs
    )
    return captured


def _trigger_analyze(monkeypatch, owner, path):
    """Open the real card context menu and run its Analyze action."""
    captured = _open_menu(monkeypatch, owner, path)
    captured["on_triggered"]("gallery.selection.analyze", None)
    return captured


def test_analyze_applies_to_every_selected_target(monkeypatch) -> None:
    """RED BEFORE: `next(iter(selected_paths))` analyzed exactly one of three."""
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    analyzed: list[Path] = []
    owner = _owner({a, b, c}, order=[a, b, c])
    owner.analyze = _record_analyze(analyzed)
    _trigger_analyze(monkeypatch, owner, a)
    assert analyzed == [a, b, c]


def test_analyze_respects_selected_order(monkeypatch) -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    analyzed: list[Path] = []
    owner = _owner({a, b, c}, order=[c, a, b])
    owner.analyze = _record_analyze(analyzed)
    _trigger_analyze(monkeypatch, owner, a)
    assert analyzed == [c, a, b]


def test_analyze_on_unselected_card_acts_on_that_card_only(monkeypatch) -> None:
    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    analyzed: list[Path] = []
    owner = _owner({a, b, c}, order=[a, b, c])
    owner.analyze = _record_analyze(analyzed)
    _trigger_analyze(monkeypatch, owner, d)
    assert analyzed == [d]


def test_analyze_callback_precedence_is_kept(monkeypatch) -> None:
    """A provided callback still wins over the default — and gets the scope."""
    fired: list[list[Path]] = []
    analyzed: list[Path] = []
    owner = _owner({Path("/a.png"), Path("/b.png")})
    owner.analyze = _record_analyze(analyzed)
    captured = _open_menu(
        monkeypatch,
        owner,
        Path("/a.png"),
        selection_count=2,
        on_analyze=lambda targets: fired.append(list(targets)),
    )
    captured["on_triggered"]("gallery.selection.analyze", None)
    assert fired == [[Path("/a.png"), Path("/b.png")]]
    assert analyzed == []


def test_find_similar_uses_the_whole_selection(monkeypatch, caplog) -> None:
    """Find similar is a selection action too — it sees all three, not one."""
    import logging

    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[a, b, c])
    captured = _capture_menu(monkeypatch)
    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, a, global_pos=QPoint(0, 0), selection_count=3,
    )
    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        captured["on_triggered"]("gallery.selection.find_similar", None)
    assert any("3 target(s)" in r.getMessage() for r in caplog.records)


def test_analyze_isolates_per_item_failures(monkeypatch) -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    seen: list[Path] = []

    def _fn(path):
        if path == b:
            raise RuntimeError("boom")
        seen.append(path)

    owner = _owner({a, b, c}, order=[a, b, c])
    assert action_scope.apply_to_targets(owner, _fn, card_path=a) == 2
    assert seen == [a, c]


def test_resolve_clicked_outside_selection_is_card_only() -> None:
    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    owner = _owner({a, b, c}, order=[b, a, c])
    assert action_scope.resolve_targets(owner, card_path=d) == [d]


def test_resolve_empty_selection_with_card_path() -> None:
    card = Path("/a.png")
    owner = _owner(set())
    assert action_scope.resolve_targets(owner, card_path=card) == [card]


def test_resolve_empty_selection_never_falls_back_to_the_first_item(monkeypatch) -> None:
    """RED BEFORE: an empty scope resolved to the first visible card."""
    monkeypatch.setattr(action_scope, "_focused_path", lambda owner: None)
    first = SimpleNamespace(path=Path("/first.png"))
    second = SimpleNamespace(path=Path("/second.png"))
    owner = _owner(set(), items=[first, second])
    assert action_scope.resolve_targets(owner) == []
    # Focus is an EXPLICIT keyboard input, never inferred by the resolver.
    assert action_scope.resolve_targets(owner, focused=True) == []


def test_resolve_empty_selection_prefers_focused_card() -> None:
    focused = Path("/focused.png")
    first = SimpleNamespace(path=Path("/first.png"))
    owner = _owner(set(), items=[first], focused_path=focused)
    assert action_scope.resolve_targets(owner, focused=True) == [focused]
    assert action_scope.resolve_targets(owner) == []


def test_resolve_empty_scope_is_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(action_scope, "_focused_path", lambda owner: None)
    owner = SimpleNamespace(state=SimpleNamespace(selected_paths=set()))
    assert action_scope.resolve_targets(owner) == []
    assert action_scope.resolve_targets(owner, focused=True) == []
    assert action_scope.resolve_targets(owner, card_path=Path("/a.png")) == [Path("/a.png")]


def test_selected_order_is_stable_and_deduped() -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[c, a, b, a, "c"])
    assert action_scope.selected_paths(owner) == [c, a, b]
    assert action_scope.selected_paths(owner) == [c, a, b]
    assert action_scope.resolve_targets(owner, card_path=b) == [c, a, b]


def test_selected_paths_normalizes_strings_and_hides_mirror_types() -> None:
    owner = _owner({"/a.png", "/b.png"}, order=["/b.png", "/a.png"])
    assert action_scope.selected_paths(owner) == [Path("/b.png"), Path("/a.png")]


def test_reset_metrics_adapter_passes_the_resolved_targets(monkeypatch) -> None:
    """The legacy ``_ctx_reset_metrics`` adapter forwards the ONE resolver's scope.

    Owner report 2026-10-27 supersedes the 2026-10-22 pool-wide reading: a mass
    action is the SELECTION, so the adapter may not widen it (it used to pass
    ``paths=None``, i.e. every card of the tab).
    """
    from tabs.image_gallery.ui.card import context_actions
    from tabs.image_gallery.use_cases import cache_reset

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    calls: list[dict] = []
    monkeypatch.setattr(
        cache_reset,
        "reset_metrics_caches",
        lambda owner, paths=None, **kw: calls.append({"owner": owner, "paths": paths}),
    )
    owner = _owner({a, b, c}, order=[b, a, c])
    context_actions._ctx_reset_metrics(owner, b)
    assert len(calls) == 1
    assert calls[0]["owner"] is owner
    assert calls[0]["paths"] == [b, a, c]


def test_reset_metrics_empty_scope_clears_nothing(monkeypatch) -> None:
    """An empty answer is final: no card, no selection, no reset."""
    from tabs.image_gallery.ui.card import context_actions
    from tabs.image_gallery.use_cases import cache_reset

    calls: list = []
    monkeypatch.setattr(
        cache_reset,
        "reset_metrics_caches",
        lambda owner, paths=None, **kw: calls.append(paths),
    )
    # Deterministic empty scope: no selection, no card, no focus (the focus
    # probe reads the process-wide QApplication otherwise).
    monkeypatch.setattr(action_scope, "_focused_path", lambda owner: None)
    context_actions._ctx_reset_metrics(SimpleNamespace(), None)
    assert calls == []


# --- the reset is a MASS action, not a tab-wide one -------------------------
#
# Owner report 2026-10-27: "Почему я выделил 3 изображения, а он экшн повесил на
# все, которые есть в вкладке?" — three cards selected, every card of the tab
# lost its numbers. Both entries resolved the scope correctly and then threw it
# away (``reset_metrics_caches`` forced ``paths=None``), which is the same
# defect class as ``next(iter(selected_paths))``: the action ignored the ONE
# resolver's answer. The tests below pin the observable consequence on the
# CARDS (numbers/rank/badges), not on an internal call signature, so a future
# rewiring cannot pass them while clearing the pool.
#
# A genuinely pool-wide reset still exists as the USE CASE call
# ``cache_reset.clear_metrics_caches(owner)`` (``paths=None``), used by
# maintenance/tests; no per-card control reaches it any more.


def _reset_pool(paths):
    """Pool items carrying the state a reset must (and must not) clear."""
    kept = SimpleNamespace(description="kept-read", tags=("sky",))
    items = []
    for i, p in enumerate(paths):
        items.append(
            SimpleNamespace(
                path=p,
                metrics={"sharpness": 100.0 + i},
                rank=i + 1,
                crown_rank=i + 1,
                is_best=(i == 0),
                analysis=kept,
                analysis_status="done",
                analysis_records=("record",),
                artifact_maps={"banding": [[1]]},
                vlm_brief="kept brief",
            )
        )
    return items


def _reset_owner(selected, pool):
    items = _reset_pool(pool)
    return _owner(set(selected), order=list(selected), items=items), items


def _no_backends(monkeypatch) -> None:
    """Keep the test about SCOPE: no composed backend sweeps the disk caches."""
    from tabs.image_gallery.use_cases import cache_reset

    monkeypatch.setattr(cache_reset, "_gallery_backends", lambda: ())


def test_card_menu_reset_clears_only_the_three_selected_cards(monkeypatch) -> None:
    """RED BEFORE: the menu resolved 3 targets, the reset zeroed all 4 cards."""
    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    owner, items = _reset_owner({a, b, c}, [a, b, c, d])
    _no_backends(monkeypatch)
    captured = _open_menu(monkeypatch, owner, a, selection_count=3)
    captured["on_triggered"]("gallery.reset_metrics", None)

    assert [it.metrics for it in items] == [{}, {}, {}, {"sharpness": 103.0}]
    # The untouched card keeps EVERYTHING a reset would drop.
    assert items[3].rank == 4
    assert items[3].crown_rank == 4
    assert items[3].analysis_records == ("record",)
    assert items[3].artifact_maps == {"banding": [[1]]}
    assert items[3].vlm_brief == "kept brief"
    assert items[3].analysis is not None


def test_registry_reset_action_clears_only_the_selected_cards(monkeypatch) -> None:
    """The Find Action / MCP entry takes the same scope (one builder, one fix)."""
    from tabs.image_gallery.use_cases.registration import run_action

    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    owner, items = _reset_owner({a, b, c}, [a, b, c, d])
    _no_backends(monkeypatch)
    run_action(SimpleNamespace(_controller=owner, _widget=None), "gallery.reset-metrics")

    assert [it.metrics for it in items] == [{}, {}, {}, {"sharpness": 103.0}]
    assert items[3].rank == 4


def test_reset_on_an_unselected_card_is_the_point_form(monkeypatch) -> None:
    """Right-clicking outside the selection acts on that card alone."""
    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    owner, items = _reset_owner({a, b, c}, [a, b, c, d])
    _no_backends(monkeypatch)
    captured = _open_menu(monkeypatch, owner, d)
    captured["on_triggered"]("gallery.reset_metrics", None)

    assert [it.metrics for it in items] == [
        {"sharpness": 100.0},
        {"sharpness": 101.0},
        {"sharpness": 102.0},
        {},
    ]


def test_pool_wide_reset_survives_only_as_the_explicit_use_case(monkeypatch) -> None:
    """The maintenance path is not lost — it simply has no per-card entry."""
    from tabs.image_gallery.use_cases import cache_reset

    a, b, c = (Path(p) for p in ("/a.png", "/b.png", "/c.png"))
    owner, items = _reset_owner(set(), [a, b, c])
    _no_backends(monkeypatch)
    cache_reset.clear_metrics_caches(owner)  # paths=None — the whole pool, by request

    assert [it.metrics for it in items] == [{}, {}, {}]
    assert not any(getattr(it, "rank", None) for it in items)


def test_ask_ai_selection_scope_reads_the_three_selected_cards(monkeypatch) -> None:
    """The last direct ``state.selected_paths`` reader in an action entry.

    Ask AI keeps a scope KIND (the flyout owns its scope line), but WHICH cards
    that kind means must come from the ONE selection source like every other
    entry. The resolver is stubbed so the test fails if the entry reads the
    state mirror itself again (the pre-fix body never consulted ``action_scope``
    at all, so the recorded call is the discriminator).
    """
    from tabs.image_gallery.controller import GalleryController

    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    seen: list = []
    consulted: list = []

    def _selected(owner):
        consulted.append(owner)
        return [a, b, c]

    monkeypatch.setattr(action_scope, "selected_paths", _selected)
    owner = SimpleNamespace(
        state=SimpleNamespace(selected_paths={a, b, c, d}, selected_order=[a, b, c, d]),
        _open_ask_ai=lambda anchor, scope, **kw: seen.append(scope),
    )
    GalleryController.open_ask_ai(owner, "selection", None, a)

    assert consulted == [owner]
    assert [seen[0].kind, tuple(seen[0].paths)] == ["selection", (a, b, c)]
    assert d not in seen[0].paths


def test_keyboard_current_path_is_the_first_resolved_target(monkeypatch) -> None:
    from tabs.image_gallery.use_cases import triage_ui

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[c, a, b])
    assert triage_ui.current_path(owner) == c


def test_carry_selection_uses_the_same_read() -> None:
    from tabs.image_gallery.use_cases import carry

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    owner = _owner({a, b, c}, order=[b, c, a])
    assert carry._selected_paths(owner) == [b, c, a]


# --- the menu owns the scope: callbacks receive the resolved targets --------
#
# The contract this pins (owner report 2026-10-20, second round): a card-menu
# callback describes HOW to act, never WHICH cards. Before this contract the
# menu called ``on_analyze()`` with no arguments, so a zero-arg production
# closure re-derived its own scope (``next(iter(selected_paths))``) and a
# six-card selection analyzed one arbitrary card. Every test below asserts
# the callback's ARGUMENT; a zero-arg call cannot satisfy them by accident.


def test_analyze_callback_receives_all_selected_targets(monkeypatch) -> None:
    """RED BEFORE: the callback was called with no arguments (scope lost)."""
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    seen: list[list[Path]] = []
    owner = _owner({a, b, c}, order=[a, b, c])
    captured = _open_menu(monkeypatch, owner, a, on_analyze=lambda t: seen.append(list(t)))
    captured["on_triggered"]("gallery.selection.analyze", None)
    assert seen == [[a, b, c]]


def test_analyze_callback_outside_selection_is_the_clicked_card(monkeypatch) -> None:
    a, b, c, d = (Path(p) for p in ("/a.png", "/b.png", "/c.png", "/d.png"))
    seen: list[list[Path]] = []
    owner = _owner({a, b, c}, order=[b, a, c])
    captured = _open_menu(monkeypatch, owner, d, on_analyze=lambda t: seen.append(list(t)))
    captured["on_triggered"]("gallery.selection.analyze", None)
    assert seen == [[d]]


def test_analyze_callback_with_empty_selection_gets_the_clicked_card(monkeypatch) -> None:
    card = Path("/a.png")
    seen: list[list[Path]] = []
    owner = _owner(set())
    captured = _open_menu(
        monkeypatch, owner, card, selection_count=0, on_analyze=lambda t: seen.append(list(t))
    )
    captured["on_triggered"]("gallery.selection.analyze", None)
    assert seen == [[card]]


def test_find_similar_callback_receives_all_selected_targets(monkeypatch) -> None:
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    seen: list[list[Path]] = []
    owner = _owner({a, b, c}, order=[c, a, b])
    captured = _open_menu(
        monkeypatch, owner, a, on_find_similar=lambda t: seen.append(list(t))
    )
    captured["on_triggered"]("gallery.selection.find_similar", None)
    assert seen == [[c, a, b]]


def test_callbacks_and_default_see_the_same_scope(monkeypatch) -> None:
    """One resolve, one scope: a callback and the default path agree exactly."""
    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    analyzed: list[Path] = []
    seen: list[list[Path]] = []
    owner = _owner({a, b, c}, order=[b, c, a])
    owner.analyze = _record_analyze(analyzed)

    with_cb = _open_menu(monkeypatch, owner, b, on_analyze=lambda t: seen.append(list(t)))
    with_cb["on_triggered"]("gallery.selection.analyze", None)
    without_cb = _open_menu(monkeypatch, owner, b)
    without_cb["on_triggered"]("gallery.selection.analyze", None)

    assert seen == [[b, c, a]]
    assert analyzed == seen[0]


@pytest.mark.parametrize("param", ["on_analyze", "on_carry", "on_find_similar"])
def test_zero_arg_callback_fails_closed(monkeypatch, param) -> None:
    """Contract guard: a callback that cannot take the targets is rejected.

    Silently calling it with no arguments is the bypass this contract
    removes — it must be loud, not forgiven.
    """
    owner = _owner({Path("/a.png")})
    with pytest.raises((TypeError, ValueError)) as excinfo:
        _open_menu(monkeypatch, owner, Path("/a.png"), **{param: lambda: None})
    assert param in str(excinfo.value)


def test_default_analyze_isolates_per_target_failures(monkeypatch) -> None:
    """One failing target never aborts the rest of the analyzer's context.

    The context is the PRODUCTION one (``context_for_paths``), so it carries the
    AI backend's own axis set: R6 refuses an axis-less AI call by name instead
    of judging on borrowed detector axes (owner rule 2026-10-26), and this test
    is about the per-target loop, not about the profile gate.
    """
    from tabs.image_gallery.services.metric_profile import MetricProfile
    from tabs.image_gallery.use_cases import ai_analyze
    from tabs.image_gallery.use_cases.action_context import (
        ORIGIN_ACTION,
        context_for_paths,
    )

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    seen: list[Path] = []
    items = [SimpleNamespace(path=p, mtime_ns=0) for p in (a, b, c)]

    def _begin(ctx, item):
        if item.path == b:
            raise RuntimeError("boom")
        seen.append(item.path)

    owner = SimpleNamespace(
        state=SimpleNamespace(
            mode="camera",
            algorithms_profile=None,
            ai_profile=MetricProfile(
                axis_ids=("sharpness", "noise"), mode="camera", source="vlm"
            ),
            items=items,
        ),
        widget=SimpleNamespace(refresh_card=lambda it: None),
        _judgment_domain="ai",
        _ai_settings_store=SimpleNamespace(
            load=lambda: SimpleNamespace(
                enabled=True,
                api_key="k",
                model="m",
                base_url="http://h",
                reasoning_effort="auto",
            )
        ),
        _begin_analysis=_begin,
    )
    monkeypatch.setattr(ai_analyze, "load_cached_analysis", lambda *a, **k: None)

    ctx = context_for_paths(owner, (a, b, c), origin=ORIGIN_ACTION)
    assert ai_analyze.analyze(owner, ctx) is None
    assert seen == [a, c]


def test_card_context_call_site_analyzes_every_selected_target(monkeypatch) -> None:
    """RED BEFORE: the production path passed a zero-arg closure that analyzed
    ``next(iter(selected_paths))`` — one arbitrary card of a multi-selection.

    The widget's own context-menu entry (``card_actions._on_card_context``) is
    what the owner actually clicked; a popup-level test alone cannot catch a
    caller that shadows the menu's default scope again.
    """
    from tabs.image_gallery.ui.widget_parts import card_actions

    a, b, c = Path("/a.png"), Path("/b.png"), Path("/c.png")
    analyzed: list[Path] = []
    tri_owner = SimpleNamespace(
        state=SimpleNamespace(selected_paths={a, b, c}, selected_order=[a, b, c]),
        _judgment_domain="algorithms",
        analyze=_record_analyze(analyzed),
    )
    owner = SimpleNamespace(
        _owner_for_triage=lambda: tri_owner,
        _grid_view=SimpleNamespace(card_for=lambda p: None),
        _context=None,
    )
    captured = _capture_menu(monkeypatch)
    card_actions._on_card_context(owner, a)
    captured["on_triggered"]("gallery.selection.analyze", None)
    assert analyzed == [a, b, c]



# --- the widening cannot come back -----------------------------------------
#
# The behaviour tests above would still pass if a future edit re-introduced
# ``paths=None`` at ONE of the two reset call sites while the other kept the
# scope (each test fires one entry). This structural guard names the exact
# bypass that produced the 2026-10-27 report: a resolved ``ActionContext`` is
# passed to ``reset_metrics_caches`` as ``paths=None`` instead of its targets.
# It is red on the parent tree (both call sites read ``paths=None``).


def _called_with_paths_none(fn, call_name: str) -> bool:
    """True when *fn*'s source calls ``call_name(..., paths=None)``."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name != call_name:
            continue
        for kw in node.keywords:
            if kw.arg == "paths" and isinstance(kw.value, ast.Constant):
                if kw.value.value is None:
                    return True
        if any(isinstance(a, ast.Constant) and a.value is None for a in node.args):
            return True
    return False


def test_no_reset_entry_widens_a_resolved_scope_to_the_pool() -> None:
    from tabs.image_gallery.ui.card import context_actions
    from tabs.image_gallery.use_cases import gallery_actions

    assert not _called_with_paths_none(
        gallery_actions.reset_metrics, "reset_metrics_caches"
    ), "gallery_actions.reset_metrics must pass the context's targets, never None"
    assert not _called_with_paths_none(
        context_actions._ctx_reset_metrics, "reset_metrics_caches"
    ), "_ctx_reset_metrics must pass the resolved targets, never None"


# --- ONE scope for every gallery action (2026-10-27 unification) ------------
#
# Owner report: "выбрал 2 карточки — обработалось 100, и наоборот". Each test
# below is RED on the pre-unification tree and pins one of the five independent
# resolvers that used to coexist (Ctrl+A over the pool, visible∩12 for the domain
# switch, selected[0] for B, a single card for Quick Look, pool for Run triage).


def _gallery_item(name: str):
    from tabs.image_gallery.models import GalleryItem

    return GalleryItem(path=Path(f"/g/{name}"), mtime_ns=0)


def _grid(owner, visible, *, laid_out: bool = True):
    from types import SimpleNamespace

    grid = SimpleNamespace(
        visible_paths_strict=lambda: (list(visible) if laid_out else None),
        visible_paths=lambda: list(visible),
    )
    owner.widget = SimpleNamespace(_grid_view=grid)
    return owner


def test_select_all_selects_what_the_filter_shows(monkeypatch) -> None:
    """RED BEFORE (1): Ctrl+A put all 100 items in the selection, filter or not.

    Rule 6: the selection is what is VISIBLE — the filter hides two of a
    hundred cards, so two are selected. Pre-fix ``selection.select_all`` walked
    ``state.items`` and selected every card of the tab.
    """
    from tabs.image_gallery.use_cases import selection

    items = [_gallery_item("keep_alpha.png"), _gallery_item("keep_beta.png")] + [
        _gallery_item(f"other_{i}.png") for i in range(98)
    ]
    owner = _grid(_owner(set(), items=items), [it.path for it in items])
    owner.state.filter_text = "keep_"

    selection.select_all(owner)

    assert {p.name for p in owner.state.selected_paths} == {
        "keep_alpha.png",
        "keep_beta.png",
    }


def test_select_all_in_a_small_viewport_selects_the_viewport_only() -> None:
    """RED BEFORE (2): Ctrl+A ignored the viewport and selected the pool."""
    from tabs.image_gallery.use_cases import selection

    items = [_gallery_item(f"img_{i}.png") for i in range(100)]
    owner = _grid(_owner(set(), items=items), [items[0].path, items[1].path])

    selection.select_all(owner)

    assert {p.name for p in owner.state.selected_paths} == {"img_0.png", "img_1.png"}


def test_domain_switch_analyzes_the_selection_not_the_viewport() -> None:
    """RED BEFORE (3): a two-card selection, twenty visible → twelve analyzed."""
    from tabs.image_gallery.use_cases import ai_analysis

    items = [_gallery_item(f"img_{i}.png") for i in range(20)]
    a, b = items[0].path, items[1].path
    analyzed: list = []
    owner = _grid(
        _owner({a, b}, order=[a, b], items=items), [it.path for it in items]
    )
    owner.analyze = lambda ctx: analyzed.extend(ctx.targets)

    ai_analysis._run_ai_for_visible(owner)

    assert analyzed == [a, b]


def test_domain_switch_refuses_an_unlaid_out_grid_instead_of_the_pool() -> None:
    """RED BEFORE: no viewport + no selection analyzed the first 12 of the pool."""
    from tabs.image_gallery.use_cases import ai_analysis

    items = [_gallery_item(f"img_{i}.png") for i in range(20)]
    analyzed: list = []
    owner = _grid(
        _owner(set(), items=items), [it.path for it in items], laid_out=False
    )
    owner.analyze = lambda ctx: analyzed.extend(ctx.targets)

    ai_analysis._run_ai_for_visible(owner)

    assert analyzed == [], "an unlaid-out grid must not analyze the pool"


def test_run_triage_with_a_selection_names_the_pool_and_refuses() -> None:
    """RED BEFORE (5): Run triage silently re-ran the folder over a selection."""
    from tabs.image_gallery.use_cases import action_context, registration
    from tabs.image_gallery.use_cases.action_context import (
        REFUSAL_AMBIGUOUS_SCOPE,
        Refusal,
    )

    items = [_gallery_item(f"img_{i}.png") for i in range(3)]
    a, b = items[0].path, items[1].path
    ctrl = _owner({a, b}, order=[a, b], items=items)
    ctrl.state.folder = Path("/g")
    opened: list = []
    ctrl.open_folder = opened.append
    tab = SimpleNamespace(_controller=ctrl, _widget=None)

    ctx = action_context.build_context(ctrl, origin="action", action_id="gallery.run-triage")
    refusal = registration._action_run_triage(tab, ctx)

    assert opened == [], "the folder was re-opened despite an ignored selection"
    assert isinstance(refusal, Refusal)
    assert refusal.reason == REFUSAL_AMBIGUOUS_SCOPE
    assert "pool=3" in refusal.detail and "selection=2" in refusal.detail


def test_menu_header_counts_the_resolved_scope_not_the_selection_mirror(
    monkeypatch,
) -> None:
    """RED BEFORE (7): the header counted the ``state.selected_paths`` mirror.

    The gallery slot is the selection authority; here the slot holds ONE card
    while the local mirror still holds three. The menu must title the section
    with the scope it will act on (``len(ctx.targets)``), not with the stale
    mirror count.
    """
    from tabs.image_gallery.state.models import GallerySlotState
    from tabs.image_gallery.ui.card.context_menu import (
        popup_gallery_card_context_menu,
    )

    a, b, c = (Path(p) for p in ("/a.png", "/b.png", "/c.png"))
    owner = _owner({a, b, c}, order=[a, b, c], items=[])
    owner.store = SimpleNamespace(
        get_session_state_slot=lambda name, session_id=None: GallerySlotState(
            selection=[str(a)]
        )
    )
    captured = _capture_menu(monkeypatch)

    popup_gallery_card_context_menu(
        SimpleNamespace(), owner, a, global_pos=QPoint(0, 0), selection_count=3
    )

    assert _section_title(captured["entries"]) == "1 selected"


def test_menu_actions_use_the_context_the_menu_built(monkeypatch) -> None:
    """RED BEFORE (8): four entries re-resolved their own scope on click.

    The menu resolves ONCE. A card joining the selection between opening the
    menu and clicking must not join the action: the body receives the context
    the menu already built.
    """
    from tabs.image_gallery.use_cases import triage as _triage

    a, b, c = (Path(p) for p in ("/a.png", "/b.png", "/c.png"))
    owner = _owner({a, b}, order=[a, b])
    best: list[Path] = []
    monkeypatch.setattr(_triage, "make_best", lambda o, p: best.append(Path(p)) or True)

    captured = _open_menu(monkeypatch, owner, a, selection_count=2)
    # The user Ctrl-clicks a third card while the menu is open.
    owner.state.selected_paths = {a, b, c}
    owner.state.selected_order = [a, b, c]
    captured["on_triggered"]("gallery.make_best", None)

    assert best == [a, b], "the menu entry re-resolved its scope on click"


def test_keyboard_make_best_applies_to_the_whole_selection(monkeypatch) -> None:
    """RED BEFORE (10): ``B`` called ``make_best`` on ``selected_order[0]`` only."""
    from tabs.image_gallery.use_cases import triage as _triage
    from tabs.image_gallery.use_cases import triage_ui

    a, b, c = (Path(p) for p in ("/a.png", "/b.png", "/c.png"))
    ctrl = _owner({a, b, c}, order=[c, a, b])
    widget = SimpleNamespace(_owner_for_triage=lambda: ctrl)
    best: list[Path] = []
    monkeypatch.setattr(_triage, "make_best", lambda o, p: best.append(Path(p)) or True)

    event = _KeyEvent(Qt.Key.Key_B)
    triage_ui.handle_key(widget, event)

    assert best == [c, a, b]
    assert event.accepted


def test_quick_look_reject_uses_the_menu_application(monkeypatch) -> None:
    """RED BEFORE (11): QL reject had its own toggle path (``toggle_reject``).

    Both surfaces now apply the ONE helper, so the direction rule (uniform from
    the invoked card) cannot differ between the menu and Quick Look.
    """
    from tabs.image_gallery.ui.quick_look.overlay_parts import dispatch
    from tabs.image_gallery.use_cases import triage as _triage

    a = Path("/a.png")
    owner = _owner({a}, order=[a], items=[SimpleNamespace(path=a, rejected=False)])
    applied: list = []
    toggled: list = []
    monkeypatch.setattr(
        _triage, "set_rejected_paths", lambda o, ps, rej: applied.append((list(ps), rej)) or 1
    )
    monkeypatch.setattr(_triage, "toggle_reject", lambda o, p: toggled.append(p) or True)
    overlay = SimpleNamespace(
        _current_item=SimpleNamespace(path=a, rejected=False),
        _owner=owner,
        _refresh_triage_state=lambda: None,
    )

    dispatch._on_reject(overlay)

    assert applied == [([a], True)]
    assert toggled == [], "Quick Look by-passed the menu's reject application"


def test_quick_look_reject_matches_the_menu_for_the_same_card() -> None:
    """Parity guard for (11): one selected card, both surfaces, same flags."""
    from tabs.image_gallery.ui.card import context_actions
    from tabs.image_gallery.ui.quick_look.overlay_parts import dispatch

    a = Path("/a.png")

    def _fresh():
        item = SimpleNamespace(path=a, rejected=False, triage_rejected=False)
        return _owner({a}, order=[a], items=[item]), item

    menu_owner, menu_item = _fresh()
    ql_owner, ql_item = _fresh()
    overlay = SimpleNamespace(
        _current_item=ql_item,
        _owner=ql_owner,
        _refresh_triage_state=lambda: None,
    )

    context_actions._ctx_toggle_reject(menu_owner, a)
    dispatch._on_reject(overlay)

    assert bool(menu_item.rejected) == bool(ql_item.rejected) is True


def test_quick_look_compare_does_not_rewrite_the_selection(monkeypatch) -> None:
    """RED BEFORE (12): Compare narrowed a three-card selection to one card."""
    from tabs.image_gallery.use_cases import gallery_actions
    from tabs.image_gallery.ui.quick_look.overlay_parts import dispatch

    a, b, c = (Path(p) for p in ("/a.png", "/b.png", "/c.png"))
    owner = _owner({a, b, c}, order=[a, b, c])
    written: list = []

    def _set_selection(paths):
        written.append(list(paths))
        owner.state.selected_paths = set(paths)
        owner.state.selected_order = list(paths)

    owner.set_selection = _set_selection
    carried: list = []
    monkeypatch.setattr(
        gallery_actions, "carry", lambda o, ctx, **kw: carried.append(list(ctx.targets))
    )
    overlay = SimpleNamespace(
        _current_item=SimpleNamespace(path=a, thumbnail=None),
        _owner=owner,
        hide=lambda: None,
    )

    dispatch._on_compare(overlay)

    assert carried == [[a]]
    assert {p.name for p in owner.state.selected_paths} == {"a.png", "b.png", "c.png"}
    assert written == [], "Quick Look Compare rewrote the gallery selection"


def test_make_source_answers_the_same_in_the_menu_and_the_registry(monkeypatch) -> None:
    """RED BEFORE (9): the menu picked the clicked card, the registry refused.

    Rule 8: one answer for a multi-selection — the entry is not offered, and
    the Find Action row refuses by name.
    """
    from tabs.image_gallery.use_cases import registration
    from tabs.image_gallery.use_cases.action_context import (
        REFUSAL_AMBIGUOUS_SCOPE,
        Refusal,
    )

    a, b = Path("/a.png"), Path("/b.png")
    owner = _owner({a, b}, order=[a, b], items=[])
    captured = _open_menu(monkeypatch, owner, a, selection_count=2)

    assert "gallery.set_as_source" not in _ids(captured["entries"])
    refusal = registration.run_action(
        SimpleNamespace(_controller=owner, _widget=None), "gallery.set-as-source"
    )
    assert isinstance(refusal, Refusal)
    assert refusal.reason == REFUSAL_AMBIGUOUS_SCOPE


def test_make_source_still_shows_for_a_single_card(monkeypatch) -> None:
    """The refusal is about the SCOPE, not about hiding a working action."""
    a = Path("/a.png")
    owner = _owner({a}, order=[a], items=[])
    captured = _open_menu(monkeypatch, owner, a, selection_count=1)
    assert "gallery.set_as_source" in _ids(captured["entries"])


def _ids(entries) -> list[str]:
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSection

    out: list[str] = []
    for entry in entries:
        if isinstance(entry, ContextMenuSection):
            out.extend(a.action_id for a in entry.entries)
        elif isinstance(entry, ContextMenuAction):
            out.append(entry.action_id)
    return out


def _section_title(entries) -> str:
    from sli_ui_toolkit.widgets import ContextMenuSection

    for entry in entries:
        if isinstance(entry, ContextMenuSection):
            return str(getattr(entry, "title", "") or "")
    return ""


class _KeyEvent:
    """Minimal QKeyEvent double (``triage_ui.handle_key`` reads key/accept)."""

    def __init__(self, key) -> None:
        self._key = key
        self.accepted = False

    def key(self):
        return self._key

    def accept(self) -> None:
        self.accepted = True
