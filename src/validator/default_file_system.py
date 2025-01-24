"""Default implementation of file system operations."""
from pathlib import Path
from typing import Set

from .file_system_interface import FileSystemInterface
from .async_utils import read_file_async, file_exists_async, find_python_files_async

class DefaultFileSystem(FileSystemInterface):
    """Default implementation of file system operations."""
    async def read_file(self, path: Path) -> str:
        """Read a file's contents.
        
        Args:
            path: Path to the file to read
            
        Returns:
            The file's contents as a string
        """
        # Ensure path is a Path object
        path = Path(str(path))
        return await read_file_async(path)
        
    async def file_exists(self, path: Path) -> bool:
        """Check if a file exists.
        
        Args:
            path: Path to check
            
        Returns:
            True if the file exists, False otherwise
        """
        # Ensure path is a Path object
        path = Path(str(path))
        return await file_exists_async(path)
        
    async def find_python_files(self, directory: Path) -> Set[Path]:
        """Find all Python files in a directory.
        
        Args:
            directory: Directory to search in
            
        Returns:
            Set of paths to Python files
        """
        # Ensure directory is a Path object
        directory = Path(str(directory))
        return await find_python_files_async(directory) 