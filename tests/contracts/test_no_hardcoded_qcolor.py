"""Contract: no hardcoded QColor — all colors must go through ThemeManager tokens.

Dogma: `QColor("#...")` / `QColor(r,g,b)` with literal values is forbidden outside
the allow-list. Use `try_resolve_theme_color(tm, "token")` with fallback via
helper (e.g. `_token_qcolor("gallery.card.background", "#383838")`), or
`QColor(0,0,0,0)` transparent. HSV-generated `QColor.fromHsvF` is allowed.

See docs/legacy/plan_app_wide_tokenization.md §2 and AGENTS.md:85 sli-ui-toolkit-docs-first.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"

# Allowed: transparent and HSV-generated (not hard-coded palette)
ALLOW_RE = re.compile(
    r"""QColor\s*\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)"""  # transparent
    r"""|QColor\.fromHsvF\s*\("""
    r"""|QColor\.fromHsv\s*\("""
)

# Detect hardcoded QColor with literal hex or literal ints
HARDCODED_RE = re.compile(
    r"""QColor\s*\(\s*["']#[0-9A-Fa-f]{3,8}["']\s*\)"""  # QColor("#...")
    r"""|QColor\s*\(\s*\d+\s*,\s*\d+\s*,\s*\d+"""  # QColor(255,255,255) or QColor(0,150,255,153)
)

# Allow-listed files / patterns that are not theming (e.g., color picker HSV, transparent, tests, canvas)
ALLOW_PATHS = {
    "src/core/theme.py",  # QColor(v) from themes.json is allowed (variable, not literal)
    "src/shared/rendering/glass_panel.py",  # debug red QColor(255,0,0)
    "src/ui/widgets/color/picker_dialog.py",  # HSV-generated, keep allow for fromHsvF
}

ALLOW_FILE_PATTERNS = [
    re.compile(r"tests/.*"),  # tests may use QColor for assertions
    re.compile(r".*\.pyc"),
    re.compile(r"src/tabs/.*/canvas/.*"),  # canvas rendering — not UI chrome, uses overlay colors
    re.compile(r"src/tabs/.*/scene/.*"),
    re.compile(r"src/shared/rendering/.*"),
    re.compile(r"src/ui/canvas_infra/.*"),
    re.compile(r"src/tabs/image_compare/canvas/.*"),
    re.compile(r"src/tabs/multi_compare/canvas/.*"),
]

def _is_allowed_file(path: Path) -> bool:
    rel = str(path.relative_to(ROOT))
    if rel in ALLOW_PATHS:
        return True
    for pat in ALLOW_FILE_PATTERNS:
        if pat.search(rel):
            return True
    return False

def _is_allowed_line(line: str) -> bool:
    # Transparent and HSV are allowed even if they match HARDCODED_RE
    if ALLOW_RE.search(line):
        return True
    # QColor with variable (not literal) is allowed: QColor(resolve_theme_color(...)), QColor(color), QColor(v)
    # HARDCODED_RE only matches literals, so variable is already not flagged
    return False

def test_no_hardcoded_qcolor():
    offenders = []
    for p in SRC.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if _is_allowed_file(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "QColor" not in line:
                continue
            # Check each QColor occurrence in the line
            for m in HARDCODED_RE.finditer(line):
                snippet = m.group(0)
                # Skip allowed transparent/HSV in same line
                if _is_allowed_line(line):
                    # Still need to check if the specific snippet is allowed (e.g., QColor(0,0,0,0) in a line with also QColor("#..."))
                    if "0,0,0,0" in snippet or "fromHsv" in line:
                        continue
                # Also allow fallback helpers that wrap QColor with token: _token_qcolor("token", "#...") is not QColor("#...")
                # But bare QColor("#...") is forbidden
                if 'try_resolve' in line or '_token' in line or 'resolve_theme' in line:
                    # Line already uses token helper, but still has QColor("#...") as fallback arg — allow if it's inside helper call
                    # e.g., _token_qcolor("gallery.card.background", "#383838") — the second arg is fallback, not bare QColor
                    # Detect bare QColor("#...") not inside helper
                    if re.search(r"_token.*QColor\s*\(|try_resolve.*QColor", line):
                        # Check if the QColor is the fallback arg of the helper, not a standalone
                        # Allow: _token_qcolor("token", "#...") -> the QColor is not present, it's just "#..."
                        # But QColor("#...") inside helper is still hardcode, but we allow fallback arg as string
                        if "QColor(" in line and "#"+ snippet.split("#")[-1].split('"')[0] in line:
                            # If the QColor is inside _token_qcolor's fallback, it's actually not QColor("#...") but "#..." string
                            # So we should not flag QColor("#...") that is inside helper's fallback — but our regex is QColor("#..."), not "#..."
                            pass
                offenders.append(f"{p.relative_to(ROOT)}:{lineno}: {line.strip()}  // {snippet}")

    # Filter to only bare QColor("#...") and QColor(int,int,int) not in allow
    # Remove false positives where QColor is fromHsvF or transparent
    filtered = [o for o in offenders if not _is_allowed_line(o)]

    # Dogma: no new hardcoded QColor in UI chrome — canvas/rendering excluded via ALLOW_FILE_PATTERNS.
    # Current debt baseline is 91 (down from 386). Phase 0 of plan_app_wide_tokenization.md allows this baseline,
    # but any increase fails. Next phases will ratchet 91 → 50 → 20 → 0.
    baseline = 91
    assert len(filtered) <= baseline, (
        f"Hardcoded QColor increased: {len(filtered)} > baseline {baseline} — use ThemeManager tokens via try_resolve_theme_color / _token_qcolor:\n"
        + "\n".join(filtered[:20])
        + (f"\n... and {len(filtered)-20} more" if len(filtered) > 20 else "")
        + f"\nTotal: {len(filtered)} in src (allow transparent QColor(0,0,0,0) and fromHsvF only, baseline {baseline})"
    )
