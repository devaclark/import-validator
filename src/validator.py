"""Main import validator implementation."""
import ast
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import asyncio
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

from .async_utils import (
    AsyncCache,
    find_python_files_async,
    parse_file_async
)
from .config import ImportValidatorConfig
from .error_handling import ErrorHandler, ConsoleErrorHandler
from .exporters import create_exporter
from .validator_types import (
    AnalysisResult,
    CircularRefs,
    ExportFormat,
    ImportGraph,
    ImportStats,
    ImportUsage,
    ValidationError
)
from .visualization import create_visualizer, NetworkXVisualizer


class AsyncImportValidator:
    """Asynchronous import validator implementation."""
    
    def __init__(
        self,
        src_dir: str,
        tests_dir: str,
        config: Optional[ImportValidatorConfig] = None,
        error_handler: Optional[ErrorHandler] = None
    ):
        self.src_dir = Path(src_dir)
        self.tests_dir = Path(tests_dir)
        self.config = config or ImportValidatorConfig()
        self.error_handler = error_handler or ConsoleErrorHandler()
        
        # Analysis state
        self.module_definitions: Dict[str, str] = {}
        self.import_graph: ImportGraph = defaultdict(set)
        self.invalid_imports: Dict[str, Set[str]] = defaultdict(set)
        self.unused_imports: Dict[str, Set[str]] = defaultdict(set)
        self.relative_imports: Dict[str, Set[str]] = defaultdict(set)
        self.import_counts = Counter()
        self.file_import_counts: Dict[str, int] = defaultdict(int)
        self.import_usages: Dict[str, Dict[str, ImportUsage]] = defaultdict(dict)
        self.circular_refs: CircularRefs = {}
        
        # Caching
        self.cache = AsyncCache()

    async def extract_definitions(self, file_path: Path) -> None:
        """Extract class and function definitions from a file."""
        try:
            tree = await parse_file_async(file_path)
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    self.module_definitions[node.name] = str(file_path)
        except Exception as e:
            self.error_handler.handle_error(ValidationError(
                file=file_path,
                error_type="ParseError",
                message=f"Failed to parse file: {str(e)}"
            ))

    @lru_cache(maxsize=1000)
    def find_module_path(self, import_path: str, current_file: str) -> Optional[str]:
        """Find the actual module path for an import."""
        parts = import_path.split('.')
        
        # Handle relative imports
        if import_path.startswith('.'):
            current_dir = Path(current_file).parent
            dots = len(parts[0])
            for _ in range(dots):
                if current_dir.name:  # Only move up if not at root
                    current_dir = current_dir.parent
            parts = parts[1:]
            base_path = current_dir
            
            # For relative imports, ensure we're not detecting circular refs to self
            if str(current_dir / '__init__.py') == current_file:
                return None
        else:
            # Handle absolute imports
            if parts[0] in ('src', 'tests'):
                base_path = self.src_dir if parts[0] == 'src' else self.tests_dir
                parts = parts[1:]
            else:
                return None
        
        # Try to find the module
        current_path = base_path
        for part in parts[:-1]:
            current_path = current_path / part
            if not (current_path / '__init__.py').exists() and not current_path.with_suffix('.py').exists():
                return None
        
        # Check for the final module
        if parts:
            final_part = parts[-1]
            module_file = current_path / f"{final_part}.py"
            if module_file.exists():
                return str(module_file)
        
        # Check if it's in __init__.py
        init_file = current_path / '__init__.py'
        if init_file.exists() and init_file != Path(current_file):  # Don't return self
            return str(init_file)
            
        return None

    async def analyze_imports(self, file_path: Path) -> AnalysisResult:
        """Analyze imports in a file."""
        result = AnalysisResult(file_path=file_path)
        
        try:
            tree = await parse_file_async(file_path)
            
            # Track all names that are used in the file
            name_usage = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    name_usage.add(node.id)
                elif isinstance(node, ast.Attribute):
                    name_usage.add(node.attr)
            
            # Convert file path to module path
            if 'src' in file_path.parts:
                base_path = self.src_dir
                base_module = 'src'
            else:
                base_path = self.tests_dir
                base_module = 'tests'
            
            try:
                relative_path = file_path.relative_to(base_path)
                current_module = f"{base_module}.{'.'.join(relative_path.parent.parts)}"
            except ValueError:
                current_module = str(file_path)
            
            # Analyze import nodes
            for node in ast.walk(tree):
                match node:
                    case ast.Import(names=names):
                        for name in names:
                            imported_name = name.asname or name.name
                            result.imports.add(name.name)
                            
                            # Convert module name to file path
                            module_path = self.find_module_path(name.name, str(file_path))
                            if module_path:
                                self.import_graph[str(file_path)].add(module_path)
                            
                            self.import_counts[name.name] += 1
                            self.file_import_counts[str(file_path)] += 1
                            
                            # Check if import is used
                            if imported_name not in name_usage:
                                result.unused_imports.add(imported_name)
                            
                            if not await self.is_valid_import(name.name):
                                result.invalid_imports.add(name.name)
                                if module_path:
                                    self.invalid_imports[str(file_path)].add(module_path)
                                else:
                                    self.invalid_imports[str(file_path)].add(name.name)
                    
                    case ast.ImportFrom(module=module, names=names, level=level):
                        if module is None:
                            module_name = current_module
                        else:
                            # Handle relative imports
                            if level > 0:
                                parts = current_module.split('.')
                                if len(parts) >= level:
                                    parent_module = '.'.join(parts[:-level])
                                    if module:
                                        module_name = f"{parent_module}.{module}"
                                    else:
                                        module_name = parent_module
                                else:
                                    module_name = module
                                result.relative_imports.add(
                                    f"{'.' * level}{module if module else ''}"
                                )
                            else:
                                module_name = module
                        
                        result.imports.add(module_name)
                        
                        # Convert module name to file path
                        module_path = self.find_module_path(module_name, str(file_path))
                        if module_path:
                            self.import_graph[str(file_path)].add(module_path)
                        
                        self.import_counts[module_name] += 1
                        self.file_import_counts[str(file_path)] += 1
                        
                        if not await self.is_valid_import(module_name):
                            result.invalid_imports.add(module_name)
                            if module_path:
                                self.invalid_imports[str(file_path)].add(module_path)
                            else:
                                self.invalid_imports[str(file_path)].add(module_name)
                        
                        # Check each imported name
                        for alias in names:
                            imported_name = alias.asname or alias.name
                            if imported_name not in name_usage:
                                result.unused_imports.add(
                                    f"{module_name}.{imported_name}"
                                )
            
            # Calculate complexity score
            result.complexity_score = self.calculate_complexity(result)
            
        except Exception as e:
            self.error_handler.handle_error(ValidationError(
                file=file_path,
                error_type="AnalysisError",
                message=f"Failed to analyze imports: {str(e)}"
            ))
        
        return result

    def calculate_complexity(self, result: AnalysisResult) -> float:
        """Calculate complexity score for a file."""
        return (
            len(result.imports) * self.config.weight_factors['imports'] +
            len(result.relative_imports) * self.config.weight_factors['relative'] +
            len(result.unused_imports) * self.config.weight_factors['unused'] +
            (1 if result.file_path in self.circular_refs else 0) * self.config.weight_factors['circular']
        )

    async def is_valid_import(self, module_name: str) -> bool:
        """Check if an import is valid."""
        # Check cache first
        cached_result = await self.cache.get(f"valid_import:{module_name}")
        if cached_result is not None:
            return cached_result
        
        result = False
        try:
            # Handle relative imports and local modules
            if module_name.startswith('.'):
                result = True
            elif module_name.startswith(('src.', 'tests.')):
                result = True
            elif any(module_name.startswith(f"{base}.") for base in ['src', 'tests']):
                result = True
            # Check if it's in our valid packages list
            elif module_name.split('.')[0] in self.config.valid_packages:
                result = True
            else:
                # Handle standard library and installed packages
                try:
                    __import__(module_name.split('.')[0])
                    result = True
                except ImportError:
                    result = False
        except Exception:
            result = False
        
        # Cache the result
        await self.cache.set(f"valid_import:{module_name}", result)
        return result

    def find_circular_references(self) -> CircularRefs:
        """Find circular references in the import graph."""
        def find_cycles(node: str, visited: Set[str], path: List[str]) -> List[List[str]]:
            if node in visited:
                start = path.index(node)
                return [path[start:]]
            visited.add(node)
            path.append(node)
            cycles = []
            for neighbor in self.import_graph[node]:
                if neighbor in self.import_graph:
                    cycles.extend(find_cycles(neighbor, visited.copy(), path.copy()))
            return cycles

        file_cycles: CircularRefs = {}
        for node in self.import_graph:
            cycles = find_cycles(node, set(), [])
            if cycles:
                file_cycles[node] = cycles
        return file_cycles

    def generate_stats(self) -> ImportStats:
        """Generate statistics about import patterns."""
        # Calculate total edges (sum of all import relationships)
        total_edges = sum(len(imports) for imports in self.import_graph.values())
        
        # Calculate total nodes (unique files in the graph)
        nodes = set(self.import_graph.keys())  # Files that import others
        for imports in self.import_graph.values():  # Files that are imported
            nodes.update(imports)
        
        return ImportStats(
            total_imports=sum(self.import_counts.values()),
            unique_imports=len(self.import_counts),
            most_common=self.import_counts.most_common(10),
            complexity_score=sum(
                self.file_import_counts.values()
            ) / len(self.file_import_counts) if self.file_import_counts else 0.0,
            files_with_most_imports=sorted(
                self.file_import_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            invalid_imports_count=sum(len(imports) for imports in self.invalid_imports.values()),
            unused_imports_count=sum(len(imports) for imports in self.unused_imports.values()),
            relative_imports_count=sum(len(imports) for imports in self.relative_imports.values()),
            circular_refs_count=len(self.circular_refs),
            total_nodes=len(nodes),
            total_edges=total_edges
        )

    async def validate_all(self) -> None:
        """Validate all imports in the project."""
        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
        ) as progress:
            # Find all Python files
            task = progress.add_task("Finding Python files...", total=None)
            src_files = await find_python_files_async(
                self.src_dir,
                self.config.ignore_patterns
            )
            test_files = await find_python_files_async(
                self.tests_dir,
                self.config.ignore_patterns
            )
            progress.update(task, completed=True)
            
            # Extract definitions
            task = progress.add_task(
                "Extracting definitions...",
                total=len(src_files) + len(test_files)
            )
            for file in src_files | test_files:
                await self.extract_definitions(file)
                progress.update(task, advance=1)
            
            # Analyze imports
            task = progress.add_task(
                "Analyzing imports...",
                total=len(src_files) + len(test_files)
            )
            analysis_tasks = []
            for file in src_files | test_files:
                analysis_tasks.append(self.analyze_imports(file))
            
            results = await asyncio.gather(*analysis_tasks)
            for result in results:
                # Update global state with results
                self.invalid_imports[str(result.file_path)] = result.invalid_imports
                self.unused_imports[str(result.file_path)] = result.unused_imports
                self.relative_imports[str(result.file_path)] = result.relative_imports
                progress.update(task, advance=1)
            
            # Find circular references
            task = progress.add_task("Finding circular references...", total=None)
            self.circular_refs = self.find_circular_references()
            progress.update(task, completed=True)

    def export_results(
        self,
        format: ExportFormat,
        output_file: Path,
        visualize: bool = True
    ) -> None:
        """Export validation results."""
        # Create exporter
        exporter = create_exporter(format)
        
        # Export results
        exporter.export(
            stats=self.generate_stats(),
            import_graph=self.import_graph,
            invalid_imports=self.invalid_imports,
            unused_imports=self.unused_imports,
            relative_imports=self.relative_imports,
            circular_refs=self.circular_refs,
            errors=self.error_handler.get_errors(),
            output_file=output_file
        )
        
        # Generate visualization if requested
        if visualize:
            visualizer = create_visualizer(format)
            # Set max_edges from config if available
            if hasattr(visualizer, 'max_edges'):
                visualizer.max_edges = self.config.max_edges_per_diagram
            
            # Handle different visualization outputs
            if isinstance(visualizer, NetworkXVisualizer):
                # NetworkX produces a PNG file
                viz_file = output_file.with_name(output_file.stem + '_graph.png')
            else:
                # D3 and Mermaid produce HTML/MD files
                viz_file = output_file.with_suffix('.viz' + output_file.suffix)
            
            visualizer.visualize(
                import_graph=self.import_graph,
                invalid_imports=self.invalid_imports,
                circular_refs={(s, t) for s, refs in self.circular_refs.items() for cycle in refs for t in cycle},
                output_file=viz_file
            ) 