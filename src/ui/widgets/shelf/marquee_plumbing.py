"""Shared marquee drag plumbing for tab shelf/grid views.

The mechanism (drag tracker, band visual, scroll-compensated rect math) is
canonical in ``sli_ui_toolkit`` (``MarqueeState`` / ``MarqueeBandWidget`` /
``resolve_band_rects``). The tab-specific parts — turning a band rect into
hit paths (``hit_test``) and applying preview/commit to tab state
(``preview`` / ``commit``) — stay in the tabs. This module owns everything
in between, parameterized by a small :class:`MarqueeWiring` bundle, so the
gallery grid and the session-picker recent shelf stop carrying
near-identical copies of the same drag plumbing (a divergence there once
left the gallery band invisible while selection kept working).

Conventions the wiring relies on (same names in every consumer view):

- ``view.items_host`` — content widget the gesture tracks (host-local coords).
- ``view.scroll_area`` — scroll area whose ``viewport()`` parents the band.
- ``view._marquee_gesture`` / ``view._marquee_additive`` / ``view._marquee_base``
  — gesture holder, Ctrl-additive flag, press-time selection snapshot.
- ``view._marquee_press_pos`` / ``view._marquee_press_scroll`` — press-time
  bookkeeping for mid-drag scroll compensation.
- ``view._marquee_last_update_sig`` — coalescing signature (reset per press).
- ``view._marquee_band`` — cached ``MarqueeBandWidget`` (created lazily).
- ``view._selection_accent`` — band accent (optional; toolkit default wins
  when absent).

All helpers are fail-open: a view without ``scroll_area`` (e.g. unit-test
doubles) still gets hit-testing/selection, just no band visual.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from sli_ui_toolkit.widgets import MarqueeBandWidget, MarqueeState, resolve_band_rects

from ui.widgets.shelf.selection import ctrl_held


def _noop_trace(msg: str, *args: Any) -> None:
    """Default trace: silent (tabs pass their env-gated logger to be heard)."""


@dataclasses.dataclass(frozen=True)
class MarqueeWiring:
    """Tab-specific ends of the shared drag plumbing.

    ``hit_test(view, rect)`` maps a content-space band rect to selection
    paths (tab geometry). ``preview(view, paths, additive)`` applies a
    live preview without committing. ``commit(view, paths, additive)``
    commits the finished band — the empty set is passed through for
    empty/tiny finishes, so clear-vs-keep lives in the tab callback.
    ``base_snapshot(view)`` reads the press-time selection.
    ``press_preview(view, additive)`` runs right after band start (live
    clear for non-additive drags). ``trace(msg, *args)`` is the env-gated
    log sink; ``state_trace(line)`` feeds ``MarqueeState`` tracker lines
    (``None`` keeps the tracker silent).
    """

    hit_test: Callable[[Any, QRect], set]
    preview: Callable[[Any, set, bool], None]
    commit: Callable[[Any, set, bool], None]
    base_snapshot: Callable[[Any], set]
    press_preview: Callable[[Any, bool], None]
    trace: Callable[..., None] = _noop_trace
    state_trace: Callable[[str], None] | None = None


def scroll_offset(view: Any) -> QPoint:
    """Live scroll offset in content px ((h, v) scrollbar values)."""
    try:
        area = getattr(view, "scroll_area", None)
        h = v = 0
        if area is not None:
            try:
                bar_h = area.horizontalScrollBar()
                h = int(bar_h.value()) if bar_h is not None else 0
            except Exception:
                pass
            try:
                bar_v = area.verticalScrollBar()
                v = int(bar_v.value()) if bar_v is not None else 0
            except Exception:
                pass
        return QPoint(h, v)
    except Exception:
        return QPoint(0, 0)


def band_widget(view: Any) -> MarqueeBandWidget | None:
    """Lazy viewport band widget (floats above host + cards)."""
    band = getattr(view, "_marquee_band", None)
    if band is None:
        try:
            viewport = view.scroll_area.viewport()
            band = MarqueeBandWidget(viewport)
            try:
                accent = getattr(view, "_selection_accent", None)
                if accent is not None:
                    band.set_accent(accent)
            except Exception:
                pass
            view._marquee_band = band  # type: ignore[attr-defined]
        except Exception:
            return None
    return band


def band_rects(view: Any, rect: QRect) -> tuple[QRect, QRect]:
    """Scroll-compensated (viewport_rect, content_rect); toolkit math."""
    try:
        return resolve_band_rects(
            getattr(view, "_marquee_press_pos", None),
            getattr(view, "_marquee_press_scroll", None),
            rect,
            scroll_offset(view),
        )
    except Exception:
        return QRect(rect), QRect(rect)


def ensure_gesture(view: Any, wiring: MarqueeWiring) -> MarqueeState:
    """Lazily create the toolkit ``MarqueeState`` holder for *view*."""
    gesture = getattr(view, "_marquee_gesture", None)
    host = getattr(view, "items_host", None)
    if gesture is not None and not isinstance(gesture, MarqueeState):
        # Pre-unify holder: drop it so the tab never mixes visuals.
        try:
            gesture.cancel()
        except Exception:
            pass
        gesture = None
    if gesture is None:
        gesture = MarqueeState(
            host,
            parent=view,
            on_update=lambda r: on_rect_update(view, r, wiring),
            on_finish=lambda r: on_rect_finish(view, r, wiring),
            on_trace=wiring.state_trace,
        )
        try:
            view._marquee_gesture = gesture  # type: ignore[attr-defined]
        except Exception:
            pass
    else:
        try:
            viewport = view.scroll_area.viewport()
        except Exception:
            viewport = None
        try:
            gesture.set_clip_widget(viewport)
        except Exception:
            pass
    accent = getattr(view, "_selection_accent", None)
    if accent is not None:
        # The gesture keeps it for traces; the band widget paints with it.
        for target in (gesture, band_widget(view)):
            try:
                if target is not None and hasattr(target, "set_accent"):
                    target.set_accent(accent)
            except Exception:
                pass
    return gesture


def refresh_accent(view: Any, accent: Any = None) -> None:
    """Resync the band accent after a theme flip (gesture + band widget)."""
    if accent is None:
        accent = getattr(view, "_selection_accent", None)
    else:
        try:
            view._selection_accent = accent  # type: ignore[attr-defined]
        except Exception:
            pass
    if accent is None:
        return
    gesture = getattr(view, "_marquee_gesture", None)
    if gesture is not None:
        try:
            gesture.set_accent(accent)
        except Exception:
            pass
    try:
        band = getattr(view, "_marquee_band", None)
        if band is not None and hasattr(band, "set_accent"):
            band.set_accent(accent)
    except Exception:
        pass


def on_rect_update(view: Any, rect: QRect, wiring: MarqueeWiring) -> None:
    """Preview selection while the band is dragging.

    Coalescing: the gesture emits per mousemove (100+/s unthrottled) but
    most moves do not change membership. When the normalized hit set +
    additive flag match the last dispatched update, only the band visual
    (already moved above) shifts and this returns early. The signature
    resets on every new press, and ``on_rect_finish`` always recomputes,
    so a mid-drag layout shift can delay one preview frame at most, never
    a commit.
    """
    try:
        import time as _time

        _t_hit_start = _time.perf_counter()
    except Exception:
        _t_hit_start = None  # type: ignore[assignment]
    # Band visual (viewport space, over cards) + scroll-corrected content
    # rect for hit-testing — the two never diverge by construction.
    try:
        viewport_rect, rect = band_rects(view, rect)
    except Exception:
        viewport_rect = rect
    try:
        band = band_widget(view)
        if band is not None:
            band.set_band(viewport_rect)
    except Exception:
        pass
    paths = wiring.hit_test(view, rect)
    try:
        _t_hit_ms = (_time.perf_counter() - _t_hit_start) * 1000.0  # type: ignore[operator]
    except Exception:
        _t_hit_ms = -1.0
    try:
        additive = bool(getattr(view, "_marquee_additive", False))
    except Exception:
        additive = False
    try:
        sig = (frozenset(str(p) for p in paths), additive)
    except Exception:
        sig = None
    if sig is not None and getattr(view, "_marquee_last_update_sig", None) == sig:
        try:
            wiring.trace("marquee UPDATE-skip identical membership")
        except Exception:
            pass
        return
    try:
        view._marquee_last_update_sig = sig  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        wiring.trace(
            "marquee UPDATE rect=(%d,%d %dx%d) paths=%d additive=%s hit=%.1fms",
            rect.x(), rect.y(), rect.width(), rect.height(),
            len(paths), additive, _t_hit_ms,
        )
    except Exception:
        pass
    wiring.preview(view, paths, additive)


def on_rect_finish(view: Any, rect: QRect, wiring: MarqueeWiring) -> None:
    """Commit selection when the band finishes (empty set clears or keeps)."""
    try:
        band = band_widget(view)
        if band is not None:
            band.set_active(False)
    except Exception:
        pass
    # Compensate only real bands: empty (tiny-finish) rects must stay empty
    # so the tab commit callback still sees the clear/keep decision.
    if not rect.isEmpty():
        try:
            _, rect = band_rects(view, rect)
        except Exception:
            pass
    try:
        wiring.trace(
            "marquee FINISH rect=(%d,%d %dx%d) empty=%s additive=%s",
            rect.x(), rect.y(), rect.width(), rect.height(), rect.isEmpty(),
            bool(getattr(view, "_marquee_additive", False)),
        )
    except Exception:
        pass
    if rect.isEmpty():
        paths: set = set()
    else:
        paths = wiring.hit_test(view, rect)
    try:
        additive = bool(getattr(view, "_marquee_additive", False))
    except Exception:
        additive = False
    wiring.commit(view, paths, additive)


def host_mouse_press(view: Any, event: QMouseEvent, wiring: MarqueeWiring) -> bool:
    """Start a band on empty-host left press; ``False`` falls through."""
    if event.button() != Qt.MouseButton.LeftButton:
        try:
            wiring.trace("marquee press REFUSE button=%s (not Left)", event.button())
        except Exception:
            pass
        return False
    host = getattr(view, "items_host", None)
    if host is None:
        try:
            wiring.trace("marquee press REFUSE reason=no-host")
        except Exception:
            pass
        return False
    try:
        press_pos = event.position().toPoint()
    except Exception:
        press_pos = None
    try:
        child = host.childAt(press_pos) if press_pos is not None else None
    except Exception:
        child = None
    if child is not None:
        try:
            wiring.trace(
                "marquee press REFUSE pos=%s child=%s (not empty host)",
                press_pos, type(child).__name__,
            )
        except Exception:
            pass
        return False
    try:
        additive = bool(ctrl_held(event.modifiers()))
    except Exception:
        additive = False
    try:
        view._marquee_additive = additive  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        base = wiring.base_snapshot(view)
        view._marquee_base = set(base) if base is not None else set()  # type: ignore[attr-defined]
    except Exception:
        try:
            view._marquee_base = set()  # type: ignore[attr-defined]
        except Exception:
            pass
    # New gesture: drop the coalescing signature so the first update of
    # this drag always dispatches (its base may differ from the last drag).
    try:
        view._marquee_last_update_sig = None  # type: ignore[attr-defined]
    except Exception:
        pass
    # Scroll basis for mid-drag compensation — stashed BEFORE start:
    # start() emits the first on_update synchronously, and band_rects
    # reads this basis. Stashing after start (as before) mixed the new
    # origin with the previous drag's basis, flashing a stale-based band
    # for a couple of frames on every press (bare clicks included).
    try:
        view._marquee_press_pos = event.position().toPoint()  # type: ignore[attr-defined]
        view._marquee_press_scroll = scroll_offset(view)  # type: ignore[attr-defined]
    except Exception:
        pass
    gesture = ensure_gesture(view, wiring)
    try:
        if not gesture.start(event.position().toPoint()):
            try:
                wiring.trace(
                    "marquee press IGNORED (gesture refused) pos=%s",
                    event.position().toPoint(),
                )
            except Exception:
                pass
            return False
    except Exception as exc:
        try:
            wiring.trace("marquee press FAILED err=%r", exc)
        except Exception:
            pass
        return False
    try:
        band = band_widget(view)
        if band is not None:
            band.set_active(True)
    except Exception:
        pass
    try:
        wiring.trace(
            "marquee press START pos=%s additive=%s base_n=%s gesture_active=%s",
            event.position().toPoint(), additive,
            len(getattr(view, "_marquee_base", set()) or set()),
            bool(getattr(gesture, "active", False)),
        )
    except Exception:
        pass
    # Live preview clear for non-additive drags (tab decides the shape).
    wiring.press_preview(view, additive)
    return True


def event_filter(view: Any, watched: QObject, event: QEvent, wiring: MarqueeWiring) -> bool:
    """Host mouse press → start band (installed on the items host)."""
    try:
        host = getattr(view, "items_host", None)
    except Exception:
        host = None
    if (
        host is not None
        and watched is host
        and event.type() == QEvent.Type.MouseButtonPress
        and isinstance(event, QMouseEvent)
    ):
        return host_mouse_press(view, event, wiring)
    return False
