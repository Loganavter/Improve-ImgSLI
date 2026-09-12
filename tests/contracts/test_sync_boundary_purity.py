"""Sync-boundary purity: no widget↔side-slot channel bypassing the Store.

Covers ``docs/dev/CONTRACTS.md`` / ``docs/dev/STORE.md`` invariant 2 (all
state changes go through the Dispatcher): ``use_cases/persistence.py``
reads widget state (``btn.isChecked()`` / ``edit.text()``) into the
``image_compare.state`` side slot and writes it back via
``btn.setChecked()`` / ``edit.setText()``. That channel round-trips UI
state past the Store — no action, no reducer, no subscribers — so the
canonical ``render_config`` copy and the side-slot copy desync (e.g.
``show_file_names`` vs ``render_config.include_file_names_in_saved``).

Part (a) scans the persistence boundary modules
(``use_cases/persistence.py``, ``session_persistence.py``, ``tab.py``)
for widget-state IO calls — reads ``isChecked/text/value/currentIndex/
currentText/checkState/isVisible/toPlainText`` and writes
``setChecked/setText/setValue/setCurrentIndex/setPlainText`` — both as
direct ``Call(func=Attribute)`` and via the ``getattr(widget, name,
...)()`` indirection used in ``snapshot_into``. Camera host helpers
(``set_zoom_level`` / ``set_pan_offsets`` / ``get_zoom_level`` / ...) are
not widget IO and are exempt.

Part (b) pins the known duplicate source: ``ImageCompareState`` fields
parsed from ``models.py``; ``show_file_names`` duplicates
``render_config.include_file_names_in_saved`` and must stay listed in
``PENDING_DUPLICATES`` until the slot is removed. A token-overlap
heuristic against the live ``RenderConfig`` fields fails on any *other*
model field that smells like ``render_config`` semantics unless it is
explicitly allowlisted. ``edit_name_1/2`` ownership is undecided and
deliberately not encoded (supervisor follow-up).

RATCHET: both ``PENDING_MIGRATION`` and ``PENDING_DUPLICATES`` fail when
stale (site migrated but exemption left behind), forcing cleanup at
integration.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ._framework import SRC, read

BOUNDARY_MODULES: tuple[str, ...] = (
    "src/tabs/image_compare/use_cases/persistence.py",
    "src/tabs/image_compare/session_persistence.py",
    "src/tabs/image_compare/tab.py",
)

READ_ATTRS: frozenset[str] = frozenset(
    {
        "isChecked",
        "text",
        "value",
        "currentIndex",
        "currentText",
        "checkState",
        "isVisible",
        "toPlainText",
    }
)

WRITE_ATTRS: frozenset[str] = frozenset(
    {
        "setChecked",
        "setText",
        "setValue",
        "setCurrentIndex",
        "setPlainText",
    }
)

IO_ATTRS: frozenset[str] = READ_ATTRS | WRITE_ATTRS

CAMERA_HELPER_PREFIXES: tuple[str, ...] = (
    "set_zoom_level",
    "set_pan_offsets",
    "get_zoom_level",
    "get_pan_offset",
)

# Widget-state IO on the sync boundary — exact (file, lineno, attr).
# The persistence.py snapshot/restore and tab.py apply_host_session_mode
# sites were migrated Store-first; only a benign UI-internal read remains.
# Delete the entry (not the scan) once it migrates too.
PENDING_MIGRATION: frozenset[tuple[str, int, str]] = frozenset(
    {
        # tab.py UI-internal read (widget→widget visibility, no slot
        # involved) — tolerated pending the boundary audit.
        ("src/tabs/image_compare/tab.py", 435, "isVisible"),
    }
)

MODELS_PATH = SRC / "tabs" / "image_compare" / "models.py"
STORE_VIEWPORT_PATH = SRC / "core" / "store_viewport.py"

# Model field -> canonical render_config path it duplicates.
KNOWN_DUPLICATES: dict[str, str] = {
    "show_file_names": "render_config.include_file_names_in_saved",
}

# Duplicate sources tolerated until the side slot is removed.
# (show_file_names was removed from ImageCompareState with the Store-first
# persistence migration; the set stays as the ratchet for regressions.)
PENDING_DUPLICATES: frozenset[str] = frozenset()

# Other model fields overlapping render_config semantics, explicitly
# reviewed. zoom/pan_x/pan_y are camera (host-owned, not render_config);
# the edit_name_1/2 caption fields were removed (captions come from
# DocumentModel display names).
ALLOWED_OVERLAPS: dict[str, str] = {}


def _is_camera_helper(attr: str) -> bool:
    return attr.startswith(CAMERA_HELPER_PREFIXES)


def _widget_state_io() -> set[tuple[str, int, str]]:
    """(file, lineno, attr) widget-state IO hits in the boundary modules."""
    found: set[tuple[str, int, str]] = set()
    root = SRC.parent
    for rel_path in BOUNDARY_MODULES:
        path = root / rel_path
        if not path.is_file():
            continue
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in IO_ATTRS:
                if _is_camera_helper(func.attr):
                    continue
                found.add((rel_path, node.lineno, func.attr))
            elif (
                isinstance(func, ast.Call)
                and isinstance(func.func, ast.Name)
                and func.func.id == "getattr"
                and len(func.args) >= 2
                and isinstance(func.args[1], ast.Constant)
                and isinstance(func.args[1].value, str)
                and func.args[1].value in IO_ATTRS
            ):
                # getattr(widget, "isChecked", ...)() indirection.
                if _is_camera_helper(func.args[1].value):
                    continue
                found.add((rel_path, node.lineno, func.args[1].value))
    return found


def _dataclass_fields(path: Path, class_name: str) -> list[str]:
    try:
        tree = ast.parse(read(path))
    except (OSError, SyntaxError):
        return []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields: list[str] = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append(item.target.id)
            return fields
    return []


def _tokens(name: str) -> set[str]:
    return set(t for t in re.split(r"_+", name.lower()) if t and not t.isdigit())


def _render_config_overlap_candidates() -> set[str]:
    """Model fields sharing ≥2 name tokens with a RenderConfig field."""
    model_fields = _dataclass_fields(MODELS_PATH, "ImageCompareState")
    config_fields = _dataclass_fields(STORE_VIEWPORT_PATH, "RenderConfig")
    candidates: set[str] = set()
    for field in model_fields:
        if field in ("edit_name_1", "edit_name_2"):
            continue  # ownership undecided — supervisor follow-up, never flagged
        field_toks = _tokens(re.sub(r"_\d+$", "", field))
        for cfg in config_fields:
            if field_toks & _tokens(cfg) and len(field_toks & _tokens(cfg)) >= 2:
                candidates.add(field)
                break
    return candidates


def test_sync_boundary_no_unlisted_widget_io():
    found = _widget_state_io()
    unexpected = sorted(found - set(PENDING_MIGRATION))
    assert not unexpected, (
        "Widget↔side-slot sync bypassing the Store — route widget state via "
        "store.get_dispatcher().dispatch(Action, scope=...) instead "
        f"({len(unexpected)} hits):\n  "
        + "\n  ".join(f"{p}:{ln} — .{attr}(...)" for p, ln, attr in unexpected)
    )
    stale = sorted(set(PENDING_MIGRATION) - found)
    assert not stale, (
        "Stale PENDING_MIGRATION entries — the site already migrated, "
        f"delete the exemption:\n  "
        + "\n  ".join(f"{p}:{ln} — .{attr}(...)" for p, ln, attr in stale)
    )


def test_no_duplicate_render_sources():
    model_fields = _dataclass_fields(MODELS_PATH, "ImageCompareState")
    assert model_fields, f"Could not parse ImageCompareState fields from {MODELS_PATH}"
    for field, canonical in KNOWN_DUPLICATES.items():
        if field in model_fields:
            assert field in PENDING_DUPLICATES, (
                f"Duplicate source {field!r} (≈ {canonical}) exists in "
                "ImageCompareState but is not listed in PENDING_DUPLICATES — "
                "remove the duplicate or register the exemption"
            )
    stale = sorted(f for f in PENDING_DUPLICATES if f not in model_fields)
    assert not stale, (
        "Stale PENDING_DUPLICATES entries — the side-slot field is gone, "
        f"delete the exemption: {stale}"
    )
    candidates = _render_config_overlap_candidates()
    unlisted = sorted(candidates - set(PENDING_DUPLICATES) - set(ALLOWED_OVERLAPS))
    assert not unlisted, (
        "ImageCompareState fields overlapping render_config semantics — "
        "remove the duplicate or add to PENDING_DUPLICATES/ALLOWED_OVERLAPS "
        f"with a reason: {unlisted}"
    )
