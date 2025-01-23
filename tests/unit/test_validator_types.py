"""Tests for validator types."""
import ast
from pathlib import Path
from src.validator.validator_types import (
    ExportFormat,
    ImportUsage,
    ValidationError,
    ImportStats
)


def test_export_format():
    """Test ExportFormat enum."""
    assert ExportFormat.MARKDOWN.name == 'MARKDOWN'
    assert ExportFormat.HTML.name == 'HTML'
    assert ExportFormat.JSON.name == 'JSON'
    assert ExportFormat.CSV.name == 'CSV'
    
    # Test that values are unique
    values = [format.value for format in ExportFormat]
    assert len(values) == len(set(values))


def test_import_usage():
    """Test ImportUsage dataclass."""
    usage = ImportUsage(
        file=Path("test.py"),
        imports={"os", "sys"},
        invalid_imports={"invalid_module"},
        unused_imports={"sys"},
        relative_imports={".utils"},
        complexity_score=1.5,
        errors=["Error message"]
    )
    
    assert usage.file_path == "test.py"
    assert usage.name == "test.py"
    assert usage.imports == {"os", "sys"}
    assert usage.invalid_imports == {"invalid_module"}
    assert usage.unused_imports == {"sys"}
    assert usage.relative_imports == {".utils"}
    assert usage.complexity_score == 1.5
    assert usage.errors == ["Error message"]


def test_validation_error():
    """Test ValidationError dataclass."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='import_error',
        message='Invalid import',
        line_number=42,
        context='import statement'
    )
    
    assert error.file_path == str(Path('test.py'))
    assert error.error_type == 'import_error'
    assert error.message == 'Invalid import'
    assert error.line_number == 42
    assert error.context == 'import statement'


def test_validation_error_optional_fields():
    """Test ValidationError with optional fields."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='import_error',
        message='Invalid import'
    )
    
    assert error.line_number is None
    assert error.context is None


def test_import_stats():
    """Test ImportStats dataclass."""
    stats = ImportStats(
        total_imports=100,
        unique_imports=50,
        most_common=[('os', 10), ('sys', 8)],
        complexity_score=5.5,
        files_with_most_imports=[('main.py', 20), ('utils.py', 15)],
        invalid_imports_count=5,
        unused_imports_count=10,
        relative_imports_count=15,
        circular_refs_count=2,
        total_nodes=30,
        total_edges=40
    )
    
    assert stats.total_imports == 100
    assert stats.unique_imports == 50
    assert stats.most_common == [('os', 10), ('sys', 8)]
    assert stats.complexity_score == 5.5
    assert stats.files_with_most_imports == [('main.py', 20), ('utils.py', 15)]
    assert stats.invalid_imports_count == 5
    assert stats.unused_imports_count == 10
    assert stats.relative_imports_count == 15
    assert stats.circular_refs_count == 2
    assert stats.total_nodes == 30
    assert stats.total_edges == 40


def test_import_stats_defaults():
    """Test ImportStats default values."""
    stats = ImportStats()
    
    assert stats.total_imports == 0
    assert stats.unique_imports == 0
    assert stats.most_common == []
    assert stats.complexity_score == 0.0
    assert stats.files_with_most_imports == []
    assert stats.invalid_imports_count == 0
    assert stats.unused_imports_count == 0
    assert stats.relative_imports_count == 0
    assert stats.circular_refs_count == 0
    assert stats.total_nodes == 0
    assert stats.total_edges == 0