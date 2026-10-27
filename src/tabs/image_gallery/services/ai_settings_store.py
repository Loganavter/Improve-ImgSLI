"""Self-contained AI settings storage for the Image Gallery tab.

Deliberately bypasses the global Redux-store settings path (``core/store_settings.py``
/ ``plugins/settings/mutations.py`` / ``application_service.py``) — that path costs
~8 file edits for a setting nothing else in the app needs to react to. Instead this
reads/writes its own ``QSettings`` group directly, saved immediately on change.

Caveat, by design: ``QSettings`` stores its values in plaintext on disk (an INI
file under ``~/.config/<org>/<app>.conf`` on Linux). The API key is therefore
**not** kept here: it goes through ``core.secret_store`` (OS keyring, else an
encrypted machine-bound file, else memory-only for the session) and a plaintext
value left by an older build is migrated out on the first load.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from PySide6.QtCore import QSettings

from core.plugin_system.settings import SETTINGS_APP, SETTINGS_ORG
from tabs.image_gallery.services.ai_config_gate import AiCallGate
from tabs.image_gallery.services.ai_providers import (
    PROVIDER_CUSTOM,
    PROVIDER_OPENROUTER,
    provider_by_id,
)

logger = logging.getLogger(__name__)

# Aliases kept so existing call sites (and any importer of these names) keep
# working; the canonical pair is the single source of the persisted identity.
_QS_ORG = SETTINGS_ORG
_QS_APP = SETTINGS_APP
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

#: Provider-aware concurrency bounds for the AI judge lane (board 2026-10-24).
#: A shared-pool provider must not be hammered by one thread per CPU: the width
#: is a declared setting, default :data:`JUDGE_CONCURRENCY_DEFAULT`, clamped to
#: [1, 8] — never ``os.cpu_count()`` (the provider, often a shared pool, is the
#: scarce resource; eight workers is what the CPU-derived pool would send).
JUDGE_CONCURRENCY_MIN = 1
JUDGE_CONCURRENCY_MAX = 8
JUDGE_CONCURRENCY_DEFAULT = 3

#: Image downscale max-edge choices for AI calls; 0 = send original bytes.
#: Owned by services/decode_policy.py (single home); aliases keep historic names.
from tabs.image_gallery.services.decode_policy import (
    VLM_DEFAULT_MAX_EDGE_PX as _DEFAULT_VLM_MAX_EDGE,
    VLM_MAX_EDGE_CHOICES as VLM_MAX_EDGES,
)

#: Pairwise ordering of a near-tie top set (board: pointwise cannot order
#: near-ties). Only the pointwise top ``pairwise_top_n`` take part, each pair
#: asked in BOTH orders, so one pass costs at most ``N x (N-1)`` calls; 8 is the
#: affordable maximum (56 calls), 2 the smallest set where a swap means anything.
PAIRWISE_TOP_N_MIN = 2
PAIRWISE_TOP_N_MAX = 8
PAIRWISE_TOP_N_DEFAULT = 5

#: "No near-tie, no calls": when the pointwise spread across the top set
#: already exceeds this many 0-100 quality points the pass is skipped entirely.
#: Default 10.0 — half the LOW end of the same-image sampling swing the judge
#: showed live (12-23 points, plan-gallery-ai-judgement J5) while the variants
#: it was asked to separate differed by 2-6: at or above 10 the gap is at least
#: the instrument's own movement, so the pointwise order is decided; below it
#: the order is inside the noise and goes to pairwise comparison.
PAIRWISE_NEAR_TIE_THRESHOLD_MIN = 0.0
PAIRWISE_NEAR_TIE_THRESHOLD_MAX = 100.0
PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT = 10.0


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


def _clamp_int(value, default: int, low: int, high: int) -> int:
    """Parse *value* as int and clamp it into [low, high] (never raises)."""
    try:
        n = int(str(value).strip())
    except Exception:
        n = int(default)
    return max(int(low), min(int(high), n))


def _clamp_float(value, default: float, low: float, high: float) -> float:
    """Parse *value* as float and clamp it into [low, high] (never raises)."""
    try:
        n = float(str(value).strip())
    except Exception:
        n = float(default)
    if n != n:  # NaN
        n = float(default)
    return max(float(low), min(float(high), n))


def _load_secret_value() -> str:
    """The stored provider key, re-probing a cached backend that saw none.

    ``core.secret_store`` resolves its backend once per process and the two
    non-keyring backends answer "" without re-checking: ``MODE_SESSION`` never
    reads anything at all. A process that booted before the keyring answered
    therefore reported "no key" for its WHOLE lifetime — every AI call
    unauthenticated (401) until a restart, even after the key was stored
    (measured 2026-10-25). So an empty answer is not trusted: the probe is
    reset ONCE and the store read again — a load-time re-probe only, no timer,
    no thread, no polling.

    Cost, by construction: a store that HAS a key returns early (and
    :func:`secret_store.load` memoizes it), so a healthy store never re-probes;
    a keyring-backed store with no entry needs none (its ``load()`` re-execs the
    lookup on every call, so it cannot cache a negative); only the genuinely
    stuck states — session-only, or encrypted-file while a keyring was expected
    — pay one ``shutil.which`` per load. The AI settings page
    (:mod:`...ui.settings_ai`, #669) re-probes for the FIELD it shows; this is
    the same repair on the seam that feeds the AI clients, so a code path that
    never opens the page heals too.
    """
    try:
        from core import secret_store
    except Exception:
        return ""
    try:
        value = str(secret_store.load() or "")
        if value:
            return value
        if secret_store.active_mode() == secret_store.MODE_KEYRING:
            return ""
        secret_store.reset_backend_probe()
        value = str(secret_store.load() or "")
    except Exception:
        logger.debug("AI key re-probe on load failed", exc_info=True)
        return ""
    if value:
        # Length only: the key itself must never reach the log.
        logger.info(
            "AI API key appeared after a stale secret-backend probe (length=%d); "
            "using it for this session",
            len(value),
        )
    return value


def _load_api_key(settings: QSettings) -> str:
    """The provider key, from the secret store; migrates an INI plaintext once.

    Configs written before the key moved out of QSettings still carry
    ``api_key`` in the group. Move it into ``core.secret_store`` and drop the
    row, so the plaintext does not survive in the INI (or in its backups).
    """
    try:
        from core import secret_store
    except Exception:
        return str(settings.value("api_key", "") or "")
    try:
        legacy = str(settings.value("api_key", "") or "")
    except Exception:
        legacy = ""
    if legacy:
        secret_store.store(legacy)
        try:
            settings.remove("api_key")
        except Exception:
            pass
        return legacy
    return _load_secret_value()


@dataclass(frozen=True)
class AiSettings(AiCallGate):
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
    #: merged per image (per-axis median). The owner set the cost ceiling to
    #: THREE on 2026-10-21: the judge is stochastic, one draw moved an axis by
    #: 12-23 points while the variants differed by 2-6, so a single draw could
    #: not order them. k=3 costs three image calls per card and the trace states
    #: it. k is part of the analysis cache identity, so the k=1 cards become
    #: MISSes once and are re-drawn at k=3. ``sampling_temperature`` /
    #: ``sampling_seed`` are sent only when non-default (0.0 / 0 = the backend's
    #: own default draw) and are always part of that identity.
    sample_count: int = 3
    sampling_temperature: float = 0.0
    sampling_seed: int = 0
    #: How many AI requests may be in flight for the judge lane (default 3,
    #: clamped [JUDGE_CONCURRENCY_MIN, JUDGE_CONCURRENCY_MAX]). Replaces the
    #: ``os.cpu_count()``-derived width: the provider (often a shared pool) is
    #: the scarce resource, not the local CPU.
    judge_concurrency: int = JUDGE_CONCURRENCY_DEFAULT
    #: Hard per-run ceiling on judge CALLS (0 = unlimited). A card costs one
    #: call per declared draw (``sample_count``), so the pass stops on the last
    #: whole card that fits and leaves a continue affordance instead of
    #: silently draining the budget.
    judge_run_call_ceiling: int = 0
    #: Pairwise ordering of a near-tie top set (board 2026-10-25). OFF by
    #: default even though the settings page now owns the switch
    #: (``ui/settings_ai``, «Refine near-ties pairwise»): the user-facing cost
    #: contract — the ``judge run start: up to X calls`` line from
    #: ``use_cases/judge_budget`` — is stated BEFORE this pass and does not count
    #: its ``top_n x (top_n-1)`` bound, so default-on would spend up to 20 calls
    #: on a near-tie series OUTSIDE the number the user was shown (root
    #: cost-contract decision, 2026-10-25; flipping it is a follow-up whose
    #: acceptance is "the estimate counts the pairwise bound, verified on a live
    #: run"). Persisted like every other knob (a config written with ``true``
    #: keeps it on); the pass is still gated twice before it costs anything: only
    #: a series whose top-set spread is within ``pairwise_near_tie_threshold`` is
    #: compared, and the whole bound is reserved against
    #: ``judge_run_call_ceiling``. The pairwise order is added next to the
    #: pointwise numbers; it never replaces them.
    pairwise_enabled: bool = False
    #: How many of the pointwise-best items take part (clamped
    #: [PAIRWISE_TOP_N_MIN, PAIRWISE_TOP_N_MAX], default 5 = at most 20 calls).
    pairwise_top_n: int = PAIRWISE_TOP_N_DEFAULT
    #: Skip the whole pass when the pointwise spread across that top set already
    #: exceeds this many 0-100 points (clamped to the scale, default 10.0).
    pairwise_near_tie_threshold: float = PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT

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
                api_key=_load_api_key(settings),
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
                    1, min(SAMPLE_COUNT_CHOICES[-1], _parse_int(settings.value("sample_count", 3), 3))
                ),
                sampling_temperature=_parse_float(
                    settings.value("sampling_temperature", 0.0), 0.0
                ),
                sampling_seed=max(0, _parse_int(settings.value("sampling_seed", 0), 0)),
                judge_concurrency=_clamp_int(
                    settings.value("judge_concurrency", JUDGE_CONCURRENCY_DEFAULT),
                    JUDGE_CONCURRENCY_DEFAULT,
                    JUDGE_CONCURRENCY_MIN,
                    JUDGE_CONCURRENCY_MAX,
                ),
                judge_run_call_ceiling=max(
                    0, _parse_int(settings.value("judge_run_call_ceiling", 0), 0)
                ),
                # Absent/anything else means OFF (the dataclass default): only
                # an explicit truthy value turns the pass on. Default-on stays
                # a follow-up until the run estimate counts the pairwise bound
                # (root cost-contract decision, see the field's comment).
                pairwise_enabled=str(
                    settings.value("pairwise_enabled", False)
                ).lower()
                in ("true", "1"),
                pairwise_top_n=_clamp_int(
                    settings.value("pairwise_top_n", PAIRWISE_TOP_N_DEFAULT),
                    PAIRWISE_TOP_N_DEFAULT,
                    PAIRWISE_TOP_N_MIN,
                    PAIRWISE_TOP_N_MAX,
                ),
                pairwise_near_tie_threshold=_clamp_float(
                    settings.value(
                        "pairwise_near_tie_threshold",
                        PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT,
                    ),
                    PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT,
                    PAIRWISE_NEAR_TIE_THRESHOLD_MIN,
                    PAIRWISE_NEAR_TIE_THRESHOLD_MAX,
                ),
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
            "judge_concurrency",
            "judge_run_call_ceiling",
            "pairwise_enabled",
            "pairwise_top_n",
            "pairwise_near_tie_threshold",
        ):
            raise ValueError(f"Unknown AI setting field: {name}")
        settings = self._settings()
        try:
            if name == "api_key":
                # Never write the key into QSettings: it goes to the secret
                # store and the INI row is dropped, so an upgraded config does
                # not leave the previous plaintext behind.
                from core import secret_store

                secret_store.store(str(value or ""))
                try:
                    settings.remove("api_key")
                except Exception:
                    pass
                return
            if name == "judge_concurrency":
                # One owner of the clamp: a value the UI could hand in (1..8)
                # is stored in range, so a config edit cannot widen the lane.
                value = _clamp_int(
                    value,
                    JUDGE_CONCURRENCY_DEFAULT,
                    JUDGE_CONCURRENCY_MIN,
                    JUDGE_CONCURRENCY_MAX,
                )
            elif name == "judge_run_call_ceiling":
                value = max(0, _parse_int(value, 0))
            elif name == "pairwise_top_n":
                value = _clamp_int(
                    value,
                    PAIRWISE_TOP_N_DEFAULT,
                    PAIRWISE_TOP_N_MIN,
                    PAIRWISE_TOP_N_MAX,
                )
            elif name == "pairwise_near_tie_threshold":
                value = _clamp_float(
                    value,
                    PAIRWISE_NEAR_TIE_THRESHOLD_DEFAULT,
                    PAIRWISE_NEAR_TIE_THRESHOLD_MIN,
                    PAIRWISE_NEAR_TIE_THRESHOLD_MAX,
                )
            elif name == "pairwise_enabled":
                value = str(value).strip().lower() in ("true", "1", "yes", "on")
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

