"""Redaction rules for the diagnostics report (privacy-first, fail-closed)."""

from __future__ import annotations

from plugins.diagnostics import redact
from plugins.diagnostics.redact import redact_text, redact_value


def test_home_directory_becomes_tilde() -> None:
    fake_home = "/home/tester"
    text = f"loaded {fake_home}/projects/pic.png"
    out = redact_text(text, home=fake_home, user="tester")
    assert fake_home not in out
    assert "~/projects/pic.png" in out


def test_username_token_is_masked() -> None:
    out = redact_text("user tester logged in", home="/home/tester", user="tester")
    assert "tester" not in out
    assert redact.USER_MASK in out


def test_sk_token_is_masked() -> None:
    out = redact_text("key sk-abc123XYZ_456789")
    assert "sk-abc123XYZ_456789" not in out
    assert redact.MASK in out


def test_api_key_value_is_masked() -> None:
    for text in (
        "api_key=supersecret123",
        'api_key: "supersecret123"',
        "token = supersecret123",
        "password: supersecret123",
    ):
        out = redact_text(text)
        assert "supersecret123" not in out, text
        assert redact.MASK in out, text


def test_bearer_token_is_masked() -> None:
    out = redact_text("Authorization: Bearer abcdef123456")
    assert "abcdef123456" not in out
    assert redact.MASK in out


def test_absolute_path_is_hashed_not_raw() -> None:
    out = redact_text('File "/opt/secretdir/thing.py", line 3')
    assert "/opt/secretdir" not in out
    assert "<path:" in out
    # basename survives for readability
    assert "thing.py" in out


def test_tilde_relative_path_is_not_rehashed() -> None:
    out = redact_text("at ~/projects/pic.png", home="/home/tester", user="tester")
    assert "~/projects/pic.png" in out
    assert "<path:" not in out


def test_urls_are_not_mangled() -> None:
    out = redact_text("see https://example.com/a/b for details")
    assert "https://example.com/a/b" in out


def test_no_raw_token_or_absolute_path_survives_combined() -> None:
    fake_home = "/home/tester"
    text = (
        f"cfg={fake_home}/app/cfg.json api_key: sk-live-ABCdef123456 "
        "path=/var/log/secret.log"
    )
    out = redact_text(text, home=fake_home, user="tester")
    assert fake_home not in out
    assert "sk-live-ABCdef123456" not in out
    assert "/var/log" not in out


def test_redact_value_recurses_into_structures() -> None:
    out = redact_value(
        {
            "message": "sk-abc123456",
            "nested": ["/etc/secret/thing", "plain"],
            "ok": 3,
        }
    )
    assert "sk-abc123456" not in out["message"]
    assert "/etc/secret" not in out["nested"][0]
    assert out["ok"] == 3


def test_redact_text_fail_closed_on_error(monkeypatch) -> None:
    # A broken inner redactor must never leak the raw text.
    def _boom(*args, **kwargs):
        raise RuntimeError("redactor exploded")

    monkeypatch.setattr(redact, "_redact_str", _boom)
    out = redact_text("sk-raw-secret-value")
    assert "sk-raw-secret-value" not in out
    assert out == redact.REDACTION_FAILED
