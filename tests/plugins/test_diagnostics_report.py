"""Report assembly: schema has no image field; builder does no file I/O."""

from __future__ import annotations

import ast
import builtins
import json
from pathlib import Path

from plugins.diagnostics import report
from plugins.diagnostics.report import (
    FORBIDDEN_FIELDS,
    DiagnosticsReport,
    assemble,
    build_issue_url,
    build_payload,
    format_failure,
    render_text,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "plugins" / "diagnostics"


def _all_keys(node) -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(str(key))
            keys |= _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= _all_keys(item)
    return keys


def _sample_report() -> DiagnosticsReport:
    failure = format_failure(ValueError, ValueError("boom"), None, source="main")
    return assemble(
        failure=failure,
        app={"version": "11.0.0", "install_source": "source"},
        environment={"os": "Linux", "session_type": "wayland"},
        machine={"kernel": "6.8.0", "gpu": [{"name": "Test GPU"}]},
        runtime={"active_tab": "image_compare", "python": {"python_version": "3.12"}},
        breadcrumbs=[{"timestamp": 1.0, "kind": "action", "label": "SET_SPLIT_POSITION"}],
        logs=["2026-01-01 - [INFO] - line"],
    )


def test_schema_has_no_image_or_pixmap_field() -> None:
    payload = _sample_report().payload
    keys = {key.lower() for key in _all_keys(payload)}
    assert keys.isdisjoint(FORBIDDEN_FIELDS), keys & FORBIDDEN_FIELDS
    # and, defensively, none of the forbidden names appear as payload keys
    assert "image" not in keys
    assert "pixmap" not in keys
    assert "screenshot" not in keys


def test_build_payload_drops_forbidden_keys_defensively() -> None:
    payload = build_payload(
        runtime={"active_tab": "x"},
        app={"version": "1", "image": "data:image/png;base64,AAAA"},
    )
    assert "image" not in payload["app"]
    # integer-ish payload stays JSON-serialisable
    json.dumps(payload)


def test_report_text_contains_all_sections() -> None:
    text = _sample_report().text
    for section in ("## Failure", "## Build", "## Environment", "## Runtime", "## Log tail"):
        assert section in text, section
    assert "ValueError: boom" in text


def test_report_builder_never_reads_file_contents(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError(f"report builder attempted file I/O: {args!r}")

    monkeypatch.setattr(builtins, "open", _boom)
    monkeypatch.setattr(Path, "read_text", _boom)
    monkeypatch.setattr(Path, "read_bytes", _boom)

    # Must not attempt any file read.
    payload = build_payload(failure={"type": "X", "message": "y"}, app={"version": "1"})
    text = render_text(payload)
    assert "X: y" in text or "X" in text


def test_report_modules_contain_no_file_io_calls() -> None:
    forbidden = {"open", "read_text", "read_bytes", "readlines"}
    offenders: list[str] = []
    for name in ("report.py", "redact.py"):
        tree = ast.parse((_SRC / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                call_name = getattr(func, "id", None) or getattr(func, "attr", None)
                if call_name in forbidden:
                    offenders.append(f"{name}:{node.lineno} {call_name}")
    assert offenders == [], offenders


def test_issue_url_is_prefilled_and_capped() -> None:
    text = "x" * 20000
    url = build_issue_url(text, title="boom", max_body=1000)
    assert url.startswith("https://github.com/Loganavter/Improve-ImgSLI/issues/new?")
    assert "title=boom" in url
    assert len(url) < 8000


def test_redaction_failure_drops_field(monkeypatch) -> None:
    from plugins.diagnostics import redact

    def _boom(*args, **kwargs):
        raise RuntimeError("redactor exploded")

    monkeypatch.setattr(redact, "redact_text", _boom)
    payload = build_payload(app={"version": "1", "leaky": "SECRET-RAW"})
    # Fail-closed: the unredactable field is dropped, never emitted raw.
    assert "leaky" not in payload["app"]
    assert "SECRET-RAW" not in json.dumps(payload)
