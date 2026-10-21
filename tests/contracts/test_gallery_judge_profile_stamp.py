"""GA3 contract: the profile freeze is stamped only when a payload was built.

``plan-gallery-ai-judgement-2026-10-21`` §Gates GA3 / §Invariants M5 ("legible":
every loss is a visible state with a cause) and verified defect **J3**:

``GalleryController.analyze`` / ``reanalyze`` / ``_run_ai_for_visible`` call
``_stamp_profile_consumed(self)`` BEFORE the delegate runs (``controller.py``
1124 / 1131 / 1187), and the stamp writes ``_profile_consumed_gen``
(``_mark_profile_consumed``, 727-739). Nothing on that path asks whether a
request payload was built. So a run whose every card is a disk-cache HIT
(0 API calls) freezes the generation anyway, and the paid VLM axis-set answer
arriving for it is dropped as "late — AI calls already built under it"
(``_apply_profile_outcome``, 777-795). The parenthetical was false for that run
in the 2026-10-21 live log (six HITs at 19:11:49 → late reply dropped at
19:11:52).

The gate drives the REAL entry (``GalleryController.analyze`` → real
``ai_analyze.analyze`` → real ``_analyze_ai``) over an all-HIT cache seam and
asserts the generation stays unfrozen. Red-before: ``_profile_consumed_gen``
is already ``0`` when the delegate is reached.

The companion green test ("the freeze is still wired somewhere") refuses the
cheap repair of deleting the freeze: P2 must MOVE the stamp to the payload-build
site, not drop it — a profile is part of the cache identity, so a mid-generation
replacement still has to be rejected once a request exists.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from ._framework import SRC, iter_py

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAnalysisResult, GalleryItem
from tabs.image_gallery.use_cases import ai_analyze
from tabs.image_gallery.use_cases.action_context import (
    BACKEND_AI,
    ActionContext,
)

GATE = "GA3"
PLAN = "plan-gallery-ai-judgement-2026-10-21"

GALLERY = SRC / "tabs" / "image_gallery"

_ALLOWLIST = Path(__file__).with_name("gallery_judge_allowlist.txt")


def _allowlisted(gate: str) -> bool:
    """True while *gate* still has a line in the shrink-only ledger."""
    for raw in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        gate_id = raw.split("#", 1)[0].split("|", 1)[0].strip()
        if gate_id == gate:
            return True
    return False


class _CacheHitOwner:
    """Duck-typed controller: real analyze entry, real ``_analyze_ai``, no Qt.

    ``_begin_analysis`` is the payload-build seam — the ONE place a request is
    constructed (``ai_analyze._analyze_ai`` calls it for every MISS). It is
    recorded instead of executed, so "was a payload built" is an observed fact,
    not an assumption of the test.
    """

    def __init__(self, paths: tuple[Path, ...]) -> None:
        self.state = SimpleNamespace(
            items=[GalleryItem(path=path, mtime_ns=0) for path in paths],
            mode="fidelity",
            metric_profile=None,
        )
        self.widget = SimpleNamespace(
            visible_paths=lambda: [str(p) for p in paths],
            refresh_card=self._refresh_card,
        )
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                model="m",
                base_url="https://example.invalid/v1",
                reasoning_effort="auto",
                enabled=True,
                api_key="test-key-not-a-secret",
            )
        )
        self._folder_gen = 0
        self._profile_consumed_gen: int | None = None
        self.refreshed: list[str] = []
        self.payloads: list[str] = []

    def _refresh_card(self, item) -> None:  # type: ignore[no-untyped-def]
        self.refreshed.append(str(item.path))

    def _mark_profile_consumed(self) -> None:
        GalleryController._mark_profile_consumed(self)

    def _begin_analysis(self, ctx, item) -> None:  # type: ignore[no-untyped-def]
        self.payloads.append(str(item.path))

    def _tr(self, key: str, default: str) -> str:
        return default

    def _is_current_folder_gen(self, gen: int) -> bool:
        return True


@pytest.mark.xfail(
    condition=_allowlisted(GATE),
    reason=(
        "GA3 red-before (plan-gallery-ai-judgement-2026-10-21 §Gates GA3 / J3): "
        "controller.analyze stamps the profile freeze before the delegate runs "
        "(controller.py:1124), so an all-HIT run freezes the generation with no "
        "request payload built. P2 deletes this line."
    ),
    strict=True,
    raises=AssertionError,
)
def test_a_cache_only_analyze_run_does_not_freeze_the_profile(monkeypatch) -> None:
    paths = (Path("/gallery/hit_1.png"), Path("/gallery/hit_2.png"))
    cached = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes={"ssim": 80}
    )
    # The identity machinery is not what this gate is about: pin the seam so the
    # run is driven by ONE fact — every card is a HIT.
    monkeypatch.setattr(
        ai_analyze, "load_cached_analysis", lambda path, mtime, identity: cached
    )
    monkeypatch.setattr(
        ai_analyze, "analysis_identity_for", lambda owner, ctx=None: {"model": "m"}
    )

    owner = _CacheHitOwner(paths)
    ctx = ActionContext(targets=paths, backend=BACKEND_AI, mode="fidelity")

    assert GalleryController.analyze(owner, ctx) is None
    assert owner.refreshed == [str(p) for p in paths], (
        "the fixture must take the real all-HIT branch (refresh per card); a "
        "changed ai_analyze flow means this gate's seam moved"
    )
    assert owner.payloads == [], "a cache HIT builds no request payload"
    assert owner._profile_consumed_gen is None, (
        "GA3: a cache-only run froze the folder-generation profile "
        f"(_profile_consumed_gen={owner._profile_consumed_gen!r}) although no "
        "request payload was built — the next VLM axis-set answer for this "
        "generation is then dropped as 'late' with a false reason"
    )


def test_the_profile_freeze_is_still_wired_somewhere() -> None:
    """Deleting the freeze is not a fix: P2 moves it to the payload-build site.

    A profile is part of the analysis cache identity, so once a request of a
    generation exists the profile may no longer change (that is what keeps the
    scorecards readable by the next open). If no code calls the stamp at all,
    GA3 has been "fixed" by removing the invariant instead of relocating it.
    """
    callers: list[str] = []
    for path in iter_py(GALLERY):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, (ast.Name, ast.Attribute))
            ):
                name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                )
                if name in {"_stamp_profile_consumed", "_mark_profile_consumed"}:
                    callers.append(f"{path.relative_to(GALLERY).as_posix()}:{node.lineno}")
    assert callers, (
        "nothing calls _stamp_profile_consumed/_mark_profile_consumed under "
        "src/tabs/image_gallery — the freeze was deleted instead of moved to "
        "the payload-build site (plan P2)"
    )
    assert hasattr(GalleryController, "_mark_profile_consumed"), (
        "GalleryController._mark_profile_consumed is the stamp writer; keep it "
        "and call it from the request builder"
    )
