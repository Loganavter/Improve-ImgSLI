"""Thin wrapper around the toolkit's generic TimelineWidget.

App-specific semantics (prominent track ids, token translations,
is_track_active branches) are contributed by tabs through the registry hook
and consumed by generic callbacks in app_callbacks. This wrapper stays
tab-agnostic.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    TimelineCallbacks,
    TimelineWidget,
)

from .app_callbacks import (
    app_is_track_active,
    app_localize_token,
    app_localize_value,
    app_should_show_track,
    app_visible_channels,
    get_prominent_track_ids,
)


class VideoTimelineWidget(TimelineWidget):
    """Video timeline widget with tab-contributed semantics."""

    def __init__(self, snapshots=None, parent=None, store=None):
        prominent = frozenset(get_prominent_track_ids())
        callbacks = TimelineCallbacks(
            should_show_track=app_should_show_track,
            visible_channels=app_visible_channels,
            is_track_active=app_is_track_active,
            localize_token=app_localize_token,
            localize_value=app_localize_value,
            prominent_track_ids=prominent,
        )
        super().__init__(
            snapshots=snapshots,
            parent=parent,
            store=store,
            callbacks=callbacks,
        )
        self._PROMINENT_TRACK_IDS = prominent
