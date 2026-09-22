"""Contract: Qt's ``QObject.tr`` must never be used — anywhere, ever.

The project i18n is JSON-only (``resources.translations`` app roots incl. tab
roots, ``dialog._tr`` instance translators, injected ``self.tr = tr_func``
resolvers, ``context.tr(key, default)`` context objects). There is no Qt
translation machinery at all: zero ``QTranslator``/``installTranslator``/
``.qm`` in the tree — ``QObject.tr`` has no legitimate caller.

Why an absolute ban (lesson 2026-09-22, settings raw-key labels):
``QObject.tr(sourceText, lang)`` treats ``lang`` as a *disambiguation
comment* (gettext ``msgctxt`` heritage; language is ambient state via
installed translators, not a per-call argument) and returns the raw
sourceText when ``(source, lang)`` misses the ``.qm`` — silently, no error.
JSON keys therefore render as ``image_gallery.settings.enable_ai`` instead
of the translation. Name collision with our JSON ``tr`` made the mistake
easy: any ``obj.tr(...)`` on a QObject reaches Qt, never our resolver.

Rules (enforced by this file):
1. ``getattr(x, "tr")`` / ``hasattr(x, "tr")`` — banned (stringly-time reach
   into Qt tr; the exact vector of the 2026-09-22 ``_dialog_tr`` bug).
2. ANY attribute-call ``obj.tr(...)`` — banned, unless the receiver follows
   an established custom-resolver convention where ``tr`` is a PLAIN
   attribute holding a JSON resolver, never QObject.tr:
   - ``self.tr(...)`` inside a class that injects ``self.tr = tr_func``, or
   - ``context.tr(...)`` / ``self._context.tr(...)`` context objects.
   Non-plain receivers (``dialog.tr``, ``widget.tr``, ...) are violations
   even with variable keys — there is no case where they are not Qt tr.
"""

from __future__ import annotations

import ast
import re

from ._framework import SRC, iter_py, parse, rel

# Custom-resolver receiver conventions (plain classes / context objects —
# `tr` there is an attribute holding our JSON resolver, never QObject.tr).
CONTEXT_RECEIVER_ATTRS = {"context", "_context"}

KEY_LITERAL_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")


def _base_names(node: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for b in node.bases:
        if isinstance(b, ast.Name):
            out.append(b.id)
        elif isinstance(b, ast.Attribute):
            out.append(b.attr)
    return out


def _injects_self_tr(node: ast.ClassDef) -> bool:
    """Class assigns ``self.tr = ...`` (injected JSON resolver convention)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assign):
            targets = sub.targets
        elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
            targets = [sub.target]
        else:
            continue
        for t in targets:
            if (
                isinstance(t, ast.Attribute)
                and t.attr == "tr"
                and isinstance(t.value, ast.Name)
                and t.value.id == "self"
            ):
                return True
    return False


def _receiver_is_context(func: ast.Attribute) -> bool:
    v = func.value
    if isinstance(v, ast.Name):
        return v.id in CONTEXT_RECEIVER_ATTRS
    if isinstance(v, ast.Attribute):
        return v.attr in CONTEXT_RECEIVER_ATTRS
    return False


def _scan_stmts(
    body: list[ast.stmt],
    injects_tr: bool,
    violations: list[str],
    path: str,
) -> None:
    """Scan statements for tr violations (skips nested ClassDefs' own bodies)."""
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.ClassDef):
            continue  # own scope: own injection flag, scanned separately
        for child in ast.iter_child_nodes(node):
            stack.append(child)
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        line = getattr(node, "lineno", 0)

        # Rule 1: getattr(x, "tr") / hasattr(x, "tr")
        if isinstance(func, ast.Name) and func.id in ("getattr", "hasattr"):
            if len(node.args) >= 2:
                a1 = node.args[1]
                if isinstance(a1, ast.Constant) and a1.value == "tr":
                    violations.append(
                        f"{path}:{line} rule1: {func.id}(x, \"tr\") — stringly "
                        f"reach into Qt tr; use an explicit JSON resolver"
                    )
            continue

        # Rule 2: any attribute-call obj.tr(...)
        if not isinstance(func, ast.Attribute) or func.attr != "tr":
            continue
        recv = func.value
        if isinstance(recv, ast.Name) and recv.id == "self":
            if injects_tr:
                continue  # self.tr = tr_func (plain coordinator convention)
            violations.append(
                f"{path}:{line} rule2: self.tr(...) — on a QObject this is Qt "
                f"tr (returns raw keys); inject tr_func or use _tr/app tr"
            )
            continue
        if (
            isinstance(recv, ast.Call)
            and isinstance(recv.func, ast.Name)
            and recv.func.id == "super"
        ):
            violations.append(
                f"{path}:{line} rule2: super().tr(...) is always Qt tr"
            )
            continue
        if _receiver_is_context(func):
            continue  # context.tr(key, default) convention
        try:
            recv_src = ast.unparse(recv)
        except Exception:
            recv_src = "?"
        extra = ""
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
            node.args[0].value, str
        ):
            if KEY_LITERAL_RE.match(str(node.args[0].value)):
                extra = f" (literal JSON key {node.args[0].value!r} would render raw)"
        violations.append(
            f"{path}:{line} rule2: {recv_src}.tr(...) is Qt tr — JSON i18n only; "
            f"use _tr / app tr / context convention{extra}"
        )


def test_no_qt_tr_anywhere():
    """QObject.tr must never be the i18n path — see module docstring."""
    violations: list[str] = []
    for p in iter_py(SRC):
        tree = parse(p)
        if tree is None:
            continue
        path = rel(p)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                inj = _injects_self_tr(node)
                _scan_stmts(node.body, inj, violations, path)
            else:
                _scan_stmts([node], False, violations, path)

    assert not violations, (
        "Qt tr must never be used for i18n (test_no_qt_tr):\n  "
        + "\n  ".join(violations)
    )
