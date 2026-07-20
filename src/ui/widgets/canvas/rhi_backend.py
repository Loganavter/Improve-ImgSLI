from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass

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


# User-facing ticket URL when every probed API is too old / missing.
RHI_SUPPORT_ISSUES_URL = "https://github.com/Loganavter/Improve-ImgSLI/issues/new"
# Last public release before hybrid CPU–GPU canvas (v8.1.0). CPU paint path.
RHI_LEGACY_CPU_RELEASE = "v7.9.0"
RHI_LEGACY_CPU_RELEASE_URL = (
    "https://github.com/Loganavter/Improve-ImgSLI/releases/tag/v7.9.0"
)

# Soft: requested API failed, another works. Hard: nothing usable left.
RHI_NOTICE_FALLBACK = "fallback"
RHI_NOTICE_UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class RhiFallbackNotice:
    """Pending user-visible notice after a startup backend fallback."""

    requested: str
    effective: str
    reason: str
    kind: str = RHI_NOTICE_FALLBACK


_pending_fallback_notice: RhiFallbackNotice | None = None


def record_rhi_fallback_notice(
    requested: str,
    effective: str,
    reason: str,
    *,
    kind: str | None = None,
) -> RhiFallbackNotice:
    """Remember a fallback so the UI can show an error after the main window."""
    global _pending_fallback_notice
    notice_kind = (kind or "").strip().lower()
    if notice_kind not in (RHI_NOTICE_FALLBACK, RHI_NOTICE_UNSUPPORTED):
        notice_kind = (
            RHI_NOTICE_UNSUPPORTED
            if (effective or "").strip().lower() == "null"
            else RHI_NOTICE_FALLBACK
        )
    notice = RhiFallbackNotice(
        requested=(requested or "default").strip().lower(),
        effective=(effective or "default").strip().lower(),
        reason=str(reason or ""),
        kind=notice_kind,
    )
    _pending_fallback_notice = notice
    return notice


def take_rhi_fallback_notice() -> RhiFallbackNotice | None:
    """Consume the pending fallback notice (once)."""
    global _pending_fallback_notice
    notice = _pending_fallback_notice
    _pending_fallback_notice = None
    return notice


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


def probe_opengl_usable_for_shaders() -> bool | None:
    """Return whether OpenGL can run our baked ``.qsb`` shaders.

    Baked targets are GLSL 330 / 300 es (+ HLSL/MSL). A Windows OpenGL 2.x
    context only offers GLSL 120/130 → ``No GLSL shader code found`` and
    ``Failed to create canvas graphics pipeline``.

    Returns:
        ``True`` / ``False`` when a probe ran, or ``None`` when OpenGL
        symbols are missing from this PySide build.
    """
    try:
        from PySide6.QtGui import QOpenGLContext, QSurfaceFormat
    except ImportError:
        return None

    try:
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        ctx = QOpenGLContext()
        ctx.setFormat(fmt)
        if not ctx.create():
            return False
        actual = ctx.format()
        major = int(actual.majorVersion())
        minor = int(actual.minorVersion())
        renderable = actual.renderableType()
        if (
            renderable == QSurfaceFormat.RenderableType.OpenGLES
            and major >= 3
        ):
            return True
        if major > 3 or (major == 3 and minor >= 3):
            return True
        logger.warning(
            "OpenGL probe got %s.%s (renderable=%s); need 3.3+ / GLES 3.0+ "
            "for baked QRhi shaders",
            major,
            minor,
            renderable,
        )
        return False
    except Exception as exc:
        logger.warning("OpenGL probe raised: %s", exc)
        return False


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


def _probe_qrhi_with_init_params(impl: QRhi.Implementation, params_name: str) -> bool | None:
    """Try ``QRhi.probe`` when PySide exposes the matching init-params type.

    Returns ``None`` when the type is not bound (common for D3D/Metal on
    Linux PySide builds); ``True``/``False`` when probe ran.
    """
    try:
        from PySide6 import QtGui
    except ImportError:
        return None
    params_cls = getattr(QtGui, params_name, None)
    if params_cls is None:
        return None
    try:
        return bool(QRhi.probe(impl, params_cls()))
    except Exception as exc:
        logger.warning("QRhi.probe(%s) failed: %s", impl, exc)
        return False


def _windows_d3d11_create_device_ok() -> bool:
    """Create a D3D11 device at feature level 11_0 (matches QRhi + HLSL 5.0)."""
    import ctypes

    try:
        d3d11 = ctypes.WinDLL("d3d11.dll")
    except OSError as exc:
        logger.warning("d3d11.dll unavailable: %s", exc)
        return False

    # D3D_FEATURE_LEVEL_11_0 … 9_1 — first matching level wins.
    levels = (ctypes.c_int * 1)(0xB000)  # D3D_FEATURE_LEVEL_11_0
    device = ctypes.c_void_p()
    context = ctypes.c_void_p()
    out_level = ctypes.c_int()
    # HRESULT D3D11CreateDevice(
    #   adapter, driver_type, software, flags, feature_levels, num,
    #   sdk_version, device, feature_level, immediate_context)
    create = d3d11.D3D11CreateDevice
    create.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    create.restype = ctypes.c_long
    hr = int(
        create(
            None,
            1,  # D3D_DRIVER_TYPE_HARDWARE
            None,
            0,
            levels,
            1,
            7,  # D3D11_SDK_VERSION
            ctypes.byref(device),
            ctypes.byref(out_level),
            ctypes.byref(context),
        )
    )
    if hr < 0 or not device:
        logger.warning(
            "D3D11CreateDevice failed hr=0x%08x (need Feature Level 11_0)",
            hr & 0xFFFFFFFF,
        )
        return False
    # Probe-only device: leave COM refs for process exit (one-shot startup).
    return True


def probe_d3d11_available() -> bool | None:
    """Return whether Direct3D 11 (Feature Level 11_0+) can start.

    Non-Windows → ``False``. Prefer ``QRhi.probe`` when PySide binds
    ``QRhiD3D11InitParams``; otherwise ``D3D11CreateDevice``.
    """
    if not sys.platform.startswith("win"):
        return False
    probed = _probe_qrhi_with_init_params(
        QRhi.Implementation.D3D11, "QRhiD3D11InitParams"
    )
    if probed is not None:
        return probed
    try:
        return _windows_d3d11_create_device_ok()
    except Exception as exc:
        logger.warning("D3D11 probe raised: %s", exc)
        return False


def probe_d3d12_available() -> bool | None:
    """Return whether Direct3D 12 looks usable on this host.

    Non-Windows → ``False``. Prefer ``QRhi.probe``; otherwise require
    ``d3d12.dll`` load (QRhi still does the real device create at runtime).
    """
    if not sys.platform.startswith("win"):
        return False
    probed = _probe_qrhi_with_init_params(
        QRhi.Implementation.D3D12, "QRhiD3D12InitParams"
    )
    if probed is not None:
        return probed
    try:
        import ctypes

        ctypes.WinDLL("d3d12.dll")
        return True
    except OSError as exc:
        logger.warning("d3d12.dll unavailable: %s", exc)
        return False
    except Exception as exc:
        logger.warning("D3D12 probe raised: %s", exc)
        return False


def probe_metal_available() -> bool | None:
    """Return whether Metal can start (macOS only).

    Prefer ``QRhi.probe`` when bound; otherwise assume available on Darwin
    (PySide often omits Metal init params outside Apple CI).
    """
    if sys.platform != "darwin":
        return False
    probed = _probe_qrhi_with_init_params(
        QRhi.Implementation.Metal, "QRhiMetalInitParams"
    )
    if probed is not None:
        return probed
    return None


def _probe_named_backend(name: str) -> bool | None:
    """Capability probe for one API name (``True``/``False``/``None`` = skip)."""
    if name == "opengl":
        return probe_opengl_usable_for_shaders()
    if name == "vulkan":
        return probe_vulkan_available()
    if name == "d3d11":
        return probe_d3d11_available()
    if name == "d3d12":
        return probe_d3d12_available()
    if name == "metal":
        return probe_metal_available()
    if name in ("null", "default"):
        return None
    return None


def _platform_alt_backends() -> tuple[str, ...]:
    """Ordered alternatives after the requested API is rejected."""
    if sys.platform.startswith("win"):
        return ("d3d11", "opengl")
    if sys.platform == "darwin":
        return ("metal", "opengl")
    return ("opengl",)


def platform_rhi_requirement_keys() -> tuple[str, ...]:
    """APIs a user on this OS can realistically try to update / enable.

    Used for unsupported-GPU copy so Windows users are not told to install
    Metal, and Linux users are not pointed at Direct3D.
    """
    if sys.platform.startswith("win"):
        return ("d3d11", "opengl", "vulkan")
    if sys.platform == "darwin":
        return ("metal", "opengl")
    return ("opengl", "vulkan")


def platform_rhi_requirements_summary() -> str:
    """Short English summary for logs / technical fallback reasons."""
    labels = {
        "d3d11": "D3D11 FL 11_0+",
        "opengl": "OpenGL 3.3+",
        "vulkan": "Vulkan",
        "metal": "Metal",
        "d3d12": "D3D12",
    }
    keys = platform_rhi_requirement_keys()
    return " / ".join(labels.get(k, k) for k in keys)


def _resolution_candidates(requested: str) -> list[str]:
    """Ordered backends to try for ``requested`` (first = preferred)."""
    name = (requested or "default").strip().lower()
    if name not in _API_BY_NAME:
        name = "default"

    if name == "default":
        if sys.platform.startswith("win"):
            return ["d3d11", "opengl"]
        return ["default"]

    out: list[str] = [name]
    for alt in _platform_alt_backends():
        if alt not in out:
            out.append(alt)
    return out


def _reject_reason(name: str, probe: bool | None) -> str:
    if name == "opengl":
        return (
            "OpenGL context too old for baked QRhi shaders "
            "(need GLSL 330+ / GL 3.3)"
        )
    if name == "d3d11":
        return "Direct3D 11 unavailable (need Feature Level 11_0+)"
    if name == "d3d12":
        return "Direct3D 12 unavailable"
    if name == "metal":
        return "Metal unavailable"
    if name == "vulkan":
        return f"Vulkan unavailable (probe={probe!r})"
    return f"{name} unavailable"


def resolve_rhi_backend_with_fallback(requested: str) -> tuple[str, str | None]:
    """Return ``(effective_backend, fallback_reason_or_None)``.

    Must run after ``QApplication`` exists so Vulkan/QRhi probes can talk to
    the platform. Does not mutate env or QSettings — callers decide persistence.

    Explicit backends are probed where we have a check (Vulkan, OpenGL 3.3+,
    D3D11 FL 11_0, D3D12 DLL, Metal). Auto (``default``) on Linux/macOS stays
    with Qt. On Windows, Auto resolves to explicit ``d3d11`` so Qt cannot land
    on a legacy OpenGL context that lacks GLSL 330 (our ``.qsb`` bake set only
    has 330 / 300 es / HLSL / MSL).

    If every candidate probes ``False`` (e.g. Windows with only D3D9 / ancient
    OpenGL), returns ``null`` so the UI can show an unsupported-GPU dialog
    instead of silently picking a dead API.
    """
    global _vulkan_rejected_for_process

    name = (requested or "default").strip().lower()
    if name not in _API_BY_NAME:
        name = "default"

    # Linux/macOS Auto: leave the choice to Qt (no speculative rewrite).
    if name == "default" and not sys.platform.startswith("win"):
        return "default", None

    candidates = _resolution_candidates(name)
    rejected: list[str] = []
    primary = candidates[0]

    for candidate in candidates:
        probe = _probe_named_backend(candidate)

        if candidate == "vulkan":
            if probe is True:
                return "vulkan", None
            # Confirmed failure, or Windows with no probe API (cannot risk
            # setApi(Vulkan) when QVulkanDefaultInstance would hard-fail).
            if probe is False or sys.platform.startswith("win"):
                _vulkan_rejected_for_process = True
                rejected.append(_reject_reason(candidate, probe))
                continue
            # Inconclusive on Linux/macOS: keep Vulkan; renderFailed can recover.
            return "vulkan", None

        if probe is False:
            rejected.append(_reject_reason(candidate, probe))
            continue

        # Usable or unprobed — accept.
        if candidate == primary and not rejected:
            return candidate, None
        lead = rejected[0] if rejected else f"{primary} unavailable"
        reason = f"{lead}; falling back to {candidate}"
        return candidate, reason

    # Nothing left (classic “only D3D9 / GL 2.x” Windows box).
    detail = "; ".join(rejected) if rejected else "no candidates"
    reason = (
        "No usable QRhi backend on this system "
        f"({detail}). Need {platform_rhi_requirements_summary()}."
    )
    return "null", reason



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
        if (
            name in ("vulkan", "opengl", "d3d11", "d3d12", "metal", "default")
            and fallback != name
        ):
            persist_rhi_backend_setting(fallback)

    widget.renderFailed.connect(_on_render_failed)
    install = getattr(widget, "installEventFilter", None)
    if callable(install):
        from ui.widgets.canvas.rhi_focus import install_qrhi_focus_parking

        install_qrhi_focus_parking(widget)


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
