---
description: Get AI commentary on a photo, a selection, or a series.
icon: ai.svg
---
## Ask AI

Ask AI answers questions about a single card, the current selection, or a whole series. Answers are advisory, and every answer carries the **AI read, unverified** badge.

### Ask about a selection {#ask-selection}

- **AI…** — opens **Ask AI** for that card or the current selection.
- **What matters here?** — the default question; it asks the model to summarize the images it is given.
- **AI read, unverified** — the badge on an answer; it marks the answer as unverified.

:::figure{side=block width=420}
![Ask AI panel](../assets/ask_ai_panel.png)
The **Ask AI** panel: the question field, the answer, and the **AI read, unverified** badge.
:::

### Ask about a series {#ask-series}

The series-header menu asks about every member of the series at once. The question carries the measured readings — see [Quality Metrics](help://workspace.image_gallery.quality).

### History and the sidebar {#history-sidebar}

- **History** — the panel lists the questions already answered in the Q/A log, newest last; each entry shows the question and its answer.
- Selecting an entry shows that stored answer again — no new AI request is made.
- The toolbar **AI** toggle shows or hides the **Ask AI** sidebar: the same ask surface, docked beside the grid instead of a popup. **✕** closes it; the arrow keys reach the toggle and every history row.

### Setup and limits {#setup}

- **Image Gallery — AI** — the settings section behind Ask AI; asking needs **Enable AI image analysis**, an **API key**, and a **Model name**. Configure it in [Settings](help://platform.settings#image-gallery-ai). Without all three, the app shows **Configure the AI API key in Settings first.**
- While the model works the panel shows **Thinking…**; a failed request reports **AI could not answer.**
- Answers never change the rank, the selection, or any stored state.
- The same question reuses the cached answer; a new model or new images ask the model again.
