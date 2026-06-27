from __future__ import annotations

from dataclasses import dataclass

from tabs.image_compare.presenters.image_canvas.coordinators import (
    CanvasBackgroundCoordinator,
    CanvasLifecycleCoordinator,
    CanvasOverlayCoordinator,
    CanvasViewCoordinator,
)


@dataclass(slots=True)
class ImageCanvasComponents:
    lifecycle: CanvasLifecycleCoordinator
    view: CanvasViewCoordinator
    background: CanvasBackgroundCoordinator
    overlay: CanvasOverlayCoordinator


def build_image_canvas_components(presenter) -> ImageCanvasComponents:
    return ImageCanvasComponents(
        lifecycle=CanvasLifecycleCoordinator(presenter),
        view=CanvasViewCoordinator(presenter),
        background=CanvasBackgroundCoordinator(presenter),
        overlay=CanvasOverlayCoordinator(presenter),
    )


def connect_image_canvas_runtime(presenter) -> None:
    dispatcher = (
        presenter.store.get_dispatcher()
        if hasattr(presenter.store, "get_dispatcher")
        else None
    )
    if dispatcher:
        dispatcher.subscribe(presenter._on_action)
