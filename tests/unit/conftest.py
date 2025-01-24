"""Test fixtures for import validator."""
import os
import pytest
from pathlib import Path
import ast

# Set QT_API to force PyQt6 usage
os.environ["QT_API"] = "pyqt6"

from src.validator.validator import AsyncImportValidator, FileSystemInterface
from src.validator.validator_types import ImportValidatorConfig, PathNormalizer, ValidationResults, ImportStats
import asyncio
from typing import Dict, Set, AsyncGenerator, Union, List
import networkx as nx
import logging
from unittest.mock import Mock, AsyncMock
import qasync


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def mock_requirements(temp_dir):
    """Create a mock requirements.txt file."""
    requirements = temp_dir / "requirements.txt"
    content = """
pytest>=7.0.0
networkx>=2.6.0
rich>=10.0.0
pydantic-settings>=2.0.0
    """
    requirements.write_text(content)
    return requirements


@pytest.fixture
def mock_pyproject(temp_dir):
    """Create a mock pyproject.toml file."""
    pyproject = temp_dir / "pyproject.toml"
    content = """
[tool.poetry.dependencies]
networkx = "^2.5"
rich = "^10.0.0"
pydantic = "^1.8.2"
"""
    pyproject.write_text(content)
    return pyproject


@pytest.fixture
def test_files(temp_dir):
    """Create test Python files with various import patterns."""
    src_dir = temp_dir / "src"
    tests_dir = temp_dir / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()

    # Create test files
    files = {
        'module_a': src_dir / "module_a.py",
        'module_b': src_dir / "module_b.py",
        'module_c': src_dir / "module_c.py",
        'module_d': src_dir / "module_d.py",
        'module_e': src_dir / "module_e.py",
    }

    # Module A: Basic imports
    files['module_a'].write_text("""
import sys
import os.path
from typing import List, Dict
    """)

    # Module B: Unused and invalid imports
    files['module_b'].write_text("""
import os  # unused
import json  # unused
from src.module_a import some_function  # invalid
    """)

    # Module C: Circular import with D
    files['module_c'].write_text("""
from src.module_d import d_function
def c_function():
    return "C"
    """)

    # Module D: Circular import with C
    files['module_d'].write_text("""
from src.module_c import c_function
def d_function():
    return "D"
    """)

    # Module E: Complex imports
    files['module_e'].write_text("""
import sys
import os
from typing import (
    List,
    Dict,
    Optional,
    Union
)
from pathlib import Path
    """)

    return temp_dir


@pytest.fixture
async def mock_read_file(request, monkeypatch, mock_file_content):
    """Mock the read_file_async function."""
    from unittest.mock import AsyncMock
    import ast
    
    async def mock_read(file_path, *args, **kwargs):
        print(f"\nMock read called for {file_path}")
        print(f"Test name: {request.node.name}")
        print(f"Mock content: {mock_file_content}")
        
        if request.node.name == "test_analyze_imports_with_read_error":
            raise FileNotFoundError(f"File not found: {file_path}")
        return mock_file_content
    
    # Create async mock
    mock = AsyncMock(side_effect=mock_read)
    
    # Patch all relevant functions
    monkeypatch.setattr('src.validator.validator.read_file_async', mock)
    monkeypatch.setattr('src.validator.async_utils.read_file_async', mock)
    monkeypatch.setattr('src.validator.validator.AsyncImportValidator.read_file', mock)
    
    # For parse error test, we need to patch ast.parse directly
    if request.node.name == "test_analyze_imports_with_parse_error":
        def mock_ast_parse(content, *args, **kwargs):
            raise SyntaxError(f"Invalid syntax in test file: {content}")
        monkeypatch.setattr('ast.parse', mock_ast_parse)
    
    await asyncio.sleep(0)  # Allow any pending async operations to complete
    return mock 


class MockFileSystem:
    """Mock file system for testing."""

    def __init__(self, base_dir: str, mock_files: Dict[str, str]):
        """Initialize mock file system.

        Args:
            base_dir: Base directory for mock files
            mock_files: Dictionary of mock files and their contents
        """
        self.base_dir = Path(base_dir)
        self.mock_files = {str(Path(k)): v.strip() for k, v in mock_files.items()}

    async def read_file(self, path: Union[str, Path]) -> str:
        """Read a file from the mock file system.

        Args:
            path: Path to the file.

        Returns:
            str: Contents of the file.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        # Convert path to absolute path if it's relative
        path = Path(path)
        if not path.is_absolute():
            path = self.base_dir / path
        
        # Normalize path to use forward slashes
        path_str = str(path).replace('\\', '/')
        if path_str in self.mock_files:
            return self.mock_files[path_str]
        
        # Try with base_dir
        base_path_str = str(self.base_dir / path).replace('\\', '/')
        if base_path_str in self.mock_files:
            return self.mock_files[base_path_str]
        
        raise FileNotFoundError(f"File not found: {path_str}")

    async def file_exists(self, path: Union[str, Path]) -> bool:
        """Check if a file exists in the mock file system.

        Args:
            path: Path to check.

        Returns:
            bool: True if the file exists, False otherwise.
        """
        # Convert path to absolute path if it's relative
        path = Path(path)
        if not path.is_absolute():
            path = self.base_dir / path
        
        # Normalize path to use forward slashes
        path_str = str(path).replace('\\', '/')
        if path_str in self.mock_files:
            return True
        
        # Try with base_dir
        base_path_str = str(self.base_dir / path).replace('\\', '/')
        return base_path_str in self.mock_files

    async def find_python_files(self, directory: Union[str, Path]) -> Set[Path]:
        """Find all Python files in a directory.

        Args:
            directory: Directory to search.

        Returns:
            Set[Path]: Set of Python file paths.
        """
        # Convert directory to absolute path if it's relative
        directory = Path(directory)
        if not directory.is_absolute():
            directory = self.base_dir / directory
        
        # Normalize directory path to use forward slashes
        directory_str = str(directory).replace('\\', '/')
        python_files = set()
        
        for path in self.mock_files.keys():
            path = Path(path)
            if str(path).startswith(directory_str) and str(path).endswith('.py'):
                python_files.add(path)
        
        return python_files

@pytest.fixture
def mock_files(test_files):
    """Create mock file contents."""
    return {
        'src/module_a.py': '''
            import sys
            import os.path
            from typing import List, Dict
        ''',
        'src/module_b.py': '''
            import os  # unused
            import json  # unused
            from src.module_a import some_function  # invalid
        ''',
        'src/module_c.py': '''
            from src.module_d import d_function
            def c_function():
                return "C"
        ''',
        'src/module_d.py': '''
            from src.module_c import c_function
            def d_function():
                return "D"
        ''',
        'src/module_e.py': '''
            import sys
            import os
            from typing import (
                List,
                Dict,
                Optional,
                Union
            )
            from pathlib import Path
        ''',
        'src/empty.py': '',
        'src/parse_error.py': '''
            def invalid_syntax:
                pass
        ''',
        'src/utils/__init__.py': '# Utils package',
        'src/utils/helper.py': '''
            def helper_function():
                return "helper"
        ''',
        'src/test.py': '''
            import os
            from src.utils import helper
        ''',
        'src/package/module.py': '''
            from ..test import test_function
            from . import package_function
            from .submodule import sub_function
        ''',
        'src/package/__init__.py': '''
            def package_function():
                pass
        ''',
        'src/__init__.py': '# Package init file',
        'src/test.py': '''
            def test_function():
                pass
        ''',
        'src/package/subpackage/module.py': '''
            from ..test import test_function
        '''
    }

@pytest.fixture
def mock_validator(tmp_path: Path, mock_qt) -> AsyncMock:
    """Create a mock validator for testing."""
    # Create a mock validator with async methods
    mock = AsyncMock()
    
    # Setup default behaviors for async methods
    results = ValidationResults()
    results.stats = ImportStats()
    results.stats.complexity_score = 0.0
    results.circular_references = {}
    
    # Setup mock methods with proper return values
    mock.validate_all = AsyncMock(return_value=results)
    mock.analyze_imports = AsyncMock(return_value=ImportStats())
    mock.find_module_path = AsyncMock(return_value="test/path")
    mock.initialize = AsyncMock()
    mock.cleanup = AsyncMock()
    
    # Make it iterable for async for loops
    mock.__aiter__ = AsyncMock(return_value=mock)
    mock.__anext__ = AsyncMock(side_effect=StopAsyncIteration)
    
    # Return the mock directly
    return mock

@pytest.fixture
async def mock_qt(monkeypatch):
    """Mock Qt components."""
    # Create a real event loop for testing
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
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
    
    # Create a dictionary with all mock components
    mock_dict = {
        'app': mock_app,
        'window': mock_window,
        'web_view': mock_web_view,
        'channel': mock_channel,
        'loop': loop
    }
    
    # Mock qasync.QEventLoop
    monkeypatch.setattr('qasync.QEventLoop', Mock(return_value=loop))
    
    yield mock_dict
    
    # Cleanup
    loop.close() 