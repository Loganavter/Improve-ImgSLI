from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

@dataclass
class TraceRecord:
    seq: int
    ts: float
    kind: str
    trace_id: str | None
    depth: int
    summary: str
    caller: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "kind": self.kind,
            "trace_id": self.trace_id,
            "depth": self.depth,
            "summary": self.summary,
            "caller": self.caller,
            "payload": self.payload,
        }

def now() -> float:
    return time.monotonic()
