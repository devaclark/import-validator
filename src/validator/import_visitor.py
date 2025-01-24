"""AST visitor for collecting import information."""
import ast
from pathlib import Path
from typing import List, Set, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .validator import AsyncImportValidator

from .validator_types import ImportInfo

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
        self.used_names: Set[str] = set()
        
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