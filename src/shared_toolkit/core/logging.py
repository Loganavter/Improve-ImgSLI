import logging
import os
import sys

def get_log_directory(app_name: str):
    """
    Get the appropriate log directory for the application based on the platform.

    Args:
        app_name: Name of the application (e.g., "Improve-ImgSLI", "Tkonverter")

    Returns:
        str: Path to the log directory
    """
    logger = logging.getLogger(app_name)

    if sys.platform == "win32":
        app_data_dir = os.getenv("APPDATA")
        if not app_data_dir:
            app_data_dir = os.path.expanduser("~")
            logger.warning(
                "Could not find APPDATA env variable, falling back to home directory."
            )
        return os.path.join(app_data_dir, app_name)

    elif sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~/Library/Application Support"), app_name
        )

    else:
        xdg_data_home = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return os.path.join(xdg_data_home, app_name)

def setup_logging(app_name: str, debug_enabled: bool = False, debug_env_var: str = None):
    """
    Setup logging for the application.

    Args:
        app_name: Name of the application (e.g., "Improve-ImgSLI", "Tkonverter")
        debug_enabled: Whether to enable debug logging
        debug_env_var: Environment variable name to check for debug mode (e.g., "IMPROVE_DEBUG", "DEBUG")
    """
    logger = logging.getLogger(app_name)

    if debug_env_var:
        suppress_debug = os.getenv(f"{debug_env_var.replace('_DEBUG', '_SUPPRESS_DEBUG')}", "0") == "1"
        if suppress_debug:
            debug_enabled = False
        elif os.getenv(debug_env_var, "0") == "1":
            debug_enabled = True

    level = logging.DEBUG if debug_enabled else logging.INFO

    if logger.handlers:
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)
        return

    logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - [%(levelname)s] - (%(filename)s:%(lineno)d) - %(message)s"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    try:
        log_dir = get_log_directory(app_name)
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "log.txt")

        file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)

    except Exception:
        logger.error(
            "FATAL: Failed to set up file logger. Continuing with console-only logging.",
            exc_info=True,
        )

def setup_simple_logging(app_name: str, level: int = logging.WARNING):
    """
    Setup simple logging for applications that don't need file logging.

    Args:
        app_name: Name of the application
        level: Logging level (default: WARNING)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)

    app_logger = logging.getLogger(app_name)
    app_logger.setLevel(level)
