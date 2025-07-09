import traceback
from PyQt6.QtCore import QSettings, QPointF, QByteArray, QLocale, QObject
from PyQt6.QtGui import QColor
from services.state_manager import AppState, AppConstants
import logging

logger = logging.getLogger("ImproveImgSLI")

class SettingsManager:

    def __init__(self, organization_name: str, application_name: str):
        self.settings = QSettings(organization_name, application_name)

    def _get_setting(self, key: str, default, target_type):
        value = self.settings.value(key)
        if value is None:
            return default
        try:
            if target_type == int:
                try:
                    return int(float(value))
                except (ValueError, TypeError):
                    return default
            elif target_type == float:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            elif target_type == bool:
                if isinstance(value, str):
                    val_lower = value.lower()
                    if val_lower == 'true':
                        return True
                    if val_lower == 'false':
                        return False
                    try:
                        return bool(int(value))
                    except ValueError:
                        pass
                return bool(value) if isinstance(
                    value, (bool, int)) else default
            elif target_type == str:
                return str(value)
            elif target_type == QColor:
                color_val = str(value)
                if QColor.isValidColorName(color_val):
                    return QColor(color_val)
                test_color = QColor(color_val)
                if test_color.isValid():
                    return test_color
                return default
            elif target_type == QByteArray:
                if not isinstance(value, str):
                    logger.warning(
                        f"Expected Base64 string for QByteArray key '{key}', but got type {
                            type(value)}. Using default.")
                    return QByteArray()
                if not value:
                    return QByteArray()
                try:
                    missing_padding = len(value) % 4
                    if missing_padding:
                        value += '=' * (4 - missing_padding)
                    byte_data = QByteArray.fromBase64(value.encode('ascii'))
                    if byte_data.isNull():
                        logger.warning(
                            f"Base64 decoding resulted in null QByteArray for key '{key}'. Value: '{value[:50]}...'")
                        return QByteArray()
                    return byte_data
                except Exception as e_b64:
                    logger.warning(
                        f"Error decoding Base64 string for QByteArray key '{key}'. Value: '{value[:50]}...', Error: {e_b64}")
                    traceback.print_exc()
                    return QByteArray()
            elif target_type == QPointF:
                if not isinstance(value, str):
                    logger.warning(
                        f"Expected string 'x,y' for QPointF key '{key}', but got type {
                            type(value)}. Using default.")
                    return QPointF()
                try:
                    parts = value.split(',')
                    if len(parts) == 2:
                        return QPointF(float(parts[0]), float(parts[1]))
                except (ValueError, TypeError, IndexError) as e_point:
                    logger.warning(
                        f"Error parsing QPointF string for key '{key}'. Value: '{value}', Error: {e_point}")
                return QPointF()
            elif target_type == list:
                if isinstance(value, list):
                    if not value or all((isinstance(item, str)
                                        for item in value)):
                        return value
                    else:
                        logger.warning(
                            f"List for key '{key}' contains non-string elements. Using default.")
                        return []
                else:
                    logger.warning(
                        f"Expected list for key '{key}', but got type {
                            type(value)}. Using default.")
                    return []
            else:
                logger.warning(
                    f"Unhandled target type '{
                        target_type.__name__}' for key '{key}'. Returning raw value.")
                return value
        except Exception as e_unexpected:
            logger.error(
                f"Unexpected error processing setting '{key}' for type {
                    target_type.__name__}. Raw Value: '{value}', Error: {e_unexpected}")
            traceback.print_exc()
            return default

    def load_all_settings(self, app_state: AppState):
        app_state.loaded_debug_mode_enabled = self._get_setting('debug_mode_enabled', False, bool)
        app_state.debug_mode_enabled = app_state.loaded_debug_mode_enabled

        app_state.loaded_geometry = self._get_setting(
            'window_geometry', QByteArray(), QByteArray)
        app_state.loaded_was_maximized = self._get_setting(
            'window_was_maximized', False, bool)
        app_state.loaded_previous_geometry = self._get_setting(
            'previous_geometry', QByteArray(), QByteArray)
        saved_lang = self._get_setting('language', None, str)
        valid_languages = ['en', 'ru', 'zh', 'pt_BR']
        default_lang = QLocale.system().name().split('_')[0]
        if default_lang not in valid_languages:
            default_lang = 'en'
        app_state.current_language = saved_lang if saved_lang in valid_languages else default_lang
        app_state.max_name_length = max(
            AppConstants.MIN_NAME_LENGTH_LIMIT, min(
                AppConstants.MAX_NAME_LENGTH_LIMIT, self._get_setting(
                    'max_name_length', 30, int)))
        app_state.movement_speed_per_sec = max(
            0.1, min(
                5.0, self._get_setting(
                    'movement_speed_per_sec', 2.0, float)))
        default_color = QColor(255, 0, 0, 255)
        loaded_color_name = self._get_setting(
            'filename_color', default_color.name(
                QColor.NameFormat.HexArgb), str)
        app_state.file_name_color = QColor(loaded_color_name)
        if not app_state.file_name_color.isValid():
            app_state.file_name_color = default_color
        app_state.jpeg_quality = max(1, min(100, self._get_setting(
            'jpeg_quality', AppConstants.DEFAULT_JPEG_QUALITY, int)))
        app_state.magnifier_offset_relative_visual = QPointF(
            app_state.magnifier_offset_relative)
        app_state.magnifier_spacing_relative_visual = app_state.magnifier_spacing_relative

    def save_all_settings(self, app_state: AppState, window_widget: QObject):
        runtime_prev_geom_valid = bool(
            app_state.loaded_previous_geometry is not None and isinstance(
                app_state.loaded_previous_geometry,
                QByteArray) and (
                not app_state.loaded_previous_geometry.isNull()) and (
                not app_state.loaded_previous_geometry.isEmpty()))
        current_geometry = window_widget.saveGeometry()
        if current_geometry and (not current_geometry.isEmpty()):
            self._save_setting('window_geometry', current_geometry)
        elif self.settings.contains('window_geometry'):
            try:
                self.settings.remove('window_geometry')
            except Exception as e:
                logger.warning(
                    f"Error removing invalid 'window_geometry' on close: {e}")
        should_save_as_maximized = window_widget.isMaximized() or window_widget.isFullScreen()
        self._save_setting('window_was_maximized', should_save_as_maximized)
        if should_save_as_maximized:
            if runtime_prev_geom_valid:
                self._save_setting(
                    'previous_geometry',
                    app_state.loaded_previous_geometry)
            elif self.settings.contains('previous_geometry'):
                try:
                    self.settings.remove('previous_geometry')
                except Exception as e:
                    logger.warning(
                        f"Error removing 'previous_geometry' setting on close (maximized but no valid previous geom): {e}")
        elif self.settings.contains('previous_geometry'):
            try:
                self.settings.remove('previous_geometry')
            except Exception as e:
                logger.warning(
                    f"Error removing 'previous_geometry' setting on close (normal): {e}")
        self._save_setting('language', app_state.current_language)
        self._save_setting('max_name_length', app_state.max_name_length)
        self._save_setting(
            'movement_speed_per_sec',
            app_state.movement_speed_per_sec)
        self._save_setting(
            'filename_color',
            app_state.file_name_color.name(
                QColor.NameFormat.HexArgb))
        self._save_setting('jpeg_quality', app_state.jpeg_quality)
        self._save_setting('debug_mode_enabled', app_state.debug_mode_enabled)
        self.settings.sync()

    def _save_setting(self, key: str, value):
        try:
            value_to_save = None
            if isinstance(value, QPointF):
                value_to_save = f'{value.x()},{value.y()}'
            elif isinstance(value, QColor):
                value_to_save = value.name(QColor.NameFormat.HexArgb)
            elif isinstance(value, QByteArray):
                if value.isNull() or value.isEmpty():
                    if self.settings.contains(key):
                        self.settings.remove(key)
                    return
                else:
                    value_to_save = value.toBase64().data().decode('ascii')
            elif isinstance(value, (int, float, bool, str)) or (isinstance(value, list) and all((isinstance(item, str) for item in value))):
                value_to_save = value
            else:
                logger.error(
                    f"Attempted to save unsupported type '{
                        type(value)}' for key '{key}'. Skipping save.")
                return
            if value_to_save is not None:
                self.settings.setValue(key, value_to_save)
        except Exception as e:
            logger.error(
                f"ERROR saving setting '{key}' (value type: {
                    type(value)}): {e}")
            traceback.print_exc()

    def restore_geometry(self, window_widget: QObject, app_state: AppState):
        geom_setting = app_state.loaded_geometry
        was_maximized = app_state.loaded_was_maximized
        geom_valid = geom_setting and isinstance(
            geom_setting, QByteArray) and (
            not geom_setting.isEmpty())
        restored_from_settings = False
        if geom_valid:
            try:
                restored_from_settings = True
                if was_maximized:
                    window_widget.restoreGeometry(geom_setting)
                    window_widget.showMaximized()
                else:
                    window_widget.restoreGeometry(geom_setting)
                    window_widget.showNormal()
            except Exception:
                traceback.print_exc()
                restored_from_settings = False
        if not restored_from_settings:
            window_widget.setGeometry(100, 100, 800, 600)
            window_widget.showNormal()
            app_state.loaded_previous_geometry = QByteArray()