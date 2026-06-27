"""Tab-local helpers for resolving the image-canvas feature presenter.

Used by image_compare canvas features (magnifier keyboard movement etc.) to
schedule canvas redraws without the platform event layer having to know about
the ``"image_canvas"`` feature key.
"""

from __future__ import annotations


def get_image_canvas_presenter(presenter):
    if presenter is None:
        return None
    if hasattr(presenter, "get_feature"):
        return presenter.get_feature("image_canvas")
    return None


def schedule_image_canvas_update(presenter) -> None:
    image_canvas_presenter = get_image_canvas_presenter(presenter)
    if image_canvas_presenter is not None:
        image_canvas_presenter.schedule_update()
