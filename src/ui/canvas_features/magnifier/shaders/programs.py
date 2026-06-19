from __future__ import annotations

import logging

from PySide6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram

_log = logging.getLogger("ImproveImgSLI")


def shader_prolog(is_gles: bool, *, fragment: bool = False) -> str:
    if not is_gles:
        return "#version 330 core"
    lines = ["#version 300 es", "precision highp float;", "precision highp int;"]
    if fragment:
        lines.append("precision mediump sampler2D;")
    return "\n".join(lines)


def compile_shader_program(
    widget,
    vert_src: str,
    frag_src: str,
    label: str,
) -> QOpenGLShaderProgram | None:
    prog = QOpenGLShaderProgram()
    ok_v = prog.addShaderFromSourceCode(
        QOpenGLShader.ShaderTypeBit.Vertex,
        vert_src,
    )
    ok_f = prog.addShaderFromSourceCode(
        QOpenGLShader.ShaderTypeBit.Fragment,
        frag_src,
    )
    linked = prog.link()
    if not (ok_v and ok_f and linked):
        _log.error("%s: shader compile/link failed: %s", label, prog.log())
        return None
    return prog
