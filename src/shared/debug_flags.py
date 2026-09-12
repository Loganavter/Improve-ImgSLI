"""Topical helper for ``IMGSLI_*_DEBUG`` env-gated tracing.

Single source for the ``_env_flag`` pattern that was duplicated across
5 live sites (render_debug, first_frame_debug, main_window/runtime,
flyout_debug, rhi_backend). No grab-bag ``utils`` — this module only
holds env-flag predicates.

Two predicates:
* ``env_flag`` — permissive: any non-empty value except ``0/false/no/off`` is true
  (``IMGSLI_RESIZE_DEBUG=1`` or ``=yes`` etc). Used by render/flyout/resize/first-frame.
* ``env_flag_strict`` — strict: only ``1/true/yes/on`` is true (historical
  ``rhi_backend`` semantics for ``ALLOW_LSFGVK``). Keep behavior for that one call site.
"""

from __future__ import annotations

import os


def env_flag(name: str) -> bool:
    """Permissive flag: true unless value is empty/0/false/no/off."""
    return os.environ.get(name, "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def env_flag_strict(name: str) -> bool:
    """Strict flag: true only for 1/true/yes/on."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


# Back-compat alias for internal callers that imported ``_env_flag``.
_env_flag = env_flag
