"""Settings-scalar registry contract — one record, five touch points, no drift.

Dogma source: P2 redux-action-shape stage 2 (settings-scalar registry).

Every persisted settings scalar must link all five places it touches,
as recorded in ``core.state_management.settings_scalars.SETTINGS_SCALARS``:

1. ``SettingsState`` field (``core/store_settings.py``),
2. ``ActionType`` member (``core/state_management/action_base.py``),
3. ``Set*Action`` dataclass with the payload field and a ``type`` default
   wired to that ``ActionType`` member (``settings_actions.py``),
4. ``SettingsReducer.reduce`` ``isinstance`` branch (``reducers.py``),
5. typed load + save pair in ``SettingsManager`` (``manager.py``;
   ``keyboard_overrides`` persists through its dedicated JSON pair).

Scans (AST, no runtime). Adding/removing a scalar anywhere without
updating the registry and the other four places fails here first.
"""

from __future__ import annotations

import ast

from core.state_management.settings_scalars import SETTINGS_SCALARS
from tests.contracts._framework import (
    MANAGER_PATH,
    SRC,
    STORE_SETTINGS_PATH,
    _method_node,
    read,
    settings_load_pairs,
    settings_save_keys,
    store_settings_field_names,
)

_ACTIONS = ast.parse(read(SRC / "core" / "state_management" / "settings_actions.py"))
_BASE = ast.parse(read(SRC / "core" / "state_management" / "action_base.py"))
_REDUCERS = ast.parse(read(SRC / "core" / "state_management" / "reducers.py"))
_MANAGER = ast.parse(read(MANAGER_PATH))
_STORE = ast.parse(read(STORE_SETTINGS_PATH))

_STORE_FIELDS = set(store_settings_field_names(_STORE))
_LOAD_KEYS = {p["key"] for p in settings_load_pairs(_MANAGER)}
_SAVE_KEYS = set(settings_save_keys(_MANAGER))


def _action_type_members() -> set[str]:
    for node in ast.walk(_BASE):
        if isinstance(node, ast.ClassDef) and node.name == "ActionType":
            members = set()
            for t in node.body:
                if not isinstance(t, ast.Assign):
                    continue
                v = t.value
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    members.add(v.value)
            return members
    return set()


def _action_classes() -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in ast.walk(_ACTIONS)
        if isinstance(node, ast.ClassDef)
    }


def _reducer_isinstance_targets() -> set[str]:
    targets = set()
    for node in ast.walk(_REDUCERS):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) == 2
            and isinstance(node.args[1], ast.Name)
        ):
            targets.add(node.args[1].id)
    return targets


_ACTION_TYPES = _action_type_members()
_ACTION_CLASSES = _action_classes()
_REDUCER_TARGETS = _reducer_isinstance_targets()


def _has_dataclass_field(cls: ast.ClassDef, name: str) -> bool:
    return any(
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == name
        for node in cls.body
    )


def _type_default_refs_action_type(cls: ast.ClassDef, member: str) -> bool:
    for node in cls.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "type"
            and node.value is not None
        ):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Attribute) and sub.attr == member:
                    return True
    return False


def _payload_mentions(cls: ast.ClassDef, field_name: str) -> bool:
    for node in ast.walk(cls):
        if isinstance(node, ast.FunctionDef) and node.name == "get_payload":
            src = ast.dump(node)
            if field_name in src:
                return True
    return False


def test_registry_covers_five_touch_points():
    """Every SETTINGS_SCALARS record resolves at all five touch points."""
    for spec in SETTINGS_SCALARS:
        assert spec.setting_field in _STORE_FIELDS, (
            f"{spec.key}: SettingsState has no field {spec.setting_field!r}"
        )
        assert spec.action_type in _ACTION_TYPES, (
            f"{spec.key}: ActionType has no member {spec.action_type!r}"
        )
        cls = _ACTION_CLASSES.get(spec.action_class)
        assert cls is not None, f"{spec.key}: no action class {spec.action_class!r}"
        assert _has_dataclass_field(cls, spec.action_field), (
            f"{spec.key}: {spec.action_class} has no dataclass field {spec.action_field!r}"
        )
        assert _type_default_refs_action_type(cls, spec.action_type), (
            f"{spec.key}: {spec.action_class}.type default is not wired to {spec.action_type}"
        )
        assert _payload_mentions(cls, spec.action_field), (
            f"{spec.key}: {spec.action_class}.get_payload ignores {spec.action_field!r}"
        )
        assert spec.action_class in _REDUCER_TARGETS, (
            f"{spec.key}: SettingsReducer has no isinstance branch for {spec.action_class}"
        )
        if spec.key == "keyboard_overrides":
            load_fn = _method_node(_MANAGER, "SettingsManager", "_load_keyboard_overrides")
            save_fn = _method_node(_MANAGER, "SettingsManager", "_save_keyboard_overrides")
            assert load_fn is not None and save_fn is not None, (
                f"{spec.key}: dedicated JSON load/save pair missing in manager"
            )
        else:
            assert spec.key in _LOAD_KEYS, f"{spec.key}: no typed _get_setting load in manager"
            assert spec.key in _SAVE_KEYS, f"{spec.key}: no _save_setting save in manager"


def test_registry_has_no_duplicate_keys():
    """Scalar keys are unique (window geometry shares one action, not one key)."""
    keys = [s.key for s in SETTINGS_SCALARS]
    assert len(keys) == len(set(keys)), "duplicate scalar keys in SETTINGS_SCALARS"
