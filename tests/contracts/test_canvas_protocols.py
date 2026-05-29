"""Canvas widget protocol conformance.

The render pipeline talks to canvases through the duck-typed protocols in
``ui/widgets/gl_canvas/contracts.py``. Each concrete canvas must expose every
protocol method with a compatible signature, otherwise an export/preview path
breaks only at runtime with an ``AttributeError`` or ``TypeError``.

Dogma source: docs/dev/CONTRACTS.md §Canvas Widgets.
"""

from __future__ import annotations

import inspect

import pytest

from ui.widgets.gl_canvas.contracts import (
    BaseCanvasProtocol,
    ExportCanvasProtocol,
    GlLikeCanvasProtocol,
)
from ui.widgets.gl_canvas.widget import GLCanvas

def _protocol_methods(proto) -> dict[str, inspect.Signature]:
    """Method-name -> signature for every callable a protocol declares (incl. bases)."""
    methods: dict[str, inspect.Signature] = {}
    for klass in reversed(proto.__mro__):
        for name, member in vars(klass).items():
            if name.startswith("__"):
                continue
            if inspect.isfunction(member):
                methods[name] = inspect.signature(member)
    return methods

# GLCanvas is the single concrete canvas; it plays the GL-like *and* export role.
IMPLEMENTATIONS = {
    ("GLCanvas", GlLikeCanvasProtocol): GLCanvas,
    ("GLCanvas", ExportCanvasProtocol): GLCanvas,
    ("GLCanvas", BaseCanvasProtocol): GLCanvas,
}

CASES = list(IMPLEMENTATIONS.items())
CASE_IDS = [f"{name}-vs-{proto.__name__}" for (name, proto), _ in CASES]

@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_implementation_has_all_protocol_methods(case):
    (impl_name, proto), impl = case
    missing: list[str] = []
    for method_name in _protocol_methods(proto):
        attr = getattr(impl, method_name, None)
        if attr is None or not callable(attr):
            missing.append(method_name)
    assert not missing, (
        f"{impl_name} is missing protocol methods of {proto.__name__}: {missing}"
    )

@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_implementation_signatures_are_compatible(case):
    (impl_name, proto), impl = case
    problems: list[str] = []
    for method_name, proto_sig in _protocol_methods(proto).items():
        impl_attr = getattr(impl, method_name, None)
        if impl_attr is None:
            continue
        try:
            impl_sig = inspect.signature(impl_attr)
        except (TypeError, ValueError):
            continue
        impl_params = impl_sig.parameters
        accepts_var = any(
            p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
            for p in impl_params.values()
        )
        for pname, p in proto_sig.parameters.items():
            if pname == "self":
                continue
            if accepts_var:
                continue
            if pname not in impl_params:
                problems.append(
                    f"{impl_name}.{method_name} missing parameter '{pname}' "
                    f"required by {proto.__name__}"
                )
    assert not problems, "\n  - " + "\n  - ".join(problems)
