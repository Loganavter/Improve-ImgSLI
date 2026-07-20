#!/usr/bin/env python3
"""Generate llms.txt from the in-app help tree, resolving {{tr:...}} tokens
from the application i18n JSON files and stripping {{img:...}} figure blocks."""
import json
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# I18n helpers
# ---------------------------------------------------------------------------

def _flatten(obj: dict, prefix: str = "") -> dict[str, str]:
    """Recursively flatten nested JSON into dot-separated keys."""
    result = {}
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, key))
        elif isinstance(v, str):
            result[key] = v
    return result


def load_translations(repo_root: Path, lang: str = "en") -> dict[str, str]:
    """Load all JSON files under src/resources/i18n/<lang>/ and also
    merge per-tab i18n files found under src/tabs/*/resources/i18n/<lang>/."""
    translations: dict[str, str] = {}
    base = repo_root / "src" / "resources" / "i18n" / lang
    if base.exists():
        for path in sorted(base.rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                translations.update(_flatten(data))
            except Exception:
                pass
    # Also pick up per-tab translations
    for tab_i18n in sorted(
        (repo_root / "src" / "tabs").glob(f"*/resources/i18n/{lang}/*.json")
    ):
        try:
            data = json.loads(tab_i18n.read_text(encoding="utf-8"))
            translations.update(_flatten(data))
        except Exception:
            pass
    return translations


# ---------------------------------------------------------------------------
# Token substitution
# ---------------------------------------------------------------------------

_TR_RE = re.compile(r"\{\{tr:([^}]+)\}\}")
_IMG_FIGURE_RE = re.compile(
    r":::figure\{[^}]*\}.*?:::",
    re.DOTALL,
)
_IMG_TOKEN_RE = re.compile(r"\{\{img:[^}]+\}\}")
_ANCHOR_RE = re.compile(r"\s*\{#[^}]+\}")   # trailing {#anchor}


def resolve_tokens(text: str, translations: dict[str, str]) -> str:
    """Replace {{tr:key}} with the translated string (or the key itself as
    fallback), strip {{img:...}} figure blocks and bare image tokens."""
    # Remove whole :::figure{...} ... ::: blocks (they contain images)
    text = _IMG_FIGURE_RE.sub("", text)
    # Strip remaining {{img:...}} inline tokens
    text = _IMG_TOKEN_RE.sub("", text)
    # Remove heading anchors {#anchor}
    text = _ANCHOR_RE.sub("", text)

    def replace_tr(m: re.Match) -> str:
        key = m.group(1).strip()
        return translations.get(key, key)  # fall back to the bare key

    text = _TR_RE.sub(replace_tr, text)
    return text


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_llms_txt(repo_root: Path, lang: str = "en") -> str:
    help_dir = repo_root / "src" / "resources" / "help"
    tree_path = help_dir / "tree.json"
    lang_dir = help_dir / lang

    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    nodes = tree.get("nodes", {})
    translations = load_translations(repo_root, lang)

    output: list[str] = []
    output.append("# Improve-ImgSLI Documentation\n")
    output.append(
        "> Improve-ImgSLI is a declarative, highly-optimized image comparison "
        "tool for developers, QA, and content creators. It features a "
        "responsive UI, advanced canvas rendering, and extensive diffing tools.\n\n"
    )

    def visit_node(node_id: str, depth: int = 1) -> None:
        node = nodes.get(node_id)
        if not node:
            return

        if node["kind"] == "hub":
            if node_id != "root":
                title = resolve_tokens(node["title"], translations)
                output.append(f"{'#' * depth} {title}\n")
                if "description" in node:
                    desc = resolve_tokens(node["description"], translations)
                    output.append(f"{desc}\n\n")
            for child_id in node.get("children", []):
                visit_node(child_id, depth + 1 if node_id != "root" else depth)

        elif node["kind"] == "page":
            title = resolve_tokens(node["title"], translations)
            output.append(f"{'#' * depth} {title}\n")
            if "description" in node:
                desc = resolve_tokens(node["description"], translations)
                output.append(f"*{desc}*\n\n")

            body_rel_path = node.get("body")
            if body_rel_path:
                body_path = lang_dir / body_rel_path
                if body_path.exists():
                    raw = body_path.read_text(encoding="utf-8")
                    content = resolve_tokens(raw, translations)
                    for line in content.split("\n"):
                        if line.startswith("#"):
                            output.append("#" * depth + line)
                        else:
                            output.append(line)
                    output.append("\n\n")
                else:
                    output.append(f"*(Content missing: {body_rel_path})*\n\n")

    visit_node("root", 2)
    return "\n".join(output)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    content = build_llms_txt(repo_root)

    out_path = repo_root / "llms.txt"
    out_path.write_text(content, encoding="utf-8")

    print(f"Generated {out_path}")
    print(f"Size: {len(content)} characters")

    # Quick sanity: report any unresolved {{tr:...}} that remain
    remaining = re.findall(r"\{\{tr:[^}]+\}\}", content)
    if remaining:
        uniq = sorted(set(remaining))
        print(f"\nWARNING: {len(uniq)} unresolved tr-token(s):")
        for t in uniq[:20]:
            print(f"  {t}")
        if len(uniq) > 20:
            print(f"  ...and {len(uniq) - 20} more")
    else:
        print("All {{tr:...}} tokens resolved successfully.")
