"""Base visualizer class."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Set

from src.validator.validator_types import CircularRefs

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