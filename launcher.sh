#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_MAIN="$SCRIPT_DIR/src/__main__.py"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements-gui.txt"
DEV_REQUIREMENTS="$SCRIPT_DIR/requirements-dev.txt"

source "$SCRIPT_DIR/src/shared_toolkit/scripts/common_launcher_funcs.sh"

enable_logging_action() {
    log_info "Attempting to enable logging..."
    if ensure_venv_is_ready "$VENV_DIR" "$REQUIREMENTS"; then
        export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"
        python "$APP_MAIN" --enable-logging
        deactivate_venv
        log_status "Logging settings updated" 0
    else
        log_status "Failed to prepare environment. Aborting." 1
        cleanup_broken_venv "$VENV_DIR"
        exit 1
    fi
}

disable_logging_action() {
    log_info "Attempting to disable logging..."
    if ensure_venv_is_ready "$VENV_DIR" "$REQUIREMENTS"; then
        export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"
        python "$APP_MAIN" --disable-logging
        deactivate_venv
        log_status "Logging settings updated" 0
    else
        log_status "Failed to prepare environment. Aborting." 1
        cleanup_broken_venv "$VENV_DIR"
        exit 1
    fi
}

show_help() {
    echo "Improve ImgSLI"
    echo "Usage: $0 <command> [options]"
    echo "       $0 [--debug|-d] [--theme <dark|light>] [--ui-inspector]"
    echo ""
    echo "Commands:"
    echo "  run [args...]      Run the application with optional GUI arguments."
    echo "                     On Linux, also syncs .desktop / .imgsli MIME / thumbnailer if outdated."
    echo "                     Additional flags for 'run' (also valid at top-level):"
    echo "                       --theme <dark|light>  Force a specific theme."
    echo "                       --debug, -d          Enable debug logging for this session only."
    echo "                       --ui-inspector       Enable the developer UI inspector."
    echo "  test [args...]     Run the test suite (pytest). Extra args pass through,"
    echo "                     e.g. '$0 test tests/runtime -k gesture'."
    echo "  context [args...]  cloc report for app + sli-ui-toolkit (see --help on script)."
    echo "                     '$0 context --cloc-only' → cloc.txt"
    echo "  install            Create the virtual environment and/or install dependencies."
    echo "  recreate           Forcibly recreate the virtual environment."
    echo "  delete             Delete the virtual environment and Python caches."
    echo "  rm-cache           Remove Python caches without deleting the virtual environment."
    echo "  install-desktop    Install .desktop, .imgsli MIME type, and thumbnailer."
    echo "  uninstall-desktop  Remove .desktop / MIME / thumbnailer."
    echo "  --enable-logging   Permanently enable debug logging."
    echo "  --disable-logging  Permanently disable debug logging."
    echo "  help               Show this help message."
}

install_action() {
    if ensure_venv_is_ready "$VENV_DIR" "$REQUIREMENTS"; then
        log_info "Environment is ready."
    else
        log_status "Failed to set up environment." 1
        cleanup_broken_venv "$VENV_DIR"
        exit 1
    fi
    deactivate_venv
}

recreate_action() {
    log_info "Recreating virtual environment..."

    if ! remove_venv_dir "$VENV_DIR" "existing virtual environment"; then
        exit 1
    fi

    if ! ensure_venv_is_ready "$VENV_DIR" "$REQUIREMENTS"; then
        log_status "Failed to recreate environment." 1
        cleanup_broken_venv "$VENV_DIR"
        exit 1
    fi

    deactivate_venv
}

rm_cache_action() {
    cleanup_python_cache "$SCRIPT_DIR" "$VENV_DIR"
}

delete_action() {
    log_info "Starting cleanup..."

    if ! remove_venv_dir "$VENV_DIR" "virtual environment"; then
        exit 1
    fi

    rm_cache_action
    log_info "Cleanup completed."
}

install_desktop_action() {
    if ! ensure_linux_desktop_integration verbose; then
        log_status "Desktop template not found" 1
        exit 1
    fi
    log_status "Desktop entry / MIME / thumbnailer installed" 0
}

# Idempotent Linux integration: .desktop, MIME (beats ZIP magic), thumbnailer.
# Quiet mode (used by ``run``) only logs when something actually changes and
# skips slow MIME/KDE rebuilds when installed files already match sources.
ensure_linux_desktop_integration() {
    local mode="${1:-quiet}"
    case "$(uname -s)" in
    Linux) ;;
    *)
        if [[ "$mode" == "verbose" ]]; then
            log_info "Desktop integration is Linux-only; skipping."
        fi
        return 0
        ;;
    esac

    local template="$SCRIPT_DIR/improve-imgsli.desktop.in"
    local target="$HOME/.local/share/applications/improve-imgsli.desktop"
    local mime_src="$SCRIPT_DIR/build/linux/mime/application-x-improve-imgsli.xml"
    local mime_dst="$HOME/.local/share/mime/packages/application-x-improve-imgsli.xml"
    local thumb_bin_src="$SCRIPT_DIR/build/linux/bin/improve-imgsli-thumbnailer"
    local thumb_bin_dst="$HOME/.local/bin/improve-imgsli-thumbnailer"
    local thumb_desktop_src="$SCRIPT_DIR/build/linux/thumbnailers/improve-imgsli.thumbnailer"
    local thumb_desktop_dst="$HOME/.local/share/thumbnailers/improve-imgsli.thumbnailer"
    local mime_icon_dir="$SCRIPT_DIR/build/linux/icons/mimetypes"
    local mark_src="$SCRIPT_DIR/src/resources/icons/icon.png"
    local mark_dst="$HOME/.local/share/improve-imgsli/mark.png"

    if [[ ! -f "$template" ]]; then
        return 1
    fi

    local mime_changed=0 desktop_changed=0 thumb_changed=0 icons_changed=0
    local tmp_desktop=""
    tmp_desktop="$(mktemp)"
    sed -e "s|@LAUNCHER_PATH@|$SCRIPT_DIR/launcher.sh|g" \
        -e "s|@ICON_PATH@|$SCRIPT_DIR/src/resources/icons/icon.png|g" \
        "$template" >"$tmp_desktop"

    mkdir -p "$HOME/.local/share/applications"
    if [[ ! -f "$target" ]] || ! cmp -s "$tmp_desktop" "$target"; then
        cp "$tmp_desktop" "$target"
        chmod +x "$target"
        desktop_changed=1
    fi
    rm -f "$tmp_desktop"

    if [[ -f "$mime_src" ]]; then
        mkdir -p "$HOME/.local/share/mime/packages"
        if [[ ! -f "$mime_dst" ]] || ! cmp -s "$mime_src" "$mime_dst"; then
            cp "$mime_src" "$mime_dst"
            mime_changed=1
        fi
    fi

    if [[ -f "$thumb_bin_src" && -f "$thumb_desktop_src" ]]; then
        mkdir -p "$HOME/.local/bin" "$HOME/.local/share/thumbnailers" \
            "$HOME/.local/share/improve-imgsli"
        if [[ ! -f "$thumb_bin_dst" ]] || ! cmp -s "$thumb_bin_src" "$thumb_bin_dst"; then
            install -m 755 "$thumb_bin_src" "$thumb_bin_dst"
            thumb_changed=1
        fi
        if [[ ! -f "$thumb_desktop_dst" ]] || ! cmp -s "$thumb_desktop_src" "$thumb_desktop_dst"; then
            cp "$thumb_desktop_src" "$thumb_desktop_dst"
            thumb_changed=1
        fi
        if [[ -f "$mark_src" ]]; then
            if [[ ! -f "$mark_dst" ]] || ! cmp -s "$mark_src" "$mark_dst"; then
                cp "$mark_src" "$mark_dst"
                thumb_changed=1
            fi
        fi
    fi

    # Document-style MIME icons (PSD/XCF layout), not the full app wordmark.
    if [[ -d "$mime_icon_dir" ]]; then
        local size icon_src icon_dst
        for size in 16 22 32 48 64 128 256; do
            icon_src="$mime_icon_dir/application-x-improve-imgsli-${size}.png"
            [[ -f "$icon_src" ]] || continue
            icon_dst="$HOME/.local/share/icons/hicolor/${size}x${size}/mimetypes/application-x-improve-imgsli.png"
            mkdir -p "$(dirname "$icon_dst")"
            if [[ ! -f "$icon_dst" ]] || ! cmp -s "$icon_src" "$icon_dst"; then
                cp "$icon_src" "$icon_dst"
                icons_changed=1
            fi
        done
    fi

    if (( desktop_changed )); then
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
        log_info "Desktop entry updated: $target"
    elif [[ "$mode" == "verbose" ]]; then
        log_info "Desktop entry already up to date: $target"
    fi

    if (( mime_changed || icons_changed )); then
        update-mime-database "$HOME/.local/share/mime" 2>/dev/null || true
        xdg-mime default improve-imgsli.desktop application/x-improve-imgsli 2>/dev/null || true
        if (( icons_changed )); then
            if command -v gtk-update-icon-cache >/dev/null 2>&1; then
                gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
            fi
            if command -v xdg-icon-resource >/dev/null 2>&1; then
                # Touch the icon theme index so KDE/GNOME pick up new mimetype icons.
                xdg-icon-resource forceupdate --theme hicolor 2>/dev/null || true
            fi
        fi
        if command -v kbuildsycoca6 >/dev/null 2>&1; then
            kbuildsycoca6 --noincremental 2>/dev/null || true
        elif command -v kbuildsycoca5 >/dev/null 2>&1; then
            kbuildsycoca5 --noincremental 2>/dev/null || true
        fi
        if (( mime_changed )); then
            log_info "MIME type installed/updated (application/x-improve-imgsli)."
        fi
        if (( icons_changed )); then
            log_info "MIME icons installed (document + mark + IMGSLI)."
        fi
        if [[ "$mode" == "verbose" ]]; then
            log_info "If Dolphin still shows Zip/old icon: killall dolphin; clear ~/.cache/thumbnails."
        fi
    elif [[ "$mode" == "verbose" ]]; then
        log_info "MIME type / icons already up to date (application/x-improve-imgsli)."
        xdg-mime default improve-imgsli.desktop application/x-improve-imgsli 2>/dev/null || true
    fi

    if (( thumb_changed )); then
        log_info "Thumbnailer installed/updated (document-framed preview.png)."
        if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
            log_info "Note: ensure ~/.local/bin is on PATH so the thumbnailer is found."
        fi
    elif [[ "$mode" == "verbose" ]]; then
        log_info "Thumbnailer already up to date."
    fi

    return 0
}

uninstall_desktop_action() {
    local target="$HOME/.local/share/applications/improve-imgsli.desktop"
    local mime_xml="$HOME/.local/share/mime/packages/application-x-improve-imgsli.xml"
    local thumb_bin="$HOME/.local/bin/improve-imgsli-thumbnailer"
    local thumb_desktop="$HOME/.local/share/thumbnailers/improve-imgsli.thumbnailer"
    local mark_dst="$HOME/.local/share/improve-imgsli/mark.png"
    local size icon_dst

    if [[ -f "$target" ]]; then
        rm "$target"
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
        log_status "Desktop entry removed" 0
    else
        log_info "Desktop entry not found, nothing to remove."
    fi

    if [[ -f "$mime_xml" ]]; then
        rm "$mime_xml"
        update-mime-database "$HOME/.local/share/mime" 2>/dev/null || true
        log_info "MIME type removed."
    fi
    for size in 16 22 32 48 64 128 256; do
        icon_dst="$HOME/.local/share/icons/hicolor/${size}x${size}/mimetypes/application-x-improve-imgsli.png"
        rm -f "$icon_dst"
    done
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi
    rm -f "$thumb_bin" "$thumb_desktop" "$mark_dst"
}

context_action() {
    shift
    (cd "$SCRIPT_DIR" && bash "$SCRIPT_DIR/src/devtools/context_cloc.sh" "$@")
}

test_action() {
    shift

    if ! ensure_venv_is_ready "$VENV_DIR" "$REQUIREMENTS"; then
        log_status "Failed to prepare environment. Aborting." 1
        cleanup_broken_venv "$VENV_DIR"
        exit 1
    fi

    if ! python -c "import pytest, pytest_sugar" >/dev/null 2>&1; then
        if ! run_pip_with_inline_progress "Installing test dependencies" "$DEV_REQUIREMENTS" \
            python -m pip install -r "$DEV_REQUIREMENTS"; then
            deactivate_venv
            log_status "Failed to install test dependencies." 1
            exit 1
        fi
    fi

    log_info "Running test suite..."
    (cd "$SCRIPT_DIR" && python -m pytest "$@")
    local test_exit_code=$?

    deactivate_venv
    log_info "Tests completed with exit code: $test_exit_code"
    exit "$test_exit_code"
}

run_action() {
    shift

    local gui_args=()
    local theme_to_set=""
    local debug_mode="false"
    local ui_inspector="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
        --theme)
            if [[ -n "${2:-}" && ("$2" == "dark" || "$2" == "light") ]]; then
                theme_to_set="$2"
                shift 2
            else
                log_info "Error: --theme requires argument (dark or light)"
                exit 1
            fi
            ;;
        --debug | -d)
            debug_mode="true"
            shift
            ;;
        --ui-inspector)
            ui_inspector="true"
            debug_mode="true"
            shift
            ;;
        *)
            gui_args+=("$1")
            shift
            ;;
        esac
    done

    if ensure_venv_is_ready "$VENV_DIR" "$REQUIREMENTS"; then
        # Keep .imgsli MIME / desktop / thumbnailer in sync (no-op when current).
        ensure_linux_desktop_integration quiet || true

        log_info "Starting Improve ImgSLI..."
        export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"

        if [[ -n "$theme_to_set" ]]; then
            export APP_THEME="$theme_to_set"
        fi

        if [[ "$debug_mode" == "true" ]]; then
            gui_args=("--debug" "${gui_args[@]}")
        fi
        if [[ "$ui_inspector" == "true" ]]; then
            gui_args=("--ui-inspector" "${gui_args[@]}")
        fi

        python "$APP_MAIN" "${gui_args[@]}"
        local app_exit_code=$?

        deactivate_venv
        log_info "Application completed with exit code: $app_exit_code"
        exit "$app_exit_code"
    fi

    deactivate_venv
    log_status "Failed to prepare environment. Aborting." 1
    cleanup_broken_venv "$VENV_DIR"
    exit 1
}

if [[ "${1:-}" == "--debug" || "${1:-}" == "-d" || "${1:-}" == "--theme" || "${1:-}" == "--ui-inspector" ]]; then
    set -- run "$@"
fi

COMMAND="${1:-}"
case "$COMMAND" in
install)
    install_action
    ;;

run)
    run_action "$@"
    ;;

test)
    test_action "$@"
    ;;

context)
    context_action "$@"
    ;;

recreate)
    recreate_action
    ;;

delete)
    delete_action
    ;;

rm-cache)
    rm_cache_action
    ;;

--enable-logging)
    enable_logging_action
    ;;

--disable-logging)
    disable_logging_action
    ;;

install-desktop)
    install_desktop_action
    ;;

uninstall-desktop)
    uninstall_desktop_action
    ;;

"" | help | --help)
    show_help
    ;;

*)
    log_info "Error: Unknown command '$COMMAND'"
    show_help
    exit 1
    ;;
esac

printf "${COLOR_RESET}"
exit 0
