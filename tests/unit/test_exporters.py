"""Test cases for exporter functionality."""
from pathlib import Path
import json
import pytest
import ast

from src.exporters import (
    create_exporter,
    HTMLExporter,
    JSONExporter,
    MarkdownExporter,
    CSVExporter,
    BaseExporter
)
from src.validator.validator_types import (
    ExportFormat,
    ImportStats,
    ValidationError,
    ValidationResults
)


@pytest.fixture
def sample_data():
    """Sample data for testing exporters."""
    return {
        'stats': ImportStats(
            total_imports=10,
            unique_imports=8,
            complexity_score=5.0,
            invalid_imports_count=2,
            unused_imports_count=3,
            relative_imports_count=1,
            circular_refs_count=2,
            most_common=[('os', 5), ('sys', 3)],
            files_with_most_imports=[('main.py', 5), ('utils.py', 3)],
            total_nodes=5,
            total_edges=8,
            edges_count=8
        ),
        'import_graph': {
            'main.py': {'utils.py', 'config.py'},
            'utils.py': {'config.py'},
            'config.py': set()
        },
        'invalid_imports': {
            'main.py': {'invalid_module.py'},
            'utils.py': {'another_invalid.py'}
        },
        'unused_imports': {
            'main.py': {'unused_module'},
            'utils.py': {'another_unused'}
        },
        'relative_imports': {
            'main.py': {'.utils'},
            'utils.py': {'..config'}
        },
        'circular_refs': {
            'a.py': [['a.py', 'b.py', 'c.py', 'a.py']],
            'b.py': [['b.py', 'c.py', 'a.py', 'b.py']]
        },
        'errors': [
            ValidationError(file='main.py', error_type='ImportError', message='Module not found'),
            ValidationError(file='utils.py', error_type='CircularImport', message='Circular dependency detected')
        ],
        'module_definitions': {
            'main.py': ast.Module(body=[], type_ignores=[]),
            'utils.py': ast.Module(body=[], type_ignores=[]),
            'config.py': ast.Module(body=[], type_ignores=[])
        }
    }


def test_create_exporter():
    """Test exporter creation."""
    assert isinstance(create_exporter(ExportFormat.JSON), JSONExporter)
    assert isinstance(create_exporter(ExportFormat.HTML), HTMLExporter)
    assert isinstance(create_exporter(ExportFormat.MARKDOWN), MarkdownExporter)
    assert isinstance(create_exporter(ExportFormat.CSV), CSVExporter)


def test_json_exporter(temp_dir, sample_data):
    """Test JSON export functionality."""
    exporter = JSONExporter()
    output_file = temp_dir / "report.json"
    
    # Create ValidationResults object
    results = ValidationResults()
    results.stats = sample_data['stats']
    results.import_graph = sample_data['import_graph']
    results.invalid_imports.update(sample_data['invalid_imports'])
    results.unused_imports.update(sample_data['unused_imports'])
    results.relative_imports.update(sample_data['relative_imports'])
    results.circular_refs = sample_data['circular_refs']
    results.errors = sample_data['errors']
    results.module_definitions = sample_data['module_definitions']
    
    # Export results
    exporter.export(results, output_file)
    
    # Verify file was created and content
    assert output_file.exists()
    with open(output_file) as f:
        data = json.load(f)
        assert data['stats']['total_imports'] == 10
        assert data['stats']['unique_imports'] == 8
        assert data['stats']['complexity_score'] == 5.0
        assert data['stats']['invalid_imports_count'] == 2
        assert data['stats']['unused_imports_count'] == 3
        assert data['stats']['relative_imports_count'] == 1
        assert data['stats']['circular_refs_count'] == 2
        assert data['stats']['total_nodes'] == 5
        assert data['stats']['total_edges'] == 8
        assert set(data['import_graph']['main.py']) == {'utils.py', 'config.py'}
        assert set(data['invalid_imports']['main.py']) == {'invalid_module.py'}
        assert set(data['unused_imports']['main.py']) == {'unused_module'}
        assert set(data['relative_imports']['main.py']) == {'.utils'}
        assert len(data['circular_refs']['a.py']) == 1
        assert set(data['circular_refs']['a.py'][0]) == {'a.py', 'b.py', 'c.py'}


def test_markdown_exporter(temp_dir, sample_data):
    """Test Markdown export functionality."""
    exporter = MarkdownExporter()
    output_file = temp_dir / "report.md"
    
    # Create ValidationResults object
    results = ValidationResults()
    results.stats = sample_data['stats']
    results.import_graph = sample_data['import_graph']
    results.invalid_imports.update(sample_data['invalid_imports'])
    results.unused_imports.update(sample_data['unused_imports'])
    results.relative_imports.update(sample_data['relative_imports'])
    results.circular_refs = sample_data['circular_refs']
    results.errors = sample_data['errors']
    results.module_definitions = sample_data['module_definitions']
    
    # Export results
    exporter.export(results, output_file)
    
    # Verify file was created
    assert output_file.exists()
    
    # Verify content
    content = output_file.read_text()
    assert '# Import Analysis Report' in content
    assert '## Statistics' in content
    assert '## Import Graph' in content
    assert '## Invalid Imports' in content
    assert '## Unused Imports' in content
    assert '## Relative Imports' in content
    assert '## Circular References' in content


def test_html_exporter(temp_dir, sample_data):
    """Test HTML export functionality."""
    exporter = HTMLExporter()
    output_file = temp_dir / "report.html"
    
    # Create ValidationResults object
    results = ValidationResults()
    results.stats = sample_data['stats']
    results.import_graph = sample_data['import_graph']
    results.invalid_imports.update(sample_data['invalid_imports'])
    results.unused_imports.update(sample_data['unused_imports'])
    results.relative_imports.update(sample_data['relative_imports'])
    results.circular_refs = sample_data['circular_refs']
    results.errors = sample_data['errors']
    results.module_definitions = sample_data['module_definitions']
    
    # Export results
    exporter.export(results, output_file)
    
    # Verify file was created
    assert output_file.exists()
    
    # Verify content
    content = output_file.read_text()
    assert '<html>' in content
    assert '<title>Import Analysis Report</title>' in content
    assert str(sample_data['stats'].total_imports) in content
    assert str(sample_data['stats'].complexity_score) in content


def test_csv_exporter(temp_dir, sample_data):
    """Test CSV export functionality."""
    exporter = CSVExporter()
    output_file = temp_dir / "report.csv"
    
    # Create ValidationResults object
    results = ValidationResults()
    results.stats = sample_data['stats']
    results.import_graph = sample_data['import_graph']
    results.invalid_imports.update(sample_data['invalid_imports'])
    results.unused_imports.update(sample_data['unused_imports'])
    results.relative_imports.update(sample_data['relative_imports'])
    results.circular_refs = sample_data['circular_refs']
    results.errors = sample_data['errors']
    results.module_definitions = sample_data['module_definitions']
    
    # Export results
    exporter.export(results, output_file)
    
    # Verify CSV directory was created
    csv_dir = output_file.parent / output_file.stem
    assert csv_dir.exists()
    
    # Verify stats.csv
    stats_file = csv_dir / "stats.csv"
    assert stats_file.exists()
    content = stats_file.read_text()
    assert 'TotalImports,10' in content.replace('\r\n', '\n').replace(' ', '')
    assert 'ComplexityScore,5.0' in content.replace('\r\n', '\n').replace(' ', '')


def test_html_exporter_no_visualization(temp_dir, sample_data):
    """Test HTML export without visualization."""
    exporter = HTMLExporter()
    output_file = temp_dir / "report_no_viz.html"
    
    # Create empty graph data
    empty_data = sample_data.copy()
    empty_data['import_graph'] = {}
    empty_data['invalid_imports'] = {}
    empty_data['circular_refs'] = {}
    
    # Create ValidationResults object
    results = ValidationResults()
    results.stats = empty_data['stats']
    results.import_graph = empty_data['import_graph']
    results.invalid_imports.update(empty_data['invalid_imports'])
    results.unused_imports.update(empty_data['unused_imports'])
    results.relative_imports.update(empty_data['relative_imports'])
    results.circular_refs = empty_data['circular_refs']
    results.errors = empty_data['errors']
    results.module_definitions = empty_data['module_definitions']
    
    # Export results
    exporter.export(results, output_file, visualize=False)
    
    # Verify file was created
    assert output_file.exists()
    
    # Verify content
    content = output_file.read_text()
    assert 'Import Analysis Report' in content
    assert 'visualization' not in content.lower()


def test_create_exporter_unsupported_format():
    """Test creating an exporter with an unsupported format."""
    with pytest.raises(ValueError, match="Unsupported export format"):
        create_exporter("invalid") 


def test_base_exporter():
    """Test that BaseExporter is properly abstract."""
    class ConcreteExporter(BaseExporter):
        pass
    
    with pytest.raises(TypeError, match="Can't instantiate abstract class ConcreteExporter"):
        ConcreteExporter()


def test_base_exporter_export():
    """Test that BaseExporter.export raises NotImplementedError."""
    class ConcreteExporter(BaseExporter):
        def __init__(self):
            pass
        
        def export(self, results: ValidationResults, output_file: Path, visualize: bool = True) -> None:
            super().export(results, output_file, visualize)
    
    exporter = ConcreteExporter()
    with pytest.raises(NotImplementedError, match="Exporter subclasses must implement export method"):
        exporter.export(ValidationResults(), Path('test.json'), True) 