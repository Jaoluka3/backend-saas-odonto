import ast
import json
import os
from pathlib import Path
import networkx as nx
from datetime import datetime

class CallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.calls = []

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)

def generate_graph(repo_path):
    G = nx.DiGraph()
    repo_dir = Path(repo_path).resolve()
    
    nodes_dict = {}
    edges_list = []
    
    def add_node(n_id, n_type, label, file_path):
        if n_id not in nodes_dict:
            node_data = {
                "id": n_id, 
                "type": n_type, 
                "label": label,
                "file_path": file_path
            }
            nodes_dict[n_id] = node_data
            G.add_node(n_id, **node_data)
            
    def add_edge(src, tgt, e_type):
        edges_list.append({"source": src, "target": tgt, "type": e_type, "relation": e_type})
        G.add_edge(src, tgt, type=e_type, relation=e_type)

    for root, _, files in os.walk(repo_dir):
        if '.git' in root or '.opencode' in root or 'graphify-out' in root:
            continue
            
        for file in files:
            if not file.endswith('.py'):
                continue
                
            filepath = Path(root) / file
            rel_path = filepath.relative_to(repo_dir).as_posix()
            
            try:
                content = filepath.read_text(encoding='utf-8')
                tree = ast.parse(content)
            except Exception as e:
                print(f"Failed to parse {rel_path}: {e}")
                continue
            
            # Module node
            add_node(rel_path, 'module', file, rel_path)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_id = f"{rel_path}:{node.name}"
                    add_node(func_id, 'function', node.name, rel_path)
                    add_edge(rel_path, func_id, 'contains')
                    
                    # Extract calls
                    visitor = CallVisitor()
                    visitor.visit(node)
                    for call_name in visitor.calls:
                        add_edge(func_id, call_name, 'calls')
                    
                elif isinstance(node, ast.ClassDef):
                    class_id = f"{rel_path}:{node.name}"
                    add_node(class_id, 'class', node.name, rel_path)
                    add_edge(rel_path, class_id, 'contains')
                    
                    for subnode in node.body:
                        if isinstance(subnode, ast.FunctionDef):
                            meth_id = f"{class_id}.{subnode.name}"
                            add_node(meth_id, 'method', subnode.name, rel_path)
                            add_edge(class_id, meth_id, 'contains')
                            
                            visitor = CallVisitor()
                            visitor.visit(subnode)
                            for call_name in visitor.calls:
                                add_edge(meth_id, call_name, 'calls')
                            
                elif isinstance(node, ast.Import):
                    for name in node.names:
                        add_node(name.name, 'module', name.name, name.name)
                        add_edge(rel_path, name.name, 'imports')
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        add_node(node.module, 'module', node.module, node.module)
                        add_edge(rel_path, node.module, 'imports')

    graph_data = {
        "nodes": list(nodes_dict.values()),
        "edges": edges_list,
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "repo": str(repo_dir)
        }
    }
    
    out_path = repo_dir / "graph.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, indent=2)
    print(f"Graph generated at {out_path} with {len(nodes_dict)} nodes and {len(edges_list)} edges.")

if __name__ == "__main__":
    generate_graph(os.path.dirname(os.path.abspath(__file__)))
