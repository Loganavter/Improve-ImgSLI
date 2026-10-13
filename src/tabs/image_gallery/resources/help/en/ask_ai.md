## Ask AI

Ask AI answers questions about a single card, the current selection, or a whole series. Answers are advisory and always carry a badge that marks them as AI-supplied.

### Ask about a selection {#ask-selection}

- **AI…** — opens **Ask AI** for that card or the current selection.
- **What matters here?** — the default question; it asks the model to summarize the images it is given.
- **AI read, unverified** — the badge on text produced by the AI; it marks the answer as unverified.

### Ask about a series {#ask-series}

The series-header menu asks about every member of the series at once. Sharpness and noise readings come from [Quality Metrics](help://workspace.image_gallery.quality) and are shown without a request to the AI model.

### Setup and limits {#setup}

- **Image Gallery — AI** — the settings section behind Ask AI; asking needs **Enable AI image analysis**, an API key, and a model. Configure it in [Settings](help://platform.settings#image-gallery-ai). Without all three, the app shows **Configure the AI API key in Settings first.**
- While the model works the panel shows **Thinking…**; a failed request reports **AI could not answer.**
- Answers never change the rank, the selection, or any stored state.
- The same question reuses the cached answer; a new model or new images ask the model again.
