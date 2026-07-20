#!/usr/bin/env python3
import json
import os
from pathlib import Path

def build_llms_txt(repo_root: Path, lang="en") -> str:
    help_dir = repo_root / "src" / "resources" / "help"
    tree_path = help_dir / "tree.json"
    lang_dir = help_dir / lang
    
    with open(tree_path, 'r', encoding='utf-8') as f:
        tree = json.load(f)
        
    nodes = tree.get('nodes', {})
    
    output = []
    output.append("# Improve-ImgSLI Documentation\n")
    output.append("> Improve-ImgSLI is a declarative, highly-optimized image comparison tool for developers, QA, and content creators. It features a responsive UI, advanced canvas rendering, and extensive diffing tools.\n\n")
    
    def visit_node(node_id, depth=1):
        node = nodes.get(node_id)
        if not node:
            return
            
        if node['kind'] == 'hub':
            if node_id != 'root':
                output.append(f"{'#' * depth} {node['title']}\n")
                if 'description' in node:
                    output.append(f"{node['description']}\n\n")
            for child_id in node.get('children', []):
                visit_node(child_id, depth + 1 if node_id != 'root' else depth)
                
        elif node['kind'] == 'page':
            output.append(f"{'#' * depth} {node['title']}\n")
            if 'description' in node:
                output.append(f"*{node['description']}*\n\n")
            
            body_rel_path = node.get('body')
            if body_rel_path:
                body_path = lang_dir / body_rel_path
                if body_path.exists():
                    with open(body_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        lines = content.split('\n')
                        for line in lines:
                            if line.startswith('#'):
                                output.append('#' * depth + line)
                            else:
                                output.append(line)
                        output.append("\n\n")
                else:
                    output.append(f"*(Content missing: {body_rel_path})*\n\n")
                    
    visit_node('root', 2)
    return "\n".join(output)

if __name__ == '__main__':
    # When run from scripts/
    repo_root = Path(__file__).parent.parent
    content = build_llms_txt(repo_root)
    
    # Write to root of repository
    out_path = repo_root / "llms.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Generated {out_path}")
    print(f"Size: {len(content)} characters")
