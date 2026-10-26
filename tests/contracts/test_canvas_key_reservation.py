"""The action map may not take a key the canvas input layer already handles.

``test_keymap_unique_bindings.py`` owns "one chord, one action per tab" — the
catalog compared with itself. That invariant is blind to the defect this file
pins: a *fixed* input-layer key taken by a *remappable* action. Neither side is
hand-written here — the action side is the shipped catalog
(``collect_keymap_defaults``) and the input side is discovered from source by
``_key_claims.discover_claims`` (every ``Qt.Key.Key_*`` literal and every
modifier-less shortcut literal, attributed by file path).

2026-10-26 regression this gate was built for: ``image_compare.divider.visible``
shipped ``D``, and ``D`` is the magnifier's "pan right". The action map wins by
construction (a tab-bound chord beats the global canvas route,
``events/router.py``), so the help's promise that canvas keys are fixed and
cannot be remapped was false for one of the six movement keys — and the
keybinding audit could not report it, because the loupe keys are not catalog
rows. The chord moved to ``L``; this file is what stops it coming back.
"""

from __future__ import annotations

import pytest

from tests.contracts._key_claims import (
    KeyClaim,
    catalog_defaults,
    discover_claims,
    portable_key,
    reserved_clashes,
    scope_of,
)
from ui.actions.keymap_uniqueness import duplicate_bindings


# -- the gate ---------------------------------------------------------------


def test_shipped_catalog_takes_no_key_the_input_layer_handles():
    defaults = catalog_defaults()
    assert defaults, "keymap defaults catalog is empty — the gate would be vacuous"
    clashes = reserved_clashes(defaults, discover_claims())
    assert not clashes, (
        "the action map takes a key the canvas/input layer also handles — the "
        "action wins by construction, so that fixed key stops working:\n"
        + "\n".join(f"  {clash.describe()}" for clash in clashes)
    )


def test_the_discovery_is_not_vacuous():
    """A scanner refactor that silently finds nothing must fail, not pass."""
    claims = discover_claims()
    assert len(claims) > 100, f"only {len(claims)} claim sites discovered"
    chords = {claim.chord for claim in claims}
    # The magnifier movement family and the shared pan keys are the floor: if
    # these disappear the scan stopped working, not the app stopped handling
    # them.
    assert {"W", "A", "S", "D", "Q", "E", "Left"} <= chords, sorted(chords)


def test_scan_domain_excludes_key_synthesizers():
    """Tests, devtools and the MCP name table synthesize keys — not claims."""
    for claim in discover_claims():
        assert claim.path.startswith("src/"), claim.path
        assert not claim.path.startswith(("src/devtools/", "src/core/control/")), (
            claim.path
        )
        assert "/tests/" not in claim.path, claim.path


# -- the class the old invariant could not see -------------------------------


def test_one_chord_one_action_cannot_see_a_fixed_key_collision():
    """A chord can be perfectly unique *and* still steal a canvas key."""
    defaults = {"image_compare.divider.visible": ("D", "image_compare")}
    assert duplicate_bindings(defaults, tab="image_compare") == {}
    clashes = reserved_clashes(defaults, discover_claims())
    assert [clash.action_id for clash in clashes] == ["image_compare.divider.visible"]
    assert clashes[0].chord == "D"
    # The tab's own feature code is what needs the key — that is the site the
    # failure message must name (shared event code routes it, it does not own
    # the meaning).
    assert {claim.scope for claim in clashes[0].claims} == {"image_compare"}
    assert all(
        claim.path.startswith("src/tabs/image_compare/")
        for claim in clashes[0].claims
    )


# -- scope semantics ---------------------------------------------------------


def _claim(chord: str, scope: str | None, path: str = "src/probe.py") -> KeyClaim:
    return KeyClaim(chord, path, 1, scope, "key-literal")


def test_a_tab_claim_only_meets_that_tabs_actions():
    defaults = {
        "image_compare.divider.visible": ("D", "image_compare"),
        "multi_compare.divider.visible": ("D", "multi_compare"),
    }
    claims = (_claim("D", "image_compare"),)
    clashes = reserved_clashes(defaults, claims)
    assert [(clash.tab, clash.action_id) for clash in clashes] == [
        ("image_compare", "image_compare.divider.visible")
    ]


def test_a_platform_action_is_checked_against_every_tab():
    """Platform actions are installed in every window scope (binder resync)."""
    defaults = {"platform.settings": ("D", None)}
    claims = (_claim("D", "image_gallery"),)
    clashes = reserved_clashes(defaults, claims)
    assert [clash.tab for clash in clashes] == [None]
    assert clashes[0].action_id == "platform.settings"


def test_modifier_chords_never_meet_a_bare_key_claim():
    defaults = {"image_compare.swap": ("Ctrl+D", "image_compare")}
    assert reserved_clashes(defaults, (_claim("D", "image_compare"),)) == ()


def test_an_unbound_action_claims_nothing():
    defaults = {"image_compare.divider.visible": ("D", "image_compare")}
    claims = (_claim("D", "image_compare"),)
    assert reserved_clashes(defaults, claims, {"image_compare.divider.visible": ""}) == ()


def test_an_override_onto_a_fixed_key_is_caught():
    """Settings can produce the same defect with a valid override."""
    defaults = {"image_compare.swap": ("X", "image_compare")}
    claims = (_claim("D", "image_compare"),)
    clashes = reserved_clashes(defaults, claims, {"image_compare.swap": "D"})
    assert [clash.chord for clash in clashes] == ["D"]


# -- discovery primitives ---------------------------------------------------


@pytest.mark.parametrize(
    ("attribute", "chord"),
    [
        ("Key_D", "D"),
        ("Key_Left", "Left"),
        ("Key_Space", "Space"),
        ("Key_Plus", "+"),
        ("Key_F5", "F5"),
        ("Key_F35", "F35"),
        ("Key_SomeUnknownThing", None),
        ("Key_F99", None),
    ],
)
def test_portable_key_names(attribute, chord):
    assert portable_key(attribute) == chord


@pytest.mark.parametrize(
    ("path", "scope"),
    [
        ("src/tabs/image_compare/canvas/widget.py", "image_compare"),
        ("src/tabs/image_gallery/widget.py", "image_gallery"),
        ("src/events/app_event/keyboard.py", None),
        ("src/ui/actions/binder.py", None),
    ],
)
def test_scope_attribution_is_structural(path, scope):
    assert scope_of(path) == scope
