"""Re-export ``NavigationManager`` and ``NavigationSection`` from the toolkit.

Application-specific section implementations live in
``core.navigation_sections``.
"""

from sli_ui_toolkit.managers import NavigationManager, NavigationSection

__all__ = ["NavigationManager", "NavigationSection"]
