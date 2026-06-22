//! Store — holds state, dispatches actions, notifies subscribers.
//!
//! Mirrors `src/core/store.py`. The Python `Store` exposes `on_change(cb)`
//! and `emit_state_change(scope)`. Here we keep the same shape: dispatch a
//! typed [`Action`], the reducer produces a new state and a [`Scope`],
//! subscribers are called with that scope string.
//!
//! The store is single-threaded by design — the Python version assumes the
//! Qt event loop owns it. For multi-thread access on the C++/Rust side we
//! plan to wrap dispatch in a Qt-side mutex (post-FFI), not bake locking
//! into the core.

use std::cell::RefCell;

use crate::core::action::Action;
use crate::core::reducer::{apply, Scope};
use crate::core::state::AppState;

pub type SubscriberFn = Box<dyn FnMut(&AppState, &Scope)>;

pub struct Store {
    state: AppState,
    subscribers: RefCell<Vec<SubscriberFn>>,
}

impl Store {
    pub fn new() -> Self {
        Self {
            state: AppState::default(),
            subscribers: RefCell::new(Vec::new()),
        }
    }

    pub fn with_state(state: AppState) -> Self {
        Self {
            state,
            subscribers: RefCell::new(Vec::new()),
        }
    }

    pub fn state(&self) -> &AppState {
        &self.state
    }

    /// Register a callback. Called after every dispatched action, regardless
    /// of scope; subscribers filter themselves. Matches `Store.on_change`.
    pub fn subscribe<F>(&self, cb: F)
    where
        F: 'static + FnMut(&AppState, &Scope),
    {
        self.subscribers.borrow_mut().push(Box::new(cb));
    }

    /// Apply one action and notify subscribers.
    pub fn dispatch(&mut self, action: &Action) -> Scope {
        let scope = apply(&mut self.state, action);
        // We must not hold the borrow across user callbacks: they may call
        // back into the store (`state()` is fine, mutations would panic — the
        // Python store has the same contract via the GIL-serialised flow).
        let mut subs = self.subscribers.borrow_mut();
        for cb in subs.iter_mut() {
            cb(&self.state, &scope);
        }
        scope
    }
}

impl Default for Store {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::rc::Rc;

    #[test]
    fn store_dispatches_and_notifies() {
        let mut store = Store::new();
        let calls = Rc::new(Cell::new(0u32));
        let calls_cb = calls.clone();
        store.subscribe(move |_state, scope| {
            assert!(matches!(
                scope,
                Scope::Settings
                    | Scope::Viewport(_)
                    | Scope::Document
                    | Scope::Workspace
                    | Scope::NoOp
            ));
            calls_cb.set(calls_cb.get() + 1);
        });
        store.dispatch(&Action::SetTheme("dark".into()));
        store.dispatch(&Action::SetSplitPosition(0.7));
        assert_eq!(calls.get(), 2);
        assert_eq!(store.state().settings.theme, "dark");
        assert!((store.state().viewport.view_state.split_position - 0.7).abs() < 1e-6);
    }

    #[test]
    fn no_subscribers_is_fine() {
        let mut store = Store::new();
        store.dispatch(&Action::SetDebugMode(true));
        assert!(store.state().settings.debug_mode_enabled);
    }

    #[test]
    fn noop_actions_still_notify_with_noop_scope() {
        // Matches the Python behaviour: emit_state_change is called from
        // mutation paths only, but a wrapped dispatch always notifies so the
        // C++ side can decide whether to ignore.
        let mut store = Store::new();
        let last_scope: Rc<RefCell<Option<Scope>>> = Rc::new(RefCell::new(None));
        let last_cb = last_scope.clone();
        store.subscribe(move |_, scope| {
            *last_cb.borrow_mut() = Some(scope.clone());
        });
        // Invalid session id → NoOp.
        store.dispatch(&Action::SwitchSession("does-not-exist".into()));
        assert_eq!(*last_scope.borrow(), Some(Scope::NoOp));
    }
}
