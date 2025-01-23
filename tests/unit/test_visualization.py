"""Tests for visualization functionality."""
import pytest
from pathlib import Path
import networkx as nx
from src.visualization import (
    NetworkXVisualizer,
    D3Visualizer,
    MermaidVisualizer,
    create_visualizer,
    BaseVisualizer
)
from src.validator.validator_types import ExportFormat
from typing import Dict, Set, List


@pytest.fixture
def sample_import_graph():
    """Create a sample import graph for testing."""
    return {
        'main.py': {'utils.py', 'config.py'},
        'utils.py': {'config.py'},
        'config.py': set()
    }


@pytest.fixture
def sample_invalid_imports():
    """Create sample invalid imports for testing."""
    return {
        'main.py': {'invalid_module.py'},
        'utils.py': {'another_invalid.py'}
    }


@pytest.fixture
def sample_circular_refs():
    """Create sample circular references for testing."""
    return {
        'a.py': [['a.py', 'b.py', 'c.py', 'a.py']],
        'b.py': [['b.py', 'c.py', 'a.py', 'b.py']],
        'c.py': [['c.py', 'a.py', 'b.py', 'c.py']]
    }


def test_create_visualizer():
    """Test visualizer factory function."""
    # Test creating visualizer for each format
    assert isinstance(create_visualizer(ExportFormat.HTML), D3Visualizer)
    assert isinstance(create_visualizer(ExportFormat.MARKDOWN), MermaidVisualizer)
    assert isinstance(create_visualizer(ExportFormat.JSON), NetworkXVisualizer)
    assert isinstance(create_visualizer(ExportFormat.CSV), NetworkXVisualizer)


def test_networkx_visualizer(temp_dir, sample_import_graph, sample_invalid_imports, sample_circular_refs):
    """Test NetworkX visualization."""
    visualizer = NetworkXVisualizer()
    output_file = temp_dir / "graph.png"
    
    # Test visualization generation
    visualizer.visualize(
        import_graph=sample_import_graph,
        invalid_imports=sample_invalid_imports,
        circular_refs=sample_circular_refs,
        output_file=output_file
    )
    
    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_networkx_visualizer_empty_graph(temp_dir):
    """Test NetworkX visualization with empty graph."""
    visualizer = NetworkXVisualizer()
    output_file = temp_dir / "empty_graph.png"
    
    visualizer.visualize(
        import_graph={},
        invalid_imports={},
        circular_refs=set(),
        output_file=output_file
    )
    
    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_d3_visualizer(temp_dir, sample_import_graph, sample_invalid_imports, sample_circular_refs):
    """Test D3.js visualization."""
    visualizer = D3Visualizer()
    output_file = temp_dir / "graph.html"
    
    visualizer.visualize(
        import_graph=sample_import_graph,
        invalid_imports=sample_invalid_imports,
        circular_refs=sample_circular_refs,
        output_file=output_file
    )
    
    assert output_file.exists()
    content = output_file.read_text()
    
    # Check for essential D3.js components
    assert 'd3' in content
    assert 'force-directed' in content.lower()
    assert 'svg' in content
    
    # Check that our graph data is included
    for node in sample_import_graph:
        assert node in content
    for node, edges in sample_import_graph.items():
        for edge in edges:
            assert edge in content


def test_d3_visualizer_empty_graph(temp_dir):
    """Test D3.js visualization with empty graph."""
    visualizer = D3Visualizer()
    output_file = temp_dir / "empty_graph.html"
    
    visualizer.visualize(
        import_graph={},
        invalid_imports={},
        circular_refs=set(),
        output_file=output_file
    )
    
    assert output_file.exists()
    content = output_file.read_text()
    assert 'd3' in content
    assert 'nodes = []' in content or '"nodes": []' in content
    assert 'links = []' in content or '"links": []' in content


def test_networkx_visualizer_max_edges():
    """Test NetworkX visualizer with max edges limit."""
    visualizer = NetworkXVisualizer()
    visualizer.max_edges = 2
    
    # Create a graph with more edges than the limit
    graph = {
        'a.py': {'b.py', 'c.py', 'd.py'},
        'b.py': {'c.py', 'd.py'},
        'c.py': {'d.py'}
    }
    
    # Create the graph and check edge count
    G = visualizer.create_graph(
        graph,
        invalid_imports={},
        circular_refs=set()
    )
    
    assert len(G.edges) <= visualizer.max_edges


def test_d3_visualizer_styling():
    """Test D3 visualizer node and edge styling."""
    visualizer = D3Visualizer()
    
    # Create a graph with various types of nodes and edges
    graph = {
        'a.py': {'b.py'},
        'b.py': {'c.py'},
        'c.py': {'a.py'}
    }
    
    invalid_imports = {'a.py': {'invalid.py'}}
    circular_refs = {
        'a.py': [['a.py', 'b.py', 'c.py', 'a.py']],
        'b.py': [['b.py', 'c.py', 'a.py', 'b.py']]
    }
    
    # Get the generated graph data
    nodes, links = visualizer.prepare_graph_data(
        graph,
        invalid_imports,
        circular_refs
    )
    
    # Check node styling
    for node in nodes:
        assert 'color' in node
        assert 'size' in node
    
    # Check link styling
    for link in links:
        assert 'color' in link
        assert 'width' in link


def test_networkx_visualizer_edge_colors(temp_dir):
    """Test NetworkX visualizer edge colors."""
    visualizer = NetworkXVisualizer()
    output_file = temp_dir / "graph.png"
    
    # Create a graph with invalid and circular imports
    import_graph = {
        'a.py': {'b.py', 'c.py'},
        'b.py': {'c.py'},
        'c.py': {'a.py'}
    }
    invalid_imports = {'a.py': {'b.py'}}
    circular_refs = {
        'a.py': [['a.py', 'b.py', 'c.py', 'a.py']],
        'b.py': [['b.py', 'c.py', 'a.py', 'b.py']]
    }
    
    # Test all edge color cases
    visualizer.visualize(import_graph, invalid_imports, circular_refs, output_file)
    assert output_file.exists()
    
    # Test edge colors
    G = nx.DiGraph()
    for source, targets in import_graph.items():
        for target in targets:
            G.add_edge(source, target)
            if source in invalid_imports and target in invalid_imports[source]:
                G.edges[source, target]['invalid'] = True
            elif source in circular_refs:
                for chain in circular_refs[source]:
                    if len(chain) > 1:
                        for i in range(len(chain) - 1):
                            if chain[i] == source and chain[i + 1] == target:
                                G.edges[source, target]['circular'] = True
    
    nodes, edges, edge_colors = visualizer.prepare_graph_data(G)
    assert any(color == 'red' for color in edge_colors.values())  # Invalid imports
    assert any(color == 'orange' for color in edge_colors.values())  # Circular imports
    assert any(color == 'black' for color in edge_colors.values())  # Normal imports


def test_mermaid_visualizer_circular_refs(temp_dir):
    """Test Mermaid visualizer circular reference styling."""
    visualizer = MermaidVisualizer()
    output_file = temp_dir / "graph.md"
    
    # Create a graph with circular imports
    import_graph = {
        'a.py': {'b.py'},
        'b.py': {'c.py'},
        'c.py': {'a.py'}
    }
    invalid_imports = {'a.py': {'b.py'}}  # Add invalid imports
    circular_refs = {
        'a.py': [['a.py', 'b.py', 'c.py', 'a.py']],
        'b.py': [['b.py', 'c.py', 'a.py', 'b.py']]
    }
    
    visualizer.visualize(import_graph, invalid_imports, circular_refs, output_file)
    assert output_file.exists()
    content = output_file.read_text()
    assert 'style=stroke:#c00' in content  # Invalid imports
    assert 'style=stroke:#f90' in content  # Circular imports


def test_create_visualizer_unsupported_format():
    """Test creating a visualizer with an unsupported format."""
    with pytest.raises(ValueError, match="Unsupported visualization format"):
        create_visualizer("invalid")


class TestBaseVisualizer(BaseVisualizer):
    """Test implementation of BaseVisualizer."""
    
    def visualize(self, import_graph, invalid_imports, circular_refs, output_file):
        """Test implementation that does nothing."""
        pass


def test_base_visualizer():
    """Test that BaseVisualizer is properly abstract."""
    class ConcreteVisualizer(BaseVisualizer):
        pass
    
    with pytest.raises(TypeError, match="Can't instantiate abstract class ConcreteVisualizer"):
        ConcreteVisualizer()


def test_base_visualizer_visualize():
    """Test that BaseVisualizer.visualize raises NotImplementedError."""
    class ConcreteVisualizer(BaseVisualizer):
        def __init__(self):
            pass
        
        def visualize(
            self,
            import_graph: Dict[str, Set[str]],
            invalid_imports: Dict[str, Set[str]],
            circular_refs: Dict[str, List[List[str]]],
            output_file: Path
        ) -> None:
            super().visualize(import_graph, invalid_imports, circular_refs, output_file)
    
    visualizer = ConcreteVisualizer()
    with pytest.raises(NotImplementedError, match="Visualizer subclasses must implement visualize method"):
        visualizer.visualize({}, {}, {}, Path('test.png')) 