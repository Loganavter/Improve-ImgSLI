"""Provider/model resolution — the only place a model identity may exist.

Why one home: today each network path carries its own model constant while the
endpoint comes from the user's settings, so switching providers silently leaves
a model that the new endpoint may not serve, and an analysis is attributed to a
model that never ran (defect B1). Producers therefore never name a model: they
ask the catalog for a ``BackendRef``, and a requirement that cannot be resolved
raises ``CatalogError`` — the run is refused with a readable reason *before*
any request is made. An empty model is refused for the same reason: a path must
not invent one.

The table below holds provider ids and base URLs only. Model ids are the
per-path constants this module exists to remove, so no vendor model literal
lives here; ``ProviderPreset.models`` is the slot for a curated fallback list
and the app-side table is wired in a later wave.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import BackendRef


class CatalogError(Exception):
    """A provider/model pair could not be resolved into a ``BackendRef``."""


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    """A known endpoint: id, base URL, and an optional curated model list.

    An empty ``models`` tuple means "the user types the model" (a local server
    serves whatever it was started with, so a list would be a guess).
    """

    id: str
    base_url: str
    models: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.id or "").strip():
            raise ValueError("ProviderPreset.id must be a non-empty string")
        object.__setattr__(self, "models", tuple(str(model) for model in (self.models or ())))


#: Known endpoints in display order. ``custom`` owns no URL — the user does.
DEFAULT_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(id="openrouter", base_url="https://openrouter.ai/api/v1"),
    ProviderPreset(id="openai", base_url="https://api.openai.com/v1"),
    ProviderPreset(id="llamacpp", base_url="http://127.0.0.1:8080/v1"),
    ProviderPreset(id="custom", base_url=""),
)

_BY_ID: dict[str, ProviderPreset] = {preset.id: preset for preset in DEFAULT_PRESETS}


def presets() -> tuple[ProviderPreset, ...]:
    """The known provider presets, in display order."""
    return DEFAULT_PRESETS


def resolve(
    provider: str,
    model: str,
    *,
    user_base_url: str = "",
    params: Mapping[str, object] | None = None,
) -> BackendRef:
    """Resolve a provider/model pair into a validated ``BackendRef``.

    ``user_base_url`` wins over the preset URL (that is the whole point of the
    ``custom`` provider and of a user overriding a preset endpoint). An unknown
    provider, an empty model, or a provider left without any URL raises
    ``CatalogError``.
    """
    key = str(provider or "").strip().lower()
    preset = _BY_ID.get(key)
    if preset is None:
        raise CatalogError(
            f"unknown provider {provider!r}; known providers: "
            f"{', '.join(sorted(_BY_ID))}"
        )
    resolved_model = str(model or "").strip()
    if not resolved_model:
        raise CatalogError(
            f"provider {preset.id!r} has no model: a path must not invent one"
        )
    base_url = str(user_base_url or "").strip() or preset.base_url.strip()
    if not base_url:
        raise CatalogError(
            f"provider {preset.id!r} needs a base_url: the user owns this endpoint"
        )
    try:
        return BackendRef(
            provider=preset.id,
            model=resolved_model,
            base_url=base_url,
            params=params or {},
        )
    except ValueError as exc:  # BackendRef is the final validator
        raise CatalogError(str(exc)) from exc


def resolve_requirement(requirement: Mapping[str, object]) -> BackendRef:
    """Resolve a plan/policy requirement mapping into a ``BackendRef``.

    Keys: ``provider``, ``model``, ``base_url``, ``params``. Anything else is
    ignored; a misspelled key therefore surfaces as its own refusal (an absent
    required key reads as empty), never as a silent default.
    """
    if not isinstance(requirement, Mapping):
        raise CatalogError(
            f"backend requirement must be a mapping, got "
            f"{type(requirement).__name__}"
        )
    params = requirement.get("params") or {}
    if not isinstance(params, Mapping):
        raise CatalogError("backend requirement 'params' must be a mapping")
    base_url = requirement.get("base_url") or ""
    if not isinstance(base_url, str):
        raise CatalogError("backend requirement 'base_url' must be a string")
    return resolve(
        str(requirement.get("provider") or ""),
        str(requirement.get("model") or ""),
        user_base_url=base_url,
        params=params,
    )


__all__ = [
    "DEFAULT_PRESETS",
    "CatalogError",
    "ProviderPreset",
    "presets",
    "resolve",
    "resolve_requirement",
]
