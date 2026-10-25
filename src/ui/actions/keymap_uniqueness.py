"""One chord, one action per tab — the keybinding invariant (owner 2026-10-25).

Inside a tab a key/chord may belong to exactly ONE action. This module owns
the *audit* of that invariant, split out of ``ui/actions/keymap.py`` (which
stays the resolver) so the resolver keeps its single responsibility and both
files stay under the file-size policy.

Scope model is the binder's (:func:`ui.actions.keymap.shared_scope` /
``ActionShortcutBinder.resync``): platform actions are installed in EVERY tab
scope, so platform-vs-tab on one chord IS a collision; two different tabs may
share a chord because they are never live at the same time.

Two audiences:

* **gates** — :func:`assert_unique_bindings`,
  :func:`assert_unique_bindings_all_scopes` raise
  :class:`BindingCollisionError`. Used by ``tests/contracts/`` on the shipped
  catalog and by the Settings capture path, so a duplicate cannot ship and a
  user cannot produce one.
* **production verification** — :func:`verify_unique_or_log` never raises: it
  names every colliding chord (one ERROR line per collision) and returns them.
  Wired into the binder resync, the Settings page (build/capture/reset) and the
  Settings apply path, because "first chord wins, skip the loser" is a runtime
  degradation, not a licence to store two actions on one chord.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from core.log_names import APP_LOGGER_NAME
from ui.actions.keymap import (
    all_effective_chords,
    effective_shortcut_for_id,
)

logger = logging.getLogger(APP_LOGGER_NAME)


# -- one chord, one action per tab (the binding invariant) --------------------
#
# Owner requirement 2026-10-25: inside one tab a key/chord belongs to exactly
# ONE action. The invariant has to hold for the shipped catalog (defaults), for
# user overrides, and for anything the Settings page can produce. The binder's
# "first wins, skip the loser" behaviour is a runtime degradation, not the
# invariant — it lets a duplicate ship silently and hides which two actions
# collided.
#
# Scope model is the binder's (see ``shared_scope`` / ``ActionShortcutBinder``):
# platform actions (``owner_tab is None``) are installed in EVERY tab scope, so
# platform-vs-tab on one chord IS a collision; two different tabs may share a
# chord because they are never live at the same time.


@dataclass(frozen=True, slots=True)
class BindingCollision:
    """One chord installable by several actions inside a single tab scope."""

    chord: str
    tab: str | None
    action_ids: tuple[str, ...]

    def describe(self) -> str:
        scope = f"tab {self.tab!r}" if self.tab else "platform-only scope"
        return f"{self.chord!r} in {scope}: {', '.join(self.action_ids)}"


class BindingCollisionError(ValueError):
    """Two actions claim one chord in one tab scope — the invariant is broken.

    Raised by the strict validators (:func:`assert_unique_bindings`,
    :func:`assert_unique_bindings_all_scopes`). Production paths call
    :func:`verify_unique_or_log` instead: a broken invariant must be loud, but
    it must not take the app down mid-edit.
    """

    def __init__(self, collisions: Iterable[BindingCollision]) -> None:
        self.collisions = tuple(collisions)
        detail = "; ".join(c.describe() for c in self.collisions)
        super().__init__(
            "duplicate shortcut binding(s) — inside a tab one chord must "
            f"belong to exactly one action: {detail}"
        )


def binding_scopes(
    defaults: Mapping[str, tuple[str | None, str | None]],
) -> tuple[str | None, ...]:
    """Every scope the binder can be resynced into (platform + one per tab)."""
    tabs = sorted({owner for _default, owner in defaults.values() if owner})
    return (None, *tabs)


def scope_bindings(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None = None,
    *,
    tab: str | None = None,
    include_aliases: bool = True,
) -> dict[str, tuple[str, ...]]:
    """Map chord → actions installable together while ``tab`` is active.

    ``tab=None`` is the platform-only scope. Platform actions are in every
    scope (the binder installs them regardless of the active tab); a tab's
    actions appear only in that tab's scope. ``overrides`` resolves like the
    live binder (:func:`effective_shortcut_for_id`), so ``""`` means unbound.
    """
    by_chord: dict[str, list[str]] = {}
    for action_id, (default, owner_tab) in defaults.items():
        if owner_tab is not None and owner_tab != tab:
            continue
        if include_aliases:
            chords = all_effective_chords(
                action_id, default=default, overrides=overrides
            )
        else:
            primary = effective_shortcut_for_id(
                action_id, default=default, overrides=overrides
            )
            chords = (primary,) if primary else ()
        for chord in chords:
            holders = by_chord.setdefault(chord, [])
            if action_id not in holders:
                holders.append(action_id)
    return {chord: tuple(holders) for chord, holders in by_chord.items()}


def duplicate_bindings(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None = None,
    *,
    tab: str | None = None,
    include_aliases: bool = True,
) -> dict[str, tuple[str, ...]]:
    """Only the chords of :func:`scope_bindings` that several actions claim."""
    return {
        chord: holders
        for chord, holders in scope_bindings(
            defaults, overrides, tab=tab, include_aliases=include_aliases
        ).items()
        if len(holders) > 1
    }


def collisions_in_all_scopes(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None = None,
    *,
    include_aliases: bool = True,
) -> tuple[BindingCollision, ...]:
    """Every duplicate binding across every binder scope (empty = clean)."""
    collisions: list[BindingCollision] = []
    for tab in binding_scopes(defaults):
        for chord, holders in duplicate_bindings(
            defaults, overrides, tab=tab, include_aliases=include_aliases
        ).items():
            collisions.append(BindingCollision(chord, tab, holders))
    return tuple(collisions)


def assert_unique_bindings(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None = None,
    *,
    tab: str | None = None,
    include_aliases: bool = True,
) -> None:
    """Strict gate for one scope: raise on any chord with several holders."""
    duplicates = duplicate_bindings(
        defaults, overrides, tab=tab, include_aliases=include_aliases
    )
    if duplicates:
        raise BindingCollisionError(
            BindingCollision(chord, tab, holders)
            for chord, holders in duplicates.items()
        )


def assert_unique_bindings_all_scopes(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None = None,
    *,
    include_aliases: bool = True,
) -> None:
    """Strict gate across every scope (defaults, overrides, Settings output)."""
    collisions = collisions_in_all_scopes(
        defaults, overrides, include_aliases=include_aliases
    )
    if collisions:
        raise BindingCollisionError(collisions)


def verify_unique_or_log(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None = None,
    *,
    source: str,
    include_aliases: bool = True,
) -> tuple[BindingCollision, ...]:
    """Production-side check: loud ERROR per collision, never raises.

    Used right after a binding map is produced (Settings build/edit, apply
    path, binder resync). Reaching this with a non-empty result means either a
    shipped default pairs two actions onto one chord in one tab or a stored
    profile was hand-edited — both are defects that must be named, and neither
    may abort the user's edit.
    """
    collisions = collisions_in_all_scopes(
        defaults, overrides, include_aliases=include_aliases
    )
    for collision in collisions:
        logger.error(
            "Keybinding invariant broken (%s): %s", source, collision.describe()
        )
    return collisions


