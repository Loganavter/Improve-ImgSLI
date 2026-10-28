"""A placement hint must belong to the tab that reads it.

Measured live 2026-10-28 on a leased instance: ``open_file(path=…gif,
tab="image_compare", side="right")`` answered ``opened: true`` and put the file in
the **left** slot (``right_path`` stayed ``null``). Image Compare reads ``slot``;
``side`` is Multi Compare's key. ``drop_hint``'s docstring promises that an unknown
hint is the control surface's own error and "never a silently ignored drop", and it
does enforce that for an unknown *value* — but the key/target mismatch slipped
through, so the caller had no way to tell its placement was discarded.

The rule pinned here: validate the hint against the tab kinds the request may
reach, **before** any routing, so a refused hint cannot half-load a file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.control.drop_routing import (
    HINT_KEY_BY_TAB,
    check_hint_owner,
    open_file_into,
    open_folder_into,
)


def test_image_compare_owns_slot_and_multi_compare_owns_side():
    assert HINT_KEY_BY_TAB["image_compare"] == "slot"
    assert HINT_KEY_BY_TAB["multi_compare"] == "side"


@pytest.mark.parametrize(
    "hint, kinds",
    (
        ({"slot": 1}, ["image_compare"]),
        ({"slot": 2}, ["image_compare"]),
        ({"side": "left"}, ["multi_compare"]),
        ({"side": "top"}, ["multi_compare"]),
        ({"side": "left"}, ["image_compare", "multi_compare"]),
        ({"slot": 2}, ["image_compare", "multi_compare"]),
        (None, ["image_compare"]),
    ),
)
def test_owned_hints_pass(hint, kinds):
    check_hint_owner(hint, kinds)


@pytest.mark.parametrize(
    "hint, kinds, expected",
    (
        ({"side": "right"}, ["image_compare"], "image_compare takes slot="),
        ({"slot": 2}, ["multi_compare"], "multi_compare takes side="),
        ({"side": "left"}, ["image_gallery"], "no target tab reads it"),
    ),
)
def test_foreign_or_unowned_hints_are_refused(hint, kinds, expected):
    with pytest.raises(ValueError) as excinfo:
        check_hint_owner(hint, kinds)
    assert expected in str(excinfo.value)


def test_a_refused_hint_never_reaches_the_tab(tmp_path):
    """The refusal happens before routing, so nothing is half-loaded."""
    path = tmp_path / "probe.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")

    def _tabs():  # a mistake is "the router was asked at all"
        raise AssertionError("routing must not start when the hint is refused")

    with pytest.raises(ValueError, match="image_compare takes slot="):
        open_file_into(
            path,
            wanted="image_compare",
            candidates=["image_compare"],
            tabs=_tabs,
            kinds=["image_compare", "multi_compare"],
            run_action=lambda action_id: None,
            hint={"side": "right"},
        )


def test_open_folder_uses_the_same_rule(tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    with pytest.raises(ValueError, match="multi_compare takes side="):
        open_folder_into(
            folder,
            "multi_compare",
            tabs=lambda: [],
            kinds=["image_compare", "multi_compare"],
            run_action=lambda action_id: None,
            hint={"slot": 1},
        )
