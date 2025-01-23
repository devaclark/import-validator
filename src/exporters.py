"""Export functionality for validation results."""
import csv
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Set

from src.validator.validator_types import (
    CircularRefs,
    ExportFormat,
    ImportStats,
    ValidationError,
    ValidationResults
)
from src.visualization import create_visualizer


class BaseExporter(ABC):
    """Base class for exporters."""
    
    @abstractmethod
    def export(self, results: ValidationResults, output_file: Path, visualize: bool = True) -> None:
        """Export validation results.
        
        Args:
            results: The validation results to export
            output_file: Path to save the exported results
            visualize: Whether to include visualizations in the export
            
        Raises:
            ValueError: If the results cannot be exported
            IOError: If the output file cannot be written
            TypeError: If the results object is invalid
        """
        raise NotImplementedError("Exporter subclasses must implement export method")


class JSONExporter(BaseExporter):
    """JSON exporter for validation results."""
    
    def export(self, results: ValidationResults, output_file: Path, visualize: bool = True) -> None:
        """Export validation results to JSON."""
        data = {
            'stats': {
                'total_imports': results.stats.total_imports,
                'unique_imports': results.stats.unique_imports,
                'complexity_score': results.stats.complexity_score,
                'invalid_imports_count': results.stats.invalid_imports_count,
                'unused_imports_count': results.stats.unused_imports_count,
                'relative_imports_count': results.stats.relative_imports_count,
                'circular_refs_count': results.stats.circular_refs_count,
                'most_common': results.stats.most_common,
                'files_with_most_imports': results.stats.files_with_most_imports,
                'total_nodes': results.stats.total_nodes,
                'total_edges': results.stats.total_edges
            },
            'import_graph': {k: sorted(list(v)) for k, v in sorted(results.import_graph.items())},
            'invalid_imports': {k: sorted(list(v)) for k, v in sorted(results.invalid_imports.items())},
            'unused_imports': {k: sorted(list(v)) for k, v in sorted(results.unused_imports.items())},
            'relative_imports': {k: sorted(list(v)) for k, v in sorted(results.relative_imports.items())},
            'circular_refs': {k: sorted(v, key=lambda x: tuple(x)) for k, v in sorted(results.circular_refs.items())},
            'errors': sorted([
                {
                    'file': str(error.file_path),
                    'error_type': error.error_type,
                    'message': error.message,
                    'line_number': error.line_number,
                    'context': error.context
                }
                for error in results.errors
            ], key=lambda x: (x['file'], x['line_number'] or 0))
        }
        
        # Write JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, default=str)


class MarkdownExporter(BaseExporter):
    """Markdown exporter for validation results."""
    
    def export(self, results: ValidationResults, output_file: Path, visualize: bool = True) -> None:
        """Export validation results to Markdown."""
        content = [
            "# Import Analysis Report\n",
            "## Statistics\n",
            f"- Total imports: {results.stats.total_imports}",
            f"- Unique imports: {results.stats.unique_imports}",
            f"- Complexity score: {results.stats.complexity_score:.2f}",
            f"- Invalid imports: {results.stats.invalid_imports_count}",
            f"- Unused imports: {results.stats.unused_imports_count}",
            f"- Relative imports: {results.stats.relative_imports_count}",
            f"- Circular references: {results.stats.circular_refs_count}\n",
            "## Import Graph\n",
            f"- Total files: {results.stats.total_nodes}",
            f"- Total dependencies: {results.stats.total_edges}\n",
            "## Most Common Imports\n",
            *[f"- {name}: {count}" for name, count in sorted(results.stats.most_common)],
            "\n## Files with Most Imports\n",
            *[f"- {file}: {count}" for file, count in sorted(results.stats.files_with_most_imports)],
            "\n## Invalid Imports\n",
            *[f"- {file}:\n  - {', '.join(sorted(imports))}" for file, imports in sorted(results.invalid_imports.items())],
            "\n## Unused Imports\n",
            *[f"- {file}:\n  - {', '.join(sorted(imports))}" for file, imports in sorted(results.unused_imports.items())],
            "\n## Relative Imports\n",
            *[f"- {file}:\n  - {', '.join(sorted(imports))}" for file, imports in sorted(results.relative_imports.items())],
            "\n## Circular References\n",
            *[f"- {' -> '.join(chain)}" for chains in results.circular_refs.values() for chain in sorted(chains, key=lambda x: tuple(x))],
            "\n## Errors\n",
            *[f"- {error.file_path} (line {error.line_number}): {error.message}" for error in sorted(results.errors, key=lambda x: (x.file_path or '', x.line_number or 0))]
        ]
        
        # Write Markdown file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))


class HTMLExporter(BaseExporter):
    """HTML exporter for validation results."""
    
    def export(self, results: ValidationResults, output_file: Path, visualize: bool = True) -> None:
        """Export results to HTML format."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Import Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1, h2 {{ color: #333; }}
        .stats {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        .error {{ color: #c00; }}
        .warning {{ color: #f90; }}
    </style>
</head>
<body>
    <h1>Import Analysis Report</h1>
    
    <div class="stats">
        <h2>Statistics</h2>
        <p>Total Imports: {results.stats.total_imports}</p>
        <p>Unique Imports: {results.stats.unique_imports}</p>
        <p>Complexity Score: {results.stats.complexity_score:.1f}</p>
        <p>Invalid Imports: {results.stats.invalid_imports_count}</p>
        <p>Unused Imports: {results.stats.unused_imports_count}</p>
        <p>Relative Imports: {results.stats.relative_imports_count}</p>
        <p>Circular References: {results.stats.circular_refs_count}</p>
    </div>
    
    <h2>Import Graph Statistics</h2>
    <p>Total Files: {results.stats.total_nodes}</p>
    <p>Total Dependencies: {results.stats.total_edges}</p>
    
    {self._format_issues(results)}
</body>
</html>"""
        
        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write HTML file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Create visualization if requested
        if visualize:
            viz_file = output_file.parent / f"{output_file.stem}.viz.html"
            visualizer = create_visualizer(ExportFormat.HTML)
            visualizer.visualize(
                results.import_graph,
                results.invalid_imports,
                results.circular_refs,
                viz_file
            )
    
    def _format_issues(self, results: ValidationResults) -> str:
        """Format validation issues as HTML."""
        sections = []
        
        if results.invalid_imports:
            sections.append(f"""
            <h2 class="error">Invalid Imports</h2>
            <ul>
            {"".join(f"<li>{file}: {', '.join(imports)}</li>" for file, imports in results.invalid_imports.items())}
            </ul>""")
        
        if results.unused_imports:
            sections.append(f"""
            <h2 class="warning">Unused Imports</h2>
            <ul>
            {"".join(f"<li>{file}: {', '.join(imports)}</li>" for file, imports in results.unused_imports.items())}
            </ul>""")
        
        if results.relative_imports:
            sections.append(f"""
            <h2>Relative Imports</h2>
            <ul>
            {"".join(f"<li>{file}: {', '.join(imports)}</li>" for file, imports in results.relative_imports.items())}
            </ul>""")
        
        if results.circular_refs:
            sections.append(f"""
            <h2 class="error">Circular References</h2>
            <ul>
            {"".join(f"<li>{' -> '.join(chain)}</li>" for chains in results.circular_refs.values() for chain in chains)}
            </ul>""")

        errors = results.get_all_errors()
        if errors:
            sections.append(f"""
            <h2 class="error">Validation Errors</h2>
            <ul>
            {"".join(f"<li>{error.file_path or 'General'}: {error.error_type} - {error.message}</li>" for error in errors)}
            </ul>""")
        
        return "\n".join(sections)


class CSVExporter(BaseExporter):
    """CSV exporter for validation results."""
    
    def export(self, results: ValidationResults, output_file: Path, visualize: bool = True) -> None:
        """Export validation results to CSV files."""
        # Create directory for CSV files
        csv_dir = output_file.parent / output_file.stem
        csv_dir.mkdir(exist_ok=True)
        
        # Export stats
        with open(csv_dir / "stats.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Metric', 'Value'])
            writer.writerows([
                ['Total Imports', results.stats.total_imports],
                ['Unique Imports', results.stats.unique_imports],
                ['Complexity Score', results.stats.complexity_score],
                ['Invalid Imports Count', results.stats.invalid_imports_count],
                ['Unused Imports Count', results.stats.unused_imports_count],
                ['Relative Imports Count', results.stats.relative_imports_count],
                ['Circular References Count', results.stats.circular_refs_count],
                ['Total Nodes', results.stats.total_nodes],
                ['Total Edges', results.stats.total_edges]
            ])
        
        # Export most common imports
        with open(csv_dir / "most_common.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Import', 'Count'])
            writer.writerows(results.stats.most_common)
        
        # Export files with most imports
        with open(csv_dir / "files_with_most_imports.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Import Count'])
            writer.writerows(results.stats.files_with_most_imports)
        
        # Export invalid imports
        with open(csv_dir / "invalid_imports.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Invalid Import'])
            writer.writerows([
                [file, imp] for file, imports in results.invalid_imports.items()
                for imp in imports
            ])
        
        # Export unused imports
        with open(csv_dir / "unused_imports.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Unused Import'])
            writer.writerows([
                [file, imp] for file, imports in results.unused_imports.items()
                for imp in imports
            ])
        
        # Export relative imports
        with open(csv_dir / "relative_imports.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Relative Import'])
            writer.writerows([
                [file, imp] for file, imports in results.relative_imports.items()
                for imp in imports
            ])
        
        # Export circular references
        with open(csv_dir / "circular_refs.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Import Chain'])
            writer.writerows([
                [' -> '.join(chain)] for chains in results.circular_refs.values()
                for chain in chains
            ])
        
        # Export errors
        with open(csv_dir / "errors.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Line Number', 'Error Type', 'Message', 'Context'])
            writer.writerows([
                [error.file_path, error.line_number, error.error_type, error.message, error.context]
                for error in results.get_all_errors()
            ])


def create_exporter(format: ExportFormat) -> BaseExporter:
    """Create an exporter based on the specified format."""
    exporters = {
        ExportFormat.JSON: JSONExporter,
        ExportFormat.HTML: HTMLExporter,
        ExportFormat.MARKDOWN: MarkdownExporter,
        ExportFormat.CSV: CSVExporter
    }
    
    if not isinstance(format, ExportFormat):
        raise ValueError(f"Unsupported export format: {format}")
    
    return exporters[format]() 