"""XDG thumbnailer: document-framed preview from .imgsli zips."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import zipfile
from pathlib import Path


def _load_thumbnailer():
    path = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "linux"
        / "bin"
        / "improve-imgsli-thumbnailer"
    )
    assert path.is_file(), path
    spec = importlib.util.spec_from_file_location(
        "imgsli_thumbnailer",
        path,
        loader=importlib.machinery.SourceFileLoader("imgsli_thumbnailer", str(path)),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_thumbnailer_writes_png_from_preview_member(tmp_path: Path, monkeypatch):
    mod = _load_thumbnailer()
    mark = tmp_path / "mark.png"
    from PIL import Image

    Image.new("RGBA", (32, 32), color=(200, 80, 80, 255)).save(mark, format="PNG")
    monkeypatch.setattr(mod, "_mark_candidates", lambda: [mark])

    project = tmp_path / "demo.imgsli"
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), color=(20, 40, 60)).save(buf, format="PNG")
    png = buf.getvalue()

    with zipfile.ZipFile(project, "w") as zf:
        zf.writestr("project.json", "{}")
        zf.writestr("preview.png", png)

    out = tmp_path / "thumb.png"
    assert mod.main(["thumb", str(project), str(out), "128"]) == 0
    assert out.is_file() and out.stat().st_size > 0
    thumb = Image.open(out)
    assert thumb.size[0] == 128 and thumb.size[1] == 128


def test_thumbnailer_accepts_legacy_preview_jpg(tmp_path: Path, monkeypatch):
    mod = _load_thumbnailer()
    monkeypatch.setattr(mod, "_mark_candidates", lambda: [])
    project = tmp_path / "legacy.imgsli"
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color=(20, 40, 60)).save(buf, format="JPEG")
    jpeg = buf.getvalue()

    with zipfile.ZipFile(project, "w") as zf:
        zf.writestr("project.json", "{}")
        zf.writestr("preview.jpg", jpeg)

    out = tmp_path / "thumb.png"
    assert mod.main(["thumb", str(project), str(out), "64"]) == 0
    assert out.is_file() and out.stat().st_size > 0


def test_thumbnailer_missing_preview_exits_nonzero(tmp_path: Path):
    mod = _load_thumbnailer()
    project = tmp_path / "empty.imgsli"
    with zipfile.ZipFile(project, "w") as zf:
        zf.writestr("project.json", "{}")
    out = tmp_path / "thumb.png"
    assert mod.main(["thumb", str(project), str(out), "64"]) == 1
    assert not out.exists()
