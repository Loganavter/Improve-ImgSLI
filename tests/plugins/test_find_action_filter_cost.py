"""Find Action filtering: no description matching, no widget churn per keystroke.

Owner report 2026-10-28:

* «он отсекает лишние варианты каким-то крайне медлительным образом из-за чего
  возникают огромные лаги» — every keystroke destroyed and rebuilt a composite
  row per action (measured on a 70-action catalog: **187-359 ms per keystroke**;
  after reuse: **0.3-1.2 ms**).
* «у каждого экшена учитывается описание из справочника» — the catalog
  description was part of the Find Action haystack, so prose matched and every
  haystack carried one more key in four languages.

Both are pinned here: identity of the row widgets across queries (the mechanism
of the lag) and absence of the description from the searched text. Settings →
Keyboard keeps the description — it stays part of its own case.
"""

from __future__ import annotations

import pytest

from core.actions.types import ActionDescriptor
from ui.actions import registry as action_registry
from ui.actions.palette import dialog as palette_dialog
from ui.actions.palette.dialog import FindActionDialog
from ui.actions.registry import (
    compute_action_haystacks,
    get_action_registry,
    reset_action_registry_for_tests,
)


@pytest.fixture
def catalog():
    reset_action_registry_for_tests()
    registry = get_action_registry()
    for i in range(12):
        registry.register(
            ActionDescriptor(
                action_id=f"probe.filter.{i:02d}",
                label_key=f"probe.label.{i:02d}",
                description_key=f"probe.zebra{i:02d}",
                run=lambda: None,
            )
        )
    yield registry
    reset_action_registry_for_tests()


def test_typing_reuses_the_row_widgets(qtbot, catalog, monkeypatch):
    """A keystroke must re-order/hide rows, never construct new ones."""
    built: list[str] = []
    original_init = palette_dialog.ActionPaletteRow.__init__

    def counting_init(self, action, *args, **kwargs):
        built.append(action.action_id)
        return original_init(self, action, *args, **kwargs)

    monkeypatch.setattr(palette_dialog.ActionPaletteRow, "__init__", counting_init)

    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.wait(120)
    first_build = len(built)
    first_rows = [id(row) for row in dialog._rows]
    assert first_build >= len(first_rows) > 0

    dialog._search.setText("label")
    dialog._reload()
    # The materialized window may grow/shrink with the viewport, so the list is
    # not identical — but every row it does show must be the *same widget*.
    assert set(first_rows) <= set(id(row) for row in dialog._rows), (
        "the same actions must keep their row widgets across a query change"
    )
    rebuilt = [action_id for action_id in set(built) if built.count(action_id) > 1]
    assert rebuilt == [], (
        f"a keystroke rebuilt rows for {rebuilt}; the list must reuse them "
        "(this was the 187-359 ms per keystroke lag). Rows for newly visible "
        "actions may be materialized - that is the virtual list, not a rebuild."
    )

    dialog._search.setText("zebra")
    dialog._reload()
    assert dialog._rows == [], "filtering itself still works"


def test_description_text_is_not_searched(catalog):
    """A word that only exists in the action's description must not match."""
    matches = catalog.list_for(active_tab=None, query="zebra")
    assert [a.action_id for a in matches] == [], (
        "the catalog description is prose, not a name — Find Action must not "
        "search it (owner decision 2026-10-28)"
    )

    # The label still matches, so nothing was broken in the search itself.
    assert [a.action_id for a in catalog.list_for(active_tab=None, query="label")]


def test_settings_keyboard_search_keeps_the_description():
    """Settings → Keyboard keeps description matching (its own surface)."""
    with_description = compute_action_haystacks(
        action_id="probe.settings.row",
        label_key="probe.settings.label",
        description_key="probe.settings.zebra",
    )
    without_description = compute_action_haystacks(
        action_id="probe.settings.row",
        label_key="probe.settings.label",
        description_key="probe.settings.zebra",
        include_description=False,
    )
    assert any("zebra" in text for text in with_description)
    assert not any("zebra" in text for text in without_description)


def test_haystack_cache_does_not_keep_the_description(catalog):
    """The cached Find Action haystack is the description-free one."""
    action = catalog.get("probe.filter.00")
    assert action is not None
    haystacks = action_registry._haystacks(action)
    assert not any("zebra" in text for text in haystacks)
