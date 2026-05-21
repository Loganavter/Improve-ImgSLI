#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_MAIN="$SCRIPT_DIR/src/__main__.py"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements-gui.txt"

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
    echo "       $0 [--debug|-d] [--theme <dark|light>]"
    echo ""
    echo "Commands:"
    echo "  run [args...]      Run the application with optional GUI arguments."
    echo "                     Additional flags for 'run' (also valid at top-level):"
    echo "                       --theme <dark|light>  Force a specific theme."
    echo "                       --debug, -d          Enable debug logging for this session only."
    echo "  install            Create the virtual environment and/or install dependencies."
    echo "  recreate           Forcibly recreate the virtual environment."
    echo "  delete             Delete the virtual environment and Python caches."
    echo "  rm-cache           Remove Python caches without deleting the virtual environment."
    echo "  install-desktop    Install .desktop entry for app launcher integration."
    echo "  uninstall-desktop  Remove .desktop entry."
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
    local template="$SCRIPT_DIR/improve-imgsli.desktop.in"
    local target="$HOME/.local/share/applications/improve-imgsli.desktop"

    if [[ ! -f "$template" ]]; then
        log_status "Desktop template not found: $template" 1
        exit 1
    fi

    mkdir -p "$HOME/.local/share/applications"
    sed -e "s|@LAUNCHER_PATH@|$SCRIPT_DIR/launcher.sh|g" \
        -e "s|@ICON_PATH@|$SCRIPT_DIR/src/resources/icons/icon.png|g" \
        "$template" >"$target"

    chmod +x "$target"
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    log_status "Desktop entry installed to $target" 0
}

uninstall_desktop_action() {
    local target="$HOME/.local/share/applications/improve-imgsli.desktop"

    if [[ -f "$target" ]]; then
        rm "$target"
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
        log_status "Desktop entry removed" 0
    else
        log_info "Desktop entry not found, nothing to remove."
    fi
}

run_action() {
    shift

    local gui_args=()
    local theme_to_set=""
    local debug_mode="false"

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
        *)
            gui_args+=("$1")
            shift
            ;;
        esac
    done

    if ensure_venv_is_ready "$VENV_DIR" "$REQUIREMENTS"; then
        log_info "Starting Improve ImgSLI..."
        export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"

        if [[ -n "$theme_to_set" ]]; then
            export APP_THEME="$theme_to_set"
        fi

        if [[ "$debug_mode" == "true" ]]; then
            gui_args=("--debug" "${gui_args[@]}")
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

if [[ "${1:-}" == "--debug" || "${1:-}" == "-d" || "${1:-}" == "--theme" ]]; then
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
