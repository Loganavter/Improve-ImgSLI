#!/usr/bin/env python3
"""Dev context bundle + cloc report generator (Python port of context_cloc.sh).

Builds a context bundle for Improve-ImgSLI and the optional sibling
sli-ui-toolkit checkout: git metadata, repo trees, English help files,
other ``*.md``/``*.txt`` docs, and cloc statistics tables. The external
``cloc`` binary is still required for the statistics part.

Usage:
    python src/devtools/context_cloc.py --cloc-only
    python src/devtools/context_cloc.py -o /tmp/bundle.txt
    python src/devtools/context_cloc.py --toolkit-dir ../sli-ui-toolkit

See ``./launcher.sh context --help`` for the full option set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

DEFAULT_OUTPUT = "context.txt"
DEFAULT_MAX_FILE_LINES = 800
DEFAULT_MAX_TOTAL_CHARS = 260000
DEFAULT_STATS_THRESHOLD = 8000
NO_LIMIT_CHARS = 999999999999
SHADER_EXTS = "vert,frag,comp,geom,tesc,tese,glsl,hlsl,msl,wgsl,qsb"

IGNORED_DIR_NAMES = frozenset(
    {
        ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "build", "dist", "Cache",
        "blob_storage", ".idea", ".vscode", ".codex", ".agents", ".claude",
    }
)

CLOC_EXCLUDE_DIRS = os.environ.get(
    "CLOC_EXCLUDE_DIRS",
    ".git,.venv,venv,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache,"
    "build,dist,Cache,blob_storage,.idea,.vscode,.codex,.agents,.claude",
)

IGNORE_DIR_RE = re.compile(
    r"(^|/)(\.git|\.venv|venv|__pycache__|\.pytest_cache|\.mypy_cache|"
    r"\.ruff_cache|build|dist|Cache|blob_storage|\.idea|\.vscode|\.codex|"
    r"\.agents|\.claude)(/|$)"
)
COLLECT_EXT_RE = re.compile(r"\.(md|txt)$")
LANG_EXCLUDE_RE = re.compile(
    r"_(ar|bg|cs|da|de|el|es|et|fa|fi|fr|he|hi|hu|id|it|ja|ko|lt|nl|no|"
    r"pl|pt|ro|ru|sk|sl|sv|th|tr|uk|zh|ja)(\.(md|txt))$"
)
LANG_DIR_RE = re.compile(
    r"/(ar|bg|cs|da|de|el|es|et|fa|fi|fr|he|hi|hu|id|it|ja|ko|lt|nl|no|"
    r"pl|pt_BR|pt|ro|ru|sk|sl|sv|th|tr|uk|zh)/"
)
TREE_IGNORE = (
    "*.git|.venv|venv|__pycache__|.pytest_cache|.mypy_cache|.ruff_cache|"
    "build|dist|Cache|blob_storage|.idea|.vscode|.codex|.agents|.claude|"
    "context.txt|app_context.txt|cloc.txt"
)

TABLE_RULE = "-" * 100
SUMMARY_RULE = "=" * 42


def log_step(message: str) -> None:
    print(f"[context_cloc.py] {message}", file=sys.stderr)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def relpath(base: Path, target: Path) -> str:
    return os.path.relpath(target, base)


def is_context_output(file: Path, output: Path) -> bool:
    return file.resolve(strict=False) == output.resolve(strict=False)


class ContextWriter:
    """Appends to the output file and tracks its character count."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.chars = 0

    def open(self) -> None:
        self.path.write_text("", encoding="utf-8")
        self.chars = 0

    def write_line(self, text: str = "") -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")
        self.chars += len(text) + 1

    def append_text(self, text: str) -> None:
        if text:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(text)
        self.chars = len(self.path.read_text(encoding="utf-8", errors="replace"))


def collect_file_filter(file: Path, output: Path) -> bool:
    if not file.is_file():
        return False
    if is_context_output(file, output):
        return False
    path = file.as_posix()
    if IGNORE_DIR_RE.search(path):
        return False
    if not COLLECT_EXT_RE.search(path):
        return False
    if LANG_EXCLUDE_RE.search(path):
        return False
    if LANG_DIR_RE.search(path):
        return False
    return True


def add_file(
    writer: ContextWriter,
    seen: set[str],
    repo_dir: Path,
    file: Path,
    output: Path,
    max_lines: int,
    max_chars: int,
) -> None:
    if not collect_file_filter(file, output):
        return
    repo_label = repo_dir.name
    rel = relpath(repo_dir, file)
    key = f"{repo_label}:{rel}"
    if key in seen or writer.chars >= max_chars:
        return
    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    lines = text.count("\n")
    chars = len(text)
    estimated = chars
    if lines > max_lines and lines > 0:
        estimated = chars * max_lines // lines + 300
    if writer.chars > 0 and writer.chars + estimated > max_chars:
        writer.write_line("")
        writer.write_line(
            f"--- SKIPPED: {repo_label}/{rel} (would exceed --max-chars={max_chars}) ---"
        )
        return
    seen.add(key)
    writer.write_line("")
    writer.write_line("")
    writer.write_line(f"--- FILE: {repo_label}/{rel} (lines={lines} chars={chars}) ---")
    if lines > max_lines:
        parts = text.split("\n")
        if text.endswith("\n"):
            parts = parts[:-1]
        content = ("\n".join(parts[:max_lines]) + "\n") if max_lines > 0 else ""
        writer.append_text(content)
        writer.write_line("")
        writer.write_line(
            f"--- TRUNCATED: {repo_label}/{rel} "
            f"({lines - max_lines} lines omitted; raise --max-lines to include more) ---"
        )
    else:
        content = text if text.endswith("\n") else text + "\n"
        writer.append_text(content)


def git(cwd: Path, *args: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.rstrip("\n")


def write_git_metadata(writer: ContextWriter, repo_dir: Path) -> None:
    label = repo_dir.name
    writer.write_line("")
    writer.write_line(f"## {label} git metadata")
    writer.write_line("")
    if git(repo_dir, "rev-parse", "--is-inside-work-tree") is None:
        writer.write_line(f"Not a git repository: {repo_dir}")
        return
    writer.write_line(f"Path: {repo_dir}")
    branch = git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")
    writer.write_line(f"Branch: {branch if branch is not None else '?'}")
    head = git(repo_dir, "rev-parse", "--short", "HEAD")
    writer.write_line(f"HEAD: {head if head is not None else '?'}")
    latest_tag = git(repo_dir, "describe", "--tags", "--abbrev=0")
    if latest_tag:
        writer.write_line(f"Latest tag: {latest_tag}")
    writer.write_line("")
    writer.write_line("### recent commits")
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--oneline", "-n", "15"],
        capture_output=True,
        text=True,
    )
    writer.append_text(proc.stdout if proc.returncode == 0 else "")


def _walk_entries(repo_dir: Path) -> list[str]:
    entries: list[str] = ["."]
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
        for name in sorted(dirs + files):
            rel = (Path(root) / name).relative_to(repo_dir).as_posix()
            entries.append(rel)
    return entries


def write_full_tree(writer: ContextWriter, repo_dir: Path) -> None:
    label = repo_dir.name
    writer.write_line("")
    writer.write_line(f"## {label} full tree")
    tree_bin = shutil.which("tree")
    if tree_bin:
        proc = subprocess.run(
            [tree_bin, "-a", "-I", TREE_IGNORE, "--prune"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        writer.append_text(proc.stdout if proc.returncode == 0 else "")
    else:
        lines = ["./" + entry for entry in sorted(_walk_entries(repo_dir))]
        writer.append_text("\n".join(lines) + "\n")


def _english_help_files(repo_dir: Path) -> list[Path]:
    matches: list[Path] = []
    for root, _dirs, files in os.walk(repo_dir):
        for fname in files:
            file = Path(root) / fname
            posix = file.as_posix()
            if not (
                "/resources/help/en/" in posix
                or "/help/en/" in posix
                or posix.endswith("/resources/help/tree.json")
            ):
                continue
            if fname == "tree.json" or fname.endswith((".md", ".txt")):
                matches.append(file)
    return sorted(matches, key=lambda p: p.as_posix())


def collect_english_help(
    writer: ContextWriter,
    seen: set[str],
    repo_dir: Path,
    output: Path,
    max_lines: int,
    max_chars: int,
) -> None:
    for file in _english_help_files(repo_dir):
        if file.name == "tree.json":
            if is_context_output(file, output):
                continue
            if IGNORE_DIR_RE.search(file.as_posix()):
                continue
            repo_label = repo_dir.name
            rel = relpath(repo_dir, file)
            key = f"{repo_label}:{rel}"
            if key in seen or writer.chars >= max_chars:
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            chars = len(text)
            if writer.chars > 0 and writer.chars + chars > max_chars:
                writer.write_line("")
                writer.write_line(
                    f"--- SKIPPED: {repo_label}/{rel} (would exceed --max-chars={max_chars}) ---"
                )
                continue
            seen.add(key)
            writer.write_line("")
            writer.write_line("")
            writer.write_line(
                f"--- FILE: {repo_label}/{rel} (lines={text.count(chr(10))} chars={chars}) ---"
            )
            writer.append_text(text if text.endswith("\n") else text + "\n")
        else:
            add_file(writer, seen, repo_dir, file, output, max_lines, max_chars)


def collect_text_docs(
    writer: ContextWriter,
    seen: set[str],
    repo_dir: Path,
    output: Path,
    max_lines: int,
    max_chars: int,
) -> None:
    files: list[Path] = []
    for root, dirs, fnames in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
        for fname in fnames:
            if fname.endswith((".md", ".txt")):
                files.append(Path(root) / fname)
    for file in sorted(files, key=lambda p: p.as_posix()):
        add_file(writer, seen, repo_dir, file, output, max_lines, max_chars)


def ensure_cloc(cloc_bin: str) -> bool:
    if "/" in cloc_bin:
        return os.path.isfile(cloc_bin) and os.access(cloc_bin, os.X_OK)
    return shutil.which(cloc_bin) is not None


def cloc_summary_for_path(
    cloc_bin: str,
    target: Path,
    include_ext: str = "",
    exclude_file_re: str = "",
) -> tuple[int, int, int, int] | None:
    cmd = [cloc_bin, "--quiet", "--json", f"--exclude-dir={CLOC_EXCLUDE_DIRS}"]
    if include_ext:
        cmd.append(f"--include-ext={include_ext}")
    if exclude_file_re:
        cmd.append(f"--not-match-f={exclude_file_re}")
    cmd.append(str(target))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    summary = data.get("SUM", {})

    def get(*keys: str) -> int:
        for key in keys:
            value = summary.get(key)
            if value is not None:
                return int(value)
        return 0

    return (get("nFiles", "files"), get("blank"), get("comment"), get("code"))


def cloc_target_exclude_re(output: Path) -> str:
    base = re.escape(output.name)
    return rf"(^|/)({base}|context\.txt|app_context\.txt|cloc\.txt)$"


def _top_level_dirs(directory: Path) -> list[Path]:
    out: list[Path] = []
    with os.scandir(directory) as it:
        for entry in it:
            if entry.name in IGNORED_DIR_NAMES:
                continue
            if entry.is_dir(follow_symlinks=False):
                out.append(Path(entry.path))
    return sorted(out)


def _table_row(path: str, files: int, blank: int, comment: int, code: int) -> str:
    return f"{path:<72} | {files:>10} | {blank:>10} | {comment:>12} | {code:>10}\n"


def print_cloc_dir_stats(
    writer: ContextWriter,
    cloc_bin: str,
    dir_path: Path,
    repo_dir: Path,
    indent: int,
    threshold: int,
    include_ext: str,
    exclude_file_re: str,
) -> None:
    summary = cloc_summary_for_path(cloc_bin, dir_path, include_ext, exclude_file_re)
    if summary is None:
        return
    files, blank, comment, code = summary
    if not (code > 0 or files > 0):
        return
    rel = relpath(repo_dir, dir_path)
    if rel == ".":
        rel = repo_dir.name
    prefix = ""
    if indent > 0:
        prefix = " " * (indent * 2) + "-> "
    writer.append_text(_table_row(prefix + rel, files, blank, comment, code))
    if code > threshold:
        for subdir in _top_level_dirs(dir_path):
            print_cloc_dir_stats(
                writer, cloc_bin, subdir, repo_dir, indent + 1,
                threshold, include_ext, exclude_file_re,
            )


def _cloc_table(
    writer: ContextWriter,
    repo_dir: Path,
    threshold: int,
    cloc_bin: str,
    output: Path,
    title: str,
    include_ext: str,
) -> None:
    label = repo_dir.name
    exclude_file_re = cloc_target_exclude_re(output)
    writer.write_line("")
    writer.write_line(f"## {label} {title}")
    if threshold > 0:
        writer.write_line(f"Threshold for expanding directories: {threshold} code lines")
    else:
        writer.write_line("Threshold for expanding directories: unlimited (all directories expanded)")
    writer.write_line("")
    writer.append_text(_table_row("Path", "Files", "Blank", "Comment", "Code"))
    writer.append_text(TABLE_RULE + "\n")

    total = cloc_summary_for_path(cloc_bin, repo_dir, include_ext, exclude_file_re)
    if total is None:
        total = (0, 0, 0, 0)
    t_files, t_blank, t_comment, t_code = total
    writer.append_text(_table_row(f"{label} (total)", t_files, t_blank, t_comment, t_code))
    writer.append_text(TABLE_RULE + "\n")

    for top_dir in _top_level_dirs(repo_dir):
        print_cloc_dir_stats(
            writer, cloc_bin, top_dir, repo_dir, 0, threshold,
            include_ext, exclude_file_re,
        )

    writer.append_text(TABLE_RULE + "\n")
    writer.append_text(_table_row("TOTAL", t_files, t_blank, t_comment, t_code))
    writer.write_line("")


def write_cloc_stats(
    writer: ContextWriter,
    repo_dir: Path,
    threshold: int,
    cloc_bin: str,
    output: Path,
) -> None:
    label = repo_dir.name
    if not ensure_cloc(cloc_bin):
        writer.write_line("")
        writer.write_line(f"## {label} cloc statistics")
        writer.write_line("cloc is not available, so cloc statistics were skipped.")
        return
    log_step(f"Counting {label} cloc statistics")
    _cloc_table(writer, repo_dir, threshold, cloc_bin, output, "cloc statistics", "")


def write_cloc_shader_stats(
    writer: ContextWriter,
    repo_dir: Path,
    threshold: int,
    cloc_bin: str,
    output: Path,
) -> None:
    label = repo_dir.name
    if not ensure_cloc(cloc_bin):
        return
    log_step(f"Counting {label} cloc statistics for shader sources")
    exclude_file_re = cloc_target_exclude_re(output)
    total = cloc_summary_for_path(cloc_bin, repo_dir, SHADER_EXTS, exclude_file_re)
    if total is None or (total[3] == 0 and total[0] == 0):
        return
    _cloc_table(writer, repo_dir, threshold, cloc_bin, output, "shader cloc statistics", SHADER_EXTS)


def process_repo_cloc(
    writer: ContextWriter,
    repo_dir: Path,
    stats_threshold: int,
    cloc_bin: str,
    output: Path,
) -> None:
    log_step(f"cloc: {repo_dir.name}")
    write_cloc_stats(writer, repo_dir, stats_threshold, cloc_bin, output)
    write_cloc_shader_stats(writer, repo_dir, stats_threshold, cloc_bin, output)


def process_repo(
    writer: ContextWriter,
    seen: set[str],
    repo_dir: Path,
    stats_threshold: int,
    include_stats: bool,
    cloc_bin: str,
    output: Path,
    max_lines: int,
    max_chars: int,
) -> None:
    label = repo_dir.name
    log_step(f"Processing {label}")
    write_git_metadata(writer, repo_dir)
    write_full_tree(writer, repo_dir)
    writer.write_line("")
    writer.write_line(f"## {label} English help (priority)")
    collect_english_help(writer, seen, repo_dir, output, max_lines, max_chars)
    writer.write_line("")
    writer.write_line(f"## {label} *.md/*.txt files")
    collect_text_docs(writer, seen, repo_dir, output, max_lines, max_chars)
    if include_stats:
        write_cloc_stats(writer, repo_dir, stats_threshold, cloc_bin, output)
        write_cloc_shader_stats(writer, repo_dir, stats_threshold, cloc_bin, output)


def resolve_toolkit_dir(toolkit_dir: str | None) -> Path | None:
    if toolkit_dir:
        path = Path(toolkit_dir)
        if path.is_dir():
            return path.resolve()
    for candidate in (
        REPO_ROOT.parent / "sli-ui-toolkit",
        Path("/home/jorj/Загрузки/sli-ui-toolkit"),
    ):
        if candidate.is_dir():
            return candidate.resolve()
    for venv_python in (
        REPO_ROOT / "venv" / "bin" / "python",
        REPO_ROOT / "venv" / "Scripts" / "python.exe",
    ):
        if not (venv_python.is_file() and os.access(venv_python, os.X_OK)):
            continue
        proc = subprocess.run(
            [
                str(venv_python),
                "-c",
                "import pathlib, sli_ui_toolkit; "
                "print(pathlib.Path(sli_ui_toolkit.__file__).resolve().parent)",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context_cloc.py",
        description=(
            "Convenience wrapper around cloc for Improve-ImgSLI and the "
            "external sli-ui-toolkit."
        ),
        epilog=(
            "Recommended (cloc tables only, full directory expansion, no size cap):\n"
            "  python src/devtools/context_cloc.py --cloc-only\n\n"
            "Full context bundle (git metadata, repo trees, English help,\n"
            "*.md/*.txt docs + cloc):\n"
            "  python src/devtools/context_cloc.py"
        ),
    )
    parser.add_argument(
        "--cloc-only",
        action="store_true",
        help="Output only cloc tables (default: cloc.txt; expands all dirs)",
    )
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="Output file (default: context.txt, or cloc.txt with --cloc-only)",
    )
    parser.add_argument(
        "--max-lines", type=int, default=DEFAULT_MAX_FILE_LINES, metavar="N",
        help="Max lines copied per file in bundle mode (default: 800)",
    )
    parser.add_argument(
        "--max-chars", type=int, default=DEFAULT_MAX_TOTAL_CHARS, metavar="N",
        help="Stop bundle before output grows beyond N chars (default: 260000)",
    )
    parser.add_argument(
        "--stats-threshold", type=int, default=DEFAULT_STATS_THRESHOLD, metavar="N",
        help="Expand cloc subdirs above N code lines (default: 8000; 0 = all)",
    )
    parser.add_argument(
        "--toolkit-dir", metavar="DIR",
        help="sli-ui-toolkit repository directory",
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Skip cloc in full bundle mode",
    )
    return parser


def run_cloc_only(
    output: Path,
    toolkit_dir: Path | None,
    cloc_bin: str,
) -> int:
    log_step(f"Building cloc report -> {output}")
    writer = ContextWriter(output)
    writer.open()
    writer.write_line("# Improve-ImgSLI cloc report")
    writer.write_line(f"Generated: {now_iso()}")
    writer.write_line("Repositories: Improve-ImgSLI, sli-ui-toolkit (when found)")
    writer.write_line("Directory expansion: unlimited (--stats-threshold 0)")

    process_repo_cloc(writer, REPO_ROOT, 0, cloc_bin, output)

    if toolkit_dir is not None:
        process_repo_cloc(writer, toolkit_dir, 0, cloc_bin, output)
    else:
        writer.write_line("")
        writer.write_line("## sli-ui-toolkit")
        writer.write_line(
            "sli-ui-toolkit repository/package directory was not found. "
            "Use --toolkit-dir DIR."
        )

    print(f"Готово: {output} ({writer.chars} chars)")
    return 0


def run_bundle(
    output: Path,
    toolkit_dir: Path | None,
    cloc_bin: str,
    max_lines: int,
    max_chars: int,
    stats_threshold: int,
    include_stats: bool,
) -> int:
    seen: set[str] = set()
    log_step(f"Building context bundle -> {output}")
    writer = ContextWriter(output)
    writer.open()
    writer.write_line("# Improve-ImgSLI context bundle")
    writer.write_line(f"Generated: {now_iso()}")
    writer.write_line("Included repositories: Improve-ImgSLI, sli-ui-toolkit")
    writer.write_line("Collected file contents: English help first, then other *.md/*.txt")
    writer.write_line(f"Max file lines: {max_lines}")
    writer.write_line(f"Max total chars: {max_chars}")

    process_repo(
        writer, seen, REPO_ROOT, stats_threshold, include_stats,
        cloc_bin, output, max_lines, max_chars,
    )

    if toolkit_dir is not None:
        process_repo(
            writer, seen, toolkit_dir, 0, True,
            cloc_bin, output, max_lines, max_chars,
        )
    else:
        writer.write_line("")
        writer.write_line("## sli-ui-toolkit")
        writer.write_line(
            "sli-ui-toolkit repository/package directory was not found. "
            "Use --toolkit-dir DIR."
        )

    writer.write_line("")
    writer.write_line("## summary")
    writer.write_line(f"Files included: {len(seen)}")
    writer.write_line(f"Output chars: {writer.chars}")
    writer.write_line(f"Output file: {output}")
    writer.write_line("")
    writer.write_line(SUMMARY_RULE)
    writer.write_line(f"Generated: {now_iso()}")
    repos_line = "Repositories: Improve-ImgSLI" + (
        ", sli-ui-toolkit" if toolkit_dir is not None else ""
    )
    writer.write_line(repos_line)
    writer.write_line(f"Max file lines: {max_lines}")
    writer.write_line(f"Max total chars: {max_chars}")
    writer.write_line(SUMMARY_RULE)

    print(f"Готово: {output} ({len(seen)} files, {writer.chars} chars)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    output_explicit = args.output is not None
    output_file = Path(args.output) if args.output is not None else Path(DEFAULT_OUTPUT)
    max_lines = args.max_lines
    max_chars = args.max_chars
    stats_threshold = args.stats_threshold
    include_stats = not args.no_stats
    cloc_only = args.cloc_only

    if cloc_only:
        include_stats = True
        stats_threshold = 0
        max_chars = NO_LIMIT_CHARS
        if not output_explicit and output_file.name == DEFAULT_OUTPUT:
            output_file = Path("cloc.txt")

    toolkit_dir = resolve_toolkit_dir(args.toolkit_dir or os.environ.get("SLI_TOOLKIT_DIR"))
    cloc_bin = os.environ.get("CLOC_BIN", "cloc")

    if cloc_only:
        return run_cloc_only(output_file, toolkit_dir, cloc_bin)
    return run_bundle(
        output_file, toolkit_dir, cloc_bin,
        max_lines, max_chars, stats_threshold, include_stats,
    )


if __name__ == "__main__":
    raise SystemExit(main())
