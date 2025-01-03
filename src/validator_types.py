"""Type definitions for import validator."""
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, TypeAlias
import ast

# Type aliases for complex types
ImportFixes: TypeAlias = Dict[str, List[Tuple[str, str, str]]]
ModuleDefinitions: TypeAlias = Dict[str, str]
ImportGraph: TypeAlias = Dict[str, Set[str]]
CircularRefs: TypeAlias = Dict[str, List[List[str]]]


class ExportFormat(Enum):
    """Available export formats for reports."""
    MARKDOWN = auto()
    HTML = auto()
    JSON = auto()
    CSV = auto()


@dataclass
class ImportUsage:
    """Tracks usage information for an imported symbol."""
    imported_name: str
    import_node: ast.AST
    usages: List[ast.AST] = field(default_factory=list)
    is_used: bool = False


@dataclass
class ValidationError:
    """Represents an error encountered during validation."""
    file: Path
    error_type: str
    message: str
    line_number: Optional[int] = None
    context: Optional[str] = None


@dataclass
class ImportStats:
    """Statistics about imports in the codebase."""
    total_imports: int = 0
    unique_imports: int = 0
    most_common: List[Tuple[str, int]] = field(default_factory=list)
    complexity_score: float = 0.0
    files_with_most_imports: List[Tuple[str, int]] = field(default_factory=list)
    invalid_imports_count: int = 0
    unused_imports_count: int = 0
    relative_imports_count: int = 0
    circular_refs_count: int = 0
    total_nodes: int = 0  # Total number of files in the import graph
    total_edges: int = 0  # Total number of import relationships


@dataclass
class AnalysisResult:
    """Results of import analysis for a single file."""
    file_path: Path
    imports: Set[str] = field(default_factory=set)
    invalid_imports: Set[str] = field(default_factory=set)
    unused_imports: Set[str] = field(default_factory=set)
    relative_imports: Set[str] = field(default_factory=set)
    complexity_score: float = 0.0
    errors: List[ValidationError] = field(default_factory=list) 