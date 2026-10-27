# provenance: src/engine/gpu/mip_cascade.py:558 @ bb6947d5d^ (parent of the mip-y-parity fix)
# rule: uv-flip-compensation
"""RED fixture: the mip cascade wrote an UNCONDITIONAL Y flip.

Verbatim from before the mip-Y fix (surrounding method trimmed to the flip).
The comment says "Unconditional Y-flip" — right on OpenGL/Vulkan, wrong on
D3D11, where every generated level came out inverted relative to its source and
the trilinear sampler blended upright mip0 with flipped mip1 ("bands of another
tile's content"). The flip is now `rt_y_orientation.sampled_rt_correction`.
"""

from __future__ import annotations

import struct


class MipCascadeGenerator:
    def _write_corr_once(self, rhi, slot_updates) -> None:
        if not self._downsample_corr_written:
            # Unconditional Y-flip (see _ensure_downsample_corr_buffer) --
            # diagonal, so row-major vs. column-major storage of the mat4
            # doesn't matter here.
            flip_data = (
                1.0, 0.0, 0.0, 0.0,
                0.0, -1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            )
            assert self._downsample_corr_buffer is not None
            slot_updates.updateDynamicBuffer(
                self._downsample_corr_buffer,
                0,
                struct.pack("<16f", *flip_data),
            )
            self._downsample_corr_written = True
