"""A disposable, recording ``secret-tool`` for the whole test suite.

Why this exists: ``core.secret_store`` resolves its backend with
``shutil.which("secret-tool")`` and then *execs* that binary. On a desktop with
a login keyring a test that reaches the store therefore READS the owner's
provider key and — on ``store``/``clear`` — OVERWRITES or DELETES it. That is
not hypothetical: on 2026-10-25
``src/tabs/image_gallery/tests/runtime/test_ai_settings_store.py::test_save_and_load_round_trip``
wrote an 11-char stub (``sk-test-123``) over the owner's 73-char key in the
SHARED ``application=blinktable key=ai-api-key`` entry. The suite was green
while it did that, which is why isolation alone is not enough.

Two layers, both needed:

1. **Pinning** (session-scoped, autouse). A fake ``secret-tool`` first on
   ``PATH``, a throwaway ``XDG_DATA_HOME`` (where the encrypted-file backend
   keeps ``BlinkTable/secrets/``), and a wrapper on
   ``core.secret_store._secret_tool()`` — the single chokepoint every keyring
   operation goes through. The wrapper refuses to hand the HOST binary to
   ``subprocess``: if something reorders ``PATH`` to the real tool, the refusal
   is recorded and the sandbox tool is substituted, so no run can write the
   login keyring. A test's own fake (``tmp_path``) still wins, unchanged — that
   is the sanctioned way for key-storage tests to drive a keyring.
2. **Guard** (per test, autouse). The fake tool appends every invocation
   (argv, timestamp, and the running test's nodeid via
   ``IMGLSI_TEST_SECRET_TOOL_MARKER``) to ``invocations.jsonl``; the guard
   fails the test loudly on a *mutating* call (``store``/``clear``) from a test
   that did not declare keyring use — neither through the
   ``secret_store_keyring`` fixture nor by installing its own
   ``tmp_path / "secret-tool"`` (:func:`module_installs_own_tool`) — on a
   recorded refusal, on an invocation carrying another test's marker, on an
   encrypted-file write whose directory is outside the sandbox (recorded per
   write, not guessed from the environment afterwards), or when the app-data
   dir is not disposable at test start.

Reads (``lookup``) need no opt-in on purpose: dozens of UI tests build the AI
settings page, whose key row legitimately reads "no key configured". Sandboxed,
that read cannot expose the owner's key. Writes are the class that destroyed
data, so writes must be declared.

The scan contract ``tests/contracts/test_secret_store_test_isolation.py``
enforces the same intent statically for the known write shapes, so a new test
cannot re-introduce the call without naming this module or the opt-in fixture.
"""

from __future__ import annotations

import ast
import json
import os
import stat
import tempfile
from pathlib import Path

import pytest

#: Env carrying the sandbox root for the fake tool (it cannot take arguments).
SANDBOX_ENV = "IMGLSI_TEST_SECRET_TOOL_SANDBOX"
#: Env carrying the nodeid of the running test, stamped onto every invocation.
MARKER_ENV = "IMGLSI_TEST_SECRET_TOOL_MARKER"

TOOL_NAME = "secret-tool"
#: Fixture a test requests to declare it drives a keyring on purpose.
KEYRING_OPT_IN_FIXTURE = "secret_store_keyring"
#: Names the static scan accepts as a declaration of isolation.
ISOLATION_MARKERS = frozenset(
    {
        "secret_store_isolation",
        "secret_store_sandbox",
        KEYRING_OPT_IN_FIXTURE,
        "secret_store_isolation.py",
    }
)

_MUTATING = ("store", "clear")

# The fake tool. No interpolated paths: the root travels in ``SANDBOX_ENV`` so a
# path with spaces/quotes cannot break the script.
_TOOL_SOURCE = """\
#!/usr/bin/env python3
import json, os, pathlib, sys, time

root = pathlib.Path(os.environ["IMGLSI_TEST_SECRET_TOOL_SANDBOX"])
argv = sys.argv[1:]
cmd = argv[0] if argv else ""
payload = sys.stdin.read() if cmd == "store" else ""
rest = list(argv[1:])
if "--label" in rest:
    at = rest.index("--label")
    del rest[at:at + 2]
identity = "|".join(rest) or "default"
entries = root / "entries"
entries.mkdir(exist_ok=True)
path = entries / (identity.replace("/", "_").replace(" ", "_") + ".txt")
with (root / "invocations.jsonl").open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "ts": time.time(),
        "pid": os.getpid(),
        "marker": os.environ.get("IMGLSI_TEST_SECRET_TOOL_MARKER", ""),
        "tool": sys.argv[0],
        "identity": identity,
        "argv": argv,
    }) + "\\n")
if cmd == "store":
    path.write_text(payload, encoding="utf-8")
elif cmd == "lookup":
    if path.exists():
        sys.stdout.write(path.read_text(encoding="utf-8"))
    else:
        sys.exit(1)
elif cmd == "clear":
    path.unlink(missing_ok=True)
else:
    sys.exit(2)
"""


def _resolved(path: Path) -> Path:
    """*path* with symlinks resolved (a link to the real tool must not pass)."""
    try:
        return path.resolve()
    except OSError:
        return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def sandboxed_resolution(box: "SecretStoreSandbox", original):
    """Wrap ``core.secret_store._secret_tool``: never hand out the host binary.

    *original* is the unwrapped resolver (``shutil.which``-based in production).
    A path the box owns — its own fake, a test's own ``tmp_path`` fake, anything
    under the system temp dir — passes through untouched. Anything else is the
    host's real ``secret-tool``: it is recorded as a refusal and the sandbox
    tool is substituted, so the run cannot read or overwrite the login keyring
    even when ``PATH`` was reordered under us.
    """

    def resolve() -> str | None:
        found = original()
        if found is None:
            return None
        if box.is_sandboxed_path(found):
            return str(found)
        box.record_refusal(str(found))
        return str(box.tool_path)

    return resolve


_OWNS_TOOL: dict[str, bool] = {}


def module_installs_own_tool(module: object) -> bool:
    """Does this test module write its own ``secret-tool`` binary?

    ``tmp_path / "secret-tool"`` is the suite's established way to drive a
    keyring (``tests/.../test_ai_key_storage.py``,
    ``.../test_ai_key_page_refresh.py``): such a module answers the keyring
    itself and its calls never reach the shared sandbox, so the intent is
    already declared structurally and the guard must not demand the opt-in
    fixture on top. Cached per file — sources do not change during a run.
    """
    path = getattr(module, "__file__", None)
    if not path:
        return False
    cached = _OWNS_TOOL.get(path)
    if cached is not None:
        return cached
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        _OWNS_TOOL[path] = False
        return False
    found = any(
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Constant)
        and node.right.value == TOOL_NAME
        for node in ast.walk(tree)
    )
    _OWNS_TOOL[path] = found
    return found


class SecretStoreSandbox:
    """The installed sandbox: fake tool, disposable data dir, invocation log.

    One instance per pytest process (see :func:`get_secret_store_sandbox`); the
    root and gallery conftests share it, so the two suites cannot end up with
    two stacked ``PATH`` prepends and two ``_secret_tool`` wrappers.
    """

    def __init__(self, root: Path, *, allow_roots: tuple[Path, ...] = ()) -> None:
        self.root = Path(root)
        self.tool_path = self.root / "bin" / TOOL_NAME
        self.log_path = self.root / "invocations.jsonl"
        self.entries_dir = self.root / "entries"
        #: Directories whose ``secret-tool`` binaries are sandboxed already —
        #: pytest's basetemp (a test's own fake) and the system temp dir.
        self.allow_roots = tuple(Path(p) for p in allow_roots)
        self._nodeid = ""
        self._offset = 0
        self._allow_keyring = False
        #: True once :meth:`install` ran — the other conftest shares the box.
        self.installed = False

    # -- installation --------------------------------------------------------

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "SecretStoreSandbox":
        """Pin PATH + the app-data dir and wrap the keyring chokepoint."""
        from core import secret_store

        self.tool_path.parent.mkdir(parents=True, exist_ok=True)
        self.tool_path.write_text(_TOOL_SOURCE, encoding="utf-8")
        self.tool_path.chmod(self.tool_path.stat().st_mode | stat.S_IXUSR)
        self.log_path.touch()

        monkeypatch.setenv(SANDBOX_ENV, str(self.root))
        monkeypatch.setenv(
            "PATH", f"{self.tool_path.parent}{os.pathsep}{os.environ.get('PATH', '')}"
        )
        # The encrypted-file backend writes ``<app data>/BlinkTable/secrets``.
        monkeypatch.setenv("XDG_DATA_HOME", str(self.root / "data"))
        # QSettings resolves $XDG_CONFIG_HOME/<org>/<app>.conf; without this the
        # app config store still points at the REAL user profile and a settings
        # test rewrites it (measured 2026-10-26: the [image_gallery_ai] group was
        # dropped from the live config while the key stayed in the keyring).
        monkeypatch.setenv("XDG_CONFIG_HOME", str(self.root / "config"))
        monkeypatch.setenv("APPDATA", str(self.root / "appdata"))

        original = secret_store._secret_tool
        monkeypatch.setattr(
            secret_store, "_secret_tool", sandboxed_resolution(self, original)
        )
        # The encrypted-file backend is the other writer: record the directory in
        # effect at write time, so a test that moves XDG_DATA_HOME out of the
        # sandbox (``monkeypatch.delenv("XDG_DATA_HOME")`` and friends) is caught
        # positively instead of by guessing from the environment afterwards.
        for name in ("_file_store", "_file_clear"):
            monkeypatch.setattr(
                secret_store, name, self._record_data_write(getattr(secret_store, name))
            )
        self.installed = True
        self.reset_caches()
        return self

    def _record_data_write(self, original):
        def wrapped(*args, **kwargs):
            from core import secret_store

            self.record_data_write(secret_store.secrets_dir())
            return original(*args, **kwargs)

        return wrapped

    def uninstall(self) -> None:
        os.environ.pop(MARKER_ENV, None)

    # -- state ---------------------------------------------------------------

    def reset_caches(self) -> None:
        """Forget the resolved backend and the in-memory copy (both per process)."""
        from core import secret_store

        secret_store.forget_session_cache()
        secret_store.reset_backend_probe()

    def begin_test(self, nodeid: str, *, module: object = None) -> None:
        """Start a fresh keyring baseline and start attributing invocations."""
        nodeid = str(nodeid)
        self._nodeid = nodeid
        # Read the log HERE (fixture setup), never at teardown: a test may arm a
        # strict "no file I/O" trap for its whole body (e.g.
        # ``tests/plugins/test_diagnostics_report.py``), and reading our own log
        # then would look like the behaviour under test. At teardown only a
        # ``stat`` decides whether there is anything to read.
        self._offset = len(self.events())
        self._offset_size = self._log_size()
        self._allow_keyring = module_installs_own_tool(module)
        self._reset_entries()
        os.environ[MARKER_ENV] = nodeid
        self.reset_caches()

    def _log_size(self) -> int:
        try:
            return self.log_path.stat().st_size
        except OSError:
            return 0

    def allow_keyring(self) -> None:
        """Declare that this test drives a keyring on purpose."""
        self._allow_keyring = True

    def _reset_entries(self) -> None:
        """Empty the fake keyring: every test starts from "no key configured"."""
        if not self.entries_dir.is_dir():
            return
        for path in self.entries_dir.iterdir():
            try:
                path.unlink()
            except OSError:
                pass

    # -- the guard -----------------------------------------------------------

    def is_sandboxed_path(self, path: str | os.PathLike[str]) -> bool:
        """Is *path* a sandboxed ``secret-tool`` (ours, a test's fake, tmp)?"""
        target = _resolved(Path(str(path)))
        roots = (self.root, *self.allow_roots, Path(tempfile.gettempdir()))
        return any(_is_relative_to(target, _resolved(root)) for root in roots)

    def record_refusal(self, path: str) -> None:
        self._append({"kind": "refused", "path": str(path)})

    def record_data_write(self, path: str | os.PathLike[str]) -> None:
        """Remember which directory the encrypted-file backend was writing into."""
        self._append({"kind": "data-write", "path": str(path)})

    def _append(self, event: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    def events(self) -> list[dict]:
        try:
            text = self.log_path.read_text(encoding="utf-8")
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def problems(self) -> list[str]:
        """Everything that must fail the test that just ran (empty when clean)."""
        if self._log_size() <= self._offset_size:
            # Nothing was recorded during this test: do not touch the file.
            return []
        found: list[str] = []
        for event in self.events()[self._offset:]:
            kind = event.get("kind")
            if kind == "refused":
                found.append(
                    "the host's "
                    f"`{TOOL_NAME}` at {event.get('path')!r} was about to be executed; the "
                    "sandbox refused and substituted its own tool — a real keyring would "
                    "have been read or written"
                )
                continue
            if kind == "data-write":
                if not self.is_sandboxed_path(event.get("path") or ""):
                    found.append(
                        "the encrypted-file backend wrote into "
                        f"{event.get('path')!r}, outside the sandbox ({self.root}) — the "
                        "real app-data secrets directory was in effect"
                    )
                continue
            argv = list(event.get("argv") or [])
            command = argv[0] if argv else "?"
            marker = event.get("marker") or "<no test marker>"
            if command in _MUTATING and not self._allow_keyring:
                found.append(
                    f"`{TOOL_NAME} {command}` ran while {self._nodeid} ran, but that test "
                    f"did not opt in — request the `{KEYRING_OPT_IN_FIXTURE}` fixture "
                    f"(argv={argv})"
                )
            if marker != self._nodeid:
                found.append(
                    f"`{TOOL_NAME} {' '.join(argv)}` was executed by {marker} while "
                    f"{self._nodeid} ran — a leaked thread or a stale subprocess"
                )
        return found

    def data_home_is_disposable(self) -> bool:
        """Is the encrypted-file backend's directory inside the sandbox right now?"""
        from core import secret_store

        try:
            return self.is_sandboxed_path(secret_store.secrets_dir())
        except Exception:  # pragma: no cover - defensive, keep the guard running
            return True


# One sandbox per pytest process: the root and gallery conftests both import
# this module, and a second installation would stack PATH prepends and wrap the
# already-wrapped chokepoint.
_INSTALLED: SecretStoreSandbox | None = None


def get_secret_store_sandbox(root: Path, *, allow_roots: tuple[Path, ...] = ()) -> SecretStoreSandbox:
    """The process-wide sandbox (created on first call, reused afterwards)."""
    global _INSTALLED
    if _INSTALLED is None:
        _INSTALLED = SecretStoreSandbox(root, allow_roots=allow_roots)
    return _INSTALLED


# ---------------------------------------------------------------------------
# Fixtures (imported by ``tests/conftest.py`` and the gallery package conftest)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def secret_store_sandbox(tmp_path_factory):
    """Pin every keyring/app-data path into a throwaway tree (whole session)."""
    basetemp = Path(str(tmp_path_factory.getbasetemp()))
    box = get_secret_store_sandbox(
        basetemp / "secret_store_sandbox", allow_roots=(basetemp,)
    )
    if box.installed:
        # The other suite's conftest (``tests/`` vs ``src/tabs/``) installed it
        # first in this process; share the one sandbox, do not stack a second.
        yield box
        return
    patch = pytest.MonkeyPatch()
    box.install(patch)
    try:
        yield box
    finally:
        patch.undo()
        box.installed = False
        box.uninstall()


@pytest.fixture(autouse=True)
def secret_store_isolation(request, secret_store_sandbox):
    """Fail the test when it touched a keyring without declaring it.

    The app-data directory is checked at SETUP only: a test may legitimately
    unset ``XDG_DATA_HOME`` for the length of its body (the MCP socket tests
    do), and ``monkeypatch`` hands the session value back before the next test.
    What actually counts is the directory in effect *while* a write happens, and
    that is recorded per write (``data-write`` events) rather than guessed from
    the environment afterwards.
    """
    box = secret_store_sandbox
    problems: list[str] = []
    if not box.data_home_is_disposable():
        problems.append(
            "the secret store's app-data dir is outside the sandbox "
            f"({box.root}); an encrypted-file write would land in the real one"
        )
    box.begin_test(request.node.nodeid, module=getattr(request, "module", None))
    try:
        yield box
    finally:
        problems.extend(box.problems())
        box.reset_caches()
        if problems:
            pytest.fail(
                "host-keyring guard (tests/helpers/secret_store_isolation.py):\n  - "
                + "\n  - ".join(dict.fromkeys(problems)),
                pytrace=False,
            )


@pytest.fixture
def secret_store_keyring(secret_store_isolation, secret_store_sandbox):
    """Opt in: this test drives the (sandboxed) keyring on purpose.

    A missing entry starts every test empty, and the entry this test writes is
    cleared on the way out, so nothing it stores can reach the next test.
    """
    from core import secret_store

    secret_store_sandbox.allow_keyring()
    secret_store_sandbox.reset_caches()
    try:
        yield secret_store_sandbox
    finally:
        secret_store.clear()
        secret_store_sandbox.reset_caches()
