"""Gallery truthfulness: confidence gate, unmeasured state, rank invariant.

Regression for task-fix-gallery-truth-2026-09-20:
- ambiguous / low-confidence VLM output raises instead of crowning A
- quick-look shows 'not measured' instead of fabricated constants
- make_best / keep_best_of_series agree on rank == crown_rank == triage_rank == 1
- API payloads are downscaled/size-capped; 5xx is AiServerError with backoff
"""

from __future__ import annotations

import base64
import io
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services import ai_client, vlm
from tabs.image_gallery.services.ai_client import AiResponseError
from tabs.image_gallery.use_cases import triage as triage_uc


def _raw_tie_break(body: str) -> dict:
    return {"choices": [{"message": {"content": body}}]}


def test_tie_break_ambiguous_no_winner_raises():
    with pytest.raises(AiResponseError):
        vlm.parse_tie_break_response(
            _raw_tie_break("Both look similar.\nCONFIDENCE: 0.9\nREASON: close"),
            model="m",
            path_a=Path("/a.png"),
            path_b=Path("/b.png"),
        )


def test_tie_break_low_confidence_raises():
    with pytest.raises(AiResponseError):
        vlm.parse_tie_break_response(
            _raw_tie_break("WINNER: A\nCONFIDENCE: 0.2\nREASON: guess"),
            model="m",
            path_a=Path("/a.png"),
            path_b=Path("/b.png"),
        )


def test_tie_break_missing_confidence_raises():
    with pytest.raises(AiResponseError):
        vlm.parse_tie_break_response(
            _raw_tie_break("WINNER: B\nREASON: sharper"),
            model="m",
            path_a=Path("/a.png"),
            path_b=Path("/b.png"),
        )


def test_tie_break_decisive_parses_and_gate_passes():
    res = vlm.parse_tie_break_response(
        _raw_tie_break("WINNER: B\nCONFIDENCE: 0.85\nREASON: sharper edges"),
        model="m",
        path_a=Path("/a.png"),
        path_b=Path("/b.png"),
    )
    assert res.winner_path.endswith("b.png")
    assert vlm.is_decisive_tie_break(res) is True


def test_encode_image_downscales_big_input(tmp_path: Path):
    from PIL import Image

    big = tmp_path / "big.png"
    Image.new("RGB", (3000, 2000), (10, 20, 30)).save(big)
    mime, data = vlm._encode_image(big)
    raw = base64.b64decode(data)
    with Image.open(io.BytesIO(raw)) as im:
        assert max(im.size) <= vlm.VLM_MAX_EDGE_PX


def test_encode_image_fail_open_for_non_image(tmp_path: Path):
    # Not decodable by PIL -> original bytes still sent, never an exception.
    p = tmp_path / "note.png"
    p.write_bytes(b"not-an-image-at-all")
    mime, data = vlm._encode_image(p)
    assert base64.b64decode(data) == b"not-an-image-at-all"


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    hdrs = Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url="https://example.test/v1/chat/completions",
        code=code,
        msg="error",
        hdrs=hdrs,  # type: ignore[arg-type]
        fp=io.BytesIO(b"{}"),
    )


class _FakeResponse:
    def __init__(self, payload: bytes = b"{}"):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._payload


def test_500_is_server_error_not_plain_network(monkeypatch):
    monkeypatch.setattr(ai_client.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(_http_error(500)))
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(ai_client.AiServerError):
        ai_client.call_sync("https://example.test/v1", "key", {})


def test_retry_after_honored_on_429_then_success(monkeypatch):
    calls = {"n": 0}
    slept: list[float] = []

    def fake_urlopen(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, retry_after="7")
        return _FakeResponse()

    monkeypatch.setattr(ai_client.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    out = ai_client.call_sync("https://example.test/v1", "key", {})
    assert out == {}
    assert calls["n"] == 2
    assert slept == [7.0]


class _OverlayStub:
    def __init__(self):
        from PySide6.QtWidgets import QWidget

        self._metric_rows: list = []
        self._metrics_host = QWidget()
        from PySide6.QtWidgets import QVBoxLayout

        self._metrics_layout = QVBoxLayout(self._metrics_host)
        self._series_items: list = []
        self._current_idx = 0


def test_quick_look_unmeasured_not_fabricated(qtbot):
    from tabs.image_gallery.ui.quick_look import metrics as m

    item = GalleryItem(path=Path("/g/x.jpg"), mtime_ns=1, metrics={})
    ov = _OverlayStub()
    qtbot.addWidget(ov._metrics_host)
    m.rebuild_metrics(ov, item, True, "FIDELITY")
    texts: list[str] = []
    for row in ov._metric_rows:
        for lab in row.findChildren(object):
            try:
                t = lab.text()
            except Exception:
                continue
            if isinstance(t, str) and t:
                texts.append(t)
    blob = " ".join(texts)
    assert "not measured" in blob
    for fabricated in ("0.94", "+18%", "1.8"):
        assert fabricated not in blob


def _owner_with_series(items: list[GalleryItem]):
    class _State:
        def __init__(self):
            self.items = items
            self.series = [items]

    class _Owner:
        def __init__(self):
            self.state = _State()
            # _series_of reads owner._triage_series (not state.series).
            self._triage_series = [items]

    owner = _Owner()
    for it in items:
        it.series_id = "s1"
        it.provenance_series_id = None
    return owner


def test_rank_one_consistent_across_helpers(tmp_path: Path):
    a = GalleryItem(path=tmp_path / "a.jpg", mtime_ns=1)
    b = GalleryItem(path=tmp_path / "b.jpg", mtime_ns=2)
    owner = _owner_with_series([a, b])

    assert triage_uc.make_best(owner, b.path) is True
    assert (b.rank, b.crown_rank, b.triage_rank) == (1, 1, 1)

    a2 = GalleryItem(path=tmp_path / "a.jpg", mtime_ns=1)
    b2 = GalleryItem(path=tmp_path / "b.jpg", mtime_ns=2)
    owner2 = _owner_with_series([a2, b2])
    triage_uc.keep_best_of_series(owner2)
    kept = next(it for it in (a2, b2) if it.is_best)
    assert (kept.rank, kept.crown_rank, kept.triage_rank) == (1, 1, 1)
    # Winner invariant: exactly one rank-1 across all three fields.
    for field in ("rank", "crown_rank", "triage_rank"):
        assert sum(1 for it in (a2, b2) if getattr(it, field) == 1) == 1
