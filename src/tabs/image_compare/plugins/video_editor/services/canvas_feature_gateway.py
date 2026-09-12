from __future__ import annotations

from typing import Any

from tabs._shared.canvas import execute_canvas_feature_alias as _shared_alias


def execute_canvas_feature_alias(alias: str, *args: Any, default=None, **kwargs: Any):
    # Tab→tab direct import — no TabRegistry hop.
    # Host→tab path stays via plugins.settings.canvas_feature_gateway
    # (TabRegistry.create_service). See tabs._shared.canvas.
    return _shared_alias(alias, *args, default=default, **kwargs)
