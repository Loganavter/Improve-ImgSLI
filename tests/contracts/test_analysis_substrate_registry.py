"""Contract tests: producer discovery is a directory scan, fail-soft, manifest-only.

Dogma source: ``PLAN.md`` §"Analyzers are auto-discovered producer packages"
(``plan-gallery-analysis-engine-2026-10-20``) — the same shape the canvas
feature registry already uses (docs/dev/rendering/package-structure.md §
Auto-Discovery): one package
per analyzer, metadata in ``manifest.py``, removal-safe.

Two traps the cases below pin, both live defects elsewhere in the tree:

- **Heavy imports stay inside ``run()``.** Discovery imports every manifest on
  every start; a manifest that pulls in a learned backend would load it for
  everyone (that is why the learned metrics seam imports lazily). The manifest
  import must therefore leave ``torch`` untouched.
- **A broken analyzer degrades itself, not the app.** A raising or missing
  manifest is skipped with a debug log; discovery never raises.

The fixtures build a throwaway package under ``tmp_path`` (with ``sys.path``
injection), which is also the proof that discovery is not hard-wired to the
gallery's real analyzers directory.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

from engine.analysis.contracts import ProducerSpec
from engine.analysis.registry import ProducerRegistry, discover

ALPHA = """
from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="alpha",
    provides={"sharpness": "measured", "noise": "measured"},
    requires=frozenset({"proxy"}),
    cost="free",
)
"""

BETA = """
from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="beta",
    provides={"aesthetic": "judgment", "sharpness": "measured"},
    requires=frozenset({"text"}),
    cost="per_image",
    automatic=True,
    max_per_run=3,
)
"""

GAMMA = """
from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="gamma",
    provides={"noise": "measured"},
    cost="free",
)
"""

BROKEN = """
raise RuntimeError("manifest exploded")
"""

NOT_A_SPEC = """
PRODUCER = {"id": "dict-shaped"}
"""


def _make_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    producers: dict[str, str | None],
) -> str:
    """Build an importable temp package with one sub-package per entry.

    A ``None`` source creates the sub-package without a ``manifest.py`` (an
    analyzer whose manifest is missing must be skipped, not fatal).
    """
    package_name = f"w1_producers_{uuid.uuid4().hex}"
    root = tmp_path / package_name
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    for name, source in producers.items():
        sub = root / name
        sub.mkdir()
        (sub / "__init__.py").write_text("", encoding="utf-8")
        if source is not None:
            (sub / "manifest.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return package_name


def _ids(specs) -> tuple[str, ...]:
    return tuple(spec.id for spec in specs)


def test_discovery_reads_manifests_sorted_and_skips_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _make_package(
        tmp_path,
        monkeypatch,
        {
            "zeta": BETA,  # directory order must not leak into registry order
            "alpha": ALPHA,
            "_scratch": GAMMA,  # a distinct id, so a missed skip shows up
            "no_manifest": None,
        },
    )

    registry = discover(package, force=True)

    assert _ids(registry.producers) == ("alpha", "beta")
    assert len(registry) == 2
    assert "alpha" in registry and "beta" in registry
    assert "gamma" not in registry and "zeta" not in registry
    assert registry.get("alpha") is registry.producers[0]
    assert registry.get("missing") is None
    assert f"{package}._scratch.manifest" not in sys.modules
    assert f"{package}.no_manifest.manifest" not in sys.modules


def test_axes_union_is_first_seen_and_filters_are_per_axis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _make_package(tmp_path, monkeypatch, {"alpha": ALPHA, "beta": BETA})
    registry = discover(package, force=True)

    assert registry.axes() == ("sharpness", "noise", "aesthetic")
    assert _ids(registry.by_axis("sharpness")) == ("alpha", "beta")
    assert registry.by_axis("unknown-axis") == ()
    # ``beta`` is automatic, so the local answer for ``sharpness`` is ``alpha``.
    assert registry.for_axis("sharpness") is registry.get("alpha")
    # Nothing non-automatic answers ``aesthetic`` -> the axis has no local answer.
    assert registry.for_axis("aesthetic") is None
    assert registry.for_axis("unknown-axis") is None


def test_for_axis_refuses_to_guess_between_two_local_producers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _make_package(
        tmp_path, monkeypatch, {"alpha": ALPHA, "gamma": GAMMA}
    )
    registry = discover(package, force=True)

    assert _ids(registry.by_axis("noise")) == ("alpha", "gamma")
    assert registry.for_axis("noise") is None


def test_broken_manifest_is_skipped_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _make_package(
        tmp_path, monkeypatch, {"alpha": ALPHA, "broken": BROKEN}
    )
    registry = discover(package, force=True)

    assert _ids(registry.producers) == ("alpha",)


def test_manifest_without_a_producer_spec_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _make_package(
        tmp_path, monkeypatch, {"alpha": ALPHA, "dict_shaped": NOT_A_SPEC}
    )
    registry = discover(package, force=True)

    assert _ids(registry.producers) == ("alpha",)


def test_discovery_never_imports_producer_modules_or_heavy_backends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _make_package(tmp_path, monkeypatch, {"heavy": ALPHA})
    (tmp_path / package / "heavy" / "producer.py").write_text(
        "import torch\n\n\ndef run(ctx):\n    return ()\n", encoding="utf-8"
    )
    # A session that already imported torch would make the negative unprovable;
    # drop the entry for the duration of the test (restored by monkeypatch).
    monkeypatch.delitem(sys.modules, "torch", raising=False)

    registry = discover(package, force=True)

    assert _ids(registry.producers) == ("alpha",)
    assert f"{package}.heavy.producer" not in sys.modules
    assert "torch" not in sys.modules


def test_discovery_is_process_cached_and_force_rescans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _make_package(tmp_path, monkeypatch, {"alpha": ALPHA, "beta": BETA})

    first = discover(package, force=True)
    assert discover(package) is first
    rescanned = discover(package, force=True)
    assert rescanned is not first
    assert _ids(rescanned.producers) == _ids(first.producers)


def test_unknown_package_degrades_to_an_empty_registry():
    registry = discover(f"w1_missing_package_{uuid.uuid4().hex}", force=True)

    assert isinstance(registry, ProducerRegistry)
    assert len(registry) == 0
    assert registry.axes() == ()
    assert registry.for_axis("sharpness") is None


def test_empty_package_name_is_refused():
    with pytest.raises(ValueError, match="package name"):
        discover("  ")


def test_registry_rejects_duplicate_ids():
    spec = ProducerSpec(id="alpha", provides={"sharpness": "measured"})
    with pytest.raises(ValueError, match="duplicate"):
        ProducerRegistry((spec, spec))
