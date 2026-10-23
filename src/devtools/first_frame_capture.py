#!/usr/bin/env python3
"""Capture an app start on a private headless Wayland compositor and report
whether the FIRST presented frame already equals the settled one.

Why this tool exists
--------------------
"First presented frame is not the settled frame" (see `docs/dev/DEBUGGING.md`
rule 7 and `QT_LAYOUT_PITFALLS.md` in the private docs repo) cannot be observed
on X11: the X server maps a window only after the client painted it, so a
pre-map frame never reaches the root window — `x11grab`/`ffmpeg`/`QWidget.grab`
and the MCP captures are byte-identical from the first visible frame (measured
2026-10-23 on the Recent-header chips bug: 241 frames identical, while the
same bug was visible for ~0.8 s on Wayland and on the user's screen).

Wayland commits every buffer to the compositor, so a compositor-side capture
(here: headless sway + `grim`) sees exactly what was presented — including the
buffer painted before a deferred batch/layout pass.

Usage
-----
    python3 src/devtools/first_frame_capture.py --out /tmp/ff
    python3 src/devtools/first_frame_capture.py --out /tmp/ff --duration 15 --fps 20
    python3 src/devtools/first_frame_capture.py --out /tmp/ff -- --open-tab image_compare

Exit codes: 0 = every presented frame equals the settled one, 1 = a stale
first state was captured, 2 = harness failure (no compositor / no frames / the
app never appeared).

Requirements: `sway` (wlroots), `grim`. The compositor runs headless
(`WLR_BACKENDS=headless`, pixman renderer) on a private `XDG_RUNTIME_DIR`; the
app gets isolated `XDG_CONFIG_HOME`/`XDG_DATA_HOME`/`XDG_CACHE_HOME` unless
`--config-home`/`--data-home` are given.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A frame counts as "the app is up" when its mean luminance exceeds this (the
#: headless desktop background is dark, the app's light chrome is not).
APP_UP_MEAN = 150
#: Mean absolute pixel difference (0..255) under which two frames are equal.
EQUAL_EPSILON = 0.5


def _pick_compositor() -> str | None:
    for name in ("sway", "weston"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _start_compositor(runtime_dir: Path, log_path: Path) -> subprocess.Popen:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.chmod(0o700)
    sway = shutil.which("sway")
    if sway is None:
        raise SystemExit("first-frame-capture: `sway` is required (wlroots + grim)")
    env = dict(os.environ)
    env.update(
        {
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "WLR_BACKENDS": "headless",
            "WLR_LIBINPUT_NO_DEVICES": "1",
            "WLR_RENDERER": "pixman",
            "WLR_HEADLESS_OUTPUTS": "1",
        }
    )
    # A local scenefx build (swayfx) is a common packaging gap; honour it when
    # the library is not on the default path.
    local_scenefx = Path.home() / "swayfx" / "scenefx" / "build"
    if local_scenefx.is_dir() and not _ldconfig_has("libscenefx.so.1"):
        env["LD_LIBRARY_PATH"] = f"{local_scenefx}:{env.get('LD_LIBRARY_PATH', '')}"
    config = runtime_dir / "sway.conf"
    config.write_text(
        "output HEADLESS-1 resolution 1600x1200\n"
        # No sway-decorated border/title bar: the window box is then exactly
        # the app surface, so "differs from the pre-launch desktop" isolates it.
        "default_border none\n"
        "default_floating_border none\n",
        encoding="utf-8",
    )
    log = log_path.open("wb")
    proc = subprocess.Popen(
        [sway, "--unsupported-gpu", "-c", str(config)],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    socket = runtime_dir / "wayland-1"
    for _ in range(100):
        if socket.exists():
            return proc
        if proc.poll() is not None:
            raise SystemExit(
                f"first-frame-capture: composer died on start (see {log_path})"
            )
        time.sleep(0.1)
    proc.terminate()
    raise SystemExit("first-frame-capture: compositor socket never appeared")


def _ldconfig_has(lib: str) -> bool:
    try:
        out = subprocess.run(
            ["ldconfig", "-p"], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return False
    return lib in out


def _capture_loop(
    frames_dir: Path, wayland_display: str, runtime_dir: Path
) -> subprocess.Popen:
    grim = shutil.which("grim")
    if grim is None:
        raise SystemExit("first-frame-capture: `grim` is required")
    script = (
        f'for i in $(seq -w 1 4000); do "{grim}" "{frames_dir}/f_$i.png" 2>/dev/null; done'
    )
    env = dict(os.environ)
    env["XDG_RUNTIME_DIR"] = str(runtime_dir)
    env["WAYLAND_DISPLAY"] = wayland_display
    return subprocess.Popen(
        ["bash", "-c", script], env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _launch_app(
    repo_root: Path,
    wayland_display: str,
    runtime_dir: Path,
    config_home: Path,
    data_home: Path,
    cache_home: Path,
    app_args: list[str],
    log_path: Path,
) -> subprocess.Popen:
    app_main = repo_root / "src" / "__main__.py"
    venv_python = repo_root / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    env = dict(os.environ)
    env.update(
        {
            "IMGSLI_CONTROL": "1",
            "IMGSLI_CONTROL_DIR": str(runtime_dir),
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "WAYLAND_DISPLAY": wayland_display,
            "QT_QPA_PLATFORM": "wayland",
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_DATA_HOME": str(data_home),
            "XDG_CACHE_HOME": str(cache_home),
            "PYTHONPATH": str(repo_root / "src"),
        }
    )
    log = log_path.open("wb")
    return subprocess.Popen(
        [python, str(app_main), *app_args],
        cwd=str(repo_root),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _load_frame(path: Path):
    """Load one PNG as grayscale, or None for a truncated/incomplete file.

    The grim loop can be killed mid-write, so the newest file is not always
    complete; a partial tail frame must not abort the analysis.
    """
    from PIL import Image

    try:
        image = Image.open(path)
        image.load()
        return image.convert("L")
    except (OSError, ValueError):
        return None


#: Size every window crop is normalised to before comparison, so a window that
#: maximises or moves mid-capture cannot masquerade as a content change.
NORMALISED_SIZE = (800, 600)
#: Mean absolute difference (0..255) under which two normalised window crops
#: are considered the same state. Interpolation from the normalisation costs a
#: few units; the artifacts this tool exists for are much larger.
NORMALISED_EPSILON = 12.0


def _analyse(frames_dir: Path) -> tuple[int, list[tuple[int, float, bool]]]:
    """(first app frame, [(frame, normalised diff, geometry_changed), ...]).

    The window is detected as "pixels that differ from the frame captured
    before the app launched" (sway runs borderless, so that box is the app
    surface). Each window crop is normalised to ``NORMALISED_SIZE`` before the
    diff, so a window that grows/moves is compared on content, not on scale.
    """
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError:
        raise SystemExit("first-frame-capture: Pillow is required for analysis")

    files = sorted(frames_dir.glob("f_*.png"))
    frames = [(index, _load_frame(path)) for index, path in enumerate(files, start=1)]
    frames = [(index, image) for index, image in frames if image is not None]
    if len(frames) < 3:
        raise SystemExit(
            f"first-frame-capture: only {len(frames)} readable frames captured"
        )
    background = frames[0][1]
    screen_area = background.size[0] * background.size[1]

    def window_bbox(image):
        mask = ImageChops.difference(image, background).point(
            lambda v: 255 if v > 8 else 0
        )
        bbox = mask.getbbox()
        if bbox is None:
            return None
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        return bbox if area > 0.02 * screen_area else None

    windowed: list[tuple[int, tuple[int, int, int, int]]] = []
    for index, image in frames:
        bbox = window_bbox(image)
        if bbox is not None:
            windowed.append((index, bbox))
    if not windowed:
        raise SystemExit("first-frame-capture: the app window never appeared")
    first = windowed[0][0]
    final_index, final_bbox = windowed[-1]
    by_index = {index: image for index, image in frames}
    reference = (
        by_index[final_index]
        .crop(final_bbox)
        .resize(NORMALISED_SIZE, Image.Resampling.BILINEAR)
    )

    series: list[tuple[int, float, bool]] = []
    prev: tuple[float, bool] | None = None
    for index, bbox in windowed:
        image = by_index[index]
        normalised = image.crop(bbox).resize(
            NORMALISED_SIZE, Image.Resampling.BILINEAR
        )
        diff = ImageChops.difference(normalised, reference)
        score = round(ImageStat.Stat(diff).mean[0], 2)
        geometry_changed = bbox != final_bbox
        signature = (score, geometry_changed)
        if prev is None or abs(score - prev[0]) > 0.1 or (
            geometry_changed != prev[1]
        ):
            series.append((index, score, geometry_changed))
            prev = signature
    return first, series


def _control_call(socket_path: Path, method: str, params: dict, timeout: float = 5.0):
    """One newline-delimited JSON request on the app control socket."""
    import json
    import socket as socket_module

    sock = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(socket_path))
        sock.sendall(
            (json.dumps({"id": 1, "method": method, "params": params}) + "\n").encode()
        )
        chunks = []
        while True:
            try:
                chunk = sock.recv(65536)
            except socket_module.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
            try:
                return json.loads(b"".join(chunks).decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
    finally:
        sock.close()
    return None


def _watch_elements(
    socket_path: Path, watched: list[str], timeout_s: float
) -> tuple[float | None, dict[str, float]]:
    """Poll ``ui_elements`` until every watched id appeared (or timeout).

    Returns (app-up time, {element id: seconds after app-up when first seen}).
    Geometry-independent: it reads the app's own element model, not pixels, so
    a window resize cannot hide or fake a missing control the way a
    normalised pixel diff can.
    """
    import time

    started = time.monotonic()
    app_up: float | None = None
    seen: dict[str, float] = {}
    while time.monotonic() - started < timeout_s:
        if not socket_path.exists():
            time.sleep(0.05)
            continue
        response = _control_call(socket_path, "ui_elements", {"limit": 500})
        if not response or not response.get("ok"):
            time.sleep(0.05)
            continue
        elements = (response.get("result") or {}).get("elements") or []
        if elements and app_up is None:
            app_up = time.monotonic()
        ids = {str(element.get("id")) for element in elements}
        for name in watched:
            # Match a bare object name (``recent-sort-button``) against the
            # session-scoped id (``ImageComparisonApp/..@recent-sort-button``).
            if any(ident == name or ident.endswith("@" + name) for ident in ids):
                if name not in seen:
                    seen[name] = time.monotonic() - (app_up or time.monotonic())
        if app_up is not None and len(seen) == len(watched):
            break
        time.sleep(0.05)
    return app_up, seen



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True, help="frames + logs directory")
    parser.add_argument(
        "--repo-root",
        help="app checkout to launch (default: this checkout; use a worktree to "
        "verify a pre-fix build)",
    )
    parser.add_argument("--duration", type=float, default=12.0)
    parser.add_argument("--fps", type=int, default=20, help="advisory; grim self-paces")
    parser.add_argument("--config-home", help="reuse a prepared profile (QSettings)")
    parser.add_argument("--data-home", help="reuse a prepared data dir")
    parser.add_argument(
        "--keep", action="store_true", help="keep the compositor/app logs readable"
    )
    parser.add_argument(
        "--fail-on-geometry",
        action="store_true",
        help="also fail when the window moved/resized even if the content "
        "matches (default: geometry transitions are reported, not failed)",
    )
    parser.add_argument(
        "--watch-elements",
        help="comma-separated element ids/object names to poll through the "
        "control surface (ui_elements) from launch; a control that appears "
        "later than the app's first element is a first-frame miss even when "
        "the window resized",
    )
    parser.add_argument(
        "--element-timeout", type=float, default=20.0,
        help="how long to poll --watch-elements (default 20 s)",
    )
    parser.add_argument(
        "--element-settle-ms", type=float, default=250.0,
        help="how late a watched element may appear after the app's first "
        "element before it counts as a first-frame miss (default 250 ms)",
    )
    parser.add_argument("app_args", nargs="*", help="arguments for src/__main__.py")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT
    if not (repo_root / "src" / "__main__.py").is_file():
        raise SystemExit(f"first-frame-capture: no app entry point under {repo_root}")
    out = Path(args.out).resolve()
    frames_dir = out / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    runtime_dir = out / "runtime"
    config_home = Path(args.config_home) if args.config_home else out / "config"
    data_home = Path(args.data_home) if args.data_home else out / "data"
    cache_home = out / "cache"
    for path in (config_home, data_home, cache_home):
        path.mkdir(parents=True, exist_ok=True)

    compositor = app = capture = None
    try:
        compositor = _start_compositor(runtime_dir, out / "sway.log")
        capture = _capture_loop(frames_dir, "wayland-1", runtime_dir)
        time.sleep(0.2)
        app = _launch_app(
            repo_root,
            "wayland-1",
            runtime_dir,
            config_home,
            data_home,
            cache_home,
            args.app_args,
            out / "app.log",
        )
        watched = [w.strip() for w in (args.watch_elements or "").split(",") if w.strip()]
        element_seen: dict[str, float] = {}
        if watched:
            _app_up, element_seen = _watch_elements(
                runtime_dir / "control.sock", watched, args.element_timeout
            )
        time.sleep(args.duration)
    finally:
        _stop(capture)
        _stop(app)
        _stop(compositor)

    first, series = _analyse(frames_dir)
    print(f"first presented frame: {first}")
    stale = []
    for index, score, geometry in series:
        if score < 0:
            tag = "gone"
        elif score <= NORMALISED_EPSILON:
            tag = "settled" + (" (window resized)" if geometry else "")
        else:
            tag = "stale content" + (" (window resized)" if geometry else "")
        print(f"  frame {index:04d}: diff={score:6.2f}  {tag}")
        if score > NORMALISED_EPSILON:
            stale.append(index)
        elif geometry and args.fail_on_geometry:
            stale.append(index)
    failed = bool(stale)
    if stale:
        print(
            f"STALE FIRST FRAME: {len(stale)} presented frame(s) before the settled "
            f"state (frames {stale[0]}..{stale[-1]})"
        )
    if watched:
        budget = args.element_settle_ms / 1000.0
        print("watched elements (seconds after the app's first element):")
        for name in watched:
            delay = element_seen.get(name)
            if delay is None:
                print(f"  {name}: NEVER appeared within {args.element_timeout:.0f}s")
                failed = True
            elif delay > budget:
                print(f"  {name}: {delay * 1000:.0f} ms late  (budget {budget * 1000:.0f} ms)")
                failed = True
            else:
                print(f"  {name}: {delay * 1000:.0f} ms  ok")
    if failed:
        return 1
    print("OK: every presented frame equals the settled one and every watched "
          "element was present with the first one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
