"""Mermaid-based visualizer for import graphs."""
from pathlib import Path
from typing import Dict, Set

from .base import BaseVisualizer
from src.validator.validator_types import CircularRefs

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