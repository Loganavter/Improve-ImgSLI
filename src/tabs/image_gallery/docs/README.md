# Image Gallery

The Image Gallery is a workspace tab that browses images from a folder in a
grid. It registers the `image_gallery` session blueprint.

Product & interaction design (triage pipeline, analysis modes, UX states;
full design notes moved to the private knowledge plane in d1a6a066).
Visual mockups: [design/](design/).

Quick Look preview rendering notes (single-source tiled live path, bounds,
content identity) moved to the private knowledge plane in d1a6a066.

Local docs live here (`src/tabs/image_gallery/docs/`) per the tab-doc
placement rule — see [docs/dev/tabs/index.md](../../../../docs/dev/tabs/index.md).

## Module layout

```text
image_gallery/
    plugin.py         # @plugin("image_gallery") — session blueprint
    tab.py            # TabContract implementation (SessionState chrome, topology overlays)
    controller.py     # image loading / gallery orchestration
    widget.py         # page wrapper
    actions.py        # action catalog + keymap defaults
    bootstrap_reducers.py  # registers the gallery slot reducer
    models.py         # item/card models (tab-level, not the Redux slice)
    state/            # Redux slice: actions.py, models.py, reducer.py, selectors.py
    analysis/         # analysis engine wiring: context_builder, runner, read, producers/
    use_cases/        # pure logic (profile selection, ranking, AI flows, export)
    services/         # media/analysis services (quality_read, metric_profile,
                      # profile_judged, rank_fusion, proxy, AI clients, …)
    ui/               # gallery widgets (cards, quick look, stats strip, toolbar)
    help.py           # tab-owned Help topics
    debug.py          # debug toggles
    icons.py
    resources/{i18n,help,icons}/
    tests/
    docs/
```

## The plugin

`ImageGalleryPlugin` (`plugin.py`) is an `ISessionPlugin` that registers a
`SessionBlueprint(session_type="image_gallery", title="Image Gallery", ...)`
and a fresh state slot (`{"folder": None}`).

> Note: this is the older, separate plugin/session-blueprint registration
> path. `PluginCoordinator.create_session` looks up session types here, not in
> `TabRegistry` (which only wires the tab's page/UI). Both must exist for a
> tab to be creatable from the New Session picker — see
> `tabs/multi_compare/plugin.py` for the template this mirrors.

## Local docs

- [ANALYSIS_BACKENDS.md](ANALYSIS_BACKENDS.md) — how image analysis actually
  works: the two judgment domains (Algorithms / AI), the five network paths and
  which model each one really uses, the metric-profile seam (registry half +
  judge-named half), and who measures which axis.
- [investigations/plan-adaptive-metric-profiles-2026-10-17.md](investigations/plan-adaptive-metric-profiles-2026-10-17.md)
  — plan P0–P4 for the metric profile (axis set, salience, VLM selection,
  named domains).
- [investigations/plan-gallery-split-2026-10-17.md](investigations/plan-gallery-split-2026-10-17.md)
  — the module split this tab's layout follows.
