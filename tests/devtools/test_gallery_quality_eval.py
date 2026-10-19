"""Gallery quality mini-eval harness (devtools/gallery_quality_eval.py).

Runs the harness on synthetic, deterministic images so the detector-vs-truth
scoring and the cel-art anchoring gate are exercised without real content.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.evidence.journal import record_evidence, reset_journal, verdict

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")
pytest.importorskip("yaml")

from PIL import Image  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_evidence_journal():
    """The evidence journal is process-global: reset per probe, never leak."""
    reset_journal()
    yield


def _gradient(step: int) -> Image.Image:
    x = np.linspace(0, 255, 256).astype(np.uint8)
    arr = np.tile(x, (64, 1))
    if step > 1:
        arr = ((arr // step) * step).astype(np.uint8)
    return Image.fromarray(arr, "L").convert("RGB")


def _write(path: Path, img: Image.Image) -> Path:
    img.save(path)
    return path


@pytest.fixture()
def eval_folder(tmp_path: Path) -> Path:
    # smooth source: absolute banding clean
    _write(tmp_path / "smooth.png", _gradient(1))
    # biased source: absolute banding flagged (content bias)
    _write(tmp_path / "biased_src.png", _gradient(8))
    # worse than the smooth source -> anchored banding flagged
    _write(tmp_path / "worse.png", _gradient(16))
    # same content as the biased source -> anchored banding clean (cel-art trap)
    _write(tmp_path / "cel_trap.png", _gradient(8))
    (tmp_path / "truth.yaml").write_text(
        "\n".join(
            [
                "images:",
                "  worse.png:",
                "    source: smooth.png",
                "    expect: {banding: flagged}",
                "  cel_trap.png:",
                "    source: biased_src.png",
                "    cel_art: true",
                "    expect: {banding: clean}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_eval_scores_and_cel_art_gate(eval_folder: Path) -> None:
    """Detector verdicts are compared to the hand-labelled truth.yaml.

    Falsification: each observed ``(image, axis, got)`` agreement is derived
    from the rows; a detector-vs-truth regression makes one case disagree, the
    record reads ``violated``, and this probe fails with the measured case list
    in ``signal`` (TESTING.md rule 7 — the label, not the test, is the truth).
    """
    from devtools.gallery_quality_eval import _load_truth, _summarize, run_eval

    truth = _load_truth(eval_folder / "truth.yaml")
    result = run_eval(eval_folder, None, truth)
    summary = _summarize(result)

    by_image = {row["image"]: row for row in result["rows"]}
    assert by_image["worse.png"]["detector"]["banding"] == "flagged"
    assert by_image["cel_trap.png"]["detector"]["banding"] == "clean"

    assert summary["detector"]["banding"]["n"] == 2
    assert summary["detector"]["banding"]["exact"] == 2
    assert summary["detector"]["banding"]["fp"] == 0
    assert summary["detector"]["banding"]["fn"] == 0
    # cel-art FP gate: the one expected-clean axis must read clean.
    assert summary["cel_art"] == {"total": 1, "clean": 1}

    # Observed per-case verdicts, derived from the same rows the assertions read.
    case_verdicts = {
        f"{row['image']}:{axis}": row["detector"].get(axis, "clean") == want
        for row in result["rows"]
        for axis, want in row["expect"].items()
    }
    failed_cases = sorted(case for case, agrees in case_verdicts.items() if not agrees)
    record_evidence("gt.gallery.quality", kind="ground_truth",
                    verdict="ok" if not failed_cases else "violated",
                    signal=f"cases={sorted(case_verdicts)} failed={failed_cases}",
                    reason="detector agrees with truth.yaml",
                    ids=tuple(sorted(case_verdicts)), area="gallery.quality_eval")
    record = verdict(None, "gt.gallery.quality")
    assert record is not None, "quality ground-truth probe emitted no evidence"
    assert record.verdict == "ok", record.signal
    assert record.kind == "ground_truth"
    assert record.ids == ("cel_trap.png:banding", "worse.png:banding"), record.ids


def test_cli_smoke_writes_json(eval_folder: Path, tmp_path: Path) -> None:
    from devtools.gallery_quality_eval import main

    out = tmp_path / "out.json"
    rc = main(
        [
            "--folder",
            str(eval_folder),
            "--truth",
            str(eval_folder / "truth.yaml"),
            "--json",
            str(out),
        ]
    )
    assert rc == 0
    assert out.is_file()
    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["cel_art"]["clean"] == 1


def test_clean_set_has_no_false_alarms(tmp_path: Path) -> None:
    """Calibration regression: a clean image must not false-alarm (SalArt-VQA).

    Guards the abstention contract — the cel-art halo FP is the motivating case.
    """
    from devtools.gallery_quality_eval import _load_truth, _summarize, run_eval

    x = np.linspace(0, 255, 256).astype(np.uint8)
    _write(tmp_path / "grad.png", Image.fromarray(np.tile(x, (128, 1)), "L").convert("RGB"))
    (tmp_path / "truth.yaml").write_text(
        "\n".join(
            [
                "images:",
                "  grad.png:",
                "    expect: {banding: clean, halo: clean, blocking: clean, chroma_fringing: clean}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    truth = _load_truth(tmp_path / "truth.yaml")
    summary = _summarize(run_eval(tmp_path, None, truth))
    for axis in ("banding", "halo", "blocking", "chroma_fringing"):
        assert summary["detector"][axis]["fp"] == 0, axis


def test_write_template_lists_images(eval_folder: Path, tmp_path: Path) -> None:
    from devtools.gallery_quality_eval import main

    tmpl = tmp_path / "template.yaml"
    rc = main(["--folder", str(eval_folder), "--write-template", str(tmpl)])
    assert rc == 0
    text = tmpl.read_text(encoding="utf-8")
    assert "worse.png:" in text
    assert "expect: {}" in text
