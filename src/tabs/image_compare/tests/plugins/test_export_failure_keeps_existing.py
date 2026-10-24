"""A failed still-image save must never delete the file it was overwriting.

Regression for the failure handler in ``ExportService.export_image``
(``src/tabs/image_compare/services/image_export/service.py``): after
``write_pil_image_cancelable`` raised, the handler called
``os.remove(full_path)`` — and for a non-quick save ``full_path`` is the
user's *pre-existing* file, not a partial write. The writer is already
atomic (``pil_save.write_pil_image_cancelable`` stages ``*.tmp`` and
publishes with ``os.replace``), so on any failure before the replace the
destination is the untouched original; deleting it is data loss. Silent on
Windows, where a user retrying a save over an existing image loses it.

Trigger (cheapest deterministic one, no monkeypatching of the code under
test): the fake GPU pass returns a ``CMYK`` frame and the export asks for
PNG, so the real encoder raises ``OSError: cannot write mode CMYK as PNG``
inside ``write_pil_image_cancelable``. That is the same handler a user
cancel or a full disk reaches. Dogma / falsification rule:
``docs/dev/TESTING.md`` § Rules for writing new tests (7).
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

from tabs.image_compare.services.image_export.service import ExportService

SENTINEL = b"ORIGINAL"


def _prepare(tmp_path: Path, frame_mode: str) -> tuple[Path, ExportService, dict]:
    """Existing destination with sentinel bytes + a service that renders ``frame_mode``.

    ``render_plan`` is supplied so ``export_image`` skips the live-snapshot
    rebuild; the plan's canvas size matches the frame, which keeps the
    encode path (and only the encode path) under test.
    """
    dest = tmp_path / "shot.png"
    dest.write_bytes(SENTINEL)

    service = ExportService(
        "/nonexistent/font.ttf",
        gpu_export_service=SimpleNamespace(
            render_plan=lambda plan, **kwargs: (Image.new(frame_mode, (8, 8)), None)
        ),
    )
    options = {
        "output_dir": str(tmp_path),
        "file_name": "shot",
        "format": "PNG",
        "is_quick_save": False,
        "fill_background": False,
    }
    plan = SimpleNamespace(canvas_w=8, canvas_h=8, fill_rgba=None)
    return dest, service, {"options": options, "plan": plan}


def test_failed_overwrite_keeps_the_existing_file(tmp_path: Path) -> None:
    dest, service, prepared = _prepare(tmp_path, "CMYK")
    tmp = Path(str(dest) + ".tmp")

    with pytest.raises(OSError, match="cannot write mode CMYK as PNG"):
        service.export_image(
            None,
            Image.new("RGB", (8, 8)),
            Image.new("RGB", (8, 8)),
            prepared["options"],
            render_plan=prepared["plan"],
            render_store=None,
        )

    survivor = dest.read_bytes() if dest.exists() else None
    assert survivor == SENTINEL, (
        "the failed save deleted the user's existing file: "
        f"path={dest} exists={dest.exists()} content={survivor!r}"
    )
    assert not tmp.exists(), f"staged tmp left behind: {tmp}"


def test_successful_overwrite_replaces_the_existing_file(tmp_path: Path) -> None:
    """The fix must not turn overwrite into "refuse to overwrite"."""
    dest, service, prepared = _prepare(tmp_path, "RGB")

    result = service.export_image(
        None,
        Image.new("RGB", (8, 8)),
        Image.new("RGB", (8, 8)),
        prepared["options"],
        render_plan=prepared["plan"],
        render_store=None,
    )

    assert result == str(dest)
    assert dest.read_bytes() != SENTINEL
    with Image.open(dest) as saved:
        assert saved.format == "PNG"
        assert saved.size == (8, 8)
    assert not Path(str(dest) + ".tmp").exists()
