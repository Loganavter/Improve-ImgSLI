"""
Runtime cache that lives on the Store but is NEVER touched by reducers.

Purpose: keep state that is written by presenters/renderers as a side effect
of rendering (texture identity hashes, last-used clip rects, etc.) separate
from reducible application state. If a field belongs here, it must NOT be
derivable from actions, and it must NOT influence reducer output.

By construction, any field added to this class cannot be accidentally wiped
by a reducer that forgets to preserve it — reducers do not have access to
this object.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass
class ViewportRuntimeCache:
    last_source1_id: int = 0
    last_source2_id: int = 0
    overlay_clip_rect: tuple[int, int, int, int] | None = None

    def reset(self) -> None:
        self.last_source1_id = 0
        self.last_source2_id = 0
        self.overlay_clip_rect = None
