"""Ratchet: the AI judgment domain reads the VLM scorecard, never the detectors.

``plan-gallery-ai-backend-owns-quality-2026-10-16`` reverses the old
"detectors are authoritative / the AI never sets a measured number" doctrine: on
the AI domain the VLM's per-axis scorecard (``AiAnalysisResult.axes``) is the
item's quality read, and every surface reads it through ONE seam
(``services/quality_read``). This ratchet keeps the reversal from silently
regressing back into the field.

AST/text scan (no Qt import); the gallery's own ``tests`` are excluded. Each
scanner has a synthetic fixture proving a fresh violation is flagged, so the
guard is falsifiable — do NOT "fix the test", fix the code.
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, rel

PLAN = "plan-gallery-ai-backend-owns-quality-2026-10-16"
GALLERY = SRC / "tabs" / "image_gallery"
QUALITY_READ = GALLERY / "services" / "quality_read.py"
MODELS = GALLERY / "models.py"
METRICS = GALLERY / "ui" / "quick_look" / "metrics.py"
JEV = GALLERY / "services" / "jev_client.py"
#: The AI client source set: the old single module OR its package (the split
#: moved the prompt text to ``services/ai_client/prompt.py``).
AI_CLIENT_PREFIX = "/services/ai_client"

#: The reversed mechanism (plan §A2): merging detector numbers INTO the AI
#: result under the "detectors are authoritative" doctrine.
REVERSED_MECHANISM = "_merge_measured_metrics"

#: The reversed prompt instructions (plan §A1/§A4 grep targets). Their presence
#: in the analysis prompt means the old "one overall conclusion / do not
#: re-judge per axis" contract crept back.
REVERSED_PROMPT_PHRASES = (
    "treat them as authoritative",
    "do not restate",
    "measured metrics (authoritative)",
    "one overall conclusion instead",
)

#: The per-domain read seam API of plan §A2.
SEAM_API = ("domain_axis_scores", "ai_axis_scores", "domain_artifact_severity")


def _gallery_sources() -> dict[str, str]:
    return {rel(p): p.read_text(encoding="utf-8") for p in iter_py(GALLERY)}


# ---------------------------------------------------------------------------
# scanners (pure — the real tree and the fixtures both go through these)
# ---------------------------------------------------------------------------


def find_detector_merge_violations(sources: dict[str, str]) -> list[str]:
    """A ``_merge_measured_metrics`` definition re-introduces the reversed merge."""
    out: list[str] = []
    for path, src in sources.items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == REVERSED_MECHANISM:
                out.append(
                    f"{path}:{node.lineno}: `{REVERSED_MECHANISM}` re-introduces the "
                    f"reversed detector-merge into the AI result — the AI domain reads "
                    f"the VLM scorecard (plan {PLAN} §A2)."
                )
    return out


def find_prompt_doctrine_violations(sources: dict[str, str]) -> list[str]:
    """The analysis prompt must not re-state the reversed per-axis doctrine."""
    out: list[str] = []
    for path, src in sources.items():
        if not (
            path.endswith(AI_CLIENT_PREFIX + ".py") or AI_CLIENT_PREFIX + "/" in path
        ):
            continue
        low = src.lower()
        for phrase in REVERSED_PROMPT_PHRASES:
            if phrase in low:
                out.append(
                    f"{path}: the analysis prompt re-states the reversed doctrine "
                    f"{phrase!r} (plan {PLAN} §A1/§A4)."
                )
    return out


def find_ai_read_seam_violations(sources: dict[str, str]) -> list[str]:
    """The single per-domain read seam must exist and be used by the AI surfaces."""
    out: list[str] = []
    qr = sources.get(rel(QUALITY_READ))
    if not qr:
        return [
            f"{rel(QUALITY_READ)} is missing — the single per-domain read seam of "
            f"plan {PLAN} §A2 is gone."
        ]
    for fn in SEAM_API:
        if f"def {fn}(" not in qr:
            out.append(
                f"{rel(QUALITY_READ)}: `{fn}` is missing — the AI-domain read seam "
                f"must expose it (plan {PLAN} §A2)."
            )
    for surface in (rel(METRICS), rel(JEV)):
        src = sources.get(surface)
        if not src:
            out.append(f"{surface} is missing from the scanned gallery sources.")
            continue
        if "quality_read" not in src or "domain_axis_scores" not in src:
            out.append(
                f"{surface}: reads quality off ``item.metrics``/``item.analysis`` "
                f"directly — route the AI vs Algorithms read through "
                f"``services.quality_read.domain_axis_scores`` (plan {PLAN} §A2/§A3)."
            )
    return out


def find_scorecard_field_violations(sources: dict[str, str]) -> list[str]:
    """``AiAnalysisResult`` must carry the open ``axes`` scorecard (plan §A1)."""
    src = sources.get(rel(MODELS), "")
    if not src:
        return [f"{rel(MODELS)} is missing from the scanned gallery sources."]
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AiAnalysisResult":
            fields = {
                n.target.id
                for n in node.body
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            }
            if "axes" not in fields:
                return [
                    f"{rel(MODELS)}: `AiAnalysisResult.axes` (the open per-axis "
                    f"scorecard) is gone (plan {PLAN} §A1)."
                ]
            return []
    return [f"{rel(MODELS)}: `AiAnalysisResult` class not found (plan {PLAN} §A1)."]


# ---------------------------------------------------------------------------
# real-tree checks
# ---------------------------------------------------------------------------


def test_controller_has_no_detector_merge_into_the_ai_result():
    assert not find_detector_merge_violations(_gallery_sources())


def test_ai_analysis_prompt_is_not_the_reversed_doctrine():
    assert not find_prompt_doctrine_violations(_gallery_sources())


def test_ai_surfaces_read_through_the_seam():
    assert not find_ai_read_seam_violations(_gallery_sources())


def test_ai_analysis_result_carries_the_open_scorecard():
    assert not find_scorecard_field_violations(_gallery_sources())


# ---------------------------------------------------------------------------
# falsifiability fixtures — a fresh violation must be flagged
# ---------------------------------------------------------------------------


def test_guard_flags_a_reintroduced_detector_merge():
    src = (
        "class GalleryController:\n"
        "    def _merge_measured_metrics(self, result, item):\n"
        "        return result\n"
    )
    violations = find_detector_merge_violations({"src/tabs/image_gallery/controller.py": src})
    assert len(violations) == 1
    assert REVERSED_MECHANISM in violations[0]
    assert PLAN in violations[0]


def test_guard_flags_the_reversed_prompt_phrasing():
    src = 'PROMPT = "You are given the locally measured metrics; treat them as authoritative"\n'
    violations = find_prompt_doctrine_violations(
        {"src/tabs/image_gallery/services/ai_client/prompt.py": src}
    )
    assert len(violations) == 1
    assert PLAN in violations[0]


def test_guard_flags_a_surface_reading_detectors_directly():
    read = (
        "def domain_axis_scores(item, *, domain): ...\n"
        "def ai_axis_scores(item): ...\n"
        "def domain_artifact_severity(item, artifact, *, domain): ...\n"
    )
    bad = "def rebuild_metrics(overlay, item, is_fidelity, mode_str):\n    m = item.metrics\n"
    sources = {
        rel(QUALITY_READ): read,
        rel(METRICS): bad,
        rel(JEV): "quality_read.domain_axis_scores(item, domain='ai')\n",
    }
    violations = find_ai_read_seam_violations(sources)
    assert len(violations) == 1
    assert rel(METRICS) in violations[0]
    assert PLAN in violations[0]


def test_guard_flags_a_missing_scorecard_field():
    src = (
        "class AiAnalysisResult:\n"
        "    sharpness: int = -1\n"
    )
    violations = find_scorecard_field_violations({"src/tabs/image_gallery/models.py": src})
    assert len(violations) == 1
    assert "axes" in violations[0]


def test_guard_allows_a_clean_seam():
    read = (
        "def domain_axis_scores(item, *, domain): ...\n"
        "def ai_axis_scores(item): ...\n"
        "def domain_artifact_severity(item, artifact, *, domain): ...\n"
    )
    good = "from tabs.image_gallery.services import quality_read\nx = quality_read.domain_axis_scores(i, domain='ai')\n"
    sources = {rel(QUALITY_READ): read, rel(METRICS): good, rel(JEV): good}
    assert find_ai_read_seam_violations(sources) == []
