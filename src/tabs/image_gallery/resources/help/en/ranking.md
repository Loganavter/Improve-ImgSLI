---
description: Algorithms rank by measured quality; the AI domain adds a marked Jev ranking.
icon: algorithms.svg
---
## Ranking: Algorithms and AI

Each series gets a rank — which image is best. The toolbar switch between **Algorithms** and **AI** decides who ranks.

### Algorithms {#algorithms}

The default. It combines the measured readings into one deterministic order: the same images with the same readings give the same rank every time, and ties are broken by file path, never by the order the folder happened to load. Which readings count depends on the folder — see [Quality Metrics](help://workspace.image_gallery.quality#modes).

- An image with nothing measured shows no rank number.
- The rank orders images only within one series.

### AI (Jev) {#ai}

Opt-in. When **AI** is on, the AI ranks the series from its own quality read of each image, not the app's measurements. This rank is not fixed: the same series can come back in a different order, and the stats strip shows **Ranked by AI (Jev)** so you never mistake it for the **Algorithms** read.

- The rank is saved per series, so a re-run is stable until the series changes.
- When the AI is unavailable or unsure, the rank falls back to **Algorithms** with the reason shown, so the rank never changes without a visible cause.

### Reading the rank {#badge}

- A card shows its rank number; the winner of a series shows **★ BEST** instead of a number.
- The stats strip shows which ranker produced the numbers: **Ranked by Algorithms**, **Ranked by AI (Jev)**, or **Ranked by Manual** when you pick the winner yourself with **Keep best** / **Make best**.
- An image with no rank shows no number.

### Next topics {#next-topics}

- [Quality Metrics](help://workspace.image_gallery.quality) — what the readings behind the Algorithms rank mean.
- [Ask AI](help://workspace.image_gallery.ask_ai) — ask questions about a selection or a series.
