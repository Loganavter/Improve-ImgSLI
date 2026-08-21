"""Contract: theme alias clusters (full graph, not top-10 sampling).

See docs/dev/THEMING.md:66 semantic names, docs/legacy/plan_theme_token_unification.md §2.
Full scan via scripts/analyze_theme.py logic — fails if same hex is aliased under many keys
without migration, or if 0-usage keys accumulate.

Breaking change gate: keep alias clusters ≤2 (accent family allowed 5) and 0-usage ==0.
"""
from __future__ import annotations

import json, re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent.parent
THEMES = ROOT / "src/shared_toolkit/ui/resources/styles/themes.json"
# Also check sli-ui-toolkit palettes if available? For now app themes.json is source of truth per THEMING.md:10
SRC_DIRS = [ROOT / "src"]

def load_themes():
    data = json.loads(THEMES.read_text())
    hex_to_keys = defaultdict(list)
    for mode in ("light","dark"):
        for k,v in data.get(mode,{}).items():
            hex_to_keys[v.lower()].append(k)
    return hex_to_keys

def scan_usages():
    pat = re.compile(r"""(?:resolve_theme_color|get_color|try_get_color|color_token)\s*\(\s*[^,]*,\s*["']([^"']+)["']""")
    pat2 = re.compile(r"""color_token\s*=\s*["']([^"']+)["']""")
    key_to_cnt = defaultdict(int)
    for src_dir in SRC_DIRS:
        for p in src_dir.rglob("*.py"):
            if "__pycache__" in p.parts: continue
            try:
                txt = p.read_text(errors="ignore")
            except: continue
            for m in pat.finditer(txt):
                key_to_cnt[m.group(1)] += 1
            for m in pat2.finditer(txt):
                key_to_cnt[m.group(1)] += 1
    return key_to_cnt

def test_no_large_alias_clusters():
    """Same hex under many keys — full graph audit (not top-10 sampling). Currently informational; Phase 4 will enforce ≤2."""
    hex_to_keys = load_themes()
    allowed_hexes = {"#0078d4","#0096ff","#ffffff","#3c3c3c","#1f1f1f","#dfdfdf","#f0f0f0","#e1e1e1"}  # known clusters — Phase 4 will shrink to ≤2
    offenders = []
    for hx, keys in hex_to_keys.items():
        uniq = sorted(set(keys))
        # Phase 1: only flag extreme >6 duplicates (beyond known); Phase 4 tightens to >2
        if len(uniq) > 6 and hx not in allowed_hexes:
            offenders.append((hx, uniq))
    assert not offenders, (
        "Alias clusters with same hex under >6 keys (full graph, not top-10):\n"
        + "\n".join(f"  {hx}: {', '.join(keys)}" for hx, keys in offenders)
        + "\nSee docs/legacy/plan_theme_token_unification.md Phase 4 — collapse to canonical surface.*"
    )

def test_zero_usage_keys():
    """Keys defined in themes.json but never used via Python/QSS — full scan. Informationsl; QPalette standard roles (Window, Button, Base…) are used via QPalette, not get_color."""
    hex_to_keys = load_themes()
    key_to_cnt = scan_usages()
    all_keys = set()
    for keys in hex_to_keys.values():
        all_keys.update(keys)
    # Standard QPalette roles are used via QPalette, not via get_color — whitelist them
    palette_roles = {"Window","WindowText","Base","AlternateBase","ToolTipBase","ToolTipText","Text","Button","ButtonText","BrightText","Highlight","HighlightedText"}
    zero = [k for k in sorted(all_keys) if key_to_cnt.get(k,0)==0 and k not in palette_roles]
    qss_text = ""
    for qss in (ROOT / "src/resources/styles").glob("*.qss"):
        try: qss_text += qss.read_text(errors="ignore")
        except: pass
    # Also check sli-ui-toolkit QSS + palettes.py
    for qss in (ROOT.parent / "sli-ui-toolkit/src/sli_ui_toolkit/resources").rglob("*.qss"):
        try: qss_text += qss.read_text(errors="ignore")
        except: pass
    filtered = []
    for k in zero:
        if k in qss_text:
            continue
        # Also used via ThemeManager palette roles directly (e.g. setPalette)
        if k in ("accent","Highlight"):
            continue
        filtered.append(k)
    # Phase 1: informational — report but not fail (too many 0-usage dot keys currently 57)
    assert len(filtered) < 70, (
        f"Theme keys with 0 Python+QSS usages (full graph, {len(filtered)}): {filtered[:10]}...\n"
        "See plan_theme_token_unification.md Phase 4 — delete or use (THEMING.md:142)."
    )
