"""IMGSLI_MC_FIRST_FRAME_DEBUG gating + readiness snapshot for the
multi_compare first-frame timeline (tabs/multi_compare/first_frame_debug.py).
"""

from __future__ import annotations

from types import SimpleNamespace


def test_debug_is_noop_when_disabled(monkeypatch, caplog):
    from tabs.multi_compare import first_frame_debug as ff

    monkeypatch.delenv("IMGSLI_MC_FIRST_FRAME_DEBUG", raising=False)
    widget = SimpleNamespace()
    ff.mc_first_frame_debug(widget, "created")
    assert ff.mc_first_frame_debug_enabled() is False
    assert not caplog.records


def test_debug_logs_timeline_when_enabled(monkeypatch, caplog):
    import logging

    from tabs.multi_compare import first_frame_debug as ff

    monkeypatch.setenv("IMGSLI_MC_FIRST_FRAME_DEBUG", "1")
    caplog.set_level(logging.INFO, logger="ImproveImgSLI")
    widget = SimpleNamespace()
    ff.mc_first_frame_debug(widget, "created")
    ff.mc_first_frame_debug(widget, "present #1")
    assert len(caplog.records) == 2
    assert all("[mc-first-frame]" in r.getMessage() for r in caplog.records)
    assert "+" in caplog.records[1].getMessage()


def test_readiness_repr_counts_textures_and_composition():
    from tabs.multi_compare import first_frame_debug as ff

    tile_service = SimpleNamespace(
        _resident={1: {(0, 0), (0, 1)}, 2: {(1, 1)}},
        resident_tiles=lambda key: tile_service._resident.get(key, set()),
    )
    widget = SimpleNamespace(
        _renderer=SimpleNamespace(tile_service=tile_service),
        _active_composition=object(),
    )
    text = ff.mc_first_frame_readiness_repr(widget)
    assert "textures_resident=3" in text
    assert "composition=yes" in text


def test_readiness_repr_tolerates_missing_renderer():
    from tabs.multi_compare import first_frame_debug as ff

    widget = SimpleNamespace(_renderer=None, _active_composition=None)
    text = ff.mc_first_frame_readiness_repr(widget)
    assert "textures_resident=0" in text
    assert "composition=no" in text


def test_surface_repr_tolerates_missing_qt_api():
    from tabs.multi_compare import first_frame_debug as ff

    widget = SimpleNamespace()
    text = ff.mc_first_frame_surface_repr(widget)
    assert "visible=" in text
    assert "exposed=" in text
    assert "grab_opaque=" in text