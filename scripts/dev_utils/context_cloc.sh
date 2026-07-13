#!/usr/bin/env bash
set -euo pipefail

OUTPUT_FILE="context.txt"
MAX_FILE_LINES=800
MAX_TOTAL_CHARS=260000
STATS_THRESHOLD=8000
INCLUDE_STATS=1
TOOLKIT_DIR="${SLI_TOOLKIT_DIR:-}"
CLOC_BIN="${CLOC_BIN:-cloc}"
CLOC_EXCLUDE_DIRS="${CLOC_EXCLUDE_DIRS:-.git,.venv,venv,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache,build,dist,Cache,blob_storage,.idea,.vscode,.codex,.agents,.claude}"

usage() {
    cat <<'EOF'
Usage:
  ./launcher.sh context [options]

Build an AI context bundle for Improve-ImgSLI and the external sli-ui-toolkit.

The bundle contains:
  - git metadata for each repository;
  - full repository tree for each repository;
  - contents of *.md and *.txt files only;
  - line/char tree statistics for *.md and *.txt files.

Options:
  -o, --output FILE          Output file (default: context.txt)
  --max-lines N              Max lines copied per file (default: 800)
  --max-chars N              Stop before output grows beyond N chars (default: 260000)
  --stats-threshold N        Expand dir stats above N lines (default: 8000)
  --toolkit-dir DIR          sli-ui-toolkit repository directory
  --no-stats                 Skip cloc-based statistics
  -h, --help                 Show this help
EOF
}

log_step() {
    printf '[context.sh] %s\n' "$*" >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
    -o | --output)
        OUTPUT_FILE="${2:?missing output file}"
        shift 2
        ;;
    --max-lines)
        MAX_FILE_LINES="${2:?missing max lines}"
        shift 2
        ;;
    --max-chars)
        MAX_TOTAL_CHARS="${2:?missing max chars}"
        shift 2
        ;;
    --stats-threshold)
        STATS_THRESHOLD="${2:?missing stats threshold}"
        shift 2
        ;;
    --toolkit-dir)
        TOOLKIT_DIR="${2:?missing toolkit dir}"
        shift 2
        ;;
    --no-stats)
        INCLUDE_STATS=0
        shift
        ;;
    -h | --help)
        usage
        exit 0
        ;;
    *)
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 2
        ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

IGNORE_DIR_RE='(^|/)(\.git|\.venv|venv|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|build|dist|Cache|blob_storage|\.idea|\.vscode|\.codex|\.agents|\.claude)(/|$)'
TREE_IGNORE='*.git|.venv|venv|__pycache__|.pytest_cache|.mypy_cache|.ruff_cache|build|dist|Cache|blob_storage|.idea|.vscode|.codex|.agents|.claude|context.txt|app_context.txt'
COLLECT_EXT_RE='\.(md|txt)$'
STATS_EXT_RE='\.(py|ts|tsx|js|jsx|cpp|c|h|hpp|java|rs|go|rb|php|swift|kt|scala|clj|r|sh|bash|lua|vim|pl|m|swift|groovy|gradle|maven|xml|json|yaml|yml|toml|ini|conf|cfg|config|md|txt)$'
SHADER_STATS_EXT_RE='\.(vert|frag|comp|geom|tesc|tese|glsl|hlsl|msl|wgsl|qsb)$'
LANG_EXCLUDE_RE='_(ar|bg|cs|da|de|el|es|et|fa|fi|fr|he|hi|hu|id|it|ja|ko|lt|nl|no|pl|pt|ro|ru|sk|sl|sv|th|tr|uk|zh|ja)(\.(md|txt))$'

written_chars=0
declare -A seen_files=()

write_line() {
    local text="${1:-}"
    printf '%s\n' "$text" >>"$OUTPUT_FILE"
    written_chars=$((written_chars + ${#text} + 1))
}

repo_label_for_path() {
    local repo_dir="$1"
    basename "$repo_dir"
}

relpath() {
    local base="$1"
    local file="$2"
    file="${file#"$base"/}"
    file="${file#./}"
    printf '%s\n' "$file"
}

is_context_output() {
    local file="$1"
    [[ "$(cd "$(dirname "$file")" 2>/dev/null && pwd)/$(basename "$file")" == "$(cd "$(dirname "$OUTPUT_FILE")" 2>/dev/null && pwd)/$(basename "$OUTPUT_FILE")" ]]
}

collect_file_filter() {
    local file="$1"
    [[ -f "$file" ]] || return 1
    is_context_output "$file" && return 1
    [[ "$file" =~ $IGNORE_DIR_RE ]] && return 1
    [[ "$file" =~ $COLLECT_EXT_RE ]] || return 1
    [[ "$file" =~ $LANG_EXCLUDE_RE ]] && return 1
    [[ "$file" =~ /(ar|bg|cs|da|de|el|es|et|fa|fi|fr|he|hi|hu|id|it|ja|ko|lt|nl|no|pl|pt|ro|ru|sk|sl|sv|th|tr|uk|zh)/ ]] && return 1
    return 0
}

add_file() {
    local repo_dir="$1"
    local file="$2"
    local repo_label rel key lines chars estimated_chars

    collect_file_filter "$file" || return 0

    repo_label="$(repo_label_for_path "$repo_dir")"
    rel="$(relpath "$repo_dir" "$file")"
    key="$repo_label:$rel"

    [[ -n "${seen_files[$key]:-}" ]] && return 0
    [[ "$written_chars" -ge "$MAX_TOTAL_CHARS" ]] && return 0

    read -r lines chars _ < <(wc -lm "$file" 2>/dev/null)
    lines=${lines:-0}
    chars=${chars:-0}
    estimated_chars="$chars"
    if [[ "$lines" -gt "$MAX_FILE_LINES" && "$lines" -gt 0 ]]; then
        estimated_chars=$((chars * MAX_FILE_LINES / lines + 300))
    fi

    if [[ "$written_chars" -gt 0 && $((written_chars + estimated_chars)) -gt "$MAX_TOTAL_CHARS" ]]; then
        write_line ""
        write_line "--- SKIPPED: $repo_label/$rel (would exceed --max-chars=$MAX_TOTAL_CHARS) ---"
        return 0
    fi

    seen_files["$key"]=1

    write_line ""
    write_line ""
    write_line "--- FILE: $repo_label/$rel (lines=$lines chars=$chars) ---"
    if [[ "$lines" -gt "$MAX_FILE_LINES" ]]; then
        sed -n "1,${MAX_FILE_LINES}p" "$file" >>"$OUTPUT_FILE"
        write_line ""
        write_line "--- TRUNCATED: $repo_label/$rel ($((lines - MAX_FILE_LINES)) lines omitted; raise --max-lines to include more) ---"
    else
        sed -n '1,$p' "$file" >>"$OUTPUT_FILE"
    fi
    written_chars=$(wc -m <"$OUTPUT_FILE" | tr -d ' ')
}

write_git_metadata() {
    local repo_dir="$1"
    local repo_label latest_tag

    repo_label="$(repo_label_for_path "$repo_dir")"

    write_line ""
    write_line "## $repo_label git metadata"
    write_line ""

    if ! git -C "$repo_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        write_line "Not a git repository: $repo_dir"
        return 0
    fi

    write_line "Path: $repo_dir"
    write_line "Branch: $(git -C "$repo_dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
    write_line "HEAD: $(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || echo '?')"
    latest_tag=$(git -C "$repo_dir" describe --tags --abbrev=0 2>/dev/null || true)
    [[ -n "$latest_tag" ]] && write_line "Latest tag: $latest_tag"
    write_line ""
    write_line "### recent commits"
    git -C "$repo_dir" log --oneline -n 15 >>"$OUTPUT_FILE" 2>/dev/null || true
    written_chars=$(wc -m <"$OUTPUT_FILE" | tr -d ' ')
}

write_full_tree() {
    local repo_dir="$1"
    local repo_label

    repo_label="$(repo_label_for_path "$repo_dir")"
    write_line ""
    write_line "## $repo_label full tree"

    if command -v tree >/dev/null 2>&1; then
        (cd "$repo_dir" && tree -a -I "$TREE_IGNORE" --prune) >>"$OUTPUT_FILE" 2>/dev/null || true
    else
        (cd "$repo_dir" && find . \
            -type d \( -name .git -o -name .venv -o -name venv -o -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name build -o -name dist -o -name Cache -o -name blob_storage -o -name .idea -o -name .vscode -o -name .codex -o -name .agents -o -name .claude \) -prune \
            -o -print | sort) >>"$OUTPUT_FILE"
    fi
    written_chars=$(wc -m <"$OUTPUT_FILE" | tr -d ' ')
}

collect_text_docs() {
    local repo_dir="$1"
    local file

    while IFS= read -r -d '' file; do
        add_file "$repo_dir" "$file"
    done < <(find "$repo_dir" \
        -type d \( -name .git -o -name .venv -o -name venv -o -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name build -o -name dist -o -name Cache -o -name blob_storage -o -name .idea -o -name .vscode -o -name .codex -o -name .agents -o -name .claude \) -prune \
        -o -type f \( -name '*.md' -o -name '*.txt' \) -print0 | sort -z)
}


cloc_escape_regex() {
    python3 - "$1" <<'PY'
import re
import sys
print(re.escape(sys.argv[1]))
PY
}

ensure_cloc() {
    if [[ "$CLOC_BIN" == */* ]]; then
        [[ -x "$CLOC_BIN" ]] && return 0
    elif command -v "$CLOC_BIN" >/dev/null 2>&1; then
        return 0
    fi
    printf '[context.sh] cloc not found. Install cloc or set CLOC_BIN to its path to enable statistics.\n' >&2
    return 1
}

cloc_summary_for_path() {
    local target="$1"
    local include_ext="${2:-}"
    local exclude_file_re="${3:-}"
    local -a cmd=("$CLOC_BIN" --quiet --json --exclude-dir="$CLOC_EXCLUDE_DIRS")
    local json

    [[ -n "$include_ext" ]] && cmd+=(--include-ext="$include_ext")
    [[ -n "$exclude_file_re" ]] && cmd+=(--not-match-f="$exclude_file_re")
    cmd+=("$target")

    json="$("${cmd[@]}" 2>/dev/null)" || return 1

    python3 -c '
import json
import sys

data = json.load(sys.stdin)
summary = data.get("SUM", {})

def get(*keys):
    for key in keys:
        value = summary.get(key)
        if value is not None:
            return value
    return 0

files = get("nFiles", "files")
blank = get("blank")
comment = get("comment")
code = get("code")
print(f"{files}	{blank}	{comment}	{code}")
' <<<"$json"
}

cloc_target_exclude_re(){
    local output_basename exclude_output_basename
    output_basename="$(basename "$OUTPUT_FILE")"
    exclude_output_basename="$(cloc_escape_regex "$output_basename")"
    printf '(^|/)(%s|context\.txt|app_context\.txt)$' "$exclude_output_basename"
}

print_cloc_dir_stats() {
    local dir="$1"
    local repo_dir="$2"
    local indent="$3"
    local threshold="$4"
    local include_ext="${5:-}"
    local exclude_file_re="${6:-}"
    local files blank comment code prefix rel

    read -r files blank comment code < <(cloc_summary_for_path "$dir" "$include_ext" "$exclude_file_re")
    [[ "$code" -gt 0 || "$files" -gt 0 ]] || return 0

    rel="$(relpath "$repo_dir" "$dir")"
    [[ "$rel" == "." ]] && rel="$(repo_label_for_path "$repo_dir")"

    prefix=""
    if [[ "$indent" -gt 0 ]]; then
        prefix="$(printf '%*s' $((indent * 2)) '')-> "
    fi

    printf '%-72s | %10s | %10s | %12s | %10s
' "${prefix}${rel}" "$files" "$blank" "$comment" "$code" >>"$OUTPUT_FILE"

    if [[ "$code" -gt "$threshold" ]]; then
        while IFS= read -r subdir; do
            print_cloc_dir_stats "$subdir" "$repo_dir" $((indent + 1)) "$threshold" "$include_ext" "$exclude_file_re"
        done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d             ! -name .git ! -name .venv ! -name venv ! -name __pycache__             ! -name .pytest_cache ! -name .mypy_cache ! -name .ruff_cache             ! -name build ! -name dist ! -name Cache ! -name blob_storage             ! -name .idea ! -name .vscode ! -name .codex ! -name .agents ! -name .claude |
            sort)
    fi
}

write_cloc_stats() {
    local repo_dir="$1"
    local threshold="${2:-$STATS_THRESHOLD}"
    local repo_label total_files total_blank total_comment total_code top_dir exclude_file_re

    repo_label="$(repo_label_for_path "$repo_dir")"
    exclude_file_re="$(cloc_target_exclude_re)"

    if ! ensure_cloc; then
        write_line ""
        write_line "## $repo_label cloc statistics"
        write_line "cloc is not available, so cloc statistics were skipped."
        return 0
    fi

    log_step "Counting $repo_label cloc statistics"

    write_line ""
    write_line "## $repo_label cloc statistics"
    if [[ "$threshold" -gt 0 ]]; then
        write_line "Threshold for expanding directories: $threshold code lines"
    else
        write_line "Threshold for expanding directories: unlimited (all directories expanded)"
    fi
    write_line ""
    printf '%-72s | %10s | %10s | %12s | %10s
' "Path" "Files" "Blank" "Comment" "Code" >>"$OUTPUT_FILE"
    printf '%s
' "----------------------------------------------------------------------------------------------------" >>"$OUTPUT_FILE"

    read -r total_files total_blank total_comment total_code < <(cloc_summary_for_path "$repo_dir" "" "$exclude_file_re")
    printf '%-72s | %10s | %10s | %12s | %10s
' "$repo_label (total)" "$total_files" "$total_blank" "$total_comment" "$total_code" >>"$OUTPUT_FILE"
    printf '%s
' "----------------------------------------------------------------------------------------------------" >>"$OUTPUT_FILE"

    while IFS= read -r top_dir; do
        print_cloc_dir_stats "$top_dir" "$repo_dir" 0 "$threshold" "" "$exclude_file_re"
    done < <(find "$repo_dir" -mindepth 1 -maxdepth 1 -type d         ! -name .git ! -name .venv ! -name venv ! -name __pycache__         ! -name .pytest_cache ! -name .mypy_cache ! -name .ruff_cache         ! -name build ! -name dist ! -name Cache ! -name blob_storage         ! -name .idea ! -name .vscode ! -name .codex ! -name .agents ! -name .claude |
        sort)

    printf '%s
' "----------------------------------------------------------------------------------------------------" >>"$OUTPUT_FILE"
    printf '%-72s | %10s | %10s | %12s | %10s
' "TOTAL" "$total_files" "$total_blank" "$total_comment" "$total_code" >>"$OUTPUT_FILE"
    write_line ""

    written_chars=$(wc -m <"$OUTPUT_FILE" | tr -d ' ')
}

write_cloc_shader_stats() {
    local repo_dir="$1"
    local threshold="${2:-$STATS_THRESHOLD}"
    local repo_label total_files total_blank total_comment total_code top_dir exclude_file_re shader_exts

    repo_label="$(repo_label_for_path "$repo_dir")"
    exclude_file_re="$(cloc_target_exclude_re)"
    shader_exts="vert,frag,comp,geom,tesc,tese,glsl,hlsl,msl,wgsl,qsb"

    if ! ensure_cloc; then
        return 0
    fi

    log_step "Counting $repo_label cloc statistics for shader sources"

    read -r total_files total_blank total_comment total_code < <(cloc_summary_for_path "$repo_dir" "$shader_exts" "$exclude_file_re")
    if [[ "$total_code" -eq 0 && "$total_files" -eq 0 ]]; then
        return 0
    fi

    write_line ""
    write_line "## $repo_label shader cloc statistics"
    if [[ "$threshold" -gt 0 ]]; then
        write_line "Threshold for expanding directories: $threshold code lines"
    else
        write_line "Threshold for expanding directories: unlimited (all directories expanded)"
    fi
    write_line ""
    printf '%-72s | %10s | %10s | %12s | %10s
' "Path" "Files" "Blank" "Comment" "Code" >>"$OUTPUT_FILE"
    printf '%s
' "----------------------------------------------------------------------------------------------------" >>"$OUTPUT_FILE"
    printf '%-72s | %10s | %10s | %12s | %10s
' "$repo_label (total)" "$total_files" "$total_blank" "$total_comment" "$total_code" >>"$OUTPUT_FILE"
    printf '%s
' "----------------------------------------------------------------------------------------------------" >>"$OUTPUT_FILE"

    while IFS= read -r top_dir; do
        print_cloc_dir_stats "$top_dir" "$repo_dir" 0 "$threshold" "$shader_exts" "$exclude_file_re"
    done < <(find "$repo_dir" -mindepth 1 -maxdepth 1 -type d         ! -name .git ! -name .venv ! -name venv ! -name __pycache__         ! -name .pytest_cache ! -name .mypy_cache ! -name .ruff_cache         ! -name build ! -name dist ! -name Cache ! -name blob_storage         ! -name .idea ! -name .vscode ! -name .codex ! -name .agents ! -name .claude |
        sort)

    printf '%s
' "----------------------------------------------------------------------------------------------------" >>"$OUTPUT_FILE"
    printf '%-72s | %10s | %10s | %12s | %10s
' "TOTAL" "$total_files" "$total_blank" "$total_comment" "$total_code" >>"$OUTPUT_FILE"
    write_line ""

    written_chars=$(wc -m <"$OUTPUT_FILE" | tr -d ' ')
}

resolve_toolkit_dir() {

    local candidate

    if [[ -n "$TOOLKIT_DIR" && -d "$TOOLKIT_DIR" ]]; then
        printf '%s\n' "$(cd "$TOOLKIT_DIR" && pwd)"
        return 0
    fi

    for candidate in \
        "$REPO_ROOT/../sli-ui-toolkit" \
        "/home/jorj/Загрузки/sli-ui-toolkit"; do
        if [[ -d "$candidate" ]]; then
            printf '%s\n' "$(cd "$candidate" && pwd)"
            return 0
        fi
    done

    if [[ -x "$REPO_ROOT/venv/bin/python" ]]; then
        "$REPO_ROOT/venv/bin/python" - <<'PY' 2>/dev/null || true
from pathlib import Path
import sli_ui_toolkit
print(Path(sli_ui_toolkit.__file__).resolve().parent)
PY
    fi
}

process_repo() {
    local repo_dir="$1"
    local stats_threshold="${2:-$STATS_THRESHOLD}"
    local repo_label

    repo_dir="$(cd "$repo_dir" && pwd)"
    repo_label="$(repo_label_for_path "$repo_dir")"

    log_step "Processing $repo_label"
    write_git_metadata "$repo_dir"
    write_full_tree "$repo_dir"

    write_line ""
    write_line "## $repo_label *.md/*.txt files"
    collect_text_docs "$repo_dir"

    if [[ "$INCLUDE_STATS" -eq 1 ]]; then
        write_cloc_stats "$repo_dir" "$stats_threshold"
        write_cloc_shader_stats "$repo_dir" "$stats_threshold"
    fi
}

TOOLKIT_DIR="$(resolve_toolkit_dir | head -n 1 || true)"

: >"$OUTPUT_FILE"
log_step "Building context bundle -> $OUTPUT_FILE"
write_line "# Improve-ImgSLI context bundle"
write_line "Generated: $(date -Is)"
write_line "Included repositories: Improve-ImgSLI, sli-ui-toolkit"
write_line "Collected file contents: *.md and *.txt only"
write_line "Max file lines: $MAX_FILE_LINES"
write_line "Max total chars: $MAX_TOTAL_CHARS"

process_repo "$REPO_ROOT" "$STATS_THRESHOLD"

if [[ -n "$TOOLKIT_DIR" && -d "$TOOLKIT_DIR" ]]; then
    process_repo "$TOOLKIT_DIR" 0
else
    write_line ""
    write_line "## sli-ui-toolkit"
    write_line "sli-ui-toolkit repository/package directory was not found. Use --toolkit-dir DIR."
fi

write_line ""
write_line "## summary"
write_line "Files included: ${#seen_files[@]}"
write_line "Output chars: $(wc -m <"$OUTPUT_FILE" | tr -d ' ')"
write_line "Output file: $OUTPUT_FILE"
write_line ""
write_line "=========================================="
write_line "Generated: $(date -Is)"
write_line "Repositories: Improve-ImgSLI$([ -n "$TOOLKIT_DIR" ] && [ -d "$TOOLKIT_DIR" ] && echo ", sli-ui-toolkit" || echo "")"
write_line "Max file lines: $MAX_FILE_LINES"
write_line "Max total chars: $MAX_TOTAL_CHARS"
write_line "=========================================="

echo "Готово: $OUTPUT_FILE (${#seen_files[@]} files, $(wc -m <"$OUTPUT_FILE" | tr -d ' ') chars)"
