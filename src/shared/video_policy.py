"""Single owner for video-recording fps numeric policy.

Cross-cutting rule per docs/dev/CODE_PATTERNS.md ("one home for a
cross-cutting policy"): every fps entry point (settings load/save, dialog,
lifecycle scheduler) calls into this module and never restates the
literals. Save and load clamp to the same band so save->load is a fixpoint
(CONTRACTS.md Dogma 6 - range discipline).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FpsPolicy:
    """Video-recording fps band: default 60, clamped to 10..144."""

    DEFAULT: int = 60
    MIN: int = 10
    MAX: int = 144


def clamp_fps(v: int) -> int:
    """Clamp ``v`` into [FpsPolicy.MIN, FpsPolicy.MAX]; non-int -> DEFAULT."""
    if isinstance(v, bool) or not isinstance(v, int):
        return FpsPolicy.DEFAULT
    return max(FpsPolicy.MIN, min(FpsPolicy.MAX, v))


def is_valid_fps(v: int) -> bool:
    """True when ``v`` is an int inside the fps band."""
    if isinstance(v, bool) or not isinstance(v, int):
        return False
    return FpsPolicy.MIN <= v <= FpsPolicy.MAX
