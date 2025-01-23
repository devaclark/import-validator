"""Visualization functionality for import graphs."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Set, List, Tuple

import networkx as nx
import matplotlib
matplotlib.use('Agg')  # Use Agg backend instead of TkAgg
import matplotlib.pyplot as plt
from .validator.validator_types import CircularRefs, ExportFormat


class BaseVisualizer(ABC):
    """Base class for import graph visualizers."""
    
    @abstractmethod
    def visualize(
        self,
        import_graph: Dict[str, Set[str]],
        invalid_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        output_file: Path
    ) -> None:
        """Create a visualization of the import graph.
        
        Args:
            import_graph: Dictionary mapping source files to their imported files
            invalid_imports: Dictionary mapping files to their invalid imports
            circular_refs: Dictionary mapping files to their circular reference chains
            output_file: Path to save the visualization
            
        Raises:
            ValueError: If the visualization cannot be created
            IOError: If the output file cannot be written
        """
        raise NotImplementedError("Visualizer subclasses must implement visualize method")


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


class D3Visualizer(BaseVisualizer):
    """D3.js-based import graph visualizer."""
    
    def prepare_graph_data(
        self,
        import_graph: Dict[str, Set[str]],
        invalid_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs
    ) -> Tuple[List[Dict], List[Dict]]:
        """Prepare graph data for D3.js visualization."""
        nodes = []
        links = []
        node_ids = {}
        current_id = 0

        # Create nodes
        for source in import_graph:
            if source not in node_ids:
                has_invalid = source in invalid_imports
                has_circular = any(source in ref for ref in circular_refs)
                node_ids[source] = current_id
                nodes.append({
                    'id': current_id,
                    'name': source,
                    'size': 5,
                    'color': '#ff4444' if has_invalid else '#ff8800' if has_circular else '#4488ff'
                })
                current_id += 1

            for target in import_graph[source]:
                if target not in node_ids:
                    has_invalid = target in invalid_imports
                    has_circular = any(target in ref for ref in circular_refs)
                    node_ids[target] = current_id
                    nodes.append({
                        'id': current_id,
                        'name': target,
                        'size': 5,
                        'color': '#ff4444' if has_invalid else '#ff8800' if has_circular else '#4488ff'
                    })
                    current_id += 1

                is_invalid = source in invalid_imports and target in invalid_imports[source]
                is_circular = any(source in ref and target in ref for ref in circular_refs)
                links.append({
                    'source': node_ids[source],
                    'target': node_ids[target],
                    'invalid': is_invalid,
                    'circular': is_circular,
                    'color': '#ff0000' if is_invalid else '#ff8800' if is_circular else '#999999',
                    'width': 2 if is_invalid or is_circular else 1
                })

        return nodes, links
    
    def visualize(
        self,
        import_graph: Dict[str, Set[str]],
        invalid_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        output_file: Path
    ) -> None:
        """Generate D3.js visualization."""
        nodes, links = self.prepare_graph_data(import_graph, invalid_imports, circular_refs)

        # Create HTML template
        html_content = f'''<!DOCTYPE html>
<html>
<head>
    <title>Import Graph Visualization</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        .node {{
            stroke: #fff;
            stroke-width: 2px;
        }}
        .link {{
            stroke: #999;
            stroke-opacity: 0.6;
            stroke-width: 2px;
        }}
        .link.invalid {{
            stroke: #c00;
        }}
        .link.circular {{
            stroke: #f90;
        }}
        .node-label {{
            font-family: Arial;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <h1>Force-Directed Import Graph</h1>
    <div id="graph"></div>
    <script>
        const nodes = {str(nodes).replace("'", '"')};
        const links = {str(links).replace("'", '"')};
        
        const width = 800;
        const height = 600;
        
        const svg = d3.select('#graph')
            .append('svg')
            .attr('width', width)
            .attr('height', height);
        
        const simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(links).id(d => d.id))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(width / 2, height / 2));
        
        const link = svg.append('g')
            .selectAll('line')
            .data(links)
            .join('line')
            .attr('class', d => `link ${{d.invalid ? 'invalid' : ''}} ${{d.circular ? 'circular' : ''}}`)
            .style('stroke', d => d.color)
            .style('stroke-width', d => d.width);
        
        const node = svg.append('g')
            .selectAll('circle')
            .data(nodes)
            .join('circle')
            .attr('class', 'node')
            .attr('r', d => d.size)
            .style('fill', d => d.color);
        
        const label = svg.append('g')
            .selectAll('text')
            .data(nodes)
            .join('text')
            .attr('class', 'node-label')
            .text(d => d.name);
        
        simulation.on('tick', () => {{
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);
            
            node
                .attr('cx', d => d.x)
                .attr('cy', d => d.y);
            
            label
                .attr('x', d => d.x + 8)
                .attr('y', d => d.y + 3);
        }});
    </script>
</body>
</html>'''

        # Write to file
        output_file.write_text(html_content)


class MermaidVisualizer(BaseVisualizer):
    """Mermaid-based import graph visualizer."""
    
    def prepare_graph_data(
        self,
        import_graph: Dict[str, Set[str]],
        invalid_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs
    ) -> str:
        """Prepare graph data for Mermaid visualization."""
        lines = ['graph TD;']
        
        # Add edges with styling
        for source, targets in import_graph.items():
            for target in targets:
                style = ''
                if source in invalid_imports and target in invalid_imports[source]:
                    style = ' style=stroke:#c00'
                elif source in circular_refs:
                    for chain in circular_refs[source]:
                        if len(chain) > 1:
                            for i in range(len(chain) - 1):
                                if chain[i] == source and chain[i + 1] == target:
                                    style = ' style=stroke:#f90'
                
                # Clean node names for Mermaid compatibility
                source_clean = source.replace('.', '_').replace('/', '_')
                target_clean = target.replace('.', '_').replace('/', '_')
                
                lines.append(f'    {source_clean}["{source}"] --> {target_clean}["{target}"]{style}')
        
        return '\n'.join(lines)
    
    def visualize(
        self,
        import_graph: Dict[str, Set[str]],
        invalid_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        output_file: Path
    ) -> None:
        """Create a Mermaid visualization of the import graph."""
        mermaid = self.prepare_graph_data(import_graph, invalid_imports, circular_refs)
        
        markdown = f"""# Import Graph Visualization

```mermaid
{mermaid}
```

## Legend
- Red edges: Invalid imports
- Orange edges: Circular references
- Black edges: Valid imports
"""
        
        output_file.write_text(markdown, encoding='utf-8')


def create_visualizer(format: ExportFormat) -> BaseVisualizer:
    """Create a visualizer based on the specified format."""
    visualizers = {
        ExportFormat.HTML: D3Visualizer,
        ExportFormat.MARKDOWN: MermaidVisualizer,
        ExportFormat.JSON: NetworkXVisualizer,
        ExportFormat.CSV: NetworkXVisualizer
    }

    if format not in visualizers:
        raise ValueError(f"Unsupported visualization format: {format}")

    return visualizers[format]() 