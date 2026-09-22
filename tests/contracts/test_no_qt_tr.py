"""Contract: Qt's ``QObject.tr`` must never be used — anywhere, ever.

Two naming domains, zero overlap:

- **module** ``tr`` — the JSON translator (``resources.translations.tr``,
  toolkit twin), imported BARE: ``from resources.translations import tr``.
  Never reached as an attribute of an object.
- **instance** ``_tr`` — every object-level resolver: ``TabContext._tr``,
  ``SettingsDialog._tr``, injected ``self._tr = tr_func``, child-widget
  ``self._tr`` storage, ``translate`` as the callable kwarg for passing
  resolvers into widgets. No object anywhere may carry an attribute named
  ``tr``.

Qt's ``QObject.tr`` belongs to neither domain and is never the i18n path:
the tree has zero ``QTranslator``/``installTranslator``/``.qm``, and
``QObject.tr(sourceText, lang)`` treats ``lang`` as a *disambiguation
comment* (gettext ``msgctxt`` heritage; language is ambient state via
installed translators, not a per-call argument) — returning the raw
sourceText on a miss, silently, no error. JSON keys would therefore render
as ``image_gallery.settings.enable_ai`` instead of the translation (lesson
2026-09-22, settings raw-key labels). Name collision with our JSON ``tr``
made that mistake easy: any ``obj.tr(...)`` on a QObject reaches Qt, never
our resolver.

Rules (absolute — no allowlists, enforced by this file):

1. Any attribute-call ``obj.tr(...)`` — banned. On a QObject it is Qt tr;
   anywhere else it is a domain violation (use a bare module import or the
   instance ``_tr``).
2. ``getattr(x, "tr")`` / ``hasattr(x, "tr")`` — banned (stringly-time
   reach into Qt tr; the exact vector of the 2026-09-22 ``_dialog_tr`` bug).
3. Any assignment to an attribute named ``tr`` (``self.tr = ...``,
   ``dialog.tr = ...``, ``x.tr = ...``) — banned (reintroduction of an
   instance-domain ``tr`` attribute).
"""

from __future__ import annotations

import ast
import re

from ._framework import SRC, iter_py, parse, rel

KEY_LITERAL_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")


def _scan_tree(tree: ast.AST, path: str, violations: list[str]) -> None:
    """Collect rule 1/2/3 violations anywhere in ``tree``."""
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)

        if isinstance(node, ast.Call):
            func = node.func
            # Rule 2: getattr(x, "tr") / hasattr(x, "tr")
            if isinstance(func, ast.Name) and func.id in ("getattr", "hasattr"):
                if len(node.args) >= 2:
                    a1 = node.args[1]
                    if isinstance(a1, ast.Constant) and a1.value == "tr":
                        violations.append(
                            f"{path}:{line} rule2: {func.id}(x, \"tr\") — stringly "
                            f"reach into Qt tr; use the instance _tr / bare module tr"
                        )
                continue
            # Rule 1: any attribute-call obj.tr(...)
            if isinstance(func, ast.Attribute) and func.attr == "tr":
                try:
                    recv_src = ast.unparse(func.value)
                except Exception:
                    recv_src = "?"
                extra = ""
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
                    node.args[0].value, str
                ):
                    if KEY_LITERAL_RE.match(str(node.args[0].value)):
                        extra = (
                            f" (literal JSON key {node.args[0].value!r} would render raw)"
                        )
                violations.append(
                    f"{path}:{line} rule1: {recv_src}.tr(...) — Qt tr / wrong "
                    f"domain; JSON i18n only: bare module tr or instance _tr{extra}"
                )
            continue

        # Rule 3: any assignment target x.tr = ...
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        else:
            continue
        for t in targets:
            if isinstance(t, ast.Attribute) and t.attr == "tr":
                violations.append(
                    f"{path}:{line} rule3: assignment to attribute 'tr' — banned; "
                    f"instance resolvers are named _tr"
                )


def test_no_qt_tr_anywhere():
    """QObject.tr must never be the i18n path — see module docstring."""
    violations: list[str] = []
    for p in iter_py(SRC):
        tree = parse(p)
        if tree is None:
            continue
        _scan_tree(tree, rel(p), violations)

    assert not violations, (
        "Qt tr must never be used for i18n (test_no_qt_tr):\n  "
        + "\n  ".join(violations)
    )
