from __future__ import annotations

class KeyframingValidationError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        message: str,
        tool_id: str | None = None,
        track_id: str | None = None,
        channel_id: str | None = None,
        timestamp: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.tool_id = tool_id
        self.track_id = track_id
        self.channel_id = channel_id
        self.timestamp = timestamp
