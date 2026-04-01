from __future__ import annotations

from dataclasses import dataclass

from ui.presenters.image_canvas.coordinators import (
    CanvasBackgroundCoordinator,
    CanvasLifecycleCoordinator,
    CanvasMagnifierCoordinator,
    CanvasResultCoordinator,
    CanvasViewCoordinator,
)

@dataclass(slots=True)
class ImageCanvasComponents:
    lifecycle: CanvasLifecycleCoordinator
    view: CanvasViewCoordinator
    background: CanvasBackgroundCoordinator
    magnifier: CanvasMagnifierCoordinator
    results: CanvasResultCoordinator

def build_image_canvas_components(presenter) -> ImageCanvasComponents:
    return ImageCanvasComponents(
        lifecycle=CanvasLifecycleCoordinator(presenter),
        view=CanvasViewCoordinator(presenter),
        background=CanvasBackgroundCoordinator(presenter),
        magnifier=CanvasMagnifierCoordinator(presenter),
        results=CanvasResultCoordinator(presenter),
    )

def connect_image_canvas_runtime(presenter) -> None:
    presenter._worker_finished_signal.connect(presenter.results.on_worker_finished)
    presenter._worker_error_signal.connect(presenter.results.on_worker_error)

    dispatcher = (
        presenter.store.get_dispatcher()
        if hasattr(presenter.store, "get_dispatcher")
        else None
    )
    if dispatcher:
        dispatcher.subscribe(presenter._on_action)
