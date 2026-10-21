"""Allowlist for the seven C1 canvas-hardening gates (shrink-only ratchet).

Wave C1 of the canvas hardening plan adds seven gates under
``tests/contracts/`` (``test_render_visibility_declared.py``,
``test_render_mode_declared.py``, ``test_no_duck_typed_arg_shuffle.py``,
``test_no_except_nameerror.py``, ``test_scene_order_table_complete.py``,
``test_capacity_agreement.py``,
``test_pass_discovery_raises_on_broken_import.py``). Each gate owns one slice
of the dict below, keyed by its file name; every slice is the same
``entry -> reason`` ratchet ``drain_guard_allowlist.py`` documents:

- a gate FAILS when it finds a violation with no entry (uncovered), and
- a gate FAILS when an entry no longer suppresses a finding (stale).

So the list can only shrink. An entry whose target is fixed must be deleted in
the SAME commit that fixes it — otherwise the owning gate goes red on the
stale half.

Entry shape: ``"<repo-relative path>"`` (whole file) or
``"<repo-relative path>::<symbol>"`` (one class / function / table). A symbol
is the last dotted component of the owning scope (``Class.method`` for a
method body). Every reason must name the wave that removes the entry (``C2`` /
``C3`` — the waves after C1) and the precondition for removing it; the
"real reason" half is enforced by ``allowlist_problems`` below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tests.contracts._framework import ROOT, read

#: Waves after C1 that are allowed to clear entries. A reason naming any other
#: wave is a planning error, not a get-out-of-jail card.
_REMOVING_WAVES = ("C2", "C3")

#: Shortest reason that can plausibly carry a wave + a precondition.
_MIN_REASON = 60


@dataclass(frozen=True)
class Finding:
    """One gate violation, addressable by an allowlist entry.

    ``path`` is repo-relative (use ``_framework.rel``); ``symbol`` is the
    class/function/table the violation lives in, or ``""`` for a whole-file
    finding (module-level literal, import shape, ...).
    """

    path: str
    symbol: str
    detail: str

    @property
    def key(self) -> str:
        return f"{self.path}::{self.symbol}" if self.symbol else self.path


#: gate file name -> {entry -> reason}. Namespaced by gate so a slice is
#: reviewable on its own and stale entries are attributed to one gate.
ALLOWLIST: dict[str, dict[str, str]] = {
    "test_render_visibility_declared.py": {},
    "test_no_duck_typed_arg_shuffle.py": {},
    "test_no_except_nameerror.py": {},
    "test_scene_order_table_complete.py": {
        "src/ui/canvas_infra/scene/stacking_policy.py::resolve_render_pass_order": (
            "the render-pass resolver still returns `_RENDER_PASS_ORDER.get(role, "
            "_RENDER_PASS_DEFAULT)`, so a CanvasStackRole without a row draws at "
            "a silent default. C2 switches it to `__getitem__`; precondition: "
            "grep every resolve_render_pass_order caller for a role that could "
            "arrive without a row, then add a test asserting an unknown role "
            "raises KeyError (the strictness must fail in a test, not a frame)."
        ),
        "src/ui/canvas_infra/scene/stacking_policy.py::resolve_scene_object_order": (
            "the scene-object resolver still returns `_SCENE_OBJECT_ORDER.get("
            "role, _SCENE_OBJECT_DEFAULT)`, so a missing role silently takes "
            "(OBJECT, 0). C2 switches it to `__getitem__`; precondition: land "
            "the HUD_INTERACTION_OVERLAY row FIRST (otherwise the strict "
            "resolver raises on that role), then grep the callers and add a "
            "test asserting an unknown role raises KeyError."
        ),
        "src/ui/canvas_infra/scene/stacking_policy.py::_SCENE_OBJECT_ORDER.HUD_INTERACTION_OVERLAY": (
            "`HUD_INTERACTION_OVERLAY` has no `_SCENE_OBJECT_ORDER` row, so it "
            "falls through to the default `(CanvasStackLayer.OBJECT, 0)` — the "
            "pair `IMAGE_OVERLAY_CONTENT` already owns, i.e. a real draw-order "
            "collision between the HUD interaction overlay and image content. "
            "C2 lands the row (adding the key changes draw order) with ONE live "
            "frame showing a HUD interaction overlay plus a negative control: "
            "without the key the collision check fails, with it the frame shows "
            "the overlay above the image content."
        ),
    },
    "test_capacity_agreement.py": {
        "src/tabs/image_compare/canvas/rhi_renderer/resources.py::_ARRAY_CAPACITY": (
            "the IC pool sizes its SRB-bound array for 2032 layers "
            "(_TILE_CACHE_BUDGET_BYTES // _ARRAY_LAYER_BYTES) while "
            "TileTextureService's default is 2048, so the service may hold 16 "
            "layers tile_arrays[0] cannot address. C3 makes the numbers agree "
            "(test-only fix: pass the computed capacity through every site "
            "below in the same commit, then delete this entry)."
        ),
        "src/tabs/image_compare/canvas/rhi_renderer/renderer.py::RhiCanvasRenderer.__init__": (
            "the renderer default-constructs its TileTextureService, so the "
            "service's 2048-layer default disagrees with the pool's 2032. C3 "
            "passes the computed capacity in here; precondition: the "
            "_ARRAY_CAPACITY entry above is cleared in the same commit and the "
            "image-compare render suite stays green."
        ),
        "src/tabs/image_compare/canvas/rhi_renderer/renderer.py::RhiCanvasRenderer.initialize": (
            "the re-init call passes max_tile_extent but not max_array_size, so "
            "a re-initialized renderer silently returns to the 2048 default "
            "against the pool's 2032. C3 passes the computed capacity here too "
            "(same commit as the other call sites); precondition: initialize() "
            "has a test that asserts the service limit matches the pool after a "
            "real re-init."
        ),
        "src/tabs/multi_compare/scene/renderer.py::MultiCompareRhiRenderer.__init__": (
            "the multi-compare renderer default-constructs its TileTextureService "
            "while its BaseImagesPass array is sized from the tab's own "
            "capacity derivation, so the allocator and the bound array can "
            "disagree. C3 passes the computed capacity in; precondition: the "
            "multi-compare render suite stays green with the explicit value."
        ),
        "src/tabs/multi_compare/scene/renderer.py::MultiCompareRhiRenderer.initialize": (
            "the multi-compare re-init call passes max_tile_extent but not "
            "max_array_size, so a re-initialized renderer falls back to the "
            "2048 default. C3 passes the computed capacity here too; "
            "precondition: a test asserts the service limit after re-init, and "
            "the same commit clears the __init__ entry above."
        ),
    },
    "test_pass_discovery_raises_on_broken_import.py": {
        "src/ui/canvas_infra/scene/registry.py::_iter_feature_modules": (
            "the feature-module iterator catches every ModuleNotFoundError and "
            "continues, so a broken transitive import inside an existing "
            "passes.py is indistinguishable from 'this feature has no "
            "passes.py' — its passes silently vanish from every frame. C3 "
            "narrows the catch to `exc.name == '<feature>.passes'` and lets "
            "every other ImportError propagate; precondition: this gate's "
            "three-feature probe stays green and the registry's own tests "
            "still cover a feature that genuinely ships no passes.py."
        ),
    },
}


def entries(gate: str) -> dict[str, str]:
    """The allowlist slice owned by *gate* (a ``test_*.py`` file name)."""
    return ALLOWLIST.get(gate) or {}


def entry_parts(entry: str) -> tuple[str, str]:
    """``"path::symbol"`` -> ``(path, symbol)``; ``symbol`` is ``""`` if absent."""
    path, _sep, symbol = entry.partition("::")
    return path, symbol


def _entry_matches(entry: str, finding: Finding) -> bool:
    path, symbol = entry_parts(entry)
    if path != finding.path:
        return False
    if not symbol:
        return True
    return symbol == finding.symbol


def allows(gate: str, finding: Finding) -> bool:
    return any(_entry_matches(entry, finding) for entry in entries(gate))


def unexplained(gate: str, findings: list[Finding]) -> list[Finding]:
    """Findings with no allowlist entry — the uncovered half of the ratchet."""
    return [finding for finding in findings if not allows(gate, finding)]


def format_findings(findings: list[Finding]) -> str:
    return "\n".join(f"  {f.key}: {f.detail}" for f in findings)


def allowlist_problems(gate: str, findings: list[Finding]) -> list[str]:
    """Shape *and* staleness problems for *gate*'s slice.

    Shape: the entry names a real file, a ``::symbol`` that actually occurs in
    it, and a substantive reason naming the removing wave and a precondition.
    Staleness: the entry must still suppress at least one current finding.
    """
    problems: list[str] = []
    slice_ = entries(gate)

    for entry, reason in slice_.items():
        path_text, symbol = entry_parts(entry)
        reason_text = reason.strip()

        if len(reason_text) < _MIN_REASON:
            problems.append(f"{entry}: reason is too short to state a wave + precondition")
        if "TODO" in reason_text or "FIXME" in reason_text:
            problems.append(f"{entry}: reason is a placeholder")
        if not any(wave in reason_text for wave in _REMOVING_WAVES):
            problems.append(
                f"{entry}: reason does not name the wave that removes it "
                f"({' / '.join(_REMOVING_WAVES)})"
            )

        path = ROOT / path_text
        if not path.is_file():
            problems.append(f"{entry}: no such file under the repository root")
            continue
        source = read(path)
        if symbol:
            last = symbol.rsplit(".", 1)[-1]
            if not re.search(rf"\b{re.escape(last)}\b", source):
                problems.append(
                    f"{entry}: symbol {symbol!r} does not occur in {path_text}"
                )

        if not any(_entry_matches(entry, finding) for finding in findings):
            problems.append(
                f"{entry}: stale entry — it no longer suppresses any finding of "
                f"{gate}; delete it in the commit that fixed the seam"
            )

    return problems
