## Ask AI

Ask a question about what you see: one image, the current selection, or a whole series. Answers arrive on the card with an unverified-read badge.

### Ask about a selection {#ask-selection}

- **{{tr:image_gallery.ask_ai.action}}** — the card and selection context-menu entry opens {{tr:image_gallery.ask_ai.title}} for that card, or for the current selection when several images are selected.
- **Default prompt** — {{tr:image_gallery.ask_ai.default_prompt}} summarizes the slice; type anything else to ask your own question.
- **Badge** — {{tr:image_gallery.ask_ai.read_badge}} marks AI-supplied text so you never mistake it for a measurement.

### Ask about a series {#ask-series}

The series-header menu asks about every member at once — useful for "which of these is sharpest?" across near-duplicates. Scores from [Quality Metrics](help://gallery_quality) stay the faster answer for pure sharpness or noise questions.

### Setup and limits {#setup}

- **Enable first** — {{tr:image_gallery.settings.ai_title}} in Settings holds the switch ({{tr:image_gallery.settings.enable_ai}}), base URL, key, and model. Asking needs the switch on plus a key and a model, otherwise it shows {{tr:image_gallery.errors.not_configured}}.
- **While thinking** — {{tr:image_gallery.ask_ai.busy}}; failures report {{tr:image_gallery.ask_ai.error}} instead of inventing an answer.
- **Caching** — identical questions reuse the cached answer; switching the model or the images asks again.
