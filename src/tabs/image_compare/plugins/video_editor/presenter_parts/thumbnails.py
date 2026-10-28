import logging
from typing import Callable, Dict, List

from PySide6.QtGui import QPixmap
from sli_ui_toolkit.managers import SettleGate
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)

from .common import VIDEO_EDITOR_AUTO_CROP
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


class ThumbnailCoordinator:
    def __init__(
        self,
        view,
        editor_service,
        playback_engine,
        thumbnail_service,
        emit_thumbnails_updated: Callable[[Dict[int, QPixmap]], None],
        timer_parent=None,
    ):
        self.view = view
        self.editor_service = editor_service
        self.playback_engine = playback_engine
        self.thumbnail_service = thumbnail_service
        self.emit_thumbnails_updated = emit_thumbnails_updated

        # Coalesce resize + scrollbar-range churn while the window is dragged.
        # Deliberately settles later than PreviewCoordinator's gate (120ms):
        # both do a blocking main-thread GPU render on settle, and if they
        # land on the same tick the second one queues up behind the first,
        # showing up as one long stall instead of two short ones.
        self._visible_refresh = SettleGate(
            on_settle=self._refresh_visible_thumbnails,
            interval_ms=SettleGate.DEFAULT_INTERVAL_MS * 2,
            parent=timer_parent,
        )
        # P3 wave discipline: last visible window handed to the service.
        # The settled refresh compares against it and retires in-flight
        # workers only when the wanted set actually changed — same window
        # re-settling (e.g. repeated resizes without scrolling) must not
        # bump the generation token. None = no baseline yet (no retire).
        self._last_visible_indices: List[int] | None = None
        # Z4 zoom-aware refresh: last timeline zoom scalar seen. A refresh
        # where the zoom changed is zoom-driven (geometry reshuffled, content
        # identical) and must NOT retire the in-flight wave — completions are
        # index-addressed (P3), so they stay valid. Scroll/pan (window moved,
        # zoom unchanged) retires as before. None = no baseline yet.
        # Read via the public get_pixels_per_second() only — never the
        # toolkit-private _zoom_level.
        self._last_zoom_level: float | None = None
        # I4 feed generation mirror: the token returned by the service's
        # ``generate_thumbnails`` (or by ``retire_in_flight_thumbnails`` on
        # the scroll path). ``on_single_thumbnail_ready`` drops tagged
        # completions that mismatch it; ``None`` = unknown (service without
        # the seam, e.g. test doubles) → fail-open, apply everything.
        self._feed_generation: int | None = None

        # Frame-count owner is the editor service (ceil(duration*fps)+1 off
        # its get_duration). Derive through it; the service falls back to
        # its recording formula on any doubt (fail-open).
        try:
            set_source = getattr(
                self.thumbnail_service, "set_frame_count_source", None
            )
            derive = getattr(self.editor_service, "get_frame_count", None)
            if callable(set_source) and callable(derive):
                set_source(derive)
        except Exception:
            logger.debug("frame-count source wiring skipped", exc_info=True)

    def _gate_deleted(self) -> bool:
        """True once the settle gate's C++ objects are gone.

        ``SettleGate`` hangs off the presenter, which ``cleanup`` /
        ``_on_view_destroyed`` ``deleteLater()``, so its ``QTimer`` child dies
        while these Python wrappers survive: ``cancel``/``ping`` then raise
        ``RuntimeError: Internal C++ object ... already deleted`` from a
        teardown with nothing left to stop (owner traceback 2026-10-28:
        ``closeEvent``→``cleanup``→``cancel``→``QTimer.stop``).
        """
        try:
            import shiboken6

            return not shiboken6.isValid(self._visible_refresh)
        except Exception:
            return False

    def _cancel_visible_refresh(self) -> None:
        if self._gate_deleted():
            return
        try:
            self._visible_refresh.cancel()
        except RuntimeError:
            # Gate alive, its QTimer already dead (half-torn-down parent).
            logger.debug("thumbnail settle gate timer already deleted; cancel skipped")

    def _ping_visible_refresh(self) -> None:
        if self._gate_deleted():
            return
        try:
            self._visible_refresh.ping()
        except RuntimeError:
            logger.debug("thumbnail settle gate timer already deleted; ping skipped")

    def detach_view(self):
        self._cancel_visible_refresh()
        # No post-detach add_thumbnail storms: retire the live wave so late
        # worker completions drop on arrival (fail-open kept — the
        # generation token and membership filter still apply on doubt).
        try:
            teardown = getattr(self.thumbnail_service, "teardown", None)
            if callable(teardown):
                teardown()
            else:
                cancel = getattr(self.thumbnail_service, "cancel", None)
                if callable(cancel):
                    cancel()
        except Exception:
            logger.debug("thumbnail detach cancel skipped", exc_info=True)
        self._last_visible_indices = None
        self._last_zoom_level = None
        self._feed_generation = None
        self.view = None

    def calculate_optimal_thumbnail_count(self) -> int:
        if self.view is None or not hasattr(self.view, "timeline"):
            return 50

        timeline = self.view.timeline
        content_height = timeline.height() - timeline.RULER_HEIGHT
        if content_height <= 0:
            return 50

        if not timeline.has_snapshots():
            return 50

        # Consume the installed toolkit viewport geometry (single source) —
        # never a duplicated tile/logical-width formula. Fail-open: any
        # doubt falls back to the legacy local math below.
        tile_width = 0.0
        logical_width = 0.0
        try:
            tile_width = float(timeline_viewport.get_base_tile_width(timeline))
            logical_width = float(timeline_viewport.get_logical_width(timeline))
        except Exception:
            tile_width = 0.0
            logical_width = 0.0
        if not tile_width > 0 or not logical_width > 0:
            aspect_ratio = 16.0 / 9.0
            tile_width = content_height * aspect_ratio
            total_duration = timeline.get_total_duration()
            px_per_sec = timeline.get_pixels_per_second()
            logical_width = total_duration * px_per_sec
        if logical_width <= 0 or tile_width <= 0:
            return 50

        visible_count = int(logical_width / tile_width) + 2
        return max(20, min(visible_count, 200))

    def generate_thumbnails(self):
        self._cancel_visible_refresh()
        try:
            from tabs.image_compare.debug import ic_thumbnail_debug
            tl = getattr(self.view, "timeline", None) if self.view is not None else None
            ic_thumbnail_debug("thumb_coord generate_thumbnails view=%s timeline=%s h=%s has_snapshots=%s total_frames=%s", bool(self.view), bool(tl), getattr(tl, "height", lambda: -1)() if tl else -1, bool(getattr(tl, "has_snapshots", lambda: False)() if tl else False), self.editor_service.get_frame_count() if self.editor_service else -1)
        except Exception:
            pass
        if self.view is not None and hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "clear_thumbnails"
        ):
            self.view.timeline.clear_thumbnails()

        recording = self.editor_service.get_current_recording()
        if not recording:
            try:
                from tabs.image_compare.debug import ic_thumbnail_debug
                ic_thumbnail_debug("thumb_coord generate_thumbnails ABORT no recording")
            except Exception:
                pass
            return

        vis = self.get_visible_frame_indices()
        cnt = self.calculate_optimal_thumbnail_count()
        try:
            from tabs.image_compare.debug import ic_thumbnail_debug
            ic_thumbnail_debug("thumb_coord generate_thumbnails target=%s vis_len=%s vis=%s fps=%s", cnt, len(vis), vis[:12], self.editor_service.get_fps())
        except Exception:
            pass
        # I4: mirror the queued generation so tagged completions can drop
        # late arrivals. A non-int return (test doubles, legacy services)
        # leaves the mirror unknown → fail-open.
        queued_generation = self.thumbnail_service.generate_thumbnails(
            recording,
            target_count=cnt,
            auto_crop=True,
            priority_indices=vis,
            fps=self.editor_service.get_fps(),
        )
        if isinstance(queued_generation, int):
            self._feed_generation = queued_generation
        self._last_visible_indices = list(vis)
        self._last_zoom_level = self._read_zoom_level()
        push_window = getattr(
            self.thumbnail_service, "set_visible_window", None
        )
        if callable(push_window):
            push_window(vis)

    def on_single_thumbnail_ready(
        self, index: int, pixmap: QPixmap, generation: int | None = None
    ):
        """Single-index upsert, tagged with its generation (I4).

        A tagged completion whose generation mismatches the mirrored feed
        generation is a late arrival from a retired wave and drops here —
        belt-and-braces behind the service-side token + captured-window
        filter in ``_on_thumbnail_generated``. ``generation=None`` (today's
        presenter wiring, which connects the 2-arg ``thumbnailReady``) and
        an unknown mirror fail open: the pixmap applies. Fail-open for
        DELIVERY; identity is enforced fail-closed on the service side.
        """
        try:
            from tabs.image_compare.debug import ic_thumbnail_debug
            ic_thumbnail_debug("thumb_coord on_single_ready idx=%s has_view=%s gen=%s feed=%s", index, bool(self.view), generation, self._feed_generation)
        except Exception:
            pass
        if (
            generation is not None
            and self._feed_generation is not None
            and generation != self._feed_generation
        ):
            try:
                from tabs.image_compare.debug import ic_thumbnail_debug
                ic_thumbnail_debug("thumb_coord on_single_ready DROP stale gen=%s feed=%s idx=%s", generation, self._feed_generation, index)
            except Exception:
                pass
            return
        if self.view is not None and hasattr(self.view, "timeline") and hasattr(
            self.view.timeline, "add_thumbnail"
        ):
            self.view.timeline.add_thumbnail(index, pixmap)

    def on_thumbnails_generated(self, thumbnails: Dict[int, QPixmap]):
        """Atomic generation replace (I4): apply, then fan out.

        The full dict goes straight to ``timeline.set_thumbnails`` — the
        single atomic-replace consumer (verified: the only
        ``presenter.thumbnailsUpdated`` listener is
        ``shell._on_thumbnails_updated`` → ``set_thumbnails``). The
        presenter hop is ``Signal(dict)``, which QVariantMap-converts
        QPixmap values away (receivers get ``{}`` → strip wipe), so the
        re-emit below is a fallback for headless/no-widget operation only
        — applied replaces never re-emit. A-shell owns the presenter
        signal; flipping it to ``Signal(object)`` restores the fanout.
        """
        applied = False
        if (
            self.view is not None
            and hasattr(self.view, "timeline")
            and hasattr(self.view.timeline, "set_thumbnails")
        ):
            try:
                self.view.timeline.set_thumbnails(dict(thumbnails))
                applied = True
            except Exception:
                logger.debug(
                    "bulk thumbnail replace skipped", exc_info=True
                )
        if not applied:
            self.emit_thumbnails_updated(thumbnails)

    def on_thumbnails_generation_finished(self):
        # P3 idle fill: the initial wave covered the visible window only
        # (visible-window-exact queue). Queue every still-unseen index at
        # background priority — generate_additional runs them at lower pool
        # priority and consults the P2 disk cache first, so a warm
        # remainder costs ~zero. track_finish=False there means this fill
        # never re-emits generationFinished: no loop, no second scheduler.
        try:
            if self.editor_service is None:
                return None
            total_frames = self.editor_service.get_frame_count()
            generated = set(
                getattr(self.thumbnail_service, "_generated_indices", None)
                or ()
            )
            pending = set(
                getattr(self.thumbnail_service, "_pending_indices", None) or ()
            )
            if not isinstance(total_frames, int) or total_frames <= 0:
                return None
            remainder = [
                i
                for i in range(total_frames)
                if i not in generated and i not in pending
            ]
            if remainder:
                self.thumbnail_service.generate_additional_thumbnails(
                    remainder,
                    fps=self.editor_service.get_fps(),
                )
        except Exception:
            logger.debug("Idle thumbnail remainder fill skipped", exc_info=True)
        return None

    def on_timeline_viewport_changed(self):
        try:
            from tabs.image_compare.debug import ic_thumbnail_debug
            ic_thumbnail_debug("thumb_coord viewportChanged ping gate_pending=%s", self._visible_refresh.is_pending())
        except Exception:
            pass
        self._ping_visible_refresh()

    def on_timeline_zoom_changed(self, *_args):
        # Zoom reshuffles geometry, not content — settle first, don't refit.
        try:
            from tabs.image_compare.debug import ic_thumbnail_debug
            ic_thumbnail_debug("thumb_coord zoomChanged ping gate_pending=%s", self._visible_refresh.is_pending())
        except Exception:
            pass
        self._ping_visible_refresh()

    def on_timeline_viewport_state_changed(self, _state=None):
        # Toolkit TimelineWidget emits viewportChangedState after its own
        # layout settle (fit_view/update_fixed_width) finishes — at that
        # point get_visible_thumbnail_frame_indices returns a settled window.
        # Bypass the extra debounce and refresh immediately.
        try:
            from tabs.image_compare.debug import ic_thumbnail_debug
            ic_thumbnail_debug("thumb_coord viewportChangedState cancel+refresh gate_pending=%s", self._visible_refresh.is_pending())
        except Exception:
            pass
        self._cancel_visible_refresh()
        self._refresh_visible_thumbnails()

    def _read_zoom_level(self) -> float | None:
        """Snapshot the timeline zoom scalar via the public pps API.

        Reads ``get_pixels_per_second`` only — never the toolkit-private
        ``_zoom_level``. None means "unknown": callers keep today's
        scroll-cancel behavior (fail-open).
        """
        try:
            tl = (
                getattr(self.view, "timeline", None)
                if self.view is not None
                else None
            )
            if tl is None:
                return None
            getter = getattr(tl, "get_pixels_per_second", None)
            if callable(getter):
                try:
                    return float(getter())
                except (TypeError, ValueError):
                    return None
            return None
        except Exception:
            return None

    def _refresh_visible_thumbnails(self):
        # NOTE: TimelineWidget.resizeEvent already updates zoom/logical_width
        # synchronously, so visible window is fresh even while _layout_settle
        # is pending (that's only for update_layout_width). Previous guard
        # `if settle.is_pending(): return` deferred forever during drag and
        # caused the strip to die — see plan 2026-09-02 Phase 2.
        try:
            tl = getattr(self.view, "timeline", None) if self.view is not None else None
            settle = getattr(tl, "_layout_settle", None) if tl is not None else None
            if settle is not None and hasattr(settle, "is_pending") and settle.is_pending():
                try:
                    from tabs.image_compare.debug import ic_thumbnail_debug
                    ic_thumbnail_debug("thumb_coord _refresh layout_settle pending but proceed anyway (resizeEvent already fresh)")
                except Exception:
                    pass
        except Exception:
            pass
        visible_indices = self.get_visible_frame_indices()
        try:
            from tabs.image_compare.debug import ic_thumbnail_debug
            tl = getattr(self.view, "timeline", None) if self.view is not None else None
            pps = tl.get_pixels_per_second() if tl and hasattr(tl, "get_pixels_per_second") else -1
            ic_thumbnail_debug("thumb_coord _refresh vis_len=%s vis=%s pps=%s total=%s pending=%s generated=%s", len(visible_indices), visible_indices[:12], pps, self.editor_service.get_frame_count() if self.editor_service else -1, len(getattr(self.thumbnail_service, "_pending_indices", [])), len(getattr(self.thumbnail_service, "_generated_indices", [])))
        except Exception:
            pass
        if visible_indices:
            # P3 scroll-cancel: the refresh path queues same-generation
            # additional workers, so without a bump a scrolled-away wave
            # would still apply on arrival. When the wanted set changed,
            # retire it first — non-blocking (unlike cancel()), progress
            # in _generated_indices and the P2 disk cache survive, and
            # cache hits still emit instantly with no worker. Unchanged
            # window → no bump (debounce re-settles must not churn the
            # token); no baseline yet (None) → nothing to retire.
            # Z4 zoom-aware: a zoom change reshuffles geometry, not content
            # — completions are index-addressed (P3), so the in-flight wave
            # stays valid and must NOT retire (retiring here emptied the
            # strip on every wheel tick). Zoom-driven refresh requeues the
            # newly-visible indices and lets the membership filter in
            # _on_thumbnail_generated drop whatever scrolled out of view.
            current_zoom = self._read_zoom_level()
            zoom_changed = (
                self._last_zoom_level is not None
                and current_zoom is not None
                and current_zoom != self._last_zoom_level
            )
            if self._last_visible_indices is not None and set(
                visible_indices
            ) != set(self._last_visible_indices):
                should_retire = not zoom_changed
                try:
                    from tabs.image_compare.debug import ic_thumbnail_debug
                    ic_thumbnail_debug(
                        "thumb_coord _refresh zoom_vs_pan zoom_changed=%s zoom=%s last_zoom=%s retire=%s",
                        zoom_changed,
                        current_zoom,
                        self._last_zoom_level,
                        should_retire,
                    )
                except Exception:
                    pass
                if should_retire:
                    retire = getattr(
                        self.thumbnail_service, "retire_in_flight_thumbnails", None
                    )
                    if callable(retire):
                        retired_generation = retire()
                        if isinstance(retired_generation, int):
                            self._feed_generation = retired_generation
            # NOTE (rep-remap, I1/I2): a zoom-driven refresh that skips the
            # retire above keeps the in-flight wave alive while the rep grid
            # remaps (strip_block_layout recomputes rep frames from geometry
            # alone). Completions stay index-addressed, so they remain valid
            # — the widget re-resolves each rep to its pixmap (or the
            # fail-closed placeholder when absent) on the next paint. Never
            # rebind a rep to a neighbor: missing is a placeholder.
            self._last_visible_indices = list(visible_indices)
            self._last_zoom_level = current_zoom
            push_window = getattr(
                self.thumbnail_service, "set_visible_window", None
            )
            if callable(push_window):
                push_window(visible_indices)
            self.thumbnail_service.generate_additional_thumbnails(
                visible_indices,
                fps=self.editor_service.get_fps(),
            )
        else:
            try:
                from tabs.image_compare.debug import ic_thumbnail_debug
                ic_thumbnail_debug("thumb_coord _refresh EMPTY no indices queued")
            except Exception:
                pass

    def get_visible_frame_indices(self, margin: int = 2) -> List[int]:
        if self.view is None or not hasattr(self.view, "timeline"):
            return []

        total_frames = self.editor_service.get_frame_count()
        if total_frames == 0:
            return []

        try:
            timeline = self.view.timeline
            if hasattr(timeline, "get_visible_thumbnail_frame_indices"):
                return [
                    idx
                    for idx in timeline.get_visible_thumbnail_frame_indices(
                        overscan_blocks=margin
                    )
                    if 0 <= idx < total_frames
                ]

            current_frame = self.playback_engine.get_current_frame()
            visible_range = 5
            start_idx = max(0, current_frame - visible_range - margin)
            end_idx = min(total_frames, current_frame + visible_range + margin)
            return list(range(start_idx, end_idx))
        except Exception as exc:
            logger.debug(f"Error calculating visible frames: {exc}")
            return list(range(min(10, total_frames)))

    def cleanup(self):
        # Idempotent: closeEvent teardown and view.destroyed both land here (the
        # second on a dead presenter) — gate cancel must survive missing C++.
        self._cancel_visible_refresh()
        self._feed_generation = None
        try:
            teardown = getattr(self.thumbnail_service, "teardown", None)
            if callable(teardown):
                teardown()
            else:
                self.thumbnail_service.cancel()
        except Exception:
            logger.debug("thumbnail cleanup cancel skipped", exc_info=True)
