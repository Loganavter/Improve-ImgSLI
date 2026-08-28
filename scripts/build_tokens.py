#!/usr/bin/env python3
"""Build themes.json from primitive + semantic + component tokens.

Deterministic, no network, no randomness:
  primitive.json  (required) — base palette + metrics (~30 tokens, e.g. blue500 #0096FF, gray800 #383838, space, radius)
  semantic.json   (optional) — semantic aliases (accent → {color.blue500})
  component.json  (optional) — component tokens (card.background → {color.gray800})

Output:
  src/resources/themes.json (sorted keys, indent 2, LF, trailing newline)
  src/shared_toolkit/ui/resources/styles/themes.json if that dir exists

Reference syntax: "{color.blue500}" or "{blue500}" → resolved via primitive flat map.
Supported semantic/component shapes:
  {"light": {token: value}, "dark": {token: value}}
  {"token": {"light": value, "dark": value}}
  {"token": value}  (same for both themes)

If semantic+component are absent, existing themes.json is re-emitted deterministically
(sorted) so `python scripts/build_tokens.py` is idempotent from day one.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS_DIR = ROOT / "src/resources/tokens"
PRIMITIVE_PATH = TOKENS_DIR / "primitive.json"
SEMANTIC_PATH = TOKENS_DIR / "semantic.json"
COMPONENT_PATH = TOKENS_DIR / "component.json"
THEMES_PATH = ROOT / "src/resources/themes.json"
VENDORED_PATH = ROOT / "src/shared_toolkit/ui/resources/styles/themes.json"

_REF_RE = re.compile(r"\{([^}]+)\}")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_primitive(data: dict, prefix: str = "") -> dict[str, str]:
    """Flatten nested primitive.json → flat map like 'color.blue500' → '#0096FF'."""
    flat: dict[str, str] = {}
    for k, v in data.items():
        if k.startswith("$"):
            continue
        key = f"{prefix}{k}" if not prefix else f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(flatten_primitive(v, prefix=f"{key}."))
        else:
            flat[key] = str(v).strip()
    return flat


def normalize_tokens(data: dict) -> dict[str, dict[str, str]]:
    """Normalize semantic/component file → {'light': {k:v}, 'dark': {k:v}}."""
    out: dict[str, dict[str, str]] = {"light": {}, "dark": {}}
    if not isinstance(data, dict) or not data:
        return out
    # shape 1: {"light": {...}, "dark": {...}}
    if "light" in data or "dark" in data:
        for mode in ("light", "dark"):
            block = data.get(mode)
            if isinstance(block, dict):
                for k, v in block.items():
                    if k.startswith("$"):
                        continue
                    out[mode][k] = v
        return out
    # shape 2/3: {"token": value} or {"token": {"light":..., "dark":...}}
    for token, val in data.items():
        if token.startswith("$"):
            continue
        if isinstance(val, dict) and ("light" in val or "dark" in val):
            for mode in ("light", "dark"):
                if mode in val:
                    out[mode][token] = val[mode]  # type: ignore[typeddict-item]
        else:
            out["light"][token] = val  # type: ignore[assignment]
            out["dark"][token] = val  # type: ignore[assignment]
    return out


def resolve_value(value: object, primitives: dict[str, str]) -> object:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if "{" not in s:
        return s

    def repl(m: re.Match[str]) -> str:
        ref = m.group(1).strip()
        # direct hit
        if ref in primitives:
            return primitives[ref]
        # try color.<ref>
        cand = f"color.{ref}"
        if cand in primitives:
            return primitives[cand]
        # try without color prefix if ref already has it
        # fallback: keep original placeholder (will be visible diff)
        return m.group(0)

    return _REF_RE.sub(repl, s)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv

    if not PRIMITIVE_PATH.exists():
        print(f"missing {PRIMITIVE_PATH} — create src/resources/tokens/primitive.json first", file=sys.stderr)
        return 2

    primitive_raw = load_json(PRIMITIVE_PATH)
    primitives = flatten_primitive(primitive_raw)
    # quick sanity: expect ~30 entries; warn if far off but don't fail
    if not (20 <= len(primitives) <= 50):
        print(f"warning: primitive.json has {len(primitives)} flat tokens (expected ~30)", file=sys.stderr)

    # base themes: existing file if present, else empty
    base = load_json(THEMES_PATH)
    if not base or "light" not in base or "dark" not in base:
        base = {"light": {}, "dark": {}}
        # seed empty so generation from tokens alone works

    # overlay semantic + component (component wins)
    for path in (SEMANTIC_PATH, COMPONENT_PATH):
        data = load_json(path)
        if not data:
            continue
        norm = normalize_tokens(data)
        for mode in ("light", "dark"):
            for k, v in norm[mode].items():
                base[mode][k] = resolve_value(v, primitives)

    # resolve any remaining placeholders that may already be in base (e.g. checked-in themes.json with {color.*})
    for mode in ("light", "dark"):
        for k, v in list(base[mode].items()):
            base[mode][k] = resolve_value(v, primitives)  # type: ignore[assignment]

    # deterministic emit: sorted keys, indent 2, LF
    output = {
        "light": dict(sorted(base["light"].items())),
        "dark": dict(sorted(base["dark"].items())),
    }
    new_text = json.dumps(output, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    # json.dumps with sorted base already sorted; keep sort_keys=False to preserve that order explicitly
    # but base was sorted above, so output is deterministic

    if check:
        if THEMES_PATH.exists():
            old = THEMES_PATH.read_text(encoding="utf-8")
            if old != new_text:
                print("themes.json would change (run without --check to update)", file=sys.stderr)
                return 1
        else:
            print("themes.json missing — would be created", file=sys.stderr)
            return 1
        print("themes.json up to date")
        return 0

    THEMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    THEMES_PATH.write_text(new_text, encoding="utf-8")
    print(f"wrote {THEMES_PATH} ({len(output['light'])} light, {len(output['dark'])} dark)")

    if VENDORED_PATH.parent.exists():
        VENDORED_PATH.parent.mkdir(parents=True, exist_ok=True)
        VENDORED_PATH.write_text(new_text, encoding="utf-8")
        print(f"wrote {VENDORED_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
