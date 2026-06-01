from ui.canvas_features.magnifier.shaders.programs import (
    compile_shader_program,
    shader_prolog,
)
from ui.canvas_features.magnifier.shaders.sources import (
    ARC_FRAG,
    ARC_VERT,
    BORDER_DISK_FRAG,
    MAG_VERT,
    MagShaderKey,
    build_mag_frag,
)

__all__ = [
    "ARC_FRAG",
    "ARC_VERT",
    "BORDER_DISK_FRAG",
    "MAG_VERT",
    "MagShaderKey",
    "build_mag_frag",
    "compile_shader_program",
    "shader_prolog",
]
