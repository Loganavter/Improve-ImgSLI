## Quality Metrics

Every image scores 0–100; higher is better.

### Measured metrics {#measured-metrics}

In report order:

- **Sharpness** — detail resolving power.
- **Exposure** — brightness balance.
- **Highlight detail** — survival in brights.
- **Clean** — freedom from noise; lower noise scores higher.
- **White balance** — cast shift from neutral.
- **Source match** — structural similarity to source.
- **Detail** — detail gain versus the source.
- **Color accuracy** — color shift from source.
- **Typicality** — distance from series norm.
- **Aesthetic** — learned taste score.

Perceptual and naturalness rows — LPIPS and DISTS distances plus BRISQUE naturalness — appear only with the optional learned backend.

### Where scores appear {#where-scores}

- **Quick Look** — per-image metric rows with raw readings.
- **Card dots** — one severity triple per mode: `clean`, `mild`, or `flagged` per artifact.
- **{{tr:image_gallery.sort_quality}}** — AI quality first; unscored items sink to the end.

### Modes {#modes}

Fidelity holds only while a source is set — picking the source is manual, never automatic. Without a source the folder resolves to camera or batch-synthetic. The mode selects the artifact triple.

### Reference source {#reference-source}

{{tr:image_gallery.action.set_as_source}} sets the fidelity reference; fidelity analysis re-runs against it. Scores follow the new reference on the next pass.
