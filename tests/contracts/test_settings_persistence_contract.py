"""Settings persistence contract — no implicit, unpersisted controls.

Dogma source: docs/dev/CONTRACTS.md §Settings persistence contract.

Every value a user can change in the UI must reach the long-term config
(QSettings) with an **explicitly declared type**, and the load/save surface
must be a **full pass**: nothing saved without a typed load, nothing loaded
without a save, nothing in the store that a reducer can mutate without a
persistence path.

Scans (AST, no runtime — see ``_framework.settings_load_pairs`` etc.):

1. **Typed loads** — every ``_get_setting`` load in ``load_all_settings``
   declares ``str | int | float | bool``. A missing type is an implicit,
   guessed-format roundtrip.
2. **Full-pass pairing** — the keys loaded in ``load_all_settings`` are
   exactly the keys saved in ``save_all_settings``. A setting that is only
   saved incrementally (or only loaded) drifts or resets between sessions.
3. **Store coverage** — every ``SettingsState`` field is persisted (typed
   load + save) unless it is explicitly listed as transient (or JSON-
   persisted out-of-band).
4. **Apply path pairing** — any ``SettingsApplicationService`` method that
   dispatches a ``Set*Action`` (mutates the store) must also call
   ``_save_setting`` in the same method; every incremental save key must
   have a typed load.
5. **Mutation service** — every call site of
   ``set_viewport_value`` / ``set_settings_value`` / ``set_viewport_color``
   must pass an explicit literal ``setting_key=``; mutating without one is
   an implicit control that never persists.
"""

from __future__ import annotations

import ast

from tests.contracts._framework import (
    JSON_PERSISTED_STORE_SETTINGS,
    MANAGER_PATH,
    MUTATIONS_PATH,
    SERVICE_PATH,
    STORE_SETTINGS_PATH,
    TRANSIENT_STORE_SETTINGS,
    SETTINGS_TYPE_NAMES,
    _method_node,
    read,
    settings_incremental_save_keys,
    settings_load_pairs,
    settings_save_keys,
    store_settings_field_names,
)

_MANAGER = ast.parse(read(MANAGER_PATH))
_SERVICE = ast.parse(read(SERVICE_PATH))
_MUTATIONS = ast.parse(read(MUTATIONS_PATH))
_STORE = ast.parse(read(STORE_SETTINGS_PATH))


def test_every_setting_load_declares_explicit_type():
    """Dogma 1: no ``_get_setting`` load without an explicit scalar type."""
    pairs = settings_load_pairs(_MANAGER)
    assert pairs, "load_all_settings must contain typed loads"
    untyped = [p for p in pairs if p["type"] not in SETTINGS_TYPE_NAMES]
    assert not untyped, (
        "settings loaded without an explicit str/int/float/bool type "
        f"({untyped}) — declare the type so the roundtrip format is explicit"
    )


def test_load_save_full_pass_pairing():
    """Dogma 2: loaded keys == saved keys (both directions)."""
    pairs = settings_load_pairs(_MANAGER)
    loaded = {p["key"] for p in pairs}
    saved = settings_save_keys(_MANAGER)

    only_loaded = sorted(loaded - saved)
    assert not only_loaded, (
        "settings loaded at startup but never written by save_all_settings — "
        "the value can never be re-persisted after any full pass "
        f"({only_loaded})"
    )
    only_saved = sorted(saved - loaded)
    assert not only_saved, (
        "settings written by save_all_settings but never loaded with a typed "
        f"_get_setting ({only_saved}) — add them to load_all_settings"
    )


def test_store_settings_fields_all_persisted():
    """Dogma 3: every reducer-mutable store field has a typed load + save.

    The transient and JSON-persisted manifests are explicit, documented
    declarations (docs/dev/CONTRACTS.md §Settings persistence contract) —
    a field is either persisted through the scalar pass, persisted
    out-of-band with a dedicated helper pair, or explicitly declared
    transient with a reason. Nothing falls through implicitly.
    """
    pairs = settings_load_pairs(_MANAGER)
    loaded = {p["key"] for p in pairs}
    saved = settings_save_keys(_MANAGER)
    field_by_key = {p["key"]: p["field"] for p in pairs}

    uncovered = []
    for field in store_settings_field_names(_STORE):
        if field in TRANSIENT_STORE_SETTINGS:
            continue
        if field in JSON_PERSISTED_STORE_SETTINGS:
            # JSON blob persisted out-of-band through a dedicated helper pair
            # wired into BOTH the load and save master passes.
            if _has_json_helper_pair(_MANAGER, field):
                continue
            uncovered.append(field)
            continue
        if field in field_by_key.values():
            continue
        uncovered.append(field)
    assert not uncovered, (
        "store settings fields that a control can mutate but that have no "
        "typed load + save — the change would be lost on restart. Either add "
        "them to load_all_settings/save_all_settings, or declare them "
        "explicitly in the transient/JSON manifests with a reason "
        f"(docs/dev/CONTRACTS.md). Fields: {sorted(uncovered)}"
    )


def _has_json_helper_pair(tree: ast.Module, field: str) -> bool:
    """True when SettingsManager wires the out-of-band helper pair.

    The dedicated ``_load_<field>`` / ``_save_<field>`` methods must exist
    AND be called by the master pass (load_all_settings /
    save_all_settings), so the full pass still covers the blob.
    """
    load_methods = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SettingsManager"
        for node in node.body
        if isinstance(node, ast.FunctionDef)
    }
    load_name, save_name = f"_load_{field}", f"_save_{field}"
    if load_name not in load_methods or save_name not in load_methods:
        return False

    def _calls(method_name: str, helper_name: str) -> bool:
        fn = _method_node(tree, "SettingsManager", method_name)
        if fn is None:
            return False
        return any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == helper_name
            for n in ast.walk(fn)
        )

    return _calls("load_all_settings", load_name) and _calls(
        "save_all_settings", save_name
    )


def test_apply_path_mutations_always_persist():
    """Dogma 4a: apply methods must not write incremental keys, and
    ``apply()`` must end by scheduling the full-snapshot persist.

    The settings file is only ever written as a coherent snapshot of the
    Store (``schedule_persist`` -> ``save_all_settings``). Incremental
    ``_save_setting`` calls inside the apply path are forbidden: a stale
    dialog widget could silently overwrite good values with its defaults
    (the observed "random settings reset" — ui_mode/scale/rhi reverted).
    """
    violations = []
    for node in ast.walk(_SERVICE):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith(
            ("_apply", "apply")
        ):
            continue
        if _count_save_setting_calls(node):
            violations.append(node.name)
    assert not violations, (
        "SettingsApplicationService apply methods must not call "
        "_save_setting (incremental writes can corrupt the file with stale "
        "widget state); the apply path mutates the Store via dispatches and "
        f"ends with _schedule_persist(): {violations}"
    )


def test_apply_schedules_full_snapshot_persist():
    """Dogma 4b: ``apply()`` itself must call ``_schedule_persist``."""
    apply_node = _method_node(_SERVICE, "SettingsApplicationService", "apply")
    assert apply_node is not None, "SettingsApplicationService.apply missing"
    calls = [
        node
        for node in ast.walk(apply_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_schedule_persist"
    ]
    assert calls, (
        "apply() must call _schedule_persist() so every dialog change "
        "reaches the file as a full Store snapshot"
    )


def test_incremental_saves_have_typed_loads():
    """Dogma 4b: every incremental save key is a typed load key."""
    loaded = {p["key"] for p in settings_load_pairs(_MANAGER)}
    incremental = settings_incremental_save_keys(_SERVICE) - {"keyboard_overrides"}
    unknown = sorted(incremental - loaded)
    assert not unknown, (
        "settings saved by the apply path but never loaded with an explicit "
        f"type at startup ({unknown}) — the control's value resets every session"
    )


def test_mutation_service_call_sites_require_setting_key():
    """Dogma 5: mutating a value without setting_key= is an implicit control.

    Scans every production caller (mutation service, settings controller,
    canvas feature commands) — not just the service definition itself.
    """
    from tests.contracts._framework import SRC, iter_py

    violations = []
    for path in iter_py(SRC):
        tree = ast.parse(read(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr
                in ("set_viewport_value", "set_settings_value", "set_viewport_color")
            ):
                if _has_setting_key(node):
                    continue
                caller = _nearest_function(node, tree)
                violations.append(
                    (node.func.attr, f"{rel(path)}:{node.lineno}", caller)
                )
    assert not violations, (
        "SettingsMutationService callers must pass an explicit setting_key= "
        f"(got none at {violations}) — a control that mutates the store "
        "without persisting is implicitly broken"
    )


def _count_dispatches(fn: ast.FunctionDef) -> int:
    count = 0
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "dispatch"
        ):
            count += 1
    return count


def _count_save_setting_calls(fn: ast.FunctionDef) -> int:
    count = 0
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "_save_setting"
        ):
            count += 1
    return count


def _has_setting_key(call: ast.Call) -> bool:
    """True when the call passes setting_key (literal, keyword or positional)."""
    for kw in call.keywords:
        if kw.arg == "setting_key":
            return True
    # 3rd positional slot of the mutation helpers is setting_key.
    return len(call.args) >= 3


def _nearest_function(node: ast.AST, tree: ast.Module) -> str:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            if child is node:
                if isinstance(parent, ast.FunctionDef):
                    return parent.name
                if isinstance(parent, ast.Lambda):
                    return "<lambda>"
    return "<unknown>"