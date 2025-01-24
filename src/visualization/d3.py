"""D3.js-based visualizer for import graphs."""
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .base import BaseVisualizer
from src.validator.validator_types import CircularRefs

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