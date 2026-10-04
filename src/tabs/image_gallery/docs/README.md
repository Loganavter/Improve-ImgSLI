# Image Gallery

The Image Gallery is a workspace tab that browses images from a folder in a
grid. It registers the `image_gallery` session blueprint.

Product & interaction design (triage pipeline, analysis modes, UX states;
full design notes moved to the private knowledge plane in d1a6a066).
Visual mockups: [design/](design/).

Quick Look preview rendering notes (single-source tiled live path, bounds,
content identity) moved to the private knowledge plane in d1a6a066.

Local docs live here (`src/tabs/image_gallery/docs/`) per the tab-doc
placement rule — see [docs/dev/tabs/index.md(../../../../docs/dev/tabs/index.md).

## Module layout

```text
image_gallery/
    plugin.py         # @plugin("image_gallery") — session blueprint
    tab.py            # TabContract implementation
    controller.py     # image loading / gallery orchestration
    widget.py         # page wrapper
    models.py         # gallery state
    use_cases/        # pure logic
    services/         # folder/media services
    ui/               # gallery widgets
    icons.py
    resources/i18n/
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
