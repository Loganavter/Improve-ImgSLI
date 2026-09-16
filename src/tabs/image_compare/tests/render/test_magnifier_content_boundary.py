"""F4 magnifier-content permanent boundary pin.

F0 verdict SPLIT, F4 verdict BOUNDARY (see ``magnifier_pass.py`` module
docstring ``F4-BOUNDARY``): arcs/border already ride the v2 semantic seam
(F2), while the array-sampled content path stays tab-side permanently.
This test pins the boundary from both sides so a silent drift either way
fails loudly:

1. array-shape markers PRESENT tab-side (``magnifier_pass.py`` +
   ``mag.frag``): externally-held texture array, strided dynamic-offset
   uniforms, per-frame SRB rebuild, dual pipelines, and the in-code
   3-part proof (docstring + ``F4-BOUNDARY`` site comments);
2. array-shape markers ABSENT engine-side (``shell.py`` /
   ``textured.py``): neither shell names a texture array, a dynamic
   uniform offset, or an array sampler -- the conjunction the content
   path needs exists only in the magnifier pass;
3. record path + hold gates untouched: the dynamic-offset draw loop and
   both residency hold gates still exist with their historic names
   (ruling 4: math moves, gating stays).

Invalidation (also in the module docstring): if content ever drops array
sampling, this file -- not the pass -- is what changes: single raster
upload migrates to ``TexturedOverlayShell``, pure decoration to
``OverlayShell`` + ``semantic.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_RENDER_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "canvas"
    / "features"
    / "magnifier"
    / "render"
)
_PASS_SRC = (_RENDER_DIR / "magnifier_pass.py").read_text()
_MAG_FRAG_SRC = (
    _RENDER_DIR.parent / "shaders" / "qrhi" / "mag.frag"
).read_text()
_ENGINE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "src" / "engine" / "overlay"
_SHELL_SRC = (_ENGINE_DIR / "shell.py").read_text()
_TEXTURED_SRC = (_ENGINE_DIR / "textured.py").read_text()


def test_array_markers_present_in_magnifier_pass():
    """Content path keeps its array shape: held array + dynamic offsets."""
    assert "newTextureArray" in _PASS_SRC  # placeholder array fallback
    assert "uniformBufferWithDynamicOffset" in _PASS_SRC  # strided SRB
    assert "tile_arrays[0]" in _PASS_SRC  # held, not owned, array consume
    assert "ubufAligned" in _PASS_SRC  # strided uniform buffer
    assert "MAG_UNIFORM_SIZE" in _PASS_SRC  # 288B block layout


def test_mag_shader_samples_externally_owned_array():
    """mag.frag samples a sampler2DArray no engine shell declares."""
    assert "sampler2DArray" in _MAG_FRAG_SRC


def test_three_part_proof_lives_in_code():
    """Boundary proof is in the pass, not in a doc or a commit message."""
    assert "F4-BOUNDARY" in _PASS_SRC
    assert "PERMANENT BOUNDARY" in _PASS_SRC
    assert "INVALIDATION" in _PASS_SRC


def test_array_markers_absent_from_engine_shells():
    """No existing shell hosts the array conjunction (uniqueness, part 2)."""
    for src in (_SHELL_SRC, _TEXTURED_SRC):
        assert "newTextureArray" not in src
        assert "uniformBufferWithDynamicOffset" not in src
        assert "sampler2DArray" not in src
        assert "tile_arrays" not in src


def test_record_path_and_hold_gates_untouched():
    """Ruling 4: record stays a dynamic-offset draw loop; gates keep names."""
    assert "index * stride" in _PASS_SRC  # dynamic-offset draw
    assert "_lens_residency_hold" in _PASS_SRC
    assert "_frame_slices_residency_hold" in _PASS_SRC
    assert "_frame_draw_tile_indices" in _PASS_SRC


def test_no_tab_side_scale_definition():
    """Scale math stays engine-owned: tab imports, never defines, scale.

    (Built without the literal tab-side scale-def pattern so this pin
    itself keeps the ruling grep clean -- only pre-existing
    engine-import aliases may match.)
    """
    import re

    assert "from engine.cache.draw_plans import" in _PASS_SRC
    assert re.search(r"def \w*content" + "_scale", _PASS_SRC) is None
