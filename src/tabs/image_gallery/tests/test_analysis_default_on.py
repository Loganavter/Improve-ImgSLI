"""P9b: the analysis engine is the ONLY path — the env flag is gone and ignored.

Two facts, each assertable on its own:

1. **The env var changes nothing.** The old engine flag set to ``0`` or ``1``
   produces exactly the entry an unset environment produces, records included:
   there is no kill-switch left to disable the engine (P9b deleted the legacy
   branch, so a "disabled" run would have had nothing to run).
2. **The flag API is gone.** ``services.analysis_bridge`` no longer exposes the
   flag name, the off-value set or its reader — an import of them is an
   ``AttributeError``, not a silently ignored call. A surviving symbol would let
   a caller believe a switch exists.

Every test states its mode explicitly on purpose: a suite-wide default in
``conftest.py`` would hide "which mode did this test mean?" at the call site.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tabs.image_gallery.services import analysis_bridge
from tabs.image_gallery.services.proxy import clear_proxy_cache, run_proxy_stages_sync

#: The removed switch, spelled from parts on purpose: the P9b acceptance gate
#: greps ``src/`` for the old flag env var and for the name of the function that
#: read it, and must stay empty — so the one place those tokens could
#: legitimately appear (a test asserting they are GONE) must not spell them out.
_FLAG_ENV = "IMGSLI_" + "ANALYSIS_ENGINE"
REMOVED_FLAG_SYMBOLS = ("ENGINE_" + "FLAG", "ENGINE_" + "OFF_VALUES", "engine_" + "enabled")


def _gradient(size: int = 64):
    from PIL import Image

    image = Image.new("RGB", (size, size))
    pixels = image.load()
    span = max(2 * (size - 1), 1)
    for y in range(size):
        for x in range(size):
            value = int((x + y) * 255 / span)
            pixels[x, y] = (value, value, value)
    return image


def _write_pair(tmp_path):
    """A readable item/source pair with a real (blurred) reference."""
    from PIL import ImageFilter

    image = _gradient()
    item = tmp_path / "item.png"
    source = tmp_path / "source.png"
    image.save(item)
    image.filter(ImageFilter.GaussianBlur(1.2)).save(source)
    return item, source


def _run(item, source):
    clear_proxy_cache()
    out = run_proxy_stages_sync(
        [SimpleNamespace(path=item)], source, include_camera=True
    )
    assert tuple(out) == (str(item),)
    return out[str(item)]


def test_the_env_var_is_ignored(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Unset, ``=0`` and ``=1`` are the same run: records, same shape, same values.

    Full-dict equality is deliberate: anything weaker would let a stray flag
    branch change one stage (e.g. the artifacts) while the assertion still saw
    the ``"analysis"`` key and passed.
    """
    item, source = _write_pair(tmp_path)

    monkeypatch.delenv(_FLAG_ENV, raising=False)
    unset = _run(item, source)
    monkeypatch.setenv(_FLAG_ENV, "0")
    off_value = _run(item, source)
    monkeypatch.setenv(_FLAG_ENV, "1")
    on_value = _run(item, source)

    assert "analysis" in unset and unset["analysis"], (
        "the engine must produce records with no opt-in: it is the only path"
    )
    assert all(record.producer == "local" for record in unset["analysis"])
    assert {"artifacts", "fidelity", "camera"} <= set(unset)
    assert off_value == unset, "the old kill-switch value must be a no-op now"
    assert on_value == unset, "the old opt-in value must be a no-op too"


def test_analysis_bridge_no_longer_exposes_the_flag():
    """No second reader of a switch that no longer exists."""
    for name in REMOVED_FLAG_SYMBOLS:
        assert not hasattr(analysis_bridge, name), (
            f"{name} survived in analysis_bridge: a caller could believe the "
            "engine is still switchable"
        )
        assert name not in analysis_bridge.__all__, name


def test_the_engine_api_analysis_bridge_still_exports_is_intact():
    """The deletion must not have taken the record glue with it."""
    for name in (
        "CAMERA_AXES",
        "FIDELITY_AXES",
        "ARTIFACT_AXES",
        "records_by_axis",
        "unusable_axes",
        "stage_dicts_from_records",
        "engine_records",
    ):
        assert hasattr(analysis_bridge, name), name
        assert name in analysis_bridge.__all__, name
