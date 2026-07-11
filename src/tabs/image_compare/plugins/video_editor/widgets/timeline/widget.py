"""App-specific thin wrapper around the toolkit's generic TimelineWidget."""

from __future__ import annotations

import math

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
)

_APP_PROMINENT_TRACK_IDS = {
    "splitter.main.position",
}

class VideoTimelineWidget(TimelineWidget):
    """VideoTimelineWidget with app-specific track filtering and i18n."""

    def __init__(self, snapshots=None, parent=None, store=None):
        callbacks = TimelineCallbacks(
            should_show_track=app_should_show_track,
            visible_channels=app_visible_channels,
            is_track_active=app_is_track_active,
            localize_token=app_localize_token,
            localize_value=app_localize_value,
            prominent_track_ids=_APP_PROMINENT_TRACK_IDS,
        )
        super().__init__(
            snapshots=snapshots,
            parent=parent,
            store=store,
            callbacks=callbacks,
        )
        self._PROMINENT_TRACK_IDS = _APP_PROMINENT_TRACK_IDS
