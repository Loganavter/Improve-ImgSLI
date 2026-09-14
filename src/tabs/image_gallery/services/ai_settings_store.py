"""Self-contained AI settings storage for the Image Gallery tab.

Deliberately bypasses the global Redux-store settings path (``core/store_settings.py``
/ ``plugins/settings/mutations.py`` / ``application_service.py``) — that path costs
~8 file edits for a setting nothing else in the app needs to react to. Instead this
reads/writes its own ``QSettings`` group directly, saved immediately on change.

Caveat, by design: ``QSettings`` stores its values in plaintext on disk (an INI
file under ``~/.config/<org>/<app>.conf`` on Linux). The API key is therefore
stored unencrypted, same as every other value in this file — no keyring/OS
credential-store integration is added in this pass. The settings UI surfaces
this explicitly (``image_gallery.settings.api_key_warning``).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

_QS_ORG = "improve-imgsli"
_QS_APP = "improve-imgsli"
_QS_GROUP = "image_gallery_ai"

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class AiSettings:
    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = ""


class AiSettingsStore:
    """Thin wrapper over a dedicated ``QSettings`` group."""

    def _settings(self) -> QSettings:
        settings = QSettings(_QS_ORG, _QS_APP)
        settings.beginGroup(_QS_GROUP)
        return settings

    def load(self) -> AiSettings:
        settings = self._settings()
        try:
            return AiSettings(
                enabled=str(settings.value("enabled", False)).lower() in ("true", "1"),
                base_url=str(settings.value("base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL),
                api_key=str(settings.value("api_key", "") or ""),
                model=str(settings.value("model", "") or ""),
            )
        finally:
            settings.endGroup()

    def save_field(self, name: str, value) -> None:
        if name not in ("enabled", "base_url", "api_key", "model"):
            raise ValueError(f"Unknown AI setting field: {name}")
        settings = self._settings()
        try:
            settings.setValue(name, value)
        finally:
            settings.endGroup()
            settings.sync()
