"""Resolve effective action shortcuts (defaults + user overrides)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from core.actions.types import ActionDescriptor

try:
    from PySide6.QtGui import QKeySequence
except Exception:  # pragma: no cover - import-time without Qt in tiny unit tests
    QKeySequence = None  # type: ignore[misc, assignment]


def normalize_sequence(sequence: str | None) -> str:
    """Return PortableText form, or empty string if unbound / invalid."""
    text = (sequence or "").strip()
    if not text:
        return ""
    if QKeySequence is None:
        return text
    key = QKeySequence(text)
    if key.isEmpty():
        return ""
    return key.toString(QKeySequence.SequenceFormat.PortableText)


def effective_shortcut(
    action: ActionDescriptor,
    overrides: Mapping[str, str] | None,
) -> str | None:
    """Resolve display/runtime chord.

    - key missing in overrides → descriptor default
    - key present with empty string → unbound
    - key present with value → that sequence (normalized)
    """
    overrides = overrides or {}
    if action.action_id in overrides:
        normalized = normalize_sequence(overrides[action.action_id])
        return normalized or None
    default = normalize_sequence(action.shortcut)
    return default or None


def effective_shortcut_for_id(
    action_id: str,
    *,
    default: str | None,
    overrides: Mapping[str, str] | None,
) -> str | None:
    overrides = overrides or {}
    if action_id in overrides:
        normalized = normalize_sequence(overrides[action_id])
        return normalized or None
    normalized = normalize_sequence(default)
    return normalized or None


def chord_conflicts(
    bindings: Mapping[str, str | None],
) -> dict[str, list[str]]:
    """Map normalized chord → action_ids that share it (len > 1 only)."""
    by_chord: dict[str, list[str]] = {}
    for action_id, sequence in bindings.items():
        chord = normalize_sequence(sequence)
        if not chord:
            continue
        by_chord.setdefault(chord, []).append(action_id)
    return {chord: ids for chord, ids in by_chord.items() if len(ids) > 1}


def _binding_priority(action_id: str, *, owner_tab: str | None) -> tuple:
    return binding_priority(action_id, owner_tab=owner_tab)


def binding_priority(action_id: str, *, owner_tab: str | None) -> tuple:
    """Shared chord-winner order for binder, keymap, and Settings display.

    Lower sorts first and wins chord conflicts (platform before tab).
    Single source of truth — :mod:`ui.actions.binder` and
    :func:`exclusive_overrides` must both rank through this function so the
    live shortcut, the stored overrides, and the Settings page agree.
    """
    if action_id == "platform.settings":
        return (0, "")
    if owner_tab is None:
        return (1, action_id)
    return (2, f"{owner_tab}:{action_id}")


# Alias chords that live outside the one-shortcut-per-action registry row
# (e.g. Ctrl+Y as a second redo chord next to Ctrl+Shift+Z). Aliases compete
# in conflict detection exactly like primary chords so stealing/allocation
# UIs and the live binder see the same occupancy.
ACTION_ALIAS_CHORDS: dict[str, tuple[str, ...]] = {
    "platform.redo": ("Ctrl+Y",),
}


def aliases_for(action_id: str) -> tuple[str, ...]:
    """Normalized alias chords registered for ``action_id`` (possibly empty)."""
    return tuple(
        chord
        for chord in (
            normalize_sequence(raw)
            for raw in ACTION_ALIAS_CHORDS.get(action_id, ())
        )
        if chord
    )


def all_effective_chords(
    action_id: str,
    *,
    default: str | None,
    overrides: Mapping[str, str] | None,
) -> tuple[str, ...]:
    """Primary effective chord plus registered aliases (deduped, in order)."""
    primary = effective_shortcut_for_id(
        action_id, default=default, overrides=overrides
    )
    chords = [primary] if primary else []
    for alias in aliases_for(action_id):
        if alias not in chords:
            chords.append(alias)
    return tuple(chords)


def shared_scope(owner_a: str | None, owner_b: str | None) -> bool:
    """True when two actions can be installed in one window scope.

    Mirrors ``ActionShortcutBinder.resync``: the binder installs platform
    actions (``owner_tab is None``) plus the ACTIVE tab's actions, so a
    platform action competes with every tab and two different tabs never
    coexist. A chord shared by two tab owners is therefore NOT a conflict —
    each tab binds it while it is active (two tabs may ship the same toggle
    chord). Treating that share as a conflict used to persist a dead ``""``
    override against the alphabetically later tab, permanently.
    """
    return owner_a is None or owner_b is None or owner_a == owner_b


def exclusive_overrides(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None,
    *,
    prefer_action_id: str | None = None,
) -> dict[str, str]:
    """Return overrides where each chord is owned by at most one action.

    ``defaults`` maps ``action_id → (default_shortcut, owner_tab)``.
    Conflicting actions other than the winner get an explicit unbound override
    (``""``) so their defaults cannot reclaim the chord.

    Conflicts are resolved in the binder's scope (:func:`shared_scope`): a
    platform holder wins the chord everywhere, a tab holder wins it inside its
    own tab, and a chord shared by two different tabs belongs to both.
    """
    result = {
        key: normalize_sequence(value) if value else ""
        for key, value in (overrides or {}).items()
    }
    # action_id → (primary chord, alias chords). Primaries outrank aliases:
    # an alias never steals a chord from a primary holder — it simply stays
    # uninstalled while occupied. Alias collisions therefore never mutate
    # overrides; only primary-vs-primary losers are explicitly unbound.
    primaries: dict[str, str] = {}
    for action_id, (default, _owner) in defaults.items():
        primary = effective_shortcut_for_id(
            action_id, default=default, overrides=result
        )
        if primary:
            primaries[action_id] = primary

    by_chord: dict[str, list[str]] = {}
    for action_id, primary in primaries.items():
        by_chord.setdefault(primary, []).append(action_id)

    for chord, action_ids in by_chord.items():
        if len(action_ids) < 2:
            continue
        ranked = sorted(
            action_ids,
            key=lambda aid: (
                0 if prefer_action_id and aid == prefer_action_id else 1,
                binding_priority(aid, owner_tab=defaults[aid][1]),
            ),
        )
        if prefer_action_id and ranked[0] == prefer_action_id:
            # A deliberate steal (Settings capture) outranks every scope: the
            # action the user just typed a chord for wins it everywhere.
            losers = ranked[1:]
        else:
            losers = _scope_losers(ranked, defaults)
        for action_id in losers:
            # Explicitly unbind losers so defaults cannot keep the chord.
            result[action_id] = ""
    return result


def _scope_losers(
    ranked: list[str],
    defaults: Mapping[str, tuple[str | None, str | None]],
) -> list[str]:
    """Holders that lose ``chord`` inside the binder's scope (``ranked[0]`` wins)."""
    platform_holders = [aid for aid in ranked if defaults[aid][1] is None]
    if platform_holders:
        # Platform actions are installed in every tab scope, so their winner
        # outranks every tab holder. This is the pre-scope behaviour and it is
        # deliberate: a platform chord keeps winning while any tab is active.
        return [aid for aid in ranked if aid != platform_holders[0]]
    losers: list[str] = []
    claimed_owners: set[str | None] = set()
    for action_id in ranked:
        owner_tab = defaults[action_id][1]
        if owner_tab in claimed_owners:
            losers.append(action_id)
        else:
            claimed_owners.add(owner_tab)
    return losers


def repair_legacy_cross_tab_unbounds(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    """Drop only the ``""`` overrides the old all-tabs ranking poisoned.

    Profiles written before the scope fix carry empty overrides for the loser
    of a chord two tabs both ship (the divider toggle both tabs bind to one
    key). The binder never saw that conflict — it installs one tab at a time —
    so the override was pure damage: the action was dead even in its own tab.

    An empty override is kept when it is a real user choice: the action is the
    default winner of its own chord, has no chord at all, or shares the chord
    with another action of the same scope (a genuine same-tab conflict).
    Pure: the caller's mapping is never mutated, a new dict is returned.
    """
    repaired = dict(overrides or {})
    if not repaired:
        return repaired

    default_winners = resolve_chord_winners(defaults, {})
    holders_by_chord: dict[str, list[str]] = {}
    for action_id, (default, _owner) in defaults.items():
        chord = normalize_sequence(default)
        if chord:
            holders_by_chord.setdefault(chord, []).append(action_id)

    for action_id, value in tuple(repaired.items()):
        if normalize_sequence(value) or action_id not in defaults:
            continue
        default, owner_tab = defaults[action_id]
        chord = normalize_sequence(default)
        if not chord:
            continue
        same_scope_rival = any(
            other != action_id and shared_scope(owner_tab, defaults[other][1])
            for other in holders_by_chord.get(chord, ())
        )
        if same_scope_rival:
            continue
        winner = default_winners.get(chord)
        if winner is None or winner == action_id:
            continue
        if shared_scope(owner_tab, defaults[winner][1]):
            continue
        del repaired[action_id]
    return repaired


def resolve_chord_winners(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None,
    *,
    prefer_action_id: str | None = None,
) -> dict[str, str]:
    """Map every occupied chord → winning ``action_id`` (primaries + aliases).

    Primary holders outrank alias holders on the same chord; ties break by
    :func:`binding_priority` (``prefer_action_id`` first). Shared by the live
    binder and conflict UIs so all three sides agree on the winner.
    """
    primaries: dict[str, str] = {}
    for action_id, (default, _owner) in defaults.items():
        primary = effective_shortcut_for_id(
            action_id, default=default, overrides=overrides
        )
        if primary:
            primaries[action_id] = primary

    def _rank(aid: str) -> tuple:
        return (
            0 if prefer_action_id and aid == prefer_action_id else 1,
            binding_priority(aid, owner_tab=defaults[aid][1]),
        )

    winners: dict[str, str] = {}
    # Primaries claim first, in rank order.
    for action_id in sorted(primaries, key=_rank):
        winners.setdefault(primaries[action_id], action_id)
    # Aliases fill only chords no primary holds.
    alias_holders: dict[str, list[str]] = {}
    for action_id in defaults:
        for alias in aliases_for(action_id):
            alias_holders.setdefault(alias, []).append(action_id)
    for chord, action_ids in alias_holders.items():
        if chord in winners:
            continue
        winners[chord] = sorted(action_ids, key=_rank)[0]
    return winners


def steal_chord_in_overrides(
    *,
    action_id: str,
    chord: str | None,
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: dict[str, str],
) -> dict[str, str]:
    """Assign ``chord`` to ``action_id`` and unbind every other owner of it."""
    normalized = normalize_sequence(chord)
    default = defaults.get(action_id, (None, None))[0]
    default_norm = normalize_sequence(default)
    next_overrides = dict(overrides)
    if not normalized:
        next_overrides[action_id] = ""
    elif normalized == default_norm:
        next_overrides.pop(action_id, None)
    else:
        next_overrides[action_id] = normalized
    return exclusive_overrides(
        defaults, next_overrides, prefer_action_id=action_id
    )


@dataclass(frozen=True, slots=True)
class KeymapDefaultEntry:
    """Metadata-only catalog row for Settings (no run / target)."""

    action_id: str
    label_key: str
    default_shortcut: str | None = None
    owner_tab: str | None = None
    breadcrumb: tuple[str, ...] = ()
    description_key: str | None = None
    # Same semantics as ActionDescriptor — mode names / aliases for the
    # Settings → Keyboard filter (e.g. SSIM → Difference Mode cycle).
    search_keys: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()


def keymap_entry_rank(
    entry: KeymapDefaultEntry,
    query: str,
    *,
    extra_search_terms: tuple[str, ...] = (),
) -> int | None:
    """Find Action–style rank for a keyboard binder row, or ``None`` if no match.

    Searches the same fields as the command palette (id, label, description,
    breadcrumb, chord, ``search_keys`` / ``search_terms``) plus any extras
    (group title, effective chord). Uncached so extras never pollute the
    palette haystack cache.
    """
    from ui.actions.registry import (
        _normalize,
        action_query_rank,
        compute_action_haystacks,
    )

    needle = _normalize((query or "").strip())
    if not needle:
        return 0
    haystacks = compute_action_haystacks(
        action_id=entry.action_id,
        label_key=entry.label_key,
        description_key=entry.description_key,
        breadcrumb=entry.breadcrumb,
        shortcut=entry.default_shortcut,
        search_keys=entry.search_keys,
        search_terms=entry.search_terms + tuple(
            term for term in extra_search_terms if term
        ),
    )
    return action_query_rank(needle, haystacks=haystacks)


class KeymapDefaultsRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, KeymapDefaultEntry] = {}

    def register(self, entry: KeymapDefaultEntry) -> None:
        if not entry.action_id:
            raise ValueError("KeymapDefaultEntry.action_id must be non-empty")
        self._by_id[entry.action_id] = entry

    def all_entries(self) -> list[KeymapDefaultEntry]:
        return sorted(
            self._by_id.values(),
            key=lambda e: (e.owner_tab or "", e.action_id),
        )

    def clear(self) -> None:
        self._by_id.clear()

