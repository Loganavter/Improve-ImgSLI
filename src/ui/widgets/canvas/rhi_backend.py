from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager

from PySide6.QtGui import QRhi
from PySide6.QtWidgets import QRhiWidget

logger = logging.getLogger("ImproveImgSLI.rhi")

FALLBACK_MAX_TEXTURE_SIZE = 4096

RHI_BACKEND_ENV = "IMPROVE_IMGSLI_RHI_BACKEND"
ALLOW_LSFGVK_ENV = "IMPROVE_IMGSLI_ALLOW_LSFGVK"
DISABLE_LSFGVK_ENV = "DISABLE_LSFGVK"
RHI_SETTINGS_ORG = "improve-imgsli"
RHI_SETTINGS_APP = "improve-imgsli"
RHI_SETTINGS_KEY = "rhi_backend"

_API_BY_NAME = {
    "default": None,
    "opengl": QRhiWidget.Api.OpenGL,
    "vulkan": QRhiWidget.Api.Vulkan,
    "d3d11": QRhiWidget.Api.Direct3D11,
    "d3d12": QRhiWidget.Api.Direct3D12,
    "metal": QRhiWidget.Api.Metal,
    "null": QRhiWidget.Api.Null,
}

# Set when resolve rejects Vulkan for this process — widgets must not setApi(Vulkan).
_vulkan_rejected_for_process = False


def supported_rhi_backend_names() -> tuple[str, ...]:
    return tuple(_API_BY_NAME)


def requested_rhi_backend_name() -> str:
    value = os.environ.get(RHI_BACKEND_ENV, "default").strip().lower()
    return value if value in _API_BY_NAME else "default"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def platform_fallback_rhi_backend() -> str:
    """Conservative API when the preferred backend cannot start."""
    if sys.platform.startswith("win"):
        return "d3d11"
    if sys.platform == "darwin":
        return "metal"
    return "opengl"


def configure_vulkan_layer_environment(backend_name: str) -> bool:
    """Disable known-bad implicit Vulkan layers for the app's QRhi widgets."""
    if (
        backend_name == "vulkan"
        and sys.platform.startswith("linux")
        and not _env_flag(ALLOW_LSFGVK_ENV)
    ):
        os.environ[DISABLE_LSFGVK_ENV] = "1"
        return True
    return False


def configure_rhi_process_environment(backend_name: str) -> None:
    """Apply the process-wide backend selection before widgets call setApi."""
    os.environ[RHI_BACKEND_ENV] = backend_name


@contextmanager
def _quiet_qt_vulkan_messages():
    """Swallow Qt's noisy Vulkan create failures during a deliberate probe."""
    try:
        from PySide6.QtCore import qInstallMessageHandler
    except Exception:
        yield
        return

    def _handler(mode, context, message):  # noqa: ANN001
        text = str(message)
        if "Vulkan" in text or "vulkan" in text:
            return
        # Re-emit non-Vulkan messages through the previous handler if any.
        try:
            sys.stderr.write(text + "\n")
        except Exception:
            pass

    previous = qInstallMessageHandler(_handler)
    try:
        yield
    finally:
        try:
            qInstallMessageHandler(previous)
        except Exception:
            qInstallMessageHandler(None)


def probe_vulkan_available() -> bool | None:
    """Probe whether Qt can create a Vulkan instance for QRhi.

    Returns:
        ``True`` / ``False`` when a probe ran, or ``None`` when this PySide
        build has no Vulkan probe symbols.
    """
    try:
        from PySide6.QtGui import QRhiVulkanInitParams  # type: ignore[attr-defined]
    except ImportError:
        QRhiVulkanInitParams = None  # type: ignore[misc, assignment]

    if QRhiVulkanInitParams is not None:
        with _quiet_qt_vulkan_messages():
            try:
                ok = bool(
                    QRhi.probe(QRhi.Implementation.Vulkan, QRhiVulkanInitParams())
                )
            except Exception as exc:
                logger.warning("QRhi.probe(Vulkan) failed: %s", exc)
                return False
        return ok

    try:
        from PySide6.QtGui import QVulkanInstance  # type: ignore[attr-defined]
    except ImportError:
        return None

    with _quiet_qt_vulkan_messages():
        try:
            instance = QVulkanInstance()
            try:
                from PySide6.QtGui import QRhiVulkanInitParams as _Params  # type: ignore

                instance.setExtensions(_Params.preferredInstanceExtensions())
            except Exception:
                pass
            if instance.create():
                return True
            error = getattr(instance, "errorCode", lambda: None)()
            logger.warning("QVulkanInstance.create failed (error=%s)", error)
            return False
        except Exception as exc:
            logger.warning("Vulkan probe raised: %s", exc)
            return False


def resolve_rhi_backend_with_fallback(requested: str) -> tuple[str, str | None]:
    """Return ``(effective_backend, fallback_reason_or_None)``.

    Must run after ``QApplication`` exists so Vulkan/QRhi probes can talk to
    the platform. Does not mutate env or QSettings — callers decide persistence.

    Explicit ``vulkan`` requires a successful probe. A missing probe API
    (``None``) is treated as failure so widgets never ``setApi(Vulkan)`` on a
    broken runtime (Windows ``-9`` / missing ICD).
    """
    global _vulkan_rejected_for_process

    name = (requested or "default").strip().lower()
    if name not in _API_BY_NAME:
        name = "default"

    should_probe = name == "vulkan" or (
        name == "default" and sys.platform.startswith("linux")
    )
    if not should_probe:
        return name, None

    available = probe_vulkan_available()
    # Explicit Vulkan: only keep it when the probe positively succeeded.
    if name == "vulkan" and available is not True:
        _vulkan_rejected_for_process = True
        fallback = platform_fallback_rhi_backend()
        reason = (
            f"Vulkan unavailable (probe={available!r}); falling back to {fallback}"
        )
        return fallback, reason

    # Linux Auto: if Vulkan is known-bad, force OpenGL so Qt does not pick it.
    if name == "default" and available is False:
        _vulkan_rejected_for_process = True
        fallback = platform_fallback_rhi_backend()
        if fallback != name:
            return fallback, f"Vulkan unavailable; falling back to {fallback}"

    return name, None


def persist_rhi_backend_setting(backend_name: str) -> None:
    """Write the backend into QSettings so the next launch skips a broken API."""
    if backend_name not in _API_BY_NAME:
        return
    try:
        from PySide6.QtCore import QSettings

        qs = QSettings(RHI_SETTINGS_ORG, RHI_SETTINGS_APP)
        qs.setValue(RHI_SETTINGS_KEY, backend_name)
        qs.sync()
    except Exception:
        logger.exception("Failed to persist rhi_backend=%s", backend_name)


def configure_rhi_widget(widget: QRhiWidget) -> None:
    name = requested_rhi_backend_name()
    if name == "vulkan" and _vulkan_rejected_for_process:
        name = platform_fallback_rhi_backend()
        configure_rhi_process_environment(name)
        logger.warning(
            "Refusing Vulkan for %s; using %s for this process",
            type(widget).__name__,
            name,
        )
    api = _API_BY_NAME[name]
    if api is not None:
        widget.setApi(api)
    fallback = platform_fallback_rhi_backend()

    def _on_render_failed() -> None:
        actual = getattr(widget.api(), "name", "platform-default")
        logger.error(
            "%s renderFailed requested=%s actual=%s — try Settings → "
            "Render Backend → %s (or --rhi-backend %s) and restart",
            type(widget).__name__,
            name,
            actual,
            fallback,
            fallback,
        )
        if name in ("vulkan", "default") and fallback != name:
            persist_rhi_backend_setting(fallback)

    widget.renderFailed.connect(_on_render_failed)


def log_initialized_rhi_widget(widget: QRhiWidget) -> None:
    pass


def query_max_texture_size(rhi: QRhi | None) -> int:
    """Backend-reported max 2D texture dimension, source of truth for
    tile-size-vs-limit decisions (docs/dev/TILED_RENDERING_DESIGN.md Phase 0).
    Falls back to a conservative constant if ``rhi`` is unavailable or the
    backend reports something unusable."""
    if rhi is None:
        return FALLBACK_MAX_TEXTURE_SIZE
    try:
        limit = int(rhi.resourceLimit(QRhi.ResourceLimit.TextureSizeMax))
    except (RuntimeError, ValueError, TypeError):
        return FALLBACK_MAX_TEXTURE_SIZE
    return limit if limit > 0 else FALLBACK_MAX_TEXTURE_SIZE
