"""Data model for the Image Gallery tab — controller-local, not a Redux store slice.

Folder contents are derived from disk on demand; nothing here needs to survive
a session switch beyond the last-opened folder path (persisted separately via
``context.store.set_session_state_slot``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QPixmap


class ThumbnailStatus(str, Enum):
    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"


class AnalysisStatus(str, Enum):
    NOT_ANALYZED = "not_analyzed"
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"


class Mode(str, Enum):
    FIDELITY = "fidelity"
    CAMERA = "camera"
    BATCH_SYNTHETIC = "batch_synthetic"


class Severity(str, Enum):
    CLEAN = "clean"
    MILD = "mild"
    FLAGGED = "flagged"


class Artifact(str, Enum):
    BANDING = "banding"
    HALO = "halo"
    OVER_SMOOTHING = "over_smoothing"
    INVENTED_TEXTURE = "invented_texture"
    BLOCKING = "blocking"
    CHROMA_FRINGING = "chroma_fringing"
    NOISE_AMPLIFICATION = "noise_amplification"


class TriageState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class AiDefect:
    """One quality defect the model reported (kind + severity + note)."""

    kind: str
    severity: str = "mild"  # "clean" | "mild" | "flagged"
    note: str = ""


@dataclass(frozen=True)
class AiAnalysisResult:
    description: str
    tags: tuple[str, ...]
    model: str
    analyzed_at_iso: str
    # Technical-quality verdict (the app's analysis format). Axis scores are
    # 0-100 quality (higher=better), -1 means unscored. ``sharpness``/
    # ``noise``/``exposure`` are filled from the MEASURED detectors (the
    # model's own estimates are not trusted there); ``composition`` is the
    # AI-only axis. ``description``/``tags`` are legacy/optional — the
    # gallery reports quality, not scene content.
    sharpness: int = -1
    noise: int = -1
    exposure: int = -1
    composition: int = -1
    verdict: str = "unknown"  # "keep" | "reject" | "unknown"
    verdict_reason: str = ""
    defects: tuple[AiDefect, ...] = ()
    confidence: float = 0.0
    # Short, vision-based note per axis (canonical metric id → phrase), shown
    # next to the metric label, e.g. {"noise": "coarse film grain"}.
    axis_notes: dict[str, str] = field(default_factory=dict)


def ai_quality_score(result: AiAnalysisResult | None) -> float | None:
    """Mean of the scored axes (0-100), or None when nothing is scored."""
    try:
        if result is None:
            return None
        axes = [
            result.sharpness,
            result.noise,
            result.exposure,
            result.composition,
        ]
        scored = [int(v) for v in axes if int(v) >= 0]
    except Exception:
        return None
    if not scored:
        return None
    return sum(scored) / len(scored)


@dataclass(frozen=True)
class TieBreakResult:
    """Stage 3 VLM tie-break decision for top-2 of a series."""

    winner_path: str
    loser_path: str
    reason: str
    confidence: float
    model: str
    decided_at_iso: str


@dataclass(frozen=True)
class CompareBrief:
    """Stage 3 structured difference report — one per finalist pair."""

    pair: tuple[str, str]
    summary: str
    differences: tuple[str, ...]
    tags: tuple[str, ...]
    model: str
    created_at_iso: str


@dataclass
class GalleryItem:
    path: Path
    mtime_ns: int
    thumbnail_status: ThumbnailStatus = ThumbnailStatus.NOT_LOADED
    thumbnail: "QPixmap | None" = None
    analysis_status: AnalysisStatus = AnalysisStatus.NOT_ANALYZED
    analysis: AiAnalysisResult | None = None
    analysis_error: str | None = None
    series_id: str | None = None
    rank: int | None = None
    metrics: dict = field(default_factory=dict)
    # Stage 2 triage fields — crown/reject/S3 safety model (design.md:87-99,129-136)
    rejected: bool = False
    is_best: bool = False
    crown_rank: int | None = None
    provenance_series_id: str | None = None
    # Stage 2 artifact catalog — 7 detectors, severity per artifact (design.md:67-83)
    artifacts: dict[Artifact, Severity] = field(default_factory=dict)
    # Coarse localization per artifact name ({name: [[0..1]*grid]*grid}) for the
    # axes that fired — a "where to look" hint (SalArt-VQA grounding).
    artifact_maps: dict = field(default_factory=dict)
    # Stage 3 VLM fields — tie-break pending/silent degrade + compare briefs
    vlm_tie_pending: bool = False
    vlm_tie_result: TieBreakResult | None = None
    vlm_tie_error: str | None = None
    vlm_brief: CompareBrief | None = None
    vlm_brief_status: str = "none"
    vlm_brief_error: str | None = None

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class Series:
    id: str
    members: list[GalleryItem]
    centroid: list[float] | None = None
    phash_centroid: int | None = None


@dataclass
class GalleryState:
    folder: Path | None = None
    items: list[GalleryItem] = field(default_factory=list)
    filter_text: str = ""
    selected_paths: set[Path] = field(default_factory=set)
    selected_order: list[Path] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    mode: Mode | None = None
    source_path: Path | None = None
    triage_state: TriageState = TriageState.IDLE
    # Stage 3 VLM caches (mirrors disk cache in vlm_cache)
    tie_breaks: dict[str, TieBreakResult] = field(default_factory=dict)
    briefs: dict[str, CompareBrief] = field(default_factory=dict)
