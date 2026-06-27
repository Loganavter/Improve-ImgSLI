from __future__ import annotations


def preview_begin(store):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    svc = MagnifierStoreService(store)
    svc.ensure_active_magnifier()
    model = svc.get_active_or_first_magnifier()
    if model is None:
        return None
    return {
        "prev_left": bool(getattr(model, "visible_left", True)),
        "prev_right": bool(getattr(model, "visible_right", True)),
    }


def preview_restore(store, *, prev_left: bool, prev_right: bool):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return
    svc = MagnifierStoreService(store)
    model = svc.get_active_or_first_magnifier()
    if model is None:
        return
    if (
        bool(getattr(model, "visible_left", True)) != prev_left
        or bool(getattr(model, "visible_right", True)) != prev_right
    ):
        svc.set_active_magnifier_visibility_parts(left=prev_left, right=prev_right)
        return True
    return False


def preview_set_side(store, *, side: str):
    from ..store import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return
    svc = MagnifierStoreService(store)
    svc.set_active_magnifier_visibility_parts(
        left=(side == "left"),
        right=(side == "right"),
    )
