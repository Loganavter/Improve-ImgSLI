#!/usr/bin/env python3
"""Stdio entry point for the Improve-ImgSLI app MCP server.

Runs as a local MCP server: the client launches it as a subprocess and speaks
newline-delimited JSON-RPC 2.0 over stdin/stdout (logs go to stderr). It has
**no third-party dependencies** — the transport is ``app/protocol.py`` — and
drives the app through a headless snapshot / launcher subprocess, so it can be
started with any Python 3.11+ (the app's own venv is used automatically when it
exists).

    python3 mcp-server/app/server.py            # serve on stdio
    python3 mcp-server/app/server.py --check    # print the catalog + version
    python3 mcp-server/app/server.py --repo-root /path/to/Improve-ImgSLI

Wiring (opencode.jsonc)::

    "mcpServers": {
      "app": {
        "type": "local",
        "command": "python3",
        "args": ["<repo>/mcp-server/app/server.py"],
        "environment": {"IMGSLI_REPO_ROOT": "<repo>"}
      }
    }

Environment: ``IMGSLI_REPO_ROOT`` (repo root), ``IMGSLI_MCP_ARTIFACTS``
(scratch dir for dumps/captures), ``IMGSLI_MCP_TIMEOUT`` (headless boot budget,
seconds). See ``README.md`` and ``docs/dev/MCP.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Absolute-script execution gives us no package context: put ``mcp-server/`` on
# sys.path so ``app`` imports as a package regardless of how we were invoked.
_HERE = Path(__file__).resolve()
_PACKAGE_PARENT = _HERE.parents[1]
if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

from app import catalog  # noqa: E402
from app.backend import DEFAULT_TIMEOUT_S, AppBackend  # noqa: E402
from app.protocol import MCPProtocol, serve_stdio  # noqa: E402

#: Repo root as ``<repo>/mcp-server/app/server.py`` → ``<repo>``.
_DEFAULT_REPO_ROOT = _HERE.parents[2]


def _env_timeout() -> float:
    try:
        return float(os.environ.get("IMGSLI_MCP_TIMEOUT", DEFAULT_TIMEOUT_S))
    except ValueError:
        return DEFAULT_TIMEOUT_S


def build_protocol(repo_root: Path | str | None = None) -> MCPProtocol:
    """Wire a backend to the catalog and return the protocol dispatcher.

    Exposed for tests and ``--check`` so the whole surface can be exercised
    without a transport (and with injected backends).
    """
    root = Path(repo_root or os.environ.get("IMGSLI_REPO_ROOT") or _DEFAULT_REPO_ROOT)
    backend = AppBackend(root, timeout_s=_env_timeout())
    return MCPProtocol(backend)


def _catalog_summary() -> dict:
    return {
        "server": catalog.SERVER_NAME,
        "serverVersion": catalog.SERVER_VERSION,
        "protocolVersion": catalog.PROTOCOL_VERSION,
        "supportedProtocolVersions": list(catalog.SUPPORTED_PROTOCOL_VERSIONS),
        "tools": [tool["name"] for tool in catalog.TOOLS],
        "toolCount": len(catalog.TOOLS),
        "resources": [item["uri"] for item in catalog.RESOURCES],
        "resourceTemplates": [item["uriTemplate"] for item in catalog.RESOURCE_TEMPLATES],
        "prompts": [prompt["name"] for prompt in catalog.PROMPTS],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="imgsli-mcp-app", description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Improve-ImgSLI checkout root (default: derived, or IMGSLI_REPO_ROOT).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print the declared catalog as JSON and exit (no stdio loop).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        print(json.dumps(_catalog_summary(), ensure_ascii=False, indent=2))
        return 0
    protocol = build_protocol(args.repo_root)
    print(
        f"[mcp-app] serving stdio — protocol {catalog.PROTOCOL_VERSION}, "
        f"{len(catalog.TOOLS)} tools",
        file=sys.stderr,
        flush=True,
    )
    return serve_stdio(protocol)


if __name__ == "__main__":
    raise SystemExit(main())
