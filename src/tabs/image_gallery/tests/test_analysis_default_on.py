"""P9a: the analysis engine is ON by default, and the env flag is its kill-switch.

Three facts, each one assertable on its own:

1. **No env var ⇒ on.** ``analysis_bridge.engine_enabled()`` is True and a proxy
   batch carries the ``"analysis"`` records — the engine needs no opt-in.
2. **An explicit off value ⇒ off.** ``0``/``false``/``no``/``off``
   (case-insensitive, stripped) make the reader False and the batch is the
   legacy dict with no ``"analysis"`` key — the legacy stages are still there
   and still correct, so the switch is a real switch, not a shape change.
3. **Anything else ⇒ on, including ``1``.** Back-compat for the flag-ON era and
   a fail-safe for typos/empty values: a misspelling must not silently
   resurrect the legacy path.

Every test here states its own mode; there is deliberately NO autouse default in
``conftest.py`` — a suite-wide default would make "which mode did this test
mean?" invisible at the call site again, which is the exact ambiguity P9a
removes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tabs.image_gallery.services import artifacts
from tabs.image_gallery.services.analysis_bridge import ENGINE_FLAG, engine_enabled
from tabs.image_gallery.services.proxy import clear_proxy_cache, proxy_for, run_proxy_stages_sync

#: The only keys a kill-switched (legacy) entry may carry — the pre-engine shape.
LEGACY_ENTRY_KEYS = {"artifacts", "artifact_maps", "camera", "fidelity"}


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


def _assert_legacy_entry(entry, item, source) -> None:
    """No records, the legacy shape, and the legacy values (never an empty dict)."""
    assert "analysis" not in entry, (
        "the kill-switch must keep the pre-engine entry: no 'analysis' key"
    )
    assert set(entry) <= LEGACY_ENTRY_KEYS, sorted(entry)
    assert len(entry["artifacts"]) == 7
    assert "camera" in entry and "fidelity" in entry
    # The numbers come from the legacy stages over the same shared proxies.
    proxy = proxy_for(item)
    source_proxy = proxy_for(source)
    assert entry["artifacts"] == artifacts.analyze_images(
        proxy.image, source_proxy.image
    )


def test_engine_is_on_with_no_env_var(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """The default: no opt-in, the batch carries per-axis records."""
    monkeypatch.delenv(ENGINE_FLAG, raising=False)
    item, source = _write_pair(tmp_path)

    assert engine_enabled() is True

    entry = _run(item, source)

    assert "analysis" in entry
    assert entry["analysis"], "the default-on batch must carry records, not None"
    assert all(record.producer == "local" for record in entry["analysis"])
    # Additive: the stage dicts the reader outside the engine still needs.
    assert {"artifacts", "fidelity", "camera"} <= set(entry)


@pytest.mark.parametrize(
    "value", ["0", "false", "off", "no", "0 ", " OFF ", "No", "False"]
)
def test_off_values_disable_the_engine(
    tmp_path, monkeypatch: pytest.MonkeyPatch, value: str
):
    """Every documented off value is a kill-switch: legacy entry, no records."""
    monkeypatch.setenv(ENGINE_FLAG, value)
    item, source = _write_pair(tmp_path)

    assert engine_enabled() is False

    _assert_legacy_entry(_run(item, source), item, source)


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "", "  ", "garbage"])
def test_any_other_value_keeps_the_engine_on(
    tmp_path, monkeypatch: pytest.MonkeyPatch, value: str
):
    """Back-compat with ``=1`` and fail-safe for empty/garbage values."""
    monkeypatch.setenv(ENGINE_FLAG, value)
    item, source = _write_pair(tmp_path)

    assert engine_enabled() is True

    assert "analysis" in _run(item, source)


def test_back_compat_flag_one_still_records(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """``=1`` (the pre-P9a opt-in) keeps working byte for byte."""
    monkeypatch.setenv(ENGINE_FLAG, "1")
    item, source = _write_pair(tmp_path)

    entry = _run(item, source)

    assert "analysis" in entry and entry["analysis"]
    assert {"artifacts", "fidelity", "camera"} <= set(entry)
