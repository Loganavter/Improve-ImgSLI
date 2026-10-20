"""``help_figures`` devtool: recipes, crop rules, deterministic manifest, drift.

No display is opened here: the capture step is injected as a fake that writes a
tiny PNG, and the Xvfb context is monkeypatched. Falsification: a base checkout
has no ``src/devtools/help_figures.py`` / ``help_figures.json``, so every test
below fails on import or on a missing manifest.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from devtools import capture_surface


@pytest.fixture()
def hf():
    from devtools import help_figures

    return help_figures


def _fake_capture(color=(10, 20, 30), size=(6, 4)):
    from PIL import Image

    def capture(figure, locale, theme, out_dir):
        path = Path(out_dir) / f"{figure.id}__{locale}__{theme}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color).save(path)
        return path

    return capture


def _entry(figure_id="help-gallery-populated", surface="gallery-populated", **overrides):
    entry = {
        "id": figure_id,
        "surface": surface,
        "crop": None,
        "locales": ["en"],
        "themes": ["dark"],
        "destination": "src/resources/help/assets/platform/tab_strip.png",
        "note": "",
        "captures": [],
    }
    entry.update(overrides)
    return entry


def _manifest_file(tmp_path, figures):
    path = tmp_path / "help_figures.json"
    path.write_text(json.dumps({"schema_version": 1, "figures": figures}), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Recipe shape
# ---------------------------------------------------------------------------


def test_recipe_covers_every_validated_surface_once(hf):
    manifest = hf.load_manifest()

    assert manifest.schema_version == hf.SCHEMA_VERSION
    surfaces = [figure.surface for figure in manifest.figures]
    assert sorted(surfaces) == sorted(capture_surface.SURFACES), (
        "the recipe must cover exactly the validated capture_surface.SURFACES"
    )
    assert len(set(surfaces)) == len(surfaces), "one recipe per surface, no duplicates"
    for figure in manifest.figures:
        assert figure.locales and figure.themes
        if figure.covered:
            assert figure.destination, f"{figure.id}: a covered figure needs a shipped destination"
            assert (hf.REPO_ROOT / figure.destination).is_file()
        else:
            assert figure.reason in {"new-surface", "hand-composed"}, figure.id
            if figure.destination:
                assert "/resources/help/assets/" in figure.destination


def test_committed_manifest_is_canonical(hf):
    manifest = hf.load_manifest()
    original = hf.MANIFEST_PATH.read_text(encoding="utf-8")

    assert hf.dumps_manifest(manifest) == original, (
        "help_figures.json is not in canonical form — run --write-manifest or fix ordering"
    )
    assert "generated" not in original and "timestamp" not in original


# ---------------------------------------------------------------------------
# Crop validation
# ---------------------------------------------------------------------------


def test_crop_rejects_zero_and_negative_size(hf):
    with pytest.raises(hf.CropError, match=r"help-x: crop width and height must be > 0"):
        hf.validate_crop([0, 0, 0, 10], figure_id="help-x")
    with pytest.raises(hf.CropError, match=r"help-x: crop width and height must be > 0"):
        hf.validate_crop([0, 0, -5, 10], figure_id="help-x")


def test_crop_rejects_negative_origin(hf):
    with pytest.raises(hf.CropError, match=r"help-x: crop origin must be >= 0"):
        hf.validate_crop([-1, 0, 10, 10], figure_id="help-x")


def test_crop_rejects_rect_exceeding_captured_size(hf):
    with pytest.raises(hf.CropError, match=r"help-x: crop 200x100\+0\+0 exceeds captured image 100x100"):
        hf.validate_crop([0, 0, 200, 100], figure_id="help-x", size=(100, 100))
    with pytest.raises(hf.CropError, match=r"exceeds captured image 100x100"):
        hf.validate_crop([90, 90, 20, 20], figure_id="help-x", size=(100, 100))


def test_crop_rejects_non_integer_values(hf):
    with pytest.raises(hf.CropError, match=r"crop values must be integers"):
        hf.validate_crop([0, 0, 10.5, 10], figure_id="help-x")
    with pytest.raises(hf.CropError, match=r"crop must be \[x, y, w, h\]"):
        hf.validate_crop([0, 0, 10], figure_id="help-x")


def test_crop_png_applies_rect_and_reports_oversized(hf, tmp_path):
    from PIL import Image

    source = tmp_path / "shot.png"
    Image.new("RGB", (10, 8), (1, 2, 3)).save(source)
    out = hf.crop_png(source, [2, 1, 4, 3], figure_id="help-x")
    with Image.open(out) as image:
        assert image.size == (4, 3)

    untouched = tmp_path / "shot2.png"
    Image.new("RGB", (10, 8), (1, 2, 3)).save(untouched)
    with pytest.raises(hf.CropError, match=r"help-x: crop 99x3\+2\+1 exceeds captured image 10x8"):
        hf.crop_png(untouched, [2, 1, 99, 3], figure_id="help-x")


# ---------------------------------------------------------------------------
# Manifest determinism
# ---------------------------------------------------------------------------


def test_manifest_round_trip_is_byte_stable(hf, tmp_path):
    manifest = hf.load_manifest()
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"

    hf.write_manifest(first, manifest)
    reloaded = hf.load_manifest(first)
    hf.write_manifest(second, reloaded)

    assert first.read_bytes() == second.read_bytes()
    assert hf.dumps_manifest(reloaded) == hf.dumps_manifest(manifest)


def test_apply_results_orders_captures_and_pins(hf, tmp_path):
    path = _manifest_file(tmp_path, [_entry()])
    manifest = hf.load_manifest(path)
    records = [
        {
            "figure": "help-gallery-populated",
            "locale": locale,
            "theme": theme,
            "sha256": "a" * 64,
            "size": 100,
            "width": 6,
            "height": 4,
            "pins_applied": ["theme", "locale"],
            "pins_unavailable": ["ui_scale", "font"],
        }
        for locale, theme in (("ru", "light"), ("en", "dark"))
    ]
    updated = hf.apply_results(manifest, records)

    assert [(b.locale, b.theme) for b in updated.figures[0].captures] == [
        ("en", "dark"),
        ("ru", "light"),
    ]
    assert updated.figures[0].pins_applied == ("locale", "theme")
    assert updated.figures[0].pins_unavailable == ("font", "ui_scale")


def test_manifest_rejects_unknown_surface_and_escaping_destination(hf, tmp_path):
    with pytest.raises(hf.ManifestError, match=r"unknown surface 'nope'"):
        hf.load_manifest(_manifest_file(tmp_path, [_entry(surface="nope")]))

    escaping = _entry(destination="../outside/assets/x.png")
    with pytest.raises(hf.ManifestError, match=r"destination must be repo-relative"):
        hf.load_manifest(_manifest_file(tmp_path, [escaping]))

    not_assets = _entry(destination="src/tabs/image_gallery/widget.py")
    with pytest.raises(hf.ManifestError, match=r"help package assets dir"):
        hf.load_manifest(_manifest_file(tmp_path, [not_assets]))


def test_manifest_rejects_duplicate_destinations(hf, tmp_path):
    figures = [_entry(), _entry(figure_id="help-other", surface="gallery")]
    with pytest.raises(hf.ManifestError, match=r"share one destination"):
        hf.load_manifest(_manifest_file(tmp_path, figures))


def test_uncovered_figure_needs_reason_and_covered_needs_a_real_file(hf, tmp_path):
    uncovered = _entry(
        figure_id="help-empty", surface="gallery", covered=False, destination=None, reason=""
    )
    with pytest.raises(hf.ManifestError, match=r"uncovered figure needs a reason"):
        hf.load_manifest(_manifest_file(tmp_path, [uncovered]))

    ghost = _entry(destination="src/resources/help/assets/platform/no-such-figure.png")
    with pytest.raises(hf.ManifestError, match=r"covered destination does not exist"):
        hf.load_manifest(_manifest_file(tmp_path, [ghost]))


def test_generate_skips_uncovered_figures(hf, tmp_path):
    manifest = hf.load_manifest()
    covered = [figure.id for figure in manifest.figures if figure.covered]
    assert 0 < len(covered) < len(manifest.figures), "recipe needs both covered and uncovered entries"

    records = hf.generate(manifest, tmp_path / "out", capture=_fake_capture(), stream=io.StringIO())
    assert {record["figure"] for record in records} == set(covered)


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def test_drift_same_hash_exits_zero(hf, tmp_path, capsys):
    path = _manifest_file(tmp_path, [_entry()])
    manifest = hf.load_manifest(path)
    capture = _fake_capture()

    records = hf.generate(manifest, tmp_path / "out", capture=capture, stream=io.StringIO())
    baseline = hf.apply_results(manifest, records)
    hf.write_manifest(path, baseline)

    assert hf.check_figures(hf.load_manifest(path), tmp_path / "again", capture=capture) == 0
    out = capsys.readouterr().out
    assert "ok" in out and "drift check: ok=1" in out


def test_drift_changed_hash_exits_one_and_names_figure(hf, tmp_path, capsys):
    path = _manifest_file(tmp_path, [_entry()])
    manifest = hf.load_manifest(path)
    records = hf.generate(
        manifest, tmp_path / "out", capture=_fake_capture(), stream=io.StringIO()
    )
    hf.write_manifest(path, hf.apply_results(manifest, records))

    exit_code = hf.check_figures(
        hf.load_manifest(path), tmp_path / "again", capture=_fake_capture(color=(200, 1, 1))
    )
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "help-gallery-populated" in out
    assert "drift" in out


def test_missing_hash_is_unbaselined_not_drift(hf, tmp_path, capsys):
    path = _manifest_file(tmp_path, [_entry()])
    manifest = hf.load_manifest(path)

    assert hf.check_figures(manifest, tmp_path / "out", capture=_fake_capture()) == 0
    out = capsys.readouterr().out
    assert "unbaselined" in out
    assert "drift check: unbaselined=1" in out


def test_generate_writes_only_inside_out_dir(hf, tmp_path):
    manifest = hf.load_manifest()
    out_dir = tmp_path / "shots"
    records = hf.generate(manifest, out_dir, capture=_fake_capture(), stream=io.StringIO())

    assert len(records) == len([f for f in manifest.figures if f.covered])
    for record in records:
        assert Path(record["path"]).is_relative_to(out_dir)


# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------


def test_pin_report_flags_constructor_pins(hf):
    manifest = hf.load_manifest()
    settings = next(f for f in manifest.figures if f.surface == "settings")
    gallery = next(f for f in manifest.figures if f.surface == "gallery")

    applied, unavailable = hf.pin_report(settings, "en", "dark")
    assert applied == ("locale", "theme")
    assert "locale:constructor-pins-en" in unavailable
    assert "theme:constructor-pins-dark" not in unavailable  # pinned theme matches the ctor
    assert "ui_scale" in unavailable and "font" in unavailable

    _, light_unavailable = hf.pin_report(settings, "en", "light")
    assert "theme:constructor-pins-dark" in light_unavailable

    _, gallery_unavailable = hf.pin_report(gallery, "en", "dark")
    assert "locale:constructor-pins-en" not in gallery_unavailable


# ---------------------------------------------------------------------------
# CLI validation (never touches X)
# ---------------------------------------------------------------------------


def test_list_needs_no_display_and_lists_every_surface(hf, monkeypatch, capsys):
    def _boom(*args, **kwargs):
        raise AssertionError("--list must not start or require a display")

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(hf, "display_context", _boom)

    assert hf.main(["--list"]) == 0
    out = capsys.readouterr().out
    for surface in capture_surface.SURFACES:
        assert surface in out, f"{surface} missing from --list"


def test_unknown_figure_exits_two(hf, monkeypatch, capsys):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(hf, "display_context", lambda *a, **k: pytest.fail("no display"))

    assert hf.main(["--figure", "no-such-figure"]) == 2
    assert "unknown figure" in capsys.readouterr().err


def test_all_and_figure_conflict(hf):
    with pytest.raises(SystemExit) as exc:
        hf.main(["--all", "--figure", "help-onboarding"])
    assert exc.value.code == 2


def test_unknown_backend_is_rejected_before_any_capture(hf):
    with pytest.raises(SystemExit) as exc:
        hf.main(["--all", "--backend", "wayland"])
    assert exc.value.code == 2


def test_check_cannot_write_manifest(hf, tmp_path):
    path = _manifest_file(tmp_path, [_entry()])
    with pytest.raises(SystemExit) as exc:
        hf.main(["--check", "--write-manifest", "--manifest", str(path)])
    assert exc.value.code == 2


def test_uncovered_figure_selection_exits_two(hf, monkeypatch, capsys):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(hf, "display_context", lambda *a, **k: pytest.fail("no display"))

    assert hf.main(["--figure", "help-gallery-empty"]) == 2
    err = capsys.readouterr().err
    assert "uncovered" in err and "new-surface" in err


def test_all_requires_a_mode(hf):
    with pytest.raises(SystemExit) as exc:
        hf.main([])
    assert exc.value.code == 2


def test_main_check_uses_injected_display_and_capture(hf, tmp_path, monkeypatch, capsys):
    from contextlib import contextmanager

    path = _manifest_file(tmp_path, [_entry()])
    manifest = hf.load_manifest(path)
    records = hf.generate(
        manifest, tmp_path / "out", capture=_fake_capture(), stream=io.StringIO()
    )
    hf.write_manifest(path, hf.apply_results(manifest, records))

    used = {}

    @contextmanager
    def _fake_display(backend):
        used["backend"] = backend
        yield ":99"

    monkeypatch.setattr(hf, "display_context", _fake_display)
    monkeypatch.setattr(hf, "capture_png", _fake_capture())

    assert hf.main(["--check", "--manifest", str(path), "--out", str(tmp_path / "again")]) == 0
    assert used["backend"] == "xvfb"
    assert "drift check: ok=1" in capsys.readouterr().out
