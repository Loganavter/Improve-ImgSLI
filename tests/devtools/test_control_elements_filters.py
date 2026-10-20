"""``ui_elements`` narrowing + per-element ``properties`` + ``property:`` targets.

An agent that can only fetch the whole inventory and diff it client-side pays
for every row twice (once on the wire, once in context). These tests pin the
server-side half of the fix:

* ``role`` (exact), ``label`` (case-insensitive substring), ``properties``
  (exact match on the element's own bag) and ``limit`` narrow **without**
  touching ids or tree order — a filtered row is byte-identical to its
  unfiltered self, so an id learned before a filter still resolves;
* an unknown filter value is an honest empty list, never an error;
* every row carries a ``properties`` bag built from the widget's own dynamic
  properties (``gallery_path`` is the motivating one), scalars only — a
  pointer/container property is not serialised;
* ``property:<name>=<value>`` resolves through the shared resolver, so
  ``ui_click`` / ``ui_focus`` / ``nav_key target=`` accept it too, and a
  missing property fails with the existing named error + close matches.

Falsification (red against today's code): the filter arguments are ignored
today (every call returns all rows), rows have no ``properties`` key, and the
resolver only matches ids, so ``property:...`` is reported as a missing id.

Runs offscreen only — no Xvfb (the supervisor runs the live proof).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from core.actions.types import ActionDescriptor, ActionTarget
from core.control import elements
from core.control.elements import resolve as resolve_module
from core.control.handlers import ControlHandlers, MethodError
from ui.actions.registry import ActionRegistry


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _registry(*actions: ActionDescriptor) -> ActionRegistry:
    registry = ActionRegistry()
    for action in actions:
        registry.register(action)
    return registry


def _descriptor(action_id: str, **kwargs) -> ActionDescriptor:
    return ActionDescriptor(
        action_id=action_id,
        label_key=f"action.{action_id}",
        description_key=f"action.{action_id}_desc",
        run=None,
        **kwargs,
    )


def _handlers(window, registry, tmp_path) -> ControlHandlers:
    return ControlHandlers(
        window=window,
        app=QApplication.instance(),
        artifacts_dir=tmp_path / "artifacts",
        log_ring=None,
        registry_provider=lambda: registry,
    )


def _find(payload: dict, **match) -> dict:
    for row in payload["elements"]:
        if all(row.get(key) == value for key, value in match.items()):
            return row
    raise AssertionError(f"no element matching {match!r} in {payload['count']} rows")


# -- filters ------------------------------------------------------------------


def test_filters_narrow_without_changing_ids_or_tree_order(tmp_path):
    app = _qapp()
    window = QWidget()
    window.setObjectName("FilterWindow")
    layout = QVBoxLayout(window)
    alpha = QPushButton("Alpha one", window)
    beta = QPushButton("beta two", window)
    gamma = QPushButton("Gamma three", window)
    for button in (alpha, beta, gamma):
        layout.addWidget(button)
    alpha.setProperty("group", "demo")
    gamma.setProperty("group", "demo")
    window.resize(260, 200)
    window.show()
    app.processEvents()

    handlers = _handlers(window, _registry(), tmp_path)
    try:
        full = handlers.ui_elements({})
        assert {row["label"] for row in full["elements"]} >= {
            "Alpha one",
            "beta two",
            "Gamma three",
        }
        full_ids = [row["id"] for row in full["elements"]]
        by_label = {row["label"]: row for row in full["elements"]}

        # label: case-insensitive substring.
        narrowed = handlers.ui_elements({"label": "ALPHA"})
        assert [row["label"] for row in narrowed["elements"]] == ["Alpha one"]
        assert narrowed["elements"][0]["id"] == by_label["Alpha one"]["id"]

        # role: exact (the three stock buttons are all ``button``).
        roles = handlers.ui_elements({"role": "button"})
        assert {"Alpha one", "beta two", "Gamma three"} <= {
            row["label"] for row in roles["elements"]
        }

        # properties: exact match on the element's own bag.
        tagged = handlers.ui_elements({"properties": {"group": "demo"}})
        assert [row["label"] for row in tagged["elements"]] == ["Alpha one", "Gamma three"]

        # A combination narrows further.
        combined = handlers.ui_elements({"role": "button", "properties": {"group": "demo"}, "label": "gamma"})
        assert [row["label"] for row in combined["elements"]] == ["Gamma three"]

        # Order is tree order, so every filtered id list is a subsequence.
        for payload in (narrowed, roles, tagged, combined):
            filtered_ids = [row["id"] for row in payload["elements"]]
            positions = [full_ids.index(element_id) for element_id in filtered_ids]
            assert positions == sorted(positions)

        # limit keeps the first N of the same order and reports the truncation.
        limited = handlers.ui_elements({"limit": 2})
        assert [row["id"] for row in limited["elements"]] == full_ids[:2]
        assert limited["count"] == 2
        assert limited["total"] == len(full_ids)
    finally:
        window.close()


def test_unknown_filter_values_return_empty_not_an_error(tmp_path):
    app = _qapp()
    window = QWidget()
    window.setObjectName("EmptyFilterWindow")
    layout = QVBoxLayout(window)
    layout.addWidget(QPushButton("only", window))
    window.resize(220, 120)
    window.show()
    app.processEvents()

    handlers = _handlers(window, _registry(), tmp_path)
    try:
        for params in (
            {"role": "no-such-role"},
            {"label": "no-such-label"},
            {"properties": {"no_such_property": "x"}},
        ):
            payload = handlers.ui_elements(params)
            assert payload["elements"] == [], params
            assert payload["count"] == 0
        # An empty properties mapping filters nothing (backwards compatible).
        assert handlers.ui_elements({"properties": {}})["count"] > 0
    finally:
        window.close()


# -- the properties bag -------------------------------------------------------


def test_rows_carry_scalar_properties_and_skip_pointers(tmp_path):
    """``gallery_path`` is the motivating property; non-scalars are not copied."""
    app = _qapp()
    window = QWidget()
    window.setObjectName("PropertiesWindow")
    layout = QVBoxLayout(window)
    card = QPushButton("a card", window)
    layout.addWidget(card)
    card.setProperty("gallery_path", "/gallery/card_1.png")
    card.setProperty("zoom_level", 3)
    card.setProperty("is_thumb", True)
    card.setProperty("widget_pointer", card)  # QObject: not serialisable
    card.setProperty("tags", ["a", "b"])  # container: not a scalar
    window.resize(240, 140)
    window.show()
    app.processEvents()

    handlers = _handlers(window, _registry(), tmp_path)
    try:
        row = _find(handlers.ui_elements({}), label="a card")
        assert row["properties"]["gallery_path"] == "/gallery/card_1.png"
        assert row["properties"]["zoom_level"] == 3
        assert row["properties"]["is_thumb"] is True
        assert "widget_pointer" not in row["properties"]
        assert "tags" not in row["properties"]
        assert all(
            isinstance(value, (str, int, float, bool))
            for value in row["properties"].values()
        )

        # The bag can be filtered on (exact value).
        tagged = handlers.ui_elements({"properties": {"gallery_path": "/gallery/card_1.png"}})
        assert [candidate["id"] for candidate in tagged["elements"]] == [row["id"]]
    finally:
        window.close()


def test_property_target_clicks_the_right_widget_through_the_shared_resolver(
    tmp_path, monkeypatch
):
    """``property:<name>=<value>`` is an id for every live tool, not a new tool."""
    app = _qapp()
    window = QWidget()
    window.setObjectName("PropertyTargetWindow")
    layout = QVBoxLayout(window)
    clicked: list[str] = []
    for name in ("one", "two"):
        button = QPushButton(name, window)
        button.setProperty("gallery_path", f"/gallery/{name}.png")
        button.clicked.connect(lambda _checked=False, value=name: clicked.append(value))
        layout.addWidget(button)
    window.resize(240, 160)
    window.show()
    app.processEvents()

    handlers = _handlers(window, _registry(), tmp_path)
    try:
        result = handlers.ui_click({"id": "property:gallery_path=/gallery/two.png"})
        assert result["clicked"] is True
        assert result["target"] == "QPushButton"
        assert clicked == ["two"], "the property target, not the first button"
    finally:
        window.close()


# -- resolver unit level (fake elements, no widget tree) ----------------------


def _fake_elements() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(id="win/0.1", role="card", label="a", properties={"gallery_path": "/g/a.png"}),
        SimpleNamespace(id="win/0.2", role="card", label="b", properties={"gallery_path": "/g/b.png", "index": 2}),
    ]


def test_resolver_matches_a_property_reference(monkeypatch):
    monkeypatch.setattr(elements, "RETRY_TIMEOUT_MS", 50, raising=False)
    monkeypatch.setattr(resolve_module, "collect_elements", lambda **_kwargs: _fake_elements())

    resolved = resolve_module.resolve_element(object(), "property:gallery_path=/g/b.png")
    assert resolved.id == "win/0.2"

    # A stringified scalar matches too (the id is a string end to end).
    resolved_by_int = resolve_module.resolve_element(object(), "property:index=2")
    assert resolved_by_int.id == "win/0.2"

    # Nothing matches -> the existing named error, listing known properties.
    with pytest.raises(MethodError) as exc:
        resolve_module.resolve_element(object(), "property:gallery_pat=/g/a.png")
    assert "property" in exc.value.message
    assert exc.value.hint and "gallery_path" in exc.value.hint


def test_resolver_rejects_a_malformed_property_reference():
    with pytest.raises(MethodError) as exc:
        resolve_module.resolve_element(object(), "property:gallery_path")
    assert "name=value" in exc.value.message
