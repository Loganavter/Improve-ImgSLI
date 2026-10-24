"""Export write boundary: a typed name can never leave ``output_dir``.

Tab-owned half of the export-name sanitiser proof. The string rules
(invalid characters, reserved device stems, trailing dots/spaces, length cap,
strict rejection of path-shaped names) live in
``tests/plugins/test_export_name_sanitize.py`` — that half needs nothing from
this tab and stays host-level.

This file asserts the *write boundary* on the real service, because the
host-owned export dialog (``src/plugins/export``) hands ``output_dir`` +
``file_name`` straight to the tab's export service. Root ``tests/`` may not
deep-import a tab's internals (``tests/contracts/test_root_tests_no_tab_internals_leak.py``),
so the assertion lives where the code it exercises lives.

Falsification rule: on the previous code the service joined the raw name with
``os.path.join(image_export/service.py)`` and an absolute/UNC name replaced the
chosen directory — these cases are red there and green with
``sanitize_export_basename`` + ``safe_child_path``.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

try:  # pragma: no cover - environment shim, not behaviour under test
    import imagecodecs  # noqa: F401
except ModuleNotFoundError:  # bare clone / system interpreter lacks the wheel
    sys.modules["imagecodecs"] = types.ModuleType("imagecodecs")

from tabs.image_compare.services.image_export.service import ExportService  # noqa: E402

OUTSIDE_NAMES = [
    pytest.param("/tmp/evil", id="absolute-posix"),
    pytest.param("C:\\tmp\\evil", id="absolute-drive"),
    pytest.param("\\\\srv\\share\\evil", id="unc"),
    pytest.param("..\\evil", id="backslash-traversal"),
    pytest.param("../evil", id="slash-traversal"),
    pytest.param("..", id="dots-only"),
]


def _service_rendering_rgb() -> ExportService:
    return ExportService(
        "/nonexistent/font.ttf",
        gpu_export_service=SimpleNamespace(
            render_plan=lambda plan, **kwargs: (Image.new("RGB", (8, 8)), None)
        ),
    )


def _render_plan() -> SimpleNamespace:
    return SimpleNamespace(canvas_w=8, canvas_h=8, fill_rgba=None)


def _options(output_dir: Path, file_name: str, *, quick: bool = False) -> dict:
    return {
        "output_dir": str(output_dir),
        "file_name": file_name,
        "format": "PNG",
        "is_quick_save": quick,
        "fill_background": False,
    }


@pytest.mark.parametrize("bad_name", OUTSIDE_NAMES)
def test_export_refuses_to_write_outside_output_dir(
    tmp_path: Path, bad_name: str
) -> None:
    service = _service_rendering_rgb()
    before = sorted(entry.name for entry in tmp_path.iterdir())

    with pytest.raises(ValueError):
        service.export_image(
            None,
            Image.new("RGB", (8, 8)),
            Image.new("RGB", (8, 8)),
            _options(tmp_path, bad_name),
            render_plan=_render_plan(),
            render_store=None,
        )

    after = sorted(entry.name for entry in tmp_path.iterdir())
    assert after == before, f"save boundary wrote something for {bad_name!r}: {after}"


def test_export_still_writes_a_safe_name_into_output_dir(tmp_path: Path) -> None:
    """The refusal must not turn a normal save into a failure."""
    service = _service_rendering_rgb()

    result = service.export_image(
        None,
        Image.new("RGB", (8, 8)),
        Image.new("RGB", (8, 8)),
        _options(tmp_path, "shot"),
        render_plan=_render_plan(),
        render_store=None,
    )

    assert result == str(tmp_path / "shot.png")
    assert Path(result).resolve().parent == tmp_path.resolve()
    assert Path(result).exists()
