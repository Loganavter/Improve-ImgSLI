#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/venv"
APP_MAIN="$SCRIPT_DIR/src/Improve_ImgSLI.py"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

show_spinner() {
  local pid=$1
  local msg=$2
  local delay=0.1
  local spinstr='/-\|'

  local msg_len
  msg_len=$(printf "%s" "$msg" | wc -c)
  local clear_len=$((msg_len + 3))
  local clear_str=$(printf "%${clear_len}s" "")

  while ps -p $pid > /dev/null; do
    local temp=${spinstr#?}
    printf "\r%s %c " "$msg" "$spinstr"
    local spinstr=$temp${spinstr%"$temp"}
    sleep $delay
  done

  printf "\r%s\r" "$clear_str"
}

run_with_spinner() {
    local msg=$1
    shift
    local error_log
    error_log=$(mktemp) || { echo "Error: Failed to create temporary file"; exit 1; }
    trap 'rm -f "$error_log"' RETURN

    "$@" > /dev/null 2> "$error_log" &
    local cmd_pid=$!

    show_spinner $cmd_pid "$msg"
    wait $cmd_pid
    local exit_code=$?

    if [ $exit_code -ne 0 ]; then
        echo "$msg [ERROR]"
        cat "$error_log" >&2
        rm -f "$error_log"
        trap - RETURN
        return $exit_code
    else
        rm -f "$error_log"
        trap - RETURN
        return 0
    fi
}

activate_venv() {
    local activate_script=""
    if [ -f "$VENV_DIR/bin/activate" ]; then
        activate_script="$VENV_DIR/bin/activate"
    elif [ -f "$VENV_DIR/Scripts/activate" ]; then
        activate_script="$VENV_DIR/Scripts/activate"
    fi

    if [ -n "$activate_script" ]; then
        source "$activate_script"
        if [ -z "$VIRTUAL_ENV" ] || [ "$VIRTUAL_ENV" != "$VENV_DIR" ]; then
             echo "Error: Failed to activate venv correctly ($activate_script). VIRTUAL_ENV variable not set or incorrect."
             return 1
        fi
        if ! command -v python > /dev/null || ! command -v pip > /dev/null; then
             echo "Error: python or pip not found in activated venv ($VIRTUAL_ENV)."
             type deactivate > /dev/null && deactivate
             return 1
        fi
        return 0
    else
        echo "Error: Virtual environment activation script not found in $VENV_DIR"
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
    echo "Creating virtual environment in $VENV_DIR..."
    if ! python3 -m venv "$VENV_DIR" > /dev/null 2>&1 && ! python -m venv "$VENV_DIR" > /dev/null 2>&1; then
        echo "Error: Failed to create virtual environment using python3 or python."
        return 1
    fi
    if [ ! -d "$VENV_DIR" ]; then
         echo "Error: Venv directory ($VENV_DIR) was not created."
         return 1
    fi

    if ! activate_venv; then
        echo "Error: Failed to activate the newly created venv."
        rm -rf "$VENV_DIR"
        return 1
    fi

    run_with_spinner "Updating pip..." pip install --upgrade pip --disable-pip-version-check --quiet
    if [ $? -ne 0 ]; then
        echo "Error updating pip."
        deactivate_venv
        rm -rf "$VENV_DIR"
        return 1
    fi

    run_with_spinner "Installing dependencies..." pip install -r "$REQUIREMENTS" --disable-pip-version-check --quiet
    if [ $? -ne 0 ]; then
        echo "Error installing dependencies."
        deactivate_venv
        rm -rf "$VENV_DIR"
        return 1
    fi

    if ! touch "$VENV_DIR/.installed"; then
        echo "Error: Failed to create marker file .installed"
        deactivate_venv
        rm -rf "$VENV_DIR"
        return 1
    fi

    echo "Environment setup complete."
    return 0
}


venv_ready=false
retry_done=false

while ! $venv_ready; do

    if [ ! -d "$VENV_DIR" ]; then
        if ! setup_new_venv; then
            echo "Critical error: Failed to create and set up venv."
            exit 1
        fi
        venv_ready=true
    else
        echo "Existing virtual environment found."
        if ! activate_venv; then
             echo "Failed to activate existing venv. Considering it corrupted."
             if $retry_done; then
                 echo "Error: Retry activation attempt also failed after recreation."
                 exit 1
             fi
             echo "Removing potentially corrupted venv..."
             rm -rf "$VENV_DIR"
             retry_done=true
             continue
        fi

        update_needed=false
        if [ ! -f "$VENV_DIR/.installed" ]; then
            echo "Installation marker .installed is missing."
            update_needed=true
        elif [ "$REQUIREMENTS" -nt "$VENV_DIR/.installed" ]; then
            echo "requirements.txt is newer than the installation marker."
            update_needed=true
        fi

        install_ok=true
        if $update_needed; then
            run_with_spinner "Checking/Updating dependencies..." pip install -r "$REQUIREMENTS" --disable-pip-version-check --quiet
            if [ $? -ne 0 ]; then
                install_ok=false
                echo "Error updating dependencies in existing venv."
            else
                touch "$VENV_DIR/.installed"
                echo "Dependencies updated successfully."
            fi
        fi

        if $install_ok; then
            venv_ready=true
        else
            if $retry_done; then
                echo "Critical error: Failed to install dependencies even after recreating venv."
                deactivate_venv
                exit 1
            fi

            echo "Venv seems corrupted. Removing for recreation..."
            deactivate_venv
            rm -rf "$VENV_DIR"
            retry_done=true
        fi
    fi
done

if [ -z "$VIRTUAL_ENV" ] || [ "$VIRTUAL_ENV" != "$VENV_DIR" ]; then
     echo "WARNING: Venv not active before running the application. Attempting to activate again..."
     if ! activate_venv; then
         echo "Critical error: Failed to activate venv right before running the application."
         exit 1
     fi
fi

echo "Running application"
python "$APP_MAIN"
app_exit_code=$?

deactivate_venv

echo "Application finished with exit code: $app_exit_code"
exit $app_exit_code