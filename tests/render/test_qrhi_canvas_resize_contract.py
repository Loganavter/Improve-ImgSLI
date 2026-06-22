"""QRhi widget resize events must refresh canvas coordinate geometry."""

import ast
from pathlib import Path


WIDGET = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "ui"
    / "widgets"
    / "gl_canvas"
    / "widget.py"
)


def test_gl_canvas_resize_event_delegates_to_resize_geometry_pipeline():
    tree = ast.parse(WIDGET.read_text(encoding="utf-8"))
    resize_method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "resizeEvent"
    )

    calls = [
        node
        for node in ast.walk(resize_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resize_gl"
    ]

    assert len(calls) == 1
