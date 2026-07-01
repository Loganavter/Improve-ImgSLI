"""Image-compare pair canvas must not be selected through the shared facade."""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, read, rel


def test_pair_canvas_modules_live_under_image_compare_tab():
    shared_canvas = SRC / "ui" / "widgets" / "canvas"
    forbidden = (
        "__init__.py",
        "contracts.py",
        "feature_overlay_gpu.py",
        "helpers.py",
        "interaction.py",
        "render_config.py",
        "render_context.py",
        "rhi_feature_common.py",
        "rhi_renderer.py",
        "scene.py",
        "state.py",
        "style_tokens.py",
        "widget.py",
        "shader_sources/__init__.py",
        "shader_sources/base.py",
        "shader_sources/common.py",
        "texture_parts/base_images.py",
        "texture_parts/common.py",
        "texture_parts/layers.py",
        "texture_parts/upload_queue.py",
        "shaders/base.frag",
        "shaders/base.frag.qsb",
        "shaders/base.vert",
        "shaders/base.vert.qsb",
        "shaders/step1.frag",
        "shaders/step1.frag.qsb",
        "shaders/step1.vert",
        "shaders/step1.vert.qsb",
    )
    offenders = []
    for relative in forbidden:
        path = shared_canvas / relative
        if relative == "__init__.py":
            text = read(path)
            if "CanvasWidget" in text or "GLCanvas" in text:
                offenders.append(f"{rel(path)} exports pair canvas widget aliases")
            continue
        if path.exists():
            offenders.append(rel(path))
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_no_public_pair_canvas_imports_from_shared_facade():
    offenders: list[str] = []
    for path in iter_py(SRC):
        if path == SRC / "ui" / "widgets" / "canvas" / "__init__.py":
            continue
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "ui.widgets.canvas":
                continue
            names = {alias.name for alias in node.names}
            leaked = names & {"CanvasWidget", "GLCanvas"}
            if leaked:
                offenders.append(f"{rel(path)}:{node.lineno} imports {sorted(leaked)}")
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_main_window_ui_does_not_construct_image_compare_primitives():
    path = SRC / "ui" / "main_window" / "ui.py"
    text = read(path)
    forbidden = (
        "from sli_ui_toolkit.widgets import",
        "ColorSettingsButton",
        "create_image_compare_canvas_widget",
        "_create_selection_controls",
        "_create_view_controls",
        "_create_video_controls",
        "_create_slider_controls",
        "_create_text_and_status_widgets",
        "_configure_image_label",
        "_init_warning_label",
    )
    hits = [token for token in forbidden if token in text]
    assert not hits, (
        "ui.main_window.ui must leave image_compare primitive construction to "
        f"the tab factory: {hits}"
    )


def test_magnifier_feature_widgets_live_under_image_compare_tab():
    offenders = []
    for relative in (
        "managers/transient_ui_parts/magnifier.py",
        "managers/transient_ui_parts/magnifier_instances.py",
        "widgets/magnifier_color_controls.py",
        "widgets/magnifier_visibility_flyout.py",
    ):
        path = SRC / "ui" / relative
        if path.exists():
            offenders.append(rel(path))
    assert not offenders, (
        "magnifier feature UI belongs under tabs.image_compare.ui: "
        + ", ".join(offenders)
    )


def test_image_compare_toolbar_presenter_lives_under_tab():
    offenders = []
    for relative in (
        "presenters/toolbar_presenter.py",
        "presenters/toolbar/__init__.py",
        "presenters/toolbar/connections.py",
        "presenters/toolbar/orientation.py",
        "presenters/toolbar/state.py",
    ):
        path = SRC / "ui" / relative
        if path.exists():
            offenders.append(rel(path))
    assert not offenders, (
        "image_compare toolbar presenter belongs under tabs.image_compare.presenters: "
        + ", ".join(offenders)
    )


def test_shared_render_arch_stays_generic():
    path = SRC / "ui" / "canvas_presentation" / "render_arch.py"
    text = read(path)
    forbidden = (
        "filename",
        "capture",
        "guides",
        "divider",
        "magnifier",
        "diff",
        "channel",
        "split_position",
        "letterbox",
        "BaseImagePrimitive",
        "SceneFrame",
        "RenderList",
        "ResolvedCanvasStyle",
    )
    hits = [token for token in forbidden if token in text]
    assert not hits, f"shared render_arch.py must stay generic: {hits}"
