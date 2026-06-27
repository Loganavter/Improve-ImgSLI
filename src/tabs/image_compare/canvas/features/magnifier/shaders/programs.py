"""Legacy GL shader helpers retained as no-ops post-QRhi migration."""

from __future__ import annotations


def shader_prolog(is_gles: bool, *, fragment: bool = False) -> str:
    """Return the GLSL prolog string the legacy GL pipeline used.

    The QRhi pipeline compiles shaders ahead of time via qsb, so this is
    unused at runtime — but legacy helper imports still resolve to it.
    """
    if not is_gles:
        return "#version 330 core"
    lines = ["#version 300 es", "precision highp float;", "precision highp int;"]
    if fragment:
        lines.append("precision mediump sampler2D;")
    return "\n".join(lines)


def compile_shader_program(widget, vert_src: str, frag_src: str, label: str):
    """No-op shim — QRhi shaders are pre-compiled to .qsb at build time."""
    return None
