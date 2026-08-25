# Codebase-mass root-cause review (2026-08-26)

Question: why is `src/` ≈ 127k LOC, and which of the causes are actually
avoidable? Method: two parallel reviews — quantitative (per-subsystem cloc,
top files, IC↔MC similarity metrics, ceremony counts, git growth) and
qualitative (cost-per-feature walkthroughs for a canvas feature, a settings
scalar, and a Find Action; defensive-programming density; i18n/help tax) —
then cross-checked against [CODE_MASS_REDUCTION.md](../CODE_MASS_REDUCTION.md)
and its Sprint 1–4 verdicts so already-settled questions are not re-litigated.

Headline: **the mass is not monster classes** — top-size files are clean by
concerns (`tiled_pixel_store.py`, `rhi_renderer/renderer.py`,
`PreviewCoordinator` are sanctioned "when not to split" cases). The mass is
*sanctioned structure multiplied by feature count*: per-feature scaffolding ×
2 tab mirrors × 4 locales × thin-owner delegators.

## Cause ranking (% of src/ = 126 757)

| # | Cause | Share | Verdict |
|---|---|---|---|
| 1 | image_compare as an app-in-app: canvas 18 278 (magnifier alone 8 369), video_editor plugin 8 829 | ~25% | unavoidable — rendering parity / QRhi domain cost |
| 2 | per-feature canvas scaffolding: fixed entry ticket ~200–400 LOC (manifest/passes/settings bindings/i18n×4) even for small features (capture: 11 files / 632 LOC; guides: 16 / 1 048) | ~7% | contested — justified for magnifier-scale features, heavy for small ones |
| 3 | i18n ×4 locales + help content (~6.5k resource LOC) | ~5% | unavoidable — product requirement (AGENTS.md "translations and help impact") |
| 4 | Redux ceremony: 67 action dataclasses + reducer branches ≈ 3.5–4k | ~3% | partially avoidable — core (undo/redo/tracing) earns its keep; the *form* has a mechanical defect (below) |
| 5 | thin-owner delegator noise: 399 single-line delegating methods (~10% of all methods), owners with 63–74 methods | ~0.5% | unavoidable — direct consequence of the sanctioned pattern |

## Avoidable reserve ≈ 7–9k LOC (6–7%)

1. **IC↔MC parallel surfaces (~3–4k)** — `multi_compare/scene/` 2 657 +
   `multi_compare/canvas/` 1 201 mirror the IC canvas stack; mirrored file
   pairs (`widget.py` 584/365, `tab.py` 418/379, line similarity only 2–28%
   — flows diverged, extraction is non-mechanical, see Sprint 3 verdict).
   NOT neglect: a deliberate risk-gate. Sprint 4 froze scene+canvas merge
   (5 407 LOC) pending a dedicated QRhi design note; non-QRhi duplicates are
   already in the 2026-08-25 TODO queue; `tabs/_shared/` holds the first
   893 LOC (save_flow/pyramid/loading_toast/canvas).
2. **session_picker/recent (~2.5k prod + 2.2k tests)** — `items_view.py` 686
   + use_cases 512: a recent-projects panel outweighing whole plugins.
   No functional justification found; candidate for a scoped slim-down.
3. **Dual event infrastructure** — `src/events/` 2 015 LOC coexists with
   core EventBus in `core/plugin_system/` (752); plus legacy
   `src/shared_toolkit/` 2 019. Historical layers; consolidation is
   architecture work, not cleanup.
4. **devtools inside src/** (2 043) — packaging lever, acknowledged by the
   project itself.

## The one cheap structural lever: dead dataclass decorator on actions

62 action classes repeat the same shape: `@dataclass` decorator whose
generated `__init__` is immediately overridden by a handwritten one calling
`super().__init__()` and a `get_payload` returning the single field
(e.g. `plugins/settings/actions/settings_actions.py:5-10`; pattern count:
62 classes). The decorator is dead weight; the shape is copy-paste
mechanics, not dogma. A generic parameterized action (or fixing the shape
once) compresses this without losing undo/tracing properties — the dogma
itself (Dispatcher → RootReducer → Store) stays untouched.

Related mechanical tax: one settings scalar costs ~12–15 lines across 6–7
files (ActionType entry, action class, reducer branch,
VIEWPORT_GETTERS/ACTIONS mappings, load/save, page row, i18n ×4); deleting
one dead setting touched 14 files / ~120 LOC (CODE_MASS_REDUCTION.md:87-105).
A generator or registry-driven scalar would remove most of that surface.

## Confirmed non-problems (do not spend effort)

- Comments: 13 696 lines (10.8%) — concentrated where complexity is highest
  (renderer.py 220, base_images.py 174), reference investigations and race
  guards; value > mass.
- Defensive programming density (`except Exception` = 68% of 1 133 try
  blocks, getattr ×2 605) sits on legitimate boundaries: plugin discovery,
  RHI backend probing, IO/memmap edges, tab-host isolation (CONTRACTS.md
  graceful-degradation dogma). Consequence of plugin/auto-discovery
  architecture, not local uncertainty.
- Test bloat hypothesis refuted by Sprint 3 (claimed 1 300–1 800 duplicate
  test LOC did not materialize); ratio tests:prod ≈ 0.29:1 overall.
- Indirection layers: presenter→use_case→service chains carry logic at each
  hop; the project already audited SessionManager/PluginLifecycleManager/
  ExportController and documented them as not pass-through.
- Re-export `__init__` noise: 79 files of ~1 line each — negligible.

## Process verdict

~93–94% of the mass is either domain-necessary or protected by explicit
dogma/contract-tests; the project's own processes (CODE_MASS_REDUCTION
sprints, contract suite, doc-link graph) actively police the remaining
avoidable fraction. The open levers, in effort-to-payoff order:

1. generic/action-shape fix + settings-scalar registry (`Design needed`);
2. session_picker/recent slim-down (P3);
3. non-QRhi IC↔MC consolidation queue (already tracked, 2026-08-25);
4. event-infra / shared_toolkit consolidation (architecture item);
5. devtools packaging decision (ops).
