"""Validator module for analyzing Python imports."""
import asyncio
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Union, Tuple, Any, AsyncGenerator
import ast
from collections import defaultdict
import json
from aiohttp import web
import aiohttp_cors
from aiohttp_cors import ResourceOptions, setup as setup_cors
import networkx as nx
import re
import aiofiles
import os
import pkg_resources
import uuid

from .constants import TEMPLATES_DIR
from .async_utils import find_python_files_async, parse_ast_threaded, read_file_async, file_exists_async, get_installed_packages
from .error_handling import ValidationError
from .validator_types import ImportUsage, ValidationResults, PathNormalizer, ImportInfo, ImportValidatorConfig, FileStatus, ImportRelationship
from .file_system import AsyncFileSystem

# Set up logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Create file handler
file_handler = logging.FileHandler(log_dir / "import_validator.log", mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# Create console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Known module-to-package mappings
MODULE_TO_PACKAGE = {
    'yaml': 'pyyaml',
    'PIL': 'pillow',
    'bs4': 'beautifulsoup4',
    'sklearn': 'scikit-learn',
    'cv2': 'opencv-python',
    'psycopg2': 'psycopg2-binary'
}

# Reverse mapping for package-to-module
PACKAGE_TO_MODULES = {
    'pyyaml': ['yaml'],
    'pillow': ['PIL'],
    'beautifulsoup4': ['bs4'],
    'scikit-learn': ['sklearn'],
    'opencv-python': ['cv2'],
    'psycopg2-binary': ['psycopg2']
}

class PathEncoder(json.JSONEncoder):
    """Custom JSON encoder for handling Path objects."""
    def default(self, obj):
        if isinstance(obj, Path):
            return str(obj).replace('\\', '/')
        return super().default(obj)

def json_dumps(obj) -> str:
    """Safely convert object to JSON string."""
    return json.dumps(obj, ensure_ascii=False, cls=PathEncoder)

class FileSystemInterface:
    """Interface for file system operations."""
    async def read_file(self, path: Path) -> str:
        raise NotImplementedError
        
    async def file_exists(self, path: Path) -> bool:
        raise NotImplementedError
        
    async def find_python_files(self, directory: Path) -> Set[Path]:
        raise NotImplementedError

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

class AsyncImportValidator:
    """Asynchronous import validator."""

    def __init__(self, config: ImportValidatorConfig, fs: Optional[FileSystemInterface] = None):
        """Initialize validator.

        Args:
            config: Validator configuration
            fs: Optional file system interface
        """
        self.config = config
        self.fs = fs or DefaultFileSystem()
        self.logger = logging.getLogger('import_validator')
        self.trace_id = str(uuid.uuid4())[:8]  # Generate a short trace ID
        self.validation_pass = 0  # Track validation pass number
        
        logger.debug(f"[Trace: {self.trace_id}] Initializing validator instance")
        
        # Convert paths to absolute paths and ensure they are Path objects
        self.base_dir = Path(config.base_dir).resolve()
        self.src_dir = Path(config.src_dir).resolve()
        self.tests_dir = Path(config.tests_dir).resolve() if config.tests_dir else None
        
        # Initialize path handling
        self.path_normalizer = PathNormalizer(
            src_dir=str(self.src_dir),
            tests_dir=str(self.tests_dir) if self.tests_dir else None,
            base_dir=str(self.base_dir)
        )
        
        # Track file statuses
        self.file_statuses: Dict[str, FileStatus] = {}
        self.missing_files: Set[str] = set()
        self.invalid_files: Set[str] = set()
        
        # Initialize import tracking
        self.module_definitions = {}
        self.import_graph = nx.DiGraph()
        self.import_relationships: Dict[str, ImportRelationship] = {}
        
        # Initialize package tracking
        self.stdlib_modules = set(sys.stdlib_module_names)
        self.installed_packages = self.stdlib_modules.copy()
        self.valid_packages = set()  # Track third-party packages separately
        self.package_to_modules = {}  # Track which modules each package provides

        # First, add all packages from all sources
        if hasattr(config, 'valid_packages') and config.valid_packages:
            self.installed_packages.update(config.valid_packages)
            self.valid_packages.update(config.valid_packages)
            
        if hasattr(config, 'requirements') and config.requirements:
            self.installed_packages.update(config.requirements)
            self.valid_packages.update(config.requirements)
            
        if hasattr(config, 'pyproject_dependencies') and config.pyproject_dependencies:
            self.installed_packages.update(config.pyproject_dependencies)
            self.valid_packages.update(config.pyproject_dependencies)

        # Add all installed packages to valid packages (except stdlib)
        non_stdlib_packages = self.installed_packages - self.stdlib_modules
        self.valid_packages.update(non_stdlib_packages)
        logger.debug(f"Added non-stdlib packages to valid_packages: {non_stdlib_packages}")

        # Build package-to-module mapping by inspecting each package
        for package in list(self.valid_packages):
            try:
                # First try to find the package's dist-info directory
                package_path = None
                for site_package in sys.path:
                    dist_info = Path(site_package).glob(f"{package.replace('-', '_')}-*.dist-info")
                    for d in dist_info:
                        top_level_file = d / 'top_level.txt'
                        if top_level_file.exists():
                            with open(top_level_file) as f:
                                modules = {line.strip() for line in f if line.strip()}
                                self.package_to_modules[package] = modules
                                logger.debug(f"Found modules {modules} from top_level.txt for package {package}")
                                # Add all discovered modules to both collections
                                self.installed_packages.update(modules)
                                self.valid_packages.update(modules)
                                break

                # If no top_level.txt found, try importing the package
                if package not in self.package_to_modules:
                    spec = importlib.util.find_spec(package)
                    if spec and spec.origin:
                        # Add the package name itself as a valid module
                        self.package_to_modules[package] = {package}
                        self.valid_packages.add(package)

                        # If the package has a file location, inspect it
                        package_dir = os.path.dirname(spec.origin)
                        package_name = os.path.basename(package_dir)

                        # Add the directory name if different from package
                        if package_name != package:
                            self.package_to_modules[package].add(package_name)
                            self.valid_packages.add(package_name)

                        # Look for top-level modules
                        if os.path.isdir(package_dir):
                            for item in os.listdir(package_dir):
                                # Add .py files as modules
                                if item.endswith('.py') and item != '__init__.py':
                                    module_name = item[:-3]
                                    self.package_to_modules[package].add(module_name)
                                    self.valid_packages.add(module_name)
                                # Add directories with __init__.py as modules
                                elif os.path.isdir(os.path.join(package_dir, item)):
                                    init_path = os.path.join(package_dir, item, '__init__.py')
                                    if os.path.exists(init_path):
                                        self.package_to_modules[package].add(item)
                                        self.valid_packages.add(item)

                        logger.debug(f"Found modules {self.package_to_modules[package]} provided by package {package}")

            except Exception as e:
                logger.debug(f"Error inspecting package {package}: {e}")
                continue

        # Add common package prefixes for standard library
        self.installed_packages.update({
            'typing', 'collections', 'functools', 'dataclasses',
            'pathlib', 'unittest', 'logging', 'asyncio', 'abc'
        })

        logger.debug(f"Initialized with {len(self.valid_packages)} valid packages")
        logger.debug(f"Valid packages: {sorted(self.valid_packages)}")
        logger.debug(f"Installed packages: {sorted(self.installed_packages)}")
        logger.debug(f"Package to modules mapping: {self.package_to_modules}")

        # Set source directories
        self.source_dirs = [self.src_dir]
        if self.tests_dir:
            self.source_dirs.append(self.tests_dir)
            
        self.logger.info(f"Initialized validator with base_dir: {self.base_dir}")
        self.logger.info(f"Source directory: {self.src_dir}")
        self.logger.info(f"Tests directory: {self.tests_dir}")
        self.logger.info(f"Installed packages: {len(self.installed_packages)}")
        self.logger.info(f"Using file system interface: {self.fs.__class__.__name__}")

    def get_file_status(self, file_path: str) -> FileStatus:
        """Get detailed status information about a file."""
        normalized_path = self.path_normalizer.normalize(file_path)
        if normalized_path not in self.file_statuses:
            self.file_statuses[normalized_path] = FileStatus(
                path=normalized_path,
                exists=os.path.exists(normalized_path),
                is_test=self.path_normalizer.is_test_file(normalized_path),
                import_count=len(self.import_relationships.get(normalized_path, {}).imports),
                invalid_imports=len(self.import_relationships.get(normalized_path, {}).invalid_imports),
                circular_refs=len(self.import_relationships.get(normalized_path, {}).circular_refs),
                relative_imports=len(self.import_relationships.get(normalized_path, {}).relative_imports)
            )
        return self.file_statuses[normalized_path]

    def get_import_details(self, file_path: str) -> ImportRelationship:
        """Get detailed import relationship information for a file."""
        normalized_path = self.path_normalizer.normalize(file_path)
        if normalized_path not in self.import_relationships:
            self.import_relationships[normalized_path] = ImportRelationship(
                file_path=normalized_path,
                imports=set(),
                imported_by=set(),
                invalid_imports=set(),
                relative_imports=set(),
                circular_refs=set(),
                stdlib_imports=set(),
                thirdparty_imports=set(),
                local_imports=set()
            )
        return self.import_relationships[normalized_path]

    def update_import_relationship(self, source: str, target: str, import_type: str):
        """Update import relationship tracking.
        
        Args:
            source: Source file path
            target: Target module/file path
            import_type: Type of import ('local', 'stdlib', 'thirdparty', 'relative', 'invalid')
        """
        try:
            logger.debug(f"[Trace: {self.trace_id}] Updating import relationship: {source} -> {target} ({import_type})")
            
            # Convert paths to strings if they're Path objects
            source = str(source) if isinstance(source, Path) else source
            target = str(target) if isinstance(target, Path) else target
            
            logger.debug(f"[Trace: {self.trace_id}] Converted paths to strings: {source} -> {target}")
            
            # Get or create relationship object
            if source not in self.import_relationships:
                logger.debug(f"[Trace: {self.trace_id}] Creating new import relationship for {source}")
                self.import_relationships[source] = ImportRelationship(
                    file_path=source,
                    imports=set(),
                    imported_by=set(),
                    invalid_imports=set(),
                    relative_imports=set(),
                    circular_refs=set(),
                    stdlib_imports=set(),
                    thirdparty_imports=set(),
                    local_imports=set()
                )
                
            relationship = self.import_relationships[source]
            logger.debug(f"[Trace: {self.trace_id}] Retrieved relationship object for {source}")
            
            # Update appropriate sets based on import type
            relationship.imports.add(target)
            logger.debug(f"[Trace: {self.trace_id}] Added {target} to imports set for {source}")
            
            if import_type == 'invalid':
                relationship.invalid_imports.add(target)
                logger.debug(f"[Trace: {self.trace_id}] Added {target} to invalid_imports set for {source}")
            elif import_type == 'relative':
                relationship.relative_imports.add(target)
                logger.debug(f"[Trace: {self.trace_id}] Added {target} to relative_imports set for {source}")
            elif import_type == 'stdlib':
                relationship.stdlib_imports.add(target)
                logger.debug(f"[Trace: {self.trace_id}] Added {target} to stdlib_imports set for {source}")
            elif import_type == 'thirdparty':
                relationship.thirdparty_imports.add(target)
                logger.debug(f"[Trace: {self.trace_id}] Added {target} to thirdparty_imports set for {source}")
            elif import_type == 'local':
                relationship.local_imports.add(target)
                logger.debug(f"[Trace: {self.trace_id}] Added {target} to local_imports set for {source}")
                
            # Update imported_by relationship for local imports
            if import_type in ('local', 'relative'):
                if target not in self.import_relationships:
                    logger.debug(f"[Trace: {self.trace_id}] Creating new import relationship for target {target}")
                    self.import_relationships[target] = ImportRelationship(
                        file_path=target,
                        imports=set(),
                        imported_by=set(),
                        invalid_imports=set(),
                        relative_imports=set(),
                        circular_refs=set(),
                        stdlib_imports=set(),
                        thirdparty_imports=set(),
                        local_imports=set()
                    )
                self.import_relationships[target].imported_by.add(source)
                logger.debug(f"[Trace: {self.trace_id}] Added {source} to imported_by set for {target}")
                
        except Exception as e:
            logger.error(f"[Trace: {self.trace_id}] Error updating import relationship: {e}", exc_info=True)
            # Don't re-raise to avoid breaking the import analysis process

    def get_node_color(self, file_path: str) -> str:
        """Get visualization color for a node based on its status."""
        status = self.get_file_status(file_path)
        if not status.exists:
            return "#ff6b6b"  # Red for missing files
        if status.is_test:
            return "#4ecdc4"  # Teal for test files
        if status.invalid_imports > 0:
            return "#ffe66d"  # Yellow for files with invalid imports
        if status.circular_refs > 0:
            return "#ff9f43"  # Orange for files in circular references
        return "#51cf66"  # Green for normal source files

    def get_edge_color(self, source: str, target: str) -> str:
        """Get visualization color for an edge based on import type."""
        source_rel = self.get_import_details(source)
        if target in source_rel.invalid_imports:
            return "#ff6b6b"  # Red for invalid imports
        if target in source_rel.relative_imports:
            return "#ff9f43"  # Orange for relative imports
        if target in source_rel.stdlib_imports:
            return "#4ecdc4"  # Teal for stdlib imports
        if target in source_rel.thirdparty_imports:
            return "#ffe66d"  # Yellow for third-party imports
        return "#51cf66"  # Green for local imports

    def get_node_details(self, file_path: str) -> Dict[str, Any]:
        """Get detailed information about a node for the details panel."""
        status = self.get_file_status(file_path)
        relationship = self.get_import_details(file_path)
        
        return {
            "path": file_path,
            "exists": status.exists,
            "type": "Test File" if status.is_test else "Source File",
            "status": "Missing" if not status.exists else "Valid",
            "imports": {
                "total": status.import_count,
                "invalid": len(relationship.invalid_imports),
                "relative": len(relationship.relative_imports),
                "stdlib": len(relationship.stdlib_imports),
                "thirdparty": len(relationship.thirdparty_imports),
                "local": len(relationship.local_imports)
            },
            "imported_by": list(relationship.imported_by),
            "circular_references": list(relationship.circular_refs),
            "issues": self._get_file_issues(file_path)
        }

    def _get_file_issues(self, file_path: str) -> List[Dict[str, str]]:
        """Get list of issues for a file."""
        issues = []
        status = self.get_file_status(file_path)
        relationship = self.get_import_details(file_path)
        
        if not status.exists:
            issues.append({
                "type": "error",
                "message": "File does not exist"
            })
        
        if relationship.invalid_imports:
            issues.append({
                "type": "error",
                "message": f"Invalid imports: {', '.join(relationship.invalid_imports)}"
            })
            
        if relationship.circular_refs:
            issues.append({
                "type": "warning",
                "message": f"Circular references detected: {', '.join(str(ref) for ref in relationship.circular_refs)}"
            })
            
        if relationship.relative_imports:
            issues.append({
                "type": "info",
                "message": f"Uses relative imports: {', '.join(relationship.relative_imports)}"
            })
            
        return issues

    async def initialize(self) -> None:
        """Initialize validator by finding Python files and extracting imports."""
        logger.debug(f"Initializing validator for project: {self.config.base_dir}")
        
        # Initialize installed packages with standard library
        self.installed_packages = set(sys.stdlib_module_names)
        
        # Add packages from all sources
        if self.config.valid_packages:
            self.installed_packages.update(self.config.valid_packages)
        if self.config.requirements:
            self.installed_packages.update(self.config.requirements)
        if self.config.pyproject_dependencies:
            self.installed_packages.update(self.config.pyproject_dependencies)
            
        logger.debug(f"Initialized validator with {len(self.installed_packages)} packages")
        
        # Initialize caches
        self.import_cache = {}
        self.ast_cache = {}
        
        # Ensure paths are Path objects
        if isinstance(self.src_dir, str):
            self.src_dir = Path(self.src_dir)
        if isinstance(self.tests_dir, str):
            self.tests_dir = Path(self.tests_dir)
        if isinstance(self.base_dir, str):
            self.base_dir = Path(self.base_dir)
            
        # Ensure paths are absolute
        self.src_dir = self.src_dir.resolve()
        if self.tests_dir:
            self.tests_dir = self.tests_dir.resolve()
        self.base_dir = self.base_dir.resolve()
        
        logger.debug(f"Using base_dir: {self.base_dir}")
        logger.debug(f"Using src_dir: {self.src_dir}")
        logger.debug(f"Using tests_dir: {self.tests_dir}")
        
        # Initialize path normalizer
        self.path_normalizer = PathNormalizer(
            src_dir=str(self.src_dir),
            tests_dir=str(self.tests_dir) if self.tests_dir else None,
            base_dir=str(self.base_dir)
        )
        
        # Track file statuses
        self.file_statuses: Dict[str, FileStatus] = {}
        self.missing_files: Set[str] = set()
        self.invalid_files: Set[str] = set()
        
        # Initialize import tracking
        self.module_definitions = {}
        self.import_graph = nx.DiGraph()
        self.import_relationships: Dict[str, ImportRelationship] = {}
        
        # Initialize package tracking
        self.stdlib_modules = set(sys.stdlib_module_names)
        self.installed_packages = self.stdlib_modules.copy()
        self.valid_packages = set()  # Track third-party packages separately

        # Add packages from all sources
        if hasattr(self.config, 'valid_packages') and self.config.valid_packages:
            self.installed_packages.update(self.config.valid_packages)
            self.valid_packages.update(self.config.valid_packages)
        if hasattr(self.config, 'requirements') and self.config.requirements:
            self.installed_packages.update(self.config.requirements)
            self.valid_packages.update(self.config.requirements)
        if hasattr(self.config, 'pyproject_dependencies') and self.config.pyproject_dependencies:
            self.installed_packages.update(self.config.pyproject_dependencies)
            self.valid_packages.update(self.config.pyproject_dependencies)

        # Add common package prefixes for standard library
        self.installed_packages.update({
            'typing', 'collections', 'functools', 'dataclasses',
            'pathlib', 'unittest', 'logging', 'asyncio', 'abc'
        })

        # Try importing each package to find its actual import name
        for package in list(self.valid_packages):
            try:
                module = importlib.import_module(package)
                # If the module was imported successfully, check if it provides other import names
                if hasattr(module, '__file__'):
                    module_dir = os.path.dirname(module.__file__)
                    # Add the actual import name to installed_packages
                    import_name = os.path.basename(module_dir)
                    if import_name != package:
                        logger.debug(f"Adding import name {import_name} for package {package}")
                        self.installed_packages.add(import_name)
                        self.valid_packages.add(import_name)
            except ImportError:
                continue

        logger.debug(f"Initialized with {len(self.valid_packages)} valid packages")
        logger.debug(f"Valid packages: {sorted(self.valid_packages)}")

        # Set source directories
        self.source_dirs = [self.src_dir]
        if self.tests_dir:
            self.source_dirs.append(self.tests_dir)
            
        self.logger.info(f"Initialized validator with base_dir: {self.base_dir}")
        self.logger.info(f"Source directory: {self.src_dir}")
        self.logger.info(f"Tests directory: {self.tests_dir}")
        self.logger.info(f"Installed packages: {len(self.installed_packages)}")

    def get_file_status(self, file_path: str) -> FileStatus:
        """Get detailed status information about a file."""
        normalized_path = self.path_normalizer.normalize(file_path)
        if normalized_path not in self.file_statuses:
            self.file_statuses[normalized_path] = FileStatus(
                path=normalized_path,
                exists=os.path.exists(normalized_path),
                is_test=self.path_normalizer.is_test_file(normalized_path),
                import_count=len(self.import_relationships.get(normalized_path, {}).imports),
                invalid_imports=len(self.import_relationships.get(normalized_path, {}).invalid_imports),
                circular_refs=len(self.import_relationships.get(normalized_path, {}).circular_refs),
                relative_imports=len(self.import_relationships.get(normalized_path, {}).relative_imports)
            )
        return self.file_statuses[normalized_path]

    def get_import_details(self, file_path: str) -> ImportRelationship:
        """Get detailed import relationship information for a file."""
        normalized_path = self.path_normalizer.normalize(file_path)
        if normalized_path not in self.import_relationships:
            self.import_relationships[normalized_path] = ImportRelationship(
                file_path=normalized_path,
                imports=set(),
                imported_by=set(),
                invalid_imports=set(),
                relative_imports=set(),
                circular_refs=set(),
                stdlib_imports=set(),
                thirdparty_imports=set(),
                local_imports=set()
            )
        return self.import_relationships[normalized_path]

    def update_import_relationship(self, source: str, target: str, import_type: str):
        """Update import relationship tracking."""
        source_rel = self.get_import_details(source)
        target_rel = self.get_import_details(target)
        
        source_rel.imports.add(target)
        target_rel.imported_by.add(source)
        
        if import_type == 'invalid':
            source_rel.invalid_imports.add(target)
        elif import_type == 'relative':
            source_rel.relative_imports.add(target)
        elif import_type == 'stdlib':
            source_rel.stdlib_imports.add(target)
        elif import_type == 'thirdparty':
            source_rel.thirdparty_imports.add(target)
        else:
            source_rel.local_imports.add(target)

    def get_node_color(self, file_path: str) -> str:
        """Get visualization color for a node based on its status."""
        status = self.get_file_status(file_path)
        if not status.exists:
            return "#ff6b6b"  # Red for missing files
        if status.is_test:
            return "#4ecdc4"  # Teal for test files
        if status.invalid_imports > 0:
            return "#ffe66d"  # Yellow for files with invalid imports
        if status.circular_refs > 0:
            return "#ff9f43"  # Orange for files in circular references
        return "#51cf66"  # Green for normal source files

    def get_edge_color(self, source: str, target: str) -> str:
        """Get visualization color for an edge based on import type."""
        source_rel = self.get_import_details(source)
        if target in source_rel.invalid_imports:
            return "#ff6b6b"  # Red for invalid imports
        if target in source_rel.relative_imports:
            return "#ff9f43"  # Orange for relative imports
        if target in source_rel.stdlib_imports:
            return "#4ecdc4"  # Teal for stdlib imports
        if target in source_rel.thirdparty_imports:
            return "#ffe66d"  # Yellow for third-party imports
        return "#51cf66"  # Green for local imports

    def get_node_details(self, file_path: str) -> Dict[str, Any]:
        """Get detailed information about a node for the details panel."""
        status = self.get_file_status(file_path)
        relationship = self.get_import_details(file_path)
        
        return {
            "path": file_path,
            "exists": status.exists,
            "type": "Test File" if status.is_test else "Source File",
            "status": "Missing" if not status.exists else "Valid",
            "imports": {
                "total": status.import_count,
                "invalid": len(relationship.invalid_imports),
                "relative": len(relationship.relative_imports),
                "stdlib": len(relationship.stdlib_imports),
                "thirdparty": len(relationship.thirdparty_imports),
                "local": len(relationship.local_imports)
            },
            "imported_by": list(relationship.imported_by),
            "circular_references": list(relationship.circular_refs),
            "issues": self._get_file_issues(file_path)
        }

    def _get_file_issues(self, file_path: str) -> List[Dict[str, str]]:
        """Get list of issues for a file."""
        issues = []
        status = self.get_file_status(file_path)
        relationship = self.get_import_details(file_path)
        
        if not status.exists:
            issues.append({
                "type": "error",
                "message": "File does not exist"
            })
        
        if relationship.invalid_imports:
            issues.append({
                "type": "error",
                "message": f"Invalid imports: {', '.join(relationship.invalid_imports)}"
            })
            
        if relationship.circular_refs:
            issues.append({
                "type": "warning",
                "message": f"Circular references detected: {', '.join(str(ref) for ref in relationship.circular_refs)}"
            })
            
        if relationship.relative_imports:
            issues.append({
                "type": "info",
                "message": f"Uses relative imports: {', '.join(relationship.relative_imports)}"
            })
            
        return issues

    async def analyze_imports(self, file_path: Union[str, Path], results: ValidationResults) -> None:
        """Analyze imports in a file.
        
        Args:
            file_path: Path to the file to analyze
            results: ValidationResults object to store results
        """
        self.validation_pass += 1
        logger.debug(f"[Trace: {self.trace_id}] Starting validation pass {self.validation_pass} for {file_path}")
        
        try:
            # Convert file_path to Path and resolve it
            file_path = Path(str(file_path)).resolve()
            str_file_path = str(file_path)
            logger.debug(f"[Trace: {self.trace_id}] Resolved file path: {str_file_path}")
            
            # Read and parse file
            content = await self.fs.read_file(file_path)
            logger.debug(f"[Trace: {self.trace_id}] Successfully read file: {str_file_path}")
            
            tree = ast.parse(content)
            logger.debug(f"[Trace: {self.trace_id}] Successfully parsed AST for: {str_file_path}")
            
            # Initialize import tracking for this file
            if str_file_path not in results.imports:
                results.imports[str_file_path] = set()
            if str_file_path not in results.invalid_imports:
                results.invalid_imports[str_file_path] = set()
            if str_file_path not in results.relative_imports:
                results.relative_imports[str_file_path] = set()
            logger.debug(f"[Trace: {self.trace_id}] Initialized import tracking for: {str_file_path}")
            
            # Visit the AST to collect imports
            visitor = ImportVisitor(str_file_path, self)
            visitor.visit(tree)
            logger.debug(f"[Trace: {self.trace_id}] Found {len(visitor.imports)} imports in: {str_file_path}")
            
            # Process collected imports
            for import_info in visitor.imports:
                module = import_info.name
                logger.debug(f"[Trace: {self.trace_id}] Processing import '{module}' in {str_file_path}")
                
                results.imports[str_file_path].add(module)
                results.stats.total_imports += 1
                
                # Handle relative imports
                if module.startswith('.'):
                    logger.debug(f"[Trace: {self.trace_id}] Processing relative import '{module}' in {str_file_path}")
                    results.relative_imports[str_file_path].add(module)
                    results.stats.relative_imports_count += 1
                    
                    # Resolve relative import
                    dots = len(module) - len(module.lstrip('.'))
                    module_name = module.lstrip('.')
                    logger.debug(f"[Trace: {self.trace_id}] Resolving relative import: dots={dots}, module_name={module_name}")
                    
                    # Get parent directory
                    parent = file_path.parent
                    for _ in range(dots - 1):
                        if str(parent) == str(parent.parent):  # At root directory
                            logger.debug(f"[Trace: {self.trace_id}] Hit root directory while resolving relative import")
                            break
                        parent = parent.parent
                        # Stop at src/tests directory
                        if parent.name in ['src', 'tests']:
                            logger.debug(f"[Trace: {self.trace_id}] Hit src/tests directory while resolving relative import")
                            break
                            
                    # Split into parts
                    parts = module_name.split('.')
                    current_path = parent
                    logger.debug(f"[Trace: {self.trace_id}] Resolving from parent directory: {current_path}")
                    
                    # Build path incrementally
                    found_module = False
                    for i, part in enumerate(parts):
                        # First check if this part exists as a .py file
                        py_file = current_path / f"{part}.py"
                        logger.debug(f"[Trace: {self.trace_id}] Checking for Python file: {py_file}")
                        
                        if await self.fs.file_exists(py_file):
                            # If this is the last part or the next part might be a class/function name
                            if i == len(parts) - 1 or i == len(parts) - 2:
                                resolved_path = str(py_file.resolve())
                                logger.debug(f"[Trace: {self.trace_id}] Found module file, adding edge: {str_file_path} -> {resolved_path}")
                                self.import_graph.add_edge(str_file_path, resolved_path)
                                self.update_import_relationship(str_file_path, resolved_path, 'relative')
                                found_module = True
                                break
                                
                        # If not a .py file or not the last part, check/traverse directory
                        current_path = current_path / part
                        if i < len(parts) - 1:  # Only check for __init__.py if not the last part
                            init_file = current_path / '__init__.py'
                            logger.debug(f"[Trace: {self.trace_id}] Checking for __init__.py: {init_file}")
                            
                            if not await self.fs.file_exists(init_file):
                                # Try the parent directory's .py file for the last part
                                if i == len(parts) - 2:
                                    py_file = current_path.parent / f"{parts[-1]}.py"
                                    logger.debug(f"[Trace: {self.trace_id}] Checking parent directory for Python file: {py_file}")
                                    
                                    if await self.fs.file_exists(py_file):
                                        resolved_path = str(py_file.resolve())
                                        logger.debug(f"[Trace: {self.trace_id}] Found module file in parent, adding edge: {str_file_path} -> {resolved_path}")
                                        self.import_graph.add_edge(str_file_path, resolved_path)
                                        self.update_import_relationship(str_file_path, resolved_path, 'relative')
                                        found_module = True
                                        break
                                        
                    if not found_module:
                        logger.debug(f"[Trace: {self.trace_id}] Could not find module for relative import '{module}' in {str_file_path}")
                        results.invalid_imports[str_file_path].add(module)
                        results.stats.invalid_imports_count += 1
                else:
                    # Handle absolute imports
                    logger.debug(f"[Trace: {self.trace_id}] Processing absolute import '{module}' in {str_file_path}")
                    import_type = self._classify_import(module, str_file_path)
                    logger.debug(f"[Trace: {self.trace_id}] Import '{module}' classified as {import_type}")
                    
                    if import_type == 'local':
                        # Try to find module path
                        module_path = await self.find_module_path(module, str_file_path)
                        if module_path:
                            logger.debug(f"[Trace: {self.trace_id}] Found local module path: {module_path}")
                            self.import_graph.add_edge(str_file_path, module_path)
                            self.update_import_relationship(str_file_path, module_path, 'local')
                            results.stats.local_imports += 1
                        else:
                            logger.debug(f"[Trace: {self.trace_id}] Could not find path for local import '{module}'")
                            results.invalid_imports[str_file_path].add(module)
                            results.stats.invalid_imports_count += 1
                    elif import_type == 'stdlib':
                        results.stats.stdlib_imports += 1
                        self.update_import_relationship(str_file_path, module, 'stdlib')
                    elif import_type == 'thirdparty':
                        results.stats.thirdparty_imports += 1
                        self.update_import_relationship(str_file_path, module, 'thirdparty')
                    else:
                        logger.debug(f"[Trace: {self.trace_id}] Invalid import '{module}' in {str_file_path}")
                        results.invalid_imports[str_file_path].add(module)
                        results.stats.invalid_imports_count += 1
                        self.update_import_relationship(str_file_path, module, 'invalid')
                        
        except Exception as e:
            logger.error(f"[Trace: {self.trace_id}] Error analyzing imports in {file_path}: {e}", exc_info=True)
            raise

    async def find_module_path(self, module_name: str, current_file: Optional[str] = None) -> Optional[str]:
        """Find the path to a module.
        
        Args:
            module_name: Name of the module to find
            current_file: Optional path of file containing the import
            
        Returns:
            Resolved path to the module file or None if not found
        """
        try:
            logger.debug(f"[Trace: {self.trace_id}] Finding module path for '{module_name}' from {current_file}")
            
            # Get base module (before any dots)
            base_module = module_name.split('.')[0]
            
            # Handle src.* imports
            if base_module == 'src':
                # Convert module path to directory structure
                parts = module_name.split('.')
                # Remove 'src' prefix
                parts = parts[1:]
                
                # Try as a .py file first - use all but the last part if it might be a class/object
                module_parts = parts[:-1] if len(parts) > 1 else parts
                module_path = self.src_dir.joinpath(*module_parts[:-1], f"{module_parts[-1]}.py")
                logger.debug(f"[Trace: {self.trace_id}] Checking for .py file at: {module_path}")
                
                if await self.fs.file_exists(module_path):
                    resolved = str(module_path.resolve())
                    logger.debug(f"[Trace: {self.trace_id}] Found module file at: {resolved}")
                    return resolved
                
                # Try as a package (directory with __init__.py)
                package_path = self.src_dir.joinpath(*module_parts)
                init_path = package_path / '__init__.py'
                logger.debug(f"[Trace: {self.trace_id}] Checking for package at: {init_path}")
                
                if await self.fs.file_exists(init_path):
                    resolved = str(init_path.resolve())
                    logger.debug(f"[Trace: {self.trace_id}] Found package at: {resolved}")
                    return resolved
                
                # Try as a module without .py extension
                if await self.fs.file_exists(package_path):
                    resolved = str(package_path.resolve())
                    logger.debug(f"[Trace: {self.trace_id}] Found module at: {resolved}")
                    return resolved
                
            # Handle tests.* imports similarly
            elif base_module == 'tests' and self.tests_dir:
                parts = module_name.split('.')
                # Remove 'tests' prefix
                parts = parts[1:]
                
                # Try as a .py file first - use all but the last part if it might be a class/object
                module_parts = parts[:-1] if len(parts) > 1 else parts
                module_path = self.tests_dir.joinpath(*module_parts[:-1], f"{module_parts[-1]}.py")
                logger.debug(f"[Trace: {self.trace_id}] Checking for .py file at: {module_path}")
                
                if await self.fs.file_exists(module_path):
                    resolved = str(module_path.resolve())
                    logger.debug(f"[Trace: {self.trace_id}] Found module file at: {resolved}")
                    return resolved
                
                # Try as a package (directory with __init__.py)
                package_path = self.tests_dir.joinpath(*module_parts)
                init_path = package_path / '__init__.py'
                logger.debug(f"[Trace: {self.trace_id}] Checking for package at: {init_path}")
                
                if await self.fs.file_exists(init_path):
                    resolved = str(init_path.resolve())
                    logger.debug(f"[Trace: {self.trace_id}] Found package at: {resolved}")
                    return resolved
                
                # Try as a module without .py extension
                if await self.fs.file_exists(package_path):
                    resolved = str(package_path.resolve())
                    logger.debug(f"[Trace: {self.trace_id}] Found module at: {resolved}")
                    return resolved
                
            # Check if it's a standard library module
            if self.is_stdlib_module(module_name):
                return None
                
            logger.debug(f"[Trace: {self.trace_id}] Could not find module path for '{module_name}'")
            return None
            
        except Exception as e:
            logger.error(f"[Trace: {self.trace_id}] Error finding module path for '{module_name}': {e}", exc_info=True)
            return None

    def _classify_import(self, import_name: str, current_file: Union[str, Path]) -> str:
        """Classify an import as stdlib, thirdparty, local, or invalid.
        
        Args:
            import_name: Name of the import to classify
            current_file: Path of file containing the import
            
        Returns:
            Classification as 'stdlib', 'thirdparty', 'local', or 'invalid'
        """
        try:
            # Handle src/tests base modules
            if import_name.startswith(('src.', 'tests.')):
                logger.debug(f"[Trace: {self.trace_id}] Import '{import_name}' classified as local (src/tests)")
                return 'local'
                
            # Handle relative imports as local
            if import_name.startswith('.'):
                logger.debug(f"[Trace: {self.trace_id}] Import '{import_name}' classified as local (relative)")
                return 'local'
                
            # Get base module name (before any dots)
            base_module = import_name.split('.')[0]
            logger.debug(f"[Trace: {self.trace_id}] Base module: '{base_module}'")
            
            # Check if base module itself is src or tests
            if base_module in ('src', 'tests'):
                logger.debug(f"[Trace: {self.trace_id}] Import '{import_name}' classified as local (src/tests base)")
                return 'local'
                
            # Check if it's a standard library module
            if base_module in self.stdlib_modules:
                logger.debug(f"[Trace: {self.trace_id}] Import '{import_name}' classified as stdlib")
                return 'stdlib'
                
            # Check if the module is directly in valid_packages
            if base_module in self.valid_packages:
                logger.debug(f"[Trace: {self.trace_id}] Import '{import_name}' classified as thirdparty (in valid_packages)")
                return 'thirdparty'
                
            # Check if any package provides this module
            for package, modules in self.package_to_modules.items():
                if base_module in modules and package in self.valid_packages:
                    logger.debug(f"[Trace: {self.trace_id}] Found module {base_module} is provided by valid package {package}")
                    # Add the module to valid_packages since we know it's valid
                    self.valid_packages.add(base_module)
                    return 'thirdparty'
                    
            # Check if it's in installed_packages
            if base_module in self.installed_packages:
                logger.debug(f"[Trace: {self.trace_id}] Import '{import_name}' classified as thirdparty (in installed_packages)")
                # Since it's installed, add it to valid_packages
                self.valid_packages.add(base_module)
                return 'thirdparty'
                
            # Try to find the package that provides this module
            try:
                spec = importlib.util.find_spec(base_module)
                if spec and spec.origin:
                    package_dir = str(Path(spec.origin).parent)
                    while package_dir:
                        init_path = Path(package_dir) / '__init__.py'
                        if init_path.exists():
                            package_name = Path(package_dir).name
                            # Check if this package is in our valid packages
                            if package_name in self.valid_packages:
                                logger.debug(f"[Trace: {self.trace_id}] Found module {base_module} belongs to package {package_name}")
                                # Add to our mappings since we found a new valid module
                                self.package_to_modules.setdefault(package_name, set()).add(base_module)
                                self.valid_packages.add(base_module)
                                return 'thirdparty'
                        parent_dir = str(Path(package_dir).parent)
                        if parent_dir == package_dir:
                            break
                        package_dir = parent_dir
            except Exception as e:
                logger.debug(f"[Trace: {self.trace_id}] Error finding spec for {base_module}: {e}")
                
            # Try to find the module in the project
            if current_file:
                try:
                    # Convert current_file to Path safely
                    current_path = Path(str(current_file))
                    module_path = current_path.parent / f"{base_module}.py"
                    if module_path.exists():
                        logger.debug(f"[Trace: {self.trace_id}] Found local module file: {module_path}")
                        return 'local'
                        
                    # Check if it's a local package
                    package_init = current_path.parent / base_module / '__init__.py'
                    if package_init.exists():
                        logger.debug(f"[Trace: {self.trace_id}] Found local package: {package_init}")
                        return 'local'
                except Exception as e:
                    logger.debug(f"[Trace: {self.trace_id}] Error checking local module: {e}")
                    
            logger.debug(f"[Trace: {self.trace_id}] Import '{import_name}' classified as invalid")
            return 'invalid'
            
        except Exception as e:
            logger.debug(f"[Trace: {self.trace_id}] Error classifying import '{import_name}': {e}")
            return 'invalid'

    def find_circular_references(self, results: ValidationResults) -> Dict[str, List[List[str]]]:
        """Find circular references in the import graph.
        
        Args:
            results: ValidationResults object containing the import graph
            
        Returns:
            Dictionary mapping file paths to lists of cycles containing that file
        """
        try:
            cycles = list(nx.simple_cycles(results.import_graph))
            if not cycles:
                return {}

            circular_refs = defaultdict(list)
            for cycle in cycles:
                for node in cycle:
                    circular_refs[node].append(cycle)

            # Update stats with the number of unique cycles
            results.stats.circular_refs_count = len(cycles)
            results.circular_references = dict(circular_refs)

            return dict(circular_refs)
        except Exception as e:
            results.add_error(ValidationError(
                error_type="CircularReferenceError",
                message=f"Error finding circular references: {str(e)}"
            ))
            return {}

    async def validate_all(self) -> ValidationResults:
        """Validate all Python files in the project.

        Returns:
            ValidationResults containing analysis results and any errors
        """
        results = ValidationResults()

        try:
            # Find all Python files
            src_files = await self.fs.find_python_files(self.src_dir)
            tests_files = await self.fs.find_python_files(self.tests_dir) if self.tests_dir else set()

            # Analyze each file
            for file_path in src_files | tests_files:
                try:
                    await self.analyze_imports(file_path, results)
                except (FileNotFoundError, SyntaxError, ImportError) as e:
                    # These errors are already handled in analyze_imports
                    continue

            # Find circular references
            self.find_circular_references(results)

            # Calculate complexity and update stats
            results.stats.calculate_complexity()
            results.update_stats()

        except Exception as e:
            error = ValidationError(
                error_type="ProjectError",
                message=str(e),
                context="Error validating project"
            )
            results.errors.append(error)
            raise

        return results

    def resolve_relative_import(self, import_name: str, current_file: str, module_name: str = None) -> Optional[str]:
        """Resolve a relative import to an absolute path.
        
        Args:
            import_name: The relative import to resolve
            current_file: The file containing the import
            module_name: Optional module name for the import
            
        Returns:
            The normalized path to the resolved import, or None if not found
        """
        return self.path_normalizer.resolve_relative_import(import_name, current_file)

    def is_stdlib_module(self, module_name: str) -> bool:
        """Check if a module is part of the Python standard library.
        
        Args:
            module_name: Name of the module to check
            
        Returns:
            True if the module is part of the standard library, False otherwise
        """
        # Get base module (before any dots)
        base_module = module_name.split('.')[0]
        
        # Check if it's in stdlib_modules set
        if base_module in self.stdlib_modules:
            return True
            
        # Try importing as stdlib module
        try:
            # Special case handling for common stdlib modules
            if base_module in {'os', 'sys', 'pathlib', 'typing', 'ast', 'json', 'logging', 'asyncio', 'importlib'}:
                self.stdlib_modules.add(base_module)
                return True
                
            spec = importlib.util.find_spec(base_module)
            if spec is None:
                return False
                
            # If module has no origin (built-in) or is in stdlib location
            if spec.origin is None or (
                spec.origin and 
                'site-packages' not in spec.origin and
                any(p in spec.origin for p in ('python3', 'python39', 'python38', 'python37', 'python36'))
            ):
                self.stdlib_modules.add(base_module)
                return True
                
        except (ImportError, AttributeError):
            pass
            
        return False

class ImportVisitor(ast.NodeVisitor):
    """AST visitor for collecting import information."""
    
    def __init__(self, file_path: Union[str, Path], validator: 'AsyncImportValidator'):
        """Initialize the visitor.
        
        Args:
            file_path: Path to the file being visited
            validator: Reference to the validator instance
        """
        # Convert file_path to string to ensure consistent handling
        self.file_path = str(file_path) if isinstance(file_path, Path) else file_path
        self.validator = validator
        self.imports: List[ImportInfo] = []
        self.used_names = set()
        
    def visit_Import(self, node: ast.Import) -> None:
        """Visit Import node."""
        for name in node.names:
            import_info = ImportInfo(
                name=name.name,
                alias=name.asname,
                is_relative=False,
                lineno=node.lineno
            )
            self.imports.append(import_info)
        self.generic_visit(node)
        
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit ImportFrom node."""
        module = ('.' * node.level) + (node.module or '')
        for name in node.names:
            full_name = f"{module}.{name.name}" if module else name.name
            import_info = ImportInfo(
                name=full_name,
                alias=name.asname,
                is_relative=node.level > 0,
                lineno=node.lineno
            )
            self.imports.append(import_info)
        self.generic_visit(node)
        
    def visit_Name(self, node: ast.Name) -> None:
        """Visit Name node to track used imports."""
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        self.generic_visit(node)
        
    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Visit Attribute node to track used imports."""
        # Build full attribute path
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            # Add all possible prefixes
            full_path = '.'.join(reversed(parts))
            while parts:
                self.used_names.add('.'.join(reversed(parts)))
                parts.pop()
        self.generic_visit(node)
        
    def finalize(self) -> None:
        """Mark imports as used or unused based on collected information."""
        for import_info in self.imports:
            name = import_info.alias or import_info.name.split('.')[-1]
            if name in self.used_names:
                import_info.is_used = True

async def handle_project_scan(request):
    """Handle project scanning requests from the web interface."""
    try:
        data = await request.json()
        project_name = data['projectName']
        files = data['files']
        base_dir = data.get('basePath')  # Get the full base path from the client
        context = data.get('context', {})
        
        if not base_dir:
            raise ValueError("Base directory path not provided")
            
        # Convert base_dir to Path and resolve it
        try:
            base_dir = Path(base_dir).resolve()
            logger.debug(f"[Project Scan] Resolved base directory: {base_dir}")
        except Exception as e:
            logger.error(f"[Project Scan] Error resolving base directory '{base_dir}': {e}", exc_info=True)
            raise ValueError(f"Invalid base directory path: {e}")
        
        logger.info(f"[Project Scan] Received scan request for project: {project_name}")
        logger.info(f"[Project Scan] Base directory: {base_dir}")
        logger.info(f"[Project Scan] Files to scan: {len(files)}")
        logger.info(f"[Project Scan] Context: {context}")
        
        # Create response stream
        try:
            response = web.StreamResponse(
                status=200,
                reason='OK',
                headers={
                    'Content-Type': 'application/x-ndjson',
                    'Transfer-Encoding': 'chunked'
                }
            )
            await response.prepare(request)
            logger.debug("[Project Scan] Response stream prepared successfully")
        except Exception as e:
            logger.error(f"[Project Scan] Error preparing response stream: {e}", exc_info=True)
            raise
        
        async def send_update(data):
            """Helper function to send updates."""
            try:
                message = json_dumps(data)
                await response.write(message.encode('utf-8'))
                await response.write(b'\n')
                await response.drain()
                logger.debug(f"[Project Scan] Sent update: {data.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"[Project Scan] Error sending update: {e}", exc_info=True)
                raise
        
        # Initial progress
        await send_update({
            'type': 'progress',
            'progress': 0,
            'status': 'Starting import validation...'
        })

        # Create validator config
        try:
            config = ImportValidatorConfig(
                base_dir=str(base_dir),
                src_dir=str(base_dir / 'src'),
                tests_dir=str(base_dir / 'tests'),
                valid_packages=set(),  # Will be populated from requirements and pyproject
                ignore_patterns={"*.pyc", "__pycache__/*"},
                complexity_threshold=10.0,
                max_edges_per_diagram=100
            )
            logger.debug("[Project Scan] Created validator config successfully")
        except Exception as e:
            logger.error(f"[Project Scan] Error creating validator config: {e}", exc_info=True)
            raise

        # Initialize validator with custom file system
        try:
            fs = DefaultFileSystem()
            validator = AsyncImportValidator(config=config, fs=fs)
            await validator.initialize()
            logger.debug("[Project Scan] Validator initialized successfully")
        except Exception as e:
            logger.error(f"[Project Scan] Error initializing validator: {e}", exc_info=True)
            raise
        
        # Update progress - 50%
        await send_update({
            'type': 'progress',
            'progress': 50,
            'status': 'Validating imports...'
        })
        
        # Create a ValidationResults object to store results
        results = ValidationResults()
        
        # Process each file
        for file_info in files:
            try:
                # Get relative path and convert to absolute path
                relative_path = file_info['path']
                full_path = base_dir / relative_path
                logger.debug(f"[Project Scan] Processing file: {full_path}")
                
                # Skip if file doesn't exist
                if not full_path.exists():
                    logger.warning(f"[Project Scan] Skipping non-existent file: {full_path}")
                    continue
                    
                # Convert to Path object for processing
                file_path = Path(full_path).resolve()
                await validator.analyze_imports(file_path, results)
                logger.debug(f"[Project Scan] Successfully analyzed imports for: {file_path}")
                
            except Exception as e:
                logger.error(f"[Project Scan] Error processing file {relative_path}: {e}", exc_info=True)
                continue
        
        # Find circular references
        try:
            validator.find_circular_references(results)
            logger.debug("[Project Scan] Successfully found circular references")
        except Exception as e:
            logger.error(f"[Project Scan] Error finding circular references: {e}", exc_info=True)
            raise
        
        # Update progress - 80%
        await send_update({
            'type': 'progress',
            'progress': 80,
            'status': 'Creating visualization...'
        })
        
        # Create graph data for visualization
        try:
            nodes = []
            links = []
            node_ids = set()
            
            # First pass: Create nodes and collect all file paths
            for file_path in results.imports.keys():
                try:
                    # Log the type of file_path before processing
                    logger.debug(f"[Project Scan] Processing node for file_path: {file_path} (type: {type(file_path)})")
                    
                    # Ensure file_path is a string
                    file_path = str(file_path)
                    # Convert to Path and resolve for consistent handling
                    resolved_path = str(Path(file_path).resolve())
                    node_ids.add(resolved_path)
                    
                    # Check if this file is in any circular references
                    is_circular = False
                    if results.circular_refs:
                        for cycles in results.circular_refs.values():
                            for cycle in cycles:
                                if any(str(Path(p).resolve()) == resolved_path for p in cycle):
                                    is_circular = True
                                    break
                            if is_circular:
                                break
                        
                    # Create node with all values explicitly converted to strings
                    node = {
                        'id': resolved_path,
                        'name': str(Path(file_path).name),
                        'full_path': resolved_path,
                        'imports': [str(imp) for imp in results.imports.get(file_path, [])],
                        'invalid_imports': [str(imp) for imp in results.invalid_imports.get(file_path, [])],
                        'relative_imports': [str(imp) for imp in results.relative_imports.get(file_path, [])],
                        'invalid': bool(results.invalid_imports.get(file_path, [])),
                        'circular': is_circular
                    }
                    nodes.append(node)
                    logger.debug(f"[Project Scan] Successfully created node for: {file_path}")
                except Exception as e:
                    logger.error(f"[Project Scan] Error creating node for {file_path}: {e}", exc_info=True)
                    continue
            
            # Second pass: Create links
            for source, imports in results.imports.items():
                try:
                    # Log the type of source before processing
                    logger.debug(f"[Project Scan] Processing links for source: {source} (type: {type(source)})")
                    
                    # Ensure source is a string
                    source = str(source)
                    source_path = str(Path(source).resolve())
                    
                    if source_path in node_ids:
                        for imp in imports:
                            # Log the type of import before processing
                            logger.debug(f"[Project Scan] Processing import: {imp} (type: {type(imp)})")
                            
                            # Ensure import is a string
                            imp = str(imp)
                            # Only process local imports
                            if validator._classify_import(imp, source) == 'local':
                                target_path = await validator.find_module_path(imp, source)
                                if target_path:
                                    target_path = str(Path(target_path).resolve())
                                    if target_path in node_ids:
                                        # Check if this link is part of a circular reference
                                        is_circular = False
                                        if results.circular_refs:
                                            for cycles in results.circular_refs.values():
                                                for cycle in cycles:
                                                    cycle_paths = [str(Path(p).resolve()) for p in cycle]
                                                    if source_path in cycle_paths and target_path in cycle_paths:
                                                        idx_source = cycle_paths.index(source_path)
                                                        idx_target = cycle_paths.index(target_path)
                                                        if (idx_source + 1) % len(cycle_paths) == idx_target:
                                                            is_circular = True
                                                            break
                                            if is_circular:
                                                break
                                    
                                    link = {
                                        'source': source_path,
                                        'target': target_path,
                                        'invalid': False,
                                        'circular': is_circular
                                    }
                                    links.append(link)
                                    logger.debug(f"[Project Scan] Successfully created link: {source_path} -> {target_path}")
                except Exception as e:
                    logger.error(f"[Project Scan] Error creating links for {source}: {e}", exc_info=True)
                    continue

            graph_data = {'nodes': nodes, 'links': links}
            logger.debug("[Project Scan] Successfully created graph data")
            
            # Send final update with graph data
            await send_update({
                'type': 'complete',
                'graph': graph_data
            })
            
            return response
            
        except Exception as e:
            logger.error(f"[Project Scan] Error creating graph data: {e}", exc_info=True)
            raise
            
    except Exception as e:
        error_msg = f"Error handling project scan: {str(e)}"
        logger.error(f"[Project Scan] {error_msg}", exc_info=True)
        return web.json_response({
            'error': error_msg
        }, status=500)

async def handle_json_data(request):
    """Handle requests for raw JSON data."""
    try:
        data = await request.json()
        project_name = data['projectName']
        base_dir = data.get('basePath')  # Get the full base path from the client
        context = data.get('context', {})
        
        if not base_dir:
            raise ValueError("Base directory path not provided")
            
        # Handle Windows paths
        if context.get('isWindowsPath'):
            base_dir = str(base_dir).replace('/', '\\')
        
        project_path = Path(base_dir).resolve()  # Get absolute path
        
        if not project_path.exists():
            raise ValueError(f"Project path does not exist: {project_path}")
        
        # Find src and tests directories
        src_dir = project_path / 'src'
        tests_dir = project_path / 'tests'
        
        # If no src directory exists, check for Python files in the root
        if not src_dir.exists() or not any(src_dir.glob('**/*.py')):
            # Look for Python files in the root
            if any(project_path.glob('*.py')):
                src_dir = project_path
            else:
                raise ValueError(f"No Python files found in {project_path}")
        
        tests_dir = tests_dir if tests_dir.exists() and any(tests_dir.glob('**/*.py')) else None
        
        logger.info(f"Using src_dir: {src_dir}")
        logger.info(f"Using tests_dir: {tests_dir}")
        
        # Create validator config with absolute paths
        config = ImportValidatorConfig(
            src_dir=str(src_dir.resolve()),
            tests_dir=str(tests_dir.resolve()) if tests_dir else None,
            base_dir=str(project_path.resolve()),
            valid_packages={"pytest", "networkx", "rich", "pydantic-settings"},
            ignore_patterns={"*.pyc", "__pycache__/*"},
            complexity_threshold=10.0,
            max_edges_per_diagram=100
        )
        
        # Run the validator
        validator = AsyncImportValidator(config=config)
        await validator.initialize()
        
        # Run validation
        results = await validator.validate_all()
        
        # Return the complete data structure with accurate stats
        return web.json_response({
            'import_graph': {str(k): list(v) for k, v in results.import_graph.edges()},
            'imports': {str(k): list(v) for k, v in results.imports.items()},
            'invalid_imports': {str(k): list(v) for k, v in results.invalid_imports.items()},
            'relative_imports': {str(k): list(v) for k, v in results.relative_imports.items()},
            'circular_refs': {str(k): [list(cycle) for cycle in v] for k, v in results.circular_refs.items()},
            'stats': {
                'total_imports': results.stats.total_imports,
                'unique_imports': results.stats.unique_imports,
                'invalid_imports': results.stats.invalid_imports_count,
                'relative_imports': results.stats.relative_imports_count,
                'circular_refs': results.stats.circular_refs_count,
                'complexity_score': results.stats.complexity_score
            }
        })
    except Exception as e:
        logger.error(f"Error getting JSON data: {str(e)}", exc_info=True)
        return web.json_response({'error': str(e)}, status=500)

async def handle_file_contents(request):
    """Handle requests for file contents."""
    try:
        data = await request.json()
        file_path = data['filePath']
        
        # Ensure we have a proper absolute path with drive letter
        if not file_path.startswith(('\\', '/')):
            # Already has drive letter
            full_path = Path(file_path)
        else:
            # Missing drive letter, try to get it from the path
            drive_match = re.match(r'^[/\\]*([A-Za-z]:)', file_path)
            if drive_match:
                # Drive letter is in the path but with leading slashes
                drive = drive_match.group(1)
                path_without_drive = file_path[drive_match.end():].lstrip('/\\')
                full_path = Path(f"{drive}\\{path_without_drive}")
            else:
                raise ValueError(f"File path must include drive letter: {file_path}")
            
        if not full_path.is_absolute():
            raise ValueError(f"File path must be absolute: {file_path}")
            
        if not await AsyncFileSystem().file_exists(full_path):
            raise FileNotFoundError(f"File not found: {full_path}")
            
        content = await AsyncFileSystem().read_file(full_path)
        return web.json_response({
            'content': content
        })
    except Exception as e:
        logger.error(f"Error reading file contents: {e}", exc_info=True)
        return web.json_response({
            'error': str(e)
        }, status=500)

async def run_server_async():
    """Run the web server asynchronously."""
    app = web.Application()
    
    # Setup CORS with proper configuration
    cors = setup_cors(app, defaults={
        "*": ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["GET", "POST", "OPTIONS"]
        )
    })
    
    # Add static file handling for templates with proper CORS
    templates_dir = Path(__file__).parent / 'templates'
    
    # Serve static files first
    static_resource = app.router.add_static('/static/', templates_dir / 'static')
    cors.add(static_resource)
    
    # Serve the template at root
    async def serve_template(request):
        template_path = templates_dir / 'd3_template.html'
        return web.FileResponse(template_path)
    
    # Add API routes with CORS
    scan_resource = cors.add(app.router.add_resource("/api/scan-project"))
    scan_route = scan_resource.add_route("POST", handle_project_scan)
    cors.add(scan_route)
    
    json_resource = cors.add(app.router.add_resource("/api/json-data"))
    json_route = json_resource.add_route("POST", handle_json_data)
    cors.add(json_route)
    
    file_contents_resource = cors.add(app.router.add_resource("/api/file-contents"))
    file_contents_route = file_contents_resource.add_route("POST", handle_file_contents)
    cors.add(file_contents_route)
    
    # Add root route
    root_resource = app.router.add_resource('/')
    root_route = root_resource.add_route('GET', serve_template)
    cors.add(root_route)
    
    # Run the app
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Try ports in sequence until one works
    ports = list(range(8080, 8100))  # Try ports 8080-8099
    site = None
    
    for port in ports:
        try:
            # Try IPv4 first
            try:
                site = web.TCPSite(runner, host='127.0.0.1', port=port)
                await site.start()
                print(f"Starting server at http://127.0.0.1:{port}")
                break
            except OSError:
                # If IPv4 fails, try IPv6
                site = web.TCPSite(runner, host='::1', port=port)
                await site.start()
                print(f"Starting server at http://[::1]:{port}")
                break
        except OSError as e:
            if port == ports[-1]:  # If this was the last port to try
                logger.error(f"Could not find an available port in range {ports[0]}-{ports[-1]}")
                await runner.cleanup()
                raise
            continue
    
    # Keep the server running
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour and continue running
    except asyncio.CancelledError:
        logger.info("Server shutdown requested")
    finally:
        await runner.cleanup()

def run_server():
    """Run the web server for real-time validation."""
    try:
        asyncio.run(run_server_async())
    except KeyboardInterrupt:
        print("\nServer shutdown requested")
    except Exception as e:
        print(f"\nServer error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        run_server()
    else:
        print("Usage: python -m validator.validator --server")
        sys.exit(1)
