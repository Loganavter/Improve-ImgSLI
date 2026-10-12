"""VLM upload downscale: configurable max edge (0 = original bytes)."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from tabs.image_gallery.services import vlm


@pytest.fixture
def big_png(tmp_path: Path) -> Path:
    path = tmp_path / "big.png"
    Image.new("RGB", (3000, 2000), (10, 20, 30)).save(path)
    return path


@pytest.fixture(autouse=True)
def _restore_max_edge(monkeypatch):
    monkeypatch.setattr(vlm, "_vlm_max_edge_px", vlm.DEFAULT_VLM_MAX_EDGE_PX)


def test_set_and_get_max_edge_round_trip():
    vlm.set_vlm_max_edge(512)
    assert vlm.get_vlm_max_edge() == 512
    vlm.set_vlm_max_edge(0)
    assert vlm.get_vlm_max_edge() == 0
    vlm.set_vlm_max_edge(-7)
    assert vlm.get_vlm_max_edge() == 0


def test_encode_image_honors_configured_max_edge(big_png: Path):
    vlm.set_vlm_max_edge(512)
    _mime, data = vlm._encode_image(big_png)
    with Image.open(io.BytesIO(base64.b64decode(data))) as im:
        assert max(im.size) == 512


def test_encode_image_zero_sends_original_bytes(big_png: Path):
    vlm.set_vlm_max_edge(0)
    _mime, data = vlm._encode_image(big_png)
    assert base64.b64decode(data) == big_png.read_bytes()
