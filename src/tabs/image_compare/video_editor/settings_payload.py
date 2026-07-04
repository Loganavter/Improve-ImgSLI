"""Video-editor payload seeder + reader for the settings dialog.

Owns the ``video_editor_recording`` section of
``SettingsDialogData.tab_extras`` / ``SettingsDialogContext.tab_extras``.
"""

from __future__ import annotations

from typing import Any

SECTION_ID = "video_editor_recording"

_DEFAULTS: dict[str, Any] = {
    "video_recording_fps": 60,
}


def defaults() -> dict[str, Any]:
    return dict(_DEFAULTS)


def seed_from_store(store: object) -> dict[str, Any]:
    if store is None:
        return dict(_DEFAULTS)
    settings = getattr(store, "settings", None)
    return {
        "video_recording_fps": int(
            getattr(settings, "video_recording_fps", _DEFAULTS["video_recording_fps"])
            if settings is not None
            else _DEFAULTS["video_recording_fps"]
        ),
    }


def read_from_dialog(dialog: object) -> dict[str, Any]:
    spin = getattr(dialog, "spin_fps", None)
    if spin is None:
        return {}
    if hasattr(spin, "value"):
        return {"video_recording_fps": int(spin.value())}
    return {}


def register(registry) -> None:
    registry.register_payload_seeder(SECTION_ID, seed_from_store)
    registry.register_payload_reader(SECTION_ID, read_from_dialog)
