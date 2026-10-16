---
description: Algorithms rank by measured quality; the AI domain adds a marked Jev ranking.
icon: algorithms.svg
---
## Ranking: Algorithms and AI

Each series gets a rank — which image is best. The **Algorithms | AI** switch in the toolbar decides who ranks.

### Algorithms {#algorithms}

The default. It fuses every measured quality reading (sharpness, exposure, noise, color, source match, and the learned perceptual scores) into one deterministic order. The same images with the same readings give the same rank every time; ties are broken by file path, never by the order the folder happened to load.

- An image with nothing measured is **unranked** — no number, never `#0`.
- The rank orders images only within one series.

### AI (Jev) {#ai}

Opt-in. On the AI domain the assistant **Jev** ranks the series from the AI's own quality read of each image — the per-axis scores the AI gives, not the detector readings. This ranking is **marked** and **non-deterministic**: the same series can come back in a different order, and the badge says **AI (Jev)** so you never mistake it for the Algorithms read.

- It is cached and pinned per series, so a re-run is stable until the series changes.
- When Jev is unavailable or unsure it **degrades visibly** back to the Algorithms rank, and the reason is shown — the rank never silently changes hands.

### Reading the badge {#badge}

The rank badge states the ranker: **Algorithms**, **AI (Jev)**, or **Manual** when you pick the winner yourself with **Keep best** / **Make best**. An image with no rank shows no number.

### Next topics {#next-topics}

- [Quality Metrics](help://workspace.image_gallery.quality) — what the readings behind the Algorithms rank mean.
- [Ask AI](help://workspace.image_gallery.ask_ai) — ask questions about a selection or a series.
