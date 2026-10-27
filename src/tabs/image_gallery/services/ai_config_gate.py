"""The ONE definition of "the AI settings allow a paid call".

Split out of ``services/ai_settings_store`` when the gate pushed that module over
the file-size limit (docs/dev/FILE_SIZE_POLICY.md) — and it is the right seam
anyway: this module is pure (no Qt, no state, no transport), while the store owns
``QSettings`` plus the secret-store migration. Callers that only ever ask the
question (the profile selector, the VLM tie-break, the Analyze entry) never need
to import the store.

Why one definition matters (measured 2026-10-27 08:05, live log): the same
config — ``enabled=true``, a key and an endpoint, **empty ``model``** — was
"not configured" for the tie-break and "configured" for the profile selector,
because the selector let the endpoint stand in for a model id. The selector then
spent a call on ``{"model": ""}``, OpenRouter answered ``HTTP 400 "No models
provided"``, and the AI domain finished the run with no axes, no rank and no
analysis. One gate, three callers: the divergence is now a test
(``tests/runtime/test_ai_config_guard.py``).
"""

from __future__ import annotations

#: Fields a paid call needs non-empty, in the order a message names them.
#: ``enabled`` is the switch and is read separately — "disabled" is not an
#: empty field, so it cannot live in this tuple.
REQUIRED_CALL_FIELDS: tuple[str, ...] = ("base_url", "api_key", "model")


def missing_config_fields(settings) -> tuple[str, ...]:
    """The settings that stop a paid AI call; ``()`` means "callable".

    ``enabled`` plus a non-empty ``base_url``, ``api_key`` AND ``model``. An
    endpoint is not a model id: a blank model is refused here, not discovered as
    a provider error after the call was paid for.

    Duck-typed on purpose — the wiring passes a settings row into
    ``use_cases``, so a double (or ``None``, or a broken store) must read as "not
    configured" instead of raising. Never returns, formats or logs a VALUE: only
    whether a field is empty.
    """
    if settings is None:
        return ("enabled",) + REQUIRED_CALL_FIELDS
    missing: list[str] = []
    try:
        enabled = bool(getattr(settings, "enabled", False))
    except Exception:
        enabled = False
    if not enabled:
        missing.append("enabled")
    for name in REQUIRED_CALL_FIELDS:
        try:
            value = str(getattr(settings, name, "") or "").strip()
        except Exception:
            value = ""
        if not value:
            missing.append(name)
    return tuple(missing)


def incomplete_config_message(missing) -> str:
    """One sentence naming what is missing ("" when nothing is).

    The same words in every caller, so three log lines cannot describe one config
    differently. Never carries the key, only its absence.
    """
    names = [str(name) for name in (missing or ())]
    if not names:
        return ""
    return "AI is not configured — missing: " + ", ".join(names)


class AiCallGate:
    """``is_configured`` / ``configured_reason`` for a settings row.

    A mixin rather than three delegating methods on ``AiSettings``: the store
    module sits at the file-size limit (docs/dev/FILE_SIZE_POLICY.md), and the
    check must keep exactly one home. The attributes are the settings fields the
    subclass already declares (``enabled`` / ``base_url`` / ``api_key`` /
    ``model``); nothing here reads them directly — the module gate does.
    """

    def missing_config_fields(self) -> tuple[str, ...]:
        """What this config lacks before a paid call (empty tuple ⇒ usable)."""
        return missing_config_fields(self)

    def is_configured(self) -> bool:
        """True when a paid AI call may be attempted — an endpoint is not a model."""
        return not missing_config_fields(self)

    def configured_reason(self) -> str:
        """Why a paid call must not happen ("" when configured) — never the key."""
        return incomplete_config_message(missing_config_fields(self))
