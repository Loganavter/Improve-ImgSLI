# Plan — adaptive metric profiles (content-aware metric selection from the pool)

Status: draft · Date: 2026-10-17 · Scope: `src/tabs/image_gallery/` (tab-owned)

Related: [plan-gallery-split-2026-10-17.md](plan-gallery-split-2026-10-17.md) ·
[../../../docs/dev/CODE_PATTERNS.md](../../../../../docs/dev/CODE_PATTERNS.md)

## Problem

The **metric profile** (which axes a series is measured/scored on) is fixed per
`mode`, and the mode is picked by a local **stub heuristic**
(`services/mode.py::select_mode`: hub → `fidelity`, avg sharpness > 120 →
`camera`, else `batch_synthetic` — docstring: "Stub heuristic (as spec allows)").

So every folder is judged against the same handful of axes, while the metric
**pool is much broader** (16 measurable axes + `composition`):

```
sharpness exposure clipping noise white_balance ssim detail_gain color_accuracy
typicality aesthetic lpips dists brisque clipping_delta halo_delta chroma_fringe_delta
```

Consequences called out by the product owner:

- a series of **10 seed variations** of a generated image is scored on
  `white_balance` — a priori irrelevant — while a *hallucination/invented-texture*
  axis would be the useful one;
- "the axis that matters" (`invented_texture`, `over_smoothing`, …) is only
  present in ONE profile (`batch_synthetic`), so a mis-picked mode hides it;
- there are **more domains than 3 modes**, and a 3-way enum cannot express them.

## General model (the criterion every phase is measured by)

> A **metric profile** is a *subset of the fixed metric pool* chosen per
> **comparison context** (folder → series → domain), from a cheap **salience**
> pre-analysis, with the **VLM as the selector** and a deterministic heuristic
> fallback.

The **pool is immutable** (axis ids + their detectors). Only the *active subset*
varies. This keeps detectors, the VLM scorecard, `rank_fusion`, the dots and the
Quick Look rows on ONE vocabulary — the invariant the two-domain model rests on.

## Pieces already in place (reuse, don't rebuild)

| Need | Existing seam |
|---|---|
| Metric pool (the vocabulary) | `services/metric_scores.py` `SPECS` / `SCORECARD_AXIS_IDS` |
| Profile read (the single seam) | `services/rank_fusion.py::measured_axes_for(mode)` |
| Context detection | `services/mode.py` (`select_mode`, hub via `detect_source`) |
| Cheap per-item measurements | the local proxy pass writes `item.metrics` for every item |
| Salience signal | `use_cases/tie_break.py::_is_tie` / `controller.TIE_EPSILON` (pairwise near-equal) |
| VLM call + cache + stage gate | `services/ai_client` + `ai_cache` + `use_cases/pipeline_stages` (`jev_rank` precedent) |
| Artifact profile | `use_cases/quality.py::MODE_ARTIFACTS` |

## Target pipeline

0. **Triage** commits series (existing).
1. **Context** — reference hub (`detect_source`) + coarse content (existing).
2. **Salience (local, no network)** — from `item.metrics`: per-axis spread across
   the series (normalized stdev / max−min) **and** pairwise deviation vs the
   reference (SSIM or the embedding distance `_is_tie` already uses). Output:
   axes ranked by salience + members ranked by deviation magnitude.
3. **Probe** — pick the **K most-deviant members** (K from the series size and
   the salience spread; see below) + a compact salience summary (top axes and
   their deltas).
4. **Select (VLM, one call)** — from the **fixed pool**, choose the applicable
   axes (optionally the artifact profile). Constrain to pool ids; unknown or
   detector-unavailable axes are dropped, never fabricated. Declared stage
   `metric_profile` (via `pipeline_stages`), gated on `metrics_ready`; the
   result is **pinned** (cache key = folder-gen + member fingerprint + salience
   fingerprint) so a re-run over unchanged inputs issues **no second call**.
5. **Measure** — the profile's axes are what the prompt requests
   (`ai_client._scorecard_axes`), and what the dots / Quick Look / rank fusion
   read. Nothing downstream changes shape.
6. **Fallback** — no key / network / salience → the heuristic profile (today's
   mode mapping). The control always does something visible, never a dead end.

## Adaptive probe size (how many images we send)

`K = clamp(2, len(series), round(base + k · salience_spread))`, members chosen by
deviation from the reference (or the pairwise-farthest set). Rationale: a
near-uniform series only needs the two extremes to name the domain; a scattered
series needs more to characterize it. This replaces a fixed cap.

## Domains beyond the three modes

Model "domains" as **named profiles over the pool**; `fidelity` / `camera` /
`batch_synthetic` become built-ins. The VLM may select a built-in or compose an
ad-hoc subset from the pool (constrained to pool ids). New detector axes join
the pool independently of the profiles, so the enum no longer caps the domains.

## Constraints / risks

- **Vocabulary stays fixed** — free-form VLM axes are rejected: they would not
  match the detector numbers, and `rank_fusion` compares variants of a series
  **over the same axes**; a profile is therefore per-context and applied
  uniformly to its members.
- **Determinism + cost** — the chosen profile must be a pure function of
  (member set, measured metrics, model reply) and pinned (the `ai_cache`
  discipline). One extra VLM call per folder, cached.
- **Fail-open** — missing metrics (no salience) → the heuristic profile.
- **Observability** — the profile is stated in the `[ai]` trace
  (`metric profile: axes=[…] source=vlm|heuristic`) so an empty/odd measurement
  set is explained, not silent (the `gal-jev-debug` lesson).

## Phases (each independently shippable + revertible)

- **P0 — profile plumbing (no VLM).** Introduce a `MetricProfile` value object
  (axis ids) and an active-profile seam; `measured_axes_for(mode)` reads it. UI
  unchanged; the profile equals today's mode mapping. Pure refactor.
- **P1 — local salience (no VLM).** Per-axis spread + member deviation →
  `profile = {heuristic base} ∪ {axes whose spread exceeds a floor}`.
  Deterministic and unit-testable; no network.
- **P2 — VLM profile selection.** Probe (K members + salience summary) → VLM
  chooses from the pool; pin it (cache + `pipeline_stages.metric_profile`);
  heuristic fallback; trace the decision.
- **P3 — adaptive K** (the formula) + reference choice (hub, else
  pairwise-farthest).
- **P4 — domains + UI.** Named profiles, a visible "active metric profile" chip,
  and a manual override.

## Acceptance (per phase)

- gallery + `tests/contracts` green; new profile tests (same inputs → same
  profile; unavailable axes dropped; fallback when AI off).
- P2+: the `[ai]` trace names the profile + source; a re-run over unchanged
  inputs issues no second VLM call (cache pin); a debug counter proves one call
  per folder-gen.

## Non-goals

- free-form, model-invented axes (pool is closed);
- replacing the local detectors (the pool is their vocabulary);
- per-ITEM profiles (a profile is per-context; items share it).
