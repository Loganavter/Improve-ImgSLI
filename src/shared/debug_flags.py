"""One resolver for the app's ``*_DEBUG``/tuning env knobs.

The app is renaming its user-facing identity to **BlinkTable**. Environment
variables follow with a ``BLINKTABLE_`` prefix, but the historic ``IMGSLI_``
spelling must keep working — scripts, docs, launchers and users' shells carry
it. This module is the single place that decision lives, so the ~85
``env_flag(...)`` call sites needed no edit at all when the alias layer landed.

Resolution order (fixed, everywhere):

1. ``BLINKTABLE_<suffix>`` when set **and non-empty** after stripping;
2. ``IMGSLI_<suffix>`` (legacy spelling, same rule);
3. the caller's ``default``.

An empty/whitespace-only value counts as *unset* (so an empty
``BLINKTABLE_<X>`` cannot shadow a real ``IMGSLI_<X>``). A name that does not carry the legacy prefix is
read as-is — ``alias_name`` never invents a spelling.

Two predicates:
* ``env_flag`` — permissive: any non-empty value except ``0/false/no/off`` is true
  (``BLINKTABLE_RESIZE_DEBUG=1`` or the legacy ``IMGSLI_RESIZE_DEBUG=yes`` etc).
  Used by render/flyout/resize/first-frame.
* ``env_flag_strict`` — strict: only ``1/true/yes/on`` is true (historical
  ``rhi_backend`` semantics for ``ALLOW_LSFGVK``). Keep behavior for that one call site.

Both predicates keep their public signatures and their truthy/falsy vocabulary;
only the *lookup* changed, so callers stay unaware of the alias.
"""

from __future__ import annotations

import os

#: New spelling, honoured first.
ENV_PREFIX = "BLINKTABLE_"
#: Historic spelling, still supported (not deprecated silently).
LEGACY_ENV_PREFIX = "IMGSLI_"


def alias_name(name: str) -> str:
    """Return the ``BLINKTABLE_<suffix>`` spelling of an ``IMGSLI_<suffix>`` name.

    Names that do not carry :data:`LEGACY_ENV_PREFIX` are returned unchanged —
    there is no second spelling to look up, and no prefix is ever invented.
    """
    if name.startswith(LEGACY_ENV_PREFIX):
        return ENV_PREFIX + name[len(LEGACY_ENV_PREFIX) :]
    return name


def env_value(name: str, default: str | None = None) -> str | None:
    """Resolve an env value: alias (non-empty) → legacy name (non-empty) → default.

    Values are stripped; an empty or whitespace-only string counts as unset.
    Never raises for a malformed name — a non-legacy name is simply read once.
    """
    alias = alias_name(name)
    if alias != name:
        value = os.environ.get(alias, "").strip()
        if value:
            return value
    value = os.environ.get(name, "").strip()
    if value:
        return value
    return default


def env_flag(name: str) -> bool:
    """Permissive flag: true unless value is empty/0/false/no/off."""
    return (env_value(name, "") or "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def env_flag_strict(name: str) -> bool:
    """Strict flag: true only for 1/true/yes/on."""
    return (env_value(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


# Back-compat alias for internal callers that imported ``_env_flag``.
_env_flag = env_flag
