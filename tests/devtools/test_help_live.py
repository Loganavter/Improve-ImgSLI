"""``help_live`` recipes, profile seeding, and the stable-capture contract.

No display here: the app lifecycle is exercised by the supervisor's live proof;
these tests pin the parts that decide whether a live figure is trustworthy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devtools import help_live


def _entry(**overrides):
    entry = {
        "id": "help-x",
        "capture": "@window",
        "steps": [{"open_tab": "image_compare"}, {"sleep": 1.0}],
        "crop": [0, 0, 100, 50],
        "destination": "src/x/resources/help/assets/x.png",
        "locales": ["en"],
        "themes": ["dark"],
        "note": "n",
    }
    entry.update(overrides)
    return entry


def test_loads_steps_in_order_and_rejects_unknown(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [
                    _entry(
                        steps=[
                            {"open_tab": "image_compare"},
                            {"open_folder": {"path": "@samples", "tab": "image_compare", "slot": 2}},
                            {"wait_jobs": 30},
                            {"ui_click": {"id": "property:gallery_path=/tmp/a.png"}},
                            {"press_keys": "H"},
                        ]
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    figure = help_live.load_recipes(path)[0]
    assert [step.kind for step in figure.steps] == [
        "open_tab",
        "open_folder",
        "wait_jobs",
        "ui_click",
        "press_keys",
    ]
    assert figure.steps[1].kwargs == {
        "path": "@samples",
        "tab": "image_compare",
        "slot": 2,
    }
    assert figure.steps[3].kwargs["id"] == "property:gallery_path=/tmp/a.png"

    path.write_text(
        json.dumps({"schema_version": 1, "figures": [_entry(steps=[{"dance": 1}])]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown step"):
        help_live.load_recipes(path)


def test_rejects_a_figure_without_destination(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(
        json.dumps({"schema_version": 1, "figures": [_entry(destination="")]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="id \\+ destination"):
        help_live.load_recipes(path)


def test_profile_seeds_theme_language_and_export_dir(tmp_path):
    path = help_live.write_profile(tmp_path, locale="zh", theme="light", width=1200, height=760)
    text = path.read_text(encoding="utf-8")
    assert "theme=light" in text
    assert "language=zh" in text
    assert "window_width=1200" in text and "window_height=760" in text
    # A real home directory in the export dialog would leak a username into a
    # shipped figure; the seed is a fictional, neutral path.
    assert "export_default_dir=/home/user/Pictures" in text
    assert path.name.endswith(".conf")


def test_profile_seeds_the_rhi_backend(tmp_path):
    """IC canvas figures need Vulkan: llvmpipe/OpenGL cannot create the mip probe."""
    path = help_live.write_profile(
        tmp_path, locale="en", theme="dark", width=1000, height=700, rhi_backend="vulkan"
    )
    assert "rhi_backend=vulkan" in path.read_text(encoding="utf-8")
    default = help_live.write_profile(
        tmp_path / "default", locale="en", theme="dark", width=1000, height=700
    )
    assert "rhi_backend=opengl" in default.read_text(encoding="utf-8")


def test_recipe_carries_backend_and_capture_interval(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [
                    _entry(rhi_backend="vulkan", stable_interval_s=0.15,
                           capture="@screen")
                ],
            }
        ),
        encoding="utf-8",
    )
    figure = help_live.load_recipes(path)[0]
    assert figure.rhi_backend == "vulkan"
    assert figure.stable_interval_s == 0.15
    assert figure.capture == "@screen"


def test_samples_are_byte_stable(tmp_path):
    first = help_live.ensure_samples(tmp_path)
    hashes = {p.name: p.read_bytes() for p in first.glob("*.png")}
    second = help_live.ensure_samples(tmp_path)
    assert {p.name: p.read_bytes() for p in second.glob("*.png")} == hashes
    assert (second / "singles" / "sunset" / "sunset.png").is_file()


class _FakeClient:
    def __init__(self, sizes):
        self.sizes = list(sizes)
        self.calls = 0

    def call(self, method, params=None):
        assert method == "capture_live"
        self.calls += 1
        size = self.sizes[min(self.calls - 1, len(self.sizes) - 1)]
        path = Path(self._dir) / f"shot-{self.calls}.png"
        path.write_bytes(b"payload" if self.calls == 1 else b"payload")
        self._last = path
        return {"path": str(path), "size": list(size)}


def test_stable_capture_requires_two_identical_frames(tmp_path):
    client = _FakeClient([(1200, 800)])
    client._dir = tmp_path
    out = tmp_path / "out.png"
    written = help_live.stable_capture(client, "@window", out)
    assert written.is_file()
    assert client.calls == 2  # first capture is only a candidate


def test_stable_capture_rejects_a_helper_window(tmp_path):
    client = _FakeClient([(356, 194)])
    client._dir = tmp_path
    with pytest.raises(help_live.LiveError, match="min_size"):
        help_live.stable_capture(client, "@window", tmp_path / "o.png", (800, 500))


def test_crop_uses_x_y_w_h(tmp_path):
    from PIL import Image

    shot = tmp_path / "shot.png"
    Image.new("RGB", (200, 100), (10, 20, 30)).save(shot)
    out = tmp_path / "x.png"
    help_live.crop_and_install(shot, out, (10, 5, 50, 40))
    with Image.open(out) as image:
        assert image.size == (50, 40)


def test_jpeg_destination_is_converted(tmp_path):
    from PIL import Image

    shot = tmp_path / "shot.png"
    Image.new("RGB", (20, 10), (1, 2, 3)).save(shot)
    out = tmp_path / "x.jpg"
    help_live.crop_and_install(shot, out, None)
    with Image.open(out) as image:
        assert image.format == "JPEG"


def test_jpeg_install_composites_the_transparent_window_margin(tmp_path):
    """RED-BEFORE: alpha was dropped, so the CSD shadow band became black.

    A top-level grab is RGBA with a fully transparent margin (measured on
    ``ru/light/export_dialog.jpg``: 27588 transparent pixels, black at every
    corner and along all four edges). ``convert("RGB")`` does not composite —
    it discards alpha and leaves black, which reads as a rendering defect on a
    light theme. The margin is also not part of the window, so it is cropped.
    """
    from PIL import Image

    source = tmp_path / "shot.png"
    grab = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
    window = Image.new("RGBA", (50, 30), (250, 250, 250, 255))
    grab.paste(window, (5, 5))
    for x, y in ((5, 5), (6, 5), (5, 6)):  # a rounded corner stays transparent
        grab.putpixel((x, y), (0, 0, 0, 0))
    grab.save(source)

    destination = tmp_path / "figure.jpg"
    help_live.crop_and_install(source, destination, None)

    with Image.open(destination) as image:
        assert image.size == (50, 30), "the transparent margin is not the window"
        out = image.convert("RGB")
    edge = [out.getpixel((x, 0)) for x in range(out.width)]
    edge += [out.getpixel((0, y)) for y in range(out.height)]
    assert all(sum(pixel) > 600 for pixel in edge), edge[:4]


def test_screen_window_crop_drops_the_root_window_band(tmp_path):
    """RED-BEFORE: a @screen crop kept the black root window around the dialog.

    The window rect from ``dump_ui_layout`` includes the CSD shadow, and on a
    bare X server the pixels outside the dialog are the root window, so the
    figure shipped a solid band (measured on ``ru/light/video_export.jpg``:
    33507 dark pixels, 33688 inside a 12 px border).
    """
    from PIL import Image

    screen = Image.new("RGB", (60, 50), (0, 0, 0))
    dialog = Image.new("RGB", (40, 30), (245, 245, 245))
    screen.paste(dialog, (10, 10))
    source = tmp_path / "screen.png"
    screen.save(source)

    destination = tmp_path / "figure.png"
    help_live.crop_and_install(source, destination, None, trim_uniform_border=24)

    with Image.open(destination) as image:
        assert image.size == (40, 30), "the root-window band is not window content"
        out = image.convert("RGB")
    assert out.getpixel((0, 0)) == (245, 245, 245)
    assert out.getpixel((39, 29)) == (245, 245, 245)


def test_a_uniform_border_trim_never_eats_content(tmp_path):
    """The band stops at the first differing pixel, even inside ``max_px``."""
    from PIL import Image

    image = Image.new("RGB", (40, 40), (0, 0, 0))
    for x in range(40):
        for y in range(40):
            if 5 <= x < 35 and 5 <= y < 35:
                image.putpixel((x, y), (10, 118, 168))
    source = tmp_path / "shot.png"
    image.save(source)

    destination = tmp_path / "figure.png"
    help_live.crop_and_install(source, destination, None, trim_uniform_border=24)

    with Image.open(destination) as out:
        assert out.size == (30, 30)
