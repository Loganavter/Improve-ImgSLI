"""Guards against a ``struct.pack`` format string drifting from the GPU
uniform-buffer size it's meant to fill.

Every ``pack_*_uniform*`` function pairs a hand-written format string with
a buffer-size constant used to allocate the actual ``QRhiBuffer`` -- nothing
ever checked the two agree. A mismatch (an edited format string, a field
added/removed on one side but not the other) doesn't raise: it silently
writes fewer/more bytes than the GPU buffer holds, landing as wrong values
in whichever uniform field the byte offset drifted into. That's exactly the
shape of bug this project burned a very long investigation on for the
magnifier's screen-position math (docs/dev/rendering/qrhi-gotchas.md
#magnifier-content-detaches-from-its-own-border-on-zoom-pan) -- a
numerically-plausible-looking value with no exception anywhere near it.

Call ``assert_uniform_size`` once at module load, right next to the format
string and size constant it checks -- it's a plain ``struct.calcsize``
comparison, free at runtime, and turns a silent GPU-side corruption into an
immediate, loud import-time failure with a message that names the two
constants to go compare by hand.
"""

from __future__ import annotations

import struct


def assert_uniform_size(fmt: str, expected_size: int, *, label: str) -> None:
    actual_size = struct.calcsize(fmt)
    if actual_size != expected_size:
        raise AssertionError(
            f"{label}: struct.pack format {fmt!r} is {actual_size} bytes, "
            f"but the declared uniform buffer size is {expected_size} bytes. "
            "These must match byte-for-byte, or the packed struct silently "
            "writes the wrong bytes into (or short of) the GPU buffer. Fix "
            "whichever of the format string / size constant / GLSL UBuf "
            "layout is out of sync."
        )
