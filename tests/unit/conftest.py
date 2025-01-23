"""Test fixtures for import validator."""
import os
import pytest
from pathlib import Path
import ast

# Set QT_API to force PyQt6 usage
os.environ["QT_API"] = "pyqt6"

from src.validator.validator import AsyncImportValidator, FileSystemInterface
from src.validator.validator_types import ImportValidatorConfig, PathNormalizer
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
async def mock_validator(tmp_path: Path, mock_qt) -> AsyncGenerator[AsyncImportValidator, None]:
    """Create a mock validator for testing."""
    # Create mock file system
    mock_files = {
        str(tmp_path / 'src/test.py'): '''
import os
from src.utils import helper
''',
        str(tmp_path / 'src/empty.py'): '',
        str(tmp_path / 'src/invalid.py'): '''
import nonexistent_module
from nonexistent_package import something
from .nonexistent import stuff
''',
        str(tmp_path / 'src/package/module.py'): '''
from . import module
from .utils import helper
from ..core import base
''',
        str(tmp_path / 'src/utils/__init__.py'): '# Utils package',
        str(tmp_path / 'src/utils/helper.py'): '''
def helper_function():
    return "helper"
'''
    }
    
    # Create source and test directories
    src_dir = tmp_path / "src"
    tests_dir = tmp_path / "tests"
    src_dir.mkdir(exist_ok=True)
    tests_dir.mkdir(exist_ok=True)
    
    # Create package and utils directories
    (src_dir / "package").mkdir(exist_ok=True)
    (src_dir / "utils").mkdir(exist_ok=True)
    
    # Write the mock files
    for path, content in mock_files.items():
        file_path = Path(path)
        file_path.parent.mkdir(exist_ok=True)
        file_path.write_text(content.strip())
    
    # Create validator config
    config = ImportValidatorConfig(
        src_dir=str(src_dir),
        tests_dir=str(tests_dir),
        base_dir=str(tmp_path),
        valid_packages={"pytest", "networkx", "rich", "pydantic-settings"},
        ignore_patterns={"*.pyc", "__pycache__/*"},
        complexity_threshold=10.0,
        max_edges_per_diagram=100
    )
    
    # Create mock file system
    fs = MockFileSystem(str(tmp_path), mock_files)
    
    # Create validator with mock file system
    validator = AsyncImportValidator(config=config, fs=fs)
    
    # Mock Qt-related methods
    validator.show_progress = AsyncMock()
    validator.update_progress = AsyncMock()
    validator.cleanup = AsyncMock()
    
    yield validator
    
    # Clean up
    await validator.cleanup()

@pytest.fixture
async def mock_qt(monkeypatch):
    """Mock Qt components for testing."""
    os.environ['QT_API'] = 'pyqt6'
    
    # Create a real event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Mock Qt components
    mock_app = Mock()
    mock_web_view = Mock()
    mock_channel = Mock()
    mock_dialog = Mock()
    mock_dialog.exec = Mock()
    mock_dialog.setValue = Mock()
    mock_dialog.setLabelText = Mock()
    
    # Mock QApplication
    monkeypatch.setattr('src.validator.qt_app.QApplication', Mock(return_value=mock_app))
    monkeypatch.setattr('src.validator.qt_app.QMainWindow', Mock())
    monkeypatch.setattr('src.validator.qt_app.QWebEngineView', Mock(return_value=mock_web_view))
    monkeypatch.setattr('src.validator.qt_app.QWebChannel', Mock(return_value=mock_channel))
    monkeypatch.setattr('src.validator.qt_app.QProgressDialog', Mock(return_value=mock_dialog))
    
    yield {
        'app': mock_app,
        'web_view': mock_web_view,
        'channel': mock_channel,
        'dialog': mock_dialog,
        'loop': loop
    }
    
    # Cleanup
    loop.close() 