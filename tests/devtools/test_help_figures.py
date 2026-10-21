"""``help_figures`` devtool: recipes, crop rules, deterministic manifest, drift.

No display is opened here: the capture step is injected as a fake that writes a
tiny PNG, and the Xvfb context is monkeypatched. Falsification: a base checkout
has no ``src/devtools/help_figures.py`` / ``help_figures.json``, so every test
below fails on import or on a missing manifest.
"""

from __future__ import annotations

import io
import json
import os
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


def test_pinned_size_mismatch_is_drift_once_baselined(hf, tmp_path, capsys):
    """A baseline records what was generated; the pin still says what it must be.

    Same bytes, same recorded hash — but the frame is not the pinned one, so a
    ``--check`` that called this ``ok`` could never tell the shipped set apart
    from an ignored pin.
    """
    path = _manifest_file(tmp_path, [_entry(size=[10, 8])])
    manifest = hf.load_manifest(path)
    capture = _fake_capture(size=(6, 4))
    records = hf.generate(manifest, tmp_path / "out", capture=capture, stream=io.StringIO())
    hf.write_manifest(path, hf.apply_results(manifest, records))

    assert hf.check_figures(hf.load_manifest(path), tmp_path / "again", capture=capture) == 1
    out = capsys.readouterr().out
    assert "drift" in out
    assert "10x8" in out and "6x4" in out


def test_pin_mismatch_without_a_baseline_stays_unbaselined(hf, tmp_path, capsys):
    manifest = hf.load_manifest(_manifest_file(tmp_path, [_entry(size=[10, 8])]))

    assert hf.check_figures(manifest, tmp_path / "out", capture=_fake_capture(size=(6, 4))) == 0
    out = capsys.readouterr().out
    assert "unbaselined" in out
    assert "drift=" not in out



def test_generate_writes_only_inside_out_dir(hf, tmp_path):
    manifest = hf.load_manifest()
    out_dir = tmp_path / "shots"
    records = hf.generate(manifest, out_dir, capture=_fake_capture(), stream=io.StringIO())

    assert len(records) == sum(
        hf.figure_variant_count(f) for f in manifest.figures if f.covered
    )
    for record in records:
        assert Path(record["path"]).is_relative_to(out_dir)


# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------


def test_pin_report_claims_every_forced_pin(hf):
    manifest = hf.load_manifest()
    settings = next(f for f in manifest.figures if f.surface == "settings")
    gallery = next(f for f in manifest.figures if f.surface == "gallery")

    # font/ui_scale are forced by capture_surface's canonical bootstrap for
    # every frame (and it fails loudly if the font does not take). Locale/theme
    # reach the constructor-carrying surfaces too (settings_kwargs / the
    # onboarding store), so no constructor caveat remains.
    for figure in (settings, gallery):
        for theme in ("dark", "light"):
            applied, unavailable = hf.pin_report(figure, "ru", theme)
            assert applied == ("locale", "theme", "font", "ui_scale")
            assert unavailable == ()


def test_settings_kwargs_follow_the_captured_locale_and_theme(hf):
    cs = hf.capture_surface
    assert cs.settings_kwargs() == cs.SETTINGS_KWARGS
    ru_light = cs.settings_kwargs("ru", "light")
    assert ru_light["current_language"] == "ru"
    assert ru_light["current_theme"] == "light"
    assert ru_light["active_tab"] == cs.SETTINGS_KWARGS["active_tab"]


def test_jpeg_destination_is_converted_from_the_png_grab(hf, tmp_path):
    import types
    from PIL import Image

    path = tmp_path / "shot.png"
    Image.new("RGB", (8, 6), (10, 20, 30)).save(path)
    figure = types.SimpleNamespace(destination="src/x/help/assets/fig.jpg")
    out = hf._match_destination_format(path, figure)
    with Image.open(out) as image:
        assert image.format == "JPEG"
        assert image.size == (8, 6)

    png = types.SimpleNamespace(destination="src/x/help/assets/fig.png")
    assert hf._match_destination_format(path, png) == path


def test_fake_session_context_answers_with_the_tab_svg_icons(hf, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    hf.capture_surface._bootstrap_qt("dark", "en")
    for kind in ("image_compare", "multi_compare", "image_gallery"):
        icon = hf.capture_surface._tab_icon(kind)
        assert icon is not None and not icon.isNull(), kind
    assert hf.capture_surface._tab_icon("nope") is None


# ---------------------------------------------------------------------------
# Canonical environment (CI baselines are sha256, so the frame must not depend
# on the host's font or DPI)
# ---------------------------------------------------------------------------


def test_xvfb_command_pins_dpi(hf):
    cmd = hf.xvfb_command(91)
    assert cmd[0] == "Xvfb" and ":91" in cmd
    assert cmd[cmd.index("-dpi") + 1] == "96"


def test_canonical_env_pins_scale_and_dpi(hf, monkeypatch):
    monkeypatch.delenv("QT_SCALE_FACTOR", raising=False)
    monkeypatch.delenv("QT_FONT_DPI", raising=False)
    hf.capture_surface._pin_canonical_env()
    assert hf.capture_surface.os.environ["QT_SCALE_FACTOR"] == "1"
    assert hf.capture_surface.os.environ["QT_FONT_DPI"] == "96"


def test_bootstrap_applies_the_bundled_font_chain(hf, monkeypatch):
    """The grab must use the product's fonts, not the host's defaults.

    Both faces are pinned: Source Sans 3 for Latin, Noto Sans SC for Han. The
    Han probe is a real glyph run, so a cleared fallback chain cannot pass.
    """
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    cs = hf.capture_surface
    app = cs._bootstrap_qt("dark", "zh")
    assert cs.BUNDLED_FONT_FAMILY == "Source Sans 3"
    assert cs.BUNDLED_CJK_FONT_FAMILY == "Noto Sans SC"
    assert tuple(app.font().families()[:2]) == ("Source Sans 3", "Noto Sans SC")
    assert "Noto Sans SC" in cs._cjk_run_families(app.font())
    assert cs.BUNDLED_CJK_FONT_PATH.is_file()


def test_bundled_fonts_ship_their_licences(hf):
    """Both bundled fonts are SIL OFL 1.1, so both licence texts must ship."""
    fonts_dir = hf.capture_surface.BUNDLED_FONT_PATH.parent
    for name in ("LICENSE-SourceSans3.txt", "LICENSE-NotoSansSC.txt"):
        text = (fonts_dir / name).read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE" in text.upper()
        assert "Version 1.1" in text



def test_covered_recipes_pin_the_shipped_frame(hf):
    """Every reproducible figure declares the frame it must reproduce."""
    manifest = hf.load_manifest()
    for figure in manifest.figures:
        if not figure.covered:
            continue
        assert figure.size is not None or figure.crop is not None, (
            f"{figure.id}: a covered figure needs a size pin or a crop"
        )


def test_surface_as_is_pins_match_shipped_pixels(hf):
    """Pins come from the measured shipped inventory, not from a guess."""
    for figure in hf.load_manifest().figures:
        if not figure.covered or figure.size is None:
            continue
        assert hf._shipped_size(figure) == figure.size, (
            f"{figure.id}: pin {figure.size} != shipped {hf._shipped_size(figure)}"
        )


def test_settings_recipe_pins_the_measured_shipped_size(hf):
    manifest = hf.load_manifest()
    settings = next(f for f in manifest.figures if f.surface == "settings")

    assert settings.size == (1016, 776)


def test_size_pin_reaches_the_surface_grab(hf, tmp_path, monkeypatch):
    """The pin is applied before the grab (window size), not by resizing pixels."""
    from types import SimpleNamespace

    from PIL import Image

    seen = {}

    class _StubSession:
        def __init__(self, *args, width=None, height=None, **kwargs):
            seen["size"] = (width, height)
            self.dest = Path(args[1])
            self.saved = []

        def grab(self, widget, filename, default_w, default_h, delay=0):
            path = self.dest / "shot.png"
            Image.new("RGB", seen["size"], (1, 2, 3)).save(path)
            self.saved.append(path)
            return path

    monkeypatch.setattr(hf, "_RecordingSession", _StubSession)
    monkeypatch.setattr(hf.capture_surface, "_bootstrap_qt", lambda theme, lang: object())
    surface = SimpleNamespace(
        isolated=False,
        name="stub",
        build=lambda session: session.grab(None, "shot", 10, 10),
    )

    dest = tmp_path / "out"
    dest.mkdir()
    shot = hf._run_surface(surface, dest, "dark", "en", (16, 9))

    assert seen["size"] == (16, 9)
    with Image.open(shot) as image:
        assert image.size == (16, 9)


def test_pin_honoured_is_recorded_and_an_ignoring_surface_is_not_faked(hf, tmp_path):
    from PIL import Image

    entry = _entry(size=[10, 8])
    manifest = hf.load_manifest(_manifest_file(tmp_path, [entry]))

    honoured = hf.generate(
        manifest, tmp_path / "honoured", capture=_fake_capture(size=(10, 8)), stream=io.StringIO()
    )
    assert (honoured[0]["width"], honoured[0]["height"]) == (10, 8)
    assert "size" in honoured[0]["pins_applied"]
    assert not any(p.startswith("size:") for p in honoured[0]["pins_unavailable"])

    ignored = hf.generate(
        manifest, tmp_path / "ignored", capture=_fake_capture(size=(6, 4)), stream=io.StringIO()
    )
    assert (ignored[0]["width"], ignored[0]["height"]) == (6, 4), (
        "an ignored pin must not be faked by resampling the grab"
    )
    assert "size:surface-ignores-pin:6x4" in ignored[0]["pins_unavailable"], (
        "a refused pin must record the achieved size for the reader"
    )
    assert "size" not in ignored[0]["pins_applied"]


def test_pin_report_records_the_achieved_size_of_a_refused_pin(hf, tmp_path):
    manifest = hf.load_manifest(_manifest_file(tmp_path, [_entry(size=[1016, 776])]))
    figure = manifest.figures[0]

    applied, unavailable = hf.pin_report(figure, "en", "dark", captured_size=(1032, 792))

    assert "size" not in applied
    assert "size:surface-ignores-pin:1032x792" in unavailable


def test_generate_says_when_a_pin_was_not_honoured(hf, tmp_path):
    """The CLI must not let a different frame pass as the pinned one."""
    manifest = hf.load_manifest(_manifest_file(tmp_path, [_entry(size=[10, 8])]))

    stream = io.StringIO()
    hf.generate(manifest, tmp_path / "out", capture=_fake_capture(size=(6, 4)), stream=stream)

    out = stream.getvalue()
    assert "pin_unavailable help-gallery-populated [en/dark]" in out
    assert "pinned 10x8" in out and "achieved 6x4" in out


def test_parity_table_lists_pinned_achieved_and_verdict(hf, tmp_path, capsys):
    manifest = hf.load_manifest(_manifest_file(tmp_path, [_entry(size=[10, 8])]))

    rows, mismatched = hf.print_parity_table(
        manifest,
        hf.generate(manifest, tmp_path / "out", capture=_fake_capture(size=(6, 4)), stream=io.StringIO()),
    )
    out = capsys.readouterr().out

    assert mismatched and rows[0]["status"] == "dims-differ"
    assert "pinned" in out and "achieved" in out
    assert "help-gallery-populated" in out
    assert "10x8" in out and "6x4" in out and "differ" in out

    hf.print_parity_table(
        manifest,
        hf.generate(manifest, tmp_path / "ok", capture=_fake_capture(size=(10, 8)), stream=io.StringIO()),
    )
    out = capsys.readouterr().out
    assert "parity" in out and "differ" not in out



def test_multi_variant_recipe_stages_into_locale_theme_folders(hf, tmp_path):
    figure = hf.Figure(
        id="help-multi",
        surface="settings",
        destination="src/resources/help/assets/platform/settings_keyboard.png",
        locales=("en", "ru"),
        themes=("dark", "light"),
    )
    manifest = hf.Manifest(figures=(figure,))

    assert hf.install_destination(figure, "ru", "light").as_posix() == (
        "src/resources/help/assets/ru/light/settings_keyboard.png"
    )
    assert hf.install_destination(figure, "en", "dark").as_posix() == (
        "src/resources/help/assets/en/dark/settings_keyboard.png"
    )

    out_dir = tmp_path / "out"
    records = hf.generate(manifest, out_dir, capture=_fake_capture(), stream=io.StringIO())

    assert len(records) == 4
    for record in records:
        assert record["asset"].startswith("src/resources/help/assets/")
        staged = out_dir / record["asset"]
        assert staged.is_file(), record["asset"]
        assert Path(record["path"]) == staged


def test_single_variant_recipe_keeps_the_flat_destination(hf):
    figure = hf.Figure(
        id="help-flat",
        surface="settings",
        destination="src/resources/help/assets/platform/settings_keyboard.png",
        locales=("en",),
        themes=("dark",),
    )

    assert hf.install_destination(figure, "en", "dark").as_posix() == figure.destination


def test_compare_reports_parity_and_dims_differ(hf, tmp_path):
    manifest = hf.load_manifest(_manifest_file(tmp_path, [_entry(size=[10, 8])]))

    rows, mismatched = hf.compare_parity(
        manifest,
        hf.generate(manifest, tmp_path / "a", capture=_fake_capture(size=(6, 4)), stream=io.StringIO()),
    )
    assert mismatched
    assert rows[0]["status"] == "dims-differ"
    assert rows[0]["target"] == (10, 8) and rows[0]["target_source"] == "pin"

    rows, mismatched = hf.compare_parity(
        manifest,
        hf.generate(manifest, tmp_path / "b", capture=_fake_capture(size=(10, 8)), stream=io.StringIO()),
    )
    assert not mismatched
    assert rows[0]["status"] == "parity"


def test_compare_falls_back_to_the_shipped_size_without_a_pin(hf, tmp_path):
    manifest = hf.load_manifest(_manifest_file(tmp_path, [_entry(size=None)]))

    rows, mismatched = hf.compare_parity(
        manifest,
        hf.generate(manifest, tmp_path / "out", capture=_fake_capture(size=(6, 4)), stream=io.StringIO()),
    )

    assert mismatched
    assert rows[0]["target_source"] == "shipped"
    assert rows[0]["target"] == hf._shipped_size(manifest.figures[0])


def test_main_compare_reports_and_exits_one_on_dims_differ(hf, tmp_path, monkeypatch, capsys):
    from contextlib import contextmanager

    path = _manifest_file(tmp_path, [_entry(size=[10, 8])])

    @contextmanager
    def _fake_display(backend):
        yield ":99"

    monkeypatch.setattr(hf, "display_context", _fake_display)
    monkeypatch.setattr(hf, "capture_png", _fake_capture(size=(6, 4)))

    assert hf.main(["--compare", "--manifest", str(path), "--out", str(tmp_path / "out")]) == 1
    out = capsys.readouterr().out
    assert "dims-differ" in out
    assert "6x4" in out and "10x8" in out


def test_main_all_prints_the_parity_table(hf, tmp_path, monkeypatch, capsys):
    from contextlib import contextmanager

    path = _manifest_file(tmp_path, [_entry(size=[10, 8])])

    @contextmanager
    def _fake_display(backend):
        yield ":99"

    monkeypatch.setattr(hf, "display_context", _fake_display)
    monkeypatch.setattr(hf, "capture_png", _fake_capture(size=(6, 4)))

    assert hf.main(["--all", "--manifest", str(path), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "pinned" in out and "achieved" in out
    assert "help-gallery-populated" in out and "differ" in out
    assert "pin_unavailable" in out




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


# ---------------------------------------------------------------------------
# Parallel capture (--jobs). Nothing here opens a display: the pool seam is
# exercised with a module-level helper, and every capture path uses the fake.
# ---------------------------------------------------------------------------


def _ordered_cell_probe(value):
    """Picklable worker probe: later cells sleep longer, so completion is LIFO."""
    import time as _time

    _time.sleep(0.02 * (5 - value))
    return (value, os.getpid())


def _explode_on_three(value):
    """Picklable worker probe that fails for one cell only."""
    if value == 3:
        raise RuntimeError(f"boom {value}")
    return value


def _spawn_context_or_skip():
    mp = pytest.importorskip("multiprocessing")
    try:
        mp.get_context("spawn")
    except ValueError as exc:  # pragma: no cover - spawn exists on Linux/Windows
        pytest.skip(f"spawn start method unavailable: {exc}")


def test_jobs_defaults_to_one_and_clamps(hf):
    parser = hf.build_parser()

    assert parser.parse_args(["--list"]).jobs == 1
    assert parser.parse_args(["--list", "--jobs", "3"]).jobs == 3
    assert parser.parse_args(["--list", "--jobs", "99"]).jobs == hf.MAX_JOBS
    assert hf.resolve_jobs(0) == min(hf.AUTO_JOBS_CEILING, hf.os.cpu_count() or 1)
    assert hf.resolve_jobs("auto") == hf.resolve_jobs(0)
    assert hf.resolve_jobs("AUTO") == hf.resolve_jobs(0)
    assert hf.resolve_jobs(2) == 2
    assert hf.resolve_jobs(None) == 1


def test_jobs_rejects_negative_and_garbage_values(hf):
    parser = hf.build_parser()

    for bad in ("-1", "nope"):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--list", "--jobs", bad])
        assert exc.value.code == 2, bad
    with pytest.raises(ValueError, match=r"--jobs must be >= 0"):
        hf.resolve_jobs(-2)
    with pytest.raises(ValueError, match=r"expects an integer or 'auto'"):
        hf.resolve_jobs("many")


def test_jobs_one_keeps_the_in_process_path(hf, tmp_path, monkeypatch):
    """``jobs=1`` must never touch the pool (no spawn, same records)."""
    manifest = hf.load_manifest(_manifest_file(tmp_path, [_entry()]))

    def _boom(*args, **kwargs):
        raise AssertionError("jobs=1 must not start a pool")

    monkeypatch.setattr(hf, "_map_cells", _boom)
    records = hf.generate(
        manifest, tmp_path / "out", capture=_fake_capture(), stream=io.StringIO(), jobs=1
    )

    assert [(r["figure"], r["locale"], r["theme"]) for r in records] == [
        ("help-gallery-populated", "en", "dark")
    ]
    assert (records[0]["width"], records[0]["height"]) == (6, 4)


def test_injected_capture_stays_in_process_even_with_high_jobs(hf, tmp_path, monkeypatch):
    """A test seam closure is not picklable, so it must stay in the parent."""
    manifest = hf.load_manifest(_manifest_file(tmp_path, [_entry()]))

    monkeypatch.setattr(hf, "_map_cells", lambda *a, **k: pytest.fail("no pool for injected capture"))
    records = hf.generate(
        manifest, tmp_path / "out", capture=_fake_capture(), stream=io.StringIO(), jobs=4
    )

    assert len(records) == 1


def test_parallel_map_returns_input_order_and_runs_each_cell_once(hf):
    _spawn_context_or_skip()

    results = hf._map_cells(_ordered_cell_probe, [1, 2, 3, 4], jobs=2)

    assert [value for value, _pid in results] == [1, 2, 3, 4], (
        "a parallel run must return results in input order, not completion order"
    )
    assert len(results) == 4, "every cell exactly once"
    assert all(pid != os.getpid() for _value, pid in results), (
        "cells must run in the pool's workers, not the parent"
    )


def test_parallel_map_propagates_a_worker_exception(hf):
    _spawn_context_or_skip()

    with pytest.raises(RuntimeError, match=r"boom 3"):
        hf._map_cells(_explode_on_three, [1, 2, 3, 4], jobs=2)


def test_capture_failure_names_the_cell(hf, monkeypatch, tmp_path):
    """A failed worker must say which figure/locale/theme died."""
    cell = hf._Cell(
        figure=hf.Figure(id="help-x", surface="settings", destination=None),
        locale="ru",
        theme="light",
        out_dir=str(tmp_path),
    )

    monkeypatch.setattr(hf, "_bootstrap_worker_qt", lambda theme, locale: None)

    def _explode(figure, locale, theme, out_dir):
        raise RuntimeError("surface crashed")

    monkeypatch.setattr(hf, "capture_png", _explode)
    with pytest.raises(hf.FigureError, match=r"help-x \[ru/light\]: surface crashed"):
        hf._capture_cell(cell)


def test_main_forwards_jobs_to_the_generating_commands(hf, tmp_path, monkeypatch):
    from contextlib import contextmanager

    path = _manifest_file(tmp_path, [_entry()])
    seen = {}

    @contextmanager
    def _fake_display(backend):
        yield ":99"

    def _fake_check(manifest, out_dir, *, jobs=1, **kwargs):
        seen["check"] = jobs
        return 0

    def _fake_compare(manifest, out_dir, *, jobs=1, **kwargs):
        seen["compare"] = jobs
        return 0

    monkeypatch.setattr(hf, "display_context", _fake_display)
    monkeypatch.setattr(hf, "check_figures", _fake_check)
    monkeypatch.setattr(hf, "compare_sizes", _fake_compare)

    assert hf.main(["--check", "--jobs", "5", "--manifest", str(path)]) == 0
    assert hf.main(["--compare", "--jobs", "auto", "--manifest", str(path)]) == 0
    assert seen["check"] == 5
    assert seen["compare"] == hf.resolve_jobs("auto")

