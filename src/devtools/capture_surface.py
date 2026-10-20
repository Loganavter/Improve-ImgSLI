"""Headless screenshots of real app surfaces — Help figures + visual checks.

Devtool only. Nothing here is imported by the application runtime; it drives
the production widgets from a private X display to produce PNGs that answer
"what does this dialog / grid / overlay actually look like?" (see
``docs/dev/SCREENSHOTS.md``).

Audit-Meta: pattern=devtool-pipeline reason="one capture adapter: surface catalogue, window lifecycle + size pin, bootstrap and CLI share one grab contract; splitting the session from the surfaces forks how a frame is produced"

Why not ``QT_QPA_PLATFORM=offscreen``: offscreen Qt paints *black* via
``QWidget.grab()`` for anything that goes through the toolkit painter
pipeline, so the output is useless. A private ``Xvfb`` display gives a real
(software) OpenGL-less X server that ``grab()`` can render into, without
disturbing the user's running app on ``:0``. ``DISPLAY`` is therefore taken
from the environment and never defaulted to ``:0``.

The static surface set (dialog, gallery, session picker, onboarding) grabs
fine. The live QRhi/GL canvas in Multi Compare does **not**: ``grab()``
returns blank or mis-positioned bands because the GL swapchain is not part
of the widget raster. See ``docs/dev/SCREENSHOTS.md`` for the workaround.

Usage::

    Xvfb :91 -screen 0 1400x1000x24 &
    DISPLAY=:91 LIBGL_ALWAYS_SOFTWARE=1 \\
        python src/devtools/capture_surface.py gallery-populated --out /tmp/shots

    python src/devtools/capture_surface.py --list   # no display required
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

#: Repo root (``<repo>/src/devtools/capture_surface.py`` -> ``<repo>``).
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

#: i18n roots registered at bootstrap. Without these, widget strings show the
#: raw key (``help.topic.foo``) instead of translated text. Mirrors the app's
#: own bootstrap registration; validated against the throwaway capture
#: harness that produced the shipped Help figures.
I18N_ROOTS = (
    "src/resources/i18n",
    "src/ui/resources/i18n",
    "src/plugins/export/resources/i18n",
    "src/plugins/help/resources/i18n",
    "src/plugins/image_properties/resources/i18n",
    "src/plugins/onboarding/resources/i18n",
    "src/plugins/settings/resources/i18n",
    "src/tabs/image_compare/resources/i18n",
    "src/tabs/image_compare/canvas/features/magnifier/resources/i18n",
    "src/tabs/image_compare/plugins/video_editor/resources/i18n",
    "src/tabs/image_gallery/resources/i18n",
    "src/tabs/multi_compare/resources/i18n",
    "src/tabs/session_picker/resources/i18n",
)

#: Default output dir: scratch space, never inside the repo (no PNGs committed).
DEFAULT_OUT = "/tmp/opencode/capture-surface"

XVFB_HINT = (
    "capture_surface needs an X display. The offscreen Qt platform renders\n"
    "black grabs, and the user's live app on :0 must not be disturbed. Start a\n"
    "private Xvfb and point DISPLAY at it, e.g.:\n"
    "  Xvfb :91 -screen 0 1400x1000x24 &\n"
    "  DISPLAY=:91 LIBGL_ALWAYS_SOFTWARE=1 \\\n"
    "      python src/devtools/capture_surface.py settings --out /tmp/shots"
)

#: The QRhi/GL canvas of Multi Compare is not rasterized into ``grab()``, and
#: on a real X display QRhi init hard-exits the process. Isolated surfaces run
#: in an offscreen child so the tool survives; the canvas area stays blank.
LIMITATION = (
    "note: the live QRhi/GL canvas is not capturable headlessly — on an X "
    "display QRhi init aborts the process, and offscreen renders the canvas "
    "blank. Captured chrome-only in an isolated offscreen child; for a real "
    "canvas shot, capture the running app manually."
)

#: The SettingsDialog kwargs the sync suite uses (``**SETTINGS_KWARGS``).
SETTINGS_KWARGS = dict(
    current_language="en",
    current_theme="dark",
    current_max_length=30,
    min_limit=1,
    max_limit=200,
    debug_mode_enabled=False,
    system_notifications_enabled=True,
    active_tab="image_compare",
)


@dataclass(frozen=True)
class Surface:
    """One capturable widget: how to build it and what shot it yields.

    ``isolated`` marks a surface whose widget can hard-exit the process
    (QRhi/GL init failure). It is built in a child process under the offscreen
    platform so a crash cannot take the tool down — see ``_run_isolated``.
    """

    name: str
    description: str
    build: Callable[["CaptureSession"], None]
    isolated: bool = False


SURFACES: dict[str, Surface] = {}


def _surface(name: str, description: str, *, isolated: bool = False):
    def deco(fn: Callable[["CaptureSession"], None]) -> Callable[["CaptureSession"], None]:
        SURFACES[name] = Surface(name, description, fn, isolated)
        return fn

    return deco


class CaptureSession:
    """Per-run context: the QApplication, output dir, and the grab helper."""

    #: How long the re-applied size pin gets to settle before the grab (ms).
    #: A show path can shrink the window after the first pump (the onboarding
    #: overlay does); the second resize needs one more event-loop turn.
    PIN_SETTLE_MS = 200

    def __init__(
        self,
        app,
        out_dir: Path,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self.app = app
        self.out_dir = out_dir
        self.width = width
        self.height = height
        #: Frame requested by the last grab (CLI override or surface default).
        self.last_pin: tuple[int, int] | None = None
        #: Frame actually grabbed (== ``last_pin`` unless the surface refused).
        self.last_size: tuple[int, int] | None = None
        self.samples_dir = out_dir / "_samples"
        self.samples_dir.mkdir(parents=True, exist_ok=True)

    def pump(self, ms: int = 900) -> None:
        """Spin the event loop ``ms`` milliseconds, then drain pending events.

        Widgets size and style themselves across posted events (show/layout/
        theme polish); grabbing without pumping captures a half-laid-out
        frame. ``QTimer.singleShot`` + a nested ``QEventLoop`` is the smallest
        reliable "let Qt settle" primitive.
        """
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()
        self.app.processEvents()

    def apply_size(self, widget, width: int, height: int, delay: int = 0) -> tuple[int, int]:
        """Size the surface to ``width``x``height``; return what it settled at.

        The pin is applied TWICE on purpose. A ``resize`` before ``show`` is
        only a request: the show path (layout polish, deferred geometry, a
        ``showEvent`` that re-fits the window) can land somewhere else — the
        onboarding overlay returns 648 px for a 684 px request. Re-applying
        the pin once the window is up reaches the pinned frame without
        touching pixels.

        Some shells (CSD dialogs) resize their *content* box and keep a frame
        margin of their own, so ``size()`` lands a constant offset off the
        request. The pin names the frame that gets grabbed, so the measured
        offset is corrected once and the result re-read — the correction is
        kept only if the frame really equals the pin. The extra settle after a
        re-apply is paid only when that re-apply actually changed the frame, so
        a surface that already honoured the pin keeps its original timing
        (capture timing shows through on animated chrome, e.g. a fading
        scrollbar).

        A surface that genuinely refuses (fixed-size layout, minimum/maximum
        clamp) keeps its own frame. Callers must report that as
        pin_unavailable with the returned size — never resample the grab
        to fake the pin.
        """
        pin = (width, height)
        window = widget.window()
        window.resize(width, height)
        window.show()
        self.pump(delay)
        settled = (window.width(), window.height())
        window.resize(width, height)
        if (window.width(), window.height()) != settled:
            # The re-apply really changed the frame (a show path had re-fitted
            # it): let the layout/repaint for the new size finish before the
            # grab. No change => no extra settle, so a surface that already
            # honoured the pin keeps its original capture timing.
            self.app.processEvents()
            self.pump(self.PIN_SETTLE_MS)
        achieved = (window.width(), window.height())
        if achieved != pin:
            offset = (achieved[0] - pin[0], achieved[1] - pin[1])
            corrected = (pin[0] - offset[0], pin[1] - offset[1])
            if corrected[0] > 0 and corrected[1] > 0:
                window.resize(*corrected)
                self.app.processEvents()
                self.pump(self.PIN_SETTLE_MS)
                achieved = (window.width(), window.height())
        return achieved

    def grab(
        self,
        widget,
        filename: str,
        default_w: int,
        default_h: int,
        delay: int = 1200,
    ) -> Path:
        """pin -> show -> pump -> re-pin -> pump -> grab -> save.

        CLI ``--width``/``--height`` override the surface's default size.
        ``last_pin``/``last_size`` keep the requested vs grabbed frame so a
        caller can report an unhonoured pin (the Help-figure generator does).
        """
        w = self.width or default_w
        h = self.height or default_h
        self.last_pin = (w, h)
        windowed = self.apply_size(widget, w, h, delay=delay)
        pixmap = widget.grab()
        dest = self.out_dir / filename
        pixmap.save(str(dest))
        self.last_size = (pixmap.width(), pixmap.height())
        print(f"saved {dest} {pixmap.width()}x{pixmap.height()}")
        if self.last_size != self.last_pin and (self.width or self.height):
            print(
                f"pin not honoured: requested {w}x{h}, window settled at "
                f"{windowed[0]}x{windowed[1]}, grabbed {pixmap.width()}x{pixmap.height()}",
                file=sys.stderr,
            )
        return dest

    def make_samples(self) -> list[Path]:
        """Generate six gradient demo images so populated surfaces aren't empty."""
        from PIL import Image, ImageDraw

        specs = [
            ("sunset", (230, 120, 60), (40, 20, 90)),
            ("forest", (60, 160, 90), (10, 40, 30)),
            ("ocean", (60, 140, 220), (10, 30, 80)),
            ("desert", (230, 200, 120), (120, 80, 40)),
            ("city", (140, 140, 160), (20, 20, 40)),
            ("rose", (220, 120, 160), (80, 20, 60)),
        ]
        out = []
        for name, top, bot in specs:
            path = self.samples_dir / f"{name}.png"
            if not path.exists():
                im = Image.new("RGB", (640, 480))
                draw = ImageDraw.Draw(im)
                for y in range(480):
                    t = y / 479
                    color = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3))
                    draw.line([(0, y), (640, y)], fill=color)
                draw.ellipse([220, 120, 420, 320], fill=(255, 240, 200))
                im.save(path)
            out.append(path)
        return out


# ---------------------------------------------------------------------------
# Surface builders
# ---------------------------------------------------------------------------


@_surface("settings", "Settings dialog — General section.")
def _settings(sess: CaptureSession) -> None:
    from plugins.settings.dialog import SettingsDialog

    dialog = SettingsDialog(**SETTINGS_KWARGS)
    sess.grab(dialog, "settings.png", 1016, 776, delay=900)


@_surface("settings-keyboard", "Settings dialog — Keyboard shortcuts section.")
def _settings_keyboard(sess: CaptureSession) -> None:
    from plugins.settings.dialog import SettingsDialog

    dialog = SettingsDialog(**SETTINGS_KWARGS)
    dialog.select_section("builtin.keyboard")
    sess.grab(dialog, "settings-keyboard.png", 1016, 776, delay=1000)


@_surface("gallery", "Image Gallery — empty (drop-zone) state.")
def _gallery(sess: CaptureSession) -> None:
    from tabs.contract import TabContext
    from tabs.image_gallery.widget import ImageGalleryWidget

    widget = ImageGalleryWidget(None, context=TabContext())
    sess.grab(widget, "gallery.png", 1280, 800, delay=1200)


def _gallery_item(path, index: int, **extra):
    from PySide6.QtGui import QPixmap
    from tabs.image_gallery.models import GalleryItem, ThumbnailStatus

    item = GalleryItem(path=path, mtime_ns=1000 + index)
    item.thumbnail = QPixmap(str(path)).scaled(320, 240)
    item.thumbnail_status = ThumbnailStatus.LOADED
    for key, value in extra.items():
        setattr(item, key, value)
    return item


@_surface("gallery-populated", "Image Gallery — grid populated with demo images.")
def _gallery_populated(sess: CaptureSession) -> None:
    from tabs.contract import TabContext
    from tabs.image_gallery.widget import ImageGalleryWidget

    items = [_gallery_item(p, i, rank=i + 1) for i, p in enumerate(sess.make_samples())]
    widget = ImageGalleryWidget(None, context=TabContext())
    widget.rebuild_grid(items)
    sess.grab(widget, "gallery-populated.png", 1280, 800, delay=1500)


@_surface(
    "multi",
    "Multi Compare — empty slot grid (best effort: canvas area is blank).",
    isolated=True,
)
def _multi(sess: CaptureSession) -> None:
    from tabs.multi_compare.widget import MultiCompareWidget

    widget = MultiCompareWidget()
    _grab_multi(sess, widget, "multi.png")


@_surface(
    "multi-populated",
    "Multi Compare — four demo images loaded (best effort: canvas blank).",
    isolated=True,
)
def _multi_populated(sess: CaptureSession) -> None:
    from tabs.multi_compare.controller import MultiCompareController
    from tabs.multi_compare.widget import MultiCompareWidget

    widget = MultiCompareWidget()
    controller = MultiCompareController(widget, None)
    count = controller.load_images(sess.make_samples()[:4])
    print(f"multi slots loaded: {count}")
    _grab_multi(sess, widget, "multi-populated.png")


def _grab_multi(sess: CaptureSession, widget, filename: str) -> None:
    print(LIMITATION, file=sys.stderr)
    sess.grab(widget, filename, 1200, 760, delay=2500)


class _FakeSessionContext:
    """Minimal TabContext stand-in for SessionPickerWidget (no host window)."""

    def __init__(self, blueprints) -> None:
        self._blueprints = blueprints

    def _tr(self, key: str, default: str | None = None) -> str:
        # Delegate to the real i18n helper so card descriptions resolve to
        # text, not raw keys (the i18n roots are registered at bootstrap).
        try:
            from resources.translations import get_current_language, tr

            result = tr(key, get_current_language() or "en", default=default or "")
            return result if result != key else (default or key)
        except Exception:
            return default or key

    def call_service(self, name: str, *args, **kwargs):
        if name == "list_session_blueprints":
            return tuple(self._blueprints)
        if name == "get_tab_icon":
            return None
        raise RuntimeError(f"unexpected service: {name}")

    def get_active_session(self):
        return None


@_surface("session-picker", "Session Picker — tab-type chooser with demo sessions.")
def _session_picker(sess: CaptureSession) -> None:
    from core.session_blueprints import SessionBlueprint
    from tabs.session_picker.widget import SessionPickerWidget

    context = _FakeSessionContext(
        [
            SessionBlueprint(
                session_type="image_compare", plugin_name="comparison", title="Image Compare"
            ),
            SessionBlueprint(
                session_type="multi_compare", plugin_name="multi_compare", title="Multi Compare"
            ),
            SessionBlueprint(
                session_type="image_gallery", plugin_name="gallery", title="Image Gallery"
            ),
        ]
    )
    widget = SessionPickerWidget(context=context)
    sess.grab(widget, "session-picker.png", 1100, 760, delay=1200)


@_surface("onboarding", "Onboarding overlay — first-run mode picker.")
def _onboarding(sess: CaptureSession) -> None:
    from types import SimpleNamespace

    from plugins.onboarding.overlay import OnboardingOverlay

    store = SimpleNamespace(settings=SimpleNamespace(current_language="en"))
    overlay = OnboardingOverlay(None, store)
    sess.grab(overlay, "onboarding.png", 1000, 720, delay=1500)


# ---------------------------------------------------------------------------
# Bootstrap + CLI
# ---------------------------------------------------------------------------


def _require_display() -> str:
    """Refuse to run without an X display — offscreen grabs render black.

    ``DISPLAY`` is taken from the environment, never defaulted to ``:0`` (the
    user's live app must not be disturbed).
    """
    display = os.environ.get("DISPLAY", "").strip()
    if not display:
        print(XVFB_HINT, file=sys.stderr)
        raise SystemExit(2)
    return display


def _bootstrap_qt(theme: str, lang: str):
    """Create the QApplication and install theme + i18n (both mandatory).

    Without a theme the painter pipeline paints unstyled/black surfaces;
    without ``emit_language_changed`` widget text stays raw i18n keys.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from resources.translations import add_i18n_root, emit_language_changed
    from sli_ui_toolkit.managers import ThemeManager

    for rel in I18N_ROOTS:
        path = REPO_ROOT / rel
        if path.is_dir():
            add_i18n_root(path)

    theme_manager = ThemeManager.get_instance()
    theme_manager.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    try:
        import ui.icon_manager  # noqa: F401  — configures the icon resolver
    except Exception as exc:  # pragma: no cover - best effort
        print(f"[capture_surface] icon_manager not loaded: {exc}", file=sys.stderr)
    theme_manager.set_theme(theme, app, await_ripples=False)
    emit_language_changed(lang)
    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture_surface",
        description="Capture a PNG of a real app surface on a private X display.",
    )
    parser.add_argument("surface", nargs="?", help="surface name (see --list)")
    parser.add_argument("--list", action="store_true", help="list surfaces and exit")
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"output directory (default: {DEFAULT_OUT})",
    )
    parser.add_argument("--width", type=int, default=None, help="override surface width")
    parser.add_argument("--height", type=int, default=None, help="override surface height")
    parser.add_argument("--theme", choices=("dark", "light"), default="dark")
    parser.add_argument("--lang", default="en", help="i18n language code (default: en)")
    parser.add_argument(
        "--in-process",
        action="store_true",
        help=argparse.SUPPRESS,  # internal: child of an isolated surface
    )
    return parser


def _list_surfaces() -> int:
    print("Surfaces:")
    for name in sorted(SURFACES):
        print(f"  {name:<18} {SURFACES[name].description}")
    return 0


def _run_isolated(args) -> int:
    """Build an ``isolated`` surface in an offscreen child process.

    QRhi/GL init can hard-exit the interpreter (uncatchable), which would take
    the tool down. Re-running ourselves with ``--in-process`` under
    ``QT_QPA_PLATFORM=offscreen`` contains the failure and still captures the
    widget chrome.
    """
    import subprocess

    cmd = [sys.executable, str(Path(__file__).resolve()), args.surface, "--in-process"]
    cmd += ["--out", args.out, "--theme", args.theme, "--lang", args.lang]
    if args.width is not None:
        cmd += ["--width", str(args.width)]
    if args.height is not None:
        cmd += ["--height", str(args.height)]

    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    print(LIMITATION, file=sys.stderr)
    proc = subprocess.run(cmd, env=env, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        print(
            f"surface {args.surface!r} exited {proc.returncode} — not capturable "
            "in this environment.",
            file=sys.stderr,
        )
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        return _list_surfaces()
    if not args.surface:
        parser.error("a surface is required (or use --list)")

    surface = SURFACES.get(args.surface)
    if surface is None:
        print(f"unknown surface: {args.surface!r}", file=sys.stderr)
        print("known surfaces: " + ", ".join(sorted(SURFACES)), file=sys.stderr)
        return 2

    _require_display()
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

    if surface.isolated and not args.in_process:
        return _run_isolated(args)

    app = _bootstrap_qt(args.theme, args.lang)
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    session = CaptureSession(app, out_dir, width=args.width, height=args.height)
    surface.build(session)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
