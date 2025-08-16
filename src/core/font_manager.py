from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication
from utils.resource_loader import resource_path
import os
import logging

logger = logging.getLogger("ImproveImgSLI")

class FontManager(QObject):
	_instance = None
	font_changed = pyqtSignal()

	@classmethod
	def get_instance(cls):
		if cls._instance is None:
			cls._instance = FontManager()
		return cls._instance

	def __init__(self):
		if FontManager._instance is not None:
			raise RuntimeError("FontManager is a singleton, use get_instance()")
		super().__init__()
		self._current_mode: str = "builtin"
		self._current_family: str = ""
		self._built_in_font_path = "resources/fonts/SourceSans3-Regular.ttf"
		self._built_in_family_cache: str | None = None

	def apply_from_state(self, app_state):
		mode = getattr(app_state, "ui_font_mode", "builtin") or "builtin"
		family = getattr(app_state, "ui_font_family", "") or ""
		self.set_font(mode=mode, family=family)

	def _ensure_builtin_loaded(self) -> str | None:
		if self._built_in_family_cache:
			return self._built_in_family_cache
		try:
			path = resource_path(self._built_in_font_path)
			if os.path.exists(path):
				font_id = QFontDatabase.addApplicationFont(path)
				families = QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
				if families:
					self._built_in_family_cache = families[0]
					return self._built_in_family_cache
		except Exception:
			pass
		return None

	def set_font(self, mode: str, family: str = ""):

		if mode == "system":
			mode = "system_default"
		if mode not in ("builtin", "system_default", "system_custom"):
			mode = "builtin"
		self._current_mode = mode
		self._current_family = family or ""

		app = QApplication.instance()
		if not app:
			return

		if mode == "builtin":
			final_family = self._ensure_builtin_loaded()
			if final_family:
				app.setFont(QFont(final_family))
			else:
				app.setFont(QFont())
		elif mode == "system_default":

			try:
				sys_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
				app.setFont(sys_font)
			except Exception:
				app.setFont(QFont())
		else:

			final_family = self._current_family or ""
			if final_family:
				app.setFont(QFont(final_family))
			else:
				app.setFont(QFont())
		self.font_changed.emit()
