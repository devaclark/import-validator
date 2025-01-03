"""Visualization utilities for import validator."""
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Set
import json
import networkx as nx
import matplotlib.pyplot as plt
from rich.progress import Progress
from .validator_types import ImportGraph, ExportFormat


class Visualizer(Protocol):
    """Protocol for visualization implementations."""
    
    def visualize(
        self,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        circular_refs: Set[tuple[str, str]],
        output_file: Path
    ) -> None:
        """Generate visualization of the import graph."""
        ...


class NetworkXVisualizer:
    """Visualizer using NetworkX and matplotlib."""
    
    def __init__(
        self,
        node_color: str = 'lightblue',
        edge_color: str = 'gray',
        font_size: int = 8,
        node_size: int = 500,
        max_edges: int = 500
    ):
        self.node_color = node_color
        self.edge_color = edge_color
        self.font_size = font_size
        self.node_size = node_size
        self.max_edges = max_edges

    def visualize(
        self,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        circular_refs: Set[tuple[str, str]],
        output_file: Path
    ) -> None:
        """Generate NetworkX visualization of the import graph."""
        G = nx.DiGraph()
        edge_count = 0
        
        # Add nodes and edges (limited to max_edges)
        for source, targets in import_graph.items():
            if edge_count >= self.max_edges:
                break
                
            source_name = str(Path(source).name)
            G.add_node(source_name)
            
            for target in targets:
                if edge_count >= self.max_edges:
                    break
                    
                target_name = str(Path(target).name)
                G.add_edge(source_name, target_name)
                edge_count += 1
        
        # Set up the plot
        plt.figure(figsize=(20, 20))
        pos = nx.spring_layout(G, k=1, iterations=50)
        
        # Draw the base graph
        nx.draw(
            G, pos,
            with_labels=True,
            node_color=self.node_color,
            node_size=self.node_size,
            font_size=self.font_size,
            font_weight='bold',
            arrows=True,
            edge_color=self.edge_color,
            arrowsize=10
        )
        
        # Highlight invalid imports
        invalid_edges = [
            (str(Path(source).name), str(Path(target).name))
            for source, targets in invalid_imports.items()
            for target in targets
            if G.has_edge(str(Path(source).name), str(Path(target).name))
        ]
        if invalid_edges:
            nx.draw_networkx_edges(
                G, pos,
                edgelist=invalid_edges,
                edge_color='red',
                width=2
            )
        
        # Highlight circular references
        circular_edges = [
            (str(Path(source).name), str(Path(target).name))
            for source, target in circular_refs
            if G.has_edge(str(Path(source).name), str(Path(target).name))
        ]
        if circular_edges:
            nx.draw_networkx_edges(
                G, pos,
                edgelist=circular_edges,
                edge_color='orange',
                width=2
            )
        
        plt.savefig(output_file, format='png', dpi=300, bbox_inches='tight')
        plt.close()


class MermaidVisualizer:
    """Visualizer using Mermaid diagrams."""
    
    def __init__(self, max_edges: int = 100):
        self.max_edges = max_edges

    def visualize(
        self,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        circular_refs: Set[tuple[str, str]],
        output_file: Path
    ) -> None:
        """Generate Mermaid visualization of the import graph."""
        mermaid_code = [
            "graph TB",
            "  %% Node styles",
            "  classDef default fill:#f9f9f9,stroke:#333,stroke-width:1px;",
            "  classDef invalid fill:#ffebee,stroke:#c62828,stroke-width:2px;",
            "  classDef circular fill:#fff3e0,stroke:#ef6c00,stroke-width:2px;",
            "  %% Link styles",
            "  linkStyle default stroke:#666,stroke-width:1px;",
            ""
        ]
        
        # Add nodes
        added_nodes = set()
        for source in import_graph:
            source_id = str(Path(source).name).replace('.', '_')
            if source_id not in added_nodes:
                style_class = ""
                if source in invalid_imports and invalid_imports[source]:  # Only if there are actual invalid imports
                    style_class = ":::invalid"
                elif any(s == source or t == source for s, t in circular_refs):
                    style_class = ":::circular"
                
                mermaid_code.append(f"  {source_id}[\"{source_id}\"] {style_class}")
                added_nodes.add(source_id)
        
        # Add edges (limited to max_edges)
        edge_count = 0
        for source, targets in import_graph.items():
            if edge_count >= self.max_edges:
                mermaid_code.append("  %% Note: Some edges omitted due to size limits")
                break
                
            source_id = str(Path(source).name).replace('.', '_')
            for target in targets:
                target_id = str(Path(target).name).replace('.', '_')
                
                edge_style = ""
                if source in invalid_imports and target in invalid_imports[source]:
                    edge_style = " style stroke:#c62828"
                elif (source, target) in circular_refs:
                    edge_style = " style stroke:#ef6c00"
                
                mermaid_code.append(f"  {source_id} --> {target_id}{edge_style}")
                edge_count += 1
        
        # Write to file
        output_file.write_text('\n'.join(mermaid_code), encoding='utf-8')


class D3Visualizer:
    """Visualizer using D3.js for interactive visualization."""
    
    def __init__(self, template_file: Optional[Path] = None, max_edges: int = 500):
        self.template_file = template_file or Path(__file__).parent / 'templates' / 'd3_template.html'
        self.max_edges = max_edges

    def _to_js_bool(self, value: bool) -> str:
        """Convert Python boolean to JavaScript boolean string."""
        return "true" if value else "false"

    def visualize(
        self,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        circular_refs: Set[tuple[str, str]],
        output_file: Path
    ) -> None:
        """Generate D3.js visualization of the import graph."""
        # Convert graph to D3 format
        nodes = []
        links = []
        node_ids = {}
        edge_count = 0
        
        # Create nodes and store their IDs
        for i, source in enumerate(import_graph):
            node_ids[source] = i
            # Convert sets to lists and ensure all paths are strings
            invalid_list = [str(path) for path in invalid_imports.get(source, set())]
            
            # Find all circular references involving this node
            circular_chains = []
            for s, t in circular_refs:
                if s == source:
                    circular_chains.append([s, t])
                elif t == source:
                    # Look for the complete chain
                    chain = [t]
                    current = t
                    while True:
                        next_refs = [(s1, t1) for s1, t1 in circular_refs if s1 == current]
                        if not next_refs:
                            break
                        current = next_refs[0][1]
                        chain.append(current)
                        if current == t:  # Complete cycle found
                            circular_chains.append(chain)
                            break
            
            nodes.append({
                'id': i,
                'name': str(Path(source).name),
                'full_path': str(source),
                'invalid': self._to_js_bool(bool(invalid_imports.get(source, set()))),  # Only true if there are actual invalid imports
                'circular': self._to_js_bool(any(s == source or t == source for s, t in circular_refs)),
                'invalid_imports': invalid_list,
                'circular_chains': circular_chains
            })
        
        # Create links based on import relationships (limited to max_edges)
        for source, targets in import_graph.items():
            if edge_count >= self.max_edges:
                break
                
            source_id = node_ids[source]
            for target in targets:
                if edge_count >= self.max_edges:
                    break
                    
                # Only create link if both source and target exist
                if target in node_ids:
                    target_id = node_ids[target]
                    is_invalid = source in invalid_imports and target in invalid_imports[source]
                    is_circular = (source, target) in circular_refs
                    
                    # Only add the link if it represents a real relationship
                    if source != target:  # Avoid self-links
                        links.append({
                            'source': source_id,
                            'target': target_id,
                            'invalid': self._to_js_bool(is_invalid),
                            'circular': self._to_js_bool(is_circular)
                        })
                        edge_count += 1
        
        # Read template and replace placeholders
        template = self.template_file.read_text(encoding='utf-8')
        graph_data = {
            'nodes': nodes,
            'links': links,
            'total_edges': len(links),
            'max_edges': self.max_edges,
            'edges_limited': edge_count >= self.max_edges
        }
        # Ensure proper JSON serialization with explicit encoding
        json_str = json.dumps(graph_data, ensure_ascii=False, separators=(',', ':'))
        visualization = template.replace(
            '/*DATA_PLACEHOLDER*/',
            f'const graph = {json_str};'
        )
        
        # Write output with explicit encoding
        output_file.write_text(visualization, encoding='utf-8')


def create_visualizer(format: ExportFormat) -> Visualizer:
    """Factory function to create appropriate visualizer."""
    if format == ExportFormat.HTML:
        return D3Visualizer()
    elif format == ExportFormat.MARKDOWN:
        return MermaidVisualizer()
    else:
        return NetworkXVisualizer() 