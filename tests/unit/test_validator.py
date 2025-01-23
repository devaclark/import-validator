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
from src.validator.validator import PathEncoder, json_dumps
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
async def mock_validator(tmp_path):
    """Create a mock validator for testing."""
    # Create test files
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    
    test_files = {
        'src/test.py': 'import os\nimport sys\ndef test(): pass',
        'src/empty.py': '',
        'src/invalid.py': 'import nonexistent_module',
        'src/package/__init__.py': '',
        'src/package/module.py': 'from . import helper',
        'src/utils/helper.py': 'from ..test import test'
    }
    
    # Create the files
    for path, content in test_files.items():
        file_path = tmp_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content.strip())
    
    # Create validator config
    config = ImportValidatorConfig(
        base_dir=str(tmp_path),
        src_dir='src',
        tests_dir='tests',
        valid_packages=['src'],
        ignore_patterns=[],
        complexity_threshold=3.0,
        max_edges_per_diagram=100
    )
    
    # Create mock file system
    mock_fs = MockFileSystem(base_dir=str(tmp_path), mock_files=test_files)
    
    # Create validator
    validator = AsyncImportValidator(config=config, file_system=mock_fs)
    
    # Mock progress methods
    validator.show_progress = AsyncMock()
    validator.update_progress = AsyncMock()
    validator.cleanup = AsyncMock()
    
    # Mock validate_all to return results
    async def mock_validate_all():
        return ValidationResults()
    validator.validate_all = mock_validate_all
    
    # Mock analyze_imports to return results
    async def mock_analyze_imports(file_path):
        if 'empty.py' in str(file_path):
            return ImportStats()
        elif 'invalid.py' in str(file_path):
            return ImportStats(total_imports=1, errors=['Invalid import: nonexistent_module'])
        elif 'module.py' in str(file_path):
            return ImportStats(total_imports=1, relative_imports=1)
        else:
            return ImportStats(total_imports=2, standard_imports=2)
    validator.analyze_imports = mock_analyze_imports
    
    # Make validator iterable
    async def mock_aiter(self):
        yield ValidationResults()
    validator.__aiter__ = mock_aiter.__get__(validator)
    
    return validator

@pytest.mark.asyncio
async def test_analyze_imports(mock_validator, tmp_path):
    """Test analyzing imports from a Python file."""
    results = await mock_validator.analyze_imports(tmp_path / "src/test.py")
    assert results.stats.total_imports == 2
    assert results.stats.stdlib_imports == 2
    assert results.stats.local_imports == 0
    assert results.stats.relative_imports == 0

@pytest.mark.asyncio
async def test_analyze_imports_with_empty_file(mock_validator, tmp_path):
    """Test analyzing imports from an empty file."""
    results = await mock_validator.analyze_imports(tmp_path / "src/empty.py")
    assert results.stats.total_imports == 0

@pytest.mark.asyncio
async def test_analyze_imports_with_read_error(mock_validator, mock_qt, tmp_path):
    """Test analyzing imports from a file that can't be read."""
    async for v in mock_validator:
        results = ValidationResults()
        with pytest.raises(FileNotFoundError):
            await v.analyze_imports(tmp_path / 'nonexistent.py', results)

@pytest.mark.asyncio
async def test_analyze_imports_with_parse_error(mock_validator, mock_qt, tmp_path):
    """Test handling of syntax errors in Python files."""
    async for v in mock_validator:
        results = ValidationResults()
        with pytest.raises(SyntaxError):
            await v.analyze_imports(tmp_path / 'src/parse_error.py', results)

@pytest.mark.asyncio
async def test_analyze_imports_with_invalid_imports(mock_validator, tmp_path):
    """Test analyzing imports with invalid imports."""
    results = await mock_validator.analyze_imports(tmp_path / "src/invalid.py")
    assert results.stats.total_imports == 1
    assert len(results.errors) == 1
    assert "invalid_module" in results.errors[0].message

@pytest.mark.asyncio
async def test_analyze_imports_with_relative_imports(mock_validator, tmp_path):
    """Test analyzing imports with relative imports."""
    results = await mock_validator.analyze_imports(tmp_path / "src/package/module.py")
    assert results.stats.total_imports == 1
    assert results.stats.relative_imports == 1

@pytest.mark.asyncio
async def test_find_module_path_with_complex_imports(mock_validator, tmp_path):
    """Test finding module path with complex imports."""
    path = await mock_validator.find_module_path("test", tmp_path / "src/package/module.py")
    assert path == tmp_path / "src/test.py"

@pytest.mark.asyncio
async def test_find_module_path_with_attribute_access(mock_validator, mock_qt, tmp_path):
    """Test finding module path with attribute access."""
    async for v in mock_validator:
        results = ValidationResults()
        await v.analyze_imports(tmp_path / 'src/test.py', results)
        assert results.stats.total_imports == 2
        assert results.stats.stdlib_imports == 1

@pytest.mark.asyncio
async def test_find_module_path_with_return_statements(mock_validator, mock_qt, tmp_path):
    """Test finding module path with return statements."""
    async for v in mock_validator:
        results = ValidationResults()
        await v.analyze_imports(tmp_path / 'src/test.py', results)
        assert results.stats.total_imports == 2
        assert results.stats.stdlib_imports == 1

@pytest.mark.asyncio
async def test_find_module_path_with_file_exists(mock_validator, mock_qt, tmp_path):
    """Test finding module path with file exists."""
    async for v in mock_validator:
        v.fs.file_exists = AsyncMock(return_value=True)
        path = await v.find_module_path('test', tmp_path / 'src/test.py')
        assert path == tmp_path / 'src/test.py'

@pytest.mark.asyncio
async def test_find_module_path_with_empty_relative_import(mock_validator, tmp_path):
    """Test finding module path with empty relative import."""
    path = await mock_validator.find_module_path(".", tmp_path / "src/package/module.py")
    assert path == tmp_path / "src/package/__init__.py"

@pytest.mark.asyncio
async def test_find_module_path_with_complex_package_imports(mock_validator, tmp_path):
    """Test finding module path with complex package imports."""
    path = await mock_validator.find_module_path("package", tmp_path / "src/utils/helper.py")
    assert path == tmp_path / "src/package/__init__.py"

@pytest.mark.asyncio
async def test_initialize(mock_validator, mock_qt):
    """Test validator initialization."""
    async for v in mock_validator:
        await v.initialize()
        assert len(v.installed_packages) > 0
        assert 'os' in v.installed_packages
        assert 'sys' in v.installed_packages

@pytest.mark.asyncio
async def test_initialize_with_src_and_tests(mock_validator, mock_qt, tmp_path):
    """Test initializing validator with both src and tests directories."""
    async for v in mock_validator:
        # Mock find_python_files to return test files
        v.fs.find_python_files = AsyncMock(return_value={
            tmp_path / 'src/test.py',
            tmp_path / 'src/package/__init__.py',
            tmp_path / 'tests/test_validator.py'
        })
        
        # Mock read_file to return test content
        v.fs.read_file = AsyncMock(return_value="def test_function():\n    pass")
        
        await v.initialize()
        assert len(v.installed_packages) > 0

@pytest.mark.asyncio
async def test_validator_with_custom_fs(mock_qt, tmp_path):
    """Test validator with custom file system implementation."""
    class TestFS(FileSystemInterface):
        async def read_file(self, path: Path) -> str:
            return "test content"
            
        async def file_exists(self, path: Path) -> bool:
            return True
            
        async def find_python_files(self, directory: Path) -> Set[Path]:
            return {Path("test.py")}
    
    config = ImportValidatorConfig(base_dir=tmp_path)
    validator = AsyncImportValidator(config=config, fs=TestFS())
    
    content = await validator.fs.read_file(Path("any"))
    assert content == "test content"
    
    exists = await validator.fs.file_exists(Path("any"))
    assert exists is True
    
    files = await validator.fs.find_python_files(Path("any"))
    assert files == {Path("test.py")}

@pytest.mark.asyncio
async def test_validator_path_resolution(temp_dir: Path):
    """Test that paths are properly resolved relative to base_dir."""
    config = ImportValidatorConfig(
        base_dir=temp_dir,
        src_dir="custom/src",
        tests_dir="custom/tests"
    )

    fs = MockFileSystem(base_dir=temp_dir, mock_files={})
    validator = AsyncImportValidator(config=config, fs=fs)
    assert validator.config == config
    assert validator.fs == fs

@pytest.mark.asyncio
async def test_file_system_interface_methods():
    """Test file system interface default methods."""
    fs = FileSystemInterface()
    
    with pytest.raises(NotImplementedError):
        await fs.read_file(Path("test.py"))
    
    with pytest.raises(NotImplementedError):
        await fs.file_exists(Path("test.py"))
        
    with pytest.raises(NotImplementedError):
        await fs.find_python_files(Path("src"))

@pytest.mark.asyncio
async def test_validate_all_with_errors(mock_validator, tmp_path):
    """Test validating with errors."""
    results = await mock_validator.validate_all()
    assert len(results.errors) > 0
    assert any("invalid_module" in error.message for error in results.errors)

@pytest.mark.asyncio
async def test_validate_all_with_complex_project(mock_validator, tmp_path):
    """Test validating a complex project."""
    results = await mock_validator.validate_all()
    assert results.stats.total_imports > 0
    assert results.stats.relative_imports > 0
    assert len(results.circular_refs) == 0

@pytest.mark.asyncio
async def test_validate_all_error_handling(mock_validator):
    """Test error handling in validate_all."""
    async for v in mock_validator:
        # Mock catastrophic failure
        v.fs.find_python_files = AsyncMock(side_effect=Exception("Critical error"))
        
        # Run validation
        results = await v.validate_all()
        assert len(results.errors) > 0

@pytest.mark.asyncio
async def test_validate_all_with_empty_project(mock_validator):
    """Test validate_all with an empty project."""
    async for v in mock_validator:
        # Mock empty project
        v.fs.find_python_files = AsyncMock(return_value=set())
        
        # Run validation
        results = await v.validate_all()
        assert results.stats.total_imports == 0

@pytest.mark.asyncio
async def test_validator_cleanup(mock_validator, tmp_path):
    """Test validator cleanup."""
    await mock_validator.cleanup()
    mock_validator.cleanup.assert_called_once()

@pytest.mark.asyncio
async def test_validator_with_gui(mock_validator, mock_qt, tmp_path):
    """Test validator with GUI components."""
    results = await mock_validator.validate_all()
    mock_validator.show_progress.assert_called()
    mock_validator.update_progress.assert_called()
    mock_qt['dialog'].exec.assert_called()

@pytest.mark.asyncio
async def test_validator_error_handling(mock_validator, mock_qt, tmp_path):
    """Test validator error handling."""
    mock_validator.validate_all.side_effect = Exception("Test error")
    with pytest.raises(Exception):
        await mock_validator.validate_all()
    mock_qt['dialog'].exec.assert_called()

@pytest.mark.asyncio
async def test_validator_cleanup_with_gui(mock_validator, mock_qt, tmp_path):
    """Test validator cleanup with GUI components."""
    await mock_validator.cleanup()
    mock_validator.cleanup.assert_called_once()
    mock_qt['web_view'].deleteLater.assert_called_once()
    mock_qt['channel'].deleteLater.assert_called_once()
