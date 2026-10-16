#!/usr/bin/env python3
"""Comment/docstring CITATION checker — stale-citation (outdated-claim) detection.

An outdated comment is a correctness defect: agents execute prose as truth. This
tool scans the **comments and docstrings** of a Python tree and flags citations
whose *concrete, resolvable* claims no longer hold — a ``path.py:NNN`` that
points nowhere, a line number past end-of-file, a backticked symbol that names
nothing in the tree.

It deliberately answers only questions with a mechanical yes/no. It does **not**
read like a proofreader.

Resolvers (v2)
--------------
1. ``path.py:NNN`` — regex ``([A-Za-z0-9_][A-Za-z0-9_./\\-]*\\.py):(\\d+)``.
   The candidate is resolved relative to (a) the citing file's directory,
   (b) the repo root, (c) the repo ``src/``. When none of those exist, a
   **basename index** (``basename -> [paths]`` built over every ``.py`` under
   the scanned roots) is consulted: exactly one match resolves the citation and
   the line bound below is enforced against it; zero matches keep
   ``unresolved-path``; *several* matches also keep ``unresolved-path`` and
   append ``[ambiguous basename …]`` to the snippet so the fix is obvious. A
   resolved file must satisfy ``NNN <= number_of_lines(file)``, else
   ``line-out-of-range``.
2. Backticked symbols — regex ``` `([A-Za-z_][A-Za-z0-9_.]*)` ```. A token is
   first passed through the **shape filter** (v2, below); non-symbol shapes are
   dropped before resolution. For the survivors, with
   ``base = text.split('.')[0]``, resolved when ``base`` is in the repo's
   defined-name index (``ast``: ``FunctionDef`` / ``AsyncFunctionDef`` /
   ``ClassDef`` names, ``Name.id``, ``Attribute.attr`` across every ``.py``
   under the target roots **plus every ``--extra-root DIR``**) **or** in the
   external allowlist (Python builtins + common stdlib + a broad PySide6 list;
   extend with ``--allow FILE``, one name per line). Otherwise
   ``unknown-symbol``. ``--extra-root`` contributes *names only*: comments and
   docstrings under it are never scanned, so a sibling checkout (e.g.
   ``../sli-ui-toolkit/src``) can supply symbol definitions without adding its
   own findings.
3. Session ids ``plan-…`` / ``inv-…`` — **off by default** (the artifacts that
   own those ids live in a sibling docs repo that is not readable here, so ids
   are not resolvable in this checkout). With ``--ids-file FILE`` (one id per
   line) the resolver turns on: ids absent from the file are reported as
   ``unverifiable-id`` and fail the run.

Shape filter — v2 false-positive reduction
------------------------------------------
v1 reported 769 ``unknown-symbol`` findings over ``src/`` and the majority were
false positives: the defined-name index only sees this checkout, so a backticked
env var, theme token, directory name, shader filename or external toolkit symbol
all read as "unknown". v2 skips a token *without resolving or flagging it* when
its shape proves it is not a code symbol:

* **ALL-CAPS constants / env vars** — ``^[A-Z][A-Z0-9_]*$`` (``UI_NAV_DEBUG``,
  ``MAX_SUPPORTED_IMAGE_DIMENSION``).
* **paths / directory names / filenames** — anything containing ``/`` or ending
  in a known doc/asset extension (``.py``, ``.md``, ``.png``, ``.json``,
  ``.yaml``, ``.qss``, ``.svg``, …).
* **theme / config tokens** — ``>= 3`` dotted segments
  (``gallery.card.border``).
* **external-module symbols** — base segment in
  ``{PySide6, Qt, sli_ui_toolkit, numpy, PIL, pyvips, shiboken6}``.
* **phrases** — anything containing whitespace: impossible for the regex to
  match; asserted in code rather than silently trusted.

Residual false-positive classes this filter does **not** neutralise (documented,
not hidden): single-word prose in backticks (``gallery``, ``is``, ``pass``,
``none``), directory names written without a slash (``use_cases``), shader
filenames whose suffix is not in the extension list (``mag.frag``), GLSL
identifiers (``uvRect1``, ``sampler2DArray``), 2-segment scope tokens
(``surface.background``), and external symbols not supplied via
``--extra-root`` / ``--allow``.

Honest scope — v1 is explicitly OUT of scope for
------------------------------------------------
* **Semantic staleness / prose correctness** (a comment that truthfully names a
  file but describes the wrong behavior, or a deleted feature still described).
* **Stale numeric counts** ("the 7 passes", "3 call sites").
* Bare filename citations without a line number (`` `store.py` ``): the path
  resolver only fires on ``:NNN`` and file-like backticks are skipped by the
  symbol resolver, so these are neither checked nor reported.
* Ambiguous basename citations: when several files share the cited basename and
  no primary base resolves, the path stays ``unresolved-path`` (the snippet
  names the collision) — fix the comment by adding the path.
* Symbols defined outside the target roots and outside the allowlist (toolkit /
  third-party names) are false positives by construction — index the toolkit
  with ``--extra-root`` or extend ``--allow``.
* The checker verifies that a cited *thing exists*; it does not verify that the
  cited line still *contains* what the comment claims.

Findings are a ratchet, not a truth oracle: use ``--baseline`` and grow the
allowlist rather than reflowing comments to please the tool.

Usage::

    python3 scripts/check_comment_citations.py                 # default root: src/
    python3 scripts/check_comment_citations.py --root src --json report.json
    python3 scripts/check_comment_citations.py --extra-root ../sli-ui-toolkit/src
    python3 scripts/check_comment_citations.py --allow names.txt --baseline .cc_baseline
    python3 scripts/check_comment_citations.py --ids-file ids.txt

Exit code is ``1`` when findings remain after the baseline suppresses accepted
ones, otherwise ``0``. Stdlib only; importable (``main(argv=None) -> int``,
no import-time side effects).
"""

from __future__ import annotations

import argparse
import ast
import builtins
import io
import json
import os
import re
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

#: Repo root, derived from this script's location (``<repo>/scripts/<this>``).
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Default scan root: the production tree.
DEFAULT_ROOT = REPO_ROOT / "src"

#: Secondary resolution base for ``path.py:NNN`` citations.
SRC_ROOT = REPO_ROOT / "src"

# --- kinds -----------------------------------------------------------------

KIND_UNRESOLVED_PATH = "unresolved-path"
KIND_LINE_OUT_OF_RANGE = "line-out-of-range"
KIND_UNKNOWN_SYMBOL = "unknown-symbol"
KIND_UNVERIFIABLE_ID = "unverifiable-id"

#: Kinds that make the run exit non-zero. ``unverifiable-id`` only fails when
#: the id resolver is enabled (``--ids-file``); on its own it is advisory.
FAILING_KINDS = frozenset(
    {KIND_UNRESOLVED_PATH, KIND_LINE_OUT_OF_RANGE, KIND_UNKNOWN_SYMBOL}
)


def is_failing(kind: str, ids_enabled: bool) -> bool:
    """Whether ``kind`` should make the run exit non-zero."""
    if kind in FAILING_KINDS:
        return True
    return kind == KIND_UNVERIFIABLE_ID and ids_enabled

# --- regexes ---------------------------------------------------------------

#: ``path/to/module.py:123`` (verbatim v1 spec regex).
PATH_REF_RE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./\-]*\.py):(\d+)")

#: ``\`symbol.or.attr\```.
SYMBOL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)`")

#: Session ids owned by the sibling docs repo (``plan-…`` / ``inv-…``).
ID_RE = re.compile(r"\b((?:plan|inv)-[A-Za-z0-9][A-Za-z0-9_.\-]*)")

#: ALL-CAPS tokens (env vars / module-level constants) are never code symbols.
ALL_CAPS_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

#: Directories never walked.
SKIP_DIRS = frozenset(
    {
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "build",
        "dist",
        ".tox",
        ".eggs",
        "site-packages",
    }
)

#: Backticked tokens ending in one of these are filenames, not symbols.
_FILE_EXTENSIONS = (
    ".py", ".pyi", ".pyx", ".md", ".rst", ".txt", ".json", ".jsonl", ".yaml",
    ".yml", ".toml", ".ini", ".cfg", ".qss", ".sh", ".bash", ".bat", ".ps1",
    ".desktop", ".service", ".timer", ".fish", ".png", ".jpg", ".jpeg", ".svg",
    ".webp", ".gif", ".ico", ".csv", ".xml", ".html", ".css", ".js", ".ts",
    ".tsx", ".jsx", ".cpp", ".cc", ".h", ".hpp", ".c", ".rs", ".go", ".java",
    ".kt", ".sql", ".lock", ".log",
    # shaders / GPU assets (cited as ``mag.frag`` in prose, not symbols)
    ".frag", ".vert", ".geom", ".comp", ".tesc", ".tese", ".glsl", ".qsb",
    ".spv", ".wgsl",
)

#: Placeholder-style identifiers (``img_1``, ``series_N``, ``uvRect1``): a
#: template name, not a symbol that can go stale.
_PLACEHOLDER_RE = re.compile(
    r"^(?:[a-z][A-Za-z]*\d+|.*_[A-Z0-9]+|.*_\d+)$"
)

#: Common stdlib *symbols* (``sys.stdlib_module_names`` only gives modules).
_STDLIB_SYMBOLS = (
    "AbstractContextManager", "AbstractEventLoop", "Any", "Annotated", "Callable",
    "ChainMap", "ClassVar", "Counter", "Decimal", "Deque", "Dict", "Enum",
    "Final", "Fraction", "FrozenSet", "Generic", "IO", "IntEnum", "Iterable",
    "Iterator", "Literal", "Mapping", "MutableMapping", "NamedTuple", "Optional",
    "OrderedDict", "ParamSpec", "Protocol", "Sequence", "Set", "TextIO",
    "Type", "TypeVar", "TypedDict", "Union", "abstractmethod", "annotations",
    "ascii", "asyncio", "atexit", "base64", "cached_property", "collections",
    "contextlib", "contextmanager", "csv", "dataclass", "dataclasses", "datetime",
    "defaultdict", "deque", "enum", "functools", "getattr", "glob", "hashlib",
    "hmac", "inspect", "int", "io", "itertools", "json", "linecache", "logging",
    "lru_cache", "math", "mock", "namedtuple", "operator", "os", "partial",
    "pathlib", "pickle", "pprint", "queue", "random", "re", "reduce", "resource",
    "shutil", "signal", "socket", "sqlite3", "statistics", "string", "struct",
    "subprocess", "sys", "tempfile", "textwrap", "threading", "time", "timezone",
    "traceback", "types", "typing", "unittest", "urllib", "uuid", "warnings",
    "weakref", "wraps", "xml", "zipfile", "zoneinfo",
)

#: Dunders routinely named in comments.
_DUNDER_SYMBOLS = (
    "__all__", "__call__", "__class__", "__contains__", "__delattr__", "__dict__",
    "__doc__", "__enter__", "__eq__", "__exit__", "__file__", "__getattr__",
    "__getitem__", "__hash__", "__init__", "__iter__", "__len__", "__main__",
    "__module__", "__name__", "__new__", "__next__", "__post_init__", "__repr__",
    "__setitem__", "__slots__", "__str__",
)

#: Broad PySide6/Qt surface (classes, modules, decorators, functions) named in
#: app comments. Deliberately generous: a miss here is a false positive, and a
#: false positive makes the checker untrustworthy faster than a false negative.
_PYSIDE6_SYMBOLS = (
    # --- QtCore ---------------------------------------------------------
    "QAbstractAnimation", "QAbstractEventDispatcher", "QAbstractItemModel",
    "QAbstractListModel", "QAbstractTableModel", "QAnimationGroup", "QBitArray",
    "QBuffer", "QByteArray", "QByteArrayList", "QChar", "QChildEvent",
    "QCoreApplication", "QDataStream", "QDate", "QDateTime", "QDeadlineTimer",
    "QDir", "QDirIterator", "QDynamicPropertyChangeEvent", "QEasingCurve",
    "QElapsedTimer", "QEvent", "QEventLoop", "QFile", "QFileInfo",
    "QFileSystemWatcher", "QGuiApplication", "QIODevice", "QItemSelectionModel",
    "QJsonArray", "QJsonDocument", "QJsonObject", "QJsonParseError",
    "QJsonValue", "QLibraryInfo", "QLine", "QLineF", "QLocale",
    "QLoggingCategory", "QMargins", "QMarginsF", "QMetaMethod", "QMetaObject",
    "QMetaProperty", "QModelIndex", "QMutex", "QMutexLocker", "QObject",
    "QParallelAnimationGroup", "QPauseAnimation", "QPersistentModelIndex",
    "QPoint", "QPointF", "QProcess", "QProcessEnvironment", "QPropertyAnimation",
    "QRandomGenerator", "QRect", "QRectF", "QRecursiveMutex", "QRegularExpression",
    "QRegularExpressionMatch", "QRegularExpressionMatchIterator", "QRunnable",
    "QSaveFile", "QSemaphore", "QSequentialAnimationGroup", "QSettings",
    "QSignalBlocker", "QSignalMapper", "QSize", "QSizeF", "QSizePolicy",
    "QSocketNotifier", "QSortFilterProxyModel", "QStandardPaths", "QStringListModel",
    "QSysInfo", "QTextStream", "QThread", "QThreadPool", "QTime", "QTimeZone",
    "QTimer", "QTimerEvent", "QTranslator", "QUrl", "QUrlQuery", "QUuid",
    "QVariant", "QVariantAnimation", "QWaitCondition", "QXmlStreamReader",
    "QXmlStreamWriter", "Property", "Signal", "Slot", "Qt", "pyqtProperty",
    "pyqtSignal", "pyqtSlot", "qCritical", "qDebug", "qFatal", "qInfo",
    "qWarning", "QAbstractNativeEventFilter", "QOperatingSystemVersion",
    # --- QtGui ----------------------------------------------------------
    "QAccessible", "QAccessibleEvent", "QAction", "QActionGroup", "QBitmap",
    "QBrush", "QClipboard", "QColor", "QColorConstants", "QColorSpace",
    "QContextMenuEvent", "QCursor", "QDesktopServices", "QDoubleValidator",
    "QDrag", "QDragEnterEvent", "QDragLeaveEvent", "QDragMoveEvent",
    "QDropEvent", "QEnterEvent", "QFocusEvent", "QFont", "QFontDatabase",
    "QFontMetrics", "QFontMetricsF", "QGlyphRun", "QHideEvent", "QHoverEvent",
    "QIcon", "QImage", "QImageReader", "QImageWriter", "QInputEvent",
    "QInputMethod", "QIntValidator", "QKeyEvent", "QKeySequence", "QMatrix4x4",
    "QMouseEvent", "QMoveEvent", "QNativeGestureEvent", "QOpenGLBuffer",
    "QOpenGLContext", "QOpenGLFunctions", "QOpenGLShader", "QOpenGLShaderProgram",
    "QOpenGLVertexArrayObject", "QOpenGLWindow", "QPaintDevice", "QPaintEngine",
    "QPaintEvent", "QPainter", "QPainterPath", "QPainterPathStroker", "QPalette",
    "QPdfWriter", "QPen", "QPicture", "QPixmap", "QPlatformSurfaceEvent",
    "QPolygon", "QPolygonF", "QQuaternion", "QRasterWindow", "QRawFont", "QRegion",
    "QResizeEvent", "QScreen", "QScrollEvent", "QShortcut", "QShowEvent",
    "QStaticText", "QSurface", "QSurfaceFormat", "QTabletEvent", "QTextBlock",
    "QTextBlockFormat", "QTextCharFormat", "QTextCursor", "QTextDocument",
    "QTextLayout", "QTextLine", "QTextOption", "QTransform", "QValidator",
    "QVector2D", "QVector3D", "QVector4D", "QWheelEvent", "QWindow",
    "QVulkanInstance", "QRhi", "QRhiBuffer", "QRhiCommandBuffer",
    "QRhiComputePipeline", "QRhiGraphicsPipeline", "QRhiRenderBuffer",
    "QRhiRenderPassDescriptor", "QRhiResourceUpdateBatch", "QRhiSampler",
    "QRhiShaderResourceBindings", "QRhiShaderStage", "QRhiSwapChain",
    "QRhiTexture", "QRhiTextureRenderTarget", "QRhiVertexInputAttribute",
    "QRhiVertexInputBinding", "QRhiVertexInputLayout", "QRhiWidget", "QShader",
    "QShaderCode", "QShaderDescription",
    # --- QtWidgets ------------------------------------------------------
    "QAbstractButton", "QAbstractItemView", "QAbstractScrollArea",
    "QAbstractSlider", "QAbstractSpinBox", "QApplication", "QBoxLayout",
    "QButtonGroup", "QCalendarWidget", "QCheckBox", "QColorDialog", "QComboBox",
    "QDataWidgetMapper", "QDialog", "QDialogButtonBox", "QDockWidget",
    "QDoubleSpinBox", "QErrorMessage", "QFileDialog", "QFocusFrame",
    "QFontComboBox", "QFontDialog", "QFormLayout", "QFrame", "QGraphicsBlurEffect",
    "QGraphicsColorizeEffect", "QGraphicsDropShadowEffect", "QGraphicsEffect",
    "QGraphicsItem", "QGraphicsLineItem", "QGraphicsObject", "QGraphicsOpacityEffect",
    "QGraphicsPathItem", "QGraphicsPixmapItem", "QGraphicsProxyWidget",
    "QGraphicsRectItem", "QGraphicsScene", "QGraphicsTextItem", "QGraphicsView",
    "QGraphicsWidget", "QGridLayout", "QGroupBox", "QHBoxLayout", "QHeaderView",
    "QInputDialog", "QItemDelegate", "QKeySequenceEdit", "QLabel", "QLayout",
    "QLineEdit", "QListView", "QListWidget", "QListWidgetItem", "QMainWindow",
    "QMdiArea", "QMenu", "QMenuBar", "QMessageBox", "QPlainTextEdit",
    "QProgressBar", "QProgressDialog", "QPushButton", "QRadioButton",
    "QRubberBand", "QScrollArea", "QScrollBar", "QSizeGrip", "QSlider",
    "QSpacerItem", "QSpinBox", "QSplashScreen", "QSplitter", "QStackedLayout",
    "QStackedWidget", "QStatusBar", "QStyle", "QStyledItemDelegate",
    "QStyleFactory", "QStyleOption", "QStyleOptionButton", "QStyleOptionViewItem",
    "QSystemTrayIcon", "QTabBar", "QTabWidget", "QTableView", "QTableWidget",
    "QTableWidgetItem", "QTextBrowser", "QTextEdit", "QToolBar", "QToolButton",
    "QToolTip", "QTreeView", "QTreeWidget", "QTreeWidgetItem", "QUndoCommand",
    "QUndoStack", "QUndoView", "QVBoxLayout", "QWhatsThis", "QWidget",
    "QWizard", "QWizardPage",
)

#: A few well-known third-party names that keep showing up in this tree's
#: comments; extend per project with ``--allow``.
_KNOWN_THIRD_PARTY_SYMBOLS = (
    "PySide6", "shiboken6", "numpy", "pyvips", "PIL", "Image", "imagecodecs",
    "pytest", "loguru", "rich",
)

#: Names that are not builtins but read as "well-known" in comments.
_COMMON_SYMBOLS = ("self", "cls", "mcs", "kwargs", "args")

#: Base module segments owned by external packages: any backticked token whose
#: first dotted segment is one of these is resolved (not a stale in-tree name).
EXTERNAL_MODULE_PREFIXES = frozenset(
    {"PySide6", "Qt", "sli_ui_toolkit", "numpy", "PIL", "pyvips", "shiboken6"}
)

_SNIPPET_LIMIT = 160


@dataclass(frozen=True, slots=True)
class Finding:
    """One stale citation: ``file`` is repo-root-relative when possible."""

    file: str
    line: int
    kind: str
    snippet: str
    #: The concrete offending token (base symbol / cited path / id) — the thing
    #: an allowlist or a human acts on. Empty for kinds without one.
    token: str = ""

    def key(self) -> str:
        """Baseline key: ``file:line:kind``."""
        return f"{self.file}:{self.line}:{self.kind}"


# --- discovery / parsing ---------------------------------------------------


def discover_python_files(roots: list[Path]) -> list[Path]:
    """Return a sorted, de-duplicated list of ``.py`` files under ``roots``."""
    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        root = Path(root)
        if root.is_file():
            if root.suffix == ".py" and root not in seen:
                seen.add(root)
                out.append(root)
            continue
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                d
                for d in dirnames
                if not d.startswith(".") and d not in SKIP_DIRS
            )
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                path = Path(dirpath) / name
                if path not in seen:
                    seen.add(path)
                    out.append(path)
    return sorted(out, key=lambda p: p.as_posix())


def _docstring_spans(tree: ast.AST):
    """Yield ``(start_line, end_line)`` for every docstring in ``tree``."""
    containers = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, containers):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            value = first.value
            start = getattr(value, "lineno", None)
            end = getattr(value, "end_lineno", None)
            if start and end:
                yield start, end


def scan_python_file(path: Path) -> tuple[set[str], dict[int, str]]:
    """Return ``(defined_names, {lineno: scanned_text})`` for one file.

    ``scanned_text`` merges comment text and docstring source lines; the code
    body itself is never scanned.
    """
    names: set[str] = set()
    try:
        source = path.read_bytes().decode("utf-8", "replace")
    except OSError:
        return names, {}

    tree: ast.AST | None
    try:
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)

    parts: dict[int, list[str]] = {}
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                parts.setdefault(token.start[0], []).append(token.string)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass

    if tree is not None:
        source_lines = source.splitlines()
        for start, end in _docstring_spans(tree):
            for lineno in range(max(1, start), min(end, len(source_lines)) + 1):
                parts.setdefault(lineno, []).append(source_lines[lineno - 1])

    return names, {lineno: "\n".join(chunks) for lineno, chunks in parts.items()}


# --- allowlist / index -----------------------------------------------------


def default_symbol_allowlist() -> set[str]:
    """Builtins + stdlib + broad PySide6 (+ a few common third-party names)."""
    names = set(dir(builtins))
    names.update(getattr(sys, "stdlib_module_names", ()))
    names.update(_STDLIB_SYMBOLS)
    names.update(_DUNDER_SYMBOLS)
    names.update(_PYSIDE6_SYMBOLS)
    names.update(_KNOWN_THIRD_PARTY_SYMBOLS)
    names.update(_COMMON_SYMBOLS)
    return names


def load_name_file(path: Path) -> set[str]:
    """Read one name/id per line; ``#`` comments and blanks are ignored."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    names: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line)
    return names


def load_baseline(path: Path) -> set[str]:
    """Read ``file:line:kind`` keys; ``#`` comments and blanks are ignored."""
    keys: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return keys
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        keys.add(line)
    return keys


# --- resolvers -------------------------------------------------------------


def _display_path(path: Path) -> str:
    """Repo-root-relative when under the repo, else the path as given."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _is_file_like(token: str) -> bool:
    """True for backticked tokens that name a file, not a symbol."""
    lowered = token.lower()
    return "/" in token or lowered.endswith(_FILE_EXTENSIONS)


def is_symbol_shaped(token: str) -> bool:
    """Whether ``token`` looks enough like a code symbol to resolve/flag it.

    Shape-only filter (no index access): a ``False`` result means the token is
    skipped silently — it can never be a stale in-tree symbol by construction
    (env var, theme token, path, external-module name, phrase). See the module
    docstring "Shape filter" section for the residual false-positive classes
    this deliberately leaves in place.
    """
    # The symbol regex cannot match whitespace; assert rather than trust it.
    assert not any(ch.isspace() for ch in token), f"phrase token: {token!r}"
    if _is_file_like(token):
        return False
    if ALL_CAPS_RE.match(token):
        return False
    # A bare lowercase word (``gallery``, ``is``, ``pass``) is prose or a module/
    # package name — module/package names are indexed, so a real one resolves;
    # this shape rule only stops prose words from being flagged as symbols.
    if "." not in token and "_" not in token and token.islower():
        return False
    if _PLACEHOLDER_RE.match(token):
        return False
    if len(token.split(".")) >= 3:
        return False
    return token.split(".")[0] not in EXTERNAL_MODULE_PREFIXES


def _path_candidates(raw: str, citing: Path) -> list[Path]:
    """Resolve ``raw`` against (a) citing dir, (b) repo root, (c) repo src/."""
    candidates: list[Path] = []
    for base in (citing.parent, REPO_ROOT, SRC_ROOT):
        try:
            candidate = Path(os.path.normpath(base / raw))
        except (OSError, ValueError):
            continue
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _resolve_path_ref(
    raw: str,
    citing: Path,
    basename_index: dict[str, list[Path]],
) -> tuple[list[Path], int]:
    """Resolve a ``path.py`` citation.

    Returns ``(resolved_files, ambiguous_count)``. Primary bases first; then the
    basename index: a single name match resolves, several are reported as an
    ambiguity (the caller keeps ``unresolved-path`` and names the collision).
    """
    primary = [c for c in _path_candidates(raw, citing) if c.is_file()]
    if primary:
        return primary, 0
    matches = basename_index.get(os.path.basename(raw), [])
    if len(matches) == 1:
        return list(matches), 0
    return [], len(matches)


def _count_lines(path: Path, cache: dict[Path, int]) -> int:
    count = cache.get(path)
    if count is None:
        try:
            count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            count = 0
        cache[path] = count
    return count


def _snippet(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) > _SNIPPET_LIMIT:
        return flat[: _SNIPPET_LIMIT - 3] + "..."
    return flat


def citations_in_text(
    text: str,
    line: int,
    citing: Path,
    index: set[str],
    allowlist: set[str],
    known_ids: set[str] | None,
    line_counts: dict[Path, int],
    basename_index: dict[str, list[Path]] | None = None,
) -> list[Finding]:
    """Extract every finding from one scanned line of comment/docstring text."""
    found: list[Finding] = []
    display = _display_path(citing)
    snippet = _snippet(text)
    basenames = basename_index or {}

    for match in PATH_REF_RE.finditer(text):
        raw, number = match.group(1), int(match.group(2))
        resolved, ambiguous = _resolve_path_ref(raw, citing, basenames)
        if resolved:
            if not any(number <= _count_lines(c, line_counts) for c in resolved):
                found.append(
                    Finding(display, line, KIND_LINE_OUT_OF_RANGE, snippet, raw)
                )
        elif ambiguous > 1:
            note = f"{snippet} [ambiguous basename: {ambiguous} matches]"
            found.append(
                Finding(display, line, KIND_UNRESOLVED_PATH, note, raw)
            )
        else:
            found.append(
                Finding(display, line, KIND_UNRESOLVED_PATH, snippet, raw)
            )

    for match in SYMBOL_RE.finditer(text):
        raw = match.group(1)
        if not is_symbol_shaped(raw):
            continue
        base = raw.split(".")[0]
        if not base:
            continue
        if base in index or base in allowlist:
            continue
        found.append(Finding(display, line, KIND_UNKNOWN_SYMBOL, snippet, base))

    if known_ids is not None:
        for match in ID_RE.finditer(text):
            if match.group(1) not in known_ids:
                found.append(
                    Finding(
                        display,
                        line,
                        KIND_UNVERIFIABLE_ID,
                        snippet,
                        match.group(1),
                    )
                )

    return found


def collect_findings(
    roots: list[Path],
    allowlist: set[str] | None = None,
    known_ids: set[str] | None = None,
    extra_roots: list[Path] | None = None,
) -> list[Finding]:
    """Scan ``roots`` and return findings sorted by ``(file, line, kind, snippet)``.

    ``extra_roots`` contribute to the defined-name index **only** — their
    comments/docstrings are never scanned, so external checkouts (e.g. the
    sibling ``sli-ui-toolkit``) can resolve in-tree ``unknown-symbol``
    findings without importing findings of their own.
    """
    allow = default_symbol_allowlist()
    if allowlist is not None:
        # ``--allow`` EXTENDS the builtins/stdlib/PySide6 defaults (a lane
        # allowlist should not have to re-list ``print``/``Counter``/Qt names).
        allow |= set(allowlist)
    files = discover_python_files(roots)

    index: set[str] = set()
    texts: dict[Path, dict[int, str]] = {}
    basename_index: dict[str, list[Path]] = {}
    for path in files:
        names, lines = scan_python_file(path)
        index.update(names)
        # Module/package names are cited in prose too (``metric_scores``,
        # ``use_cases``); index the file stem so a module reference resolves.
        index.add(path.stem)
        basename_index.setdefault(path.name, []).append(path)
        if lines:
            texts[path] = lines

    # Directory / package names under the scanned + extra roots are legitimate
    # prose references (``background_parts``, ``image_compare``) — index them so
    # they are not mistaken for stale symbols.
    for root in list(roots) + list(extra_roots or []):
        root = Path(root)
        if not root.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(root):
            for name in dirnames:
                if not name.startswith(".") and name not in SKIP_DIRS:
                    index.add(name)

    for path in discover_python_files(list(extra_roots or [])):
        names, _ = scan_python_file(path)
        index.update(names)
        index.add(path.stem)

    line_counts: dict[Path, int] = {}
    findings: set[Finding] = set()
    for path in sorted(texts, key=lambda p: p.as_posix()):
        for lineno in sorted(texts[path]):
            findings.update(
                citations_in_text(
                    texts[path][lineno],
                    lineno,
                    path,
                    index,
                    allow,
                    known_ids,
                    line_counts,
                    basename_index,
                )
            )

    return sorted(findings, key=lambda f: (f.file, f.line, f.kind, f.snippet))


# --- CLI -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_comment_citations.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        action="append",
        metavar="DIR",
        help="directory (or .py file) to scan; repeatable (default: the repo src/)",
    )
    parser.add_argument(
        "--extra-root",
        action="append",
        dest="extra_root",
        metavar="DIR",
        help=(
            "directory (or .py file) whose names feed the symbol index only; "
            "its comments are never scanned (repeatable)"
        ),
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        metavar="PATH",
        help="write findings as JSON to PATH",
    )
    parser.add_argument(
        "--allow",
        dest="allow_path",
        metavar="FILE",
        help="extra allowed symbol names, one per line",
    )
    parser.add_argument(
        "--ids-file",
        dest="ids_path",
        metavar="FILE",
        help="enable the id resolver; ids listed here are known",
    )
    parser.add_argument(
        "--baseline",
        dest="baseline_path",
        metavar="FILE",
        help="accepted findings (file:line:kind), one per line, to suppress",
    )
    parser.add_argument(
        "--emit-allowlist",
        dest="emit_allowlist",
        metavar="PATH",
        help=(
            "write the deduped offending tokens (unknown-symbol bases) to PATH — "
            "the exact names an --allow file must contain — and exit"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    roots = [Path(r) for r in (args.root or [])] or [DEFAULT_ROOT]
    extra_roots = [Path(r) for r in (args.extra_root or [])]
    allowlist = default_symbol_allowlist()
    if args.allow_path:
        allowlist |= load_name_file(Path(args.allow_path))
    known_ids = load_name_file(Path(args.ids_path)) if args.ids_path else None
    baseline = (
        load_baseline(Path(args.baseline_path)) if args.baseline_path else set()
    )

    findings = collect_findings(roots, allowlist, known_ids, extra_roots)
    remaining = [f for f in findings if f.key() not in baseline]

    if args.emit_allowlist:
        names = sorted(
            {
                f.token
                for f in remaining
                if f.kind == KIND_UNKNOWN_SYMBOL and f.token
            }
        )
        header = [
            "# Comment-citation checker allowlist — offending tokens that are NOT",
            "# stale repo symbols (external / runtime / GLSL identifiers / documented",
            "# labels). Generated by `--emit-allowlist`. Group entries and put a",
            "# `# reason` above them; never add a name to silence a real staleness.",
        ]
        Path(args.emit_allowlist).write_text(
            "\n".join(header + names) + "\n", encoding="utf-8"
        )
        return 0

    for finding in remaining:
        sys.stdout.write(
            f"{finding.file}:{finding.line}:{finding.kind}: {finding.snippet}\n"
        )

    if args.json_path:
        payload = [
            {
                "file": finding.file,
                "line": finding.line,
                "kind": finding.kind,
                "token": finding.token,
                "snippet": finding.snippet,
            }
            for finding in remaining
        ]
        Path(args.json_path).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    failing = [f for f in remaining if is_failing(f.kind, known_ids is not None)]
    if failing:
        counts = Counter(f.kind for f in failing)
        breakdown = ", ".join(f"{kind}={counts[kind]}" for kind in sorted(counts))
        # Flush stdout so the breakdown is the LAST line when both streams merge
        # (``... 2>&1 | tail -1``); otherwise block-buffered stdout lands after.
        sys.stdout.flush()
        sys.stderr.write(
            f"check_comment_citations: {len(failing)} finding(s): {breakdown}\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
