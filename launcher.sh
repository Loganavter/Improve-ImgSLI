#!/bin/bash

COLOR_RESET="\033[0m"
BG_RED="\033[0;41m"
BG_GREEN="\033[0;42m"
BG_PROGRESS="\033[48;5;11m"
TEXT_WHITE="\033[1;37m"
TEXT_BLACK="\033[1;30m"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/venv"
APP_MAIN="$SCRIPT_DIR/src/Improve_ImgSLI.py"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

log_info() {
    printf "%s\n" "$1"
}

log_status() {
    local message="$1"
    local status_code="$2"

    if [[ "$status_code" -eq 0 ]]; then
        printf "%s ${BG_GREEN}${TEXT_WHITE}[OK]${COLOR_RESET}\n" "$message"
    else
        printf "%s ${BG_RED}${TEXT_WHITE}[ERROR]${COLOR_RESET}\n" "$message"
    fi
}

show_spinner() {
  local pid=$1
  local msg=$2
  local delay=0.1
  local spinstr='/-\|'
  
  tput civis
  trap 'tput cnorm' EXIT

  while ps -p "$pid" > /dev/null; do
    local temp=${spinstr#?}
    printf "\r\033[K%s %c " "$msg" "${spinstr:0:1}"
    spinstr=$temp${spinstr%"$temp"}
    sleep "$delay"
  done
  
  tput cnorm
}

run_with_spinner() {
    local base_msg=$1
    shift

    local terminal_cols=$(tput cols 2>/dev/null)
    if [[ -z "$terminal_cols" || "$terminal_cols" -eq 0 ]]; then
        terminal_cols=80
    fi
    local max_spinner_msg_len=$((terminal_cols - 10))
    local spinner_msg_content="$base_msg"
    if [[ ${#spinner_msg_content} -gt "$max_spinner_msg_len" ]]; then
        spinner_msg_content="${spinner_msg_content:0:$((max_spinner_msg_len - 3))}..."
    fi

    local error_log
    error_log=$(mktemp) || { log_status "Failed to create temporary file" 1; exit 1; }
    trap 'rm -f "$error_log"' RETURN

    "$@" > /dev/null 2>"$error_log" &
    local cmd_pid=$!

    show_spinner "$cmd_pid" "$spinner_msg_content"
    wait "$cmd_pid"
    local exit_code=$?

    printf "\r\033[K"

    if [[ $exit_code -ne 0 ]]; then
        printf "%s ${BG_RED}${TEXT_WHITE}[ERROR]${COLOR_RESET}\n" "$base_msg"
        sed -r "s/\x1B\[([0-9]{1,3}(;[0-9]{1,3})*)?[mGK]//g" "$error_log" >&2
    else
        printf "%s ${BG_GREEN}${TEXT_WHITE}[OK]${COLOR_RESET}\n" "$base_msg"
    fi

    return $exit_code
}

run_pip_with_inline_progress() {
    local base_msg=$1
    shift

    if [[ ! -f "$REQUIREMENTS" ]]; then
        log_status "'requirements.txt' not found" 1
        return 1
    fi

    local total_packages
    total_packages=$(grep -cE '^\s*[^#\s]' "$REQUIREMENTS")
    total_packages=${total_packages// /}

    if [[ "$total_packages" -eq 0 ]]; then
        log_info "$base_msg (No packages to install)."
        return 0
    fi

    local COLLECT_WEIGHT=30
    local DOWNLOAD_WEIGHT=60
    local collect_count=0
    local download_count=0
    local updated=false
    
    local error_log
    error_log=$(mktemp) || { log_status "Failed to create temporary file" 1; exit 1; }
    trap 'rm -f "$error_log"' RETURN

    printf "%s ${BG_PROGRESS}${TEXT_BLACK}[0%%]${COLOR_RESET}\n" "$base_msg"

    "$@" 2> "$error_log" | while IFS= read -r line; do
        local percentage=0
        updated=false
        
        if [[ "$line" == "Collecting "* ]]; then ((collect_count++)); updated=true;
        elif [[ "$line" == "Downloading "* || "$line" == "Using cached "* ]]; then ((download_count++)); updated=true;
        elif [[ "$line" == "Requirement already satisfied:"* ]]; then ((collect_count++)); ((download_count++)); updated=true;
        elif [[ "$line" == "Installing collected packages"* ]]; then collect_count=$total_packages; download_count=$total_packages; updated=true; fi

        if [[ "$updated" = true ]]; then
            percentage=$(( (collect_count * COLLECT_WEIGHT) / total_packages + (download_count * DOWNLOAD_WEIGHT) / total_packages ))
            [[ "$percentage" -gt 99 ]] && percentage=99
            printf "\033[A\r\033[K%s ${BG_PROGRESS}${TEXT_BLACK}[%d%%]${COLOR_RESET}\n" "$base_msg" "$percentage"
        fi
    done

    local exit_code=${PIPESTATUS[0]}

    printf "\033[A\r\033[K"
    if [[ $exit_code -eq 0 ]]; then
        log_status "$base_msg" 0
    else
        log_status "$base_msg" 1
        sed -r "s/\x1B\[([0-9]{1,3}(;[0-9]{1,3})*)?[mGK]//g" "$error_log" >&2
    fi

    return $exit_code
}

get_canonical_path() {
    if [[ -z "$1" ]]; then return 1; fi
    local resolved_path
    if [[ -d "$1" ]]; then resolved_path="$(cd "$1" && pwd)";
    elif [[ -f "$1" ]]; then resolved_path="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")";
    else
        local parent_dir=$(dirname "$1")
        if [[ -d "$parent_dir" ]]; then resolved_path="$(cd "$parent_dir" && pwd)/$(basename "$1")";
        else echo "$1"; return 0; fi
    fi
    echo "$resolved_path"
    return 0
}

activate_venv() {
    local activate_script=""
    local canonical_venv_dir=$(get_canonical_path "$VENV_DIR")
    if [[ -f "$VENV_DIR/bin/activate" ]]; then activate_script="$VENV_DIR/bin/activate";
    elif [[ -f "$VENV_DIR/Scripts/activate" ]]; then activate_script="$VENV_DIR/Scripts/activate"; fi

    if [[ -n "$activate_script" ]]; then
        source "$activate_script"
        return 0
    else
        return 1
    fi
}

deactivate_venv() {
    if command -v deactivate > /dev/null 2>&1; then
        deactivate
    fi
    unset VIRTUAL_ENV
}

setup_new_venv() {
    local python_executable=""
    if command -v python3 &>/dev/null; then python_executable="python3";
    elif command -v python &>/dev/null; then python_executable="python";
    else return 1; fi

    "$python_executable" -m venv "$VENV_DIR" && \
    (source "$VENV_DIR/bin/activate" || source "$VENV_DIR/Scripts/activate") && \
    python -m pip install --upgrade pip --disable-pip-version-check --quiet
    return $?
}

ensure_venv_is_ready() {
    local retry_done=false
    while true; do
        if [[ ! -d "$VENV_DIR" ]]; then
            if ! run_with_spinner "Setting up virtual environment at '$VENV_DIR'" setup_new_venv; then
                log_status "Critical error: Failed to create venv" 1
                return 1
            fi
            if ! activate_venv; then
                log_status "Critical error: Failed to activate newly created venv" 1
                rm -rf "$VENV_DIR"
                return 1
            fi
            if ! run_pip_with_inline_progress "Installing dependencies" python -m pip install -r "$REQUIREMENTS" --disable-pip-version-check; then
                log_status "Critical error: Failed to install dependencies in new venv" 1
                rm -rf "$VENV_DIR"
                return 1
            fi
            touch "$VENV_DIR/.installed"
            return 0
        else
            if ! activate_venv; then
                log_status "Failed to activate existing venv. Considering it corrupted" 1
                 if $retry_done; then log_status "Error: Retry activation also failed" 1; return 1; fi
                log_info "Removing potentially corrupted venv for recreation..."
                rm -rf "$VENV_DIR"
                retry_done=true
                continue
            fi

            local update_needed=false
            if [[ ! -f "$VENV_DIR/.installed" ]] || [[ "$REQUIREMENTS" -nt "$VENV_DIR/.installed" ]]; then
                update_needed=true
            fi

            if $update_needed; then
                if ! run_pip_with_inline_progress "Checking/Updating dependencies" python -m pip install -r "$REQUIREMENTS" --disable-pip-version-check; then
                    log_status "Dependency installation failed. Venv may be corrupted." 1
                    if $retry_done; then log_status "Error: Dependency installation failed again" 1; return 1; fi
                    log_info "Removing venv for recreation..."
                    deactivate_venv
                    rm -rf "$VENV_DIR"
                    retry_done=true
                    continue
                else
                    touch "$VENV_DIR/.installed"
                fi
            else
                log_status "Dependencies are up to date" 0
            fi
            return 0
        fi
    done
}

enable_logging_action() {
    log_info "Attempting to enable logging..."
    if ensure_venv_is_ready; then
        python "$APP_MAIN" --enable-logging
        deactivate_venv
        log_status "Logging setting updated" 0
    else
        log_status "Failed to prepare environment. Aborting." 1
        exit 1
    fi
}

disable_logging_action() {
    log_info "Attempting to disable logging..."
    if ensure_venv_is_ready; then
        python "$APP_MAIN" --disable-logging
        deactivate_venv
        log_status "Logging setting updated" 0
    else
        log_status "Failed to prepare environment. Aborting." 1
        exit 1
    fi
}

show_help() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  run [args...]      Run the application with optional GUI arguments."
    echo "  install            Install or update dependencies."
    echo "  recreate           Recreate the virtual environment."
    echo "  delete             Delete the virtual environment and caches."
    echo "  --enable-logging   Permanently enable debug logging."
    echo "  --disable-logging  Permanently disable debug logging."
    echo "  help, --help       Show this help message."
    echo ""
}

recreate_action() {
    log_info "Recreating virtual environment..."
    if [ -d "$VENV_DIR" ]; then
        log_info "Removing existing venv at '$VENV_DIR'..."
        deactivate_venv
        if rm -rf "$VENV_DIR"; then
            log_status "Existing venv removed" 0
        else
            log_status "Failed to remove venv. Please remove it manually" 1
            exit 1
        fi
    fi
    ensure_venv_is_ready
}

delete_action() {
    log_info "Starting cleanup..."
    if [ -d "$VENV_DIR" ]; then
        log_info "Removing virtual environment at '$VENV_DIR'..."
        deactivate_venv
        rm -rf "$VENV_DIR"
        log_status "Virtual environment removed" 0
    else
        log_info "Virtual environment not found, skipping."
    fi

    log_info "Removing '__pycache__' directories..."
    find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} +
    log_status "'__pycache__' directories removed" 0
    log_info "Cleanup complete."
}

handle_interrupt() {
    printf "\n"
    log_info "Operation cancelled by user. Cleaning up..."
    tput cnorm 2>/dev/null || true 
    deactivate_venv
    log_info "Cleanup complete. Exiting."
    printf "${COLOR_RESET}\n"
    exit 130
}
trap handle_interrupt INT

COMMAND=$1
case "$COMMAND" in
      
    run)
        shift
        gui_args=()

        for arg in "$@"; do
            case "$arg" in
                --enable-logging)
                    enable_logging_action
                    ;;
                --disable-logging)
                    disable_logging_action
                    ;;
                *)
                    gui_args+=("$arg")
                    ;;
            esac
        done

        if ensure_venv_is_ready; then
            log_info "Running application..."
            python "$APP_MAIN" "${gui_args[@]}"
            app_exit_code=$?
            deactivate_venv
            log_info "Application finished with exit code: $app_exit_code"
            exit $app_exit_code
        else
            deactivate_venv
            log_status "Failed to prepare environment. Aborting." 1
            exit 1
        fi
        ;;    
    recreate)
        recreate_action
        deactivate_venv
        ;;
    delete)
        delete_action
        ;;
    enable-logging)
        enable_logging_action
        ;;
    disable-logging)
        disable_logging_action
        ;;
    ""|help|--help)
        show_help
        ;;
    *)
        log_info "Error: Unknown command '$COMMAND'" [cite: 76]
        show_help
        exit 1
        ;;
esac

printf "${COLOR_RESET}"
exit 0