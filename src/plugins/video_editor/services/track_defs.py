from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.store_viewport import ViewportState
from domain.types import Color, Point

@dataclass(frozen=True)
class ViewportTrackSpec:
    public_id: str
    group_id: str
    group_label: str
    track_label: str
    track_kind: str
    channels: tuple[tuple[str, str, str], ...]
    reader: Callable[[ViewportState], dict[str, Any]]
    writer: Callable[[ViewportState, dict[str, Any]], None]

CHANNEL_LAYOUTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "scalar": (("value", "Value", "scalar"),),
    "bool":   (("value", "Value", "bool"),),
    "enum":   (("value", "Value", "enum"),),
    "color":  (("r", "R", "scalar"), ("g", "G", "scalar"), ("b", "B", "scalar"), ("a", "A", "scalar")),
    "vec2":   (("x", "X", "scalar"), ("y", "Y", "scalar")),
    "mask3":  (("left", "Left", "bool"), ("center", "Center", "bool"), ("right", "Right", "bool")),
}

def _resolve_read(viewport: ViewportState, parts: list[str]) -> Any:
    obj = viewport
    for p in parts:
        obj = getattr(obj, p)
    return obj

def _resolve_write(viewport: ViewportState, attr_path: str, value: Any) -> None:
    parts = attr_path.split(".")
    obj = viewport
    for p in parts[:-1]:
        obj = getattr(obj, p)
    setattr(obj, parts[-1], value)

def _make_accessor(
    attr: str,
    kind: str,
    write_attrs: list[str] | None,
) -> tuple[
    Callable[[ViewportState], dict[str, Any]],
    Callable[[ViewportState, dict[str, Any]], None],
]:
    read_parts = attr.split(".")
    all_write = write_attrs or [attr]

    if kind == "scalar":
        def reader(vp: ViewportState) -> dict[str, Any]:
            return {"value": float(_resolve_read(vp, read_parts))}

        def writer(vp: ViewportState, ch: dict[str, Any]) -> None:
            v = float(ch["value"])
            for wa in all_write:
                _resolve_write(vp, wa, v)

    elif kind == "bool":
        def reader(vp: ViewportState) -> dict[str, Any]:
            return {"value": bool(_resolve_read(vp, read_parts))}

        def writer(vp: ViewportState, ch: dict[str, Any]) -> None:
            v = bool(ch["value"])
            for wa in all_write:
                _resolve_write(vp, wa, v)

    elif kind == "enum":
        def reader(vp: ViewportState) -> dict[str, Any]:
            return {"value": _resolve_read(vp, read_parts)}

        def writer(vp: ViewportState, ch: dict[str, Any]) -> None:
            v = ch["value"]
            for wa in all_write:
                _resolve_write(vp, wa, v)

    elif kind == "color":
        def reader(vp: ViewportState) -> dict[str, Any]:
            c = _resolve_read(vp, read_parts)
            return {"r": int(c.r), "g": int(c.g), "b": int(c.b), "a": int(c.a)}

        def writer(vp: ViewportState, ch: dict[str, Any]) -> None:
            v = Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"]))
            for wa in all_write:
                _resolve_write(vp, wa, v)

    elif kind == "vec2":
        def reader(vp: ViewportState) -> dict[str, Any]:
            p = _resolve_read(vp, read_parts)
            return {"x": float(p.x), "y": float(p.y)}

        def writer(vp: ViewportState, ch: dict[str, Any]) -> None:
            v = Point(float(ch["x"]), float(ch["y"]))
            for wa in all_write:
                _resolve_write(vp, wa, v)

    else:
        raise ValueError(f"Unsupported kind '{kind}' for auto-accessor on '{attr}'")

    return reader, writer

def track(
    public_id: str,
    group_id: str,
    group_label: str,
    track_label: str,
    kind: str,
    *,
    attr: str | None = None,
    write_attrs: list[str] | None = None,
    reader: Callable[[ViewportState], dict[str, Any]] | None = None,
    writer: Callable[[ViewportState, dict[str, Any]], None] | None = None,
    channels: tuple[tuple[str, str, str], ...] | None = None,
) -> ViewportTrackSpec:
    resolved_channels = channels or CHANNEL_LAYOUTS[kind]

    if reader is not None and writer is not None:
        pass
    elif attr is not None:
        reader, writer = _make_accessor(attr, kind, write_attrs)
    else:
        raise ValueError(
            f"track '{public_id}': provide 'attr' for auto-accessor or both 'reader' and 'writer'"
        )

    return ViewportTrackSpec(
        public_id=public_id,
        group_id=group_id,
        group_label=group_label,
        track_label=track_label,
        track_kind=kind,
        channels=resolved_channels,
        reader=reader,
        writer=writer,
    )

def multi_attr_track(
    public_id: str,
    group_id: str,
    group_label: str,
    track_label: str,
    kind: str,
    attr_map: dict[str, str],
    *,
    channels: tuple[tuple[str, str, str], ...] | None = None,
) -> ViewportTrackSpec:
    resolved_channels = channels or CHANNEL_LAYOUTS[kind]
    channel_kind = resolved_channels[0][2]

    if channel_kind == "bool":
        coerce = bool
    elif channel_kind == "scalar":
        coerce = float
    else:
        coerce = lambda v: v

    def reader(vp: ViewportState) -> dict[str, Any]:
        return {ch_id: coerce(getattr(vp, attr_name)) for ch_id, attr_name in attr_map.items()}

    def writer(vp: ViewportState, ch: dict[str, Any]) -> None:
        for ch_id, attr_name in attr_map.items():
            if ch_id in ch:
                setattr(vp, attr_name, coerce(ch[ch_id]))

    return ViewportTrackSpec(
        public_id=public_id,
        group_id=group_id,
        group_label=group_label,
        track_label=track_label,
        track_kind=kind,
        channels=resolved_channels,
        reader=reader,
        writer=writer,
    )
