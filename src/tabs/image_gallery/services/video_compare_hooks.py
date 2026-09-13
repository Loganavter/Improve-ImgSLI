"""Stage 4 hooks for future video-compare intake — placeholders only.

Spec: "Добавь video-compare hooks stubs для Stage 4: comment/placeholder."

Video-compare will follow the same triage contract as image gallery (design.md:230
Phasing Stage 4). This module provides no-op hooks that will later wire folder
triage into ``tabs/image_compare/plugins/video_editor`` and multi-compare.

Keep as comment/placeholder — no runtime effect in Stage 3.
"""

from __future__ import annotations

from pathlib import Path


def prepare_video_compare_intake(folder: Path) -> dict:
    """Stage 4 placeholder: collect video intake from gallery triage.

    Future: map ``GalleryState.series`` + finalists into video-editor timeline
    sessions. Currently returns empty descriptor — callers should treat as no-op.
    """
    # STAGE4_TODO: wire to tabs/image_compare/plugins/video_editor/services/timeline.py
    # - detect video files in folder (same scan as images but VIDEO_EXTS)
    # - cluster by perceptual hash (first frame) → series
    # - expose compare_finalists → video_editor.create_session
    return {"folder": str(folder), "videos": [], "series": [], "stage": "placeholder"}


def dispatch_to_video_compare(paths: list[Path]) -> bool:
    """Stage 4 placeholder: dispatch finalists into video-compare workspace.

    Future: use ``events/image_carry.py`` style handoff but for video_editor
    ( ``image_carry`` currently handles stills → ImageCompare/MultiCompare ).
    Returns False until implemented.
    """
    # STAGE4_TODO: route via TabRegistry.create_service_for("image_compare", "create_video_session", paths)
    return False


# -- contract note for docs/dev/tabs ----------------------------------
# Stage 4 verification will add:
#   tests/contracts/test_gallery_video_hooks.py — asserts these stubs exist
#   and are importable without side effects (no Qt, pure).
# Until then they are documented as placeholders and must not be called
# from production paths (controller/widget guard with `if False:`).
