"""Interface for file system operations."""
from pathlib import Path
from typing import Set

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