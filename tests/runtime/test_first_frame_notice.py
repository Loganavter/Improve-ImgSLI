"""First-frame honesty: a group-B file shows one frame, and the UI says so.

``shared.image_extensions.FIRST_FRAME_SUFFIXES`` admits ``.gif``/``.apng``/
``.mpo``/``.fli``/``.flc``/``.dcx``/``.avifs``/``.psd`` on the promise that a
surface presenting one says "first frame" (or "layers flattened") instead of
letting the file look like a document the viewer can show in full. Before this
suite the promise lived only in a docstring: the properties panel listed Size
and Color mode for a 3-frame GIF as if it were a still, and the export dialog
wrote the composite in silence.

Falsification: the same helper state that produces ``1 of 3`` for a 3-frame GIF
must produce NOTHING for a PNG (regression guard: the note is the exception,
not the default) and nothing for a single-frame GIF (there is nothing hidden,
so there is nothing to say). ``.psd`` takes the other branch (layers), and a
file whose frame count no decoder reported says "first frame" rather than
inventing a number.

Two surfaces are covered because they are two different claims: the properties
panel describes the SOURCE document, the export dialog warns that the written
file is built from the frame on screen.

Placed in ``tests/runtime`` (not ``tests/plugins``): the notice is one fact
consumed by two plugins (``image_properties`` + ``export``) plus the shared
canon, which is the cross-plugin level this folder is for.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from plugins.image_properties.first_frame import first_frame_notice
from plugins.image_properties.service import build_image_properties
from resources.translations import add_i18n_root, tr

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMAGE_PROPERTIES_I18N = _REPO_ROOT / "src/plugins/image_properties/resources/i18n"
_EXPORT_I18N = _REPO_ROOT / "src/plugins/export/resources/i18n"

_FRAME_ROW = "image_properties.frame"


# ---------------------------------------------------------------------------
# Fixtures: real files, because the count must come from a real decoder
# ---------------------------------------------------------------------------


def _write_multiframe_gif(path: Path, frames: int = 3) -> None:
    """Write an *n*-frame GIF and prove it really has *n* frames.

    The frames must differ: Pillow folds identical frames into one image, and a
    fixture that silently collapses to a single frame would make the "1 of 3"
    assertion pass against a still — exactly the false green this suite exists
    to prevent.
    """
    images = []
    for index in range(frames):
        image = Image.new("RGB", (16, 16), (10 * index, 40, 200))
        ImageDraw.Draw(image).rectangle(
            [0, 0, 8, 8], fill=(255, 0, 0) if index % 2 else (255, 255, 0)
        )
        images.append(image)
    images[0].save(
        path, save_all=True, append_images=images[1:], duration=120, loop=0
    )
    with Image.open(path) as probe:
        assert probe.n_frames == frames, (
            f"fixture is not a {frames}-frame GIF ({probe.n_frames} frames): "
            "identical frames get merged by the Pillow writer"
        )


def _write_minimal_psd(path: Path) -> None:
    """Smallest well-formed PSD (1x1 RGB, no layers) — Pillow has no PSD writer.

    Header, three empty sections (colour mode data, image resources, layer and
    mask info), then the raw channel bytes. Enough for ``PsdImagePlugin`` to
    open it, which is all the panel needs: the layers statement is drawn from
    the suffix, not from a successful layer parse.
    """
    header = (
        b"8BPS"
        + struct.pack(">H", 1)  # version
        + b"\x00" * 6  # reserved
        + struct.pack(">HIIHH", 3, 1, 1, 8, 3)  # channels, h, w, depth, RGB
    )
    empty_section = struct.pack(">I", 0)
    path.write_bytes(
        header + empty_section * 3 + struct.pack(">H", 0) + bytes([10, 20, 30])
    )


def _rows(properties) -> dict:
    return {row.label_key: row for section in properties.sections for row in section.rows}


def _translate_ru(key: str) -> str:
    return tr(key, "ru")


# ---------------------------------------------------------------------------
# Properties panel: the source document
# ---------------------------------------------------------------------------


def test_multiframe_gif_reports_one_of_n(tmp_path):
    path = tmp_path / "anim.gif"
    _write_multiframe_gif(path, frames=3)

    properties = build_image_properties(path=path, display_name="anim")
    row = _rows(properties)[_FRAME_ROW]

    assert row.value_key == "image_properties.frame_of"
    assert dict(row.value_params) == {"n": "3"}
    assert row.fallback_value == "1 of 3"

    # The count has to survive translation: "{n}" is filled per language, not
    # printed raw (the reason the row carries ``value_params`` at all).
    add_i18n_root(_IMAGE_PROPERTIES_I18N)
    assert "Frame: 1 of 3" in properties.as_plain_text(lambda key: tr(key, "en"))
    assert "Кадр: 1 из 3" in properties.as_plain_text(_translate_ru)


def test_single_frame_gif_has_no_notice(tmp_path):
    path = tmp_path / "still.gif"
    Image.new("P", (8, 8), 3).save(path)

    # The panel passes the decoded count; 1 means nothing is hidden.
    assert first_frame_notice(path, frame_count=1) is None
    properties = build_image_properties(path=path, display_name="still")
    assert _FRAME_ROW not in _rows(properties)


def test_plain_png_has_no_notice(tmp_path):
    path = tmp_path / "plain.png"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(path)

    properties = build_image_properties(path=path, display_name="plain")
    assert _FRAME_ROW not in _rows(properties)


def test_psd_reports_flattened_composite(tmp_path):
    path = tmp_path / "doc.psd"
    _write_minimal_psd(path)

    properties = build_image_properties(path=path, display_name="doc")
    rows = _rows(properties)
    assert rows["image_properties.format"].value == "PSD"
    row = rows[_FRAME_ROW]
    assert row.value_key == "image_properties.layers_unsupported"
    assert row.fallback_value.startswith("Layers not supported")


def test_psd_layers_statement_needs_no_decoder(tmp_path):
    """The layers row is a suffix fact — a path Pillow cannot open still gets it.

    A PSD whose layer section is unreadable is still a PSD: reporting nothing
    would silently claim the document is fully on screen.
    """
    notice = first_frame_notice(tmp_path / "not-on-disk.psd")

    assert notice is not None
    assert notice.kind == "layers"
    assert notice.count is None


def test_unknown_frame_count_says_first_frame(tmp_path):
    """No decoder reported a count → "first frame", never an invented "1 of N"."""
    path = tmp_path / "broken.gif"
    path.write_bytes(b"GIF89a" + b"\x00" * 8)
    with pytest.raises(Exception):
        # Documents WHY the count is unknown on this fixture, instead of
        # trusting a hand-set dict: Pillow cannot parse this file at all.
        Image.open(path)

    properties = build_image_properties(path=path, display_name="broken")
    row = _rows(properties)[_FRAME_ROW]
    assert row.value_key == "image_properties.frame_first"
    assert row.fallback_value == "first frame"


def test_notice_never_raises_on_odd_paths():
    """The properties panel may not fail because of metadata detail."""
    assert first_frame_notice(None) is None
    assert first_frame_notice("") is None
    assert first_frame_notice(object()) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Export dialog: the written file
# ---------------------------------------------------------------------------


def _export_state(language: str = "en"):
    from domain.types import Color
    from plugins.export.models import ExportDialogState

    return ExportDialogState(
        current_language=language,
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=False,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
        virtual_canvas_active=True,
    )


def _export_dialog(source_paths):
    from PySide6.QtWidgets import QApplication

    from plugins.export.dialog import ExportDialog

    global _APP  # noqa: PLW0603 - keep the single offscreen app alive
    _APP = QApplication.instance() or _APP or QApplication([])
    add_i18n_root(_EXPORT_I18N)
    return ExportDialog(
        dialog_state=_export_state(),
        suggested_filename="out",
        source_paths=source_paths,
    )


_APP = None


def test_export_dialog_warns_for_first_frame_source(tmp_path):
    dialog = _export_dialog([tmp_path / "anim.gif"])
    label = dialog.first_frame_notice_label

    assert not label.isHidden()
    assert label.text() == "Only the first frame is exported"
    dialog.update_language("ru")
    assert label.text() == "Экспортируется только первый кадр"
    dialog.close()


def test_export_dialog_is_silent_for_plain_source(tmp_path):
    dialog = _export_dialog([tmp_path / "plain.png"])
    label = dialog.first_frame_notice_label

    assert label.isHidden()
    assert label.text() == ""
    dialog.close()


def test_export_dialog_is_silent_without_sources():
    dialog = _export_dialog(None)
    assert dialog.first_frame_notice_label.isHidden()
    dialog.close()


def test_export_source_suffix_matching_is_case_insensitive_and_ordered():
    from plugins.export.dialog import (
        first_frame_source_suffixes,
        has_first_frame_source,
    )

    assert first_frame_source_suffixes(["A.GIF", "b.PNG", "c.Psd"]) == (".gif", ".psd")
    assert first_frame_source_suffixes(["b.png"]) == ()
    assert has_first_frame_source(["b.png"]) is False
    assert has_first_frame_source([]) is False


# ---------------------------------------------------------------------------
# Catalogue: the wording is fixed by the owner's table, all four locales
# ---------------------------------------------------------------------------

_EXPECTED_PROPERTIES_KEYS = {
    "frame": {
        "en": "Frame",
        "ru": "Кадр",
        "zh": "帧",
        "pt_BR": "Quadro",
    },
    "frame_of": {
        "en": "1 of {n}",
        "ru": "1 из {n}",
        "zh": "第 1 帧，共 {n} 帧",
        "pt_BR": "1 de {n}",
    },
    "frame_first": {
        "en": "first frame",
        "ru": "первый кадр",
        "zh": "第一帧",
        "pt_BR": "primeiro quadro",
    },
    "layers_unsupported": {
        "en": "Layers not supported — showing the flattened composite",
        "ru": "Слои не поддерживаются — показан сведённый композит",
        "zh": "不支持图层 — 显示合并后的图像",
        "pt_BR": "Camadas não suportadas — exibindo o composto achatado",
    },
}

_EXPECTED_EXPORT_FIRST_FRAME = {
    "en": "Only the first frame is exported",
    "ru": "Экспортируется только первый кадр",
    "zh": "仅导出第一帧",
    "pt_BR": "Apenas o primeiro quadro é exportado",
}


def _load_locale(root: Path, locale: str, filename: str) -> dict:
    return json.loads((root / locale / filename).read_text(encoding="utf-8"))


def test_notice_keys_are_translated_in_every_locale():
    for locale, expected in _EXPECTED_EXPORT_FIRST_FRAME.items():
        catalog = _load_locale(_EXPORT_I18N, locale, "export.json")
        assert catalog["export"]["export_first_frame"] == expected

    for key, per_locale in _EXPECTED_PROPERTIES_KEYS.items():
        for locale, expected in per_locale.items():
            catalog = _load_locale(
                _IMAGE_PROPERTIES_I18N, locale, "image_properties.json"
            )
            assert catalog["image_properties"][key] == expected
        if key == "frame_of":
            # Every locale must keep the placeholder the panel substitutes;
            # dropping it would silently render "1 of 3" as a bare phrase.
            for locale in per_locale:
                catalog = _load_locale(
                    _IMAGE_PROPERTIES_I18N, locale, "image_properties.json"
                )
                assert "{n}" in catalog["image_properties"][key]
