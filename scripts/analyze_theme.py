#!/usr/bin/env python3
"""Скрипт ревизии палитры: соотносит цвета ↔ ключи ↔ использование.

Собирает графы:
  1) hex → [ключи] (алиасы — один цвет под разными именами)
  2) ключ → [файлы:строки] где используется (resolve_theme_color / get_color / color_token)
  3) hex → использование (транзитивно через ключи)

Вывод: JSON + DOT для визуализации, и краткий отчёт о кластерах где #ffffff используется под разными ключами.
"""
import json, re, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
THEMES = ROOT / "src/shared_toolkit/ui/resources/styles/themes.json"
PALETTES = ROOT.parent / "sli-ui-toolkit/src/sli_ui_toolkit/palettes.py"  # fallback
SRC_DIRS = [ROOT / "src", ROOT.parent / "sli-ui-toolkit/src/sli_ui_toolkit"]

def load_themes():
    data = json.loads(THEMES.read_text())
    # light + dark
    hex_to_keys = defaultdict(list)
    key_to_hex = {}
    for mode in ("light","dark"):
        for k,v in data.get(mode,{}).items():
            hex_to_keys[v.lower()].append(f"{mode}:{k}")
            key_to_hex[k] = v  # last wins, but mostly same
    return data, hex_to_keys, key_to_hex

def scan_usages():
    # Ищем ключи как строковые литералы в вызовах тем
    pat = re.compile(r"""(?:resolve_theme_color|get_color|try_get_color|color_token)\s*\(\s*[^,]*,\s*["']([^"']+)["']""")
    # также color_token="..."
    pat2 = re.compile(r"""color_token\s*=\s*["']([^"']+)["']""")
    key_to_files = defaultdict(list)
    for src_dir in SRC_DIRS:
        if not src_dir.exists(): continue
        for p in src_dir.rglob("*.py"):
            try:
                txt = p.read_text(errors="ignore")
            except: continue
            for m in pat.finditer(txt):
                k = m.group(1)
                # line number
                line = txt[:m.start()].count("\n")+1
                key_to_files[k].append(f"{p.relative_to(ROOT.parent)}:{line}")
            for m in pat2.finditer(txt):
                k = m.group(1)
                line = txt[:m.start()].count("\n")+1
                key_to_files[k].append(f"{p.relative_to(ROOT.parent)}:{line}")
    return key_to_files

def main():
    data, hex_to_keys, key_to_hex = load_themes()
    key_to_files = scan_usages()

    # Граф: цвет → ключи → файлы
    color_graph = {}
    for hx, keys in hex_to_keys.items():
        # только light для краткости, но показываем оба
        uniq = {}
        for k in keys:
            base = k.split(":",1)[1]
            uniq[base] = hx
        # если один hex под разными ключами → алиас-кластер
        if len(uniq) > 1:
            color_graph[hx] = sorted(uniq.keys())

    print("=== Алиас-кластеры (один hex → несколько ключей) ===")
    for hx, keys in sorted(color_graph.items(), key=lambda x: -len(x[1])):
        if len(keys) > 1:
            print(f"{hx:9} → {', '.join(keys)}")

    print("\n=== Топ ключей по использованию ===")
    for k, files in sorted(key_to_files.items(), key=lambda x: -len(x[1]))[:30]:
        hx = key_to_hex.get(k, "?")
        print(f"{k:35} {hx:9} used {len(files)}×  e.g. {files[0] if files else ''}")

    # Поиск #ffffff кластера
    print("\n=== Кластер #ffffff (light) ===")
    for k in hex_to_keys.get("#ffffff",[]):
        base = k.split(":",1)[1]
        if k.startswith("light:"):
            print(f"  {base:35} → {len(key_to_files.get(base,[]))} usages")

    # DOT вывод для графа цвет→ключ
    dot = ["digraph theme {"]
    dot.append('  rankdir=LR; node [shape=box];')
    for hx, keys in color_graph.items():
        if len(keys) < 2: continue
        hx_node = f'"hx_{hx}"'
        dot.append(f'  {hx_node} [label="{hx}", shape=ellipse, style=filled, fillcolor="{hx}"];')
        for k in keys:
            dot.append(f'  {hx_node} -> "{k}";')
    dot.append("}")
    out_dot = ROOT / "scripts/theme_graph.dot"
    out_dot.write_text("\n".join(dot))
    print(f"\nDOT saved → {out_dot}")

    out_json = ROOT / "scripts/theme_graph.json"
    out_json.write_text(json.dumps({
        "hex_to_keys": {k: sorted(v) for k,v in hex_to_keys.items() if len(v)>1},
        "key_to_files": {k: v[:5] for k,v in key_to_files.items()},  # sample
        "color_graph": color_graph,
    }, ensure_ascii=False, indent=2))
    print(f"JSON saved → {out_json}")

if __name__ == "__main__":
    main()
