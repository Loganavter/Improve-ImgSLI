## Ask AI

Questions cover one card, the selection, or a whole series; answers are advisory and carry a badge that marks them as AI-supplied.

### Ask about a selection {#ask-selection}

- **{{tr:image_gallery.ask_ai.action}}** — opens {{tr:image_gallery.ask_ai.title}} for that card or the current selection.
- **Default prompt** — {{tr:image_gallery.ask_ai.default_prompt}} summarizes the images it is asked about.
- **Badge** — {{tr:image_gallery.ask_ai.read_badge}} marks AI-supplied text.

### Ask about a series {#ask-series}

The series-header menu asks about every member at once. Quality scores on sharpness or noise are shown without a request to the AI model — see [Quality Metrics](help://workspace.image_gallery.quality).

### Setup and limits {#setup}

- **AI setup** — {{tr:image_gallery.settings.ai_title}} in Settings; asking needs {{tr:image_gallery.settings.enable_ai}}, a key, and a model, otherwise {{tr:image_gallery.errors.not_configured}}.
- **Progress and errors** — {{tr:image_gallery.ask_ai.busy}}; failures report {{tr:image_gallery.ask_ai.error}}.
- **Advisory only** — answers never change rank, selection, or stored state.
- **Caching** — identical questions reuse the cached answer; new model or images ask again.
