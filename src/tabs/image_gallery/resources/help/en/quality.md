---
description: Judge image sharpness and exposure with numeric scores.
icon: analyze.svg
---
## Quality Metrics

Every image gets a score from 0 to 100, where higher is better. The score summarizes several readings of the image, so a high score means the image does well on all of them.

### Measured metrics {#measured-metrics}

The score combines sharpness, exposure, noise, and color, and — once a source is set — how closely the image matches it. **Quick Look** lists each reading as a percentage; a reading the app could not take is shown as **not measured**, never as a zero. When AI image analysis is on, a composition reading joins them.

### Where scores appear {#where-scores}

- **Quick Look** — opens a panel with one row per reading and its percentage.
- **Card dots** — three dots on each card, one per defect check; a dot turns green, amber, or red as that check gets worse.
- **AI quality** — a **Sort by** value that orders images by the AI score first; it applies only while the toolbar's **AI** switch is on, and unscored images sink to the end.

### Modes {#modes}

The gallery chooses a mode for the folder, and the mode decides which defect checks the card dots show.

When an image is set as the source, the score also measures how closely each image matches it; the source is always chosen by hand, never automatically. Without a source, the gallery treats the folder either as camera photos or as a synthetic batch.

### Reference source {#reference-source}

**Source** — the image chosen as the reference for the comparison.

**Set as source** sets that reference; the analysis then re-runs against it, and the scores follow the new reference on the next pass.
