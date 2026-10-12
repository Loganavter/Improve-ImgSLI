## Ask AI

Questions cover one image, the selection, or a whole series; answers arrive on the card with an unverified-read badge.

### Ask about a selection {#ask-selection}

- **{{tr:image_gallery.ask_ai.action}}** — opens {{tr:image_gallery.ask_ai.title}} for that card or the current selection.
- **Default prompt** — {{tr:image_gallery.ask_ai.default_prompt}} summarizes the slice.
- **Badge** — {{tr:image_gallery.ask_ai.read_badge}} marks AI-supplied text.

### Ask about a series {#ask-series}

The series-header menu asks about every member at once. Scores from [Quality Metrics](help://gallery_quality) stay faster for sharpness or noise.

### Setup and limits {#setup}

- **Enable first** — {{tr:image_gallery.settings.ai_title}} in Settings; asking needs {{tr:image_gallery.settings.enable_ai}}, a key, and a model, otherwise {{tr:image_gallery.errors.not_configured}}.
- **While thinking** — {{tr:image_gallery.ask_ai.busy}}; failures report {{tr:image_gallery.ask_ai.error}}.
- **Caching** — identical questions reuse the cached answer; new model or images ask again.
