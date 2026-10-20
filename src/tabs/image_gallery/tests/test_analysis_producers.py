"""W5/W6: the gallery's analyzers as auto-discovered producer packages.

``plan-gallery-analysis-engine-2026-10-20`` §"Analyzers are auto-discovered
producer packages": one package per analyzer, metadata in ``manifest.py``,
``run(ctx)`` in ``producer.py``, discovery by directory scan and removal-safe.

The cases below pin the properties the waves exist for:

- the registry sees exactly four producers with the full 23-axis vocabulary,
  and it sees them by importing manifests only (a manifest is imported on every
  start, so a heavy backend there would load for everyone);
- a producer is a pure function of ``AnalysisContext``: it never decodes (AST
  gate, plan G11), never touches the store, and answers missing inputs with
  ``status="gap"`` instead of a substituted number;
- artifacts are ``candidate`` flags whose value is a severity rank, not a
  0..100 quality score, and they come from the one aggregate the report uses
  (``artifacts.analyze_images``), not from seven independently wrapped detectors
  — the W7 dark launch showed the two can disagree on the anchored axes;
- the AI scorecard (network path 1, W6) is a producer like any other: its model
  arrives as a ``BackendRef`` from the catalog, its bytes arrive from the
  executor, and its transport is an injected callable — nothing here opens a
  file, resolves a model or sends a request on its own;
- deleting a producer package shrinks the vocabulary and raises nothing.
"""

from __future__ import annotations

import ast
import base64
import importlib
import json
import shutil
import sys
import uuid
from pathlib import Path

import pytest

from engine.analysis.catalog import resolve
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
#: Catalog order — the order ``artifact_catalog`` declares (and returns).
ARTIFACT_AXES = (
    "banding",
    "halo",
    "blocking",
    "chroma_fringing",
    "invented_texture",
    "noise_amplification",
    "over_smoothing",
)
#: The MEASURED registry ids the AI scorecard answers — pinned by name so the
#: manifest cannot silently drift into a hand-written fourth vocabulary.
SCORECARD_AXES = (
    "sharpness",
    "exposure",
    "clipping",
    "noise",
    "white_balance",
    "ssim",
    "detail_gain",
    "color_accuracy",
    "typicality",
    "aesthetic",
    "lpips",
    "dists",
    "brisque",
    "clipping_delta",
    "halo_delta",
    "chroma_fringe_delta",
)
AXES = CAMERA_AXES + FIDELITY_AXES + ARTIFACT_AXES + SCORECARD_AXES

PRODUCER_IDS = (
    "ai_scorecard",
    "artifact_catalog",
    "camera_scalars",
    "fidelity_reference",
)

#: Arbitrary "already read by the executor" bytes — the producer must never
#: touch the path these nominally came from.
IMAGE_BYTES = b"\x89PNG\r\n\x1a\nfake-pixels"


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


def _banded_pair(size: int = 128, levels: int = 6):
    """A posterized ramp over its smooth original: a banded-vs-source fixture."""
    import numpy as np
    from PIL import Image

    ramp = np.tile(np.linspace(40, 220, size), (size, 1))
    step = 255 // levels
    quantized = (np.round(ramp / step) * step).clip(0, 255)
    smooth = Image.fromarray(ramp.astype(np.uint8)).convert("RGB")
    banded = Image.fromarray(quantized.astype(np.uint8)).convert("RGB")
    return banded, smooth


def _ctx(
    proxy: object | None = None,
    source: object | None = None,
    capabilities=(),
    *,
    backend=None,
    call=None,
    image_bytes: bytes | None = None,
    extra=None,
):
    return AnalysisContext(
        item_path="synthetic.png",
        mtime_ns=1,
        proxy_image=proxy,
        source_image=source,
        capabilities=frozenset(capabilities),
        backend=backend,
        call=call,
        image_bytes=image_bytes,
        extra=extra or {},
    )


def _run(package: str):
    return importlib.import_module(f"{PRODUCERS}.{package}.producer").run


def _manifest(package: str):
    return importlib.import_module(f"{PRODUCERS}.{package}.manifest")


def _backend(effort: str = "auto"):
    """A catalog-resolved backend: the only way a model id reaches a producer."""
    return resolve(
        "openrouter",
        "catalog-chosen-model",
        user_base_url="https://example.invalid/v1",
        params={"effort": effort},
    )


def _scorecard(**axes: int) -> str:
    """A well-formed model reply: the ``axes`` object the prompt asks for."""
    return json.dumps({"axes": dict(axes), "verdict": "keep", "reason": "clean"})


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


def test_registry_discovers_exactly_four_sorted_producers_and_23_axes():
    registry = discover(PRODUCERS, force=True)

    ids = tuple(spec.id for spec in registry.producers)
    assert ids == PRODUCER_IDS
    assert ids == tuple(sorted(ids)), (
        "discovery order must not leak into registry order"
    )
    assert set(registry.axes()) == set(AXES)
    assert len(registry.axes()) == 23
    assert registry.get("camera_scalars").requires == frozenset({"images"})
    assert registry.get("fidelity_reference").requires == frozenset(
        {"images", "reference"}
    )
    assert registry.get("ai_scorecard").requires == frozenset({"images", "backend"})
    assert registry.get("artifact_catalog").requires == frozenset({"images"})
    assert tuple(registry.get("artifact_catalog").provides) == ARTIFACT_AXES


def test_scorecard_manifest_provides_exactly_the_measured_registry():
    """The manifest cannot drift into a fourth axis vocabulary."""
    from tabs.image_gallery.services import metric_scores

    spec = _manifest("ai_scorecard").PRODUCER
    measured = {
        item.id
        for item in metric_scores.SPECS
        if item.kind is metric_scores.MetricKind.MEASURED
    }

    assert set(spec.provides) == measured
    assert tuple(spec.provides) == SCORECARD_AXES
    assert set(spec.provides.values()) == {"measured"}
    # ``composition`` is the AI-only axis with no local detector: it is not a
    # measured axis, so the scorecard producer does not answer it.
    assert "composition" not in spec.provides


def test_scorecard_manifest_is_a_capped_automatic_network_producer():
    manifest = _manifest("ai_scorecard")
    spec = manifest.PRODUCER

    assert spec.cost == "per_image"
    assert spec.automatic is True
    assert spec.max_per_run == 12 == manifest.MAX_PER_RUN, (
        "a per-image network producer must keep the visible-item ceiling "
        "(controller _AI_VISIBLE_CAP)"
    )


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

    assert len(registry) == 4
    assert "torch" not in sys.modules
    assert "piq" not in sys.modules
    leaked = [
        name
        for name in sys.modules
        if name.startswith(PRODUCERS + ".") and name.endswith(".producer")
    ]
    assert leaked == []


def test_every_local_manifest_declares_free_non_automatic_metadata_only():
    registry = discover(PRODUCERS, force=True)

    for spec in registry.producers:
        if spec.id == "ai_scorecard":
            # The network path: its cost class and cap are pinned above.
            continue
        assert spec.cost == "free"
        assert spec.automatic is False, "the resolver decides when a producer runs"
    catalog = registry.get("artifact_catalog")
    for axis in ARTIFACT_AXES:
        assert catalog.provides[axis] == "candidate"
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


@pytest.mark.parametrize("with_source", [False, True], ids=["sourceless", "with-source"])
def test_artifact_catalog_producer_returns_a_candidate_rank_per_axis(with_source: bool):
    image, source = _banded_pair()
    ctx = _ctx(
        image,
        source=source if with_source else None,
        capabilities={"images", "reference"} if with_source else {"images"},
    )

    values = _run("artifact_catalog")(ctx)

    assert tuple(value.axis for value in values) == ARTIFACT_AXES
    for value in values:
        assert value.producer == "local"
        assert value.status == "ok", value.reason
        assert value.value in {0.0, 1.0, 2.0}
    # A source is an improvement, not a switch: both forms answer all seven.
    if with_source:
        assert any(value.value > 0.0 for value in values), (
            "the banded-vs-source fixture must exercise a non-clean flag"
        )
    # The manifest is the declaration a resolver reads: a flag, not a score.
    spec = discover(PRODUCERS).get("artifact_catalog")
    assert tuple(spec.provides.values()) == ("candidate",) * len(ARTIFACT_AXES)


def test_artifact_catalog_producer_gaps_every_axis_without_an_image():
    values = _run("artifact_catalog")(_ctx())

    assert tuple(value.axis for value in values) == ARTIFACT_AXES
    for value in values:
        assert value.status == "gap"
        assert value.value is None
        assert value.reason


# ---------------------------------------------------------------------------
# run(ctx) — the AI scorecard (network path 1, W6)
# ---------------------------------------------------------------------------


def test_scorecard_producer_returns_vlm_values_with_the_context_backend():
    backend = _backend()
    payloads: list[dict] = []

    def call(payload: dict) -> str:
        payloads.append(payload)
        return _scorecard(sharpness=82, noise=12)

    values = _run("ai_scorecard")(
        _ctx(backend=backend, call=call, image_bytes=IMAGE_BYTES)
    )

    assert tuple(value.axis for value in values) == SCORECARD_AXES
    scored = {value.axis: value for value in values if value.status == "ok"}
    assert set(scored) == {"sharpness", "noise"}
    for value in scored.values():
        assert value.producer == "vlm"
        assert value.backend is backend
        assert 0.0 <= value.value <= 100.0
    # One call, and the model is the catalog's — never a literal here (I2).
    assert len(payloads) == 1
    assert payloads[0]["model"] == backend.model
    # The upload carries the executor's bytes: this producer opened nothing.
    image_part = payloads[0]["messages"][0]["content"][1]
    assert image_part["image_url"]["url"] == (
        "data:image/png;base64," + base64.b64encode(IMAGE_BYTES).decode()
    )


def test_scorecard_producer_gaps_an_axis_the_model_omitted_without_substituting():
    backend = _backend()
    values = _run("ai_scorecard")(
        _ctx(
            backend=backend,
            call=lambda payload: _scorecard(sharpness=77, composition=55),
            image_bytes=IMAGE_BYTES,
        )
    )

    by_axis = {value.axis: value for value in values}
    assert by_axis["sharpness"].status == "ok"
    for axis in SCORECARD_AXES:
        if axis == "sharpness":
            continue
        value = by_axis[axis]
        assert value.status == "gap"
        assert value.value is None, "a gap is never filled with another number"
        assert value.reason == "the model did not score this axis"
    # ``composition`` is the AI-only axis: it is not a declared measured axis,
    # so it is not smuggled into the scorecard through the model's reply.
    assert "composition" not in by_axis


@pytest.mark.parametrize("reply", ["", "not json at all", '{"axes": {"sharpness": '])
def test_scorecard_producer_gaps_every_axis_on_an_unusable_reply(reply: str):
    values = _run("ai_scorecard")(
        _ctx(backend=_backend(), call=lambda payload: reply, image_bytes=IMAGE_BYTES)
    )

    assert tuple(value.axis for value in values) == SCORECARD_AXES
    for value in values:
        assert value.status == "gap"
        assert value.value is None
        assert "could not be parsed" in value.reason


def test_scorecard_producer_turns_a_failed_call_into_gaps():
    def call(payload: dict) -> str:
        raise TimeoutError("stream idle timeout")

    values = _run("ai_scorecard")(
        _ctx(backend=_backend(), call=call, image_bytes=IMAGE_BYTES)
    )

    assert tuple(value.axis for value in values) == SCORECARD_AXES
    for value in values:
        assert value.status == "gap"
        assert value.value is None
        assert "TimeoutError" in value.reason
        assert "stream idle timeout" in value.reason


def test_scorecard_producer_names_each_missing_input_and_calls_nothing():
    calls: list[dict] = []

    def call(payload: dict) -> str:
        calls.append(payload)
        return _scorecard(sharpness=90)

    cases = {
        "no backend resolved for this run": _ctx(
            call=call, image_bytes=IMAGE_BYTES
        ),
        "no transport for this run": _ctx(backend=_backend(), image_bytes=IMAGE_BYTES),
        "no image bytes in the context": _ctx(backend=_backend(), call=call),
    }

    for reason, ctx in cases.items():
        values = _run("ai_scorecard")(ctx)
        assert tuple(value.axis for value in values) == SCORECARD_AXES
        for value in values:
            assert value.status == "gap"
            assert value.value is None
            assert value.reason == reason
    assert calls == [], "a missing input must not reach the transport"


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


NO_DECODE_ATTRS = {"Image.open", "TiledPixelStore.from_path", "read_bytes", "open"}
#: Producers receive their transport through ``AnalysisContext.call`` — a
#: producer that imports an HTTP client is a network path nobody declared.
FORBIDDEN_MODULES = {
    "tabs.image_gallery.services.proxy",
    "urllib.request",
    "urllib.error",
    "requests",
}
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
    # Guard against a vacuous pass: 4 packages x (init, manifest, producer) + root.
    assert len(files) == 13, [path.name for path in files]

    offences = [offence for path in files for offence in _decode_offences(path)]
    assert offences == [], offences


def test_the_no_io_gate_flags_a_file_read(tmp_path: Path):
    """The gate above must be able to fail — otherwise it proves nothing.

    A copy of the forbidden shape (``open`` + ``read_bytes``) in a throwaway
    module: this is the red-before half of the W6 scorecard producer, which
    receives its bytes from the context instead.
    """
    offender = tmp_path / "offender.py"
    offender.write_text(
        "def run(ctx):\n"
        "    with open(ctx.item_path, 'rb') as handle:\n"
        "        return handle.read_bytes()\n",
        encoding="utf-8",
    )

    offences = _decode_offences(offender)

    assert any(offence.endswith("open()") for offence in offences), offences
    assert any(offence.endswith("read_bytes()") for offence in offences), offences

