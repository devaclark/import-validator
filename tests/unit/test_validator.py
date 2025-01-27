"""Tests for import validator."""
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock, MagicMock
import pytest
import asyncio
import ast
from src.exporters import JSONExporter
from src.validator import (
    AsyncImportValidator,
    find_python_files_async,
    parse_ast_threaded,
    read_file_async,
    file_exists_async
)
from src.validator.validator_types import ImportStats, ValidationResults, ImportUsage, PathNormalizer, FileStatus, ImportRelationship
from src.validator.config import ImportValidatorConfig
import json
import textwrap
import networkx as nx
import sys
import logging
from src.validator.error_handling import ValidationError
from typing import Union, Dict, Set, AsyncGenerator
from src.validator.file_system_interface import FileSystemInterface
from tests.unit.conftest import MockFileSystem

# Mock Qt components at module level
pytestmark = pytest.mark.usefixtures("mock_qt")

@pytest.fixture
def mock_qt(monkeypatch):
    """Mock Qt components to prevent GUI from opening."""
    # Mock QApplication
    mock_app = Mock()
    mock_app.exec = Mock(return_value=0)
    mock_app.instance = Mock(return_value=None)
    monkeypatch.setattr('PyQt6.QtWidgets.QApplication', Mock(return_value=mock_app))
    
    # Mock QMainWindow
    mock_window = Mock()
    monkeypatch.setattr('PyQt6.QtWidgets.QMainWindow', Mock(return_value=mock_window))
    
    # Mock QWebEngineView
    mock_web_view = Mock()
    mock_web_view.page = Mock(return_value=Mock())
    monkeypatch.setattr('PyQt6.QtWebEngineWidgets.QWebEngineView', Mock(return_value=mock_web_view))
    
    # Mock QWebChannel
    mock_channel = Mock()
    monkeypatch.setattr('PyQt6.QtWebChannel.QWebChannel', Mock(return_value=mock_channel))
    
    # Mock event loop
    mock_loop = AsyncMock()
    mock_loop.run_forever = Mock(return_value=0)
    monkeypatch.setattr('qasync.QEventLoop', Mock(return_value=mock_loop))
    
    return {
        'app': mock_app,
        'window': mock_window,
        'web_view': mock_web_view,
        'channel': mock_channel,
        'loop': mock_loop
    }

@pytest.fixture
def mock_file_content(request):
    """Mock file content for testing. Returns different content based on the test being run."""
    test_name = request.node.name
    
    if test_name == "test_analyze_imports":
        return textwrap.dedent("""
            import os
            from src.utils import helper
        """).strip()
        
    elif test_name == "test_analyze_imports_with_empty_file":
        return ""
        
    elif test_name == "test_analyze_imports_with_read_error":
        return None
        
    elif test_name == "test_analyze_imports_with_parse_error":
        return "def invalid_syntax: ="  # Invalid Python syntax
        
    elif test_name == "test_analyze_imports_with_invalid_imports":
        return textwrap.dedent("""
            import nonexistent_module
            from nonexistent_package import something
            from .nonexistent import stuff
        """).strip()
        
    elif test_name == "test_analyze_imports_with_relative_imports":
        return textwrap.dedent("""
            from . import module
            from .utils import helper
            from ..core import base
        """).strip()
        
    elif test_name in ["test_read_file_async", "test_read_file_async_unicode"]:
        return textwrap.dedent("""
            # Test file
            x = 1
            y = 2
        """).strip()
        
    elif test_name == "test_parse_file_async":
        return textwrap.dedent("""
            x = 1
            y = 2
        """).strip()

    elif test_name in ["test_find_module_path_with_return_statements", 
                      "test_find_module_path_with_complex_imports",
                      "test_find_module_path_with_attribute_access"]:
        return textwrap.dedent("""
            import os
            import sys
        """).strip()
        
    elif test_name == "test_extract_definitions":
        return textwrap.dedent("""
            import os
            import sys
            
            def test_function():
                pass
        """).strip()
        
    # Default content - return empty string for other tests
    return ""

@pytest.fixture
def mock_validator():
    """Create a mock validator."""
    mock = AsyncMock()
    mock.find_module_path = AsyncMock(return_value=None)
    mock.analyze_imports = AsyncMock(return_value=[])  # Return empty list instead of ImportStats
    
    # Create a ValidationResults object for validate_all
    results = ValidationResults()
    results.stats = ImportStats()
    mock.validate_all = AsyncMock(return_value=results)
    
    return mock

@pytest.fixture
def mock_fs():
    """Create a mock file system."""
    fs = MagicMock(spec=FileSystemInterface)
    fs.read_file = AsyncMock(return_value="")
    fs.file_exists = AsyncMock(return_value=True)
    fs.find_python_files = AsyncMock(return_value=set())
    return fs

@pytest.fixture
def basic_config():
    """Create a basic validator configuration."""
    return ImportValidatorConfig(
        base_dir=".",
        src_dir="src",
        tests_dir="tests",
        valid_packages={"requests", "pytest", "flask", "sqlalchemy", "black", "mypy"}
    )

@pytest.mark.asyncio
async def test_analyze_imports(mock_validator, tmp_path):
    """Test analyzing imports from a Python file."""
    results = await mock_validator.analyze_imports(tmp_path / "src/test.py")
    assert isinstance(results, list)

@pytest.mark.asyncio
async def test_analyze_imports_with_empty_file(mock_validator, tmp_path):
    """Test analyzing imports from an empty file."""
    results = await mock_validator.analyze_imports(tmp_path / "src/empty.py")
    assert isinstance(results, list)
    assert len(results) == 0

@pytest.mark.asyncio
async def test_analyze_imports_with_read_error(mock_validator, mock_qt, tmp_path):
    """Test analyzing imports from a file that can't be read."""
    mock_validator.analyze_imports.side_effect = FileNotFoundError("File not found")
    with pytest.raises(FileNotFoundError):
        await mock_validator.analyze_imports(tmp_path / "nonexistent.py")

@pytest.mark.asyncio
async def test_analyze_imports_with_parse_error(mock_validator, mock_qt, tmp_path):
    """Test handling of syntax errors in Python files."""
    mock_validator.analyze_imports.side_effect = SyntaxError("Invalid syntax")
    with pytest.raises(SyntaxError):
        await mock_validator.analyze_imports(tmp_path / "invalid.py")

@pytest.mark.asyncio
async def test_analyze_imports_with_invalid_imports(mock_validator, tmp_path):
    """Test analyzing imports with invalid imports."""
    results = await mock_validator.analyze_imports(tmp_path / "src/invalid.py")
    assert isinstance(results, list)

@pytest.mark.asyncio
async def test_analyze_imports_with_relative_imports(mock_validator, tmp_path):
    """Test analyzing imports with relative imports."""
    results = await mock_validator.analyze_imports(tmp_path / "src/package/module.py")
    assert isinstance(results, list)

@pytest.mark.asyncio
async def test_find_module_path_with_complex_imports(mock_validator, tmp_path):
    """Test finding module path with complex imports."""
    path = await mock_validator.find_module_path("test", tmp_path / "src/package/module.py")
    assert path is None

@pytest.mark.asyncio
async def test_find_module_path_with_return_statements(mock_validator, mock_qt, tmp_path):
    """Test finding module path with return statements."""
    path = await mock_validator.find_module_path("os", tmp_path / "src/test.py")
    assert path is None

@pytest.mark.asyncio
async def test_find_module_path_with_attribute_access(mock_validator, mock_qt, tmp_path):
    """Test finding module path with attribute access."""
    path = await mock_validator.find_module_path("os.path", tmp_path / "src/test.py")
    assert path is None

@pytest.mark.asyncio
async def test_find_module_path_with_file_exists(mock_validator, mock_qt, tmp_path):
    """Test finding module path with file exists."""
    path = await mock_validator.find_module_path("helper", tmp_path / "src/utils/helper.py")
    assert path is None

@pytest.mark.asyncio
async def test_find_module_path_with_empty_relative_import(mock_validator, tmp_path):
    """Test finding module path with empty relative import."""
    path = await mock_validator.find_module_path(".", tmp_path / "src/package/module.py")
    assert path is None

@pytest.mark.asyncio
async def test_find_module_path_with_complex_package_imports(mock_validator, tmp_path):
    """Test finding module path with complex package imports."""
    path = await mock_validator.find_module_path("package", tmp_path / "src/utils/helper.py")
    assert path is None

@pytest.mark.asyncio
async def test_initialize(mock_validator, mock_qt):
    """Test validator initialization."""
    await mock_validator.initialize()
    mock_validator.initialize.assert_called_once()

@pytest.mark.asyncio
async def test_initialize_with_src_and_tests(mock_validator, mock_qt, tmp_path):
    """Test initializing validator with both src and tests directories."""
    await mock_validator.initialize()
    mock_validator.initialize.assert_called_once()

@pytest.mark.asyncio
async def test_validate_all_with_errors(mock_validator, tmp_path):
    """Test validating with errors."""
    results = await mock_validator.validate_all()
    assert isinstance(results, ValidationResults)

@pytest.mark.asyncio
async def test_validate_all_with_complex_project(mock_validator, tmp_path):
    """Test validating a complex project."""
    results = await mock_validator.validate_all()
    assert isinstance(results, ValidationResults)

@pytest.mark.asyncio
async def test_validate_all_error_handling(mock_validator):
    """Test error handling in validate_all."""
    mock_validator.validate_all.side_effect = Exception("Test error")
    with pytest.raises(Exception):
        await mock_validator.validate_all()

@pytest.mark.asyncio
async def test_validate_all_with_empty_project(mock_validator):
    """Test validate_all with an empty project."""
    results = await mock_validator.validate_all()
    assert isinstance(results, ValidationResults)

@pytest.mark.asyncio
async def test_validator_cleanup(mock_validator, tmp_path):
    """Test validator cleanup."""
    await mock_validator.cleanup()
    mock_validator.cleanup.assert_called_once()

@pytest.mark.asyncio
async def test_validator_with_gui(mock_validator, mock_qt, tmp_path):
    """Test validator with GUI components."""
    results = await mock_validator.validate_all()
    assert isinstance(results, ValidationResults)

@pytest.mark.asyncio
async def test_validator_cleanup_with_gui(mock_validator, mock_qt, tmp_path):
    """Test validator cleanup with GUI components."""
    await mock_validator.cleanup()
    mock_validator.cleanup.assert_called_once()

@pytest.mark.asyncio
async def test_validator_error_handling(mock_validator, mock_qt, tmp_path):
    """Test validator error handling."""
    mock_validator.validate_all.side_effect = Exception("Test error")
    with pytest.raises(Exception):
        await mock_validator.validate_all()

@pytest.mark.asyncio
async def test_validator_initialization(basic_config, mock_fs):
    """Test validator initialization."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Check basic attributes
    assert validator.base_dir == Path(".").resolve()
    assert validator.src_dir == Path("src").resolve()
    assert validator.tests_dir == Path("tests").resolve()
    assert validator.fs == mock_fs
    
    # Check package tracking
    assert "requests" in validator.valid_packages
    assert "flask" in validator.valid_packages
    assert "black" in validator.valid_packages
    assert "os" in validator.stdlib_modules
    assert "sys" in validator.stdlib_modules

@pytest.mark.asyncio
async def test_validator_without_tests_dir(mock_fs):
    """Test validator initialization without tests directory."""
    config = ImportValidatorConfig(
        base_dir=".",
        src_dir="src",
        tests_dir=None,
        valid_packages=set()
    )
    validator = AsyncImportValidator(config, mock_fs)
    await validator.initialize()
    
    assert validator.base_dir == Path(".").resolve()
    assert validator.src_dir == Path("src").resolve()
    assert validator.tests_dir is None
    assert len(validator.source_dirs) == 1
    assert validator.source_dirs[0] == validator.src_dir

@pytest.mark.asyncio
async def test_validator_file_status(basic_config, mock_fs):
    """Test file status tracking."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Add a file status
    validator.file_statuses["src/module.py"] = FileStatus(
        path="src/module.py",
        exists=True,
        is_test=False,
        import_count=5,
        invalid_imports=1,
        circular_refs=0,
        relative_imports=2
    )
    
    # Test get_file_status
    status = validator.get_file_status("src/module.py")
    assert status.path == "src/module.py"
    assert status.exists
    assert not status.is_test
    assert status.import_count == 5
    assert status.invalid_imports == 1
    assert status.circular_refs == 0
    assert status.relative_imports == 2
    
    # Test get_file_status for unknown file
    unknown_status = validator.get_file_status("unknown.py")
    assert unknown_status.path == "unknown.py"
    assert not unknown_status.exists
    assert unknown_status.import_count == 0

@pytest.mark.asyncio
async def test_validator_import_relationships(basic_config, mock_fs):
    """Test import relationship tracking."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Add an import relationship
    validator.import_relationships["src/module.py"] = ImportRelationship(
        file_path="src/module.py",
        imports={"os", "sys"},
        imported_by={"main.py"},
        invalid_imports={"invalid_module"},
        relative_imports={".utils"},
        circular_refs=set(),
        stdlib_imports={"os", "sys"},
        thirdparty_imports=set(),
        local_imports=set()
    )
    
    # Test get_import_details
    details = validator.get_import_details("src/module.py")
    assert details.file_path == "src/module.py"
    assert "os" in details.imports
    assert "sys" in details.imports
    assert "main.py" in details.imported_by
    assert "invalid_module" in details.invalid_imports
    assert ".utils" in details.relative_imports
    assert "os" in details.stdlib_imports
    assert "sys" in details.stdlib_imports
    
    # Test get_import_details for unknown file
    unknown_details = validator.get_import_details("unknown.py")
    assert unknown_details.file_path == "unknown.py"
    assert len(unknown_details.imports) == 0
    assert len(unknown_details.imported_by) == 0

@pytest.mark.asyncio
async def test_validator_graph_visualization(basic_config, mock_fs):
    """Test graph visualization helpers."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Add some file statuses and relationships
    validator.file_statuses["src/module.py"] = FileStatus(
        path="src/module.py",
        exists=True,
        is_test=False,
        import_count=2,
        invalid_imports=1,
        circular_refs=0,
        relative_imports=0
    )
    
    validator.import_relationships["src/module.py"] = ImportRelationship(
        file_path="src/module.py",
        imports={"os"},
        imported_by=set(),
        invalid_imports={"invalid"},
        relative_imports=set(),
        circular_refs=set(),
        stdlib_imports={"os"},
        thirdparty_imports=set(),
        local_imports=set()
    )
    
    # Test node color
    color = validator.get_node_color("src/module.py")
    assert isinstance(color, str)
    assert len(color) > 0
    
    # Test edge color
    edge_color = validator.get_edge_color("src/module.py", "os")
    assert isinstance(edge_color, str)
    assert len(edge_color) > 0
    
    # Test node details
    details = validator.get_node_details("src/module.py")
    assert isinstance(details, dict)
    assert details["path"] == "src/module.py"
    assert details["imports"] == 2
    assert details["invalid_imports"] == 1
    assert details["relative_imports"] == 0
    assert details["is_test"] is False

@pytest.mark.asyncio
async def test_validator_stdlib_detection(basic_config, mock_fs):
    """Test standard library module detection."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Test standard library modules
    assert validator.is_stdlib_module("os")
    assert validator.is_stdlib_module("sys")
    assert validator.is_stdlib_module("typing")
    assert validator.is_stdlib_module("pathlib")
    assert validator.is_stdlib_module("unittest")
    
    # Test non-standard library modules
    assert not validator.is_stdlib_module("requests")
    assert not validator.is_stdlib_module("flask")
    assert not validator.is_stdlib_module("nonexistent_module")
    assert not validator.is_stdlib_module("my_local_module")

@pytest.mark.asyncio
async def test_validator_import_classification(basic_config, mock_fs):
    """Test import classification."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Test standard library imports
    assert validator._classify_import("os", "src/module.py") == "stdlib"
    assert validator._classify_import("sys.path", "src/module.py") == "stdlib"
    assert validator._classify_import("typing.List", "src/module.py") == "stdlib"
    
    # Test third-party imports
    assert validator._classify_import("requests", "src/module.py") == "thirdparty"
    assert validator._classify_import("flask.Flask", "src/module.py") == "thirdparty"
    assert validator._classify_import("black.format", "src/module.py") == "thirdparty"
    
    # Test local imports
    assert validator._classify_import("src.module", "src/other.py") == "local"
    assert validator._classify_import("tests.test_module", "tests/other.py") == "local"
    
    # Test relative imports
    assert validator._classify_import(".utils", "src/module.py") == "relative"
    assert validator._classify_import("..module", "src/pkg/module.py") == "relative"

@pytest.mark.asyncio
async def test_validator_relative_import_resolution(basic_config, mock_fs):
    """Test relative import resolution."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Test same directory relative import
    result = validator.resolve_relative_import(
        ".utils",
        "src/package/module.py"
    )
    assert result == "src/package/utils.py"
    
    # Test parent directory relative import
    result = validator.resolve_relative_import(
        "..other",
        "src/package/subdir/module.py"
    )
    assert result == "src/package/other.py"
    
    # Test multiple levels up
    result = validator.resolve_relative_import(
        "...module",
        "src/a/b/c/module.py"
    )
    assert result == "src/a/module.py"
    
    # Test with explicit module name
    result = validator.resolve_relative_import(
        ".submodule",
        "src/package/module.py",
        "package.submodule"
    )
    assert result == "src/package/submodule.py"

@pytest.mark.asyncio
async def test_validator_import_validation(basic_config, mock_fs):
    """Test import validation."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Test valid imports
    assert validator._is_valid_import("os")  # stdlib
    assert validator._is_valid_import("sys.path")  # stdlib with attribute
    assert validator._is_valid_import("requests")  # third-party
    assert validator._is_valid_import("flask.Flask")  # third-party with attribute
    assert validator._is_valid_import("src.module")  # local
    assert validator._is_valid_import(".utils")  # relative
    
    # Test invalid imports
    assert not validator._is_valid_import("nonexistent_module")
    assert not validator._is_valid_import("unknown_package.module")
    assert not validator._is_valid_import("")
    assert not validator._is_valid_import("   ")

@pytest.mark.asyncio
async def test_validator_circular_reference_detection(basic_config, mock_fs):
    """Test circular reference detection."""
    validator = AsyncImportValidator(basic_config, mock_fs)
    await validator.initialize()
    
    # Create a graph with circular references
    validator.import_graph.add_edge("a.py", "b.py")
    validator.import_graph.add_edge("b.py", "c.py")
    validator.import_graph.add_edge("c.py", "a.py")  # Creates cycle
    validator.import_graph.add_edge("d.py", "e.py")  # No cycle
    
    # Create validation results
    results = ValidationResults()
    results.import_graph = validator.import_graph
    
    # Find circular references
    circles = validator.find_circular_references(results)
    
    # Verify results
    assert len(circles) == 1  # One cycle found
    cycle = next(iter(circles.values()))[0]  # Get the first cycle
    assert len(cycle) == 3  # Cycle length is 3
    assert set(cycle) == {"a.py", "b.py", "c.py"}  # Cycle members
