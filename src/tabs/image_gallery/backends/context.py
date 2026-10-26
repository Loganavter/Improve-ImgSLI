"""Per-call series context and the ``MetricProfile`` ⇄ ``OwnedProfile`` bridge.

ADR 009 wave A2 gives each analysis backend its own implementation. The A1
request records (``ProfileRequest`` / ``MeasureRequest`` / ``RankRequest``) are
deliberately series-FREE: they name the members (``member_keys``) and the owned
profile, never the live ``GalleryItem`` objects or the AI settings. This module
is the one place that turns a request into the concrete inputs the EXISTING
entry points need, so both adapters resolve members and build owned artifacts
the same way instead of each inventing a resolution rule:

* :class:`SeriesContext` carries what a request cannot: the live members of the
  folder, the AI settings / client the AI backend's entry points need. It is
  passed by the caller (the controller, or a test) and never stored — an
  adapter that remembered a folder would answer for another one.
* :func:`select_members` is the ONE ``member_keys`` → members rule: no keys
  means "the whole series", otherwise the members whose key is named.
* :func:`owned_profile` is the ONE ``MetricProfile`` → ``OwnedProfile``
  conversion: the axes are the backend's own profile order (registry ids and
  judge-named names alike, ``ANALYSIS_BACKENDS.md`` §5) and the ``profile_id``
  is derived from the profile's content, so a rebuilt profile over unchanged
  inputs keeps its identity and a changed one cannot be mistaken for it.
* :class:`MeasuredItem` is the identity wrapper of one member's measurement
  records, so an envelope's records stay attributable to their item without
  inventing a second per-axis record vocabulary (the records themselves are the
  gallery engine's ``AxisValue``).
* :func:`require_axes` is the ONE "an axis-less profile is no profile" rule: it
  raises ``NoProfileYet`` naming the owning backend, so A3's dead fallback (an
  empty AI profile used to answer with the local mode mapping) cannot come back
  as a silent default in a third place.

Pure: no Qt, no HTTP, no state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .contract import BackendDescriptor, OwnedProfile
from .errors import NoProfileYet

#: The payload version every adapter declares and stamps on its artifacts. The
#: profile/envelope payloads are A1's shapes; a future shape change bumps this
#: and stale artifacts become ``SchemaMismatch`` instead of being re-read.
PROFILE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SeriesContext:
    """The live series a backend resolves its request against.

    ``members`` are the folder's ``GalleryItem`` objects (canonically; anything
    the existing entry points read, i.e. ``.path`` / ``.metrics`` /
    ``.analysis_records``, works). ``settings`` / ``reference_path`` / ``cache``
    / ``client`` are the AI backend's entry-point inputs — the Algorithms
    backend ignores them, so one context type serves both and a caller cannot
    hand a backend something it must not use.

    An empty context is legal: it is what a request-only call (the contract's
    own shape) resolves to, and every adapter then behaves exactly as its
    builder does with no series (the mode mapping for Algorithms, no profile for
    AI — never a borrowed axis set).
    """

    members: tuple = ()
    settings: object | None = None
    reference_path: object | None = None
    cache: object | None = None
    client: object | None = None
    client_call: object | None = None
    salience: object | None = None
    folder_key: object | None = None
    refresh: bool = False


@dataclass(frozen=True)
class MeasuredItem:
    """One member's measurement records, keyed by the member's own key.

    ``records`` is the owning backend's own vocabulary — the gallery engine's
    ``AxisValue`` tuples for both current backends — opaque to the contract.
    The wrapper exists only so an envelope stays attributable: a flat tuple of
    records would lose which item a number belongs to, and a second record type
    carrying the path would be a second axis vocabulary.
    """

    item_key: str
    records: tuple[object, ...] = ()


def item_key_of(item) -> str:
    """The key a member is addressed by: its path when it has one."""
    path = getattr(item, "path", None)
    return str(path if path is not None else item)


def select_members(member_keys, members) -> tuple:
    """The members *member_keys* names, in the backend's own member order.

    No keys = the whole series (``MeasureRequest``'s documented default). Keys
    that name no member are simply absent: a request for an item the folder no
    longer has measures nothing, and nothing is fabricated for it.
    """
    members = tuple(members or ())
    keys = tuple(str(key) for key in (member_keys or ()) if str(key))
    if not keys:
        return members
    wanted = set(keys)
    return tuple(member for member in members if item_key_of(member) in wanted)


def profile_axes(profile) -> tuple[str, ...]:
    """The profile's own axis order: registry ids then the judge-named axes."""
    out: list[str] = []
    for axis in tuple(getattr(profile, "axis_ids", ()) or ()):
        name = str(axis)
        if name and name not in out:
            out.append(name)
    for entry in tuple(getattr(profile, "axis_entries", ()) or ()):
        name = str(getattr(entry, "name", "") or "").strip()
        if name and name not in out:
            out.append(name)
    return tuple(out)


def require_axes(profile, *, backend_id: str, operation: str) -> tuple[str, ...]:
    """The profile's own axis set, or ``NoProfileYet``.

    An axis-less profile is *no profile*: it has nothing to measure, nothing to
    rank and nothing to ask a model for. ADR 009 A3 makes that refusal typed at
    the adapter boundary instead of letting the caller fall back to the local
    mode mapping — "empty" and "diverted to the other backend's axes" must not
    be the same answer (owner rule 2026-10-26, ``ANALYSIS_BACKENDS.md`` §5).
    """
    axes = profile_axes(profile)
    if not axes:
        raise NoProfileYet(backend_id=backend_id, operation=operation)
    return axes


def profile_identity(descriptor: BackendDescriptor, profile) -> str:
    """A stable id for *profile* within *descriptor*'s backend.

    Content-derived, not counter-derived: the same axis set under the same
    source and mode keeps its id when it is re-derived (the determinism the
    profile tests already require), and a re-derived-with-different-axes profile
    gets a new one, so an envelope can only point at the profile it measured.
    """
    parts = [
        str(descriptor.backend_id),
        str(descriptor.schema_version),
        str(getattr(profile, "source", "") or ""),
        str(getattr(profile, "mode", "") or ""),
        ",".join(profile_axes(profile)),
        ",".join(
            f"{getattr(entry, 'name', '')}~{getattr(entry, 'direction', '')}"
            for entry in tuple(getattr(profile, "axis_entries", ()) or ())
        ),
    ]
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{descriptor.backend_id}:{digest[:16]}"


def owned_profile(descriptor: BackendDescriptor, profile) -> OwnedProfile:
    """The contract artifact for *profile*, owned by *descriptor*'s backend."""
    return OwnedProfile(
        backend_id=descriptor.backend_id,
        profile_id=profile_identity(descriptor, profile),
        schema_version=descriptor.schema_version,
        axes=profile_axes(profile),
        entries=tuple(getattr(profile, "axis_entries", ()) or ()),
    )


__all__ = [
    "PROFILE_SCHEMA_VERSION",
    "MeasuredItem",
    "SeriesContext",
    "item_key_of",
    "owned_profile",
    "profile_axes",
    "profile_identity",
    "require_axes",
    "select_members",
]
