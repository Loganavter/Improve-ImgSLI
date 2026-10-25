"""One product identity across every surface a user can see.

``core.log_names.APP_NAME`` is the one spelling of the product, and the BlinkTable
rename is only complete when the surfaces that *name* the app derive from it
instead of restating an older literal. ``tests/runtime/test_log_identity.py``
covers the logger and the log directory; this module covers the rest:

* **derivation** — the pre-rename literal must not sit behind a user-visible
  name. The cache root (:func:`services.io.project_package._cache_root`), the
  D-Bus notification identity, the trace ``process_name`` and the icon-service
  cache key are all ``APP_NAME`` now, so a future rename cannot stop half-way
  the way this one did.
* **no second spelling** — a source scan over ``src/``, ``mcp-server/`` and
  ``build/`` fails on any remaining pre-rename literal that is not in
  :data:`KEEPERS`, and every keeper carries the reason it must stay. A rename
  that misses a file fails here instead of silently shipping two names.

Genuine technical identities stay on the old spelling on purpose (they are
documented in ``docs/RELEASE.md`` §7: app-id, AUR ``pkgname``, MIME type,
``StartupWMClass``, Inno Setup identity, QSettings legacy pair, repository and
domain) — that is what :data:`KEEPERS` is for, not a gap.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.log_names import APP_NAME, LEGACY_LOG_DIR_NAME
from engine.frame.trace_export import build_trace
from services.io import project_package
from services.system import notifications
from ui import icon_manager

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Trees that ship to a user (code, the MCP tool, packaging) — not docs, tests,
#: scripts or the repo's own prose.
SCAN_ROOTS = (REPO_ROOT / "src", REPO_ROOT / "mcp-server", REPO_ROOT / "build")

#: Text suffixes worth scanning; binaries (icons, archives) cannot hold a name.
SCAN_SUFFIXES = {
    ".py",
    ".yaml",
    ".yml",
    ".desktop",
    ".xml",
    ".iss",
    ".txt",
    ".sh",
    ".json",
    ".md",
    ".in",
    ".cfg",
    ".toml",
    ".thumbnailer",
}

#: Any pre-rename spelling of the product: ``Improve-ImgSLI``, ``ImproveImgSLI``,
#: ``Improve ImgSLI``, ``improve-imgsli``.
LEGACY_LITERAL = re.compile(r"improve[-_ ]?imgsli", re.IGNORECASE)

#: Spelled with the old letters but NOT a product leftover: the private docs
#: repository, GitHub/media-archive URLs, the project domain, and the
#: ``IMPROVE_IMGSLI_*`` environment-variable family (renaming an env var breaks
#: every script and shell profile that exports it).
LEGACY_BY_REFERENCE = (
    re.compile(r"improve-imgsli-internal-docs", re.IGNORECASE),
    re.compile(r"github\.com/Loganavter/Improve-ImgSLI", re.IGNORECASE),
    re.compile(r"raw\.githubusercontent\.com", re.IGNORECASE),
    re.compile(r"improve-imgsli\.ru", re.IGNORECASE),
    re.compile(r"IMPROVE_IMGSLI_", re.IGNORECASE),
)

#: Files (and one file name) that must keep the old spelling, with the reason.
#: A new entry needs a reason of the same kind — "it was easier" is not one.
KEEPERS: dict[str, str] = {
    # -- the identity itself -------------------------------------------------
    "src/core/log_names.py": (
        "owns LEGACY_LOGGER_NAME / LEGACY_LOG_DIR_NAME; every other module "
        "imports them instead of spelling the old name"
    ),
    "src/core/secret_store.py": (
        "LEGACY_KEYRING_SCHEMA / _LEGACY_APP_DIR_NAME: the pre-rename keyring "
        "entry and secrets dir are read (and cleared) so an upgrade keeps the "
        "stored key — RELEASE.md §7 technical identity"
    ),
    "src/core/settings_migration.py": (
        "LEGACY_SETTINGS_ORG / LEGACY_SETTINGS_APP: the QSettings pair an "
        "upgrade copies from, once, at startup"
    ),
    # -- window / desktop identity ------------------------------------------
    "src/__main__.py": (
        "WM_CLASS trio (RESOURCE_NAME, argv[0]) plus setDesktopFileName: the "
        "AUR desktop file still ships StartupWMClass=improve-imgsli and "
        "pkgname=improve-imgsli, so renaming one side breaks taskbar grouping; "
        "the file is outside this task's scope"
    ),
    "build/AUR-template/blinktable.desktop": (
        "StartupWMClass=improve-imgsli pairs with src/__main__.py's "
        "RESOURCE_NAME, and the desktop file registers the legacy MIME type"
    ),
    # -- packaging surfaces frozen for a release ----------------------------
    "build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.yaml": (
        "Flathub app-id. docs/RELEASE.md §7: renaming it resubmits the listing "
        "and orphans installed users; the manifest also installs the legacy "
        "MIME + thumbnailer assets, and build/ci/validate_{license_files,"
        "release_metadata}.py pin this file name"
    ),
    "build/Flatpak-template/io.github.Loganavter.Improve-ImgSLI.metainfo.xml": (
        "metainfo <id> must equal the Flathub app-id, and its launchable is the "
        "installed desktop-entry id"
    ),
    "build/ci/validate_license_files.py": (
        "pins the Flatpak manifest file name as a release surface"
    ),
    "build/ci/validate_release_metadata.py": (
        "pins the metainfo/manifest file names and the GitHub tarball name "
        "(the tag archive is named after the repository)"
    ),
    "build/Windows-template/inno_setup_6.iss": (
        "Inno Setup AppId + HKCU registry keys stay on the legacy path on "
        "purpose (an upgrade must find the previous install), and the legacy "
        ".imgsli content type is still registered"
    ),
    "build/Windows-template/README.md": (
        "documents the pre-rename install folder an upgrade migrates away from"
    ),
    "build/Windows-template/licenses/WINDOWS_QT_NOTICE.txt": (
        "third-party notice naming the upstream project it was inherited from"
    ),
    # -- legacy file formats ------------------------------------------------
    "build/linux/mime/application-x-improve-imgsli.xml": (
        "legacy *.imgsli MIME registration must keep resolving"
    ),
    "build/linux/mime/application-vnd.blinktable.project+zip.xml": (
        "the current MIME page documents the legacy alias it is paired with"
    ),
    "build/linux/bin/improve-imgsli-thumbnailer": (
        "installed thumbnailer name, registered for the legacy MIME type"
    ),
    "build/linux/thumbnailers/improve-imgsli.thumbnailer": (
        "installed thumbnailer entry (TryExec/Exec) for the legacy MIME type"
    ),
    "src/services/system/windows_file_association.py": (
        "LEGACY_PROGID / LEGACY_CONTENT_TYPE: existing .imgsli associations "
        "must keep opening"
    ),
    # -- repository / tooling prose ----------------------------------------
    "src/devtools/context_cloc.py": (
        "names the git checkout directory and the cloc report, i.e. repository "
        "identity, not the product"
    ),
    "src/devtools/docs_path_baseline.txt": (
        "generated citation baseline keyed by the .cursor rule file name"
    ),
    "src/devtools/help_live.py": (
        "help-capture profile seeds the pre-rename QSettings pair that "
        "core.settings_migration imports (deliberate legacy seam)"
    ),
    "src/tabs/image_compare/tests/render/test_rhi_fallback_scenarios.py": (
        "comment illustrating a checkout path (…/Improve-ImgSLI/src); tab test, "
        "outside this task's scope"
    ),
    "src/tabs/image_compare/tests/runtime/test_page_build_spans.py": (
        "historical note quoting the pre-rename logger id a regression produced"
    ),
    "src/tabs/image_gallery/docs/investigations/"
    "plan-gallery-persistent-catalog-2026-10-21.md": (
        "dated investigation plan quoting paths as they were; docs are outside "
        "this task's scope"
    ),
    # -- MCP package (identity deliberately unchanged here) -----------------
    "mcp-server/app/catalog.py": (
        "SERVER_NAME is the MCP server id clients already configure; renaming "
        "it needs a client-config migration and the file is outside this "
        "task's scope"
    ),
    "mcp-server/app/README.md": (
        "MCP package README; still documents the pre-rename cache/log paths — "
        "STALE after this change, needs a follow-up (outside this task's file "
        "scope)"
    ),
    "mcp-server/app/__init__.py": (
        "MCP package docstring naming the app it drives (spec revision header)"
    ),
    "mcp-server/app/server.py": (
        "MCP entry point: docstring, --repo-root example path and --help text "
        "refer to the checkout directory; outside this task's scope"
    ),
    "mcp-server/requirements.txt": (
        "dependency banner naming the repo the MCP server ships in"
    ),
}


def _iter_scanned_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def _legacy_lines(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    hits: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not LEGACY_LITERAL.search(line):
            continue
        if any(blessed.search(line) for blessed in LEGACY_BY_REFERENCE):
            continue
        hits.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()[:120]}")
    return hits


def test_every_legacy_spelling_is_a_known_keeper() -> None:
    """No user-visible surface may keep the pre-rename name by accident.

    Falsification: before this, the app-data dir, the notification id, the cache
    root, the trace label and the icon key each spelled the old product name;
    nothing failed when a rename missed one, so the product shipped two names.
    """
    offenders: list[str] = []
    for path in _iter_scanned_files():
        relative = str(path.relative_to(REPO_ROOT))
        if relative in KEEPERS:
            continue
        offenders.extend(_legacy_lines(path))
    assert not offenders, (
        "pre-rename product name outside the keeper list — derive it from "
        "core.log_names.APP_NAME, or add the file to KEEPERS with a reason:\n  "
        + "\n  ".join(offenders)
    )


def test_no_pre_rename_file_name_survives_unnoticed() -> None:
    """Installed file names are a user-visible surface too (app-id, assets)."""
    offenders: list[str] = []
    for path in _iter_scanned_files():
        relative = str(path.relative_to(REPO_ROOT))
        if LEGACY_LITERAL.search(path.name) and relative not in KEEPERS:
            offenders.append(relative)
    assert not offenders, (
        "file name carries the pre-rename product name and is not a keeper:\n  "
        + "\n  ".join(offenders)
    )


def test_every_keeper_still_exists() -> None:
    """A keeper that was fixed (or deleted) must lose its exemption."""
    stale = [
        relative
        for relative in KEEPERS
        if not (REPO_ROOT / relative).exists()
    ]
    assert not stale, "keepers no longer on disk — drop their exemption: " + ", ".join(
        stale
    )


def test_the_notification_identity_is_the_app_name(monkeypatch) -> None:
    """A notification must name the app that is installed, not its old self."""
    assert notifications.DEFAULT_APP_ID == APP_NAME
    assert notifications.NotificationService().app_name == APP_NAME

    # A sandboxed install publishes its own desktop id — that still wins.
    monkeypatch.setenv("FLATPAK_ID", "io.github.Loganavter.Improve-ImgSLI")
    assert (
        notifications.NotificationService()._detect_app_id()
        == "io.github.Loganavter.Improve-ImgSLI"
    )


def test_the_settings_scope_is_the_app_name() -> None:
    """The MCP's headless settings writer must land in the app's own scope.

    ``mcp-server/app/backend.py`` cannot import the app, so it derives the
    ``QSettings`` pair from ``APP_NAME``. This pin is what keeps that derivation
    true: if the app ever separates its settings identity from ``APP_NAME``, the
    writer needs an explicit seam instead of a silent no-op write.
    """
    from core.plugin_system.settings import SETTINGS_APP, SETTINGS_ORG

    assert (SETTINGS_ORG, SETTINGS_APP) == (APP_NAME, APP_NAME)


def test_the_trace_process_name_is_the_app_name() -> None:
    """Perfetto shows the product name; ``process_name`` follows ``APP_NAME``."""
    events = build_trace([])

    process_names = [
        event["args"]["name"]
        for event in events
        if event.get("name") == "process_name" and event.get("ph") == "M"
    ]
    assert process_names == [APP_NAME]


def _force_plain_cache_location(monkeypatch) -> None:
    """Drive ``_cache_root`` through its no-Qt-application branch."""
    monkeypatch.setattr(project_package, "_qt_cache_location", lambda: "")


def test_the_cache_root_is_named_after_the_app(tmp_path, monkeypatch) -> None:
    """Every gallery/project cache hangs off one root, under the current name."""
    monkeypatch.delenv("IMGSLI_PROJECT_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    _force_plain_cache_location(monkeypatch)

    root = tmp_path / "cache" / APP_NAME
    assert project_package._cache_root() == root
    cache_dir = project_package.project_cache_dir(tmp_path / "proj")
    assert cache_dir.parent == root / "projects"
    assert len(cache_dir.name) == 24


def test_the_cache_root_falls_back_to_the_pre_rename_tree(tmp_path, monkeypatch) -> None:
    """An upgrade keeps its extracted projects: the old tree is read, not moved."""
    monkeypatch.delenv("IMGSLI_PROJECT_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    _force_plain_cache_location(monkeypatch)
    legacy = tmp_path / "cache" / LEGACY_LOG_DIR_NAME
    legacy.mkdir(parents=True)

    assert project_package._cache_root() == legacy
    # ...and the current root wins the moment it exists, leaving the old alone.
    (tmp_path / "cache" / APP_NAME).mkdir()
    assert project_package._cache_root() == tmp_path / "cache" / APP_NAME
    assert legacy.is_dir()


def test_the_explicit_project_cache_override_still_wins(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("IMGSLI_PROJECT_CACHE", str(tmp_path / "explicit"))
    (tmp_path / "cache" / LEGACY_LOG_DIR_NAME).mkdir(parents=True)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    assert project_package._cache_root() == tmp_path / "explicit"


def test_the_icon_service_key_is_the_app_name(monkeypatch) -> None:
    """The toolkit caches icon services by name: one key, the current one."""
    seen: list[str] = []

    class _Service:
        def get_icon(self, name):
            return f"icon:{name}"

    def _fake(name, **kwargs):
        seen.append(name)
        return _Service()

    monkeypatch.setattr(icon_manager, "get_icon_service", _fake)

    assert icon_manager.get_app_icon(icon_manager.AppIcon.SETTINGS) == (
        "icon:settings.svg"
    )
    assert seen == [APP_NAME]
