# Plan — gallery analysis engine (one plan, one registry, one read path)

Status: draft · Date: 2026-10-20 · Scope: `src/tabs/image_gallery/` (tab-owned)

Related: [ANALYSIS_BACKENDS.md](../ANALYSIS_BACKENDS.md) ·
[plan-adaptive-metric-profiles-2026-10-17.md](plan-adaptive-metric-profiles-2026-10-17.md)

Replace the gallery's "two judgment domains + N ad-hoc network paths" with one
analysis engine: an immutable **plan**, a **producer registry**, a **single read
path**, and a **catalog** that is the only place a model id may exist. The old
shapes are made impossible by AST gates, not by review.

Written against `main @ e6f45b2` (2026-10-20). `ANALYSIS_BACKENDS.md` was
authored at `94f438e2` — the diff between them touches docs only, so its code
citations still resolve; its conclusions are corrected below where this plan
proved them wrong.

## Goal / non-goals

**Goal.** Any axis value the user sees carries its own provenance
(producer, backend, model, status), and every outbound request is a declared
step of a plan with a known model, payload policy, cost class and cap. Adding a
producer = dropping a package in; removing one = its axes show as gaps, nothing
else breaks.

**Non-goals.**
- No UI redesign, no new metrics, no provider expansion, no canvas changes.
- No cross-session catalog (separate queue task
  `task-gallery-persistent-cross-session-2026-10-12`).
- Local detector math (`services/proxy.py`, `metric_scores.SPECS`) is wrapped,
  not rewritten.
- Ask AI stays advisory: it never writes axis values or rank.

## Why (verified defects, not impressions)

Every row is a code fact at `e6f45b2`, re-run by the supervisor — not a
docstring and not a worker claim.

| # | Bypass class | Proof |
|---|---|---|
| B1 | Model identity is a per-path constant while the endpoint is the user's | `services/jev_client.py:54` `JEV_MODEL`, `:201` `"model": JEV_MODEL`; gate `controller.py:1655-1666` requires `enabled/base_url/api_key` but **not** `model` |
| B2 | Payload policy lives per call, not per plan | scorecard uploads `image_path.read_bytes()` (`services/ai_client/request.py:77-78`); `vlm_max_edge_px` applies only to `vlm._encode_image` — the Settings label is a lie for the most frequent upload |
| B3 | Producer selection is scattered and sometimes domain-blind | switch `use_cases/ai_analysis.py:192`; settle `use_cases/triage_run.py`; triage tail runs `owner.run_tie_break_if_needed(ser)` for every series (`use_cases/proxy_pass.py:403-408`) with gate `enabled/api_key/model` only (`use_cases/tie_break.py:114`) — **no domain check**, and on success it writes `is_best/crown_rank` (`:232-241`) |
| B4 | Silent substitution / silent degradation | profile AI failure returns the heuristic profile (`services/profile_ai.py:392-408`); Jev failure reason only `logger.debug` (`controller.py:1817-1818`); priority failure silent |
| B5 | Cache identity is incomplete | tie-break key = paths+mtime, no model/endpoint (`services/vlm_cache.py:36-46`); ask key has no `base_url`/`effort` (`controller.py:2053-2078`); Jev key has no endpoint |
| B6 | The read path decides "whose numbers" by domain instead of per-axis provenance | `services/quality_read.domain_axis_scores:71-76` — a whole-dict swap (`ai` → `item.analysis.axes`, `algorithms` → `item.metrics`); no per-axis provenance exists, and `rank_fusion.item_quality:109` reads `item.metrics` with no domain parameter, so the fusion order and series priority stay algorithmic in the AI domain |

Consequence, stated plainly: today correctness rests on the author remembering
which of five (really seven) paths honours which setting. That is the thing this
plan removes.

## Target architecture

```
src/engine/analysis/            Qt-free core: no tabs.*, no core.store, no Qt
  contracts.py                  AxisValue, AnalysisRecord, BackendRef, ProducerSpec,
                                AnalysisPlan, Budget, RunJournal
  registry.py                   auto-discovery (manifest.py), removal-safe
  resolver.py                   THE only place (policy, axes, inputs) -> runs
  catalog.py                    provider/model resolution + validation
  cache.py                      one key builder: content x backend x params x axes
  budget.py                     fan-out accounting + consent hooks
  journal.py                    what ran / why / skipped / failed (UI reads this)

src/tabs/image_gallery/analysis/   thin tab adapters
  producers/local.py            proxy + metric_scores detectors
  producers/ai_scorecard.py     per-image AI scorecard
  producers/rank.py             Jev rank + series priority (one producer)
  producers/tie_break.py        VLM tie-break
  producers/profile_select.py   VLM/heuristic axis-set recommendation
  producers/ask.py              advisory Q&A (never writes axes)
  read.py                       AxisReader used by dots/rows/rank/badge/report
```

### Contracts (shape, not final code)

```python
@dataclass(frozen=True, slots=True)
class AxisValue:            # one axis of one item
    axis: str
    value: float | None     # None => unavailable; never "borrowed"
    producer: str           # registered producer id
    backend: BackendRef | None
    status: Literal["ok", "gap", "error", "stale"]
    reason: str = ""

@dataclass(frozen=True, slots=True)
class BackendRef:           # produced ONLY by catalog.resolve()
    provider: str; model: str; base_url: str
    params: Mapping[str, object]

@dataclass(frozen=True, slots=True)
class ProducerSpec:
    id: str
    provides: frozenset[str]      # axis ids
    requires: frozenset[str]      # images | reference | series | text
    cost: Literal["free", "per_image", "per_series", "per_folder", "per_question"]
    automatic: bool               # may run without an explicit user action
```

### Invariants (the actual architecture)

- **I1 Provenance per axis.** A surface renders an axis from an `AxisValue`
  whose `producer` is registered. A gap is rendered as a gap with its reason;
  no surface may substitute another producer's number for a missing axis.
- **I2 No producer names a model.** Producers receive a `BackendRef` from the
  catalog; a capability requirement ("needs a router model") is resolved or the
  run is refused **before** the POST.
- **I3 Automatic runs are declared.** `automatic=True` producers run only
  inside a plan, only under a policy that lists them, and only with a cap.
  Default policy in the Algorithms domain: no network at all.
- **I4 Plans are per folder generation.** The domain switch changes the
  *policy*, not the axis set; in-flight work is marked `stale`, not silently
  applied after the switch.
- **I5 One cache key builder.** Key = content identity × (producer, provider,
  model, base_url, params, axis set, schema version). No exceptions.
- **I6 One read path.** UI reads `AxisReader`; nobody touches
  `item.metrics` / `item.analysis` / `state.series_priority` outside the
  repository adapter. (Mirrors the store dogma: one mutation gate.)

### Redux: what goes in the store and what must not

The tab already has a Redux slot, deliberately **path-only** (`state/models.py:1-8`
excludes caches, in-flight flags, generations, workers, VLM streams). That
exclusion is right and stays. The reason the domain ended up on the controller is
the other half of the same decision: `GalleryState` is replaced wholesale on
folder open, so anything user-intent-like had nowhere to live
(`controller.py:192-200`), and `test_gallery_pipeline_substrate.py:330` now
*forbids* reading it from state.

Target: **pool and analysis policy are separate slices.**

- In the store (facts, serializable, single writer):
  `analysis.policy` (algorithms-local | ai-assisted | ai-only), `analysis.plan`
  (id, generation, declared runs), `analysis.axes[item][axis]` = `AxisValue`
  (value/producer/backend/status/reason), `analysis.budget` (declared/cap/
  spent), `analysis.journal` (last run per producer: ok/gap/error + reason).
- NOT in the store (process, not fact): transport, workers, thread pools,
  disk caches, in-flight cancellation, token internals. Those live in the
  engine; the store receives their *results* as records.

Why this is not "Redux for its own sake": with one writer (the resolver
dispatches results) the three domain writers and the 5-6 `== "ai"` gates
collapse into one slice transition, and a surface that wants "whose numbers"
reads a record instead of inferring from a controller field. Without a single
writer, adding a slice only creates a sixth mirror.

### Product decision (owner, 2026-10-20): the metric-profile chip goes away

The strip chip ("Профиль: Синтетика") is a **clickable button**
(`ui/stats_strip/__init__.py:154-166`) that opens a flyout with `auto` + the named
domains (`:682-740`, `SimpleOptionsFlyout`). It is the only UI entry point to
manual domain pinning — and its label is `domain_for_stats`'s *guess*, which can
contradict its own tooltip (doc §6.1), while a pinned domain can promise
unmeasurable axes (doc §6.3).

Decision: **delete the chip, its flyout and its state.** What it was trying to
say is already carried per-axis after P2 (producer/backend per `AxisValue`), and
"which axes are active" is visible as the rows/dots themselves. A status object
cannot lie if there is no status object.

Deleted together (one PR, recorded as a contract change, not as a test fix):

- `StatsStrip._profile_chip`, `_profile_flyout`, `_refresh_profile_chip`,
  `_on_profile_chip_clicked`, `_profile_menu_labels`, `_profile_menu_index`,
  `_on_profile_domain_chosen`, `profile_chip` / `profile_chip_text` accessors,
  `set_metric_profile`'s chip branch;
- `src/tabs/image_gallery/tests/test_metric_profile_chip.py` (it pins the chip,
  its menu index and four locales — deleting it is the point, say so in the PR);
- i18n keys `image_gallery.profile.chip|auto|axes|domain.*` in `en|ru|zh|pt_BR`;
- the help sentences that describe the chip (`resources/help/*/ranking.md`,
  `quality.md`).

Open decision (owner): **the manual pin dies with the chip** (option B, decided
2026-10-20). Deleted in the same PR: `GalleryController.set_metric_domain`,
`_metric_domain` (+ its `state.metric_domain` mirror), `profile_for_domain`'s
pinning use, the chip flyout, and — after a caller audit — `domain_for_stats`
and `DOMAIN_WEIGHTS` (they exist to label/choose a pinned domain; with no pin and
no chip they have no consumer). Keep `profile_for_mode` (the mode→axes base) and
`derive_profile` (salience): they are the automatic path, not the pin.

### Pool: capabilities, not a mode guess

Today two different questions share one filter: *which axes exist*
(`MEASURED_POOL`, 15) and *which can be measured here*
(`profile_for_mode`: 7 / 8 / 14). The VLM prompt lists all 15, then its reply is
intersected with the mode set (`profile_ai.py:233-285`), so on a camera folder
the model may ask for an axis and silently lose it.

Target: the offered set is the **capability set** — derived from actual inputs
(reference present? camera scalars? learned backend ready?), not from the mode
guess — and every excluded axis still appears as `AxisValue(status="gap",
reason=...)`. No silent truncation anywhere.

The pool itself stops being a hand-written constant: it is the union of
`provides` across discovered producers. That removes the three drifting
vocabularies (16 `SPECS` / 17 `SCORECARD_AXIS_IDS` / 17 `parse._AXIS_IDS`) — the
registry becomes the single vocabulary, and a producer that dies takes its axes
with it.

Artifacts are part of the vocabulary, not a side channel: `Artifact`
(`models.py:67-74`, 7 flags) + 16 measured axes = 22 local concepts today,
split into two unrelated systems. They become `MetricKind.CANDIDATE` axes with a
local producer, scored as flags (never numbers).

VLM-proposed axes are allowed **only** as first-class entries: a proposal must
map to a registered producer, or be recorded as a `CANDIDATE`/`JUDGMENT` flag
with `producer="vlm"` and its evidence. A free-text axis with no producer is not
an axis — it is the "who knows what ends up on the scene" failure this plan
exists to remove. `MetricKind.CANDIDATE/JUDGMENT` already exist as slots and are
empty today (`test_axis_kinds.py:27` asserts every registered axis is MEASURED).

### Analyzers are auto-discovered producer packages

Same shape as canvas features: a package per analyzer, `manifest.py` exporting
metadata, discovery by directory scan, removal-safe. Layout (mirrors
`tabs/<tab>/canvas/features/<name>/`):

```
src/tabs/image_gallery/analysis/producers/<name>/
  __init__.py
  manifest.py      # PRODUCER: ProducerSpec — METADATA ONLY (no heavy imports)
  producer.py      # run(ctx) -> tuple[AxisValue, ...]
  helpers.py ...   # free to grow subpackages
```

Discovery rules (copied from the canvas registry, deliberately):

- exact module names (`manifest`, `producer`) imported by fully qualified path;
  packages starting with `_` are excluded; a package whose import fails is
  skipped with a logged reason (graceful degradation);
- never hand-wire a producer into a central file;
- deleting a package must leave the app booting, its axes rendering as
  `status="gap"` (G8).

Two traps this pattern must avoid:

1. **Decode ownership.** `services/proxy.py:1-25` exists because artifacts,
   fidelity and camera each used to decode the same item separately. Producers
   therefore never open files or build stores themselves: they receive an
   `AnalysisContext` (decoded proxy image, source image, tiled store, item
   metadata, mode) — the `FrameContext` analogue. A producer that calls
   `Image.open` / `TiledPixelStore.from_path` is a regression; G11 bans it.
2. **Heavy imports stay inside `run()`.** `services/quality_models.py:28-34`
   documents why: `torch` + PySide6 share OpenMP and segfault at teardown, so the
   backend is imported lazily through one seam, never at module import. Discovery
   imports every manifest, so a manifest that imports torch would load it at
   startup for everyone. G12 asserts that importing all manifests leaves
   `torch`/`piq` out of `sys.modules`.

Migration (behavior-preserving, then deletions):

- `services/artifacts.py` (685 lines, 7 `detect_*` + `_DETECTORS:606`) → 7
  packages, one per artifact, each declaring `kind=candidate`;
- `services/fidelity_metrics.py` → reference-based producers (`ssim`,
  `detail_gain`, `color_accuracy`, `halo_delta`, `chroma_fringe_delta`,
  `clipping_delta`), `requires={"reference"}`;
- `services/camera_metrics.py` → no-reference scalar producers;
- `services/quality_models.py` stays the one learned-backend seam; the
  LPIPS/DISTS/BRISQUE producer imports it lazily and maps its
  ready/missing/error status to `AxisValue(status=…)`;
- `services/proxy.py` keeps its role but becomes the context builder
  (`analysis/context.py`), owned by the engine, not by a producer.

### Provenance must be per axis, including "derived from context"

The current AI prompt carries **every** measured axis as text
(`ai_client/request.py:82-97` → `metric_scores.format_measured_for_prompt:254-260`,
`"Label: raw (quality N%)"`), and then asks the model to score those same axes.
For axes a VLM cannot observe (`ssim`, `lpips`, `dists`, `brisque`, the reference
deltas) the only available answer is an echo of the detector's number — displayed
as the AI's own value. Meanwhile `rank_fusion.item_quality:109` reads
`item.metrics` with **no domain parameter**, so the fusion order and
`series_priority` stay algorithmic in the AI domain (`jev_client.py:387`,
`series_priority.py:104`).

Target rules:

- the registry declares, per axis, which producers may produce it
  (`allowed_producers`); `ssim/lpips/dists/brisque/*_delta` are local-only
  (reference/algorithm), so a model reply for them is either rejected or stored
  as `producer="vlm", status="echo", source=local` — never as an independent
  AI score;
- the prompt does not hand the model numbers for axes it is asked to judge (or
  the reply marks them as context-derived);
- rank, priority, dots, rows and the Jev vector read the same `AxisValue`
  provenance, so "which ranker and whose numbers" is one field, not a domain
  branch.

## Gates (write these FIRST; they are the deliverable that survives)

| Gate | Test | Fails when |
|---|---|---|
| G1 | `test_analysis_no_model_literals.py` | a `"vendor/model"` literal exists outside `catalog.py` + allowlist |
| G2 | `test_analysis_single_resolver.py` | `automatic` producers are referenced outside resolver/budget; `judgment_domain` is read outside the resolver |
| G3 | `test_analysis_axis_provenance.py` | a displayed axis has no registered producer, or a gap is rendered as a value |
| G4 | `test_analysis_cache_identity.py` | a key builder does not take a `BackendRef` (AST signature) |
| G5 | `test_analysis_no_direct_reads.py` | a UI module reads raw metric dicts |
| G6 | `test_analysis_no_silent_fallback.py` | `except: return <local/heuristic>` around a producer run (heuristic must be a producer, not a fallback) |
| G7 | `test_analysis_budget_declared.py` | a non-free producer lacks a cap; resolver allows unbounded automatic fan-out |
| G8 | `test_analysis_producer_removal.py` | deleting a producer package fixture breaks startup (mirrors "feature removable without breaking startup") |
| G9 | `test_analysis_no_network_without_plan.py` | a transport call happens under a policy that declares no network (mock transport, assert 0 calls) |
| G10 | `test_analysis_policy_single_writer.py` | `analysis.policy` is written outside the resolver dispatch, or a `== "ai"` / `_judgment_domain` check exists outside the resolver |
| G11 | `test_analysis_producer_owns_no_decode.py` | a producer opens files / builds a store instead of reading `AnalysisContext` |
| G12 | `test_analysis_manifest_is_light.py` | importing all manifests pulls `torch`/`piq` (or Qt) into `sys.modules` |

G1-G9 start as `xfail` with a **shrink-only allowlist** (like
`scripts/comment_citations_allow.txt`); each phase removes its own entries.
That is the ratchet that makes "honest word" unnecessary.

## Ownership (parallel waves)

Max 4 write lanes; one writer = one clone + one branch. W1 lands before W2 and
W3; W4/W5 split by producer family (disjoint directories).

| Wave | Owner | Owns files | Scope |
|---|---|---|---|
| W1 | @engine-substrate | `src/engine/analysis/{contracts,registry,context,catalog}.py` | contract types, discovery, context, catalog; no gallery behavior change |
| W2 | @analysis-gates | `tests/contracts/test_analysis_*.py` | G1-G12 with a shrink-only allowlist |
| W3 | @read-path | `services/quality_read.py`, `services/rank_fusion.py`, `ui/card/dots.py`, `ui/quick_look/metrics/`, `ui/stats_strip/` | `AxisReader`, per-axis provenance, chip + pin removal |
| W4 | @local-producers | `analysis/producers/{camera,fidelity,artifacts}/`, `services/{artifacts,fidelity_metrics,camera_metrics,proxy}.py` | detectors → auto-discovered packages |
| W5 | @ai-producers | `analysis/producers/{ai_scorecard,rank,tie_break,profile_select,ask}/`, `services/{ai_client,jev_client,series_priority,profile_ai,vlm}.py` | AI paths behind the catalog + budget |

## Phases

**P0 — gates only.** Land G1-G9 with the ratchet allowlist; no product change.
Verify: `pytest -q tests/contracts`.

**P1 — contracts + registry + resolver, adapters as no-ops.** Wrap the existing
code as producers behind the registry; add the `analysis` store slice next to
the untouched path-only pool slice; the read path still switches by domain, but
both sides are now registered. Verify equivalence with the existing gallery
suites. Behavior: unchanged.

**P2 — read path.** `AxisReader` + provenance into dots/rows/rank/badge/report;
delete the domain-wide read swap. Deliberate change: per-axis gaps/errors
instead of "domain shows the other backend's numbers".

**P3 — local producers.** proxy/metric_scores behind the registry; one owner
for "which axes exist" (profile derivation becomes a producer, not a
controller rule).

**P4 — AI scorecard.** `BackendRef` from the catalog; **one** payload policy
function decides downscale per plan (fixes B2 by construction); no `max_tokens`
guess outside the plan.

**P5 — rank producer (Jev + priority).** Catalog resolves the model or the run
is refused with a visible reason (B1, B4); endpoint in the cache key (B5).

**P6 — tie-break.** Explicit policy, cap, and a consent line naming the number
of requests; crown only if the policy says so (B3). Cache identity (B5).

**P7 — profile selector.** Axis-set recommendation with explicit provenance;
the heuristic path becomes a registered producer (`producer="heuristic"`), not
a fallback (B4).

**P8 — Ask AI.** Budget + payload cap + cache identity + visible
"cached (model X)" marker.

**P9 — delete the old.** Remove `JEV_MODEL`, dead `compare_brief_sync`, the old
per-path caches, the domain-swap read; audit i18n strings that name a backend.

Each phase ends by **deleting** its old path, never by keeping it as a fallback.

## Verify (per phase)

```
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/contracts src/tabs/image_gallery/tests -p no:cacheprovider
```
Plus per phase: G1-G9 (their allowlist entries for that phase must be gone) and
G9's "no network without a declared plan" with a mocked transport. Record runs
with `test-journal.sh run <repo> -- <args>`.

## Risks / guards

- **Deliberate behavior changes** (state them in the PR body, one per phase):
  downscale now applies to scorecard uploads (P4); Algorithms domain makes no
  network calls (P6/I3); missing axes render as gaps (P2); failed AI shows its
  reason (P5); cache keys no longer cross backends (P5-P8).
- **Cost**: tests must mock `transport.call_sync`; a live run is a separate,
  explicit acceptance step.
- **Gallery scale**: the resolver must stay O(axes), not O(items).
- **History**: autopush may sweep work into `backup/autopush/<branch>` — read
  files, not `git diff HEAD`, at close-out.

## Claimed-vs-real close-out

Verifier opens each claimed file at the cited line on the merged tree, re-runs
the full contract + gallery suites, and greps the merged tree for a second
implementation of each new symbol (`git log --all --oneline -S <symbol>`).
An `INTERFACE: none` claim is verified mechanically:
`git diff main...<branch> -G "^def |^class "` must be empty.

## Progress log

- 2026-10-20: draft from verified defects B1-B5; B6 pending axis map.

## Catalog update

On approval: add `plan-gallery-analysis-engine-2026-10-20` to
`docs/catalog.yaml` (status `draft`, tags, `relates_to`), run
`scripts/gen_indexes.py`, queue task with `type: plan`, `owns_files`, phases.
