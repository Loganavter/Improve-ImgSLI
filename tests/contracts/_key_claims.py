"""Key-claim discovery for the canvas-key reservation gate.

The gate's question: does a *remappable action chord* take a key that some
other part of the input layer also handles? Neither side of that comparison may
be a hand-written list:

* the action side is the shipped catalog (``collect_keymap_defaults``);
* the input side is **discovered from source** here — every ``Qt.Key.Key_*``
  literal and every modifier-less ``QShortcut`` / ``QKeySequence`` /
  ``setShortcut`` string in the interception surface is a claim on that key.

Attribution is structural (file path), never declarative: a claim in
``src/tabs/<tab>/…`` holds for that tab's window scope only; every other claim
belongs to shared input code. Scope semantics follow the binder
(:func:`ui.actions.keymap.shared_scope`, ``ActionShortcutBinder.resync``), with
one addition — a *platform* action is installed in every tab's window scope, so
it is compared against every tab's claims, while a tab action only meets its own
tab's claims.

Why this exists (2026-10-26): ``ui.actions.keymap_uniqueness`` compares the
catalog with itself and therefore cannot see a chord that takes a key the
canvas input layer needs. ``D`` was the divider-visibility chord in Image
Compare and also the magnifier's "pan right", and the keybinding audit could not
report it: the loupe keys are a fixed family scattered across the event layer
and the magnifier feature, not catalog rows. The visible result was a
documented, non-remappable canvas key silently taken by a remappable action.

Known blind spots, stated so the gate is not trusted beyond its reach:

* modifiers written in the same boolean expression are not analysed — a key
  literal claims the BARE key, so the ``Ctrl+V`` paste guard also reserves
  ``V``. That is conservative (it can forbid a chord that would really be free)
  and never the unsafe direction.
* claims expressed as integers, ``QKeySequence.StandardKey`` values or
  modifier-composed chord literals are out of scope: those are window-local by
  nature (a dialog's ``Ctrl+Z`` must not fight the platform undo) and belong to
  the action map's own uniqueness check.
* the scan skips ``tests/`` trees, ``src/devtools/`` and ``src/core/control/``:
  those *synthesize* keys (test doubles, capture tooling, the MCP
  ``press_keys`` name table), they do not intercept a user's keys.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from tests.contracts._framework import SRC, parse, rel
from ui.actions.keymap import all_effective_chords, normalize_sequence

#: ``Qt.Key`` names whose portable chord text is not just the stripped suffix.
_NAMED_KEYS = {
    "Key_Left": "Left",
    "Key_Right": "Right",
    "Key_Up": "Up",
    "Key_Down": "Down",
    "Key_Space": "Space",
    "Key_Escape": "Esc",
    "Key_Return": "Return",
    "Key_Enter": "Enter",
    "Key_Tab": "Tab",
    "Key_Backtab": "Backtab",
    "Key_Backspace": "Backspace",
    "Key_Delete": "Delete",
    "Key_Insert": "Insert",
    "Key_Home": "Home",
    "Key_End": "End",
    "Key_PageUp": "PgUp",
    "Key_PageDown": "PgDown",
    "Key_Plus": "+",
    "Key_Minus": "-",
    "Key_Equal": "=",
    "Key_Comma": ",",
    "Key_Period": ".",
    "Key_Slash": "/",
    "Key_Backslash": "\\",
    "Key_Semicolon": ";",
    "Key_Apostrophe": "'",
    "Key_BracketLeft": "[",
    "Key_BracketRight": "]",
    "Key_QuoteLeft": "`",
    "Key_Menu": "Menu",
    "Key_Pause": "Pause",
    "Key_Print": "Print",
}

#: Call names whose first string argument is a chord ("Ctrl+S", "D", "Left").
_CHORD_CALLS = frozenset({"QShortcut", "QKeySequence", "setShortcut"})

#: Directories that synthesize keys instead of intercepting them.
_SKIPPED_PREFIXES = ("src/devtools/", "src/core/control/")


@dataclass(frozen=True, slots=True)
class KeyClaim:
    """One place in the input layer that handles a chord.

    ``chord`` is portable text (``"D"``, ``"Left"``, ``"Space"``, ``"+"``).
    ``scope`` is a tab name for ``src/tabs/<tab>/…`` and ``None`` for shared
    input code, which is how the claim is compared (see the module docstring).
    """

    chord: str
    path: str
    line: int
    scope: str | None
    kind: str  # "key-literal" | "chord-literal"


@dataclass(frozen=True, slots=True)
class ReservedClash:
    """A catalog chord that takes a key a live input handler also handles."""

    chord: str
    tab: str | None
    action_id: str
    claims: tuple[KeyClaim, ...]

    def describe(self) -> str:
        scope = f"tab {self.tab!r}" if self.tab else "every tab (platform action)"
        sites = ", ".join(f"{c.path}:{c.line}" for c in self.claims)
        return (
            f"{self.chord!r} is claimed by {self.action_id} in {scope} and also "
            f"handled by the input layer: {sites}"
        )


def portable_key(attribute: str) -> str | None:
    """Portable chord text for a ``Qt.Key.Key_*`` attribute name, or None."""
    if not attribute.startswith("Key_"):
        return None
    if attribute in _NAMED_KEYS:
        return _NAMED_KEYS[attribute]
    tail = attribute[4:]
    if len(tail) == 1 and tail.isalnum():
        return tail.upper()
    if tail.startswith("F") and tail[1:].isdigit():
        number = int(tail[1:])
        if 1 <= number <= 35:
            return f"F{number}"
    return None


def scope_of(path: str) -> str | None:
    """Tab that owns ``path`` (``None`` = shared input code)."""
    parts = path.split("/")
    if len(parts) > 3 and parts[:2] == ["src", "tabs"]:
        return parts[2]
    return None


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _claim_sites(path: Path, tree: ast.Module, scope: str | None) -> list[KeyClaim]:
    where = rel(path)
    claims: list[KeyClaim] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chord = portable_key(node.attr)
            if chord is not None:
                claims.append(KeyClaim(chord, where, node.lineno, scope, "key-literal"))
        elif isinstance(node, ast.Call) and _call_name(node.func) in _CHORD_CALLS:
            if not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            literal = first.value.strip()
            # Modifier-composed chords are window-local by nature (a dialog's
            # Ctrl+Z is not the platform undo) — out of scope, see docstring.
            if not literal or "+" in literal:
                continue
            claims.append(
                KeyClaim(
                    normalize_sequence(literal) or literal,
                    where,
                    node.lineno,
                    scope,
                    "chord-literal",
                )
            )
    return claims


def discover_claims(root: Path | None = None) -> tuple[KeyClaim, ...]:
    """Every key/chord claim in the interception surface, sorted for stability."""
    base = root or SRC
    claims: list[KeyClaim] = []
    for path in sorted(base.rglob("*.py")):
        relative = rel(path)
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        if relative.startswith(_SKIPPED_PREFIXES):
            continue
        tree = parse(path)
        if tree is None:
            continue
        claims.extend(_claim_sites(path, tree, scope_of(relative)))
    return tuple(sorted(claims, key=lambda c: (c.chord, c.path, c.line)))


def reserved_clashes(
    defaults: dict[str, tuple[str | None, str | None]],
    claims: tuple[KeyClaim, ...],
    overrides: dict[str, str] | None = None,
) -> tuple[ReservedClash, ...]:
    """Catalog chords that take a key the input layer also handles.

    A tab action is compared with **that tab's** claims (plus nothing else: an
    action is only ever installed while its tab is active, and shared code that
    matters to that tab also has a claim inside it). A platform action is
    installed in every tab scope, so it is compared with every tab's claims.

    Modifier chords (``Ctrl+S``) cannot be taken by a bare key claim and are
    skipped; an explicitly unbound action (``""`` override) claims nothing.
    """
    by_chord: dict[str, list[KeyClaim]] = {}
    for claim in claims:
        by_chord.setdefault(claim.chord, []).append(claim)

    clashes: list[ReservedClash] = []
    for action_id, (default, owner_tab) in defaults.items():
        for chord in all_effective_chords(
            action_id, default=default, overrides=overrides
        ):
            if not chord or "+" in chord:
                continue
            if owner_tab is None:
                hits = tuple(by_chord.get(chord, ()))
            else:
                hits = tuple(
                    claim
                    for claim in by_chord.get(chord, ())
                    if claim.scope == owner_tab
                )
            if hits:
                clashes.append(ReservedClash(chord, owner_tab, action_id, hits))
    return tuple(clashes)


def catalog_defaults() -> dict[str, tuple[str | None, str | None]]:
    """The shipped catalog as Settings sees it (metadata, no live widgets)."""
    from plugins.settings.keymap_defaults import collect_keymap_defaults

    return {
        entry.action_id: (entry.default_shortcut, entry.owner_tab)
        for entry in collect_keymap_defaults().all_entries()
    }


__all__ = [
    "KeyClaim",
    "ReservedClash",
    "catalog_defaults",
    "discover_claims",
    "portable_key",
    "reserved_clashes",
    "scope_of",
]
