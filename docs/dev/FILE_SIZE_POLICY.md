# File Size Policy & Audit-Meta

Machine-checkable complement to [CODE_PATTERNS.md](CODE_PATTERNS.md) and [CODE_MASS_REDUCTION.md](CODE_MASS_REDUCTION.md).
`cloc.txt` gives mass, this doc gives *policy* — which large files are intentional and which are debt.

## Thresholds

| Scope | Limit | Marker | Enforcement |
|---|---|---|---|
| `tabs/<tab>/canvas/features/<name>/**/*.py` | 400 lines | `File-Size-Exempt:` | `tests/contracts/test_canvas_features_file_size.py` |
| `src/**/*.py` outside `tests/`, `docs/`, `resources/i18n` | 500 lines | `Audit-Meta:` | `tests/contracts/test_file_size_policy.py` |
| `tests/**/*.py` | no hard limit | — | `CODE_MASS_REDUCTION.md` Sprint 3 deferred — failure isolation > LOC |

Counts use `len(src.splitlines())` (matches `wc -l` minus trailing newline), not `cloc` code-only.

## Audit-Meta format (inline)

Add a single line anywhere in the file's top docstring or header comments:

```
Audit-Meta: pattern=<kind> size=<lines|exempt> reason="<one-line why not split>"
```

`pattern` kinds:
- `state-machine` — one async pipeline / one resource lifecycle (`CODE_PATTERNS.md` "When not to split")
- `thin-owner-target` — the `use_cases/` module itself (`CODE_PATTERNS.md` reference impl)
- `thin-owner` — thin delegator that already delegates to `use_cases/`
- `qdialog-wiring` — `QDialog` layout/signal bulk (`plugins/export/dialog.py`)
- `tiled-pipeline` — stateless tiled/parallel kernels sharing workers

Examples from the tree:

```python
"""Tiled pixel storage — always memmap-backed.
Audit-Meta: pattern=state-machine size=exempt reason="one memmap lifecycle — splitting threads memmap/shape/tile_size"
"""
```

```python
"""The magnifier's own QRhi render pass.
File-Size-Exempt: single QRhi pass, one resource lifecycle
Audit-Meta: pattern=state-machine size=exempt reason="border-disk + uber mag pipelines share one pass lifecycle"
"""
```

`File-Size-Exempt:` remains valid for canvas features (backwards compat) — `Audit-Meta:` is preferred for new code and for non-canvas files.

## Central registry

`docs/dev/file_size_registry.json` is **generated**, not hand-edited:

```bash
python src/devtools/file_meta.py --write-registry
python src/devtools/file_meta.py --check   # CI: fails if registry stale
```

The registry mirrors every `Audit-Meta:` / `File-Size-Exempt:` found under `src/` (excluding `tests/`, `__pycache__`). It exists so `cloc`-based audits don't need `grep -r`:

```bash
python src/devtools/file_meta.py --report   # human: oversized without meta
./launcher.sh context --cloc-only && python src/devtools/file_meta.py --report --cloc cloc.txt
```

## Workflow for agents

1. Before growing a file past 500 lines, check if it mixes orthogonal concerns — split via `use_cases/` per [CODE_PATTERNS.md](CODE_PATTERNS.md). If it is a single-responsibility machine, add `Audit-Meta:` with reason.
2. After adding/moving `Audit-Meta:` or `File-Size-Exempt:`, run `python src/devtools/file_meta.py --write-registry` and `python src/devtools/docs_link_graph.py --write-index` (the registry is linked from `DOC_INDEX.md` via this doc).
3. CI: `tests/contracts/test_file_size_policy.py` fails on oversized files without a marker or on stale `file_size_registry.json`.

## Related

- [CODE_PATTERNS.md](CODE_PATTERNS.md) — thin owner + `use_cases/` and "When not to split"
- [CODE_MASS_REDUCTION.md](CODE_MASS_REDUCTION.md) — mass budget and sprint history
- `tests/contracts/test_canvas_features_file_size.py` — canvas-specific dogma
- `tests/contracts/test_file_size_policy.py` — repo-wide dogma (this policy)
