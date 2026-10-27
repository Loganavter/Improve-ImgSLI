# provenance: tests/devtools/test_capture_dpr_units.py:184 @ 230431a52
# rule: none
"""LEGAL fixture: a ratio literal comparison against the test's OWN input.

Verbatim from the capture gate. The pixmap is constructed with
`setDevicePixelRatio(2.0)` two lines above, so `== 2.0` compares the assertion
with the value the test itself planted; asserting `devicePixelRatioF()` there
would be tautological. Rule `ratio-hardcoded` may fire on the comparison shape in
general (an assumed host ratio), but the tree entry for this file is allowlisted
with this reason — this fixture pins the *precision* half: the literal is only
acceptable when the fixture set it.
"""

from __future__ import annotations


def _check(grab):
    assert grab.devicePixelRatio() == 2.0
