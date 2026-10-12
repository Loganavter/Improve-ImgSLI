## Quality Metrics

Every image is measured and scored 0–100, where a higher score is always better. Scores rank the gallery and feed the AI sort.

### Measured metrics {#measured-metrics}

In report order:

- **Sharpness** — detail resolving power.
- **Exposure** — brightness balance.
- **Highlight detail** — how much survives in the brights.
- **Clean** — freedom from noise (lower noise measures score higher).
- **White balance** — color-cast shift from neutral.
- **Source match** — structural similarity to the source.
- **Detail** — high-frequency detail gain versus the source.
- **Color accuracy** — color shift from the source.
- **Typicality** — distance from the series norm.
- **Aesthetic** — learned taste score.

Optional backends add perceptual distance (LPIPS) and no-reference naturalness (BRISQUE); they need the extra quality backend installed and otherwise simply stay absent.

### Where scores appear {#where-scores}

- **Quick Look** — per-image metric rows with the raw reading beside each score.
- **Card dots** — one severity triple per mode: `clean`, `mild`, or `flagged` per artifact, so dots and the Quick Look report always agree.
- **{{tr:image_gallery.sort_quality}}** — sorts AI quality first; images with no score yet sink to the end.

### Modes {#modes}

Each folder resolves to one analysis mode, which decides which artifact triple the dots show: fidelity (an upscale or export batch with a source hub), camera (photographs), or batch-synthetic.

### Reference source {#reference-source}

{{tr:image_gallery.action.set_as_source}} sets the fidelity reference; artifact and fidelity analysis re-run against it. Pick the cleanest original — typically the unprocessed export source — before judging the rest of the series. Scores and the [Triage and Review](help://gallery_triage#keep-best) winners update from the new reference.
