"""Ratchet: gallery Jev pipeline substrate — domain SSOT + declared readiness.

``plan-gallery-jev-pipeline-2026-10-15`` §R1 (the ratchet). Two structural
dogmas established by the epic's S1/S2/J1 waves, so neither can silently
regress back into the field.

**(1) One home for the judgment domain (S1).** The Algorithms-vs-AI domain has
exactly one durable home — ``GalleryController._judgment_domain``. The fusion
rank primitive (``_apply_fusion_ranks`` and its nested ``_locked`` helper)
must read that durable field. ``state`` is a *transient render mirror* that is
wholesale REPLACED by ``self.state = GalleryState(...)`` on the
open_folder / append / clear_to_empty entry paths — the replace sites this
file asserts still exist. Reading ``state.rank_domain`` /
``state.judgment_domain`` as an authority therefore loses a restored ``ai``
domain. Reads are flagged; writes/projections and docstrings are allowed.

**(2) Declared stage readiness (S2/J1).** The ``jev_rank`` stage must be
declared with a non-empty ``requires`` (``metrics_ready``) and the run must be
gated through ``use_cases/pipeline_stages`` (``StageGate``) at the schedule
sites (``_run_jev_ranks`` → ``begin``, ``_launch_jev_batch`` → ``finished``).
The superseded ad-hoc mechanism is the anti-pattern this ratchet exists to
catch — do NOT reintroduce: a Jev trigger from the triage commit, a per-chunk
re-fire from ``_refresh_changed_metrics``, or an ``any(m.metrics)`` readiness.

Scan is AST-only (no Qt import); the gallery's own ``tests`` are excluded.
Each scanner has a synthetic fixture proving a fresh violation is flagged, so
the guard is falsifiable.
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, rel

PLAN = "plan-gallery-jev-pipeline-2026-10-15"
GALLERY = SRC / "tabs" / "image_gallery"
PIPELINE_STAGES = GALLERY / "use_cases" / "pipeline_stages.py"
#: The declared-readiness substrate (S2): the registration/gate API the stage
#: declaration and the schedule sites must go through.
PIPELINE_STAGES_API = frozenset({"register_stage", "stage_requires", "StageGate"})
DOMAIN_ATTRS = ("rank_domain", "judgment_domain")
JEV_STAGE = "jev_rank"
CONTROLLER_SUFFIX = "/controller.py"

#: cadence sites the declared-readiness gate owns (S2/J1): the schedule site
#: claims the run (``begin``) and the batch plumbing releases it (``finished``).
_GATED_METHODS = (("_run_jev_ranks", "begin"), ("_launch_jev_batch", "finished"))

#: Superseded ordering mechanism (plan §What this supersedes) — named in every
#: readiness failure so "fix the test" never reads as "delete the gate".
_ANTI_PATTERN = (
    "superseded anti-pattern (do not reintroduce): a Jev trigger from "
    "_commit_triage_series, a per-chunk re-fire from _refresh_changed_metrics, "
    "or an `any(m.metrics)` readiness"
)


# ---------------------------------------------------------------------------
# shared AST helpers
# ---------------------------------------------------------------------------


def _find_fn(root: ast.AST, name: str):
    for node in ast.walk(root):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _module_str_consts(tree: ast.Module) -> dict[str, str]:
    """Simple module-level ``NAME = "literal"`` string constants."""
    consts: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    consts[target.id] = node.value.value
    return consts


def _resolve_str(node: ast.expr | None, consts: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    return None


def _is_state_expr(node: ast.expr) -> bool:
    """True when *node* is the transient gallery mirror (``state``/``self.state``)."""
    if isinstance(node, ast.Name):
        return node.id == "state"
    if isinstance(node, ast.Attribute):
        return node.attr == "state"
    return False


def _gallery_sources() -> dict[str, str]:
    return {rel(p): p.read_text(encoding="utf-8") for p in iter_py(GALLERY)}


def _controller_key(sources: dict[str, str]) -> str | None:
    for path in sources:
        if path.endswith(CONTROLLER_SUFFIX):
            return path
    return None


# ---------------------------------------------------------------------------
# (1) domain authority
# ---------------------------------------------------------------------------


def _domain_read_lines(tree: ast.AST) -> list[tuple[int, str]]:
    """``(lineno, attr)`` for every read of ``state.rank_domain``/``judgment_domain``.

    Catches the attribute form (``self.state.rank_domain``) and the string form
    used all over the controller (``getattr(self.state, "rank_domain", ...)``).
    Writes are ``ast.Store`` and are deliberately not returned.
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in DOMAIN_ATTRS
            and isinstance(node.ctx, ast.Load)
            and _is_state_expr(node.value)
        ):
            out.append((node.lineno, node.attr))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and _is_state_expr(node.args[0])
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in DOMAIN_ATTRS
        ):
            out.append((node.lineno, str(node.args[1].value)))
    return out


def find_domain_violations(sources: dict[str, str]) -> list[str]:
    """One message per ``state``-authority domain read across *sources*."""
    out: list[str] = []
    for path in sorted(sources):
        for line, attr in _domain_read_lines(ast.parse(sources[path])):
            out.append(
                f"{path}:{line}: reads `state.{attr}` — the judgment domain's ONLY "
                "authority is `GalleryController._judgment_domain`; `state` is a "
                "transient render mirror wholesale-replaced by "
                "`self.state = GalleryState(...)` on open_folder/append/"
                "clear_to_empty, so a domain read from it loses a restored `ai` "
                f"domain. See plan {PLAN} §S1 ('one home for the judgment/rank "
                "domain')."
            )
    return out


def _reads_durable_domain(fn: ast.AST) -> bool:
    """True when *fn* reads ``self._judgment_domain`` (attr or ``getattr`` string)."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and node.attr == "_judgment_domain":
            return True
        if isinstance(node, ast.Constant) and node.value == "_judgment_domain":
            return True
    return False


def find_fusion_domain_violations(sources: dict[str, str]) -> list[str]:
    """The fusion rank primitive must read the durable domain (S1)."""
    out: list[str] = []
    key = _controller_key(sources)
    if key is None:
        return [f"no controller.py in scanned sources; cannot verify plan {PLAN} §S1"]
    tree = ast.parse(sources[key])
    fn = _find_fn(tree, "_apply_fusion_ranks")
    if fn is None:
        return [
            f"{key}: `_apply_fusion_ranks` not found — the single rank-assignment "
            f"primitive of plan {PLAN} §S1 is missing."
        ]
    if not _reads_durable_domain(fn):
        out.append(
            f"{key}:{fn.lineno}: `_apply_fusion_ranks` does not read the durable "
            "`self._judgment_domain` — the fusion primitive must gate Jev-owned "
            "ranks on the durable authority, never the replaced `state` mirror. "
            f"See plan {PLAN} §S1."
        )
    locked = _find_fn(fn, "_locked")
    if locked is None:
        out.append(
            f"{key}:{fn.lineno}: `_apply_fusion_ranks._locked` helper not found — the "
            f"Jev-owned-rank guard of plan {PLAN} §S1 is missing."
        )
    elif not _reads_durable_domain(locked):
        out.append(
            f"{key}:{locked.lineno}: `_locked` does not read the durable "
            "`self._judgment_domain`; a Jev rank must be owned on the actual AI "
            f"domain, not a stale/replaced mirror. See plan {PLAN} §S1."
        )
    return out


def _gallery_state_replace_sites(src: str) -> list[int]:
    """Lines of ``self.state = GalleryState(...)`` wholesale replacements."""
    sites: list[int] = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (
            isinstance(target, ast.Attribute)
            and target.attr == "state"
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        fname = value.func.id if isinstance(value.func, ast.Name) else getattr(value.func, "attr", None)
        if fname == "GalleryState":
            sites.append(node.lineno)
    return sites


# ---------------------------------------------------------------------------
# (2) declared readiness
# ---------------------------------------------------------------------------


def _register_stage_decls(sources: dict[str, str]) -> list[tuple[str, int, str | None, ast.expr | None, bool]]:
    """``(path, line, stage, requires_node, requires_is_nonempty_literal)`` per call."""
    decls: list[tuple[str, int, str | None, ast.expr | None, bool]] = []
    for path in sorted(sources):
        tree = ast.parse(sources[path])
        consts = _module_str_consts(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != "register_stage":
                continue
            stage = _resolve_str(node.args[0], consts) if node.args else None
            requires = next((k.value for k in node.keywords if k.arg == "requires"), None)
            nonempty = isinstance(requires, (ast.Tuple, ast.List, ast.Set)) and bool(requires.elts)
            decls.append((path, node.lineno, stage, requires, nonempty))
    return decls


def find_readiness_violations(sources: dict[str, str]) -> list[str]:
    """The ``jev_rank`` stage must be declared with a non-empty ``requires``."""
    out: list[str] = []
    decls = _register_stage_decls(sources)
    jev = [d for d in decls if d[2] == JEV_STAGE]
    if not jev:
        out.append(
            f"no `register_stage({JEV_STAGE!r}, requires=...)` declaration found in "
            f"the gallery tree — the Jev stage must declare its metrics_ready input. "
            f"See plan {PLAN} §S2. {_ANTI_PATTERN}."
        )
        return out
    for path, line, _stage, _requires, nonempty in jev:
        if not nonempty:
            out.append(
                f"{path}:{line}: the {JEV_STAGE!r} stage is registered with an "
                "empty/absent `requires` — a stage must declare its inputs (e.g. "
                f"metrics_ready) so the runner refuses to fire before them. See plan "
                f"{PLAN} §S2/§J1. {_ANTI_PATTERN}."
            )
    return out


def _references_stage_gate(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and node.value == "_stage_gate":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "_stage_gate":
            return True
    return False


def _gate_call_names(fn: ast.AST) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("begin", "finished")
    }


def find_gate_violations(sources: dict[str, str]) -> list[str]:
    """The Jev run must be gated through the declared stage gate."""
    out: list[str] = []
    key = _controller_key(sources)
    if key is None:
        return [f"no controller.py in scanned sources; cannot verify plan {PLAN} §S2"]
    tree = ast.parse(sources[key])
    for fname, needed in _GATED_METHODS:
        fn = _find_fn(tree, fname)
        if fn is None:
            out.append(
                f"{key}: `{fname}` not found — the declared-readiness schedule site "
                f"of plan {PLAN} §S2 is missing."
            )
            continue
        if not _references_stage_gate(fn) or needed not in _gate_call_names(fn):
            out.append(
                f"{key}:{fn.lineno}: `{fname}` does not gate the Jev run through the "
                "declared stage gate (`use_cases/pipeline_stages` StageGate: "
                f"`self._stage_gate.{needed}(...)`) — expected a `{needed}` call. See "
                f"plan {PLAN} §S2/§J1. {_ANTI_PATTERN}."
            )
    return out


# ---------------------------------------------------------------------------
# real-tree checks
# ---------------------------------------------------------------------------


def test_no_gallery_code_reads_domain_from_replaced_state():
    violations = find_domain_violations(_gallery_sources())
    assert not violations, "\n".join(violations)


def test_fusion_rank_reads_durable_domain_authority():
    violations = find_fusion_domain_violations(_gallery_sources())
    assert not violations, "\n".join(violations)


def test_gallery_state_is_still_wholesale_replaced():
    src = _gallery_sources()
    key = _controller_key(src)
    assert key is not None
    sites = _gallery_state_replace_sites(src[key])
    assert len(sites) >= 2, (
        "expected the wholesale `self.state = GalleryState(...)` replace sites that "
        f"make the domain authority durable; found {len(sites)}: {sites}. If `state` "
        f"is no longer replaced, revisit the domain SSOT per plan {PLAN} §S1 — do not "
        "leave a stale guard premise."
    )


def test_jev_stage_declared_with_nonempty_requires():
    violations = find_readiness_violations(_gallery_sources())
    assert not violations, "\n".join(violations)


def test_pipeline_stages_owns_the_declared_readiness_api():
    tree = ast.parse(PIPELINE_STAGES.read_text(encoding="utf-8"))
    api = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    missing = sorted(PIPELINE_STAGES_API - api)
    assert not missing, (
        f"{rel(PIPELINE_STAGES)} no longer owns the declared-readiness API: "
        f"missing {missing}. The stage declaration + gate of plan {PLAN} §S2 must "
        "stay a data declaration plus one runner in this pure (no-Qt) module."
    )


def test_jev_run_is_gated_through_stage_gate():
    violations = find_gate_violations(_gallery_sources())
    assert not violations, "\n".join(violations)


# ---------------------------------------------------------------------------
# falsifiability fixtures — a fresh violation must be flagged
# ---------------------------------------------------------------------------


def test_guard_flags_synthetic_state_domain_getattr_read():
    src = (
        "def _run_jev_ranks(self):\n"
        "    if str(getattr(self.state, 'rank_domain', 'algorithms')) == 'ai':\n"
        "        return\n"
    )
    violations = find_domain_violations({"src/tabs/image_gallery/fake_controller.py": src})
    assert len(violations) == 1
    assert "rank_domain" in violations[0]
    assert PLAN in violations[0]


def test_guard_flags_synthetic_state_domain_attribute_read():
    src = "def f(self):\n    dom = self.state.judgment_domain\n"
    violations = find_domain_violations({"src/tabs/image_gallery/fake_controller.py": src})
    assert len(violations) == 1
    assert "judgment_domain" in violations[0]


def test_guard_allows_domain_writes_and_durable_reads():
    src = (
        "def f(self):\n"
        "    self.state.rank_domain = 'ai'\n"
        "    return str(getattr(self, '_judgment_domain', 'algorithms')) == 'ai'\n"
    )
    assert find_domain_violations({"src/tabs/image_gallery/fake_controller.py": src}) == []


def test_guard_flags_synthetic_ungated_jev_run():
    src = (
        "def _run_jev_ranks(self):\n"
        "    if not any(m.metrics for m in members):\n"
        "        return\n"
        "    self._launch_jev_batch(ready, self._folder_gen)\n"
        "\n"
        "def _launch_jev_batch(self, ready, scope):\n"
        "    pass\n"
    )
    violations = find_gate_violations({"src/tabs/image_gallery/controller.py": src})
    assert len(violations) == 2
    assert "_run_jev_ranks" in violations[0]
    assert PLAN in violations[0]
    assert "do not reintroduce" in violations[0]


def test_guard_flags_synthetic_empty_jev_requires():
    src = "_STAGE = 'jev_rank'\nregister_stage(_STAGE, requires=())\n"
    violations = find_readiness_violations({"src/tabs/image_gallery/fake_stages.py": src})
    assert len(violations) == 1
    assert "requires" in violations[0]
    assert PLAN in violations[0]


def test_guard_flags_synthetic_missing_jev_declaration():
    src = "register_stage('other_stage', requires=('x',))\n"
    violations = find_readiness_violations({"src/tabs/image_gallery/fake_stages.py": src})
    assert len(violations) == 1
    assert JEV_STAGE in violations[0]
