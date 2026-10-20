"""W5: the gallery's local analyzers as auto-discovered producer packages.

``plan-gallery-analysis-engine-2026-10-20`` §"Analyzers are auto-discovered
producer packages": one package per analyzer, metadata in ``manifest.py``,
``run(ctx)`` in ``producer.py``, discovery by directory scan and removal-safe.

The cases below pin the four properties the wave exists for:

- the registry sees exactly nine producers with the full 18-axis vocabulary,
  and it sees them by importing manifests only (a manifest is imported on every
  start, so a heavy backend there would load for everyone);
- a producer is a pure function of ``AnalysisContext``: it never decodes (AST
  gate, plan G11), never touches the store, and answers missing inputs with
  ``status="gap"`` instead of a substituted number;
- artifacts are ``candidate`` flags whose value is a severity rank, not a
  0..100 quality score;
- deleting a producer package shrinks the vocabulary and raises nothing.
"""

from __future__ import annotations

import ast
import importlib
import shutil
import sys
import uuid
from pathlib import Path

import pytest

from engine.analysis.context import AnalysisContext
from engine.analysis.registry import discover

PRODUCERS = "tabs.image_gallery.analysis.producers"
PRODUCERS_DIR = Path(__file__).resolve().parents[1] / "analysis" / "producers"

CAMERA_AXES = ("sharpness", "exposure", "clipping", "noise", "white_balance")
FIDELITY_AXES = (
    "ssim",
    "detail_gain",
    "color_accuracy",
    "clipping_delta",
    "halo_delta",
    "chroma_fringe_delta",
)
ARTIFACT_AXES = (
    "banding",
    "halo",
    "over_smoothing",
    "invented_texture",
    "blocking",
    "chroma_fringing",
    "noise_amplification",
)
AXES = CAMERA_AXES + FIDELITY_AXES + ARTIFACT_AXES

PRODUCER_IDS = (
    "artifact_banding",
    "artifact_blocking",
    "artifact_chroma_fringing",
    "artifact_halo",
    "artifact_invented_texture",
    "artifact_noise_amplification",
    "artifact_over_smoothing",
    "camera_scalars",
    "fidelity_reference",
)


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _gradient(size: int = 64):
    """A decoded diode-free gradient: something every local detector can chew on."""
    from PIL import Image

    image = Image.new("RGB", (size, size))
    pixels = image.load()
    span = max(2 * (size - 1), 1)
    for y in range(size):
        for x in range(size):
            value = int((x + y) * 255 / span)
            pixels[x, y] = (value, value, value)
    return image


def _ctx(proxy: object | None = None, source: object | None = None, capabilities=()):
    return AnalysisContext(
        item_path="synthetic.png",
        mtime_ns=1,
        proxy_image=proxy,
        source_image=source,
        capabilities=frozenset(capabilities),
    )


def _run(package: str):
    return importlib.import_module(f"{PRODUCERS}.{package}.producer").run


ALPHA = """
from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="alpha",
    provides={"sharpness": "measured"},
    requires=frozenset({"images"}),
    cost="free",
)
"""

BETA = """
from engine.analysis.contracts import ProducerSpec

PRODUCER = ProducerSpec(
    id="beta",
    provides={"noise": "measured"},
    requires=frozenset({"images"}),
    cost="free",
)
"""


def _make_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    producers: dict[str, str],
) -> str:
    """A throwaway importable producers package, one sub-package per entry."""
    package_name = f"w5_producers_{uuid.uuid4().hex}"
    root = tmp_path / package_name
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    for name, source in producers.items():
        sub = root / name
        sub.mkdir()
        (sub / "__init__.py").write_text("", encoding="utf-8")
        (sub / "manifest.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return package_name


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_registry_discovers_exactly_nine_sorted_producers_and_18_axes():
    registry = discover(PRODUCERS, force=True)

    ids = tuple(spec.id for spec in registry.producers)
    assert ids == PRODUCER_IDS
    assert ids == tuple(sorted(ids)), (
        "discovery order must not leak into registry order"
    )
    assert set(registry.axes()) == set(AXES)
    assert len(registry.axes()) == 18
    assert registry.get("camera_scalars").requires == frozenset({"images"})
    assert registry.get("fidelity_reference").requires == frozenset(
        {"images", "reference"}
    )
    for axis in ARTIFACT_AXES:
        assert registry.get(f"artifact_{axis}").requires == frozenset({"images"})


def test_discovery_imports_manifests_only_not_producers_or_heavy_backends(
    monkeypatch: pytest.MonkeyPatch,
):
    """A manifest that pulled in torch would load it for every app start."""
    for name in list(sys.modules):
        if name.startswith(PRODUCERS + ".") and name.endswith(".producer"):
            monkeypatch.delitem(sys.modules, name)
    # A session that already imported a backend would make the negative
    # unprovable; drop the entries for the duration of the test.
    for heavy in ("torch", "piq"):
        monkeypatch.delitem(sys.modules, heavy, raising=False)

    registry = discover(PRODUCERS, force=True)

    assert len(registry) == 9
    assert "torch" not in sys.modules
    assert "piq" not in sys.modules
    leaked = [
        name
        for name in sys.modules
        if name.startswith(PRODUCERS + ".") and name.endswith(".producer")
    ]
    assert leaked == []


def test_every_manifest_declares_free_non_automatic_metadata_only():
    registry = discover(PRODUCERS, force=True)

    for spec in registry.producers:
        assert spec.cost == "free"
        assert spec.automatic is False, "the resolver decides when a producer runs"
    for axis in ARTIFACT_AXES:
        assert registry.get(f"artifact_{axis}").provides[axis] == "candidate"
    for axis in CAMERA_AXES + FIDELITY_AXES:
        assert (
            registry.get(
                "fidelity_reference" if axis in FIDELITY_AXES else "camera_scalars"
            ).provides[axis]
            == "measured"
        )


# ---------------------------------------------------------------------------
# run(ctx) — pure over the context
# ---------------------------------------------------------------------------


def test_camera_producer_scores_every_measured_axis_into_0_100():
    values = _run("camera_scalars")(_ctx(_gradient(), capabilities={"images"}))

    by_axis = {value.axis: value for value in values}
    assert tuple(by_axis) == CAMERA_AXES
    assert all(value.producer == "local" for value in values)
    measured = [value for value in values if value.status == "ok"]
    assert {value.axis for value in measured} >= {"sharpness", "exposure", "clipping"}
    for value in measured:
        assert value.value is not None
        assert 0.0 <= value.value <= 100.0
    # ``measure_camera_from_image`` reports no white balance: an explicit gap,
    # never a 0 that would read as "perfectly neutral".
    wb = by_axis["white_balance"]
    assert wb.status == "gap"
    assert wb.value is None
    assert wb.reason


def test_camera_producer_gaps_every_axis_without_an_image():
    values = _run("camera_scalars")(_ctx())

    assert tuple(value.axis for value in values) == CAMERA_AXES
    for value in values:
        assert value.status == "gap"
        assert value.value is None
        assert value.reason


def test_fidelity_below_a_reference_gaps_every_axis_with_a_reason():
    values = _run("fidelity_reference")(_ctx(_gradient(), capabilities={"images"}))

    assert tuple(value.axis for value in values) == FIDELITY_AXES
    for value in values:
        assert value.status == "gap"
        assert value.value is None
        assert value.reason


def test_fidelity_producer_measures_against_the_source():
    image = _gradient()
    values = _run("fidelity_reference")(
        _ctx(image, source=image.copy(), capabilities={"images", "reference"})
    )

    by_axis = {value.axis: value for value in values}
    assert tuple(by_axis) == FIDELITY_AXES
    # Identical images: the source-match axis must be measurable and maximal.
    assert by_axis["ssim"].status == "ok"
    assert by_axis["ssim"].value == 100.0
    for value in values:
        if value.status == "ok":
            assert 0.0 <= value.value <= 100.0


@pytest.mark.parametrize("axis", ARTIFACT_AXES)
def test_artifact_producer_returns_a_candidate_rank(axis: str):
    values = _run(axis)(_ctx(_gradient(), capabilities={"images"}))

    assert len(values) == 1
    value = values[0]
    assert value.axis == axis
    assert value.producer == "local"
    assert value.status == "ok"
    assert value.value in {0.0, 1.0, 2.0}
    # The manifest is the declaration a resolver reads: a flag, not a score.
    spec = discover(PRODUCERS).get(f"artifact_{axis}")
    assert spec.provides[axis] == "candidate"


@pytest.mark.parametrize("axis", ARTIFACT_AXES)
def test_artifact_producer_gaps_without_an_image(axis: str):
    value = _run(axis)(_ctx())[0]

    assert value.axis == axis
    assert value.status == "gap"
    assert value.value is None
    assert value.reason


# ---------------------------------------------------------------------------
# removal safety (plan G8)
# ---------------------------------------------------------------------------


def test_dropping_a_producer_package_shrinks_the_axes_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    package = _make_package(tmp_path, monkeypatch, {"alpha": ALPHA, "beta": BETA})
    first = discover(package, force=True)
    assert set(first.axes()) == {"sharpness", "noise"}

    shutil.rmtree(tmp_path / package / "beta")

    second = discover(package, force=True)
    assert second.axes() == ("sharpness",)
    assert tuple(spec.id for spec in second.producers) == ("alpha",)
    assert second.get("beta") is None


# ---------------------------------------------------------------------------
# no-decode gate (plan G11)
# ---------------------------------------------------------------------------


NO_DECODE_ATTRS = {"Image.open", "TiledPixelStore.from_path", "read_bytes"}
FORBIDDEN_MODULES = {"tabs.image_gallery.services.proxy"}
FORBIDDEN_MODULE_SUFFIXES = (".services.proxy",)


def _dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _producer_files() -> list[Path]:
    return sorted(PRODUCERS_DIR.rglob("*.py"))


def _decode_offences(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offences: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dotted = _dotted_name(node.func)
            if dotted in NO_DECODE_ATTRS or dotted.endswith(".read_bytes"):
                offences.append(f"{path.name}:{node.lineno}: {dotted}()")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_MODULES or alias.name.endswith(
                    FORBIDDEN_MODULE_SUFFIXES
                ):
                    offences.append(f"{path.name}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FORBIDDEN_MODULES or module.endswith(
                FORBIDDEN_MODULE_SUFFIXES
            ):
                offences.append(f"{path.name}:{node.lineno}: from {module} import ...")
    return offences


def test_producers_own_no_decode_and_never_import_the_proxy_builder():
    files = _producer_files()
    # Guard against a vacuous pass: 9 packages x (init, manifest, producer) + root.
    assert len(files) == 28, [path.name for path in files]

    offences = [offence for path in files for offence in _decode_offences(path)]
    assert offences == [], offences
