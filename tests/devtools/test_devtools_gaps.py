"""Devtools gaps (G3): trace wiring, anchor validation, i18n fan-out,
geometry documentation, non-vacuous nav check, cloc error paths.

Covers ``task-fix-devtools-gaps-2026-09-20``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- analyze_ic_gap: --trace wired ------------------------------------------------


def test_parse_trace_collects_gap_spans(tmp_path: Path):
    from devtools.analyze_ic_gap import parse_trace

    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "\n".join(
            [
                json.dumps({"ts": "t1", "kind": "render", "message": "gap_detected covered1=0.5"}),
                json.dumps({"ts": "t2", "kind": "render", "message": "frame done"}),
                "not-json but mentions Gap bbox",
            ]
        ),
        encoding="utf-8",
    )
    events = parse_trace(trace)
    assert len(events) == 2
    assert all(e["kind"] == "trace_gap" for e in events)
    assert events[0]["ts"] == "t1"


def test_parse_trace_missing_file_is_fail_open(tmp_path: Path, capsys):
    from devtools.analyze_ic_gap import parse_trace

    assert parse_trace(tmp_path / "nope.jsonl") == []
    assert "trace not found" in capsys.readouterr().err
    assert parse_trace(None) == []


def test_analyze_main_wires_trace_flag(tmp_path: Path, capsys):
    from devtools.analyze_ic_gap import main

    log = tmp_path / "log.txt"
    log.write_text("[ic-gap] pick->gap gap_id=7\n", encoding="utf-8")
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps({"message": "gap resolve_lod shared_level=2"}) + "\n", encoding="utf-8")
    main(["--log", str(log), "--trace", str(trace)])
    out = capsys.readouterr().out
    assert "trace_gap spans: 1" in out


# --- docs_link_graph: anchor validation -------------------------------------------


def _anchor_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "docs" / "dev" / "a.md", "# Alpha One\n\nJump to [B](b.md#beta-two) and [top](#alpha-one).\n")
    _write(
        repo / "docs" / "dev" / "b.md",
        "# Beta Two\n\nBack to [A](a.md#alpha-one) and [gone](a.md#no-such-heading).\n",
    )
    _write(repo / "docs" / "dev" / "c.md", "# C\n\nSelf [missing](#nope).\n")
    return repo


def test_anchor_validation_ok_and_broken(tmp_path: Path):
    from devtools.docs_link_graph import analyze_docs

    report = analyze_docs(repo_root=_anchor_repo(tmp_path))
    assert not report.broken
    broken = {(b.source, b.target) for b in report.broken_anchors}
    assert ("docs/dev/b.md", "a.md#no-such-heading") in broken
    assert ("docs/dev/c.md", "#nope") in broken
    # Valid cross-file and same-file anchors are quiet.
    assert not any(b.target == "a.md#alpha-one" for b in report.broken_anchors)
    assert not any(b.target == "b.md#beta-two" for b in report.broken_anchors)
    assert not any(b.target == "#alpha-one" for b in report.broken_anchors)


def test_heading_slug_rules(tmp_path: Path):
    from devtools.docs_link_graph import _heading_slugs

    slugs = _heading_slugs("# Foo Bar!\n\n### `Code` Name\n\n```\n# not a heading\n```\n")
    assert "foo-bar" in slugs
    assert "code-name" in slugs


def test_strict_fails_on_anchors_only(tmp_path: Path):
    from devtools.docs_link_graph import main

    repo = tmp_path / "repo"
    _write(repo / "docs" / "dev" / "a.md", "# A\n\nBad [jump](#missing).\n")
    assert main(["--repo-root", str(repo), "--strict"]) == 1
    assert main(["--repo-root", str(repo)]) == 0


# --- check_translations: multi-root fan-out ----------------------------------------


def _i18n_tree(base: Path) -> None:
    _write(base / "src" / "resources" / "i18n" / "en" / "host.json", '{"ok": "OK"}')
    _write(base / "src" / "resources" / "i18n" / "ru" / "host.json", '{"ok": ""}')
    _write(base / "src" / "tabs" / "demo" / "resources" / "i18n" / "en" / "t.json", '{"k": "v"}')
    _write(base / "src" / "tabs" / "demo" / "resources" / "i18n" / "ru" / "t.json", '{}')
    _write(base / "src" / "plugins" / "p" / "resources" / "i18n" / "en" / "p.json", '{"k": "v"}')
    _write(base / "src" / "plugins" / "p" / "resources" / "i18n" / "ru" / "p.json", '{"k": "v"}')


def test_discover_i18n_roots_fans_out(tmp_path: Path):
    from devtools.check_translations import discover_i18n_roots

    _i18n_tree(tmp_path)
    roots = discover_i18n_roots(tmp_path / "src")
    # Host root first, then path order.
    assert roots[0] == tmp_path / "src" / "resources" / "i18n"
    rels = sorted(p.relative_to(tmp_path).as_posix() for p in roots)
    assert rels == [
        "src/plugins/p/resources/i18n",
        "src/resources/i18n",
        "src/tabs/demo/resources/i18n",
    ]


def test_check_translations_multi_root_strict(tmp_path: Path, capsys):
    from devtools.check_translations import main

    _i18n_tree(tmp_path)
    tab_root = tmp_path / "src" / "tabs" / "demo" / "resources" / "i18n"
    code = main(["--root", str(tab_root), "--strict"])
    assert code == 1
    out = capsys.readouterr().out
    assert "missing keys" in out

    plugin_root = tmp_path / "src" / "plugins" / "p" / "resources" / "i18n"
    capsys.readouterr()
    assert main(["--root", str(plugin_root), "--strict"]) == 0


def test_check_translations_json_multi_root_shape(tmp_path: Path, capsys):
    from devtools.check_translations import main

    _i18n_tree(tmp_path)
    tab_root = tmp_path / "src" / "tabs" / "demo" / "resources" / "i18n"
    plugin_root = tmp_path / "src" / "plugins" / "p" / "resources" / "i18n"
    assert main(["--root", str(tab_root), "--root", str(plugin_root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {str(tab_root), str(plugin_root)}


# --- ui_layout_dump: parent-local geometry documented -------------------------------


def test_dump_declares_parent_local_geometry(qapp):
    from PySide6.QtWidgets import QWidget

    from devtools.ui_layout_dump import GEOMETRY_SPACE, dump_all_windows, dump_ui_layout

    assert GEOMETRY_SPACE == "parent-local"
    host = QWidget()
    try:
        tree = dump_ui_layout(host, SimpleNamespace(all_actions=lambda: []))
    finally:
        host.close()
        host.deleteLater()
    assert tree["geometry_space"] == "parent-local"
    assert json.dumps(tree)

    out = dump_all_windows(SimpleNamespace(all_actions=lambda: []))
    assert out["geometry_space"] == "parent-local"


# --- nav_graph: non-vacuous --check --------------------------------------------------


def test_evaluate_check_refuses_vacuous_ok():
    from devtools.nav_graph import evaluate_check

    empty = SimpleNamespace(nodes=[])
    code, message = evaluate_check(empty, lambda _g: [])
    assert code == 2
    assert "vacuous" in message


def test_evaluate_check_violations_and_clean():
    from devtools.nav_graph import evaluate_check

    graph = SimpleNamespace(nodes=[SimpleNamespace(owner="o", section="s")])
    assert evaluate_check(graph, lambda _g: ["dup"])[0] == 1
    code, message = evaluate_check(graph, lambda _g: [])
    assert code == 0
    assert "OK" in message


# --- context_cloc: bad dir error + LANG exclusion documented --------------------------


def test_cloc_errors_on_explicit_bad_toolkit_dir(capsys):
    from devtools.context_cloc import main

    code = main(["--cloc-only", "--toolkit-dir", "/nonexistent-toolkit-xyz"])
    assert code == 2
    assert "toolkit dir not found" in capsys.readouterr().err


def test_cloc_help_documents_lang_exclusion():
    from devtools.context_cloc import LANG_EXCLUSION_DOC, build_parser

    help_text = build_parser().format_help()
    assert "pt_BR" in help_text
    assert "Localized docs exclusion" in help_text
    assert "context bundles collect English docs only" in help_text
    assert LANG_EXCLUSION_DOC.startswith("Localized docs exclusion")
