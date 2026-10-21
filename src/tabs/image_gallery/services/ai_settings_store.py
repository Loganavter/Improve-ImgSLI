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

import json
from dataclasses import dataclass, field

from PySide6.QtCore import QSettings

from tabs.image_gallery.services.ai_providers import (
    PROVIDER_CUSTOM,
    PROVIDER_OPENROUTER,
    provider_by_id,
)

_QS_ORG = "improve-imgsli"
_QS_APP = "improve-imgsli"
_QS_GROUP = "image_gallery_ai"

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


#: Reasoning effort values the "Ask AI" surface accepts. ``auto`` lets the
#: router pick (low, to keep a mandatory-reasoning model from eating the whole
#: answer budget). ``none`` is reserved for non-reasoning models.
REASONING_EFFORTS = ("auto", "low", "medium", "high", "none")

#: Allowed draw counts per image (plan-gallery-ai-judgement P3-D). ``1`` is the
#: default: a k>1 sample costs k image calls per card, so the multiplier is a
#: declared setting (never a silent default) and its cost is traced.
SAMPLE_COUNT_CHOICES: tuple[int, ...] = (1, 2, 3, 5)

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


def _parse_float(value, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return default


@dataclass(frozen=True)
class AiSettings:
    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = ""
    #: Named provider preset owning ``base_url`` (``services/ai_providers``).
    #: A config written before providers existed loads as ``custom`` with its
    #: own URL — see :meth:`AiSettingsStore.load`.
    provider_id: str = PROVIDER_OPENROUTER
    #: ``{provider_id: model}`` — the model remembered per provider, so a
    #: switch back restores what the user had (owner decision 3, 2026-10-20).
    provider_models: dict[str, str] = field(default_factory=dict)
    #: Answer-token budget for Ask AI; 0 = compute from the scope size.
    ask_max_tokens: int = 0
    #: OpenRouter reasoning effort for Ask AI ("auto" | low | medium | high | none).
    reasoning_effort: str = "auto"
    #: Image downscale max edge (px) for AI image uploads; 0 = original.
    vlm_max_edge_px: int = _DEFAULT_VLM_MAX_EDGE
    #: Set once the user chose “Confirm and don't ask again” on the
    #: large-drop cost warning — subsequent large drops skip the dialog.
    suppress_large_drop_warning: bool = False
    #: Sampling configuration of the VLM scorecard (plan-gallery-ai-judgement
    #: P3-D / gate GA4). ``sample_count`` (k) is the number of independent draws
    #: merged per image: ONE by default — the owner has not set a cost ceiling, so
    #: a multiplier is never taken silently. k>1 is a declared setting and the
    #: trace states its cost (k image calls per card). ``sampling_temperature`` /
    #: ``sampling_seed`` are sent only when non-default (0.0 / 0 = the backend's
    #: own default draw) and are always part of the analysis cache identity.
    sample_count: int = 1
    sampling_temperature: float = 0.0
    sampling_seed: int = 0

    def model_for(self, provider_id: str) -> str:
        """The model remembered for *provider_id* ("" when none yet)."""
        try:
            return str(self.provider_models.get(str(provider_id or "").strip(), "") or "")
        except Exception:
            return ""


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
            stored_provider = str(settings.value("provider_id", "") or "").strip().lower()
            if stored_provider:
                provider_id = provider_by_id(stored_provider).id
            else:
                # Backward compatibility: a config written before providers
                # existed owns its free-form URL, so it loads as ``custom``
                # (its URL is kept verbatim). A virgin config has no
                # ``base_url`` key at all and starts on the default preset.
                provider_id = (
                    PROVIDER_CUSTOM
                    if settings.contains("base_url")
                    else PROVIDER_OPENROUTER
                )
            return AiSettings(
                enabled=str(settings.value("enabled", False)).lower() in ("true", "1"),
                base_url=str(settings.value("base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL),
                api_key=str(settings.value("api_key", "") or ""),
                model=str(settings.value("model", "") or ""),
                provider_id=provider_id,
                provider_models=self._read_provider_models(settings),
                ask_max_tokens=max(0, _parse_int(settings.value("ask_max_tokens", 0), 0)),
                reasoning_effort=effort,
                vlm_max_edge_px=vlm_edge,
                suppress_large_drop_warning=str(
                    settings.value("suppress_large_drop_warning", False)
                ).lower()
                in ("true", "1"),
                sample_count=max(
                    1, min(SAMPLE_COUNT_CHOICES[-1], _parse_int(settings.value("sample_count", 1), 1))
                ),
                sampling_temperature=_parse_float(
                    settings.value("sampling_temperature", 0.0), 0.0
                ),
                sampling_seed=max(0, _parse_int(settings.value("sampling_seed", 0), 0)),
            )
        finally:
            settings.endGroup()

    @staticmethod
    def _read_provider_models(settings: QSettings) -> dict[str, str]:
        """Parse the ``{provider_id: model}`` map. Never raises."""
        try:
            raw = str(settings.value("provider_models", "") or "")
        except Exception:
            return {}
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        out: dict[str, str] = {}
        for key, value in payload.items():
            pid = str(key or "").strip()
            model = str(value or "").strip()
            if pid and model:
                out[pid] = model
        return out

    def _write_provider_models(self, settings: QSettings, models: dict[str, str]) -> None:
        try:
            settings.setValue("provider_models", json.dumps(dict(models), sort_keys=True))
        except Exception:
            pass

    def save_field(self, name: str, value) -> None:
        if name not in (
            "enabled",
            "base_url",
            "api_key",
            "model",
            "provider_id",
            "ask_max_tokens",
            "reasoning_effort",
            "vlm_max_edge_px",
            "suppress_large_drop_warning",
            "sample_count",
            "sampling_temperature",
            "sampling_seed",
        ):
            raise ValueError(f"Unknown AI setting field: {name}")
        settings = self._settings()
        try:
            settings.setValue(name, value)
        finally:
            settings.endGroup()
            settings.sync()

    def save_provider(self, provider_id: str, base_url: str, model: str) -> None:
        """Persist provider + URL + model, and remember the model for it.

        ONE write for the three fields that must move together: a provider
        switch that stored only the URL would leave the old provider's model in
        place (the bug this task fixes). An empty model is not remembered — the
        next visit falls back to the provider's curated default instead.
        """
        pid = provider_by_id(provider_id).id
        text = str(model or "").strip()
        settings = self._settings()
        try:
            settings.setValue("provider_id", pid)
            settings.setValue("base_url", str(base_url or ""))
            settings.setValue("model", text)
            if text:
                models = self._read_provider_models(settings)
                models[pid] = text
                self._write_provider_models(settings, models)
        finally:
            settings.endGroup()
            settings.sync()

    def remember_model(self, provider_id: str, model: str) -> None:
        """Remember *model* for *provider_id* without touching the live fields."""
        pid = provider_by_id(provider_id).id
        text = str(model or "").strip()
        if not text:
            return
        settings = self._settings()
        try:
            models = self._read_provider_models(settings)
            models[pid] = text
            self._write_provider_models(settings, models)
        finally:
            settings.endGroup()
            settings.sync()

    def model_for(self, provider_id: str) -> str:
        """The model remembered for *provider_id* ("" when none yet)."""
        settings = self._settings()
        try:
            return self._read_provider_models(settings).get(
                provider_by_id(provider_id).id, ""
            )
        finally:
            settings.endGroup()

