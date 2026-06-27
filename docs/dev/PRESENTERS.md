# Presenter layer

Presenters sit between the Store (state) and the View (Qt widgets). They translate state changes into UI updates, route UI signals into actions or service calls, and own no business logic of their own.

This document covers `src/ui/presenters/`. For the canvas-tool subsystem layered on top, see [CANVAS_FEATURES.md](CANVAS_FEATURES.md).

## Files

```
src/ui/presenters/
├── __init__.py
├── main_window/                # The "shell" presenter — owns toolbar, dialogs, transient UI
│   ├── presenter.py            # MainWindowPresenter — thin facade
│   ├── connections.py          # signal wiring (Qt signals ↔ presenter methods)
│   ├── actions.py              # user-action handlers (button clicks, hover)
│   ├── state.py                # store→UI sync (the `on_store_state_changed` reducer)
│   ├── workspace.py            # tab/session glue
│   └── features.py             # MainWindowFeatureSet — bag of feature presenters
├── image_canvas/               # The canvas presenter
│   ├── presenter.py            # ImageCanvasPresenter — facade
│   ├── runtime.py              # build_image_canvas_components + connect_image_canvas_runtime
│   ├── lifecycle.py            # init/resize/teardown
│   ├── view.py                 # actual setPixmap/setGeometry calls into Qt widgets
│   ├── background.py / overlay # rendering side
│   ├── coordinators.py / signatures.py
│   └── background_parts/
├── toolbar_presenter.py        # ToolbarPresenter — top toolbar logic
├── toolbar/                    # connections.py, state.py, orientation.py (helpers)
└── ui_update_batcher.py        # UIUpdateBatcher — coalesce multiple UI refresh requests
```

## The shape: facade + free functions

Each presenter is a `QObject` facade with a small, stable API. Heavy logic lives in **free functions in sibling modules**, each taking `presenter` as their first arg. The facade method just delegates:

```python
class MainWindowPresenter(QObject):
    def sync_workspace_tabs(self):
        return sync_workspace_tabs(self)         # → workspace.py
    def on_language_changed(self):
        return on_language_changed(self)         # → state.py
    def _connect_signals(self):
        return connect_signals_impl(self)        # → connections.py
```

This lets you:
- find handler logic by file purpose (state vs actions vs connections), not by scrolling a 2000-line class;
- import-rename without touching the class;
- test free functions with a mock presenter.

When you read a presenter, **skip the facade body** — go to the free function. The facade exists to give an external caller (composer, plugins, event handlers) one stable object.

## The 4 sibling modules per presenter

| Module | Contains | Trigger |
|---|---|---|
| `connections.py` | `connect_signals(presenter)` — connect Qt signals to handlers | Once, during init |
| `actions.py` | Handlers for user-driven events (click, hover, drag) | UI signal → here |
| `state.py` | `on_store_state_changed(presenter, domain)` — pull from store, push to widgets | Store `state_changed` signal |
| `workspace.py` (main_window only) | Tab/session-specific syncing | Store `workspace` scope |

The cardinal rule:
- **`actions.py` writes to the store** (dispatches actions, calls services).
- **`state.py` reads from the store** (and writes to widgets).
- They don't cross over. If a state-sync function calls `dispatch`, you've created a loop with the store subscriber.

## MainWindowPresenter (`src/ui/presenters/main_window/presenter.py:45`)

The shell. Holds references to everything the window-level code needs:

```python
self.main_window_app    # the QWidget
self.ui                 # Ui_ImageComparisonApp — generated widget tree
self.store              # core.store.Store
self.main_controller    # business-logic facade
self.session_manager    # workspace sessions
self.plugin_ui_registry # plugin-contributed actions/menus
self.event_bus
self.features           # MainWindowFeatureSet
self.ui_manager         # transient UI (popups, flyouts) — features.ui_manager
self.ui_batcher         # UIUpdateBatcher
```

`MainWindowFeatureSet` (in `features.py`) bundles the four sub-presenters: `image_canvas`, `toolbar`, `export`, `settings`. Access via `presenter.get_feature(name)`.

## The store→UI flow

`state.py:on_store_state_changed(presenter, domain)` is the single subscriber to `store.state_changed`. It filters by `domain` (scope — see [STORE.md](STORE.md#scopes-the-emit_state_change-argument)) and decides what to refresh:

```python
if domain == "workspace":
    sync_workspace_tabs(presenter); sync_session_mode(presenter); ...
    presenter.ui_batcher.schedule_batch_update(["file_names", "resolution", ...])
    return
if domain == "settings":
    _apply_orientation_underline_mode(presenter)
# ... viewport handling
```

Then it pushes through `UIUpdateBatcher.schedule_batch_update([...])` to coalesce updates.

### UIUpdateBatcher (`src/ui/presenters/ui_update_batcher.py`)

A simple deferred-flush queue:
```python
batcher.schedule_update("file_names")            # add one
batcher.schedule_batch_update(["a", "b", "c"])   # add many
# flush runs via QTimer.singleShot(0, ...) — once per event-loop tick
```

Use it instead of calling `do_update_X(presenter)` directly when several state changes might fire in one tick (typical during a dispatch burst). Otherwise widgets re-render N times in a row.

## ImageCanvasPresenter (`src/ui/presenters/image_canvas/presenter.py:13`)

Owns the canvas (CanvasWidget / QRhi widget) and the magnifier/overlay state. Decomposed:

```python
presenter.lifecycle    # init/resize/movement state
presenter.view         # Qt-facing: setPixmap, setGeometry on the canvas widget
presenter.background   # frame computation / scheduling
presenter.overlay      # overlay state (capture, magnifier)
```

Built by `runtime.py:build_image_canvas_components(presenter)` which returns the four-piece bundle.

`view.py` is the only place that should be calling Qt widget mutators (`setPixmap`, etc.) on the canvas — keep it that way.

## ToolbarPresenter (`src/ui/presenters/toolbar_presenter.py`)

Smaller, same shape: `connections.py` wires button signals, `state.py:update_toolbar_states(presenter)` reflects store state into toolbar widget states (checked/enabled/visible), `orientation.py` handles the orientation toggle specifically.

## MVP boundaries — what to enforce

1. **Presenter MAY** call `widget.setText()`, `widget.setVisible()`, etc. — it owns the view. But...
2. **Presenter MUST NOT** import or construct `QPainter`, `QImage`, paint events, or anything that's strictly View-painting territory. That belongs in the widget class.
3. **Presenter MUST NOT** mutate `store.viewport.*` / `store.document.*` directly. Dispatch an action (see [STORE.md](STORE.md#invariants--what-you-must-hold)).
4. **View widgets MUST NOT** know about the store. They emit signals; the presenter translates.
5. **Free functions in `actions.py`/`state.py` MUST take `presenter` as their first arg** and only touch what's on it (`presenter.store`, `presenter.ui`, etc.). No module-level state.

## Connecting signals — the pattern

`connect_signals(presenter)` in `connections.py` does the one-time wiring. Sample:

```python
def connect_signals(presenter):
    presenter.ui.btn_swap.clicked.connect(lambda: swap_images(presenter))
    presenter.ui.combo_image1.currentIndexChanged.connect(
        lambda idx: presenter.main_controller.session.set_current_image(1, idx)
    )
    presenter.store.state_changed.connect(
        lambda scope: on_store_state_changed(presenter, scope)
    )
```

Connections are made in the presenter constructor (`presenter._connect_signals()`). Disconnections are not needed — the presenter and the UI live for the app lifetime.

## Extension recipe — adding a new UI feedback

You want: "when `viewport.session_data` changes, update some new label."

1. Add `do_update_my_label(presenter)` to `state.py`:
   ```python
   def do_update_my_label(presenter):
       value = presenter.store.viewport.session_data.something
       presenter.ui.my_label.setText(str(value))
   ```
2. Expose it as a method on `MainWindowPresenter` (or call directly).
3. Wire it into `on_store_state_changed` via the batcher:
   ```python
   presenter.ui_batcher.schedule_batch_update(["my_label", ...])
   ```
   then in `UIUpdateBatcher._flush_updates` add a branch that calls `presenter._do_update_my_label()`.
4. Do **not** subscribe a separate `store.state_changed` handler — keep one entry point in `state.on_store_state_changed`.

## Extension recipe — adding a new user-action handler

1. Add `def on_my_thing_clicked(presenter, *args)` in `actions.py`.
2. Inside, dispatch the action: `presenter.store.get_dispatcher().dispatch(SetMyThing(...))`.
3. Wire the signal in `connections.py:connect_signals`:
   ```python
   presenter.ui.btn_my_thing.clicked.connect(lambda: on_my_thing_clicked(presenter))
   ```

## See also

- [STORE.md](STORE.md) — what `state_changed` scopes mean and how to dispatch
- [CONTRACTS.md](CONTRACTS.md) — broader architectural rules
- [CANVAS_FEATURES.md](CANVAS_FEATURES.md) — the canvas-tool subsystem (parallel to but separate from these presenters)
- [TAB_CONTRACT.md](TAB_CONTRACT.md) — workspace-tab interface used by `workspace.py`
