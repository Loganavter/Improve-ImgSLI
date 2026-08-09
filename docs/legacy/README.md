# Legacy Docs

Superseded designs and formats, kept only because still-live docs cite them
as the reasoning behind current constants, architecture decisions, or
backward-compatibility branches. Not meant to be read top-to-bottom as
current state.

- **rendering/** (private, `improve-imgsli-internal-docs` repo, `docs/legacy/rendering/`) — closed rendering design/phased-implementation plans (texture-array tile atlas, image_compare/multi_compare renderer unification), plus `glass-panel-text-vibrancy-plan.md` (**not closed** — still the live log for glass-panel HUD text-color work, see its own "Still open" section for what's left).
- **[container-format.md](container-format.md)** — superseded `.imgsli` container versions (v2 ZIP without pixel cache, v1 plain JSON); current format in [docs/dev/CONTAINER_FORMAT.md](../dev/CONTAINER_FORMAT.md).
- **`flyout-render-load-investigation.md`** (private, `improve-imgsli-internal-docs` repo) — closed investigation: pinned corner HUD flyouts (`InfoHUD`/`ZoomIndicator`) appeared to load app rendering; root cause was three copies of a `dispatch_viewport_action` helper misscoping continuous drag dispatches as bare `"viewport"` instead of `"viewport.interaction"`, defeating an existing UI-refresh exclusion. Fixed in `magnifier/commands/common.py`, `magnifier/input/keyboard_movement.py`, `divider/commands/registry.py`.
