#!/bin/bash

COLOR_RESET="\033[0m"
BG_RED="\033[0;41m"
BG_GREEN="\033[0;42m"
BG_YELLOW="\033[0;43m"
TEXT_WHITE="\033[1;37m"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/venv"
APP_MAIN="$SCRIPT_DIR/src/Improve_ImgSLI.py"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"


RECREATE_VENV=false
APP_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --recreate)
      RECREATE_VENV=true
      shift
      ;;
    *)
      APP_ARGS+=("$1")
      shift
      ;;
  esac
done


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

  local msg_len=${#msg}
  local clear_len=$((msg_len + 3))
  local clear_str
  printf -v clear_str '%*s' "$clear_len" ''

  while ps -p "$pid" > /dev/null; do
    local temp=${spinstr#?}
    printf "\r%s\r%s %c " "$clear_str" "$msg" "${spinstr:0:1}"
    spinstr=$temp${spinstr%"$temp"}
    sleep "$delay"
  done

  printf "\r%s\r" "$clear_str"
}

run_with_spinner() {
    local base_msg=$1
    shift

    local terminal_cols=$(tput cols 2>/dev/null)
    if [[ -z "$terminal_cols" || "$terminal_cols" -eq 0 ]]; then
        terminal_cols=80
    fi

    local max_spinner_msg_len=$((terminal_cols - 4))

    local spinner_msg_content="$base_msg"

    if [[ ${#spinner_msg_content} -gt "$max_spinner_msg_len" ]]; then
        spinner_msg_content="${spinner_msg_content:0:$((max_spinner_msg_len - 3))}..."
    fi

    local spinner_msg="$spinner_msg_content..."

    local error_log
    error_log=$(mktemp) || { log_status "Failed to create temporary file" 1; exit 1; }
    trap 'rm -f "$error_log"' RETURN

    "$@" > /dev/null 2>"$error_log" & 
    local cmd_pid=$!

    show_spinner "$cmd_pid" "$spinner_msg"
    wait "$cmd_pid"
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        printf "%s ${BG_RED}${TEXT_WHITE}[ERROR]${COLOR_RESET}\n" "$base_msg"
        sed -r "s/\x1B\[([0-9]{1,3}(;[0-9]{1,3})*)?[mGK]//g" "$error_log" >&2
    else
        printf "%s ${BG_GREEN}${TEXT_WHITE}[OK]${COLOR_RESET}\n" "$base_msg"
    fi
    return $exit_code
}

get_canonical_path() {
    if [[ -z "$1" ]]; then return 1; fi
    local resolved_path
    if [[ -d "$1" ]]; then
        resolved_path="$(cd "$1" && pwd)"
    elif [[ -f "$1" ]]; then
        resolved_path="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
    else
        local parent_dir
        parent_dir=$(dirname "$1")
        if [[ -d "$parent_dir" ]]; then
             resolved_path="$(cd "$parent_dir" && pwd)/$(basename "$1")"
        else
             log_info "$1"
             return 0
        fi
    fi
    log_info "$resolved_path"
    return 0
}

activate_venv() {
    local activate_script=""
    local canonical_venv_dir
    canonical_venv_dir=$(get_canonical_path "$VENV_DIR")

    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        activate_script="$VENV_DIR/bin/activate"
    elif [[ -f "$VENV_DIR/Scripts/activate" ]]; then
        activate_script="$VENV_DIR/Scripts/activate"
    fi

    if [[ -n "$activate_script" ]]; then
        source "$activate_script"
        local current_virtual_env_path=""
        [[ -n "$VIRTUAL_ENV" ]] && current_virtual_env_path=$(get_canonical_path "$VIRTUAL_ENV")

        if [[ -z "$VIRTUAL_ENV" ]] || [[ "$current_virtual_env_path" != "$canonical_venv_dir" ]]; then
             log_status "Failed to activate venv correctly ($activate_script). VIRTUAL_ENV is '$VIRTUAL_ENV' (resolved: '$current_virtual_env_path'), expected '$canonical_venv_dir'" 1
             return 1
        fi
        if ! command -v python > /dev/null || ! command -v pip > /dev/null; then
             log_status "Python or pip not found in activated venv ($VIRTUAL_ENV)" 1
             type deactivate &>/dev/null && deactivate
             return 1
        fi
        log_status "Virtual environment activated successfully" 0
        return 0
    else
        log_status "Virtual environment activation script not found in $VENV_DIR" 1
        return 1
    fi
}

deactivate_venv() {
    if command -v deactivate > /dev/null 2>&1; then
        deactivate
        log_info "Virtual environment deactivated"
    fi
    unset VIRTUAL_ENV
}

setup_new_venv() {
    log_info "Initiating virtual environment setup for '$VENV_DIR'..."
    local python_executable=""
    if command -v python3 &>/dev/null; then
        python_executable="python3"
        log_status "Python 3 executable found" 0
    elif command -v python &>/dev/null; then
        python_executable="python"
        log_status "Python 2/fallback executable found" 0
    else
        log_status "Neither python3 nor python found in PATH. Cannot create virtual environment" 1
        return 1
    fi
    log_info "Using '$python_executable' for venv creation"

    run_with_spinner "Creating virtual environment at '$VENV_DIR'" "$python_executable" -m venv "$VENV_DIR"
    if [[ $? -ne 0 ]]; then
        log_status "Virtual environment creation failed" 1
        return 1
    fi

    if [[ ! -d "$VENV_DIR" ]]; then
         log_status "Venv directory ($VENV_DIR) was not created by the venv command" 1
         return 1
    fi

    if ! activate_venv; then
        log_status "Failed to activate the newly created venv" 1
        rm -rf "$VENV_DIR"
        return 1
    fi

    run_with_spinner "Updating pip in new venv" python -m pip install --upgrade pip --disable-pip-version-check --quiet
    if [[ $? -ne 0 ]]; then
        log_status "Failed updating pip" 1
        deactivate_venv
        rm -rf "$VENV_DIR"
        return 1
    fi

    run_with_spinner "Installing dependencies in new venv" python -m pip install -r "$REQUIREMENTS" --disable-pip-version-check --quiet
    if [[ $? -ne 0 ]]; then
        log_status "Failed installing dependencies" 1
        deactivate_venv
        rm -rf "$VENV_DIR"
        return 1
    fi

    if ! touch "$VENV_DIR/.installed"; then
        log_status "Failed to create marker file .installed" 1
        deactivate_venv
        rm -rf "$VENV_DIR"
        return 1
    fi

    log_info "Virtual environment setup complete"
    return 0
}

if $RECREATE_VENV && [ -d "$VENV_DIR" ]; then
    log_info "Removing existing venv due to --recreate flag..."
    deactivate_venv
    if rm -rf "$VENV_DIR"; then
        log_status "Existing venv removed" 0
    else
        log_status "Failed to remove existing venv $VENV_DIR. Please remove it manually" 1
        exit 1
    fi
fi

venv_ready=false
retry_done=false

while ! $venv_ready; do
    if [[ ! -d "$VENV_DIR" ]]; then
        if ! setup_new_venv; then
            log_status "Critical error: Failed to create and set up venv" 1
            exit 1
        fi
        venv_ready=true
    else
        log_status "Existing virtual environment found at '$VENV_DIR'" 0
        if ! activate_venv; then
             log_status "Failed to activate existing venv. Considering it corrupted" 1
             if $retry_done; then
                 log_status "Error: Retry activation attempt also failed after recreation" 1
                 exit 1
             fi
             log_info "Removing potentially corrupted venv for recreation..."
             deactivate_venv
             rm -rf "$VENV_DIR"
             retry_done=true
             continue
        fi

        update_needed=false
        if [[ ! -f "$VENV_DIR/.installed" ]]; then
            log_info "Installation marker .installed is missing"
            update_needed=true
        elif [[ "$REQUIREMENTS" -nt "$VENV_DIR/.installed" ]]; then
            log_info "requirements.txt is newer than the installation marker"
            update_needed=true
        fi

        install_ok=true
        if $update_needed; then
            run_with_spinner "Checking/Updating dependencies in existing venv" python -m pip install -r "$REQUIREMENTS" --disable-pip-version-check --quiet
            if [[ $? -ne 0 ]]; then
                install_ok=false
                log_status "Failed updating dependencies in existing venv" 1
            else
                touch "$VENV_DIR/.installed"
                log_status "Dependencies updated successfully" 0
            fi
        fi

        if $install_ok; then
            venv_ready=true
        else
            if $retry_done; then
                log_status "Critical error: Failed to install dependencies even after recreating venv" 1
                deactivate_venv
                exit 1
            fi
            log_info "Venv seems corrupted. Removing for recreation..."
            deactivate_venv
            rm -rf "$VENV_DIR"
            retry_done=true
        fi
    fi
done

canonical_venv_dir_final=$(get_canonical_path "$VENV_DIR")
current_virtual_env_path_final=""
[[ -n "$VIRTUAL_ENV" ]] && current_virtual_env_path_final=$(get_canonical_path "$VIRTUAL_ENV")

if [[ -z "$VIRTUAL_ENV" ]] || [[ "$current_virtual_env_path_final" != "$canonical_venv_dir_final" ]]; then
     log_info "WARNING: Venv not active before running the application. Attempting to activate again..."
     if ! activate_venv; then
         log_status "Critical error: Failed to activate venv right before running the application" 1
         exit 1
     fi
fi

log_info "Running application..."
python "$APP_MAIN" ${APP_ARGS[@]}
app_exit_code=$?

deactivate_venv
log_info "Application finished with exit code: $app_exit_code"
printf "${COLOR_RESET}\n"
exit $app_exit_code
