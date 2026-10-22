#!/usr/bin/env python3
"""Adapter over the host's ``live-lease`` tool (display + control-dir leases).

Devtool only. ``live-lease`` owns this machine's pool of X displays and
per-capture dirs: ``alloc`` starts the Xvfb (unless asked not to), ``env`` is
the **only** supported way to learn the display and the control dir, ``bind``
ties the app's pid/process group to the lease, ``release`` kills that group,
removes the lease, and is idempotent.

Why this exists next to :func:`help_figures._free_display_number`: that probe
is a check, not a reservation. Two lanes that probe before either Xvfb socket
exists both read the same number as free, and the loser waits ten seconds for a
socket that never appears. The lease pool is the allocator that already knows
what another lane holds.

The tool is installed outside this repository, so it is driven as a subprocess
with argv lists and no shell, never imported. ``LIVE_LEASE_BIN``
overrides the executable — the tests point it at a fake CLI inside ``tmp_path``
— and the normal resolution is ``shutil.which("live-lease")``.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

#: Executable seam (tests, and a host that keeps the tool off ``PATH``).
ENV_BIN = "LIVE_LEASE_BIN"
#: Every variable ``live-lease env`` is documented to export. Not enforced as
#: an allow-list (a lease may grow keys); named so a missing display/control dir
#: is reported against the documented contract.
EXPORTED_KEYS = (
    "DISPLAY",
    "XDG_RUNTIME_DIR",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "IMGSLI_CONTROL_DIR",
    "IMGSLI_MCP_CONTROL_SOCKET",
    "LIVE_LEASE",
)
DEFAULT_TIMEOUT_S = 60.0


class LiveLeaseError(RuntimeError):
    """The lease tool is missing, failed, or answered with something unusable."""


def _binary() -> str | None:
    """The lease executable, or ``None`` when this host has no lease layer."""
    override = os.environ.get(ENV_BIN, "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    return shutil.which("live-lease")


def available() -> bool:
    """True when a lease can be taken on this host."""
    return _binary() is not None


def _run(*args: str, timeout: float = DEFAULT_TIMEOUT_S) -> str:
    binary = _binary()
    if binary is None:
        raise LiveLeaseError(
            "live-lease is not installed (or LIVE_LEASE_BIN does not point at an "
            "executable)"
        )
    argv = [binary, *args]
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout
        )
    except OSError as exc:
        raise LiveLeaseError(f"live-lease {args[0]}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LiveLeaseError(
            f"live-lease {args[0]} did not answer within {timeout:.0f}s"
        ) from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip()
        raise LiveLeaseError(
            f"live-lease {args[0]} failed (exit {done.returncode}): "
            f"{detail or 'no output'}"
        )
    return done.stdout


def _last_line(stdout: str, *, what: str) -> str:
    """The lease id is the last non-empty stdout line (the tool may log first)."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise LiveLeaseError(f"live-lease {what} printed no lease id")
    return lines[-1]


def parse_env(text: str) -> dict[str, str]:
    """Parse ``live-lease env`` output (``export K=V`` shell lines).

    Values are shell-quoted by the tool, so a value with spaces arrives as one
    quoted token. Anything else is reported instead of guessed: exporting a
    half-parsed environment would point the app at the host's dirs.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            raise LiveLeaseError(
                f"live-lease env: cannot parse {raw!r}: {exc}"
            ) from exc
        if not tokens:
            continue
        key, sep, value = tokens[0].partition("=")
        if not sep or not key or len(tokens) > 1:
            raise LiveLeaseError(f"live-lease env: unexpected line {raw!r}")
        values[key] = value
    if not values:
        raise LiveLeaseError("live-lease env printed no variables")
    return values


@dataclass
class Lease:
    """One held lease; :meth:`release` is idempotent and owns the process group."""

    id: str
    _env: dict[str, str] | None = field(default=None, repr=False)
    _released: bool = field(default=False, repr=False)

    @property
    def env(self) -> dict[str, str]:
        """Display + the four XDG dirs + control dir, read once from the tool."""
        if self._env is None:
            self._env = parse_env(_run("env", self.id))
        return dict(self._env)

    @property
    def released(self) -> bool:
        return self._released

    def bind(self, pid: int | None = None, pgid: int | None = None) -> None:
        """Tie the capture's process (and its group) to this lease."""
        if pid is None and pgid is None:
            raise LiveLeaseError("bind needs a pid or a pgid")
        args = ["bind", self.id]
        if pid is not None:
            args += ["--pid", str(int(pid))]
        if pgid is not None:
            args += ["--pgid", str(int(pgid))]
        _run(*args)

    def release(self) -> None:
        """Kill the lease's process group and remove it; safe to call twice."""
        if self._released:
            return
        _run("release", self.id)
        self._released = True


def alloc(
    lane: str,
    task: str,
    *,
    display: str | None = None,
    ttl: int | float | None = None,
    no_xvfb: bool = False,
    wait: int | float | None = None,
    root: str | Path | None = None,
    geometry: str | None = None,
) -> Lease:
    """Allocate a lease and return it (the CLI prints its id as the last line)."""
    if not str(lane or "").strip() or not str(task or "").strip():
        raise LiveLeaseError("alloc needs a lane and a task")
    args = ["alloc", "--lane", str(lane), "--task", str(task)]
    for flag, value in (
        ("--display", display),
        ("--ttl", ttl),
        ("--no-xvfb", True if no_xvfb else None),
        ("--wait", wait),
        ("--root", root),
        ("--geometry", geometry),
    ):
        if value is None:
            continue
        args.append(flag)
        if value is not True:
            args.append(str(value))
    # ``--wait`` is the caller's own budget for the display to answer; the
    # subprocess deadline has to cover it or a legal wait reads as a failure.
    budget = DEFAULT_TIMEOUT_S + (float(wait) if wait is not None else 0.0)
    return Lease(_last_line(_run(*args, timeout=budget), what="alloc"))
