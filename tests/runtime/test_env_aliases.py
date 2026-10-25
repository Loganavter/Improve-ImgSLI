"""``BLINKTABLE_*`` aliases: one resolver, every ``IMGSLI_*`` name honoured.

Table-driven over the **real** name set: the test scans ``src/`` for every
``IMGSLI_[A-Z0-9_]+`` literal, so a new flag is covered automatically and a
rename cannot silently drop a legacy spelling. For every discovered name it
asserts the fixed precedence — alias (non-empty) → legacy name → default — plus
the empty-alias fall-through and the unchanged ``env_flag`` truthy/falsy
vocabulary. All mutation goes through ``monkeypatch``, so the process
environment is restored after each row.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.debug_flags import (
    ENV_PREFIX,
    LEGACY_ENV_PREFIX,
    alias_name,
    env_flag,
    env_flag_strict,
    env_value,
)

_SRC = Path(__file__).resolve().parents[2] / "src"
_NAME_RE = re.compile(r"IMGSLI_[A-Z0-9_]+")


def _discovered_names() -> list[str]:
    names: set[str] = set()
    for path in sorted(_SRC.rglob("*.py")):
        names.update(_NAME_RE.findall(path.read_text(encoding="utf-8")))
    return sorted(names)


NAMES = _discovered_names()

#: Permissive ``env_flag`` vocabulary (unchanged by the alias layer).
_FLAG_TRUTHY = ("1", "yes", "true", "on", "anything", "2")
_FLAG_FALSY = ("0", "false", "no", "off", "FALSE", " Off ")
#: Strict ``env_flag_strict`` vocabulary.
_STRICT_TRUTHY = ("1", "true", "yes", "on")
_STRICT_FALSY = ("0", "2", "anything", "false", "no", "off")


def test_discovered_name_set_is_the_real_one() -> None:
    # A vacuous scan (wrong root, renamed package) would make every row below
    # pass without testing anything.
    assert len(NAMES) >= 50, f"scan found only {len(NAMES)} IMGSLI_* names in {_SRC}"
    assert all(name.startswith(LEGACY_ENV_PREFIX) for name in NAMES)


def test_prefix_constants() -> None:
    assert ENV_PREFIX == "BLINKTABLE_"
    assert LEGACY_ENV_PREFIX == "IMGSLI_"
    assert ENV_PREFIX != LEGACY_ENV_PREFIX


@pytest.mark.parametrize("name", NAMES)
def test_alias_name_is_the_blinktable_spelling(name: str) -> None:
    suffix = name[len(LEGACY_ENV_PREFIX) :]
    assert alias_name(name) == ENV_PREFIX + suffix


def test_alias_name_leaves_non_legacy_names_alone() -> None:
    for name in ("BLINKTABLE_TRACE", "IMPROVE_DEBUG", "", "IMGSLI"):
        assert alias_name(name) == name


@pytest.mark.parametrize("name", NAMES)
def test_resolution_precedence(monkeypatch, name: str) -> None:
    alias = alias_name(name)
    monkeypatch.delenv(alias, raising=False)
    monkeypatch.delenv(name, raising=False)

    # (c) neither spelling set -> the caller's default (None by default).
    assert env_value(name) is None
    assert env_value(name, "sentinel") == "sentinel"

    # (b) only the legacy spelling set -> it still resolves.
    monkeypatch.setenv(name, "legacy-value")
    assert env_value(name) == "legacy-value"
    assert env_value(name, "sentinel") == "legacy-value"

    # (a) alias set and non-empty -> it wins, whitespace stripped.
    monkeypatch.setenv(alias, "  alias-value  ")
    assert env_value(name) == "alias-value"
    assert env_value(name, "sentinel") == "alias-value"

    # (d) an empty/whitespace alias is "unset" and falls through to legacy.
    monkeypatch.setenv(alias, "   ")
    assert env_value(name) == "legacy-value"

    # ... and with no legacy value either, back to the default.
    monkeypatch.delenv(name)
    assert env_value(name) is None
    assert env_value(name, "sentinel") == "sentinel"


@pytest.mark.parametrize("name", NAMES)
def test_env_flag_vocabulary_through_alias(monkeypatch, name: str) -> None:
    alias = alias_name(name)
    monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(alias, raising=False)

    # Neither spelling -> off for both predicates.
    assert env_flag(name) is False
    assert env_flag_strict(name) is False

    for value in _FLAG_TRUTHY:
        monkeypatch.setenv(alias, value)
        assert env_flag(name) is True, f"env_flag({name}) with {alias}={value!r}"
    for value in _FLAG_FALSY:
        monkeypatch.setenv(alias, value)
        assert env_flag(name) is False, f"env_flag({name}) with {alias}={value!r}"

    for value in _STRICT_TRUTHY:
        monkeypatch.setenv(alias, value)
        assert env_flag_strict(name) is True, f"strict {name} with {alias}={value!r}"
    for value in _STRICT_FALSY:
        monkeypatch.setenv(alias, value)
        assert env_flag_strict(name) is False, f"strict {name} with {alias}={value!r}"

    # The legacy spelling keeps the same vocabulary when the alias is absent.
    monkeypatch.delenv(alias)
    monkeypatch.setenv(name, "yes")
    assert env_flag(name) is True
    assert env_flag_strict(name) is True
    monkeypatch.setenv(name, "off")
    assert env_flag(name) is False
    assert env_flag_strict(name) is False


@pytest.mark.parametrize("name", NAMES)
def test_empty_alias_cannot_shadow_legacy_flag(monkeypatch, name: str) -> None:
    alias = alias_name(name)
    monkeypatch.setenv(alias, "")
    monkeypatch.setenv(name, "1")
    assert env_value(name) == "1"
    assert env_flag(name) is True
