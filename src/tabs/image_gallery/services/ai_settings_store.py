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


#: Reasoning effort values the "Ask AI" surface accepts. ``auto`` lets the
#: router pick (low, to keep a mandatory-reasoning model from eating the whole
#: answer budget). ``none`` is reserved for non-reasoning models.
REASONING_EFFORTS = ("auto", "low", "medium", "high", "none")

#: Image downscale max-edge choices for AI calls; 0 = send original bytes.
#: Owned by services/decode_policy.py (single home); aliases keep historic names.
from tabs.image_gallery.services.decode_policy import (
    VLM_DEFAULT_MAX_EDGE_PX as _DEFAULT_VLM_MAX_EDGE,
    VLM_MAX_EDGE_CHOICES as VLM_MAX_EDGES,
)


def _parse_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


@dataclass(frozen=True)
class AiSettings:
    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = ""
    #: Answer-token budget for Ask AI; 0 = compute from the scope size.
    ask_max_tokens: int = 0
    #: OpenRouter reasoning effort for Ask AI ("auto" | low | medium | high | none).
    reasoning_effort: str = "auto"
    #: Image downscale max edge (px) for AI image uploads; 0 = original.
    vlm_max_edge_px: int = _DEFAULT_VLM_MAX_EDGE
    #: Set once the user chose “Confirm and don't ask again” on the
    #: large-drop cost warning — subsequent large drops skip the dialog.
    suppress_large_drop_warning: bool = False


class AiSettingsStore:
    """Thin wrapper over a dedicated ``QSettings`` group."""

    def _settings(self) -> QSettings:
        settings = QSettings(_QS_ORG, _QS_APP)
        settings.beginGroup(_QS_GROUP)
        return settings

    def load(self) -> AiSettings:
        settings = self._settings()
        try:
            effort = str(settings.value("reasoning_effort", "auto") or "auto").lower()
            if effort not in REASONING_EFFORTS:
                effort = "auto"
            vlm_edge = _parse_int(settings.value("vlm_max_edge_px", _DEFAULT_VLM_MAX_EDGE), -1)
            if vlm_edge not in VLM_MAX_EDGES:
                vlm_edge = _DEFAULT_VLM_MAX_EDGE
            return AiSettings(
                enabled=str(settings.value("enabled", False)).lower() in ("true", "1"),
                base_url=str(settings.value("base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL),
                api_key=str(settings.value("api_key", "") or ""),
                model=str(settings.value("model", "") or ""),
                ask_max_tokens=max(0, _parse_int(settings.value("ask_max_tokens", 0), 0)),
                reasoning_effort=effort,
                vlm_max_edge_px=vlm_edge,
                suppress_large_drop_warning=str(
                    settings.value("suppress_large_drop_warning", False)
                ).lower()
                in ("true", "1"),
            )
        finally:
            settings.endGroup()

    def save_field(self, name: str, value) -> None:
        if name not in (
            "enabled",
            "base_url",
            "api_key",
            "model",
            "ask_max_tokens",
            "reasoning_effort",
            "vlm_max_edge_px",
            "suppress_large_drop_warning",
        ):
            raise ValueError(f"Unknown AI setting field: {name}")
        settings = self._settings()
        try:
            settings.setValue(name, value)
        finally:
            settings.endGroup()
            settings.sync()
