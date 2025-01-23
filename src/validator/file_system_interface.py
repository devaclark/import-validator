"""File system interface for the import validator."""
from pathlib import Path
from typing import Set
from .async_utils import read_file_async, file_exists_async, find_python_files_async

class FileSystemInterface:
    """Interface for file system operations."""
    async def read_file(self, path: Path) -> str:
        """Read a file's contents.
        
        Args:
            path: Path to the file to read
            
        Returns:
            The file's contents as a string
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            IOError: If there's an error reading the file
        """
        raise NotImplementedError
        
    async def file_exists(self, path: Path) -> bool:
        """Check if a file exists.
        
        Args:
            path: Path to check
            
        Returns:
            True if the file exists, False otherwise
        """
        raise NotImplementedError
        
    async def find_python_files(self, directory: Path) -> Set[Path]:
        """Find all Python files in a directory.
        
        Args:
            directory: Directory to search in
            
        Returns:
            Set of paths to Python files
        """
        raise NotImplementedError

class DefaultFileSystem(FileSystemInterface):
    """Default implementation of file system operations."""
    async def read_file(self, path: Path) -> str:
        return await read_file_async(path)
        
    async def file_exists(self, path: Path) -> bool:
        return await file_exists_async(path)
        
    async def find_python_files(self, directory: Path) -> Set[Path]:
        return await find_python_files_async(directory) 