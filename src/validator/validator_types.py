"""Validator type definitions."""
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Union, TYPE_CHECKING
import ast
from collections import defaultdict
from typing import DefaultDict
import os
from collections import Counter
import logging
import re
import networkx as nx
import sys

if TYPE_CHECKING:
    from .validator import AsyncImportValidator

logger = logging.getLogger(__name__)

"""
Weight Factors Documentation:

The import validator uses a weighted scoring system to calculate complexity and identify potential issues
in Python codebases. Each metric has an associated weight that determines its impact on the overall
complexity score. Below are the default weights and their purposes:

1. total_imports (0.2):
   - Measures the raw number of import statements across all files
   - Lower weight because having many imports isn't necessarily problematic
   - Increase weight if you want to encourage fewer direct dependencies
   - Use cases: Microservices where minimal dependencies are desired

2. unique_imports (0.2):
   - Counts distinct imported modules/packages
   - Similar weight to total_imports as it measures dependency diversity
   - Increase weight to discourage adding new dependencies
   - Use cases: Security-sensitive applications where each new dependency is a potential risk

3. edges (0.3):
   - Represents connections between modules in the import graph
   - Higher weight because complex module relationships increase maintenance difficulty
   - Increase weight to encourage more modular, loosely coupled designs
   - Use cases: Large monolithic applications that need to be broken down

4. invalid_imports (0.2):
   - Counts imports that cannot be resolved
   - Moderate weight as these are definite issues that need fixing
   - Increase weight when reliability is critical
   - Use cases: Production systems where broken imports are unacceptable

5. unused_imports (0.15):
   - Tracks imports that are declared but never used
   - Lower weight as these are maintenance issues rather than functional problems
   - Increase weight to enforce cleaner code
   - Use cases: Code quality initiatives, preparing for public release

6. relative_imports (0.1):
   - Counts relative imports (using dot notation)
   - Lowest weight as relative imports are valid but can be confusing
   - Increase weight to discourage relative imports
   - Use cases: Large teams where explicit imports are preferred

7. circular_refs (0.3):
   - Identifies circular dependencies between modules
   - Higher weight as circular dependencies often indicate design problems
   - Increase weight when refactoring to break dependency cycles
   - Use cases: Architectural cleanup, preparing for modularization

Customization Guidelines:
- For maintainability: Increase weights for circular_refs and edges
- For code quality: Increase weights for unused_imports and invalid_imports
- For dependency management: Increase weights for total_imports and unique_imports
- For team standards: Adjust relative_imports weight based on team preferences

Example Weight Configurations:

1. Strict Dependency Management:
   {
       'total_imports': 0.4,
       'unique_imports': 0.4,
       'edges': 0.3,
       'invalid_imports': 0.3,
       'unused_imports': 0.2,
       'relative_imports': 0.1,
       'circular_refs': 0.3
   }

2. Code Quality Focus:
   {
       'total_imports': 0.2,
       'unique_imports': 0.2,
       'edges': 0.3,
       'invalid_imports': 0.4,
       'unused_imports': 0.4,
       'relative_imports': 0.2,
       'circular_refs': 0.3
   }

3. Architectural Cleanup:
   {
       'total_imports': 0.2,
       'unique_imports': 0.2,
       'edges': 0.4,
       'invalid_imports': 0.2,
       'unused_imports': 0.2,
       'relative_imports': 0.1,
       'circular_refs': 0.5
   }
"""

# Default weight factors for complexity calculations
DEFAULT_WEIGHT_FACTORS = {
    'total_imports': 0.2,    # Weight for total number of imports
    'unique_imports': 0.2,   # Weight for number of unique imports
    'edges': 0.3,           # Weight for import graph edges
    'invalid_imports': 0.2,  # Weight for invalid imports
    'unused_imports': 0.15,  # Weight for unused imports
    'relative_imports': 0.1, # Weight for relative imports
    'circular_refs': 0.3    # Weight for circular references
}

# Minimum and maximum allowed weights
MIN_WEIGHT = 0.0
MAX_WEIGHT = 5.0

def validate_weight_factors(weight_factors: Dict[str, float]) -> None:
    """Validate weight factors are within acceptable range and contain required keys."""
    required_keys = set(DEFAULT_WEIGHT_FACTORS.keys())
    provided_keys = set(weight_factors.keys())
    
    # Check for missing keys
    missing_keys = required_keys - provided_keys
    if missing_keys:
        raise ValueError(f"Missing required weight factors: {missing_keys}")
    
    # Check weight ranges
    invalid_weights = {k: v for k, v in weight_factors.items() 
                      if not MIN_WEIGHT <= v <= MAX_WEIGHT}
    if invalid_weights:
        raise ValueError(f"Weight factors out of range [{MIN_WEIGHT}, {MAX_WEIGHT}]: {invalid_weights}")

class PathNormalizer:
    """Handles path normalization and classification."""
    
    def __init__(self, src_dir: str, tests_dir: Optional[str], base_dir: Optional[str] = None):
        """Initialize path normalizer.
        
        Args:
            src_dir: The source directory path
            tests_dir: Optional tests directory path
            base_dir: Optional base directory path
        """
        self.src_dir = src_dir
        self.tests_dir = tests_dir
        self.base_dir = base_dir
        self._path_cache = {}

    def normalize(self, path: Union[str, Path], for_lookup: bool = False) -> str:
        """Normalize a file path for consistent comparison.
        
        Args:
            path: The path to normalize
            for_lookup: Whether to add .py extension if missing
        """
        path_str = str(path).replace("\\", "/")
        cache_key = f"{path_str}:{for_lookup}"
        
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]
        
        # Remove base directory if present
        if self.base_dir and path_str.startswith(self.base_dir):
            path_str = path_str[len(self.base_dir):].lstrip('/')

        # Remove any leading ./ or ./src/
        path_str = re.sub(r"^\./?", "", path_str)
        path_str = re.sub(r"^src/", "", path_str)
        path_str = re.sub(r"^tests/", "", path_str)

        # Determine if this is a test file
        is_test = (
            path_str.startswith("test_") or
            path_str.endswith("_test.py") or
            "tests/" in path_str or
            "test/" in path_str
        )

        # Add appropriate prefix
        if is_test:
            if not path_str.startswith("tests/"):
                path_str = f"tests/{path_str}"
        else:
            if not path_str.startswith("src/"):
                path_str = f"src/{path_str}"

        # Add .py extension if needed and for_lookup is True
        if for_lookup and not path_str.endswith(".py"):
            path_str = f"{path_str}.py"

        self._path_cache[cache_key] = path_str
        return path_str

    def normalize_import_to_path(self, import_name: str) -> str:
        """Convert an import name to a file path.
        
        Args:
            import_name: The import name to convert
            
        Returns:
            The normalized file path
        """
        # Return relative imports as is
        if import_name.startswith('.'):
            return import_name
            
        # Convert dots to slashes
        path = import_name.replace('.', '/')
        
        # Add .py extension if not present
        if not path.endswith('.py'):
            path = f"{path}.py"
            
        # Handle test modules
        if path.startswith('tests/') or path.startswith('test_'):
            if not path.startswith('tests/'):
                path = f"tests/{path}"
        else:
            # Non-test modules should be in src
            if not path.startswith('src/'):
                path = f"src/{path}"
                
        return path

    def resolve_relative_import(self, import_name: str, current_file: str) -> Optional[str]:
        """Resolve a relative import to an absolute path.
        
        Args:
            import_name: The relative import to resolve
            current_file: The file containing the import
            
        Returns:
            The normalized path to the resolved import, or None if not found
        """
        if not import_name.startswith("."):
            return None

        # Count leading dots to determine how many levels to go up
        dots = len(re.match(r"^\.+", import_name).group())
        import_path = import_name[dots:]

        # Get the directory path of the current file
        current_dir = Path(current_file).parent
        
        # Go up one level for each dot after the first
        for _ in range(dots - 1):
            if current_dir.name in ['src', 'tests']:
                return None
            current_dir = current_dir.parent

        # If no remaining import path, look for __init__.py
        if not import_path:
            init_path = str(current_dir / '__init__.py')
            normalized = self.normalize(init_path, for_lookup=True)
            return normalized

        # Construct target path
        target_path = current_dir / import_path.replace('.', '/')
        
        # Try both module.py and module/__init__.py
        module_path = str(target_path) + '.py'
        init_path = str(target_path / '__init__.py')
        
        # Normalize and return the first path that exists
        module_normalized = self.normalize(module_path, for_lookup=True)
        init_normalized = self.normalize(init_path, for_lookup=True)
        
        return module_normalized or init_normalized

    def normalize_for_import(self, import_name: str) -> str:
        """Normalize an import name for comparison."""
        # Remove src/ or tests/ prefix
        if import_name.startswith('src/'):
            import_name = import_name[4:]
        elif import_name.startswith('tests/'):
            import_name = import_name[6:]

        # Remove .py extension
        if import_name.endswith('.py'):
            import_name = import_name[:-3]

        # Convert slashes to dots
        return import_name.replace('/', '.')

    def get_import_variants(self, import_name: str) -> List[str]:
        """Get possible variants of an import path.
        
        Args:
            import_name: The import name to get variants for
        
        Returns:
            List of possible import path variants
        """
        variants = []
        base_path = self.normalize_for_import(import_name)
        
        # Add base path with .py extension
        variants.append(f"{base_path}.py")
        
        # Add __init__.py variant
        variants.append(f"{base_path}/__init__.py")
        
        # For test files, try both with and without test_ prefix
        if 'test' in base_path:
            if base_path.startswith('tests/'):
                # Try without tests/ prefix
                no_prefix = base_path.replace('tests/', '', 1)
                variants.append(f"{no_prefix}.py")
                variants.append(f"{no_prefix}/__init__.py")
            else:
                # Try with tests/ prefix
                with_prefix = f"tests/{base_path}"
                variants.append(f"{with_prefix}.py")
                variants.append(f"{with_prefix}/__init__.py")
        
        return variants

    def is_test_file(self, path: Union[str, Path]) -> bool:
        """Check if a file is a test file."""
        path_str = str(path)
        return (
            path_str.startswith("test_") or
            path_str.endswith("_test.py") or
            "tests/" in path_str or
            "test/" in path_str
        )

    def get_module_name(self, path: str) -> str:
        """Convert a file path to a module name."""
        normalized = self.normalize(path)
        # Remove src/ or tests/ prefix
        if normalized.startswith("src/"):
            normalized = normalized[4:]
        elif normalized.startswith("tests/"):
            normalized = normalized[6:]
        # Remove .py extension
        if normalized.endswith(".py"):
            normalized = normalized[:-3]
        # Convert slashes to dots
        return normalized.replace("/", ".")

    def get_relative_import(self, source: str, target: str) -> str:
        """Get the relative import path from source to target."""
        source_parts = self.normalize(source).split("/")
        target_parts = self.normalize(target).split("/")
        
        # Find common prefix
        common = 0
        for s, t in zip(source_parts[:-1], target_parts):
            if s != t:
                break
            common += 1
        
        # Build relative path
        up_levels = len(source_parts) - common - 1
        relative_parts = ["." * (up_levels + 1)]
        if up_levels == 0:
            relative_parts = ["."]
        
        relative_parts.extend(target_parts[common:])
        if relative_parts[-1].endswith(".py"):
            relative_parts[-1] = relative_parts[-1][:-3]
            
        return ".".join(relative_parts)

class ExportFormat(str, Enum):
    """Export format options."""
    HTML = 'html'
    MARKDOWN = 'markdown'
    JSON = 'json'
    CSV = 'csv'

@dataclass
class ValidationError(Exception):
    """Represents a validation error."""
    error_type: str
    message: str
    file: Optional[Union[str, Path]] = None
    line_number: Optional[int] = None
    context: Optional[str] = None

    @property
    def file_path(self) -> str:
        """Return the file path as a string."""
        return str(self.file) if self.file else ""

    def __str__(self) -> str:
        """Return a string representation of the error."""
        parts = []
        if self.error_type:
            parts.append(f"[{self.error_type}]")
        if self.file:
            parts.append(f"in {self.file}")
        if self.line_number is not None and self.line_number > 0:
            parts.append(f"at line {self.line_number}")
        if self.message:
            parts.append(self.message)
        if self.context:
            parts.append(f"({self.context})")
        return " ".join(parts)


@dataclass
class ImportUsage:
    """Represents import usage statistics for a file."""
    file: Path
    imports: Set[str] = field(default_factory=set)
    invalid_imports: Set[str] = field(default_factory=set)
    unused_imports: Set[str] = field(default_factory=set)
    relative_imports: Set[str] = field(default_factory=set)
    complexity_score: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def file_path(self) -> str:
        """Return the file path as a string."""
        return str(self.file)

    @property
    def name(self) -> str:
        """Return the file name."""
        return self.file.name


@dataclass
class ImportInfo:
    """Information about an import statement."""
    name: str
    alias: str | None = None
    is_relative: bool = False
    is_used: bool = False
    lineno: int = 0


@dataclass
class ImportStats:
    """
    Tracks various import-related metrics and calculates a complexity score.
    
    Attributes:
        total_imports (int): Total number of import statements across all files
        unique_imports (int): Number of distinct imports used
        stdlib_imports (int): Number of imports from Python's standard library
        thirdparty_imports (int): Number of imports from third-party packages
        local_imports (int): Number of imports from the local project
        relative_imports_count (int): Number of relative imports
        invalid_imports_count (int): Number of imports that couldn't be resolved
        unused_imports_count (int): Number of imported modules that aren't used
        edges_count (int): Number of edges in the import graph
        circular_refs_count (int): Number of circular dependencies detected
        total_nodes (int): Total number of nodes in the import graph
        total_edges (int): Total number of edges in the import graph
        complexity_score (float): Weighted score based on various metrics
        most_common (list): Top 10 most commonly used imports across files
        files_with_most_imports (list): Top 10 files with the most imports
    """
    
    total_imports: int = 0
    unique_imports: int = 0
    stdlib_imports: int = 0
    thirdparty_imports: int = 0
    local_imports: int = 0
    relative_imports_count: int = 0
    invalid_imports_count: int = 0
    unused_imports_count: int = 0
    edges_count: int = 0
    circular_refs_count: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    complexity_score: float = 0.0
    most_common: List[Tuple[str, int]] = field(default_factory=list)
    files_with_most_imports: List[Tuple[str, int]] = field(default_factory=list)

    def add_import(self, import_name: str, is_relative: bool = False, is_valid: bool = True, is_used: bool = True):
        """Add an import and update relevant counters."""
        self.total_imports += 1
        
        if import_name not in {imp for imp, _ in self.most_common}:
            self.unique_imports += 1
        
        if is_relative:
            self.relative_imports_count += 1
        
        if not is_valid:
            self.invalid_imports_count += 1
            return
            
        if not is_used:
            self.unused_imports_count += 1
            
        # Categorize the import
        base_module = import_name.split('.')[0]
        if base_module in sys.stdlib_module_names:
            self.stdlib_imports += 1
        elif base_module in {'src', 'tests'}:
            self.local_imports += 1
        else:
            self.thirdparty_imports += 1

    def calculate_complexity(self, weight_factors: Optional[Dict[str, float]] = None) -> float:
        """Calculate complexity score based on various factors.

        The complexity score is a weighted sum of different import metrics. Each metric
        contributes to the final score based on its associated weight factor. Higher
        scores indicate more complex or problematic import structures.

        The calculation considers:
        - Total number of imports (quantity of dependencies)
        - Number of unique imports (dependency diversity)
        - Number of edges in import graph (module coupling)
        - Invalid imports (broken dependencies)
        - Unused imports (code cleanliness)
        - Relative imports (import style)
        - Circular references (architectural issues)

        Args:
            weight_factors: Optional dictionary of weight factors for each metric.
                If None, uses DEFAULT_WEIGHT_FACTORS from the module.
                Custom weights must include all required factors and be within
                valid range [MIN_WEIGHT, MAX_WEIGHT].

        Returns:
            float: The calculated complexity score, rounded to 1 decimal place.
            Higher scores indicate more complex or problematic import structures.

        Raises:
            ValueError: If weight_factors is missing required keys or contains
                values outside the valid range.
        """
        # Use provided weights or defaults
        weights = weight_factors if weight_factors is not None else DEFAULT_WEIGHT_FACTORS.copy()
        
        # Validate weights
        validate_weight_factors(weights)
        
        # Calculate weighted score
        score = 0.0
        score += self.total_imports * weights['total_imports']
        score += self.unique_imports * weights['unique_imports']
        score += self.edges_count * weights['edges']
        score += self.invalid_imports_count * weights['invalid_imports']
        score += self.unused_imports_count * weights['unused_imports']
        score += self.relative_imports_count * weights['relative_imports']
        score += self.circular_refs_count * weights['circular_refs']

        self.complexity_score = round(score, 1)
        return self.complexity_score

    def update_graph_stats(self, import_graph: nx.DiGraph):
        """Update statistics based on the import graph."""
        self.total_nodes = import_graph.number_of_nodes()
        self.total_edges = import_graph.number_of_edges()
        self.edges_count = self.total_edges
        
        try:
            cycles = list(nx.simple_cycles(import_graph))
            self.circular_refs_count = len(cycles)
        except Exception:
            self.circular_refs_count = 0

    def __str__(self) -> str:
        """Return a string representation of the stats."""
        return (
            f"Total Imports: {self.total_imports}\n"
            f"Unique Imports: {self.unique_imports}\n"
            f"Standard Library Imports: {self.stdlib_imports}\n"
            f"Third-party Imports: {self.thirdparty_imports}\n"
            f"Local Project Imports: {self.local_imports}\n"
            f"Invalid Imports: {self.invalid_imports_count}\n"
            f"Unused Imports: {self.unused_imports_count}\n"
            f"Relative Imports: {self.relative_imports_count}\n"
            f"Circular References: {self.circular_refs_count}\n"
            f"Total Graph Nodes: {self.total_nodes}\n"
            f"Total Graph Edges: {self.total_edges}\n"
            f"Complexity Score: {self.complexity_score:.2f}\n"
            f"Most Common Imports: {self.most_common}\n"
            f"Files with Most Imports: {self.files_with_most_imports}\n"
            f"Edges Count: {self.edges_count}\n"
            f"Circular References Count: {self.circular_refs_count}\n"
        )


# Type aliases for clarity
CircularRefs = Dict[str, List[List[str]]]  # File -> List of import chains
ImportGraph = Dict[str, Set[str]]  # File -> Set of imports

from .config import ImportValidatorConfig

@dataclass
class ValidationResults:
    """Results of import validation."""
    def __init__(self):
        """Initialize validation results."""
        self.imports: Dict[str, Set[str]] = defaultdict(set)
        self.relative_imports: Dict[str, Set[str]] = defaultdict(set)
        self.invalid_imports: Dict[str, Set[str]] = defaultdict(set)
        self.unused_imports: Dict[str, Set[str]] = defaultdict(set)
        self.errors: List[ValidationError] = []
        self.stats = ImportStats()
        self.import_graph = nx.DiGraph()
        self.circular_refs: Dict[str, List[List[str]]] = {}
        self.module_definitions: Dict[str, ast.Module] = {}
        self.logger = logging.getLogger(__name__)

    def update_stats(self) -> None:
        """Update statistics based on current results."""
        # Reset counters
        self.stats = ImportStats()

        # Count total and unique imports
        all_imports = set()
        import_counts = Counter()
        file_import_counts = Counter()
        
        # First pass: Count all imports and categorize them
        for file_path, imports in self.imports.items():
            file_import_counts[file_path] = len(imports)
            
            for imp in imports:
                # Update counters
                import_counts[imp] += 1
                all_imports.add(imp)
                
                # Categorize imports
                base_module = imp.split('.')[0]
                if base_module in sys.stdlib_module_names:
                    self.stats.stdlib_imports += 1
                elif base_module in {'src', 'tests'}:
                    self.stats.local_imports += 1
                else:
                    self.stats.thirdparty_imports += 1

        # Update total imports and unique imports
        self.stats.total_imports = sum(file_import_counts.values())
        self.stats.unique_imports = len(all_imports)
        
        # Get most common imports (top 10)
        self.stats.most_common = import_counts.most_common(10)
        
        # Get files with most imports (top 10)
        self.stats.files_with_most_imports = file_import_counts.most_common(10)

        # Count relative imports
        for imports in self.relative_imports.values():
            self.stats.relative_imports_count += len(imports)

        # Count invalid imports
        for imports in self.invalid_imports.values():
            self.stats.invalid_imports_count += len(imports)

        # Count unused imports
        for imports in self.unused_imports.values():
            self.stats.unused_imports_count += len(imports)

        # Update graph statistics
        if hasattr(self, 'import_graph'):
            try:
                self.stats.total_nodes = self.import_graph.number_of_nodes()
                self.stats.total_edges = self.import_graph.number_of_edges()
                self.stats.edges_count = self.stats.total_edges
                
                # Count circular references
                try:
                    cycles = list(nx.simple_cycles(self.import_graph))
                    self.stats.circular_refs_count = len(cycles)
                except Exception as e:
                    self.logger.error(f"Error finding circular references: {e}")
                    self.stats.circular_refs_count = 0
            except Exception as e:
                self.logger.error(f"Error calculating graph stats: {e}")
                self.stats.total_edges = 0
                self.stats.edges_count = 0
                self.stats.circular_refs_count = 0

        # Calculate complexity score using default weights
        self.stats.complexity_score = self.stats.calculate_complexity()

    def add_error(self, error: ValidationError) -> None:
        """Add an error to the validation results."""
        self.errors.append(error)

    def get_all_errors(self) -> List[ValidationError]:
        """Get all validation errors.
        
        Returns:
            List of all validation errors, including errors from imports, circular references,
            and any other validation issues.
        """
        all_errors = self.errors.copy()

        # Add errors for invalid imports
        for file_path, imports in self.invalid_imports.items():
            for import_name in imports:
                all_errors.append(ValidationError(
                    file=file_path,
                    error_type='InvalidImport',
                    message=f'Could not resolve import: {import_name}'
                ))

        # Add errors for unused imports
        for file_path, imports in self.unused_imports.items():
            for import_name in imports:
                all_errors.append(ValidationError(
                    file=file_path,
                    error_type='UnusedImport',
                    message=f'Import is never used: {import_name}'
                ))

        # Add errors for circular references
        for file_path, cycles in self.circular_refs.items():
            for cycle in cycles:
                all_errors.append(ValidationError(
                    file=file_path,
                    error_type='CircularImport',
                    message=f'Circular dependency detected: {" -> ".join(cycle)}'
                ))

        return all_errors

@dataclass
class FileStatus:
    """Status information for a file."""
    path: str
    exists: bool = False
    is_test: bool = False
    import_count: int = 0
    invalid_imports: int = 0
    circular_refs: int = 0
    relative_imports: int = 0

@dataclass
class ImportRelationship:
    """Tracks relationships between files based on imports."""
    file_path: str
    imports: Set[str] = field(default_factory=set)  # Files this file imports
    imported_by: Set[str] = field(default_factory=set)  # Files that import this file
    invalid_imports: Set[str] = field(default_factory=set)  # Invalid/missing imports
    relative_imports: Set[str] = field(default_factory=set)  # Relative imports
    circular_refs: Set[str] = field(default_factory=set)  # Files involved in circular refs
    stdlib_imports: Set[str] = field(default_factory=set)  # Standard library imports
    thirdparty_imports: Set[str] = field(default_factory=set)  # Third-party package imports
    local_imports: Set[str] = field(default_factory=set)  # Local project imports

    def add_import(self, target: str, import_type: str):
        """Add an import relationship."""
        self.imports.add(target)
        if import_type == 'stdlib':
            self.stdlib_imports.add(target)
        elif import_type == 'thirdparty':
            self.thirdparty_imports.add(target)
        elif import_type == 'invalid':
            self.invalid_imports.add(target)
        elif import_type == 'relative':
            self.relative_imports.add(target)
        else:
            self.local_imports.add(target)

    def add_circular_ref(self, ref_path: str):
        """Add a circular reference."""
        self.circular_refs.add(ref_path)

    def get_stats(self) -> Dict[str, int]:
        """Get import statistics."""
        return {
            'total_imports': len(self.imports),
            'invalid_imports': len(self.invalid_imports),
            'relative_imports': len(self.relative_imports),
            'circular_refs': len(self.circular_refs),
            'stdlib_imports': len(self.stdlib_imports),
            'thirdparty_imports': len(self.thirdparty_imports),
            'local_imports': len(self.local_imports)
        }
