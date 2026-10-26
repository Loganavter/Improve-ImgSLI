"""The AI backend package — plugin convention (ADR 009 A1/A2).

The registry discovers a backend by importing its module and registering the
module's ``BACKEND``; there is no hand-maintained list. The adapter itself lives
in :mod:`.profile` so this file stays a declaration.
"""

from __future__ import annotations

from .profile import CAPABILITIES, AIBackend

#: The process-wide adapter the composition point registers (``registry["ai"]``).
BACKEND = AIBackend()

__all__ = ["BACKEND", "CAPABILITIES", "AIBackend"]
