"""Factory function for creating visualizers."""
from src.validator.validator_types import ExportFormat
from .base import BaseVisualizer
from .networkx import NetworkXVisualizer
from .d3 import D3Visualizer
from .mermaid import MermaidVisualizer

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