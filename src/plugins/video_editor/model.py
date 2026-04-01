from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Tuple

if TYPE_CHECKING:
    from core.main_controller import MainController
    from core.session_manager import SessionManager
    from core.store import Store

@dataclass(frozen=True)
class VideoTimelineState:
    position: int = 0

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "VideoTimelineState":
        payload = payload or {}
        return cls(position=max(0, int(payload.get("position", 0))))

    def advance(self, step: int = 1) -> "VideoTimelineState":
        return replace(self, position=max(0, self.position + int(step)))

    def to_dict(self) -> dict[str, Any]:
        return {"position": self.position}

@dataclass(frozen=True)
class VideoSelectionState:
    start: int | None = None
    end: int | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "VideoSelectionState":
        payload = payload or {}
        start = payload.get("start")
        end = payload.get("end")
        return cls(
            start=int(start) if start is not None else None,
            end=int(end) if end is not None else None,
        )

    def is_empty(self) -> bool:
        return self.start is None and self.end is None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.start is not None:
            payload["start"] = self.start
        if self.end is not None:
            payload["end"] = self.end
        return payload

@dataclass(frozen=True)
class VideoDecoderState:
    status: str = "attached"
    timeline_position: int = 0

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "VideoDecoderState | None":
        if not payload:
            return None
        return cls(
            status=str(payload.get("status", "attached")),
            timeline_position=max(0, int(payload.get("timeline_position", 0))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timeline_position": self.timeline_position,
        }

@dataclass(frozen=True)
class VideoSourceState:
    source_id: str
    source_type: str = "session"
    timeline_position: int = 0
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "VideoSourceState | None":
        if not payload:
            return None
        return cls(
            source_id=str(payload.get("source_id", "")),
            source_type=str(payload.get("source_type", "session")),
            timeline_position=max(0, int(payload.get("timeline_position", 0))),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "timeline_position": self.timeline_position,
            "metadata": dict(self.metadata or {}),
        }

@dataclass(frozen=True)
class VideoSessionSnapshot:
    title: str
    session_id: str
    timeline: VideoTimelineState
    selection: VideoSelectionState
    source: VideoSourceState | None
    decoder: VideoDecoderState | None
    resource_namespaces: tuple[str, ...]
    metadata: dict[str, Any]

class VideoSessionModel:
    TIMELINE_SLOT = "video.timeline"
    SELECTION_SLOT = "video.selection"
    RESOURCE_NAMESPACE = "video"
    SOURCE_RESOURCE_KEY = "source"
    DECODER_RESOURCE_KEY = "decoder"

    def __init__(
        self,
        *,
        store: "Store",
        session_manager: "SessionManager",
        main_controller: "MainController | None" = None,
        session_id: str | None = None,
    ):
        self.store = store
        self.session_manager = session_manager
        self.main_controller = main_controller
        self.session_id = session_id

    def get_snapshot(self) -> VideoSessionSnapshot:
        session = self._require_session()
        timeline = self._read_timeline_state(session.id)
        selection = self._read_selection_state(session.id)
        return VideoSessionSnapshot(
            title=session.title,
            session_id=session.id,
            timeline=timeline,
            selection=selection,
            source=self._read_source_state(session.id),
            decoder=self._read_decoder_state(session.id),
            resource_namespaces=tuple(
                namespace
                for namespace, _entries in self.store.iter_session_resources(
                    session_id=session.id
                )
            ),
            metadata=dict(session.metadata),
        )

    def advance_timeline(self) -> dict[str, Any]:
        session = self._require_session()
        timeline = self._read_timeline_state(session.id).advance()
        return self.store.set_session_state_slot(
            self.TIMELINE_SLOT,
            timeline.to_dict(),
            session_id=session.id,
            emit_scope="workspace",
        )

    def seek(self, position: int) -> dict[str, Any]:
        session = self._require_session()
        timeline = VideoTimelineState(position=max(0, int(position)))
        return self.store.set_session_state_slot(
            self.TIMELINE_SLOT,
            timeline.to_dict(),
            session_id=session.id,
            emit_scope="workspace",
        )

    def set_selection(self, start: int | None, end: int | None) -> dict[str, Any]:
        session = self._require_session()
        if start is None and end is None:
            selection = VideoSelectionState()
        else:
            normalized_start = max(0, int(start if start is not None else end))
            normalized_end = max(0, int(end if end is not None else start))
            selection = VideoSelectionState(
                start=min(normalized_start, normalized_end),
                end=max(normalized_start, normalized_end),
            )
        return self.store.set_session_state_slot(
            self.SELECTION_SLOT,
            selection.to_dict(),
            session_id=session.id,
            emit_scope="workspace",
        )

    def clear_selection(self) -> dict[str, Any]:
        return self.set_selection(None, None)

    def attach_source(
        self,
        source_id: str,
        *,
        source_type: str = "session",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self._require_session()
        timeline = self._read_timeline_state(session.id)
        source = VideoSourceState(
            source_id=source_id,
            source_type=source_type,
            timeline_position=timeline.position,
            metadata=dict(metadata or {}),
        )
        return self.store.set_session_resource(
            self.RESOURCE_NAMESPACE,
            self.SOURCE_RESOURCE_KEY,
            source.to_dict(),
            session_id=session.id,
            emit_scope="workspace",
        )

    def attach_decoder(self) -> dict[str, Any]:
        session = self._require_session()
        timeline = self._read_timeline_state(session.id)
        decoder = VideoDecoderState(timeline_position=timeline.position)
        return self.store.set_session_resource(
            self.RESOURCE_NAMESPACE,
            self.DECODER_RESOURCE_KEY,
            decoder.to_dict(),
            session_id=session.id,
            emit_scope="workspace",
        )

    def detach_source(self) -> dict[str, Any] | None:
        session = self._require_session()
        return self.store.pop_session_resource(
            self.RESOURCE_NAMESPACE,
            self.SOURCE_RESOURCE_KEY,
            session_id=session.id,
            emit_scope="workspace",
        )

    def detach_decoder(self) -> dict[str, Any] | None:
        session = self._require_session()
        return self.store.pop_session_resource(
            self.RESOURCE_NAMESPACE,
            self.DECODER_RESOURCE_KEY,
            session_id=session.id,
            emit_scope="workspace",
        )

    def open_image_compare(self):
        if self.main_controller is None:
            raise RuntimeError("MainController is required to open image compare")
        session = self._require_session()
        timeline = self._read_timeline_state(session.id)
        return self.main_controller.workspace.create_workspace_session(
            "image_compare",
            activate=True,
            metadata={
                "source_video_session_id": session.id,
                "source_timeline_position": timeline.position,
            },
        )

    def _read_timeline_state(self, session_id: str) -> VideoTimelineState:
        return VideoTimelineState.from_mapping(
            self.store.get_session_state_slot(
                self.TIMELINE_SLOT,
                session_id=session_id,
                default={},
            )
        )

    def _read_selection_state(self, session_id: str) -> VideoSelectionState:
        return VideoSelectionState.from_mapping(
            self.store.get_session_state_slot(
                self.SELECTION_SLOT,
                session_id=session_id,
                default={},
            )
        )

    def _read_decoder_state(self, session_id: str) -> VideoDecoderState | None:
        return VideoDecoderState.from_mapping(
            self.store.get_session_resource(
                self.RESOURCE_NAMESPACE,
                self.DECODER_RESOURCE_KEY,
                session_id=session_id,
                default=None,
            )
        )

    def _read_source_state(self, session_id: str) -> VideoSourceState | None:
        return VideoSourceState.from_mapping(
            self.store.get_session_resource(
                self.RESOURCE_NAMESPACE,
                self.SOURCE_RESOURCE_KEY,
                session_id=session_id,
                default=None,
            )
        )

    def _require_session(self):
        session = (
            self.session_manager.get_session(self.session_id)
            if self.session_id is not None
            else self.session_manager.get_active_session()
        )
        if session is None or session.session_type != "video_compare":
            raise ValueError("Video session is not available")
        return session

@dataclass
class VideoProjectModel:

    width: int = 1920
    height: int = 1080

    fps: int = 60

    aspect_ratio_locked: bool = True
    original_ratio: float = 16 / 9

    container: str = "mp4"
    codec: str = "h264"
    quality_mode: str = "crf"
    crf: int = 23
    bitrate: str = "8000k"
    preset: str = "medium"
    pix_fmt: str = "yuv420p"

    manual_mode: bool = False
    manual_args: str = "-c:v libx264 -crf 23 -pix_fmt yuv420p"

    def get_resolution(self) -> Tuple[int, int]:
        return self.width, self.height

    def set_resolution(self, width: int, height: int):
        self.width = width
        self.height = height

        if not self.aspect_ratio_locked and height > 0:
            self.original_ratio = width / height

    def get_aspect_ratio(self) -> float:
        if self.height > 0:
            return self.width / self.height
        return 16 / 9

    def adjust_height_to_aspect_ratio(self, width: int) -> int:
        if not self.aspect_ratio_locked or self.original_ratio <= 0:
            return self.height

        new_height = int(width / self.original_ratio)

        if new_height % 2 != 0:
            new_height += 1
        return new_height

    def adjust_width_to_aspect_ratio(self, height: int) -> int:
        if not self.aspect_ratio_locked or self.original_ratio <= 0:
            return self.width

        new_width = int(height * self.original_ratio)

        if new_width % 2 != 0:
            new_width += 1
        return new_width
