"""Contract tests: model identity lives only in the catalog, and it refuses.

Dogma source: ``PLAN.md`` §Invariants I2 ("no producer names a model") and
§Gates G1 (``test_analysis_no_model_literals.py``) in
``plan-gallery-analysis-engine-2026-10-20``.

The veto case is the source scan: a vendor model id (``vendor/model``) inside
the catalog module is exactly the per-path constant the module exists to
remove, so its presence must fail even though the code would still run. The
resolution cases then pin the refusals: an unknown provider, an empty model
and a provider left without a URL all raise a readable ``CatalogError`` instead
of resolving to a guess.
"""

from __future__ import annotations

import ast
import re

import pytest

from engine.analysis.catalog import (
    DEFAULT_PRESETS,
    CatalogError,
    presets,
    resolve,
    resolve_requirement,
)
from engine.analysis.contracts import BackendRef

from ._framework import SRC

CATALOG = SRC / "engine" / "analysis" / "catalog.py"

#: A vendor model id: one ``vendor/model`` token. The tree already carries such
#: literals on network paths; none of them may appear in the catalog module.
_VENDOR_MODEL = re.compile(r"^[a-z0-9_-]+/[a-z0-9._-]+$")


def test_catalog_source_holds_no_vendor_model_ids():
    source = CATALOG.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _VENDOR_MODEL.fullmatch(node.value)
    ]
    assert not offenders, (
        "catalog.py must not name a model id (it is the per-path constant the "
        f"catalog removes); found {offenders}"
    )
    # The known offender on today's network paths, called out explicitly so the
    # scan above cannot silently weaken into a no-op.
    assert "typesafe/jev-router" not in source


def test_unknown_provider_is_refused():
    with pytest.raises(CatalogError, match="unknown provider"):
        resolve("not-a-provider", "some-model")


def test_empty_model_is_refused():
    # A path must not invent a model: empty/whitespace is a refusal, not a
    # fallback to the preset's default (presets carry no model in this wave).
    with pytest.raises(CatalogError, match="no model"):
        resolve("openrouter", "   ")


def test_user_base_url_wins_over_the_preset():
    ref = resolve(
        "openrouter", "some-model", user_base_url="https://proxy.invalid/v1"
    )
    assert ref.base_url == "https://proxy.invalid/v1"
    assert ref.provider == "openrouter"
    assert ref.model == "some-model"


def test_preset_base_url_is_the_default():
    preset = next(p for p in presets() if p.id == "openrouter")
    assert resolve("openrouter", "some-model").base_url == preset.base_url


def test_custom_provider_requires_the_user_url():
    with pytest.raises(CatalogError, match="base_url"):
        resolve("custom", "some-model")
    ref = resolve("custom", "some-model", user_base_url="http://127.0.0.1:9999/v1")
    assert ref.base_url == "http://127.0.0.1:9999/v1"


def test_resolved_ref_is_valid_hashable_and_frozen():
    ref = resolve("llamacpp", "local-model", params={"temperature": 0})
    assert isinstance(ref, BackendRef)
    assert hash(ref) == hash(ref)
    with pytest.raises(TypeError):
        ref.params["temperature"] = 1  # type: ignore[index]


def test_resolve_requirement_reads_the_declared_keys():
    ref = resolve_requirement(
        {
            "provider": "openrouter",
            "model": "some-model",
            "base_url": "https://proxy.invalid/v1",
            "params": {"effort": "low"},
        }
    )
    assert (ref.provider, ref.model, ref.base_url) == (
        "openrouter",
        "some-model",
        "https://proxy.invalid/v1",
    )
    assert dict(ref.params) == {"effort": "low"}


def test_resolve_requirement_refuses_missing_and_malformed_parts():
    with pytest.raises(CatalogError, match="no model"):
        resolve_requirement({"provider": "openrouter", "base_url": ""})
    with pytest.raises(CatalogError, match="mapping"):
        resolve_requirement(["provider", "openrouter"])  # type: ignore[arg-type]
    with pytest.raises(CatalogError, match="params"):
        resolve_requirement(
            {"provider": "openrouter", "model": "some-model", "params": "effort=low"}
        )
    with pytest.raises(CatalogError, match="base_url"):
        resolve_requirement(
            {"provider": "openrouter", "model": "some-model", "base_url": 7}
        )


def test_presets_are_unique_and_resolvable():
    ids = [preset.id for preset in presets()]
    assert ids and len(ids) == len(set(ids))
    assert tuple(presets()) == DEFAULT_PRESETS
    for preset in presets():
        if not preset.base_url:
            continue  # ``custom``: the user owns the URL, covered above
        assert resolve(preset.id, "some-model").base_url == preset.base_url
    # This wave ships no curated model lists (they arrive with the app-side
    # table); a non-empty list here would be an un-wired second vocabulary.
    assert all(preset.models == () for preset in presets())
