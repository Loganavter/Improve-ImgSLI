"""What a "first frame" file hides from the viewer — and how the panel says it.

:data:`shared.image_extensions.FIRST_FRAME_SUFFIXES` admits a group-B file
(``.gif``, ``.apng``, ``.avifs``, ``.mpo``, ``.fli``, ``.flc``, ``.dcx``,
``.psd``) on the promise that a surface presenting one of them says so: the
viewer decodes exactly one frame (or, for a PSD, the flattened composite), and
a properties panel that lists only Size / Color mode lets the user believe the
whole document is on screen.

Lives outside ``service.py`` because that module is at the file-size policy
limit (``docs/dev/FILE_SIZE_POLICY.md``) and because the fact is reusable: the
properties panel renders these rows, an export surface asks the same question.

Two branches only — the owner's rule — a PSD reports ``layers`` (the app has
no layer support at all), every other member reports ``frames``; a decoded
count merely refines the wording ("1 of 3" vs "first frame") and a
single-frame file says nothing at all. No per-format branching beyond that.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from .service import ImagePropertyRow


@dataclass(frozen=True)
class FirstFrameNotice:
    """What a group-B file hides from the viewer.

    ``kind`` is ``"frames"`` for a sequence container — the viewer shows one of
    ``count`` frames — or ``"layers"`` for a PSD, where Pillow can only hand out
    the flattened composite and layers are not available at all.
    ``count`` stays ``None`` when no decoder reported one (the file opened
    through the libvips/JXL probes, or Pillow's parse failed): the notice then
    says "first frame" rather than inventing a number.
    """

    kind: str
    count: int | None = None


def first_frame_notice(
    path: str | Path | None, *, frame_count: int | None = None
) -> FirstFrameNotice | None:
    """What the viewer is NOT showing of *path*, or ``None`` when nothing is hidden.

    ``frame_count`` is the count the decoder reported (``PIL.Image.n_frames``
    read while the panel already had the file open). Omitted / ``None`` means
    "no decoder told us", which is a different statement from "one frame":
    only the latter silences the notice.

    Never raises: a metadata row may not be the reason a properties panel
    fails, so a broken path or a missing canon import yields ``None``.
    """
    if path is None:
        return None
    try:
        from shared.image_extensions import FIRST_FRAME_SUFFIXES
    except Exception:
        return None
    try:
        suffix = Path(str(path)).suffix.lower()
    except Exception:
        return None
    if suffix not in FIRST_FRAME_SUFFIXES:
        return None
    if suffix == ".psd":
        # Layers, not frames: parsing the layer section for a count would be
        # the expensive half of opening a PSD and the number would still not
        # describe what is missing (the layers themselves).
        return FirstFrameNotice(kind="layers")
    if frame_count is not None and frame_count <= 1:
        # A single-frame file: nothing is hidden, so there is nothing to say.
        return None
    count = int(frame_count) if frame_count and frame_count > 1 else None
    return FirstFrameNotice(kind="frames", count=count)


def first_frame_rows(
    path: str | Path | None, source_info: dict[str, Any]
) -> list["ImagePropertyRow"]:
    """The honesty row for a group-B file, or nothing for a plain raster.

    Data rows only — the properties panel already renders its sections as a
    table, so this adds one line to the Image section exactly like Size or
    Color mode, after them (the familiar order must not shift).
    """
    from .service import ImagePropertyRow

    try:
        notice = first_frame_notice(path, frame_count=source_info.get("frame_count"))
    except Exception:
        return []
    if notice is None:
        return []
    if notice.kind == "layers":
        return [
            ImagePropertyRow(
                "image_properties.frame",
                "Frame",
                "",
                "image_properties.layers_unsupported",
                "Layers not supported — showing the flattened composite",
            )
        ]
    if notice.count is None:
        return [
            ImagePropertyRow(
                "image_properties.frame",
                "Frame",
                "",
                "image_properties.frame_first",
                "first frame",
            )
        ]
    return [
        ImagePropertyRow(
            "image_properties.frame",
            "Frame",
            "",
            "image_properties.frame_of",
            f"1 of {notice.count}",
            value_params=(("n", str(notice.count)),),
        )
    ]
