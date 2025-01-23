"""Common test fixtures."""
import pytest
from pathlib import Path
import tempfile
import shutil


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_files(temp_dir):
    """Create test Python files with various import patterns."""
    src_dir = temp_dir / "src"
    tests_dir = temp_dir / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()
    
    files = {}
    
    # Module A - Basic module with function definition
    module_a = src_dir / "module_a.py"
    module_a.write_text("""
def function_a():
    return "Hello from A"
    """.strip())
    files['module_a'] = module_a
    
    # Module B - Unused imports
    module_b = src_dir / "module_b.py"
    module_b.write_text("""
import os
import json
from module_a import function_a

def function_b():
    return function_a()
    """.strip())
    files['module_b'] = module_b
    
    # Module C - Invalid imports
    module_c = src_dir / "module_c.py"
    module_c.write_text("""
import non_existent_module
from another_fake_module import something

def function_c():
    return "Hello from C"
    """.strip())
    files['module_c'] = module_c
    
    # Module D and E - Circular imports
    module_d = src_dir / "module_d.py"
    module_e = src_dir / "module_e.py"
    
    module_d.write_text("""
from module_e import function_e

def function_d():
    return function_e()
    """.strip())
    
    module_e.write_text("""
from module_d import function_d

def function_e():
    return function_d()
    """.strip())
    
    files['module_d'] = module_d
    files['module_e'] = module_e
    
    # Module F and G - Relative imports
    subpkg = src_dir / "subpkg"
    subpkg.mkdir()
    
    module_f = subpkg / "module_f.py"
    module_g = subpkg / "module_g.py"
    
    module_f.write_text("""
from ..module_a import function_a
from .module_g import function_g

def function_f():
    return function_a() + function_g()
    """.strip())
    
    module_g.write_text("""
def function_g():
    return "Hello from G"
    """.strip())
    
    files['module_f'] = module_f
    files['module_g'] = module_g
    
    # Test module
    test_module = tests_dir / "test_module1.py"
    test_module.write_text("""
from src.module_a import function_a

def test_function_a():
    assert function_a() == "Hello from A"
    """.strip())
    files['test_module'] = test_module
    
    return {
        'src_dir': src_dir,
        'tests_dir': tests_dir,
        'files': files
    } 