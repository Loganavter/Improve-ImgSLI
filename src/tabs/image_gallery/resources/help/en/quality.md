## Quality Metrics

Every image gets a score from 0 to 100; higher is better. A score is a summary of several measurements of the image, such as sharpness, exposure, noise, and color, so a high score means the image does well across them.

### Measured metrics {#measured-metrics}

The score combines technical measurements of the image, including how it compares with the source when one is set. Quick Look shows the raw readings behind each score. When the optional learned backend is installed, perceptual distances and a naturalness reading are added as well.

### Where scores appear {#where-scores}

- **Quick Look** — per-image metric rows with the raw readings.
- **Card dots** — a small marker per artifact check on each card, showing whether the check is clean, mild, or flagged.
- **{{tr:image_gallery.sort_quality}}** — sorts by AI quality first; unscored items sink to the end.

### Modes {#modes}

**Fidelity** is how closely an image matches the source. Fidelity mode holds only while a source is set; picking the source is always manual, never automatic.

Without a source, the folder is treated as camera or batch-synthetic. The mode decides which artifact checks apply to the card dots.

### Reference source {#reference-source}

**Source** is the image chosen as the fidelity reference.

{{tr:image_gallery.action.set_as_source}} sets the fidelity reference; fidelity analysis re-runs against it. Scores follow the new reference on the next pass.
