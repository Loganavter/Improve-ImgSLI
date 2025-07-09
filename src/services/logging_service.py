import logging
import sys
import os
import traceback

logger = logging.getLogger("ImproveImgSLI")

def get_log_directory():
    """Determines the appropriate log directory based on the operating system."""
    app_name = "Improve-ImgSLI"
    
    if sys.platform == "win32":
        app_data_dir = os.getenv('APPDATA')
        if not app_data_dir:
            app_data_dir = os.path.expanduser('~')
            logger.warning("Could not find APPDATA env variable, falling back to home directory.")
        return os.path.join(app_data_dir, app_name)
    
    elif sys.platform == "darwin":
        return os.path.join(os.path.expanduser('~/Library/Application Support'), app_name)
        
    else:
        xdg_data_home = os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
        return os.path.join(xdg_data_home, app_name)


def setup_logging(debug_enabled: bool = False):
    level = logging.DEBUG if debug_enabled else logging.INFO
    
    if logger.handlers:
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)
        logger.info(f"Logger level updated to {logging.getLevelName(level)}.")
        return

    logger.setLevel(level)
    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - (%(filename)s:%(lineno)d) - %(message)s'
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    try:
        log_dir = get_log_directory()
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, 'log.txt')

        file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
        
        logger.info(f"File logging successfully set up. Log file at: {log_file_path}")

    except Exception as e:
        logger.error(f"FATAL: Failed to set up file logger. Continuing with console-only logging.", exc_info=True)

    logger.info(f"Logging initialized. Level: {logging.getLevelName(level)}.")