"""ONE scope mechanism for every gallery action — the policy table and resolver.

Owner report 2026-10-27: *"выбрал 2 карточки — обработалось 100, и наоборот"*.
Five independent scope resolvers existed at once (menu selection, ``selected[0]``
for ``B``, one card for Quick Look, ``visible ∩ 12`` for the domain switch,
``pool``/``series`` for the stats strip and ``Ctrl+A``) and they disagreed in
both directions.

Every test here is RED on the pre-unification tree:

* ``ACTION_SCOPE_POLICY`` / ``resolve_scope`` / ``Scope`` did not exist (the
  module-level import fails);
* ``Ctrl+A`` selected every pooled item, filter or not;
* ``SCOPE_VISIBLE`` failed open to the whole pool on an unlaid-out grid
  (``ui/grid_view/__init__.py`` returned every item);
* the domain switch analyzed ``visible ∩ 12`` no matter what was selected;
* ``B`` acted on ``selected_order[0]`` only.

The resolver is exercised with plain ``SimpleNamespace`` owners (no app boot):
a real ``GalleryItem`` pool, a fake grid view exposing
``visible_paths``/``visible_paths_strict``, and a fake store slot for the
slot-vs-mirror authority test.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from core.log_names import APP_LOGGER_NAME
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.state.models import GallerySlotState
from tabs.image_gallery.use_cases import action_scope

# -- fixtures ----------------------------------------------------------------


def _item(name: str) -> GalleryItem:
    return GalleryItem(path=Path(f"/g/{name}"), mtime_ns=0)


class _Grid:
    """Minimal grid-view double: strict and legacy viewport reads."""

    def __init__(self, visible, laid_out: bool = True) -> None:
        self._visible = [Path(p) for p in visible]
        self._laid_out = laid_out

    def visible_paths_strict(self):
        return list(self._visible) if self._laid_out else None

    def visible_paths(self):
        # The production legacy read fails OPEN when not laid out.
        return list(self._visible) if self._laid_out else list(self._visible)


class _Store:
    """Store double whose gallery slot is the selection authority."""

    def __init__(self, selection) -> None:
        self._slot = GallerySlotState(selection=[str(p) for p in selection])

    def get_session_state_slot(self, name, session_id=None):
        return self._slot


def _owner(
    items,
    selected=(),
    order=None,
    *,
    visible=None,
    laid_out: bool = True,
    filter_text: str = "",
    cap: int = 12,
    store=None,
    **extra,
):
    items = list(items)
    grid = _Grid(
        visible if visible is not None else [it.path for it in items],
        laid_out=laid_out,
    )
    state = SimpleNamespace(
        selected_paths={Path(p) for p in selected},
        selected_order=[Path(p) for p in (order if order is not None else selected)],
        items=items,
        filter_text=filter_text,
    )
    ns = SimpleNamespace(
        state=state,
        widget=SimpleNamespace(_grid_view=grid),
        _judgment_domain="algorithms",
        _AI_VISIBLE_CAP=cap,
    )
    if store is not None:
        ns.store = store
    ns.__dict__.update(extra)
    return ns


def _pool(n: int, prefix: str = "img") -> list[GalleryItem]:
    return [_item(f"{prefix}_{i}.png") for i in range(n)]


def _capture_menu(monkeypatch):
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

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None, **_kw):
        captured["entries"] = tuple(entries)
        captured["on_triggered"] = on_triggered
        return _FakeMenu(source_widget, entries=entries, on_triggered=on_triggered)

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)
    monkeypatch.setattr(_w, "ContextMenu", _FakeMenu)
    return captured


def _entries(entries):
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSection

    out = []
    for entry in entries:
        if isinstance(entry, ContextMenuSection):
            out.extend(entry.entries)
        elif isinstance(entry, ContextMenuAction):
            out.append(entry)
    return out


def _ids(entries) -> list[str]:
    return [a.action_id for a in _entries(entries)]


def _section_title(entries) -> str:
    from sli_ui_toolkit.widgets import ContextMenuSection

    for entry in entries:
        if isinstance(entry, ContextMenuSection):
            return str(getattr(entry, "title", "") or "")
    return ""


# -- the policy table --------------------------------------------------------


def test_policy_table_covers_the_owner_mandated_rows() -> None:
    """The declared minimum: one readable table, no action without a kind."""
    required = {
        # card menu (selection, else the clicked card)
        "gallery.card.analyze": action_scope.SCOPE_SELECTION_OR_CARD,
        "gallery.card.find_similar": action_scope.SCOPE_SELECTION_OR_CARD,
        "gallery.card.ask_ai": action_scope.SCOPE_SELECTION_OR_CARD,
        "gallery.card.make_best": action_scope.SCOPE_SELECTION_OR_CARD,
        "gallery.card.reject": action_scope.SCOPE_SELECTION_OR_CARD,
        "gallery.card.remove": action_scope.SCOPE_SELECTION_OR_CARD,
        "gallery.card.group": action_scope.SCOPE_SELECTION_OR_CARD,
        "gallery.card.ungroup": action_scope.SCOPE_SELECTION_OR_CARD,
        "gallery.card.reset_metrics": action_scope.SCOPE_SELECTION_OR_CARD,
        # one answer for Make source, in the menu and the registry
        "gallery.card.set_source": action_scope.SCOPE_SINGLE,
        "gallery.set-as-source": action_scope.SCOPE_SINGLE,
        # keyboard: the whole selection
        "gallery.key.delete": action_scope.SCOPE_SELECTION,
        "gallery.key.make_best": action_scope.SCOPE_SELECTION,
        "gallery.key.compare": action_scope.SCOPE_SELECTION,
        # Quick Look: the card on screen
        "gallery.quick_look.reject": action_scope.SCOPE_CARD,
        "gallery.quick_look.delete": action_scope.SCOPE_CARD,
        "gallery.quick_look.set_source": action_scope.SCOPE_CARD,
        "gallery.quick_look.compare": action_scope.SCOPE_CARD,
        # stats strip / series headers: explicitly pool- and series-wide
        "gallery.stats.keep_best": action_scope.SCOPE_POOL,
        "gallery.stats.show_all": action_scope.SCOPE_POOL,
        "gallery.stats.clean_rejected": action_scope.SCOPE_POOL,
        "gallery.stats.compare_finalists": action_scope.SCOPE_POOL,
        "gallery.series.delete": action_scope.SCOPE_SERIES,
        # run-level actions
        "gallery.run-triage": action_scope.SCOPE_POOL,
        "gallery.continue-judge": action_scope.SCOPE_PARKED,
        # domain switch / settle: selection, else the capped viewport
        "gallery.domain.switch": action_scope.SCOPE_SELECTION_ELSE_VISIBLE,
        "gallery.settle.auto": action_scope.SCOPE_SELECTION_ELSE_VISIBLE,
        # Ctrl+A: what is visible
        "select_all": action_scope.SCOPE_VISIBLE,
    }
    missing = {k: v for k, v in required.items() if action_scope.ACTION_SCOPE_POLICY.get(k) != v}
    assert not missing, f"policy rows missing or wrong: {missing}"
    unknown_kinds = {
        action_id: kind
        for action_id, kind in action_scope.ACTION_SCOPE_POLICY.items()
        if kind not in action_scope.SCOPES
    }
    assert not unknown_kinds, f"policy rows name an undeclared scope kind: {unknown_kinds}"


def test_unknown_action_id_is_a_named_refusal() -> None:
    """An id with no policy row never guesses a scope (contract test 13's twin)."""
    owner = _owner(_pool(3), selected=("/g/img_0.png",))
    scope = action_scope.resolve_scope(owner, "gallery.not.a.real.action")
    assert scope.refused == action_scope.REFUSAL_UNKNOWN_ACTION
    assert scope.targets == ()


def test_every_scope_carries_one_tracer_line() -> None:
    """Rule 4: ``Scope.reason`` is ``action=… kind=… n=… card=…`` (cap included)."""
    owner = _owner(_pool(20), selected=("/g/img_3.png",), cap=4)
    scope = action_scope.resolve_scope(
        owner, "gallery.card.analyze", card_path=Path("/g/img_3.png")
    )
    assert scope.kind == action_scope.SCOPE_SELECTION_OR_CARD
    assert scope.reason.startswith("action=gallery.card.analyze kind=selection_or_card n=1")
    assert "card=/g/img_3.png" in scope.reason
    capped = action_scope.resolve_scope(
        _owner(_pool(20), cap=4), "gallery.domain.switch"
    )
    assert "cap=4 available=20" in capped.reason, capped.reason


def test_scope_line_goes_to_the_app_logger(caplog) -> None:
    owner = _owner(_pool(1))
    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        action_scope.resolve_scope(owner, "gallery.stats.keep_best")
    assert any("scope action=gallery.stats.keep_best kind=pool" in r.getMessage() for r in caplog.records)


# -- SCOPE_VISIBLE: the viewport, never the pool -----------------------------


def test_visible_scope_refuses_an_unlaid_out_grid(monkeypatch) -> None:
    """RED BEFORE (test 4): the unlaid-out grid failed open to the whole pool."""
    owner = _owner(_pool(100), visible=[], laid_out=False)
    scope = action_scope.resolve_scope(owner, "select_all")
    assert scope.refused == action_scope.REFUSAL_NOT_LAID_OUT
    assert scope.targets == (), "an unlaid-out grid resolved to cards it never showed"


def test_visible_scope_is_the_viewport_not_the_pool() -> None:
    """RED BEFORE: ``SCOPE_VISIBLE`` answered every item of the tab."""
    items = _pool(100)
    visible = [items[0].path, items[1].path]
    owner = _owner(items, visible=visible)
    scope = action_scope.resolve_scope(owner, "select_all")
    assert scope.kind == action_scope.SCOPE_VISIBLE
    assert scope.targets == (items[0].path, items[1].path)


def test_visible_scope_intersects_the_active_filter() -> None:
    """A card the filter hides is not visible, even inside the viewport."""
    items = [_item("keep_alpha.png"), _item("keep_beta.png")] + _pool(98, prefix="other")
    owner = _owner(
        items,
        visible=[it.path for it in items],
        filter_text="keep_",
    )
    scope = action_scope.resolve_scope(owner, "select_all")
    names = {p.name for p in scope.targets}
    assert names == {"keep_alpha.png", "keep_beta.png"}, names


def test_visible_scope_with_no_grid_is_a_refusal() -> None:
    owner = SimpleNamespace(state=SimpleNamespace(items=_pool(5), filter_text=""))
    scope = action_scope.resolve_scope(owner, "select_all")
    assert scope.refused == action_scope.REFUSAL_NO_VIEWPORT
    assert scope.targets == ()


# -- SCOPE_SELECTION_ELSE_VISIBLE: rule 7 ------------------------------------


def test_domain_switch_prefers_a_non_empty_selection() -> None:
    """RED BEFORE (test 3): the switch analyzed visible∩12 regardless."""
    items = _pool(20)
    owner = _owner(items, selected=(items[0].path, items[1].path))
    scope = action_scope.resolve_scope(owner, "gallery.domain.switch")
    assert scope.targets == (items[0].path, items[1].path)
    assert "source=selection" in scope.reason


def test_domain_switch_caps_the_visible_branch_and_says_so() -> None:
    items = _pool(20)
    owner = _owner(items, cap=6)
    scope = action_scope.resolve_scope(owner, "gallery.domain.switch")
    assert len(scope.targets) == 6
    assert "cap=6 available=20" in scope.reason


def test_domain_switch_refuses_without_selection_and_viewport() -> None:
    owner = _owner(_pool(20), visible=[], laid_out=False)
    scope = action_scope.resolve_scope(owner, "gallery.settle.auto")
    assert scope.refused == action_scope.REFUSAL_NOT_LAID_OUT


# -- the other kinds ---------------------------------------------------------


def test_card_scope_is_exactly_the_invoked_card() -> None:
    items = _pool(3)
    owner = _owner(items, selected=[it.path for it in items])
    scope = action_scope.resolve_scope(
        owner, "gallery.quick_look.reject", card_path=items[1].path
    )
    assert scope.targets == (items[1].path,)


def test_single_scope_refuses_a_multi_selection() -> None:
    """Rule 8: Make source refuses instead of picking one of N."""
    items = _pool(3)
    owner = _owner(items, selected=[it.path for it in items])
    scope = action_scope.resolve_scope(owner, "gallery.set-as-source")
    assert scope.refused == action_scope.REFUSAL_AMBIGUOUS_SCOPE
    assert set(scope.targets) == {it.path for it in items}


def test_single_scope_answers_the_card_outside_the_selection() -> None:
    items = _pool(4)
    owner = _owner(items, selected=[items[0].path, items[1].path])
    scope = action_scope.resolve_scope(
        owner, "gallery.card.set_source", card_path=items[3].path
    )
    assert scope.targets == (items[3].path,)


def test_pool_and_series_scopes_read_their_real_groups() -> None:
    items = _pool(4)
    owner = _owner(items)
    owner.state.series = [
        SimpleNamespace(id="s1", members=[items[1], items[2]]),
    ]
    pool = action_scope.resolve_scope(owner, "gallery.keep-best-of-series")
    assert pool.targets == tuple(it.path for it in items)
    series = action_scope.resolve_scope(
        owner, "gallery.series.delete", card_path=items[2].path
    )
    assert series.targets == (items[1].path, items[2].path)


def test_parked_scope_reads_the_run_ledger() -> None:
    items = _pool(3)
    owner = _owner(items)
    owner._judge_run = SimpleNamespace(skipped=[items[2].path])
    scope = action_scope.resolve_scope(owner, "gallery.continue-judge")
    assert scope.targets == (items[2].path,)
    del owner._judge_run
    refused = action_scope.resolve_scope(owner, "gallery.continue-judge")
    assert refused.refused == action_scope.REFUSAL_NO_PARKED


def test_empty_selection_is_never_a_card() -> None:
    owner = _owner(_pool(5))
    scope = action_scope.resolve_scope(owner, "gallery.key.delete")
    assert scope.targets == ()
    assert scope.refused == action_scope.REFUSAL_EMPTY_SCOPE


# -- the slot is the selection authority (rule: one reader) ------------------


def test_slot_selection_wins_over_the_state_mirror() -> None:
    """RED BEFORE (test 7): the menu header counted the mirror, not the scope."""
    items = _pool(3)
    store = _Store([items[0].path])  # slot: ONE card
    owner = _owner(
        items,
        selected=[it.path for it in items],  # mirror: THREE (stale)
        store=store,
    )
    scope = action_scope.resolve_scope(
        owner, "gallery.card.analyze", card_path=items[0].path
    )
    assert scope.targets == (items[0].path,)
