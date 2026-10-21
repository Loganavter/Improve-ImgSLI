"""GA4 contract: the analysis cache identity names what produced the numbers.

``plan-gallery-ai-judgement-2026-10-21`` §Gates GA4 / §Invariants M4
("reproducible within a stated tolerance") and verified defect **J5**: the
identity that keys (and validates) a cached scorecard carries model, base_url,
mode, profile, reasoning_effort and the prompt schema
(``services/ai_cache.py:65-72``, built by ``analysis_cache_identity``) — and
NOTHING about how the sample was drawn. With no ``k`` / ``temperature`` /
``seed`` in the key, "one stochastic sample frozen as truth" is unavoidable: a
k=1 sample and a k=3 median land on the same cache entry, and two orders 90 s
apart differed by 12-23 points on axes whose variants differ by 2-6.

Two halves, because either alone is bypassable:

* AST — the declared field list ``_IDENTITY_FIELDS`` must name the sampling
  configuration. This is the identity's own declaration, so no call site can
  quietly opt out.
* runtime — ``analysis_cache_identity(...)`` must RETURN those keys (with
  defaults, i.e. the field exists even when the value is unset — an identity
  whose shape depends on whether a value was passed cannot be compared), and
  ``_canonical_identity`` (the normalizer used on BOTH sides of the payload
  check and for the filename digest) must keep them. Adding a field to the
  tuple alone would key the filename and then strip it from the comparison —
  the silent-divergence bug this gate exists to prevent.

Red-before: the identity has no k/temperature/seed field, in either half.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ._framework import SRC, parse

from tabs.image_gallery.services import ai_cache

GATE = "GA4"
PLAN = "plan-gallery-ai-judgement-2026-10-21"

AI_CACHE_PATH = SRC / "tabs" / "image_gallery" / "services" / "ai_cache.py"

_ALLOWLIST = Path(__file__).with_name("gallery_judge_allowlist.txt")

#: Accepted spellings per sampling-concern. Deliberately a small closed set: a
#: gate that accepts any name accepts nothing.
SAMPLING_FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "sample count (k)": (
        "k",
        "k_samples",
        "samples",
        "sample_count",
        "n_samples",
        "draws",
    ),
    "temperature": ("temperature", "temp", "sampling_temperature"),
    "seed": ("seed", "sampling_seed", "seed_value"),
    "schema version": (
        "prompt_schema_version",
        "schema_version",
        "analysis_schema_version",
    ),
}


def _allowlisted(gate: str) -> bool:
    """True while *gate* still has a line in the shrink-only ledger."""
    for raw in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        gate_id = raw.split("#", 1)[0].split("|", 1)[0].strip()
        if gate_id == gate:
            return True
    return False


def _missing_groups(keys) -> list[str]:  # type: ignore[no-untyped-def]
    """Human-readable list of sampling concerns *keys* does not name."""
    present = {str(key).strip().lower() for key in keys}
    return [
        label
        for label, spellings in SAMPLING_FIELD_GROUPS.items()
        if not present.intersection(spellings)
    ]


def _declared_identity_fields() -> tuple[set[str], list[str]]:
    """``(_IDENTITY_FIELDS`` string members, problems) from the module AST."""
    tree = parse(AI_CACHE_PATH)
    if tree is None:
        return set(), [f"{AI_CACHE_PATH.name} does not parse"]
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        if not (
            len(targets) == 1
            and isinstance(targets[0], ast.Name)
            and targets[0].id == "_IDENTITY_FIELDS"
        ):
            continue
        if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
            return (
                {
                    element.value
                    for element in value.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                },
                [],
            )
        return set(), ["_IDENTITY_FIELDS is no longer a literal tuple of names"]
    return set(), [
        "ai_cache declares no _IDENTITY_FIELDS tuple — the analysis identity has "
        "lost its single declaration"
    ]


@pytest.mark.xfail(
    condition=_allowlisted(GATE),
    reason=(
        "GA4 red-before (plan-gallery-ai-judgement-2026-10-21 §Gates GA4 / J5): "
        "ai_cache._IDENTITY_FIELDS (65-72) and analysis_cache_identity() carry "
        "no sampling config (k / temperature / seed), so two draws of the same "
        "stochastic judge share one cache entry. P3 deletes this line."
    ),
    strict=True,
    raises=AssertionError,
)
def test_the_analysis_identity_carries_the_sampling_config_and_schema() -> None:
    problems: list[str] = []

    declared, ast_problems = _declared_identity_fields()
    problems += ast_problems
    if declared:
        missing = _missing_groups(declared)
        if missing:
            problems.append(
                f"_IDENTITY_FIELDS names no {', '.join(missing)} "
                f"(declared: {sorted(declared)})"
            )

    identity = ai_cache.analysis_cache_identity(mode="camera")
    missing_runtime = _missing_groups(identity)
    if missing_runtime:
        problems.append(
            "analysis_cache_identity() returns no "
            f"{', '.join(missing_runtime)} (returns: {sorted(identity)})"
        )

    canonical = ai_cache._canonical_identity(identity)
    if canonical is None:
        problems.append(
            "_canonical_identity() rejects the identity it was just given — the "
            "payload check and the filename digest cannot see this configuration"
        )
    else:
        missing_canonical = _missing_groups(canonical)
        if missing_canonical:
            problems.append(
                "_canonical_identity() drops the "
                f"{', '.join(missing_canonical)} — a field that reaches the "
                "filename but not the comparison is a silent divergence"
            )

    assert not problems, (
        "GA4 (M4 reproducible): a cached scorecard must be keyed by the "
        "sampling configuration and the schema it answered, not only by the "
        "backend:\n" + "\n".join(f"- {problem}" for problem in problems)
    )


def test_the_identity_never_carries_the_api_key() -> None:
    """Pinned green invariant: the identity is hashed and stored on disk."""
    identity = ai_cache.analysis_cache_identity(mode="camera")
    assert "api_key" not in identity
    assert "test-key" not in str(identity)


def test_the_sampling_vocabulary_is_closed_and_discriminating() -> None:
    """The gate's own predicate must be able to say "no" (falsifiability)."""
    today = {"model", "base_url", "mode", "profile", "reasoning_effort",
             "prompt_schema_version"}
    assert _missing_groups(today) == ["sample count (k)", "temperature", "seed"]
    complete = today | {"k", "temperature", "seed"}
    assert _missing_groups(complete) == []
    # ``scores``/``skew`` are not the sample count.
    assert "sample count (k)" in _missing_groups({"scores", "skew", "scheme"})
