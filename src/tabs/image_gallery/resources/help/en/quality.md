---
description: Judge image sharpness and exposure with numeric scores.
icon: analyze.svg
---
## Quality Metrics

Every image gets a score from 0 to 100, where higher is better. The score summarizes several readings of the image, so a high score means the image does well on all of them.

### Measured metrics {#measured-metrics}

The score combines sharpness, exposure, noise, and color, and — once a source is set — how closely the image matches it. **Quick Look** lists each reading as a percentage; a reading the app could not take is shown as **— · not measured**, never as a zero. While **AI** is on these readings are the AI's own analysis of the image; while **Algorithms** is on they are the app's measurements.

A reading whose spread across the whole series is inside the measuring instrument's own noise reads **does not separate these variants** instead of a percentage: the row stays, but that reading cannot order these images and carries no weight in the rank.

### Axes chosen by AI {#judge-axes}

When the AI picks the axes for a series, Quick Look shows each named axis under the model's short, human-readable name; hover the row to read that axis' definition and the **measured by the judge** mark. The registry readings keep their usual names.

- An axis the AI named but never scored reads **— · not measured** — the row is not dropped and no zero is invented.
- An axis that stays the same across the series reads **does not separate these variants**.
- On a card, a dot for an axis the AI named carries the same **measured by the judge** label on hover and a different colour from the measured bands.

### Where scores appear {#where-scores}

- **Quick Look** — the panel opened by a click on a card; it shows one row per reading and its percentage.
- **Quick Look filmstrip** — `←` / `→` (or the ‹ / › circles) move the focus along the strip and `Enter` shows that image. `↓` moves the focus to the panel's action buttons (**Set as source** / **Reject** / **Delete**); `←` / `→` then pick one and `Enter` presses it; `↑` returns to the strip.
- **Card dots** — one dot per metric the folder measures; a dot turns green (70 %+), amber (40–69 %), or red (below 40 %) as that reading gets worse. Hover a dot to read its metric name and percentage.
- **AI quality** — a **Sort by** value that orders images by the AI score first; it applies only while **AI** is on, and unscored images sink to the end.

:::figure{side=block width=100%}
![Quick Look panel](../assets/quality_quicklook.png)
**Quick Look**: the image on the left, and on the right the file facts plus one row per reading with a percentage or **— · not measured**.
:::

### Modes {#modes}

The gallery chooses a mode for the folder, and the mode decides which metrics the card dots show.

When an image is set as the source, the score also measures how closely each image matches it; the source is always chosen by hand, never automatically. Without a source, the gallery treats the folder either as camera photos or as a synthetic batch.

### Reference source {#reference-source}

**Source** — the image chosen as the reference for the comparison.

**Set as source** sets that reference; the analysis then re-runs against it, and the scores follow the new reference on the next pass.
