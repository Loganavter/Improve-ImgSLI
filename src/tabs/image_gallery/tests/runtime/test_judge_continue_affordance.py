"""The judge-run continue affordance is a real, live action (board 2026-10-24).

STATE this closes: the ceiling stop parked cards and exposed
``GalleryController.continue_judge_run()`` / ``judge_run_continue_available``,
but NOTHING callable existed — a user who hit the ceiling saw the stop line and
had no action. The Find Action row registered here is that action, and it is
LIVE: ``enabled`` / ``reason`` / the parked count are re-read from the ONE
ledger (``use_cases/judge_budget``) every time the run state changes.

Falsification stories (each assertion fails without the wiring):

(a) before any ceiling stop the row is catalogued but disabled — fails if the
    descriptor hardcodes ``enabled=True`` (a stale button) or is missing
    entirely (the contract requires every handler to own exactly one row);
(b) a ceiling stop enables it and the reason names the parked count — fails if
    the row keeps the state it had at registration time (nothing refreshes it)
    or if the count comes from a second counter;
(c) dispatching the row (``run()``) resumes exactly the parked cards and the
    row follows the ledger back to disabled once nothing is left — fails if the
    handler is a stub, if it re-analyzes a card the ceiling did not refuse, or
    if the row stays enabled after the run is over;
(d) opening another folder drops the affordance — fails if a ceiling stop from
    the closed folder leaves a runnable row behind;
(e) the stats strip carries the SAME affordance visibly (enabled + labelled
    with the parked count, click ⇒ the registered handler, gone again when the
    ledger empties or the folder changes) — fails if only Find Action can
    continue a parked run.

Runs offscreen; no network, no window: the controller double never starts a
real worker (``_pool_start`` is a no-op) and the judge is scripted.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AnalysisStatus, GalleryItem
from tabs.image_gallery.use_cases import registration
from tabs.image_gallery.use_cases.action_context import ORIGIN_ACTION, context_for_paths

CONTINUE_ACTION_ID = "gallery.continue-judge"


# -- doubles ------------------------------------------------------------------


class _Text:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def setText(self, text) -> None:  # noqa: N802 (Qt name)
        self.texts.append(str(text))

    def show(self) -> None:
        pass


class _Toolbar:
    def __init__(self) -> None:
        self.scanning_label = _Text()

    def set_triage_done(self) -> None:
        pass


class _Widget:
    def __init__(self) -> None:
        self.toolbar = _Toolbar()

    def refresh_card(self, item) -> None:
        pass

    def refresh_cards(self, items) -> None:
        pass

    def set_ranks_visible(self, flag) -> None:
        pass


class _Registry:
    """Minimal ``ActionRegistry`` double: replaced by id, like the real one."""

    def __init__(self) -> None:
        self.by_id: dict[str, object] = {}

    def register(self, descriptor) -> None:
        self.by_id[descriptor.action_id] = descriptor

    def get(self, action_id: str):
        return self.by_id.get(action_id)


def _item(name: str) -> GalleryItem:
    return GalleryItem(path=Path("/gallery") / name, mtime_ns=1)


def _settings(**overrides):
    base = dict(
        enabled=True,
        api_key="k",
        model="m",
        base_url="http://h",
        sample_count=1,
        judge_run_call_ceiling=0,
        judge_concurrency=1,
        vlm_max_edge_px=1024,
        sampling_temperature=0.0,
        sampling_seed=0,
        reasoning_effort="auto",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _owner(items, **settings_overrides) -> GalleryController:
    """A storeless controller double that binds the REAL analyze path."""
    ctl = GalleryController.__new__(GalleryController)
    ctl.state = SimpleNamespace(items=list(items), mode="camera", metric_profile=None)
    ctl.widget = _Widget()
    ctl._folder_gen = 0
    ctl._judgment_domain = "ai"
    ctl._domain_epoch = 0
    ctl._tr = lambda key, default: default
    row = _settings(**settings_overrides)
    ctl._ai_settings_store = SimpleNamespace(load=lambda: row)
    # No real pool: a scheduled worker would be a real network call.
    ctl._pool_start = lambda worker, priority: None
    ctl._activity_bridge = None
    return ctl


def _tab(owner=None) -> SimpleNamespace:
    """Tab-shaped double for ``registration`` (session_type + controller)."""
    return SimpleNamespace(
        session_type="image_gallery", _widget=None, _controller=owner
    )


def _row(registry: _Registry):
    descriptor = registry.get(CONTINUE_ACTION_ID)
    assert descriptor is not None, (
        f"{CONTINUE_ACTION_ID} is not registered — the ceiling stop has no action"
    )
    return descriptor


def _register(owner=None) -> _Registry:
    registry = _Registry()
    tab = _tab(owner)
    assert registration.register_actions(tab, registry) is True
    return registry


def _run_to_ceiling(owner, items) -> None:
    ctx = context_for_paths(owner, [it.path for it in items], origin=ORIGIN_ACTION)
    owner.analyze(ctx)


# -- (a) catalogued, disabled, no parked card --------------------------------


def test_row_is_registered_but_disabled_before_any_ceiling_stop() -> None:
    owner = _owner([_item("a.png")], judge_run_call_ceiling=2)
    registry = _register(owner)

    row = _row(registry)
    assert row.enabled is False
    assert row.reason == "no card is parked at the call ceiling"
    # The label is the ONE existing translated key — no new i18n was invented.
    assert row.label_key == "image_gallery.action.continue_judge"
    assert row.owner_tab == "image_gallery"
    assert row.run is not None


def test_the_row_exists_for_every_gallery_handler() -> None:
    """The catalog and the handler inventory cannot drift apart."""
    registry = _register(_owner([]))
    assert CONTINUE_ACTION_ID in registry.by_id
    registered = {aid for aid in registry.by_id if aid.startswith("gallery.")}
    assert registered == set(registration.GALLERY_ACTION_HANDLERS)


# -- (b) the ceiling stop enables it and names the parked count --------------


def test_ceiling_stop_enables_the_row_and_names_the_parked_count() -> None:
    items = [_item(f"{i}.png") for i in range(5)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=2)
    registry = _register(owner)

    _run_to_ceiling(owner, items)

    # The stop happened inside the pass and the row followed it (no polling).
    assert owner.judge_run_continue_available is True
    assert owner.judge_run_parked_count == 3
    row = _row(registry)
    assert row.enabled is True
    # The count comes from the SAME ledger list the predicate reads.
    assert "3 card(s) parked" in row.reason
    assert "3 parked" in row.search_terms


def test_no_ceiling_means_the_row_never_enables() -> None:
    items = [_item(f"{i}.png") for i in range(3)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=0)
    registry = _register(owner)

    _run_to_ceiling(owner, items)

    assert owner.judge_run_parked_count == 0
    row = _row(registry)
    assert row.enabled is False
    assert row.reason == "no card is parked at the call ceiling"


# -- (c) dispatching the row resumes exactly the parked cards ----------------


def test_dispatching_the_row_resumes_the_parked_cards() -> None:
    items = [_item(f"{i}.png") for i in range(5)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=2)
    registry = _register(owner)
    _run_to_ceiling(owner, items)
    assert _row(registry).enabled is True

    _row(registry).run()

    # Exactly the parked cards re-entered the ordinary analysis path …
    assert [it.analysis_status for it in items[2:4]] == [
        AnalysisStatus.PENDING,
        AnalysisStatus.PENDING,
    ]
    # … the ceiling was not lifted (one card is parked again, and says so) …
    assert owner._judge_run.skipped == [items[4].path]
    assert owner.judge_run_parked_count == 1
    row = _row(registry)
    assert row.enabled is True
    assert "1 card(s) parked" in row.reason

    # … and the row disables itself once nothing is left to continue.
    row.run()
    assert owner.judge_run_continue_available is False
    assert owner.judge_run_parked_count == 0
    row = _row(registry)
    assert row.enabled is False
    assert row.reason == "no card is parked at the call ceiling"


def test_dispatch_with_nothing_parked_is_a_named_refusal_not_a_rerun() -> None:
    items = [_item("a.png")]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=2)
    _register(owner)

    result = registration.run_action(_tab(owner), CONTINUE_ACTION_ID)

    assert getattr(result, "reason", None) == "no_items"
    assert items[0].analysis_status == AnalysisStatus.NOT_ANALYZED


# -- (d) a new folder drops the affordance ----------------------------------


def test_new_folder_generation_drops_the_affordance() -> None:
    items = [_item(f"{i}.png") for i in range(4)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=1)
    registry = _register(owner)
    _run_to_ceiling(owner, items)
    assert _row(registry).enabled is True

    owner._next_folder_gen()

    row = _row(registry)
    assert row.enabled is False, "a stop from the closed folder left a live action"
    assert owner.judge_run_continue_available is False


# -- (e) the VISIBLE control in the stats strip ------------------------------
# Same affordance family as Keep best / Clean rejected / Compare finalists: a
# painter-pipeline ``Button`` in the strip. Falsification story: without it the
# ceiling stop left the user with a stop *line* and no clickable way out — the
# action existed only in Find Action.
#
# The strip holds NO copy of the flag: it pulls ``(available, parked)`` from the
# controller through the widget's documented ``_owner_for_triage`` (every tick
# while visible + on show + right after a click), and its click dispatches the
# SAME registered handler Find Action runs (``gallery.continue-judge``).


def _btn_text(btn) -> str:
    try:
        text = getattr(btn, "_text", "") or ""
        if text:
            return str(text)
    except Exception:
        pass
    return ""


def _widget(owner):
    """The real gallery widget with the real controller attached (G2 seam)."""
    from tabs.image_gallery.widget import ImageGalleryWidget

    w = ImageGalleryWidget()
    w.attach_controller(owner)
    return w


def test_the_strip_has_no_continue_control_before_anything_is_parked(qtbot) -> None:
    owner = _owner([_item("a.png")], judge_run_call_ceiling=2)
    w = _widget(owner)
    qtbot.addWidget(w)

    btn = w.stats_strip.continue_button
    w.stats_strip.refresh_continue_state()
    assert btn.isHidden() is True, "a dead continue button is armed before any stop"
    assert btn.isEnabled() is False
    assert btn.objectName() == "gallery_continue_judge"


def test_visible_continue_control_names_the_parked_count_and_resumes_by_click(qtbot) -> None:
    items = [_item(f"{i}.png") for i in range(5)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=2)
    w = _widget(owner)
    qtbot.addWidget(w)
    btn = w.stats_strip.continue_button
    assert btn.isHidden() is True

    _run_to_ceiling(owner, items)
    assert owner.judge_run_continue_available is True
    # This is what the visible strip does (show/poll): PULL the ledger.
    w.stats_strip.refresh_continue_state()

    assert btn.isHidden() is False, "the parked run never reached the visible strip"
    assert btn.isEnabled() is True
    # Same translated key as the catalogue row, plus the count from the SAME
    # ledger list (``judge_run_parked_count``).
    assert "3" in _btn_text(btn), _btn_text(btn)

    # A click is a dispatch of the registered action, not a private code path:
    # the parked cards re-enter the ordinary analysis pass …
    btn.click()
    assert [it.analysis_status for it in items[2:4]] == [
        AnalysisStatus.PENDING,
        AnalysisStatus.PENDING,
    ]
    # … one card re-parks at the same ceiling, and the button follows it
    # immediately (the click re-reads before returning, no waiting for a tick).
    assert owner.judge_run_parked_count == 1
    assert btn.isEnabled() is True
    assert "1" in _btn_text(btn), _btn_text(btn)

    # Nothing left to continue ⇒ the control goes away again.
    btn.click()
    assert owner.judge_run_continue_available is False
    assert btn.isHidden() is True
    assert btn.isEnabled() is False


def test_a_folder_change_clears_the_visible_control(qtbot) -> None:
    items = [_item(f"{i}.png") for i in range(4)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=1)
    w = _widget(owner)
    qtbot.addWidget(w)
    _run_to_ceiling(owner, items)
    w.stats_strip.refresh_continue_state()
    assert w.stats_strip.continue_button.isHidden() is False

    owner._next_folder_gen()
    w.stats_strip.refresh_continue_state()

    btn = w.stats_strip.continue_button
    assert btn.isHidden() is True, "a stop from the closed folder left a live button"
    assert btn.isEnabled() is False


def test_the_visible_control_dispatches_the_registered_action_id(qtbot) -> None:
    """The click target is the catalog handler — never a second implementation."""
    items = [_item(f"{i}.png") for i in range(3)]
    owner = _owner(items, sample_count=1, judge_run_call_ceiling=1)
    w = _widget(owner)
    qtbot.addWidget(w)
    _run_to_ceiling(owner, items)
    w.stats_strip.refresh_continue_state()
    btn = w.stats_strip.continue_button
    assert btn.isEnabled() is True

    calls: list[str] = []
    real = owner.continue_judge_run

    def _spy(*args, **kwargs):
        calls.append(CONTINUE_ACTION_ID)
        return real(*args, **kwargs)

    # ``run_action`` resolves the handler by id; the handler calls this method.
    owner.continue_judge_run = _spy  # type: ignore[method-assign]
    try:
        btn.click()
    finally:
        try:
            del owner.continue_judge_run
        except Exception:
            owner.continue_judge_run = real  # type: ignore[method-assign]

    assert calls == [CONTINUE_ACTION_ID], (
        "the strip button did not go through gallery.continue-judge"
    )
