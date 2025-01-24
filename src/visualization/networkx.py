"""NetworkX-based visualizer for import graphs."""
from pathlib import Path
from typing import Dict, List, Set, Tuple

import networkx as nx
import matplotlib
matplotlib.use('Agg')  # Use Agg backend instead of TkAgg
import matplotlib.pyplot as plt

from .base import BaseVisualizer
from src.validator.validator_types import CircularRefs

class NetworkXVisualizer(BaseVisualizer):
    """NetworkX-based import graph visualizer."""
    
    def __init__(self):
        self.max_edges = 100  # Default max edges to show

    def create_graph(
        self,
        import_graph: Dict[str, Set[str]],
        invalid_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs
    ) -> nx.DiGraph:
        """Create a NetworkX graph from import data."""
        G = nx.DiGraph()
        
        # Collect all edges with their properties
        edges = []
        for source, targets in import_graph.items():
            if not G.has_node(source):
                G.add_node(source)
            for target in targets:
                if not G.has_node(target):
                    G.add_node(target)
                is_invalid = source in invalid_imports and target in invalid_imports[source]
                is_circular = any(source in ref and target in ref for ref in circular_refs)
                edges.append((source, target, {
                    'invalid': is_invalid,
                    'circular': is_circular,
                    'priority': 2 if is_invalid else 1 if is_circular else 0
                }))
        
        # Sort edges by priority (invalid > circular > normal) and limit to max_edges
        edges.sort(key=lambda x: x[2]['priority'], reverse=True)
        edges = edges[:self.max_edges]
        
        # Add edges to graph
        for source, target, attrs in edges:
            G.add_edge(source, target, **attrs)
        
        return G
    
    def prepare_graph_data(self, G: nx.DiGraph) -> Tuple[List[str], List[Tuple[str, str]], Dict[str, str]]:
        """Prepare graph data for visualization."""
        nodes = list(G.nodes())
        edges = list(G.edges())
        edge_colors = {}
        
        for source, target in edges:
            if G.edges[source, target].get('invalid', False):
                edge_colors[(source, target)] = 'red'
            elif G.edges[source, target].get('circular', False):
                edge_colors[(source, target)] = 'orange'
            else:
                edge_colors[(source, target)] = 'black'
        
        return nodes, edges, edge_colors
    
    def visualize(
        self,
        import_graph: Dict[str, Set[str]],
        invalid_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        output_file: Path
    ) -> None:
        """Create a NetworkX visualization of the import graph."""
        G = self.create_graph(import_graph, invalid_imports, circular_refs)
        nodes, edges, edge_colors = self.prepare_graph_data(G)
        
        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(G)
        
        # Draw nodes
        nx.draw_networkx_nodes(G, pos, node_color='lightblue', node_size=1000)
        nx.draw_networkx_labels(G, pos)
        
        # Draw edges with colors
        for edge in edges:
            nx.draw_networkx_edges(
                G, pos,
                edgelist=[edge],
                edge_color=edge_colors[edge],
                arrows=True,
                arrowsize=20
            )
        
        plt.title('Import Graph Visualization')
        plt.axis('off')
        plt.savefig(output_file, format='png', bbox_inches='tight')
        plt.close() 