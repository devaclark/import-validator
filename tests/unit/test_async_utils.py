"""Tests for async utilities."""
import pytest
import ast
import asyncio
from pathlib import Path
from src.validator.async_utils import (
    read_file_async,
    parse_file_async,
    parse_ast_threaded,
    get_python_files_cached,
    AsyncCache,
    find_python_files_async,
    file_exists
)
from unittest.mock import Mock
from unittest.mock import patch


@pytest.fixture
def test_file(tmp_path):
    """Create a test file with known content."""
    file_path = tmp_path / "test.py"
    content = "# Test file\nx = 1\ny = 2\n"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def test_file_with_imports(tmp_path):
    """Create a test file with imports."""
    file_path = tmp_path / "test_imports.py"
    content = "x = 1\n"
    file_path.write_text(content)
    return file_path


@pytest.mark.asyncio
async def test_read_file_async(test_file):
    """Test reading a file asynchronously."""
    test_content = "# Test file\nx = 1\ny = 2\n"
    content = await read_file_async(test_file)
    assert content == test_content


@pytest.mark.asyncio
async def test_read_file_async_unicode(test_file):
    """Test reading a file with unicode content."""
    test_content = "# Test file\nx = 1\ny = 2\n"
    content = await read_file_async(test_file)
    assert content == test_content


@pytest.mark.asyncio
async def test_parse_ast_threaded():
    """Test parsing Python source into AST in a thread."""
    source = """
def hello():
    print('Hello, World!')
    return 42
"""
    tree = await parse_ast_threaded(source)
    assert isinstance(tree, ast.AST)
    
    # Check that the AST contains the expected nodes
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == 'hello'
        for node in ast.walk(tree)
    )


@pytest.mark.asyncio
async def test_parse_file_async(test_file_with_imports):
    """Test parsing a Python file into an AST."""
    tree = await parse_file_async(test_file_with_imports)
    assert isinstance(tree, ast.Module)
    assert isinstance(tree.body[0], ast.Assign)


def test_get_python_files_cached(temp_dir):
    """Test finding Python files with caching."""
    # Create some Python files
    (temp_dir / "a.py").touch()
    (temp_dir / "b.py").touch()
    (temp_dir / "test").mkdir()
    (temp_dir / "test" / "c.py").touch()
    
    # Create some non-Python files and ignored patterns
    (temp_dir / "d.txt").touch()
    pycache_dir = temp_dir / "__pycache__"
    pycache_dir.mkdir()
    (pycache_dir / "e.pyc").touch()
    
    files = get_python_files_cached(temp_dir, {"__pycache__"})
    
    # Should find all .py files except those in __pycache__
    assert len(files) == 3
    assert temp_dir / "a.py" in files
    assert temp_dir / "b.py" in files
    assert temp_dir / "test" / "c.py" in files


def test_get_python_files_cached_empty_dir(temp_dir):
    """Test finding Python files in an empty directory."""
    files = get_python_files_cached(temp_dir, set())
    assert len(files) == 0


def test_get_python_files_cached_multiple_ignore_patterns(temp_dir):
    """Test finding Python files with multiple ignore patterns."""
    # Create test files
    (temp_dir / "a.py").touch()
    (temp_dir / "venv").mkdir()
    (temp_dir / "venv" / "b.py").touch()
    (temp_dir / ".git").mkdir()
    (temp_dir / ".git" / "c.py").touch()
    
    files = get_python_files_cached(temp_dir, {"venv", ".git"})
    
    assert len(files) == 1
    assert temp_dir / "a.py" in files 


@pytest.mark.asyncio
async def test_async_cache():
    """Test AsyncCache functionality."""
    cache = AsyncCache(ttl_seconds=1)
    
    # Test setting and getting a value
    await cache.set("key1", "value1")
    value = await cache.get("key1")
    assert value == "value1"
    
    # Test getting a non-existent key
    value = await cache.get("nonexistent")
    assert value is None
    
    # Test TTL expiration
    await cache.set("key2", "value2")
    await asyncio.sleep(1.1)  # Wait for TTL to expire
    value = await cache.get("key2")
    assert value is None
    
    # Test clearing the cache
    await cache.set("key3", "value3")
    await cache.clear()
    value = await cache.get("key3")
    assert value is None


@pytest.mark.asyncio
async def test_async_cache_concurrent_access():
    """Test AsyncCache with concurrent access."""
    cache = AsyncCache()
    
    async def write_task(key: str, value: str):
        await cache.set(key, value)
        await asyncio.sleep(0.1)  # Simulate some work
        return await cache.get(key)
    
    # Run multiple tasks concurrently
    tasks = [
        write_task(f"key{i}", f"value{i}")
        for i in range(5)
    ]
    results = await asyncio.gather(*tasks)
    
    # Check results
    assert results == ["value0", "value1", "value2", "value3", "value4"] 


@pytest.mark.asyncio
async def test_find_python_files_async(temp_dir):
    """Test finding Python files asynchronously."""
    # Create test files
    (temp_dir / "a.py").touch()
    (temp_dir / "b.py").touch()
    (temp_dir / "test").mkdir()
    (temp_dir / "test" / "c.py").touch()
    (temp_dir / "d.txt").touch()
    
    # Create ignored files
    (temp_dir / "__pycache__").mkdir()
    (temp_dir / "__pycache__" / "e.pyc").touch()
    (temp_dir / ".git").mkdir()
    (temp_dir / ".git" / "f.py").touch()
    
    # Test without ignore patterns
    files = await find_python_files_async(temp_dir)
    assert len(files) == 4  # a.py, b.py, c.py, and f.py
    
    # Test with ignore patterns
    files = await find_python_files_async(temp_dir, ["__pycache__", ".git"])
    assert len(files) == 3  # a.py, b.py, and c.py
    
    # Test with empty directory
    empty_dir = temp_dir / "empty"
    empty_dir.mkdir()
    files = await find_python_files_async(empty_dir)
    assert len(files) == 0
    
    # Test with non-existent directory
    files = await find_python_files_async(temp_dir / "nonexistent")
    assert len(files) == 0
    
    # Test with None directory
    files = await find_python_files_async(None)
    assert len(files) == 0


@pytest.mark.asyncio
async def test_parse_file_async_error(temp_dir):
    """Test parsing a file with errors."""
    # Create a file with invalid Python syntax
    test_file = temp_dir / "invalid.py"
    test_file.write_text("def invalid_syntax(:")
    
    # Try to parse the file
    tree = await parse_file_async(test_file)
    assert tree is None
    
    # Test with non-existent file
    tree = await parse_file_async(temp_dir / "nonexistent.py")
    assert tree is None


@pytest.mark.asyncio
async def test_parse_file_async_with_encoding_error(temp_dir):
    """Test parsing a file with encoding issues."""
    # Create a file with non-UTF-8 content
    test_file = temp_dir / "encoding.py"
    with open(test_file, 'wb') as f:
        f.write(b"# -*- coding: latin-1 -*-\ndef func():\n    # \xff\n    pass\n")
    
    # Try to parse the file
    tree = await parse_file_async(test_file)
    assert isinstance(tree, ast.AST) 


@pytest.mark.asyncio
async def test_find_python_files_async_with_glob_patterns(temp_dir):
    """Test finding Python files with glob patterns."""
    # Create test files
    (temp_dir / "a.py").touch()
    (temp_dir / "b.py").touch()
    (temp_dir / "test").mkdir()
    (temp_dir / "test" / "c.py").touch()
    (temp_dir / "d.txt").touch()
    
    # Create ignored files
    (temp_dir / "__pycache__").mkdir()
    (temp_dir / "__pycache__" / "e.pyc").touch()
    (temp_dir / ".git").mkdir()
    (temp_dir / ".git" / "f.py").touch()
    
    # Test with file extensions
    files = await find_python_files_async(temp_dir, [r"\.pyc$", r"\.txt$"])
    assert len(files) == 4  # a.py, b.py, c.py, and f.py
    
    # Test with directory patterns
    files = await find_python_files_async(temp_dir, [r"__pycache__", r"\.git"])
    assert len(files) == 3  # a.py, b.py, and c.py


def test_get_python_files_cached_with_glob_patterns(temp_dir):
    """Test finding Python files with glob patterns."""
    # Create test files
    (temp_dir / "a.py").touch()
    (temp_dir / "b.py").touch()
    (temp_dir / "test").mkdir()
    (temp_dir / "test" / "c.py").touch()
    (temp_dir / "d.txt").touch()
    
    # Create ignored files
    (temp_dir / "__pycache__").mkdir()
    (temp_dir / "__pycache__" / "e.pyc").touch()
    (temp_dir / ".git").mkdir()
    (temp_dir / ".git" / "f.py").touch()
    
    # Test with file extensions
    files = get_python_files_cached(temp_dir, [r"\.pyc$", r"\.txt$"])
    assert len(files) == 4  # a.py, b.py, c.py, and f.py
    
    # Test with directory patterns
    files = get_python_files_cached(temp_dir, [r"/test/"])
    assert len(files) == 4  # a.py, b.py, c.py, and f.py 


def test_get_python_files_cached_with_cache_hit(temp_dir):
    """Test that get_python_files_cached uses the cache when available."""
    # Create test files
    (temp_dir / "a.py").touch()
    (temp_dir / "b.py").touch()
    
    # First call to populate cache
    files1 = get_python_files_cached(temp_dir, [])
    assert len(files1) == 2
    
    # Second call should use cache
    files2 = get_python_files_cached(temp_dir, [])
    assert len(files2) == 2
    assert files1 == files2


@pytest.mark.asyncio
async def test_find_python_files_async_with_ignored_files(temp_dir):
    """Test that find_python_files_async correctly ignores files."""
    # Create test files
    (temp_dir / "a.py").touch()
    (temp_dir / "b.py").touch()
    (temp_dir / "test.py").touch()
    
    # Test with ignore pattern that matches a file
    files = await find_python_files_async(temp_dir, ["test.py"])
    assert len(files) == 2  # a.py and b.py
    assert all(file.name != "test.py" for file in files)


@pytest.mark.asyncio
async def test_file_exists_error():
    """Test file_exists with permission error."""
    path = Path('nonexistent/path')
    with patch.object(Path, 'exists', side_effect=PermissionError):
        assert not await file_exists(path) 