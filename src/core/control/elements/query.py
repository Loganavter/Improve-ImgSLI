"""Element narrowing and content identity (the ``ui_elements`` filter half).

Kept out of :mod:`.inventory` so the traversal module stays about walking
widgets: this one owns the client-facing query semantics — how ``role`` /
``label`` / ``properties`` / ``limit`` narrow a row list, and what counts as a
serialisable property value. :mod:`.resolve` reuses the same value comparison
for ``property:<name>=<value>`` references, so filtering and targeting can
never disagree about what "the same value" means.
"""

from __future__ import annotations

from typing import Any

#: Upper bound accepted for ``ui_elements(limit=…)``. A client asking for more
#: gets the cap, never an unbounded inventory dump in one payload.
MAX_ELEMENT_LIMIT = 2000

#: Longest scalar property value copied into an element row. Identity needs a
#: path or an id, not a document: an oversized value is skipped rather than
#: truncated (a truncated identity would be a lie).
MAX_PROPERTY_VALUE_LEN = 512


def scalar_properties(widget: Any) -> dict[str, Any]:
    """The widget's own dynamic properties, scalar-only and JSON-safe.

    Dynamic properties are the app's cheap content identity: the gallery sets
    ``gallery_path`` on each card, the quick-look strip does the same, and any
    future widget can tag itself without the inventory growing a per-feature
    branch.

    The rule (kept deliberately narrow so a row stays serialisable):
    * ``str`` / ``bool`` / ``int`` / ``float`` values only — a ``QObject``
      pointer, a container, an enum, or anything else is dropped (a pointer in
      a JSON payload is unusable to a client and stales instantly);
    * names starting with ``_`` are dropped — Qt's own ``_q_*`` internals and
      private implementation markers are not content identity;
    * strings longer than :data:`MAX_PROPERTY_VALUE_LEN` are dropped, not
      truncated.

    No attribute is read beyond Qt's property table, so no method runs on the
    widget and nothing here can leak a stored secret the app did not already
    publish as a dynamic property.
    """
    values: dict[str, Any] = {}
    try:
        names = widget.dynamicPropertyNames()
    except Exception:
        return values
    for raw in names:
        try:
            name = bytes(raw).decode("utf-8")
        except Exception:
            continue
        if not name or name.startswith("_"):
            continue
        try:
            value = widget.property(name)
        except Exception:
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            values[name] = value
        elif isinstance(value, str) and len(value) <= MAX_PROPERTY_VALUE_LEN:
            values[name] = value
    return values


def property_value_matches(actual: Any, wanted: Any) -> bool:
    """True when element value *actual* equals filter/target value *wanted*.

    Values arrive from JSON and from id strings, so a scalar compares both
    exactly and by its string form (``property:index=2`` reaches an int ``2``;
    ``True`` never matches ``1``). Non-scalars and pointers never match a
    string: only what :func:`scalar_properties` copies is addressable.
    """
    if isinstance(actual, bool) != isinstance(wanted, bool):
        # ``True == 1`` in Python — bool identity is not int identity here.
        return isinstance(actual, (bool, str, int, float)) and isinstance(
            wanted, (bool, str, int, float)
        ) and str(actual) == str(wanted)
    if actual == wanted:
        return True
    if isinstance(actual, (str, int, float, bool)) and isinstance(
        wanted, (str, int, float, bool)
    ):
        return str(actual) == str(wanted)
    return False


def filter_elements(
    elements: list[Any],
    *,
    role: Any = None,
    label: Any = None,
    properties: Any = None,
    limit: Any = None,
) -> tuple[list[Any], int]:
    """Narrow *elements* in tree order; returns ``(rows, matched_total)``.

    ``role`` is an exact role string, ``label`` a case-insensitive substring,
    ``properties`` a mapping every one of whose entries must equal the
    element's own property value, and ``limit`` caps the returned rows at
    :data:`MAX_ELEMENT_LIMIT`. An unknown value yields an empty list — never an
    error: "this role does not exist in the current UI" is a fact, not a
    failure. Ids and ordering are untouched, so an id learned from an
    unfiltered call still resolves after a narrowed one.

    ``matched_total`` is the pre-limit match count, so a client can tell
    ``limit`` truncation from a genuinely short answer.
    """
    role_needle = role if isinstance(role, str) and role else None
    label_needle = label.casefold() if isinstance(label, str) and label else None
    property_filter = dict(properties) if isinstance(properties, dict) else {}
    rows: list[Any] = []
    for element in elements:
        if role_needle is not None and element.role != role_needle:
            continue
        if label_needle is not None and label_needle not in (element.label or "").casefold():
            continue
        if property_filter and not all(
            key in element.properties
            and property_value_matches(element.properties[key], wanted)
            for key, wanted in property_filter.items()
        ):
            continue
        rows.append(element)
    matched = len(rows)
    if isinstance(limit, int) and not isinstance(limit, bool):
        rows = rows[: max(0, min(int(limit), MAX_ELEMENT_LIMIT))]
    return rows, matched
