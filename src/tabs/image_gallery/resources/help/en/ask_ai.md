## Ask AI

You can ask questions about a single card, the current selection, or a whole series. Answers are advisory and always carry a badge that marks them as AI-supplied.

### Ask about a selection {#ask-selection}

- **AI…** — opens **Ask AI** for that card or the current selection.
- **Default prompt** — the question **What matters here?** asks the model to summarize the images it is given.
- **Badge** — the **AI read, unverified** badge marks text produced by the AI and not checked by you.

### Ask about a series {#ask-series}

The series-header menu asks about every member of the series at once. Scores for sharpness or noise come from [Quality Metrics](help://workspace.image_gallery.quality) and are shown without a request to the AI model.

### Setup and limits {#setup}

- **AI setup** — configure **Image Gallery — AI** in **Settings**; asking needs **Enable AI image analysis**, an API key, and a model. Without them, the app shows **Configure the AI API key in Settings first.**
- **Progress and errors** — while the model works, the panel shows **Thinking…**; a failed request reports **AI could not answer.**
- **Advisory only** — answers never change the rank, the selection, or any stored state.
- **Caching** — an identical question reuses the cached answer; a new model or new images ask the model again.
