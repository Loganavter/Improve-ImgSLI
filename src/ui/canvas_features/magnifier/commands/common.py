from __future__ import annotations

def dispatch_viewport_action(actions, action) -> bool:
    store = getattr(actions, "store", None)
    dispatcher = getattr(store, "_dispatcher", None) if store is not None else None
    if dispatcher is None:
        return False
    dispatcher.dispatch(action, scope="viewport")
    return True

def emit_interaction_update(actions) -> None:
    store = getattr(actions, "store", None)
    if store is not None and hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change("interaction")
