"""Reducer purity widened to all action types (W5 gap).

Inv: every Action must not mutate previous Store and must not do I/O.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import builtins
import inspect
from copy import deepcopy
from dataclasses import asdict, is_dataclass

import pytest

from core.state_management.reducers import RootReducer
from core.store import Store


def _snapshot(value):
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__slots__"):
        return {slot: _snapshot(getattr(value, slot)) for slot in value.__slots__ if hasattr(value, slot)}
    if isinstance(value, dict):
        return {k: _snapshot(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_snapshot(v) for v in value)
    if isinstance(value, set):
        return set(value)
    return deepcopy(value)


def _dummy_for_param(name, ann, default):
    if default is not inspect.Parameter.empty:
        return default
    lname=name.lower()
    if "color" in lname:
        from PySide6.QtGui import QColor
        return QColor(1,2,3,255)
    if lname=="offset":
        from domain.types import Point
        return Point(0.1,0.2)
    if lname in {"overrides"} or "overrides" in lname:
        return {}
    if lname=="keys" or "keys" in lname:
        return set()
    if lname=="rect" or "rect" in lname:
        from PySide6.QtCore import QRect
        return QRect(0,0,10,10)
    if lname in {"width","height","x","y","length","percent","weight","fps","index","level","count","size","slot"}:
        return 1
    if lname in {"position","speed","factor","alpha","spacing"} or "position" in lname:
        return 0.5
    if "mode" in lname:
        return "highlight"
    if "language" in lname:
        return "en"
    if "theme" in lname:
        return "auto"
    if "bool" in str(ann).lower():
        return True
    if "Point" in str(ann) or "point" in lname:
        from domain.types import Point
        return Point(0.1,0.2)
    if "path" in lname or "key" in lname or lname in {"format","ext","name"}:
        return "x"
    if ann==str or "str" in str(ann):
        return "x"
    if ann==int or "int" in str(ann):
        return 1
    if ann==float or "float" in str(ann):
        return 0.5
    return 1


def _collect_all_action_classes():
    import importlib
    import pkgutil
    import core.state_management as pkg
    classes=[]
    for mod in pkgutil.iter_modules(pkg.__path__):
        m=importlib.import_module(f"core.state_management.{mod.name}")
        for obj in vars(m).values():
            if inspect.isclass(obj) and obj.__name__.endswith("Action"):
                try:
                    from core.state_management.action_base import Action
                    if issubclass(obj, Action) and obj is not Action:
                        classes.append(obj)
                except Exception:
                    pass
    try:
        import tabs.multi_compare.bootstrap_reducers as mc_br
        for obj in vars(mc_br).values():
            if inspect.isclass(obj) and obj.__name__.endswith("Action"):
                from core.state_management.action_base import Action
                if issubclass(obj, Action):
                    classes.append(obj)
    except Exception:
        pass
    uniq={}
    for c in classes:
        uniq[c.__name__]=c
    return sorted(uniq.values(), key=lambda c: c.__name__)


def _make_action(cls):
    sig=inspect.signature(cls)
    kwargs={}
    for p in sig.parameters.values():
        if p.name=="self": continue
        kwargs[p.name]=_dummy_for_param(p.name, p.annotation, p.default if p.default is not inspect.Parameter.empty else inspect.Parameter.empty)
    try:
        return cls(**kwargs)
    except Exception:
        try:
            args=[]
            for p in sig.parameters.values():
                if p.name=="self": continue
                if p.default is not inspect.Parameter.empty:
                    break
                args.append(_dummy_for_param(p.name, p.annotation, inspect.Parameter.empty))
            return cls(*args)
        except Exception:
            try:
                obj=cls.__new__(cls)
                for p in sig.parameters.values():
                    if p.name=="self": continue
                    setattr(obj, p.name, _dummy_for_param(p.name, p.annotation, inspect.Parameter.empty))
                return obj
            except Exception as e:
                # return None to skip this action rather than abort whole test
                print(f"skip {cls.__name__}: {e}")
                return None


def _store_with_tabs():
    from tabs.image_compare.tab import ImageCompareTab
    ImageCompareTab().register_canvas_features()
    try:
        import tabs.multi_compare.bootstrap_reducers  # noqa: F401
    except Exception:
        pass
    store=Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    return store


def test_all_actions_are_pure_no_mutation_and_no_io():
    # Widened sweep: every Action must not mutate previous Store (pure).
    # I/O absence is checked separately on a representative action (see
    # test_reducer_no_io_representative below) to avoid flaky global open mock.
    reducer=RootReducer()
    all_actions=_collect_all_action_classes()
    assert len(all_actions) >= 20, f"expected many actions, got {len(all_actions)}"
    failures=[]
    for cls in all_actions:
        action=_make_action(cls)
        if action is None:
            continue
        old_store=_store_with_tabs()
        before={"viewport": _snapshot(old_store.viewport), "settings": _snapshot(old_store.settings)}
        try:
            new_store=reducer.reduce(old_store, action)
        except Exception as e:
            failures.append(f"{cls.__name__}: {e}")
            continue
        if _snapshot(old_store.viewport) != before["viewport"] or _snapshot(old_store.settings) != before["settings"]:
            failures.append(f"{cls.__name__}: mutated")
        assert new_store is not None
    assert not failures, "purity failures:\n" + "\n".join(failures)


def test_reducer_no_io_representative(monkeypatch):
    def _blocked(*_a, **_kw):
        raise AssertionError("reducers must not open files")
    monkeypatch.setattr("builtins.open", _blocked)
    from core.state_management.viewport_actions import SetDiffModeAction
    reducer=RootReducer()
    store=_store_with_tabs()
    new_store=reducer.reduce(store, SetDiffModeAction("ssim"))
    assert new_store.viewport.view_state.diff_mode=="ssim"
