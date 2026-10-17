"""Quick Look preview canvas — RHI resource-update-batch ownership.

Pinned invariant: **every** batch handed out by
``rhi.nextResourceUpdateBatch()`` is consumed exactly once on every path
out of ``render()`` — either handed to
``command_buffer.beginPass(target, clear, depth_clear, batch)`` or
submitted via ``command_buffer.resourceUpdate(batch)`` (the tree-wide
idiom; see ``engine.gpu.tiled_image_view.render``).

A batch abandoned on an early return is never recycled by QRhi: it stays
live in the shared resource-update pool. Under fast item switching the
pool is exhausted and Qt's own widget-compositing flush later replays a
pooled batch whose recorded uploads reference resources destroyed in the
meantime — the reported SIGSEGV in
``QWidgetRepaintManager::flush -> QPlatformBackingStore::rhiFlush``.

No GPU: the rhi + command buffer are pure-Python fakes. Each
``nextResourceUpdateBatch()`` hands out a *distinct* sentinel object and
consumption is recorded by object identity, so the fake exposes
``outstanding == taken - consumed`` — the exact predicate the pre-fix
code violated (see ``DONE.md`` for the recorded failing run).
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_gallery.ui.quick_look.preview_canvas import rhi_entry


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


class _Batch:
    """Distinct sentinel per ``nextResourceUpdateBatch()`` call."""

    __slots__ = ("n",)

    def __init__(self, n: int) -> None:
        self.n = n

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<_Batch {self.n}>"


class _FakeRhi:
    def __init__(self, *, fail_calls: tuple = ()) -> None:
        self.handed: list = []
        self.calls = 0
        self._fail_calls = set(fail_calls)

    def nextResourceUpdateBatch(self):
        self.calls += 1
        if self.calls in self._fail_calls:
            raise RuntimeError(f"rhi batch unavailable (call {self.calls})")
        batch = _Batch(self.calls)
        self.handed.append(batch)
        return batch


class _FakeCmd:
    """Records consumption of a batch by identity (beginPass or resourceUpdate)."""

    def __init__(self, *, fail_begin: bool = False) -> None:
        self.consumed: list = []
        self.begin_calls = 0
        self.end_calls = 0
        self._fail_begin = fail_begin

    def resourceUpdate(self, batch) -> None:
        self.consumed.append(batch)

    def beginPass(self, target, clear, depth_clear, batch) -> None:
        self.begin_calls += 1
        if self._fail_begin:
            raise RuntimeError("beginPass failed")
        self.consumed.append(batch)

    def endPass(self) -> None:
        self.end_calls += 1


def _outstanding(rhi: _FakeRhi, cmd: _FakeCmd) -> int:
    """taken - consumed (negative if a batch was consumed twice)."""
    return len(rhi.handed) - len(cmd.consumed)


class _FakeShell:
    def __init__(
        self, *, fail_stage: bool = False, fail_upload: bool = False
    ) -> None:
        self.stage_calls = 0
        self.upload_calls = 0
        self.draw_calls = 0
        self._fail_stage = fail_stage
        self._fail_upload = fail_upload

    def stage_quad(self, updates) -> None:
        self.stage_calls += 1
        if self._fail_stage:
            raise RuntimeError("stage failed")

    def stage_clip(self, updates, clip) -> None:
        pass

    def upload_frame(self, updates, target, frame) -> None:
        self.upload_calls += 1
        if self._fail_upload:
            raise RuntimeError("upload failed")

    def draw(self, command_buffer, width=0.0, height=0.0) -> None:
        self.draw_calls += 1


class _FakeRenderer:
    """Stand-in for ``SingleImageTiledView``.

    Mirrors the engine seam's documented behaviour: it submits the frame's
    uploads internally via ``command_buffer.resourceUpdate(updates)`` even
    when it draws nothing / is not yet covered.
    """

    def __init__(
        self,
        *,
        covered: bool,
        drawn: bool = True,
        resident: int = 1,
        consume: bool = True,
    ) -> None:
        self._covered = covered
        self._drawn = drawn
        self._resident = resident
        self._consume = consume
        self.render_calls = 0

    def has_source(self) -> bool:
        return True

    def store_size(self):
        return (64, 64)

    def render(self, command_buffer, **kwargs):
        self.render_calls += 1
        updates = kwargs.get("updates")
        if self._consume and updates is not None:
            command_buffer.resourceUpdate(updates)
        return SimpleNamespace(
            covered=self._covered,
            drawn=self._drawn,
            instances=1,
            resident=self._resident,
        )


def _target(w: int = 64, h: int = 64):
    return SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: w, height=lambda: h)
    )


class _FakeWidget:
    """Pure-Python stand-in for ``QuickLookCanvasWidget`` as seen by ``render()``."""

    def __init__(
        self,
        rhi,
        *,
        shell=None,
        target=None,
        frame=None,
        shell_ready: bool = True,
        frame_ok: bool = True,
        tiled_source=None,
        renderer=None,
        tile_level_ready: bool = False,
        rhi_raises: bool = False,
    ) -> None:
        self._rhi = rhi
        self._shell = shell if shell is not None else _FakeShell()
        self._target = target if target is not None else _target()
        self._frame = frame
        self._shell_ready = shell_ready
        self._frame_ok = frame_ok
        self._tiled_source = tiled_source
        self._renderer = renderer
        self._tile_level_ready = tile_level_ready
        self._rhi_raises = rhi_raises
        self.settled = 0
        self.pumps = 0
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

    # -- QRhiWidget surface used by render() --------------------------------
    def rhi(self):
        if self._rhi_raises:
            raise RuntimeError("no rhi")
        return self._rhi

    def renderTarget(self):
        return self._target

    def isVisible(self) -> bool:
        return True

    def width(self) -> int:
        return 64

    def height(self) -> int:
        return 64

    # -- rhi_entry module functions, bound as methods -----------------------
    def _skip_frame(self, reason) -> None:
        return rhi_entry._skip_frame(self, reason)

    def _render_tiled(self, *args, **kwargs):
        return rhi_entry._render_tiled(self, *args, **kwargs)

    def _ql_view_hooks(self):
        return rhi_entry._ql_view_hooks(self)

    def _tiled_level_ready(self) -> bool:
        return bool(self._tile_level_ready)

    # -- frame plumbing -----------------------------------------------------
    def _raster_frame(self, target):
        return self._frame

    def _ensure_tile_renderer(self):
        return self._renderer

    def _settle_present(self) -> None:
        self.settled += 1

    def _pump_next_frame(self) -> None:
        self.pumps += 1

    def _pump_throttled(self, stall_frames) -> None:
        self.pumps += 1


def _drive(widget: _FakeWidget, cmd: _FakeCmd) -> None:
    rhi_entry.render(widget, cmd)


# ---------------------------------------------------------------------------
# every early-return path consumes its batch(es)
# ---------------------------------------------------------------------------


def test_frame_ok_false_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, frame_ok=False)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


def test_not_ready_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, shell_ready=False)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


def test_no_rhi_target_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, rhi_raises=True)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


def test_null_rhi_target_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(None)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


def test_no_batch_path_consumes_tiled_batch():
    # Tiled take succeeds then is drained (no tiled source); the raster take
    # fails -> "no-batch". The drained tiled batch must not be abandoned.
    rhi = _FakeRhi(fail_calls=(2,))
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, tiled_source=None)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


def test_tiled_source_none_path_consumes_both_batches():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, tiled_source=None)
    _drive(widget, cmd)
    # 1 tiled (drained) + 1 raster (beginPass) = 2 taken, 2 consumed.
    assert len(rhi.handed) == 2
    assert _outstanding(rhi, cmd) == 0


def test_stage_failed_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, shell=_FakeShell(fail_stage=True), tiled_source=None)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


def test_raster_no_frame_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, frame=None, tiled_source=None)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


def test_upload_failed_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(
        rhi, shell=_FakeShell(fail_upload=True), tiled_source=None
    )
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


def test_begin_failed_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd(fail_begin=True)
    widget = _FakeWidget(rhi, tiled_source=None)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


# ---------------------------------------------------------------------------
# tiled-source-present paths (engine submits internally)
# ---------------------------------------------------------------------------


def test_tiled_covered_handover_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    renderer = _FakeRenderer(covered=True)
    widget = _FakeWidget(
        rhi,
        tiled_source=("item", object()),
        renderer=renderer,
        tile_level_ready=True,
    )
    _drive(widget, cmd)
    assert renderer.render_calls == 1
    # Cover handover returns early: exactly one batch, consumed by the engine.
    assert len(rhi.handed) == 1
    assert _outstanding(rhi, cmd) == 0


def test_tiled_holding_falls_through_and_consumes_batches():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    renderer = _FakeRenderer(covered=False, drawn=True, resident=1)
    widget = _FakeWidget(
        rhi,
        tiled_source=("item", object()),
        renderer=renderer,
        tile_level_ready=False,
    )
    _drive(widget, cmd)
    assert renderer.render_calls == 1
    # Engine consumed the tiled batch; the raster path then consumes its own.
    assert len(rhi.handed) == 2
    assert _outstanding(rhi, cmd) == 0


def test_tiled_no_renderer_path_consumes_batch():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, tiled_source=("item", object()), renderer=None)
    _drive(widget, cmd)
    assert _outstanding(rhi, cmd) == 0


# ---------------------------------------------------------------------------
# pool-exhaustion premise: many frames, never a single outstanding batch
# ---------------------------------------------------------------------------


def test_two_hundred_skip_frames_never_leak_a_batch():
    """Fast switching == many skip frames in a row.

    Reuse one rhi + command buffer so the accounting models QRhi's shared
    pool: after ~200 skip-path frames ``outstanding`` must still be 0, not
    2-per-frame. This is the no-GPU falsifier of the 64-batch-exhaustion
    premise behind the SIGSEGV.
    """
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, shell=_FakeShell(fail_stage=True), tiled_source=None)
    for _ in range(200):
        _drive(widget, cmd)
        assert _outstanding(rhi, cmd) == 0


# ---------------------------------------------------------------------------
# outstanding-batch counter: fail-open, gate-only logging
# ---------------------------------------------------------------------------


def test_counter_balances_to_zero_across_frames():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, shell=_FakeShell(fail_stage=True), tiled_source=None)
    for _ in range(10):
        _drive(widget, cmd)
        assert getattr(widget, "_ql_rhi_batches_outstanding", 0) == 0


def test_counter_log_silent_by_default(monkeypatch, caplog):
    import logging

    monkeypatch.delenv("IMGSLI_QL_COVER_DEBUG", raising=False)
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, tiled_source=None)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        _drive(widget, cmd)
    assert not [r for r in caplog.records if "rhi batches outstanding" in r.getMessage()]


def test_counter_log_fires_with_cover_flag(monkeypatch, caplog):
    import logging

    monkeypatch.setenv("IMGSLI_QL_COVER_DEBUG", "1")
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, tiled_source=None)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        _drive(widget, cmd)
    assert [r for r in caplog.records if "rhi batches outstanding" in r.getMessage()]


def test_alternating_handover_and_skip_frames_never_leak():
    rhi = _FakeRhi()
    cmd = _FakeCmd()
    widget = _FakeWidget(rhi, shell=_FakeShell(fail_stage=True), tiled_source=None)
    renderer = _FakeRenderer(covered=True)
    tiled_widget = _FakeWidget(
        rhi,
        tiled_source=("item", object()),
        renderer=renderer,
        tile_level_ready=True,
    )
    for _ in range(100):
        _drive(widget, cmd)
        _drive(tiled_widget, cmd)
        assert _outstanding(rhi, cmd) == 0
