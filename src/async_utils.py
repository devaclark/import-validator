"""Async utilities for import validator."""
import ast
from functools import lru_cache
from pathlib import Path
from typing import Optional, Set
import aiofiles
import asyncio
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

# Thread pool for CPU-bound operations
_ast_parser_pool = ThreadPoolExecutor(max_workers=min(32, multiprocessing.cpu_count() * 2))


async def read_file_async(file_path: Path) -> str:
    """Read a file asynchronously."""
    async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
        return await f.read()


def parse_ast_threaded(source: str, filename: str = '<unknown>') -> ast.AST:
    """Parse Python source into AST in a separate thread."""
    return ast.parse(source, filename=filename)


async def parse_file_async(file_path: Path) -> ast.AST:
    """Read and parse a Python file asynchronously."""
    content = await read_file_async(file_path)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _ast_parser_pool,
        parse_ast_threaded,
        content,
        str(file_path)
    )


@lru_cache(maxsize=1000)
def get_python_files_cached(directory: Path, ignore_patterns: Set[str]) -> Set[Path]:
    """Get all Python files in a directory (cached version)."""
    python_files = set()
    try:
        for item in directory.rglob('*.py'):
            # Check if any parent directory matches ignore patterns
            if not any(p in ignore_patterns for p in item.parts):
                python_files.add(item)
    except Exception:
        pass
    return python_files


async def find_python_files_async(
    directory: Path,
    ignore_patterns: Optional[Set[str]] = None
) -> Set[Path]:
    """Find all Python files in a directory asynchronously."""
    if ignore_patterns is None:
        ignore_patterns = {'__pycache__', '*.pyc', '*.pyo'}
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,  # Use default executor
        get_python_files_cached,
        directory,
        frozenset(ignore_patterns)  # Make hashable for caching
    )


class AsyncCache:
    """Simple async-aware cache with TTL support."""
    
    def __init__(self, ttl_seconds: int = 3600):
        self._cache = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[object]:
        """Get a value from the cache."""
        async with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if (asyncio.get_event_loop().time() - timestamp) < self._ttl:
                    return value
                del self._cache[key]
        return None
    
    async def set(self, key: str, value: object) -> None:
        """Set a value in the cache."""
        async with self._lock:
            self._cache[key] = (value, asyncio.get_event_loop().time())
    
    async def clear(self) -> None:
        """Clear the cache."""
        async with self._lock:
            self._cache.clear() 