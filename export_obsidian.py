import json
import re
from pathlib import Path
from datetime import datetime
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_obsidian

def safe_name(label: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
    cleaned = re.sub(r"\.(md|mdx|markdown)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned or "unnamed"

def enrich_frontmatter(G, output_dir):
    timestamp = datetime.now().isoformat()
    out = Path(output_dir)
    
    # Rebuild filename mapping
    node_filename = {}
    seen_names = {}
    for node_id, data in G.nodes(data=True):
        base = safe_name(data.get("label", node_id))
        if base in seen_names:
            seen_names[base] += 1
            node_filename[node_id] = f"{base}_{seen_names[base]}"
        else:
            seen_names[base] = 0
            node_filename[node_id] = base
            
    # Modify files
    for node_id, data in G.nodes(data=True):
        fname = node_filename[node_id] + ".md"
        fpath = out / fname
        if not fpath.exists():
            continue
            
        content = fpath.read_text(encoding="utf-8")
        
        # Split out old frontmatter
        parts = content.split("---")
        if len(parts) >= 3:
            body = "---".join(parts[2:])
        else:
            body = content
            
        module_name = data.get("label", node_id)
        file_path = data.get("file_path", node_id)
        degree_count = G.degree(node_id)
        
        new_frontmatter = f"""---
tags: [opencode, backend, {module_name}]
module: {file_path}
last_sync: {timestamp}
connections: {degree_count}
---"""
        
        new_content = new_frontmatter + body
        fpath.write_text(new_content, encoding="utf-8")

def export():
    graph_path = Path("graph.json")
    if not graph_path.exists():
        print("graph.json not found")
        return
        
    data = json.loads(graph_path.read_text())
    G = build_from_json(data)
    
    # Fix cluster() return signature - it only returns communities
    communities = cluster(G)
    cohesion = {} 
    
    output_dir = "/storage/emulated/0/Obsidian/opencode-vault"
    
    # Generate default output
    to_obsidian(G, communities, output_dir, cohesion=cohesion)
    
    # Enrich frontmatter as per objective 5
    enrich_frontmatter(G, output_dir)
    
    print(f"Exported Obsidian vault to {output_dir}")

if __name__ == "__main__":
    export()
