"""Validator module for analyzing Python imports."""
import asyncio
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Union, Tuple, Any
import ast
from collections import defaultdict
import json
import networkx as nx
import re
import os
import random
import uuid

from .async_utils import find_python_files_async, parse_ast_threaded, read_file_async, file_exists_async, get_installed_packages
from .error_handling import ValidationError
from .validator_types import ImportUsage, ValidationResults, PathNormalizer, ImportInfo, ImportValidatorConfig, FileStatus, ImportRelationship
from .file_system import AsyncFileSystem
from .logging_config import setup_logging
from .file_system_interface import FileSystemInterface
from .import_visitor import ImportVisitor
from .package_mappings import MODULE_TO_PACKAGE, PACKAGE_TO_MODULES
from .default_file_system import DefaultFileSystem

# Set up logging using centralized configuration
logger = logging.getLogger('validator.core')

class AsyncImportValidator:
    """Asynchronous import validator."""

    def __init__(self, config: ImportValidatorConfig, fs: FileSystemInterface):
        """Initialize the validator."""
        self.config = config
        self.fs = fs
        self.base_dir = Path(config.base_dir).resolve()
        self.src_dir = Path(config.src_dir).resolve()
        self.tests_dir = Path(config.tests_dir).resolve() if config.tests_dir is not None else None
        self.valid_packages = config.valid_packages
        self.stdlib_modules = set(sys.stdlib_module_names)
        self.installed_packages = self.stdlib_modules.copy()  # Initialize with stdlib modules
        self.import_relationships: Dict[str, ImportRelationship] = {}
        self.file_statuses: Dict[str, FileStatus] = {}
        self.import_graph = nx.DiGraph()
        self.trace_id = str(uuid.uuid4())
        self.logger = logging.getLogger('import_validator')
        self.validation_pass = 0  # Track validation pass number
        
        logger.debug(f"[Trace: {self.trace_id}] Initializing validator instance")
        
        # Initialize path handling
        self.path_normalizer = PathNormalizer(
            src_dir=str(self.src_dir),
            tests_dir=str(self.tests_dir) if self.tests_dir else None,
            base_dir=str(self.base_dir)
        )
        
        # Track file statuses
        self.missing_files: Set[str] = set()
        self.invalid_files: Set[str] = set()
        
        # Initialize import tracking
        self.module_definitions = {}
        self.package_to_modules = {}  # Track which modules each package provides

        # Set source directories
        self.source_dirs = [self.src_dir]
        if self.tests_dir:
            self.source_dirs.append(self.tests_dir)

    async def initialize(self) -> None:
        """Initialize validator by finding Python files and extracting imports."""
        logger.debug(f"Initializing validator for project: {self.config.base_dir}")
        
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

        # Add module names from our known mappings
        for module_name, package_name in MODULE_TO_PACKAGE.items():
            if package_name.lower() in {pkg.lower() for pkg in self.valid_packages}:
                self.valid_packages.add(module_name)
                self.installed_packages.add(module_name)

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

        logger.debug(f"Initialized with {len(self.valid_packages)} valid packages")
        logger.debug(f"Valid packages: {sorted(self.valid_packages)}")
        logger.debug(f"Package to modules mapping: {self.package_to_modules}")
        
        self.logger.info(f"Initialized validator with base_dir: {self.base_dir}")
        self.logger.info(f"Source directory: {self.src_dir}")
        self.logger.info(f"Tests directory: {self.tests_dir}")
        self.logger.info(f"Installed packages: {len(self.installed_packages)}")

    def get_file_status(self, file_path: str) -> FileStatus:
        """Get status for a file."""
        normalized_path = file_path
        if Path(file_path).exists():
            normalized_path = str(Path(file_path).resolve())
        
        # Return existing status if found
        if normalized_path in self.file_statuses:
            return self.file_statuses[normalized_path]
        
        # Get relationship if exists
        relationship = self.import_relationships.get(normalized_path)
        
        # Create new status for unknown file
        return FileStatus(
            path=file_path,  # Use original path for unknown files
            exists=False,
            is_test=False,
            import_count=len(relationship.imports) if relationship else 0,
            invalid_imports=len(relationship.invalid_imports) if relationship else 0,
            circular_refs=len(relationship.circular_refs) if relationship else 0,
            relative_imports=len(relationship.relative_imports) if relationship else 0
        )

    def get_import_details(self, file_path: str) -> ImportRelationship:
        """Get import details for a file."""
        normalized_path = file_path
        if Path(file_path).exists():
            normalized_path = str(Path(file_path).resolve())
        
        # Return existing relationship if found
        if normalized_path in self.import_relationships:
            return self.import_relationships[normalized_path]
        
        # Create new relationship for unknown file
        return ImportRelationship(
            file_path=file_path,  # Use original path for unknown files
            imports=set(),
            imported_by=set(),
            invalid_imports=set(),
            relative_imports=set(),
            circular_refs=set(),
            stdlib_imports=set(),
            thirdparty_imports=set(),
            local_imports=set()
        )

    def update_import_relationship(self, source: str, target: str, import_type: str):
        """Update import relationship tracking."""
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

    def get_node_details(self, file_path: str) -> Dict[str, Union[str, int, bool]]:
        """Get details about a node for visualization."""
        status = self.get_file_status(file_path)
        return {
            "path": status.path,
            "imports": status.import_count,
            "invalid_imports": status.invalid_imports,
            "relative_imports": status.relative_imports,
            "is_test": status.is_test
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

    def _classify_import(self, import_name: str, file_path: str) -> str:
        """Classify an import as stdlib, thirdparty, local, or relative."""
        # Handle relative imports first
        if import_name.startswith('.'):
            return "relative"
        
        # Split on dots to get the root package
        root_package = import_name.split('.')[0].lower()  # Convert to lowercase for comparison
        
        # Check if it's a stdlib module
        if root_package in self.stdlib_modules:
            return "stdlib"
        
        # Check if it's in valid packages (case insensitive)
        valid_packages_lower = {pkg.lower() for pkg in self.valid_packages}
        if root_package in valid_packages_lower:
            return "thirdparty"
        
        # Check module-to-package mapping
        if root_package in MODULE_TO_PACKAGE:
            mapped_package = MODULE_TO_PACKAGE[root_package].lower()
            if mapped_package in valid_packages_lower:
                return "thirdparty"
        
        # Check if it's a local module
        if self._is_local_module(import_name):
            return "local"
        
        # If none of the above, it's invalid
        return "invalid"

    def find_circular_references(self, results: ValidationResults) -> Dict[str, List[List[str]]]:
        """Find circular references in the import graph."""
        # Find all cycles in the graph
        cycles = list(nx.simple_cycles(results.import_graph))
        
        # Create a mapping of nodes to their cycles
        circular_refs: Dict[str, List[List[str]]] = {}
        
        # Process each cycle
        for cycle in cycles:
            # Only add the cycle to the first node in the cycle
            first_node = min(cycle)  # Use alphabetically first node
            if first_node not in circular_refs:
                circular_refs[first_node] = []
            circular_refs[first_node].append(cycle)
        
        return circular_refs

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

    def _is_local_module(self, import_name: str) -> bool:
        """Check if an import is a local module."""
        # Handle relative imports
        if import_name.startswith('.'):
            return True
        
        # Handle absolute imports
        parts = import_name.split('.')
        root = parts[0]
        
        # Check if it's a source or test module
        return (
            root == self.src_dir.name or
            (self.tests_dir and root == self.tests_dir.name)
        )

    def _is_valid_import(self, import_name: str) -> bool:
        """Check if an import is valid."""
        # Split on dots to get the root package
        root_package = import_name.split('.')[0].lower()  # Convert to lowercase for comparison
        
        # Check if it's a stdlib module
        if root_package in self.stdlib_modules:
            return True
            
        # Check if it's in valid packages (case insensitive)
        valid_packages_lower = {pkg.lower() for pkg in self.valid_packages}
        
        # Check direct match
        if root_package in valid_packages_lower:
            return True
            
        # Check module-to-package mapping
        if root_package in MODULE_TO_PACKAGE:
            mapped_package = MODULE_TO_PACKAGE[root_package].lower()
            if mapped_package in valid_packages_lower:
                return True
            
        # Check if it's a local module
        if self._is_local_module(import_name):
            return True
            
        return False

if __name__ == "__main__":
    print("Usage: python -m validator.validator")
    sys.exit(1)
