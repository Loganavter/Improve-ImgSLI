"""ImageSession — per-session state holder (plan_image_pipeline.md Phase 5).

Thin-owner pattern (CODE_PATTERNS.md): SessionController stays a forwarder
(~150 LOC), all session-scoped state lives in ImageSession per session_id.

Holds SlotSource paths + PipelineCache + AbortSignal per session.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field

from shared.image_processing.autocrop import CropService

from tabs.image_compare.pipeline.abort import AbortSignal
from tabs.image_compare.pipeline.cache import PipelineCache
from tabs.image_compare.pipeline.pipeline import ImagePipeline

# Реестр живых сессий для глобальной синхронизации crop-дефолта с настройкой
# auto_crop_black_borders (прецедент: CropService._live_services). Без этого
# PipelineCache/ImagePipeline fallback `else self.crop_service` воскрешает кроп
# при выключенной настройке: голый None от _get_crop_service() неотличим от
# "дефолт сессии", и preview-tier грузился обрезанным вопреки вердикту SKIP.
#
# NB: ImageSession — @dataclass с eq по умолчанию, т.е. нехешируемый, поэтому
# не WeakSet, а id-ключи со слабыми ссылками (семантику класса не трогаем).
_live_sessions: dict[int, weakref.ReferenceType] = {}


def _register_session(sess: "ImageSession") -> None:
    try:
        key = id(sess)
        _live_sessions[key] = weakref.ref(
            sess, lambda _r, _k=key: _live_sessions.pop(_k, None)
        )
    except Exception:
        pass


def set_sessions_crop_enabled(enabled: bool) -> None:
    """Синхронизировать crop-дефолт всех живых сессий с настройкой.

    OFF → sess.crop_service/cache.crop_service = None (голый None внизу по
    течению значит "выключено", а не "дефолт сессии"). ON → гарантировать живой
    сервис (старый мог быть занулён). Боксы детерминированы, закэшированные
    записи под has_crop=True/False остаются валидны после тоггла.
    """
    for ref in list(_live_sessions.values()):
        try:
            sess = ref()
        except Exception:
            continue
        if sess is None:
            continue
        try:
            sess.sync_crop_service(bool(enabled))
        except Exception:
            pass


def resolve_session_controller(presenter):
    """Writer-side session controller for a presenter that does not own one.

    Unify puts and the load pipeline live on the tab ``SessionController``
    (``controller.pipeline``, see ``_session_controller.py``), but bg
    presenters (canvas, toolbar) only carry ``store/widget/view``. Every
    inline hop invented so far missed at least one shape
    (``tab.session_controller`` does not exist — the plugin attr is
    ``session_ctrl``; ``sessions._session_controller`` overshoots by one:
    ``main_controller.sessions`` already IS the tab SessionController).
    Single choke point, best-effort, never raises — returns the controller
    or None. Chain (first hit wins):
    1. ``presenter.session_controller`` / ``presenter.controller``;
    2. ``presenter.main_controller.sessions`` — property already resolving
       to the comparison plugin's ``session_ctrl``;
    3. ``presenter.main_window_app.tab_registry.get_tab("image_compare")``
       ``.session_controller`` (future-proof; absent today);
    4. ``presenter.widget`` → ``_context.main_window`` / ``window()`` →
       ``.presenter`` → step 2 from there.
    Callers take what they need: ``.pipeline`` (unify memo/peek),
    ``._image_load_service`` (is_loading), ``._get_crop_service``.
    """
    try:
        ctrl = getattr(presenter, "session_controller", None) or getattr(
            presenter, "controller", None
        )
        if ctrl is not None:
            return ctrl
    except Exception:
        pass
    try:
        mc = getattr(presenter, "main_controller", None)
        sessions = getattr(mc, "sessions", None) if mc is not None else None
        if sessions is not None:
            return sessions
    except Exception:
        pass
    try:
        mw = getattr(presenter, "main_window_app", None)
        if mw is not None:
            tab = getattr(getattr(mw, "tab_registry", None), "get_tab", lambda *_a, **_kw: None)(
                "image_compare"
            )
            sc = getattr(tab, "session_controller", None) if tab is not None else None
            if sc is not None:
                return sc
    except Exception:
        pass
    try:
        widget = getattr(presenter, "widget", None)
        win = None
        if widget is not None:
            ctx = getattr(widget, "_context", None)
            win = getattr(ctx, "main_window", None) if ctx is not None else None
            if win is None:
                try:
                    win = widget.window()
                except Exception:
                    win = None
        win_presenter = getattr(win, "presenter", None) if win is not None else None
        mc = getattr(win_presenter, "main_controller", None) if win_presenter is not None else None
        sessions = getattr(mc, "sessions", None) if mc is not None else None
        if sessions is not None:
            return sessions
    except Exception:
        pass
    return None


@dataclass
class ImageSession:
    session_id: str
    crop_service: CropService = field(default_factory=CropService)
    cache: PipelineCache = field(default_factory=PipelineCache)
    pipeline: ImagePipeline = field(default_factory=ImagePipeline)
    abort: AbortSignal = field(default_factory=AbortSignal)
    _seq: int = 0
    pyramid_builds: set[int] = field(default_factory=set)

    def __post_init__(self):
        # wire pipeline to this session's cache + crop_service
        try:
            self.pipeline.cache = self.cache
            self.cache.crop_service = self.crop_service
        except Exception:
            pass
        _register_session(self)
        # single-flight loader (bucket D) — shares _inflight dict with pipeline
        try:
            from tabs.image_compare.pipeline.image_load_service import ImageLoadService as _ILS

            svc = _ILS(
                cache=self.cache,
                get_crop_service=lambda _self=self: getattr(_self, "crop_service", None),
            )
            # share single-flight dict: pipeline._inflight is alias to svc._inflight
            try:
                svc._inflight = self.pipeline._inflight  # type: ignore[attr-defined]
            except Exception:
                self.pipeline._inflight = svc._inflight  # type: ignore[attr-defined]
            object.__setattr__(self, "load_service", svc)
            # expose on pipeline for direct access (controller.pipeline.load_service)
            try:
                self.pipeline.load_service = svc  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass

    def sync_crop_service(self, enabled: bool) -> None:
        """Привести crop-дефолт сессии в соответствие с настройкой.

        Вызывать при создании сессии и при тоггле auto_crop_black_borders
        (см. set_sessions_crop_enabled). OFF зануляет и sess.crop_service
        (его читает ImageLoadService.get_crop_service), и cache.crop_service
        (fallback в PipelineCache/ImagePipeline) — иначе голый None внизу
        resurrection'ится в живой дефолт и кроп применяется вопреки настройке.
        """
        try:
            if enabled:
                if self.crop_service is None:
                    self.crop_service = CropService()
                self.cache.crop_service = self.crop_service
            else:
                self.crop_service = None
                self.cache.crop_service = None
        except Exception:
            pass

    def new_abort(self) -> AbortSignal:
        try:
            self.abort.abort()
        except Exception:
            pass
        self._seq += 1
        sig = AbortSignal()
        try:
            sig._generation = int(self._seq)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.abort = sig
        return self.abort
