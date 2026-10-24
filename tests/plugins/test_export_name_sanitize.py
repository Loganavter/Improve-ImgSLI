"""One export-name sanitiser: Windows rules + a hard write boundary.

Two boundaries, one rule set (``shared/image_processing/pil_save.py``):

* **Dialog** — ``ExportDialog._snapshot_export_options`` round-trips the typed
  name through the *forgiving* ``sanitize_filename_component``, so a separator
  never reaches the save flow and typing never raises.
* **Write** — ``ExportService.export_image`` runs ``sanitize_export_basename``
  (strict: rejects absolute / UNC / drive / traversal names) and then
  ``safe_child_path`` re-verifies the resolved parent. A rejected name aborts
  the save before ``os.makedirs``/``open``, so nothing is written outside the
  directory the user picked.

Windows itself is not available in CI, so the string rules (invalid characters,
reserved device stems, trailing dots, length cap) are asserted here directly,
and the OS-level verdicts are recorded as LIVE-PROOF WANTED. Falsification
rule: docs/dev/TESTING.md § Rules for writing new tests (7) — these cases fail
against the previous ``sanitize_filename_component`` (it kept control chars,
trailing dots, reserved stems and could return ``""``; the service joined the
raw name into ``output_dir``).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import inspect
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

from shared.image_processing.pil_save import (  # noqa: E402
    RESERVED_DEVICE_STEMS,
    is_reserved_device_stem,
    next_available_path,
    safe_child_path,
    sanitize_export_basename,
    sanitize_filename_component,
)
from tabs.image_compare.services.image_export.service import ExportService  # noqa: E402

# --- (a) strict sanitiser: path-shaped input is rejected, never rewritten ----

REJECT_CASES = [
    pytest.param("..\\x", id="backslash-traversal"),
    pytest.param("../x", id="slash-traversal"),
    pytest.param("..", id="dots-only"),
    pytest.param(".", id="dot-only"),
    pytest.param("/etc/passwd", id="absolute-posix"),
    pytest.param("C:\\tmp\\x", id="absolute-drive"),
    pytest.param("C:", id="bare-drive-prefix"),
    pytest.param("\\\\srv\\share\\x", id="unc"),
    pytest.param("//srv/share/x", id="unc-posix"),
    pytest.param("   ", id="whitespace-only"),
    pytest.param("", id="empty"),
    pytest.param("." * 300, id="only-trailing-dots"),
]


@pytest.mark.parametrize("name", REJECT_CASES)
def test_strict_sanitiser_rejects_path_shaped_names(name: str) -> None:
    with pytest.raises(ValueError):
        sanitize_export_basename(name)


# --- (b) strict sanitiser: Windows-hostile but rewritable input -------------

CLEAN_CASES = [
    pytest.param("a:b", "a_b", id="colon"),
    pytest.param("C:x", "C_x", id="drive-relative-colon-rewritten"),
    pytest.param("a*b?c", "a_b_c", id="invalid-set"),
    pytest.param("CON.png", "CON_.png", id="reserved-with-extension"),
    pytest.param("nul.txt", "nul_.txt", id="reserved-lowercase"),
    pytest.param("COM1", "COM1_", id="reserved-bare"),
    pytest.param("report.", "report", id="trailing-dot"),
    pytest.param("report   ", "report", id="trailing-spaces"),
    pytest.param("a\x01b\x07c", "abc", id="control-chars-removed"),
    pytest.param("a\x7fb", "ab", id="del-removed"),
]


@pytest.mark.parametrize(("name", "expected"), CLEAN_CASES)
def test_strict_sanitiser_cleans_without_rejecting(name: str, expected: str) -> None:
    assert sanitize_export_basename(name) == expected


def test_strict_sanitiser_caps_length_and_stays_non_empty() -> None:
    capped = sanitize_export_basename("x" * 300)
    assert len(capped) == 120
    assert capped

    short_cap = sanitize_export_basename("abcdef", max_len=4)
    assert short_cap == "abcd"


def test_strict_sanitiser_truncation_cannot_create_a_device_name() -> None:
    # "CONx" capped to 3 would otherwise become the reserved stem "CON".
    assert sanitize_export_basename("CONx", max_len=3) == "CO_"


@pytest.mark.parametrize("stem", sorted(RESERVED_DEVICE_STEMS))
def test_every_reserved_device_stem_is_recognised(stem: str) -> None:
    assert is_reserved_device_stem(stem)
    assert is_reserved_device_stem(stem.lower())


@pytest.mark.parametrize(
    "stem",
    ["CONS", "COM0", "COM10", "LPT0", "CONSOLE", "null", ""],
)
def test_non_reserved_stems_pass(stem: str) -> None:
    assert not is_reserved_device_stem(stem)


# --- (c) write boundary re-verification ------------------------------------


def test_safe_child_path_accepts_a_plain_child(tmp_path: Path) -> None:
    joined = safe_child_path(str(tmp_path), "ok.png")
    assert joined == tmp_path / "ok.png"
    assert joined.resolve().parent == tmp_path.resolve()


@pytest.mark.parametrize(
    "escape",
    ["..\\ok.png", "../ok.png", "sub/ok.png", "..", ".", "/etc/passwd", "C:\\tmp\\x"],
)
def test_safe_child_path_refuses_anything_that_escapes(
    tmp_path: Path, escape: str
) -> None:
    with pytest.raises(ValueError):
        safe_child_path(str(tmp_path), escape)

    # Why the separator check is part of the guard: on POSIX a backslash is an
    # ordinary character, so "..\ok.png" joins to a *child* name here while
    # Windows resolves it to the parent. Rejecting the separator keeps both
    # platforms on the same side of the boundary.
    naive = tmp_path / ".." / "ok.png"
    assert naive.resolve().parent != tmp_path.resolve()


# --- (d) service write boundary: no file outside output_dir ----------------

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


# --- (e) quick-save collision naming is unchanged --------------------------


def test_next_available_path_paren_style_unchanged(tmp_path: Path) -> None:
    first = tmp_path / "stem.png"
    assert next_available_path(first, style="paren") == first

    first.write_bytes(b"x")
    assert next_available_path(first, style="paren") == tmp_path / "stem (1).png"

    (tmp_path / "stem (1).png").write_bytes(b"x")
    assert next_available_path(first, style="paren") == tmp_path / "stem (2).png"


# --- (f) forgiving component: signature kept, never raises ------------------


def test_forgiving_component_keeps_its_public_signature() -> None:
    params = inspect.signature(sanitize_filename_component).parameters
    assert list(params) == ["name", "max_len"]
    assert params["max_len"].default == 80


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "\x00\x01",
        "a/b\\c",
        "CON",
        "CON.",
        "NUL.png",
        "report.",
        "x" * 1000,
        "..",
        ".",
        " name ",
        '?*<>|":',
        "\U0001f642 emoji",
    ],
)
def test_forgiving_component_never_raises_and_never_returns_empty(
    value: str,
) -> None:
    cleaned = sanitize_filename_component(value)
    assert isinstance(cleaned, str)
    assert cleaned
    assert not cleaned.endswith((" ", "."))
    assert "/" not in cleaned and "\\" not in cleaned


def test_forgiving_component_rewrites_instead_of_rejecting() -> None:
    assert sanitize_filename_component("a/b") == "a_b"
    assert sanitize_filename_component("CON.png") == "CON_.png"
    assert sanitize_filename_component("\x01\x02") == "image"
    assert sanitize_filename_component("   ") == "image"
    assert sanitize_filename_component("x" * 1000) == "x" * 80
