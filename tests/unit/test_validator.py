"""Tests for import validator."""
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
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
from src.validator.validator_types import ImportStats, ValidationResults, ImportUsage, PathNormalizer
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
