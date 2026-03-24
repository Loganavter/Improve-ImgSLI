from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

class RatingGestureTransaction:

    pass

try:
    import sys
    from pathlib import Path

    current_file = Path(__file__).resolve()

    src_path = current_file.parent.parent.parent
    gesture_resolver_path = src_path / "ui" / "gesture_resolver.py"

    if gesture_resolver_path.exists():

        src_path_str = str(src_path)
        if src_path_str not in sys.path:
            sys.path.insert(0, src_path_str)

        try:

            import importlib

            ui_gesture_resolver = importlib.import_module("ui.gesture_resolver")
            RatingGestureTransaction = getattr(
                ui_gesture_resolver,
                "RatingGestureTransaction",
                RatingGestureTransaction,
            )
        except (ImportError, AttributeError):

            try:
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "ui.gesture_resolver", gesture_resolver_path
                )
                if spec and spec.loader:
                    gesture_resolver_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(gesture_resolver_module)
                    RatingGestureTransaction = getattr(
                        gesture_resolver_module,
                        "RatingGestureTransaction",
                        RatingGestureTransaction,
                    )
            except Exception:
                pass
except Exception:
    pass
