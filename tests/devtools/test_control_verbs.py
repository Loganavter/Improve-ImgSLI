"""Control-surface verbs: ``open_file`` / ``ui_press`` / ``open_properties`` /
``set_setting`` (app side) and the four MCP tools that carry them.

Falsification (written to be RED against a naive stub):

* ``open_file`` — a stub that takes any path fails the unknown-extension and
  missing-file cases; a router that ignores the caller policy fails the
  "image goes to the open Image Compare, else the gallery" pair (the tabs are
  listed gallery-first, so tree order alone would answer ``image_gallery``); a
  router that claims a video loaded fails the refusal test (the app has no
  video intake — ``tabs/image_gallery/services/video_compare_hooks.py``);
* ``ui_press`` — every press assertion reads the **widget's own**
  ``pressed``/``released`` signals, so a handler that only returns a dict never
  passes; ``release=false`` must leave ``released`` un-fired (a press+release
  stub fails) and the later release must reach the *same* widget;
* ``open_properties`` — the dialog seam is monkeypatched: it must be called
  exactly once with the resolved path, and never for a missing file;
* ``set_setting`` — the whitelist, the dedicated-verb refusals, the value
  vocabulary and the reported ``previous`` value; the live path is proven
  against a real ``Store`` + ``Dispatcher`` (the store actually changes);
* MCP — the four catalog entries validate, and each backend method proxies to
  the transport (scripted ``LiveClient.call`` stub) with the documented wire
  params, or refuses honestly without a live instance;
* ``press_keys`` *vocabulary* — the two separator characters are also real
  keys (``Ctrl+,``, ``+``), so ``comma`` / ``plus`` / the escaped ``,`` and
  ``+`` must resolve to those Qt keys while a bare ``,`` / ``+`` stays a
  separator.

Runs offscreen only — no Xvfb, no app launch (the supervisor runs the live
proof).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from core.actions.types import ActionDescriptor
from core.control import discovery as discovery_module
from core.control import elements
from core.control import handlers as handlers_module
from core.control.drop_routing import media_kind, open_file_into
from core.control.handlers import ControlHandlers, MethodError
from core.store import Store
from ui.actions.registry import ActionRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from app import catalog  # noqa: E402
from app.backend import AppBackend, ToolError  # noqa: E402
from app.live import LiveBackend  # noqa: E402

#: The four verbs this module owns (app METHODS names == MCP tool names).
VERBS = ("open_file", "open_properties", "set_setting", "ui_press")


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication, seconds: float) -> None:
    import time

    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _registry(*actions: ActionDescriptor) -> ActionRegistry:
    registry = ActionRegistry()
    for action in actions:
        registry.register(action)
    return registry


def _handlers(window, registry, tmp_path, *, app=None) -> ControlHandlers:
    return ControlHandlers(
        window=window,
        app=app,
        artifacts_dir=tmp_path / "artifacts",
        log_ring=None,
        registry_provider=lambda: registry,
    )


def _store_window(store=None) -> types.SimpleNamespace:
    return types.SimpleNamespace(store=store if store is not None else Store())


def _find(payload: dict, **match) -> dict:
    for row in payload["elements"]:
        if all(row.get(key) == value for key, value in match.items()):
            return row
    raise AssertionError(f"no element matching {match!r} in {payload['count']} rows")


class _FileTab:
    """Handler-level tab stand-in: takes the suffixes it was built to take."""

    def __init__(self, *suffixes: str, drop_ok: bool = True, opened: bool = True) -> None:
        self.suffixes = tuple(suffixes)
        self.drop_ok = drop_ok
        self.opened = opened
        self.dropped: list[list[Path]] = []
        self.offered: list[list[Path]] = []

    def accepts_drop(self, paths):  # noqa: N802 - TabContract name
        paths = list(paths)
        self.offered.append(paths)
        return bool(paths) and all(p.suffix.lower() in self.suffixes for p in paths)

    def handle_drop(self, paths, hint=None):  # noqa: N802 - TabContract name
        if not self.opened:
            return False  # registered but its page is not open yet
        self.dropped.append(list(paths))
        return self.drop_ok


# -- app side: open_file ------------------------------------------------------


def _open_file_handlers(monkeypatch, handlers, tabs, *, kinds, active=None):
    monkeypatch.setattr(handlers, "_tabs", lambda: list(tabs))
    monkeypatch.setattr(handlers, "_tab_kinds", lambda: list(kinds))
    monkeypatch.setattr(handlers, "_active_kind", lambda: active)
    return handlers


def test_open_file_routes_an_image_to_the_active_tab(tmp_path, monkeypatch):
    """The active tab wins when it accepts — not tree order (gallery is first)."""
    image = tmp_path / "shot.png"
    image.write_bytes(b"x")
    gallery, compare = _FileTab(".png"), _FileTab(".png")
    handlers = _open_file_handlers(
        monkeypatch,
        _handlers(_store_window(), _registry(), tmp_path),
        [("image_gallery", gallery), ("image_compare", compare)],
        kinds=["image_compare", "image_gallery"],
        active="image_compare",
    )

    result = handlers.open_file({"path": str(image)})

    assert result == {
        "opened": True,
        "path": str(image),
        "tab": "image_compare",
        "count": 1,
    }
    assert compare.dropped == [[image]], "Image Compare's own drop hook took it"
    assert gallery.dropped == [], "the gallery was never offered the file"


def test_open_file_follows_acceptance_not_tab_order(tmp_path, monkeypatch):
    """A tab that cannot take the file is skipped, never forced."""
    image = tmp_path / "shot.jpg"
    image.write_bytes(b"x")
    compare, gallery = _FileTab(".png"), _FileTab(".jpg")
    opened: list[str] = []
    handlers = _open_file_handlers(
        monkeypatch,
        _handlers(_store_window(), _registry(), tmp_path),
        [("image_compare", compare), ("image_gallery", gallery)],
        kinds=["image_compare", "image_gallery"],
    )
    monkeypatch.setattr(handlers, "_run_action_id", lambda aid: opened.append(aid))

    result = handlers.open_file({"path": str(image)})

    assert result["tab"] == "image_gallery"
    assert gallery.dropped == [[image]]
    assert compare.dropped == [] and compare.offered, "it was asked and declined"
    assert opened == [], "nothing had to be opened"


def test_open_file_opens_a_closed_candidate_once(tmp_path, monkeypatch):
    """A registered tab whose page is closed is opened through its own action."""
    image = tmp_path / "shot.png"
    image.write_bytes(b"x")
    compare = _FileTab(".png", opened=False)
    actions: list[str] = []
    handlers = _open_file_handlers(
        monkeypatch,
        _handlers(_store_window(), _registry(), tmp_path),
        [("image_compare", compare)],
        kinds=["image_compare"],
    )

    def _run(action_id: str) -> bool:
        actions.append(action_id)
        compare.opened = True
        return True

    monkeypatch.setattr(handlers, "_run_action_id", _run)

    result = handlers.open_file({"path": str(image)})

    assert actions == ["workspace.new_image_compare"]
    assert result["tab"] == "image_compare"
    assert compare.dropped == [[image]]


def test_open_file_forced_tab_wins_over_the_active_one(tmp_path, monkeypatch):
    image = tmp_path / "shot.png"
    image.write_bytes(b"x")
    gallery, compare = _FileTab(".png"), _FileTab(".png")
    handlers = _open_file_handlers(
        monkeypatch,
        _handlers(_store_window(), _registry(), tmp_path),
        [("image_compare", compare), ("image_gallery", gallery)],
        kinds=["image_compare", "image_gallery"],
        active="image_compare",
    )

    result = handlers.open_file({"path": str(image), "tab": "image_gallery"})

    assert result["tab"] == "image_gallery"
    assert gallery.dropped == [[image]] and compare.dropped == []


def test_open_file_rejects_an_unknown_forced_tab(tmp_path, monkeypatch):
    image = tmp_path / "shot.png"
    image.write_bytes(b"x")
    handlers = _open_file_handlers(
        monkeypatch,
        _handlers(_store_window(), _registry(), tmp_path),
        [],
        kinds=["image_compare", "image_gallery"],
    )

    with pytest.raises(MethodError) as exc:
        handlers.open_file({"path": str(image), "tab": "wibble"})

    assert "unknown tab kind 'wibble'" in exc.value.message
    assert "image_compare" in exc.value.message, "the known kinds are listed"


def test_open_file_rejects_an_unknown_extension(tmp_path, monkeypatch):
    text = tmp_path / "notes.txt"
    text.write_text("x", encoding="utf-8")
    handlers = _open_file_handlers(
        monkeypatch,
        _handlers(_store_window(), _registry(), tmp_path),
        [],
        kinds=["image_gallery"],
    )

    with pytest.raises(MethodError) as exc:
        handlers.open_file({"path": str(text)})

    assert "unsupported file type" in exc.value.message
    assert "pass an image or a video file" in (exc.value.hint or "")


def test_open_file_rejects_a_missing_file_by_name(tmp_path, monkeypatch):
    missing = tmp_path / "gone.png"
    handlers = _open_file_handlers(
        monkeypatch,
        _handlers(_store_window(), _registry(), tmp_path),
        [],
        kinds=["image_gallery"],
    )

    with pytest.raises(MethodError) as exc:
        handlers.open_file({"path": str(missing)})

    assert str(missing) in exc.value.message
    assert "not an existing file" in exc.value.message


def test_open_file_refuses_a_video_by_name(tmp_path, monkeypatch):
    """No tab in this app loads a video file — never claim it loaded."""
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    compare = _FileTab(".png")  # a real Image Compare takes images only
    actions: list[str] = []
    handlers = _open_file_handlers(
        monkeypatch,
        _handlers(_store_window(), _registry(), tmp_path),
        [("image_compare", compare)],
        kinds=["image_compare", "image_gallery"],
    )
    monkeypatch.setattr(handlers, "_run_action_id", lambda aid: actions.append(aid))

    with pytest.raises(MethodError) as exc:
        handlers.open_file({"path": str(clip)})

    assert "no tab accepted" in exc.value.message
    assert "video-file intake" in (exc.value.hint or "")
    assert compare.dropped == []
    assert actions == [], "a video must not open a tab it cannot load into"


def test_active_kind_reads_the_live_session(tmp_path):
    session = types.SimpleNamespace(session_type="image_compare")
    store = types.SimpleNamespace(get_active_workspace_session=lambda: session)
    handlers = _handlers(_store_window(store), _registry(), tmp_path)
    assert handlers._active_kind() == "image_compare"

    bare = _handlers(_store_window(types.SimpleNamespace()), _registry(), tmp_path)
    assert bare._active_kind() is None, "a store with no session getter is no guess"


def test_media_kind_classifies_images_videos_and_everything_else():
    assert media_kind(Path("/a/shot.JXL")) == "image"
    assert media_kind(Path("/a/clip.MP4")) == "video"
    assert media_kind(Path("/a/notes.txt")) == ""


def test_open_file_into_takes_the_first_accepting_candidate():
    """The pure router: acceptance decides, not the tab list order."""
    clip = Path("/videos/clip.mp4")
    fallback = _FileTab(".mp4")
    preferred = _FileTab(".mp4")
    tabs = {"live": [("image_gallery", fallback), ("image_compare", preferred)]}
    routed = open_file_into(
        clip,
        wanted=None,
        candidates=["image_compare", "image_gallery"],
        tabs=lambda: list(tabs["live"]),
        kinds=["image_compare", "image_gallery"],
        run_action=lambda _aid: None,
    )
    assert routed == {"opened": True, "path": str(clip), "tab": "image_compare", "count": 1}
    assert preferred.dropped == [[clip]] and fallback.dropped == []


def test_open_file_into_raises_when_no_candidate_accepts():
    text = Path("/notes.txt")
    tab = _FileTab(".png")
    with pytest.raises(ValueError) as exc:
        open_file_into(
            text,
            wanted=None,
            candidates=["image_gallery"],
            tabs=lambda: [("image_gallery", tab)],
            kinds=["image_gallery"],
            run_action=lambda _aid: None,
        )
    assert "no tab accepted" in str(exc.value)


# -- app side: ui_press -------------------------------------------------------


def _press_window(app: QApplication, tmp_path, registry=None):
    window = QWidget()
    window.setObjectName("PressWindow")
    layout = QVBoxLayout(window)
    first = QPushButton("first", window)
    second = QPushButton("second", window)
    layout.addWidget(first)
    layout.addWidget(second)
    window.resize(240, 140)
    window.show()
    _pump(app, 0.05)
    handlers = _handlers(window, registry or _registry(), tmp_path, app=app)
    return window, first, second, handlers


def _signals(button: QPushButton) -> list[str]:
    events: list[str] = []
    button.pressed.connect(lambda: events.append("pressed"))
    button.released.connect(lambda: events.append("released"))
    button.clicked.connect(lambda: events.append("clicked"))
    return events


def test_ui_press_release_is_one_press_and_release(tmp_path):
    app = _qapp()
    window, first, _second, handlers = _press_window(app, tmp_path)
    events = _signals(first)
    try:
        row = _find(handlers.ui_elements({}), label="first")
        result = handlers.ui_press({"id": row["id"]})

        assert result == {"pressed": row["id"], "held_ms": 0, "released": True}
        assert events == ["pressed", "released", "clicked"]
    finally:
        window.close()


def test_ui_press_release_false_parks_the_press_and_releases_the_same_widget(
    tmp_path,
):
    app = _qapp()
    window, first, _second, handlers = _press_window(app, tmp_path)
    events = _signals(first)
    try:
        row = _find(handlers.ui_elements({}), label="first")

        parked = handlers.ui_press({"id": row["id"], "release": False})
        assert parked == {"pressed": row["id"], "held_ms": 0, "released": False}
        assert events == ["pressed"], "the button is held down, not released"

        released = handlers.ui_press({"id": row["id"]})
        assert released == {"pressed": row["id"], "held_ms": 0, "released": True}
        assert events == ["pressed", "released", "clicked"]
    finally:
        window.close()


def test_ui_press_releases_a_parked_press_before_pressing_another(tmp_path):
    """A second hold must not leak the first — no stuck HUD."""

    app = _qapp()
    window, first, second, handlers = _press_window(app, tmp_path)
    first_events = _signals(first)
    second_events = _signals(second)
    try:
        first_row = _find(handlers.ui_elements({}), label="first")
        second_row = _find(handlers.ui_elements({}), label="second")

        handlers.ui_press({"id": first_row["id"], "release": False})
        handlers.ui_press({"id": second_row["id"], "release": False})

        assert first_events == ["pressed", "released", "clicked"], (
            "the first hold was released (a released QPushButton also clicks)"
        )
        assert second_events == ["pressed"], "the second press is now held"

        handlers.ui_press({"id": second_row["id"], "release": True})
        assert second_events == ["pressed", "released", "clicked"]
    finally:
        window.close()


def test_ui_press_clamps_hold_ms_and_waits_exactly_that(tmp_path, monkeypatch):
    app = _qapp()
    window, first, _second, handlers = _press_window(app, tmp_path)
    waited: list[int] = []
    monkeypatch.setattr(handlers_module, "_pause", waited.append)
    events = _signals(first)
    try:
        row = _find(handlers.ui_elements({}), label="first")

        assert handlers.ui_press({"id": row["id"], "hold_ms": 99999})["held_ms"] == 5000
        assert waited == [5000], "the wait is the clamped value"

        assert handlers.ui_press({"id": row["id"], "hold_ms": -20})["held_ms"] == 0
        assert waited == [5000, 0], "a zero hold reaches _pause as a no-op"
        assert events.count("clicked") == 2
    finally:
        window.close()


def test_ui_press_of_an_unknown_id_raises(tmp_path, monkeypatch):
    app = _qapp()
    window, first, _second, handlers = _press_window(app, tmp_path)
    monkeypatch.setattr(elements, "RETRY_TIMEOUT_MS", 200, raising=False)
    try:
        row = _find(handlers.ui_elements({}), label="first")
        with pytest.raises(MethodError) as exc:
            handlers.ui_press({"id": row["id"] + "zzz"})
        assert "no element with id" in exc.value.message
        assert "ui_elements" in (exc.value.hint or "")
    finally:
        window.close()


def test_ui_press_forgets_a_park_whose_widget_disappeared(tmp_path, monkeypatch):
    """A stale hold is dropped; releasing a gone id stays a named error."""
    app = _qapp()
    window, first, second, handlers = _press_window(app, tmp_path)
    monkeypatch.setattr(elements, "RETRY_TIMEOUT_MS", 200, raising=False)
    first_events = _signals(first)
    try:
        first_row = _find(handlers.ui_elements({}), label="first")
        second_row = _find(handlers.ui_elements({}), label="second")

        handlers.ui_press({"id": second_row["id"], "release": False})
        second.setParent(None)
        second.deleteLater()
        _pump(app, 0.05)

        with pytest.raises(MethodError):
            handlers.ui_press({"id": second_row["id"]})
        assert handlers._held_press is None, "the stale park was forgotten"

        released = handlers.ui_press({"id": first_row["id"]})
        assert released["released"] is True and released["pressed"] == first_row["id"]
        assert first_events == ["pressed", "released", "clicked"]
    finally:
        window.close()


# -- app side: open_properties ------------------------------------------------


def test_open_properties_uses_the_plugin_dialog_seam_once(tmp_path, monkeypatch):
    image = tmp_path / "pic.png"
    image.write_bytes(b"x")
    window = _store_window()
    handlers = _handlers(window, _registry(), tmp_path)
    calls: list[tuple[Path, object]] = []

    def _fake_dialog(target, parent=None):
        calls.append((target, parent))
        return "ImagePropertiesDialog"

    monkeypatch.setattr(handlers_module, "show_properties_dialog", _fake_dialog)

    result = handlers.open_properties({"path": str(image)})

    assert result == {
        "opened": True,
        "path": str(image),
        "dialog": "ImagePropertiesDialog",
    }
    assert calls == [(image, window)], "the resolved path reached the app's dialog"


def test_open_properties_rejects_a_missing_file_before_any_dialog(
    tmp_path, monkeypatch
):
    missing = tmp_path / "gone.png"
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    calls: list[object] = []
    monkeypatch.setattr(
        handlers_module, "show_properties_dialog", lambda *a, **k: calls.append(a)
    )

    with pytest.raises(MethodError) as exc:
        handlers.open_properties({"path": str(missing)})

    assert str(missing) in exc.value.message
    assert calls == [], "no dialog is built for a path that does not exist"


# -- app side: set_setting ----------------------------------------------------


def test_set_setting_writes_a_whitelisted_scalar_and_reports_previous(
    tmp_path, monkeypatch
):
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    persisted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        handlers, "_persist_setting", lambda key, value: persisted.append((key, value))
    )
    monkeypatch.setattr(handlers, "_read_setting", lambda key: "opengl")
    monkeypatch.setattr(handlers, "_apply_setting", lambda key, value: True)

    result = handlers.set_setting({"key": "rhi_backend", "value": "VULKAN"})

    assert result == {
        "key": "rhi_backend",
        "value": "vulkan",
        "applied": True,
        "persisted": True,
        "previous": "opengl",
    }
    assert persisted == [("rhi_backend", "vulkan")]


def test_set_setting_applies_through_the_live_store_dispatcher(tmp_path, monkeypatch):
    """The real Redux path: the store's own settings slice actually changes."""
    from core.state_management.dispatcher import Dispatcher

    store = Store()
    store.set_dispatcher(Dispatcher(store))
    handlers = _handlers(_store_window(store), _registry(), tmp_path)
    persisted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        handlers, "_persist_setting", lambda key, value: persisted.append((key, value))
    )
    monkeypatch.setattr(handlers, "_read_setting", lambda key: None)

    result = handlers.set_setting({"key": "rhi_backend", "value": "vulkan"})

    assert result["applied"] is True and result["previous"] is None
    assert store.settings.rhi_backend == "vulkan", "dispatched, not store-written"
    assert persisted == [("rhi_backend", "vulkan")]


def test_set_setting_reports_not_applied_without_a_live_dispatcher(tmp_path, monkeypatch):
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    monkeypatch.setattr(handlers, "_persist_setting", lambda key, value: None)
    monkeypatch.setattr(handlers, "_read_setting", lambda key: None)

    result = handlers.set_setting({"key": "rhi_backend", "value": "opengl"})

    assert result["persisted"] is True
    assert result["applied"] is False, "nothing live adopted it — never claimed"


@pytest.mark.parametrize(
    "key,hint_fragment",
    [("theme", "set_theme"), ("language", "set_language")],
)
def test_set_setting_rejects_dedicated_verbs_by_name(tmp_path, key, hint_fragment):
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    persisted: list[tuple[str, str]] = []
    monkeypatch_free = persisted.append
    handlers._persist_setting = lambda k, v: monkeypatch_free((k, v))  # type: ignore[method-assign]

    with pytest.raises(MethodError) as exc:
        handlers.set_setting({"key": key, "value": "whatever"})

    assert "own verb" in exc.value.message
    assert hint_fragment in (exc.value.hint or "")
    assert persisted == [], "a rejected key never reaches the settings write"


def test_set_setting_rejects_an_unknown_key_listing_the_whitelist(tmp_path):
    handlers = _handlers(_store_window(), _registry(), tmp_path)

    with pytest.raises(MethodError) as exc:
        handlers.set_setting({"key": "font_size", "value": "12"})

    assert "not a settable key" in exc.value.message
    assert "rhi_backend" in (exc.value.hint or "")


def test_set_setting_rejects_an_invalid_rhi_backend(tmp_path):
    handlers = _handlers(_store_window(), _registry(), tmp_path)
    persisted: list[tuple[str, str]] = []
    handlers._persist_setting = lambda k, v: persisted.append((k, v))  # type: ignore[method-assign]

    with pytest.raises(MethodError) as exc:
        handlers.set_setting({"key": "rhi_backend", "value": "metal"})

    assert "unknown rhi_backend 'metal'" in exc.value.message
    assert "opengl, vulkan" in (exc.value.hint or "")
    assert persisted == []


# -- dispatch table -----------------------------------------------------------


def test_every_method_has_exactly_one_dispatch_entry():
    from core.control.handlers import METHODS

    assert len(METHODS) == len(set(METHODS)), "no duplicate method names"
    assert set(ControlHandlers._DISPATCH) == set(METHODS)
    assert set(VERBS) <= set(METHODS), "the four verbs are dispatchable"
    assert set(VERBS) <= set(ControlHandlers(window=None).capabilities()["methods"])


# -- MCP catalog --------------------------------------------------------------


def _tools() -> dict[str, dict]:
    return {tool["name"]: tool for tool in catalog.TOOLS}


def test_catalog_declares_the_four_verbs_with_valid_schemas():
    tools = _tools()
    assert set(VERBS) <= set(tools), "one TOOLS entry per verb"

    open_file = tools["open_file"]["inputSchema"]
    assert open_file["required"] == ["path"]
    assert set(open_file["properties"]) == {"path", "tab"}
    assert open_file["additionalProperties"] is False
    assert tools["open_file"]["outputSchema"]["properties"]["tab"]

    ui_press = tools["ui_press"]["inputSchema"]
    assert ui_press["required"] == ["id"]
    hold = ui_press["properties"]["hold_ms"]
    assert hold["maximum"] == 5000 and hold["minimum"] == 0 and hold["default"] == 0
    assert ui_press["properties"]["release"]["default"] is True
    assert tools["ui_press"]["annotations"]["idempotentHint"] is False

    assert tools["open_properties"]["inputSchema"]["required"] == ["path"]

    setting = tools["set_setting"]["inputSchema"]
    assert setting["required"] == ["key", "value"]
    assert "rhi_backend" in setting["properties"]["key"]["description"]
    assert "opengl or vulkan" in setting["properties"]["value"]["description"]
    assert tools["set_setting"]["annotations"]["readOnlyHint"] is False


def test_catalog_press_keys_names_the_inactive_window_refusal():
    """Complaint mcp-c-015: ``ok`` could not tell a dead chord from a lost key.

    The tool description is what a client reads before a sweep, so it must say
    that a key aimed at a window the window system has not activated is refused
    — and what activates it.
    """
    description = _tools()["press_keys"]["description"]

    assert "active window" in description
    assert "windowfocus" in description


def test_catalog_descriptions_stay_in_the_documented_band():
    tools = _tools()
    for name in VERBS:
        description = tools[name]["description"]
        assert 200 <= len(description) <= 400, f"{name}: {len(description)} chars"
        assert tools[name]["outputSchema"]["properties"], name
        for prop, spec in tools[name]["inputSchema"]["properties"].items():
            assert spec.get("description"), f"{name}.{prop} needs a description"


# -- MCP backend: live proxy ---------------------------------------------------


class _ScriptedClient:
    """Transport stub: records each wire call and answers with one payload."""

    def __init__(self, answer: dict) -> None:
        self.answer = dict(answer)
        self.requests: list[tuple[str, dict]] = []

    def alive(self) -> bool:
        return True

    def call(self, method, params=None, *, retry_on_timeout=False):
        self.requests.append((method, dict(params or {})))
        return dict(self.answer)

    def close(self) -> None:
        return None


@pytest.fixture
def no_ambient_instance(monkeypatch, tmp_path):
    """Hermetic discovery: no real app on this machine can leak into a call."""
    monkeypatch.delenv("IMGSLI_MCP_CONTROL_SOCKET", raising=False)
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "no-instance"))


def _backend(tmp_path, *, client=None, settings=None) -> AppBackend:
    calls = settings if settings is not None else []
    return AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        launcher=lambda args: 4242,
        settings_writer=lambda key, value: calls.append((key, value)),
        live_backend=LiveBackend(client=client) if client is not None else LiveBackend(),
    )


@pytest.mark.parametrize(
    "verb,args,answer,expected,wire",
    [
        (
            "open_file",
            {"path": "/img/shot.png"},
            {"opened": True, "path": "/img/shot.png", "tab": "image_compare", "count": 1},
            {
                "opened": True,
                "path": "/img/shot.png",
                "tab": "image_compare",
                "count": 1,
                "source": "live",
            },
            {"path": "/img/shot.png"},
        ),
        (
            "open_file",
            {"path": "/img/shot.png", "tab": "image_gallery"},
            {"opened": True, "path": "/img/shot.png", "tab": "image_gallery", "count": 1},
            {
                "opened": True,
                "path": "/img/shot.png",
                "tab": "image_gallery",
                "count": 1,
                "source": "live",
            },
            {"path": "/img/shot.png", "tab": "image_gallery"},
        ),
        (
            "open_properties",
            {"path": "/img/shot.png"},
            {"opened": True, "path": "/img/shot.png", "dialog": "ImagePropertiesDialog"},
            {
                "opened": True,
                "path": "/img/shot.png",
                "dialog": "ImagePropertiesDialog",
                "source": "live",
            },
            {"path": "/img/shot.png"},
        ),
        (
            "set_setting",
            {"key": "rhi_backend", "value": "vulkan"},
            {
                "key": "rhi_backend",
                "value": "vulkan",
                "applied": True,
                "persisted": True,
                "previous": "opengl",
            },
            {
                "key": "rhi_backend",
                "value": "vulkan",
                "applied": True,
                "persisted": True,
                "previous": "opengl",
                "source": "live",
            },
            {"key": "rhi_backend", "value": "vulkan"},
        ),
        (
            "ui_press",
            {"id": "main.btn", "hold_ms": 120, "release": False},
            {"pressed": "main.btn", "held_ms": 0, "released": False},
            {"pressed": "main.btn", "held_ms": 0, "released": False, "source": "live"},
            {"id": "main.btn", "hold_ms": 120, "release": False},
        ),
        (
            "ui_press",
            {"id": "main.btn"},
            {"pressed": "main.btn", "held_ms": 0, "released": True},
            {"pressed": "main.btn", "held_ms": 0, "released": True, "source": "live"},
            {"id": "main.btn"},
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_backend_proxies_each_verb_to_the_live_client(
    tmp_path, no_ambient_instance, verb, args, answer, expected, wire
):
    client = _ScriptedClient(answer)
    backend = _backend(tmp_path, client=client)

    result = getattr(backend, verb)(**args)

    assert result == expected
    assert client.requests == [(verb, wire)], "one wire call, documented params"


# -- MCP backend: fallback honesty --------------------------------------------


def test_open_file_without_a_live_instance_refuses_after_validating(
    tmp_path, no_ambient_instance
):
    backend = _backend(tmp_path)
    present = tmp_path / "shot.png"
    present.write_bytes(b"x")

    with pytest.raises(ToolError) as missing:
        backend.open_file(path=str(tmp_path / "gone.png"))
    assert "not an existing file" in missing.value.message

    with pytest.raises(ToolError) as refused:
        backend.open_file(path=str(present))
    assert "needs" in refused.value.message or "no live instance" in refused.value.message
    assert "open_file" in (refused.value.hint or "") + refused.value.message


def test_open_properties_without_a_live_instance_refuses_after_validating(
    tmp_path, no_ambient_instance
):
    backend = _backend(tmp_path)
    with pytest.raises(ToolError) as exc:
        backend.open_properties(path=str(tmp_path / "gone.png"))
    assert "not an existing file" in exc.value.message


def test_ui_press_without_a_live_instance_is_a_named_refusal(
    tmp_path, no_ambient_instance
):
    backend = _backend(tmp_path)
    with pytest.raises(ToolError) as exc:
        backend.ui_press(id="main.btn")
    assert "needs a running app" in exc.value.message


def test_set_setting_without_a_live_instance_persists_for_the_next_start(
    tmp_path, no_ambient_instance
):
    written: list[tuple[str, str]] = []
    backend = _backend(tmp_path, settings=written)

    result = backend.set_setting(key="rhi_backend", value="opengl")

    assert result == {
        "key": "rhi_backend",
        "value": "opengl",
        "applied": False,
        "persisted": True,
        "previous": None,
        "source": "fallback",
    }
    assert written == [("rhi_backend", "opengl")]


@pytest.mark.parametrize(
    "key,value,fragment",
    [
        ("theme", "dark", "set_theme"),
        ("language", "ru", "set_language"),
        ("font_size", "12", "not a settable key"),
        ("rhi_backend", "metal", "unknown rhi_backend"),
    ],
)
def test_set_setting_fallback_revalidates_before_writing(
    tmp_path, no_ambient_instance, key, value, fragment
):
    written: list[tuple[str, str]] = []
    backend = _backend(tmp_path, settings=written)

    with pytest.raises(ToolError) as exc:
        backend.set_setting(key=key, value=value)

    text = exc.value.message + " " + (exc.value.hint or "")
    assert fragment in text
    assert written == [], "a rejected key never reaches the settings write"


# -- app side: press_keys key vocabulary ---------------------------------------
#
# Falsification (complaint mcp-c-013: ``press_keys {"keys": "ctrl+comma"}`` and
# ``{"keys": "plus"}`` were both refused with "unknown key"): ``,`` and ``+``
# are the combo/sequence separators, so the two *keys* had no spelling at all --
# yet ``Ctrl+,`` (Settings, ``ui/actions/platform.py``) and ``+`` (zoom in,
# ``shared/canvas/keyboard_constants.py``) are real app chords. The parse of
# "\,", which used to resolve to BACKSLASH, is the silent half of the same gap.


def test_press_keys_spells_the_separator_keys_by_name():
    ((comma, mods, label),) = discovery_module.parse_key_sequence("comma")
    assert (comma, mods, label) == (
        Qt.Key.Key_Comma,
        Qt.KeyboardModifier.NoModifier,
        "comma",
    )

    ((plus, plus_mods, _label),) = discovery_module.parse_key_sequence("plus")
    assert (plus, plus_mods) == (Qt.Key.Key_Plus, Qt.KeyboardModifier.NoModifier)

    ((settings, settings_mods, _label),) = discovery_module.parse_key_sequence(
        "ctrl+comma"
    )
    assert (settings, settings_mods) == (
        Qt.Key.Key_Comma,
        Qt.KeyboardModifier.ControlModifier,
    ), "Ctrl+, is the Settings chord"

    ((zoom, zoom_mods, _label),) = discovery_module.parse_key_sequence("ctrl+shift+plus")
    assert (zoom, zoom_mods) == (
        Qt.Key.Key_Plus,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )


def test_press_keys_escapes_the_separator_characters():
    """An escaped comma / plus names the literal key, alone or in a combo."""
    ((escaped_comma, comma_mods, _label),) = discovery_module.parse_key_sequence("\\,")
    assert (escaped_comma, comma_mods) == (
        Qt.Key.Key_Comma,
        Qt.KeyboardModifier.NoModifier,
    )

    ((escaped_plus, plus_mods, _label),) = discovery_module.parse_key_sequence("\\+")
    assert (escaped_plus, plus_mods) == (
        Qt.Key.Key_Plus,
        Qt.KeyboardModifier.NoModifier,
    )

    ((chord, chord_mods, _label),) = discovery_module.parse_key_sequence("ctrl+\\,")
    assert (chord, chord_mods) == (Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)

    ((chord2, chord2_mods, _label),) = discovery_module.parse_key_sequence(
        "ctrl+shift+\\+"
    )
    assert (chord2, chord2_mods) == (
        Qt.Key.Key_Plus,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )

    # Two escaped keys in one sequence: the unescaped comma is the separator.
    keys = [key for key, _mods, _label in discovery_module.parse_key_sequence("\\,,\\+")]
    assert keys == [Qt.Key.Key_Comma, Qt.Key.Key_Plus]


def test_press_keys_keeps_bare_separators_as_separators():
    """The grammar is unchanged: ``+`` joins a combo, ``,`` separates combos."""
    assert [
        label
        for _key, _mods, label in discovery_module.parse_key_sequence("ctrl+p,Down")
    ] == ["ctrl+p", "Down"]

    with pytest.raises(MethodError) as exc:
        discovery_module.parse_key_sequence("+")

    assert "empty key combo" in exc.value.message
    hint = exc.value.hint or ""
    assert "\\+" in hint and "plus" in hint, "the escape is the way out"


def test_press_keys_unknown_key_still_lists_the_valid_names():
    with pytest.raises(MethodError) as exc:
        discovery_module.parse_key_sequence("wibble")

    assert "unknown key" in exc.value.message
    hint = exc.value.hint or ""
    for name in ("comma", "plus", "\\,", "\\+", "enter", "f12"):
        assert name in hint, f"{name!r} missing from the allowlist hint"
