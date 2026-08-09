from __future__ import annotations


def dispatch_viewport_action(actions, action) -> bool:
    store = getattr(actions, "store", None)
    dispatcher = getattr(store, "_dispatcher", None) if store is not None else None
    if dispatcher is None:
        return False
    # Every caller of this helper is a continuous drag/interaction update
    # (magnifier position, split-line drag, ...) and always follows up with
    # emit_interaction_update() right after — so "viewport.interaction" is
    # the scope actually intended here. The old bare "viewport" scope isn't
    # covered by on_store_state_changed's {"interaction", "geometry"}
    # subdomain skip (ui/presenters/main_window/state.py), so every drag
    # tick was triggering a full resolution/file_names/combobox/ratings UI
    # batch refresh — including an InfoHUD glassmorphism backdrop
    # grab+blur pass — on top of the correctly-scoped emission that
    # followed it.
    dispatcher.dispatch(action, scope="viewport.interaction")
    return True


def emit_interaction_update(actions) -> None:
    store = getattr(actions, "store", None)
    if store is not None and hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change("interaction")
