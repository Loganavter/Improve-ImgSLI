"""G2/G10 ratchet: the judgment domain is read only by the resolver (W5).

``plan-gallery-analysis-engine-2026-10-20`` §Gates G2/G10 and §"Redux: what goes
in the store and what must not": five (really seven) ad-hoc ``== "ai"`` gates
and every direct ``_judgment_domain`` read collapse into one policy slice
transition once the resolver exists. Until it lands, this gate pins the current
sites so the plan cannot quietly grow an eighth, and so each wave deletes its
own entries (a stale entry fails).

Two scanners, both AST-only:

1. **domain reads** — ``ast.Attribute`` loads of ``_judgment_domain`` /
   ``judgment_domain`` / ``rank_domain`` plus the ``getattr(obj, "_judgment_domain",
   ...)`` string form that the controller uses everywhere (a string read is the
   same read with worse grep-ability). Writes (``self._judgment_domain = ...``,
   ``setattr(...)``) are projections, not reads, and are deliberately not
   flagged.
2. **``"ai"`` comparisons** — ``ast.Compare`` with a literal ``"ai"`` on either
   side and an ``==`` / ``!=`` / ``in`` / ``not in`` operator. That is the shape
   of the ad-hoc domain gate.

Not every ``"ai"`` in the tree is a gate, and the scanner must not pretend it
is: dict keys, i18n keys, ``Literal["ai"]`` aliases, subscripts and call
arguments are pinned clean by explicit tests below. Only a *comparison* against
the literal is the anti-pattern.

Wave assignment in the reasons: the ``AxisReader`` substrate landed in its own
wave, so switching the read-path surfaces (dots/rows/stats_strip/badge/toolbar)
onto it and deleting their domain branches is W5/P9 work; the controller/use-case
gates become the plan policy in W5 (resolver + ``analysis.policy``). Owned by
``plan-gallery-analysis-engine-2026-10-20`` §Ownership.
"""

from __future__ import annotations

import ast

import pytest

from ._framework import SRC, iter_py, rel
from .analysis_gates_allowlist import (
    assert_ratchet,
    add_hit,
    make_key,
    source_line,
)

PLAN = "plan-gallery-analysis-engine-2026-10-20"

#: Attribute names that carry the Algorithms-vs-AI judgment (a read is a gate).
DOMAIN_ATTRS = ("_judgment_domain", "judgment_domain", "rank_domain")

#: The literal the ad-hoc gates compare against.
AI_LITERAL = "ai"

#: ``==`` / ``!=`` / ``in`` / ``not in`` — the gate shapes the plan names.
_COMPARE_OPS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)

#: Current domain-read sites (derived by running the scanner, never guessed).
#: Shrink-only: the waves named in the reasons (W5 producers/policy, P9 deletion)
#: each delete their own entries as they land.
DOMAIN_READ_ALLOWLIST: dict[str, str] = {
    # --- W5/P9: read-path surfaces stop consulting the domain -----------------
    "src/tabs/image_gallery/use_cases/ai_analysis.py|live = getattr(owner, \"_judgment_domain\", None)": (
        "gallery-six 2026-10-22: the ONE shared AI-domain gate "
        "(``_epoch_is_current``) that every AI/Jev/tie-break emission AND landing "
        "site now routes through (measured leaks: a VLM tie-break on Algorithms "
        "and four POSTs after a live switch). It REPLACES the per-site ad-hoc "
        "gates above, so it is removed by the same W5 policy slice, not before."
    ),
    "src/tabs/image_gallery/ui/card.py|domain = getattr(owner, \"_judgment_domain\", None)": (
        "card picks an artifact severity by domain — W5/P9 renders the AxisValue's "
        "own provenance instead (AxisReader / per-axis provenance)"
    ),
    "src/tabs/image_gallery/ui/card.py|_domain = getattr(owner, \"_judgment_domain\", None)": (
        "same card surface, second call site — W5/P9 (AxisReader) removes it with "
        "its sibling above"
    ),
    "src/tabs/image_gallery/ui/grid_view/drag_source.py|return str(getattr(owner, \"_judgment_domain\", \"\") or \"\")": (
        "drag payload carries the judgment domain — the metric-profile pin it "
        "mirrored is deleted (2026-10-20); this per-drag field goes in W5"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/theme.py|domain = getattr(owner, \"_judgment_domain\", None)": (
        "row theming branches on the domain — W5/P9 styles from the AxisValue "
        "(producer/status) instead of the domain"
    ),
    "src/tabs/image_gallery/ui/toolbar/__init__.py|if getattr(self, \"_judgment_domain\", \"algorithms\") == dom:": (
        "toolbar domain switch reads the authority — with the metric-profile chip "
        "deleted (2026-10-20) this is the judgment-domain switch alone; W5 "
        "replaces it with the analysis policy slice"
    ),
    "src/tabs/image_gallery/ui/toolbar/__init__.py|apply_domain(str(getattr(self, \"_judgment_domain\", \"algorithms\")))": (
        "toolbar re-applies the judgment domain after a rebuild — same switch, "
        "W5 policy slice"
    ),
    "src/tabs/image_gallery/ui/toolbar/__init__.py|return str(getattr(self, \"_judgment_domain\", \"algorithms\"))": (
        "toolbar exposes the domain for the switch — W5 policy slice"
    ),
    "src/tabs/image_gallery/ui/toolbar/sort_picker.py|if owner.judgment_domain == \"ai\":": (
        "sort picker branches on the domain — W5/P9 reads the AxisValue/provenance "
        "instead (no domain-wide branch)"
    ),
    "src/tabs/image_gallery/ui/widget_parts/view_prefs.py|_domain = getattr(owner, \"_judgment_domain\", None)": (
        "view restore re-derives AI work from the domain — W5/P9 makes it "
        "level-triggered on the read path, not on a domain field"
    ),
    "src/tabs/image_gallery/ui/widget_parts/view_prefs.py|state.set(\"judgment_domain\", str(getattr(owner, \"_judgment_domain\", \"algorithms\")))": (
        "the judgment-domain state mirror — W5 replaces it with the analysis "
        "policy slice (the metric-profile pin it sat beside is gone)"
    ),
    # --- W5: controller / use-case gates collapse into the plan policy -------
    "src/tabs/image_gallery/controller.py|if str(getattr(self, \"_judgment_domain\", \"algorithms\") or \"\").strip().lower() != \"ai\":": (
        "three ad-hoc 'is this the AI domain?' gates (708/906/1371) — W5 "
        "replaces them with the analysis policy slice + resolver"
    ),
    "src/tabs/image_gallery/controller.py|getattr(self, \"_judgment_domain\", \"\"),": (
        "domain passed into the Jev debug reason (711/910/914) — W5 (journal "
        "entry names the producer/backend instead)"
    ),
    "src/tabs/image_gallery/controller.py|and str(getattr(self, \"_judgment_domain\", \"algorithms\") or \"\")": (
        "second half of the AI-domain gate at 1035 — W5 policy slice"
    ),
    "src/tabs/image_gallery/controller.py|str(getattr(self, \"_judgment_domain\", \"algorithms\") or \"\")": (
        "second half of the AI-domain gate at 1111 — W5 policy slice"
    ),
    "src/tabs/image_gallery/controller.py|str(getattr(self, \"_judgment_domain\", \"algorithms\")),": (
        "domain passed to the fusion/rank helper (1406) — W5 reads the "
        "AxisValue provenance (plan §Provenance per axis)"
    ),
    "src/tabs/image_gallery/controller.py|domain=str(getattr(self, \"_judgment_domain\", \"algorithms\")),": (
        "domain passed to the quality read (1702) — W5 deletes the domain-wide "
        "read swap; the AxisReader substrate is already in place"
    ),
    "src/tabs/image_gallery/controller.py|src or None, domain=str(getattr(self, \"_judgment_domain\", \"algorithms\"))": (
        "domain passed to the rank fusion (1866) — W5 (provenance per axis)"
    ),
    "src/tabs/image_gallery/use_cases/action_context.py|domain = str(getattr(owner, \"_judgment_domain\", \"\") or \"\").strip().lower()": (
        "action context resolves which backend an action targets — W5 the "
        "resolver answers 'may this producer run under this policy?'"
    ),
    "src/tabs/image_gallery/use_cases/large_drop_guard.py|getattr(controller, \"_judgment_domain\", \"algorithms\") or \"algorithms\"": (
        "drop guard scales its warning by domain — W5 policy slice (the read "
        "path reads axes, not domains)"
    ),
    "src/tabs/image_gallery/use_cases/triage_run.py|if str(getattr(owner, \"_judgment_domain\", \"algorithms\") or \"\").strip().lower() != \"ai\":": (
        "three triage tails re-check the domain (582/594/613) — W5 makes the "
        "tie-break a declared plan step gated by the resolver, not by a domain"
    ),
    # --- diagnostics --------------------------------------------------------
    "src/devtools/app_snapshot.py|domain = getattr(controller, \"_judgment_domain\", None)": (
        "devtool snapshot mirrors the controller's authority for diagnostics — "
        "retired with the field itself in W5 (the policy slice replaces it)"
    ),
}

#: Current ``== "ai"``-style gate sites (derived the same way).
AI_COMPARE_ALLOWLIST: dict[str, str] = {
    # --- W5/P9: read-path surfaces -------------------------------------------
    "src/tabs/image_gallery/services/rank_badge.py|return RANK_SOURCE_JEV if dom == \"ai\" else RANK_SOURCE_FUSION": (
        "rank badge infers the ranker from the domain — W5/P9 renders the "
        "AxisValue/AnalysisRecord producer + backend instead"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/rows.py|if domain == \"ai\":": (
        "row builder picks the AI read path (287) — W5/P9 reads AxisValue records, "
        "not a domain branch"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/rows.py|subline = ssim_subline(overlay, item) if domain != \"ai\" else \"\"": (
        "subline shown only outside the AI domain (462) — W5/P9 shows per-axis "
        "provenance/gaps instead of a domain condition"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/rows.py|if domain == \"ai\" and _comp >= 0 and not _is_judged_axis(\"composition\"):": (
        "composition hint gated on the domain (558) — W5/P9 per-axis provenance; "
        "P7-C adds the judge-named guard so a judged composition row is not "
        "duplicated"
    ),
    "src/tabs/image_gallery/ui/quick_look/metrics/theme.py|return \"ai\" if str(domain or \"\").strip().lower() == \"ai\" else \"algorithms\"": (
        "domain normalizer for row theming — W5/P9 styles from the AxisValue status"
    ),
    "src/tabs/image_gallery/ui/stats_strip/__init__.py|if dom == \"ai\":": (
        "stats strip falls back from the rank token to the domain (539) — "
        "W5/P9 renders the AxisValue/provenance; the strip's profile chip is "
        "already deleted (2026-10-20)"
    ),
    "src/tabs/image_gallery/ui/toolbar/__init__.py|self._domain_switch_ai.setChecked(dom == \"ai\")": (
        "the judgment-domain switch's checked state (222/238) — the "
        "metric-profile chip is deleted (2026-10-20); the switch itself goes "
        "in the W5 policy slice"
    ),
    "src/tabs/image_gallery/ui/toolbar/sort_picker.py|if owner.judgment_domain == \"ai\":": (
        "sort picker domain branch — W5/P9 (same surface as its domain read)"
    ),
    "src/tabs/image_gallery/ui/widget_parts/view_prefs.py|if _domain is not None and _domain != \"ai\":": (
        "view restore skips AI work outside the AI domain (33) — W5/P9 makes the "
        "read path level-triggered"
    ),
    # --- W5: controller / use-case gates collapse into the plan policy ------
    "src/tabs/image_gallery/controller.py|if str(getattr(self, \"_judgment_domain\", \"algorithms\") or \"\").strip().lower() != \"ai\":": (
        "the three ad-hoc AI-domain gates (708/906/1371) — W5 replaces them "
        "with the plan policy (plan §Gates G10)"
    ),
    "src/tabs/image_gallery/controller.py|and str(getattr(self, \"_judgment_domain\", \"algorithms\") or \"\")": (
        "AI-domain gate at 1035 — W5 policy slice"
    ),
    "src/tabs/image_gallery/controller.py|str(getattr(self, \"_judgment_domain\", \"algorithms\") or \"\")": (
        "AI-domain gate at 1111 — W5 policy slice"
    ),
    "src/tabs/image_gallery/use_cases/ai_analysis.py|_ai_debug(\"judgment domain -> %s (%s)\", dom, \"Jev on\" if dom == \"ai\" else \"Jev off\")": (
        "the switch's debug line (223) — deleted with the domain switch in W5 "
        "(a journal entry replaces the log line)"
    ),
    "src/tabs/image_gallery/use_cases/ai_analysis.py|if dom != \"ai\":": (
        "activate_judgment_domain's Jev-off gate (243) — W5: the policy decides, "
        "the resolver runs"
    ),
    "src/tabs/image_gallery/use_cases/large_drop_guard.py|return domain == \"ai\"": (
        "drop-guard domain predicate (61) — W5 policy slice"
    ),
    "src/tabs/image_gallery/use_cases/triage_run.py|if str(getattr(owner, \"_judgment_domain\", \"algorithms\") or \"\").strip().lower() != \"ai\":": (
        "three triage tails (582/594/613) — W5 tie-break becomes a declared plan "
        "step, gated by the resolver (defect B3)"
    ),
}


def _getattr_string(node: ast.Call) -> str | None:
    """The name in ``getattr(obj, "<name>"[, default])``, else ``None``."""
    if not (isinstance(node.func, ast.Name) and node.func.id == "getattr"):
        return None
    if len(node.args) < 2:
        return None
    name = node.args[1]
    if isinstance(name, ast.Constant) and isinstance(name.value, str):
        return name.value
    return None


def find_domain_read_hits(sources: dict[str, str]) -> dict[str, tuple[str, ...]]:
    """``path|line`` -> occurrences for every domain read in *sources*."""
    hits: dict[str, tuple[str, ...]] = {}
    for path in sorted(sources):
        source = sources[path]
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            attr: str | None = None
            note = ""
            if (
                isinstance(node, ast.Attribute)
                and node.attr in DOMAIN_ATTRS
                and isinstance(node.ctx, ast.Load)
            ):
                attr = node.attr
                note = f"attribute read .{attr}"
            elif isinstance(node, ast.Call):
                name = _getattr_string(node)
                if name in DOMAIN_ATTRS:
                    attr = name
                    note = f'getattr string read "{attr}"'
            if attr is not None:
                add_hit(
                    hits,
                    path=path,
                    lineno=node.lineno,
                    line=source_line(source, node.lineno),
                    note=note,
                )
    return hits


def find_ai_compare_hits(sources: dict[str, str]) -> dict[str, tuple[str, ...]]:
    """``path|line`` -> occurrences for every ``X == "ai"``-style gate."""
    hits: dict[str, tuple[str, ...]] = {}
    for path in sorted(sources):
        source = sources[path]
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            if not any(
                isinstance(op, ast.Constant) and op.value == AI_LITERAL
                for op in operands
            ):
                continue
            gate_ops = [
                type(op) for op in node.ops if isinstance(op, _COMPARE_OPS)
            ]
            if not gate_ops:
                continue
            add_hit(
                hits,
                path=path,
                lineno=node.lineno,
                line=source_line(source, node.lineno),
                note="operator " + "/".join(op.__name__ for op in gate_ops),
            )
    return hits


def _src_sources() -> dict[str, str]:
    return {rel(p): p.read_text(encoding="utf-8") for p in iter_py(SRC)}


# ---------------------------------------------------------------------------
# real tree
# ---------------------------------------------------------------------------


def test_domain_reads_are_only_the_allowlisted_sites():
    assert_ratchet(
        f"G2 judgment-domain reads ({PLAN})",
        DOMAIN_READ_ALLOWLIST,
        find_domain_read_hits(_src_sources()),
    )


def test_ai_literal_comparisons_are_only_the_allowlisted_gates():
    assert_ratchet(
        f"G10 ad-hoc `== \"ai\"` gates ({PLAN})",
        AI_COMPARE_ALLOWLIST,
        find_ai_compare_hits(_src_sources()),
    )


# ---------------------------------------------------------------------------
# falsifiability: the scanners flag fresh violations
# ---------------------------------------------------------------------------


def test_scanner_flags_attribute_and_getattr_domain_reads():
    src = (
        "def gated(owner, state):\n"
        "    if state.rank_domain:\n"
        "        return True\n"
        '    return str(getattr(owner, "_judgment_domain", "")).strip() == "ai"\n'
    )
    hits = find_domain_read_hits({"src/tabs/image_gallery/example.py": src})
    assert make_key(
        "src/tabs/image_gallery/example.py", "if state.rank_domain:"
    ) in hits
    assert make_key(
        "src/tabs/image_gallery/example.py",
        'return str(getattr(owner, "_judgment_domain", "")).strip() == "ai"',
    ) in hits
    assert len(hits) == 2


def test_scanner_flags_every_gate_operator():
    src = (
        "def g(dom, domains):\n"
        '    a = dom == "ai"\n'
        '    b = dom != "ai"\n'
        '    c = "ai" in domains\n'
        '    d = dom not in ("ai",)\n'
        "    return a, b, c, d\n"
    )
    hits = find_ai_compare_hits({"src/tabs/image_gallery/example.py": src})
    assert len(hits) == 3
    assert make_key("src/tabs/image_gallery/example.py", 'a = dom == "ai"') in hits
    assert make_key("src/tabs/image_gallery/example.py", 'b = dom != "ai"') in hits
    assert (
        make_key("src/tabs/image_gallery/example.py", 'c = "ai" in domains') in hits
    )


def test_scanner_ignores_writes_and_non_comparisons():
    """The `"ai"` that is not a gate — dict keys, i18n, Literal, calls, writes."""
    src = (
        "from typing import Literal\n"
        "Backend = Literal[\"ai\", \"algorithms\"]\n"
        'LABELS = {"ai": "Jev", "algorithms": "Fusion"}\n'
        'KEY = "image_gallery.domain.ai"\n'
        'def f(dom, table, owner, tr):\n'
        '    label = tr("image_gallery.domain.ai")\n'
        '    sub = table["ai"]\n'
        '    picked = _pick("ai")\n'
        '    owner._judgment_domain = "ai"\n'
        '    setattr(owner, "judgment_domain", "ai")\n'
        "    return label, sub, picked\n"
    )
    hits = {"src/tabs/image_gallery/example.py": src}
    assert find_ai_compare_hits(hits) == {}
    assert find_domain_read_hits(hits) == {}


def test_allowlists_are_shrink_only():
    """An entry whose code was fixed must fail the gate (real allowlists)."""
    for name, allowlist in (
        ("G2", DOMAIN_READ_ALLOWLIST),
        ("G10", AI_COMPARE_ALLOWLIST),
    ):
        if not allowlist:
            continue
        with pytest.raises(AssertionError, match="STALE"):
            assert_ratchet(f"{name} probe (empty scan)", allowlist, {})
