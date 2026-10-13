## Quality Metrics

Every image gets a score from 0 to 100, and a higher score is better. The score summarizes several measurements of the image, such as sharpness, exposure, noise, and color, so a high score means the image does well across all of them.

### Measured metrics {#measured-metrics}

The score combines technical measurements of the image, including how it compares with the source when one is set. **Quick Look** shows the raw readings behind each score. When AI image analysis is enabled, perceptual distances and a naturalness reading are added as well.

### Where scores appear {#where-scores}

- **Quick Look** — opens a panel with the metric rows and the raw readings for one image.
- **Card dots** — each card shows a small marker per artifact check, telling you whether the check is clean, mild, or flagged.
- **AI quality** — a **Sort by** value that orders images by their AI score first; unscored images sink to the end.

### Modes {#modes}

**Fidelity** describes how closely an image matches the source. It applies only while a source is set, and the source is always chosen by hand, never automatically.

Without a source, the folder is treated as camera photos or as a synthetic batch. The mode decides which artifact checks apply to the card dots.

### Reference source {#reference-source}

**Source** is the image chosen as the fidelity reference.

**Set as source** sets the fidelity reference; the fidelity analysis then re-runs against it, and the scores follow the new reference on the next pass.
