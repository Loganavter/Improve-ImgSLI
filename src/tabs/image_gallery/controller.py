"""Presenter for the Image Gallery tab: folder scan, thumbnails, Stage 3 VLM (tie-break + briefs).
Audit-Meta: pattern=state-machine size=exempt reason="one controller lifecycle — folder scan/thumbnail/triage/VLM sharing GenericWorker state"

Pass 2 VLM is optional, targeted, always via GenericWorker (never UI-blocking).
Unresolved tie-breaks degrade silent-but-visible: pending badge cleared,
local ranking kept.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QPixmap
from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.models import (
    AnalysisStatus,
    GalleryItem,
    GalleryState,
    Mode,
    Series,
    ThumbnailStatus,
    TriageState,
)
from tabs.image_gallery.services.ai_cache import load_cached_analysis, save_analysis
from tabs.image_gallery.services.ai_client import (
    AiAuthError,
    AiClientError,
    AiNetworkError,
    AiRateLimitError,
    AiResponseError,
    analyze_image_sync,
)
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log
from tabs.image_gallery.services.filtering import filter_items
from tabs.image_gallery.services.folder_scanner import scan_folder
from tabs.image_gallery.services.thumbnail_cache import render_and_cache_thumbnail

logger = logging.getLogger("ImproveImgSLI")


# Stage 3: epsilon for local metric tie — when top-2 within this delta, VLM tie-break applies.
# Mirrors design.md Pass 2 "when local metrics are within epsilon".
TIE_EPSILON = 0.025  # embedding distance normalized; tuned for 8×8 HSV vectors

_ERROR_KEYS = {
    AiAuthError: ("image_gallery.errors.auth", "Authentication failed — check your API key."),
    AiRateLimitError: ("image_gallery.errors.rate_limit", "Rate limited — try again later."),
    AiNetworkError: ("image_gallery.errors.network", "Network error while contacting the AI API."),
    AiResponseError: ("image_gallery.errors.parse", "Could not parse the AI response."),
}


class GalleryController:
    def __init__(self, widget, *, thread_pool: QThreadPool | None = None, context=None):
        self.widget = widget
        self.state = GalleryState()
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._context = context
        self._ai_settings_store = AiSettingsStore()
        # Generation tokens against async races: bumped on every folder switch
        # (open_folder/open_paths). Late triage/artifact/thumbnail/VLM results
        # carrying a stale generation are dropped, never applied to the new
        # folder's items. Filter keystrokes get their own token so a slow
        # brief-disk worker cannot resurrect an outdated query.
        self._folder_gen = 0
        self._filter_gen = 0
        self._pending_filter_text = ""
        self._filter_timer = None

        widget.folder_pick_requested.connect(self._on_pick_folder)
        widget.analyze_requested.connect(self.analyze_item_by_path)
        widget.filter_text_changed.connect(self.set_filter_text)
        # Back-link for widget keyPressEvent / card flyout to resolve owner.
        try:
            widget._controller = self  # type: ignore[attr-defined]
            widget._owner = self  # type: ignore[attr-defined]
            # A3: link selection HUD collaborator (widget owns it) to controller for use_cases/selection
            try:
                hud = getattr(widget, "_selection_hud", None)
                if hud is not None:
                    self._selection_hud = hud  # type: ignore[attr-defined]
                    # also expose on widget for widget-side calls
                    widget._selection_hud = hud  # type: ignore[attr-defined]
            except Exception:
                pass
            # Marquee owner for grid_view hit-test commit
            try:
                if hasattr(widget, "_grid_view") and widget._grid_view is not None:
                    widget._grid_view._owner = self  # type: ignore[attr-defined]
            except Exception:
                pass
            # Also expose on window when widget reparented.
            try:
                win = widget.window()
                if win is not None:
                    win._gallery_controller = self  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass

    def _next_folder_gen(self) -> int:
        """Bump the folder generation: all in-flight workers go stale."""
        self._folder_gen += 1
        return self._folder_gen

    def _is_current_folder_gen(self, gen: int) -> bool:
        return gen == self._folder_gen

    # -- folder loading ----------------------------------------------------

    def open_folder(self, folder: Path) -> None:
        import time

        t0 = time.perf_counter()
        folder = Path(folder)
        gen = self._next_folder_gen()
        _ = gen  # sync scan below replaces state immediately; gen guards workers
        _dnd_log("open_folder: ENTER %s is_file=%s is_dir=%s", folder, folder.is_file(), folder.is_dir())
        # If a single image file was passed (user dropped one image), don't scan its parent
        # — show just that image. Previously we scanned parent and fed entire folder (1037 items).
        if folder.is_file():
            _dnd_log("open_folder single file branch -> open_paths single %s", folder)
            # Delegate to open_paths so we don't set folder to parent
            try:
                self.open_paths([folder])
                _dnd_log("open_folder: EXIT via open_paths (%.1f ms)", (time.perf_counter() - t0) * 1000)
                return
            except Exception:
                _dnd_log("open_folder single file fallback", exc_info=True)
                try:
                    mtime = folder.stat().st_mtime_ns
                except Exception:
                    mtime = 0
                items = [GalleryItem(path=folder, mtime_ns=mtime)]
                display_folder = folder.parent
                self.state = GalleryState(folder=display_folder, items=items, triage_state=TriageState.RUNNING)
                _dbg("open_folder single file -> parent %s items=%d", display_folder, len(items))
                self.widget.set_folder_label(display_folder)
                self.widget.rebuild_grid(items)
                for item in items:
                    self._load_thumbnail(item)
                self._start_triage(items)
                return
        _dnd_log("open_folder: scan_folder START %s", folder)
        items = scan_folder(folder)
        _dnd_log("open_folder: scan_folder DONE %s -> %d items (%.1f ms)", folder, len(items), (time.perf_counter() - t0) * 1000)
        _dnd_log("open_folder scanned %s -> %d items", folder, len(items))
        self.state = GalleryState(folder=folder, items=items, triage_state=TriageState.RUNNING)
        _dnd_log("open_folder: set state + rebuild_grid START (%d items)", len(items))
        self.widget.set_folder_label(folder)
        self.widget.rebuild_grid(items)
        _dnd_log("open_folder: rebuild_grid DONE (%.1f ms total)", (time.perf_counter() - t0) * 1000)
        for item in items:
            self._load_thumbnail(item)
        self._start_triage(items)
        _dnd_log("open_folder: EXIT ok (%.1f ms)", (time.perf_counter() - t0) * 1000)

    def open_paths(self, paths: list[Path]) -> None:
        """Open an explicit list of image paths (single/multiple drop).

        Fixes "скормить всю папку когда скинул одно изображение": previously
        a single image drop was converted to its parent folder and the whole
        folder was scanned (40 images). Now we build items only from the
        explicitly dropped paths.
        """
        import time

        t0 = time.perf_counter()
        _dnd_log("open_paths: ENTER %d paths %r", len(paths), paths[:3])
        # Folder switch cancels everything in flight from the previous folder.
        self._next_folder_gen()
        # Filter to images that exist
        from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS

        filtered: list[GalleryItem] = []
        for p in paths:
            pp = Path(p)
            if pp.is_file() and pp.suffix.lower() in ACCEPTED_IMAGE_EXTENSIONS:
                try:
                    mtime = pp.stat().st_mtime_ns
                except Exception:
                    mtime = 0
                filtered.append(GalleryItem(path=pp, mtime_ns=mtime))
            elif pp.is_dir():
                # If a directory was dropped among files, scan it
                filtered.extend(scan_folder(pp))
        # Deduplicate by path
        seen: set[str] = set()
        uniq: list[GalleryItem] = []
        for it in filtered:
            s = str(it.path.resolve()) if it.path.exists() else str(it.path)
            if s not in seen:
                seen.add(s)
                uniq.append(it)
        # For explicit file drops, don't set folder to parent — keep it None
        # so we don't imply the whole parent folder was opened (fixes "установил путь на папку"
        # when user dropped a single image). Folder is only set when a directory
        # was explicitly dropped/scanned. For file lists, display_folder stays None
        # and the label shows the dropped files, not their parent.
        display_folder = None
        has_dir_input = any(Path(p).is_dir() for p in paths)
        if has_dir_input and uniq:
            # Directory was among dropped paths — use its path as folder
            for p in paths:
                if Path(p).is_dir():
                    display_folder = Path(p)
                    break
            if display_folder is None:
                try:
                    display_folder = uniq[0].path.parent
                except Exception:
                    display_folder = None
        # else: file-only drop — leave display_folder as None (no folder context)
        self.state = GalleryState(folder=display_folder, items=uniq, triage_state=TriageState.RUNNING)
        _dnd_log("open_paths -> folder %s items=%d (has_dir=%s) (%.1f ms)", display_folder, len(uniq), has_dir_input, (time.perf_counter() - t0) * 1000)
        if display_folder is not None:
            self.widget.set_folder_label(display_folder)
        else:
            # For single/multi file drop, show what was actually dropped, not parent
            try:
                if len(uniq) == 1:
                    self.widget.set_folder_label(uniq[0].path)
                elif len(uniq) > 1:
                    self.widget.set_folder_label(Path(f"{len(uniq)} images dropped"))
                else:
                    self.widget.set_folder_label(Path(""))
            except Exception:
                pass
        self.widget.rebuild_grid(uniq)
        for item in uniq:
            self._load_thumbnail(item)
        self._start_triage(uniq)

    def _on_pick_folder(self) -> None:
        start_dir = str(self.state.folder) if self.state.folder else ""
        chosen = self.widget.pick_folder_dialog(start_dir=start_dir)
        if not chosen:
            return
        p = Path(chosen)
        _dbg("pick_folder_dialog chosen: %s is_file=%s is_dir=%s", p, p.is_file(), p.is_dir())
        # If dialog returned a file (image picked), open just that file
        if p.is_file():
            self.open_paths([p])
        elif p.is_dir():
            self.open_folder(p)
        else:
            # Fallback: try as folder
            if Path(chosen).exists():
                if Path(chosen).is_file():
                    self.open_paths([Path(chosen)])
                else:
                    self.open_folder(Path(chosen))

    def _find_item(self, path: Path) -> GalleryItem | None:
        for item in self.state.items:
            if item.path == path:
                return item
        return None

    # -- thumbnails ----------------------------------------------------------

    def _load_thumbnail(self, item: GalleryItem) -> None:
        item.thumbnail_status = ThumbnailStatus.LOADING
        gen = self._folder_gen
        worker = GenericWorker(render_and_cache_thumbnail, item.path, item.mtime_ns)
        worker.signals.result.connect(
            lambda cache_path, path=item.path, g=gen: self._on_thumbnail_ready(path, cache_path, g)
        )
        worker.signals.error.connect(
            lambda err, path=item.path, g=gen: self._on_thumbnail_error(path, g)
        )
        # Thumbnails are lowest priority: triage/artifact/VLM workers jump ahead.
        try:
            self._thread_pool.start(worker, 0)
        except TypeError:
            self._thread_pool.start(worker)

    def _on_thumbnail_ready(self, path: Path, cache_path: Path | None, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched mid-flight — late thumbnail dropped
        item = self._find_item(path)
        if item is None:
            return
        if cache_path is None:
            item.thumbnail_status = ThumbnailStatus.ERROR
        else:
            pixmap = QPixmap(str(cache_path))
            if pixmap.isNull():
                item.thumbnail_status = ThumbnailStatus.ERROR
            else:
                item.thumbnail = pixmap
                item.thumbnail_status = ThumbnailStatus.LOADED
        self.widget.refresh_card(item)

    def _on_thumbnail_error(self, path: Path, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return
        item = self._find_item(path)
        if item is None:
            return
        item.thumbnail_status = ThumbnailStatus.ERROR
        self.widget.refresh_card(item)

    # -- AI analyze -----------------------------------------------------------

    def _tr(self, key: str, default: str) -> str:
        context = self._context
        if context is not None:
            return context._tr(key, default)
        return default

    def analyze_item_by_path(self, path: Path) -> None:
        item = self._find_item(path)
        if item is None:
            return
        self.analyze_item(item)

    def analyze_item(self, item: GalleryItem) -> None:
        cached = load_cached_analysis(item.path, item.mtime_ns)
        if cached is not None:
            item.analysis = cached
            item.analysis_status = AnalysisStatus.DONE
            item.analysis_error = None
            self.widget.refresh_card(item)
            return

        settings = self._ai_settings_store.load()
        if not settings.enabled or not settings.api_key or not settings.model:
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = self._tr(
                "image_gallery.errors.not_configured",
                "Configure the AI API key in Settings first.",
            )
            self.widget.refresh_card(item)
            return

        item.analysis_status = AnalysisStatus.PENDING
        item.analysis_error = None
        self.widget.refresh_card(item)

        worker = GenericWorker(
            analyze_image_sync,
            item.path,
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
        )
        gen = self._folder_gen
        worker.signals.result.connect(
            lambda result, path=item.path, mtime_ns=item.mtime_ns, g=gen: self._on_analysis_ready(
                path, mtime_ns, result, g
            )
        )
        worker.signals.error.connect(
            lambda err, path=item.path, g=gen: self._on_analysis_error(path, err, g)
        )
        self._thread_pool.start(worker)

    def _on_analysis_ready(self, path: Path, mtime_ns: int, result, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late analysis dropped
        item = self._find_item(path)
        if item is None:
            return
        save_analysis(path, mtime_ns, result)
        item.analysis = result
        item.analysis_status = AnalysisStatus.DONE
        item.analysis_error = None
        self.widget.refresh_card(item)

    def _on_analysis_error(self, path: Path, error_info, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return
        item = self._find_item(path)
        if item is None:
            return
        exctype, value, _tb = error_info
        message = None
        for error_cls, (key, default) in _ERROR_KEYS.items():
            if isinstance(value, error_cls) or (
                isinstance(exctype, type) and issubclass(exctype, error_cls)
            ):
                message = self._tr(key, default)
                break
        if message is None and isinstance(value, AiClientError):
            message = str(value)
        item.analysis_status = AnalysisStatus.ERROR
        item.analysis_error = message or str(value)
        self.widget.refresh_card(item)

    # -- triage (Stage 2 Pass 1) -----------------------------------------------

    def _run_triage_sync(self, items: list[GalleryItem]) -> tuple[list[Series], Path | None, Mode]:
        """Pure pipeline for GenericWorker: cluster → hub → mode."""
        from tabs.image_gallery.services.clustering import cluster_items
        from tabs.image_gallery.services.hub_detection import detect_source
        from tabs.image_gallery.services.mode import select_mode

        series = cluster_items(items)
        source = detect_source(series, items)
        mode = select_mode(series, items, source)
        return (series, source, mode)

    def _start_triage(self, items: list[GalleryItem]) -> None:
        if not items:
            self.state.triage_state = TriageState.DONE
            self.state.series = []
            self.state.mode = None
            self.state.source_path = None
            try:
                self.widget.set_triage([], None, None)
            except Exception:
                logger.debug("widget.set_triage failed for empty folder", exc_info=True)
            return
        self.state.triage_state = TriageState.RUNNING
        # A1: S1 scanning n/N in toolbar + empty state (progressive grid)
        try:
            self.widget.set_scanning(0, len(items))
        except Exception:
            logger.debug("widget.set_scanning failed", exc_info=True)
        worker = GenericWorker(self._run_triage_sync, list(items))
        gen = self._folder_gen
        worker.signals.result.connect(lambda res, g=gen: self._on_triage_ready(res, g))
        worker.signals.error.connect(lambda err, g=gen: self._on_triage_error(err, g))
        # Triage outranks thumbnails so the grid labels settle first.
        try:
            self._thread_pool.start(worker, 2)
        except TypeError:
            self._thread_pool.start(worker)

    def _run_artifacts_sync(self, items: list[GalleryItem], source_path: Path | None) -> dict[str, dict]:        """Pure worker for GenericWorker: analyze 7 artifacts per item."""
        from tabs.image_gallery.services.artifacts import analyze_artifacts

        out: dict[str, dict] = {}
        for it in items:
            try:
                res = analyze_artifacts(it.path, source_path)
                # Store as str -> Severity value string for serialization, but keep Enum
                out[str(it.path)] = res
            except Exception:
                logger.debug("artifact analyze failed for %s", it.path, exc_info=True)
                out[str(it.path)] = {}
        return out

    def _start_artifact_analysis(self, items: list[GalleryItem], source_path: Path | None) -> None:
        if not items:
            return
        # Run in background via GenericWorker (never UI-blocking).
        try:
            gen = self._folder_gen
            worker = GenericWorker(self._run_artifacts_sync, list(items), source_path)
            worker.signals.result.connect(lambda res, g=gen: self._on_artifacts_ready(res, g))
            worker.signals.error.connect(self._on_artifacts_error)
            try:
                self._thread_pool.start(worker, 1)
            except TypeError:
                self._thread_pool.start(worker)
        except Exception:
            logger.debug("artifact worker start failed", exc_info=True)

    def _on_artifacts_ready(self, result: object, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late artifact catalog dropped
        # result: dict[str(path), dict[Artifact, Severity]]
        if not isinstance(result, dict):
            return
        for item in self.state.items:
            key = str(item.path)
            arts = result.get(key)
            if arts is None:
                continue
            try:
                # Keep Enum values as-is (models.Severity)
                item.artifacts = dict(arts)  # type: ignore[assignment]
                # Also mirror into metrics for persistence / quick look fallback
                if isinstance(item.metrics, dict):
                    item.metrics["artifacts"] = {str(k): (v.value if hasattr(v, "value") else str(v)) for k, v in arts.items()}
                # Refresh card dots (warm/red flagged, yellow mild, gray clean)
                try:
                    self.widget.refresh_card(item)
                except Exception:
                    logger.debug("widget.refresh_card failed for artifact %s", item.path, exc_info=True)
                # Quick look report: if widget has quick look overlay visible, refresh it.
                try:
                    # Widget owns _quick_look_overlay (QuickLookOverlay).
                    for attr in ("_quick_look_overlay", "_quick_look", "_quicklook", "_quicklook_overlay"):
                        ql = getattr(self.widget, attr, None)
                        if ql is not None and hasattr(ql, "refresh_artifacts"):
                            try:
                                ql.refresh_artifacts(item)
                            except Exception:
                                pass
                    # Also try generic widget helpers.
                    if hasattr(self.widget, "refresh_quick_look"):
                        try:
                            self.widget.refresh_quick_look(item)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                    if hasattr(self.widget, "refresh_artifacts_for"):
                        try:
                            self.widget.refresh_artifacts_for(item)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                logger.debug("artifact apply failed for %s", item.path, exc_info=True)

    def _on_artifacts_error(self, error_info: object) -> None:
        logger.debug("artifact worker error: %r", error_info, exc_info=True)

    # -- fidelity metrics (Stage 2 Pass 1b, wave B producer) --------------------

    def _start_fidelity_analysis(self, items: list[GalleryItem], source_path: Path | None) -> None:
        """Background SSIM/HF/ΔE/upscale metrics vs source (GenericWorker).

        Fail-closed: without a source there is nothing to compare against —
        keys stay absent and quick look renders "not measured" rows.
        """
        if not items or source_path is None:
            return
        try:
            from tabs.image_gallery.services.fidelity_metrics import run_fidelity_sync

            gen = self._folder_gen
            worker = GenericWorker(run_fidelity_sync, list(items), source_path)
            worker.signals.result.connect(lambda res, g=gen: self._on_fidelity_ready(res, g))
            worker.signals.error.connect(
                lambda err: logger.debug("fidelity worker error: %r", err, exc_info=True)
            )
            try:
                self._thread_pool.start(worker, 1)
            except TypeError:
                self._thread_pool.start(worker)
        except Exception:
            logger.debug("fidelity worker start failed", exc_info=True)

    def _on_fidelity_ready(self, result: object, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late fidelity metrics dropped
        if not isinstance(result, dict):
            return
        for item in self.state.items:
            try:
                key = str(item.path)
            except Exception:
                continue
            entry = result.get(key)
            if not isinstance(entry, dict):
                continue
            # Identity fail-closed: entry key came from this item's own path;
            # write the 4 keys only when all measured, never a partial copy.
            required = ("ssim", "hf_ratio", "delta_e", "upscale_factor")
            if not all(k in entry for k in required):
                continue
            try:
                if not isinstance(item.metrics, dict):
                    continue
                for k in required:
                    item.metrics[k] = entry[k]
                try:
                    self.widget.refresh_card(item)
                except Exception:
                    logger.debug("widget.refresh_card failed for fidelity %s", item.path, exc_info=True)
            except Exception:
                logger.debug("fidelity apply failed for %s", item.path, exc_info=True)

    def _on_triage_ready(self, result: object, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            logger.debug("triage result dropped: stale folder generation")
            return
        try:
            series, source, mode = result  # type: ignore[misc]
        except Exception:
            logger.debug("triage result unpack failed: %r", result, exc_info=True)
            self.state.triage_state = TriageState.ERROR
            return
        self.state.series = series  # type: ignore[assignment]
        self.state.source_path = source  # type: ignore[assignment]
        self.state.mode = mode  # type: ignore[assignment]
        self.state.triage_state = TriageState.DONE
        try:
            self.widget.set_triage(series, mode, source)
        except Exception:
            logger.debug("widget.set_triage failed", exc_info=True)
        # A1: toolbar ✓ triage complete
        try:
            # Prefer widget helper, fallback to toolbar directly
            if hasattr(self.widget, "set_triage_done"):
                self.widget.set_triage_done()  # type: ignore[attr-defined]
            elif hasattr(self.widget, "toolbar") and hasattr(self.widget.toolbar, "set_triage_done"):
                self.widget.toolbar.set_triage_done()  # type: ignore[attr-defined]
        except Exception:
            logger.debug("toolbar.set_triage_done failed", exc_info=True)
        # Stage 2 artifact catalog (7 detectors) — background after clustering → dots + quick look
        try:
            self._start_artifact_analysis(list(self.state.items), source)
        except Exception:
            logger.debug("artifact analysis start failed", exc_info=True)
        # Stage 2 fidelity metrics (SSIM/HF/ΔE/upscale vs source) — background, fail-closed
        try:
            self._start_fidelity_analysis(list(self.state.items), source)
        except Exception:
            logger.debug("fidelity analysis start failed", exc_info=True)
        # Stage 3: targeted tie-break for top-2 when local metrics within epsilon (badge pending)
        try:
            for ser in series or []:
                self.run_tie_break_if_needed(ser)
        except Exception:
            logger.debug("tie-break auto-run failed", exc_info=True)

    def _on_triage_error(self, error_info: object, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return
        logger.debug("triage worker error: %r", error_info, exc_info=True)
        self.state.triage_state = TriageState.ERROR
        try:
            self.widget.set_triage([], None, None)
        except Exception:
            pass

    # -- Stage 3 VLM: tie-break + compare briefs (GenericWorker, badge pending, silent degrade) --

    def _is_tie(self, a: GalleryItem, b: GalleryItem, epsilon: float = TIE_EPSILON) -> bool:
        """Local-metric epsilon check for top-2 tie-break eligibility."""
        try:
            da = a.metrics.get("embedding_dist_to_centroid")
            db = b.metrics.get("embedding_dist_to_centroid")
            if da is not None and db is not None:
                return abs(float(da) - float(db)) < epsilon
            # Fallback: sharpness / ssim deltas
            for key in ("sharpness", "ssim", "artifact_score"):
                va = a.metrics.get(key)
                vb = b.metrics.get(key)
                if va is not None and vb is not None:
                    try:
                        av, bv = float(va), float(vb)
                        denom = max(abs(av), abs(bv), 1e-6)
                        if abs(av - bv) / denom < epsilon * 2:
                            return True
                    except Exception:
                        continue
            # No metrics → conservative: treat rank-1 vs rank-2 as tie candidate if phash close?
            # Use hamming of phash if available
            pa = a.metrics.get("phash")
            pb = b.metrics.get("phash")
            if isinstance(pa, int) and isinstance(pb, int):
                ham = bin(int(pa) ^ int(pb)).count("1")
                if ham <= 4:
                    return True
            return False
        except Exception:
            return False

    def run_tie_break_if_needed(self, series) -> None:
        """Stage 3: selective VLM tie-break for top-2 when local metrics within epsilon.

        *series* may be a ``Series`` dataclass (has .members) or plain list[GalleryItem].
        Sets badge ``AI tie-break…`` pending on both candidates until resolved;
        degrades silent-but-visible if unresolved (badge cleared, local ranking kept).
        Uses ``GenericWorker`` (never UI-blocking), cached via ``vlm_cache`` (hash paths+mtime).
        """
        try:
            members = list(getattr(series, "members", series) or [])
        except Exception:
            return
        if len(members) < 2:
            return
        # Sort by rank (1 is best) then embedding distance
        def _sort_key(it: GalleryItem):
            r = getattr(it, "rank", None) or getattr(it, "crown_rank", None)
            try:
                rk = int(r) if r is not None else 999
            except Exception:
                rk = 999
            d = it.metrics.get("embedding_dist_to_centroid") if isinstance(it.metrics, dict) else None
            try:
                df = float(d) if d is not None else 1e9
            except Exception:
                df = 1e9
            return (rk, df)

        sorted_members = sorted(members, key=_sort_key)
        top2 = sorted_members[:2]
        if len(top2) < 2:
            return
        a, b = top2[0], top2[1]
        if not self._is_tie(a, b):
            return

        # Use existing analyze_image_sync only via VLM targeted path — tie-break needs 2 images.
        settings = self._ai_settings_store.load()
        # Degrade silent-but-visible if AI not configured: keep local ranking, no badge
        if not settings.enabled or not settings.api_key or not settings.model:
            logger.debug("tie-break skipped: AI not configured (silent degrade)")
            return

        # Resolve source path for fidelity mode (if available) — needed early for cache key source_mtime
        source = getattr(self.state, "source_path", None)
        try:
            source = Path(source) if source is not None else None
        except Exception:
            source = None
        # source_mtime for vlm_cache key (design parity: hash(paths+mtime+source_mtime))
        source_mtime: int | None = None
        if source is not None:
            try:
                si = self._find_item(source)
                if si is not None:
                    source_mtime = int(getattr(si, "mtime_ns", 0) or 0) or None
                else:
                    source_mtime = int(Path(source).stat().st_mtime_ns)
            except Exception:
                source_mtime = None

        # Check cache first (key = hash(paths+mtime+source_mtime))
        try:
            from tabs.image_gallery.services.vlm_cache import load_cached_tie_break, save_tie_break
        except Exception:
            load_cached_tie_break = None  # type: ignore
            save_tie_break = None  # type: ignore

        if load_cached_tie_break is not None:
            try:
                cached = load_cached_tie_break(a.path, a.mtime_ns, b.path, b.mtime_ns, source_mtime)
                if cached is not None:
                    self._apply_tie_break_result(a, b, cached)
                    return
            except Exception:
                logger.debug("tie-break cache load failed", exc_info=True)

        # Badge pending on both candidates
        for it in top2:
            it.vlm_tie_pending = True
            it.vlm_tie_error = None
            try:
                self.widget.refresh_card(it)
            except Exception:
                pass

        from tabs.image_gallery.services.vlm import tie_break_sync

        worker = GenericWorker(
            tie_break_sync,
            a.path,
            b.path,
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            source=source,
        )

        def _on_result(result, a_path=a.path, b_path=b.path, a_mtime=a.mtime_ns, b_mtime=b.mtime_ns, _src_mtime=source_mtime, gen=self._folder_gen):
            if not self._is_current_folder_gen(gen):
                return  # folder switched mid-VLM — late tie-break dropped
            try:
                if save_tie_break is not None:
                    save_tie_break(a_path, a_mtime, b_path, b_mtime, result, _src_mtime)
            except Exception:
                logger.debug("tie-break cache save failed", exc_info=True)
            # Find current items (may have been refreshed)
            item_a = self._find_item(a_path)
            item_b = self._find_item(b_path)
            if item_a is None or item_b is None:
                return
            self._apply_tie_break_result(item_a, item_b, result)

        def _on_error(error_info, top2_paths=(a.path, b.path), gen=self._folder_gen):
            if not self._is_current_folder_gen(gen):
                return
            logger.debug("tie-break worker error: %r", error_info, exc_info=True)
            # Silent-but-visible degrade: clear pending badge, keep local ranking
            for p in top2_paths:
                it = self._find_item(p)
                if it is not None:
                    it.vlm_tie_pending = False
                    # keep vlm_tie_error visible as tooltip but not badge
                    try:
                        exctype, value, _tb = error_info
                        it.vlm_tie_error = str(value)[:200] if value is not None else "tie-break unresolved"
                    except Exception:
                        it.vlm_tie_error = "tie-break unresolved"
                    try:
                        self.widget.refresh_card(it)
                    except Exception:
                        pass

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        self._thread_pool.start(worker)

    def _apply_tie_break_result(self, a: GalleryItem, b: GalleryItem, result) -> None:
        """Apply VLM winner: mark winner is_best/crown_rank, clear pending badges."""
        try:
            winner_str = str(getattr(result, "winner_path", ""))
            loser_str = str(getattr(result, "loser_path", ""))
            # Resolve which of a,b is winner by path equality (resolve-aware)
            def _matches(item: GalleryItem, s: str) -> bool:
                try:
                    return str(item.path.resolve()) == s or str(item.path) == s
                except Exception:
                    return str(item.path) == s

            winner = a if _matches(a, winner_str) else (b if _matches(b, winner_str) else a)
            loser = b if winner is a else a
            # Downgrade loser, promote winner within series (keep other members untouched)
            try:
                winner.is_best = True
                winner.crown_rank = 1
                winner.rank = 1
                winner.vlm_tie_result = result
            except Exception:
                pass
            try:
                loser.is_best = False
                loser.crown_rank = 2
                loser.rank = 2
                loser.vlm_tie_result = result
            except Exception:
                pass
            for it in (a, b):
                it.vlm_tie_pending = False
                it.vlm_tie_error = None
                try:
                    self.widget.refresh_card(it)
                except Exception:
                    pass
            # Persist in state
            try:
                key = getattr(a, "series_id", None) or getattr(b, "series_id", None) or f"{a.path}:{b.path}"
                self.state.tie_breaks[str(key)] = result
            except Exception:
                pass
        except Exception:
            logger.debug("apply tie-break failed", exc_info=True)
            for it in (a, b):
                try:
                    it.vlm_tie_pending = False
                    self.widget.refresh_card(it)
                except Exception:
                    pass

    def _apply_brief_result(self, pa: Path, pb: Path, result, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late brief dropped
        try:
            # Persist in state (one per pair)
            try:
                key = f"{Path(pa).resolve()}:{Path(pb).resolve()}"
                # normalize order
                if str(Path(pa).resolve()) > str(Path(pb).resolve()):
                    key = f"{Path(pb).resolve()}:{Path(pa).resolve()}"
                self.state.briefs[key] = result
            except Exception:
                pass
            for p in (pa, pb):
                it = self._find_item(p)
                if it is not None:
                    it.vlm_brief = result
                    it.vlm_brief_status = "done"
                    it.vlm_brief_error = None
                    try:
                        self.widget.refresh_card(it)
                    except Exception:
                        pass
        except Exception:
            logger.debug("apply brief failed", exc_info=True)

    # -- Stage 2 crown/reject/S3 (thin wrappers → use_cases/triage) --------

    def make_best(self, path: Path) -> bool:
        from tabs.image_gallery.use_cases.triage import make_best as _make_best

        return bool(_make_best(self, path))

    def toggle_reject(self, path: Path) -> bool:
        from tabs.image_gallery.use_cases.triage import toggle_reject as _toggle

        return bool(_toggle(self, path))

    def keep_best_of_series(self) -> dict:
        from tabs.image_gallery.use_cases.triage import keep_best_of_series as _keep

        return _keep(self)

    def clean_rejected(self) -> list[dict]:
        from tabs.image_gallery.use_cases.triage import clean_rejected as _clean

        return _clean(self)

    def show_clean_review(self) -> None:
        # Delegate to widget's S3 overlay (TopLevelInWindowOverlay).
        try:
            if hasattr(self.widget, "show_clean_review"):
                self.widget.show_clean_review(self)
        except Exception:
            pass

    # -- filtering (debounced; brief-disk match off UI thread) --------

    #: Keystroke coalescing window — rapid typing applies once, not per char.
    FILTER_DEBOUNCE_MS = 120

    def set_filter_text(self, text: str) -> None:
        self._pending_filter_text = text or ""
        timer = self._filter_timer
        if timer is None:
            try:
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(self._apply_pending_filter)
                self._filter_timer = timer
            except Exception:
                timer = None
        if timer is None:
            # No Qt event loop (headless unit context) — apply synchronously.
            self._apply_filter(self._pending_filter_text, self._filter_gen + 1)
            return
        try:
            timer.stop()
            timer.start(self.FILTER_DEBOUNCE_MS)
        except Exception:
            self._apply_filter(self._pending_filter_text, self._filter_gen + 1)

    def apply_pending_filter(self) -> None:
        """Flush a debounced keystroke synchronously (tests / teardown)."""
        timer = self._filter_timer
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._apply_pending_filter()

    def _apply_pending_filter(self) -> None:
        self._filter_gen += 1
        self._apply_filter(self._pending_filter_text, self._filter_gen)

    def _apply_filter(self, text: str, filter_gen: int) -> None:
        from tabs.image_gallery.services.filtering import match_brief_items, match_fast_items

        self._filter_gen = max(self._filter_gen, filter_gen)
        gen = self._filter_gen
        self.state.filter_text = text
        # Fast pass on the UI thread: filename + in-memory tags only, no disk.
        fast = {item.path for item in match_fast_items(self.state.items, text)}
        if not (text or "").strip():
            fast = {item.path for item in self.state.items}
        for item in self.state.items:
            try:
                self.widget.set_card_visible(item.path, item.path in fast)
            except Exception:
                pass
        if not (text or "").strip():
            return
        # Slow pass off the UI thread: brief-cache disk match, mtime-honored.
        # Merged on arrival only if no newer keystroke/folder switch landed.
        snapshot = list(self.state.items)

        def _slow() -> set:
            try:
                return {item.path for item in match_brief_items(snapshot, text)}
            except Exception:
                return set()

        folder_gen = self._folder_gen
        worker = GenericWorker(_slow)
        worker.signals.result.connect(
            lambda extra, g=gen, fg=folder_gen: self._on_brief_filter_ready(extra, g, fg)
        )
        worker.signals.error.connect(lambda _err: None)
        try:
            self._thread_pool.start(worker, 0)
        except TypeError:
            self._thread_pool.start(worker)

    def _on_brief_filter_ready(self, extra_paths: set, filter_gen: int, folder_gen: int) -> None:
        if filter_gen != self._filter_gen or not self._is_current_folder_gen(folder_gen):
            return  # stale query or folder switch — never resurrect old matches
        if not extra_paths:
            return
        for item in self.state.items:
            if item.path in extra_paths:
                try:
                    self.widget.set_card_visible(item.path, True)
                except Exception:
                    pass