"""INVARIANT (ADR 009 A3): pairwise is a CAPABILITY of the AI backend.

The A/B refinement is a paid VLM pass that refines a VLM order. ADR 009 says a
capability is *requested from the descriptor, never assumed* — so the request
goes through the owning adapter, and the backend that never declared it refuses
by name:

* ``CapabilityNotDeclared`` from the Algorithms adapter (its declared set is
  ``measure``/``rank``/``profile``/``reset``) — both through the composition
  helper the production trigger calls and through the adapter's own
  ``require_pairwise``;
* the Algorithms RANK refuses a ``pairwise_order`` for the same reason: the A/B
  order is a model verdict, and a local rank that accepted it could be reordered
  by a judge that never measured the items;
* the AI adapter declares it, its ``require_pairwise`` passes, and its rank
  applies the documented subset rule (named paths take the leading ranks, every
  other member follows the measured order).

Falsification story (red on the A2 base): ``start_pairwise_refinement`` reached
``pairwise_rank`` for ANY domain owner (the pass itself then re-checked the
domain in three places), and ``capabilities`` was a declaration nothing read —
``require_capability`` had no caller outside the contract's own tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tabs.image_gallery.backends import (
    BackendMismatch,
    CapabilityNotDeclared,
    MeasureRequest,
    OwnedProfile,
    PAIRWISE_CAPABILITY,
    ProfileRequest,
    RankRequest,
)
from tabs.image_gallery.backends.ai import BACKEND as AI_BACKEND
from tabs.image_gallery.backends.algorithms import BACKEND as ALGORITHMS_BACKEND
from tabs.image_gallery.backends.composition import backend, pairwise_backend
from tabs.image_gallery.backends.context import SeriesContext, owned_profile
from tabs.image_gallery.models import AiAnalysisResult, GalleryItem, GalleryState
from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.metric_profile import DOMAIN_AI, DOMAIN_ALGORITHMS


def _item(name: str, *, variation: int) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update({"sharpness": 200.0, "noise": 0.2})
    item.analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="judge-model",
        analyzed_at_iso="t",
        axes={"sharpness": variation, "noise": variation},
    )
    return item


def _owned_algorithms_profile(members):
    return ALGORITHMS_BACKEND.make_profile(
        ProfileRequest(mode="camera"), context=SeriesContext(members=tuple(members))
    )


def _owned_ai_profile():
    """A judge profile this AI adapter made (its real ``install`` seam)."""
    from tabs.image_gallery.services.metric_profile import MetricProfile

    AI_BACKEND.reset()  # process singleton: a clean generation for this test
    profile = MetricProfile(
        axis_ids=("sharpness", "noise"), mode="camera", source="vlm"
    )
    AI_BACKEND.install(GalleryState(mode="camera"), profile)
    return owned_profile(AI_BACKEND.descriptor, profile)


def test_the_algorithms_adapter_does_not_declare_pairwise() -> None:
    assert PAIRWISE_CAPABILITY not in ALGORITHMS_BACKEND.descriptor.capabilities

    with pytest.raises(CapabilityNotDeclared) as excinfo:
        ALGORITHMS_BACKEND.require_pairwise()

    message = str(excinfo.value)
    assert DOMAIN_ALGORITHMS in message and PAIRWISE_CAPABILITY in message, (
        "the refusal must name the backend AND the capability: " + message
    )
    assert excinfo.value.declared == ALGORITHMS_BACKEND.descriptor.capabilities


def test_the_composition_helper_refuses_the_algorithms_backend() -> None:
    """The production request point asks THIS helper (the call site)."""
    with pytest.raises(CapabilityNotDeclared):
        pairwise_backend(DOMAIN_ALGORITHMS)

    assert pairwise_backend(DOMAIN_AI) is backend(DOMAIN_AI)


def test_the_ai_adapter_declares_pairwise() -> None:
    assert PAIRWISE_CAPABILITY in AI_BACKEND.descriptor.capabilities
    assert AI_BACKEND.require_pairwise() is None


def test_the_algorithms_rank_refuses_a_pairwise_order() -> None:
    members = [_item("a.png", variation=80), _item("b.png", variation=60)]
    owned = _owned_algorithms_profile(members)

    with pytest.raises(CapabilityNotDeclared):
        ALGORITHMS_BACKEND.rank(
            RankRequest(profile=owned, pairwise_order=(str(members[1].path),)),
            context=SeriesContext(members=tuple(members)),
        )


def test_the_ai_rank_applies_a_declared_pairwise_order(tmp_path) -> None:
    a, b = _item("a.png", variation=80), _item("b.png", variation=60)
    members = [a, b]
    owned = _owned_ai_profile()

    def _client(_payload):
        # The judge's own pointwise order: a (80) above b (60).
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"ranking": ["img_1", "img_2"]})
                    }
                }
            ]
        }

    pointwise = AI_BACKEND.rank(
        RankRequest(profile=owned),
        context=SeriesContext(
            members=tuple(members),
            client=_client,
            cache=jev_cache.JevRankCache(tmp_path / "pointwise"),
        ),
    )
    assert pointwise.ranks == {str(a.path): 1, str(b.path): 2}, (
        f"fixture sanity: the judge ranked the higher score first: {pointwise.ranks}"
    )

    reordered = AI_BACKEND.rank(
        RankRequest(profile=owned, pairwise_order=(str(b.path), str(a.path))),
        context=SeriesContext(
            members=tuple(members),
            client=_client,
            cache=jev_cache.JevRankCache(tmp_path / "pairwise"),
        ),
    )
    assert reordered.ranks == {str(b.path): 1, str(a.path): 2}, (
        "the declared capability's order must lead: " + repr(reordered.ranks)
    )


def test_an_ai_envelope_still_cannot_be_ranked_by_the_algorithms_backend() -> None:
    """Defence in depth: the capability seam does not widen the ownership seam."""
    members = [_item("a.png", variation=80), _item("b.png", variation=60)]
    foreign = OwnedProfile(
        backend_id=DOMAIN_AI,
        profile_id="ai:test",
        schema_version=AI_BACKEND.descriptor.schema_version,
        axes=("sharpness",),
    )

    with pytest.raises(BackendMismatch):
        ALGORITHMS_BACKEND.rank(
            RankRequest(profile=foreign), context=SeriesContext(members=tuple(members))
        )
    with pytest.raises(BackendMismatch):
        ALGORITHMS_BACKEND.measure(
            MeasureRequest(profile=foreign), context=SeriesContext(members=tuple(members))
        )
