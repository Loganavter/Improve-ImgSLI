"""Stage 4 hooks for future video-compare intake — placeholders only.

Spec: "Добавь video-compare hooks stubs для Stage 4: comment/placeholder."

Video-compare will follow the same triage contract as image gallery (design.md:230
Phasing Stage 4). This module provides no-op hooks that will later wire folder
triage into ``tabs/image_compare/plugins/video_editor`` and multi-compare.

Keep as comment/placeholder — no runtime effect in Stage 3.
"""

from __future__ import annotations


# -- contract note for docs/dev/tabs ----------------------------------
# Stage 4 verification will add:
#   tests/contracts/test_gallery_video_hooks.py — asserts these stubs exist
#   and are importable without side effects (no Qt, pure).
# Until then they are documented as placeholders and must not be called
# from production paths (controller/widget guard with `if False:`).
