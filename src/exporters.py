"""Export utilities for import validator."""
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Protocol, Set
from .validator_types import (
    ImportStats,
    ValidationError,
    ExportFormat,
    ImportGraph,
    CircularRefs
)
from .visualization import D3Visualizer


class Exporter(Protocol):
    """Protocol for export implementations."""
    
    def export(
        self,
        stats: ImportStats,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        unused_imports: Dict[str, Set[str]],
        relative_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        errors: List[ValidationError],
        output_file: Path
    ) -> None:
        """Export analysis results to a file."""
        ...


class HTMLExporter:
    """Export results to HTML format with interactive D3.js visualization."""
    
    def __init__(self):
        self.d3_visualizer = D3Visualizer()
        
    def export(
        self,
        stats: ImportStats,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        unused_imports: Dict[str, Set[str]],
        relative_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        errors: List[ValidationError],
        output_file: Path
    ) -> None:
        """Export analysis results to HTML with interactive visualization."""
        # Convert circular_refs from Dict[str, List[List[str]]] to Set[tuple[str, str]]
        circular_edges = set()
        for cycles in circular_refs.values():
            for cycle in cycles:
                for i in range(len(cycle) - 1):
                    circular_edges.add((cycle[i], cycle[i + 1]))
                # Add edge from last to first to complete the cycle
                if cycle:
                    circular_edges.add((cycle[-1], cycle[0]))
        
        # Create visualization
        viz_file = output_file.with_suffix('.viz.html')
        self.d3_visualizer.visualize(
            import_graph=import_graph,
            invalid_imports=invalid_imports,
            circular_refs=circular_edges,
            output_file=viz_file
        )
        
        # Create HTML report
        html_content = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "    <title>Import Analysis Report</title>",
            "    <style>",
            "        body { font-family: Arial, sans-serif; margin: 20px; }",
            "        h1, h2 { color: #333; }",
            "        table { border-collapse: collapse; margin: 10px 0; }",
            "        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
            "        th { background-color: #f5f5f5; }",
            "        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }",
            "        .stat-card { background: #f9f9f9; padding: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
            "        .viz-container { margin: 20px 0; }",
            "        iframe { border: none; width: 100%; height: 800px; }",
            "    </style>",
            "</head>",
            "<body>",
            "    <h1>Import Analysis Report</h1>",
            "",
            "    <div class='viz-container'>",
            "        <h2>Import Graph Visualization</h2>",
            f"        <iframe src='{viz_file.name}'></iframe>",
            "    </div>",
            "",
            "    <h2>Summary</h2>",
            "    <div class='stats'>",
            f"        <div class='stat-card'><strong>Total Imports:</strong> {stats.total_imports}</div>",
            f"        <div class='stat-card'><strong>Unique Imports:</strong> {stats.unique_imports}</div>",
            f"        <div class='stat-card'><strong>Complexity Score:</strong> {stats.complexity_score:.2f}</div>",
            f"        <div class='stat-card'><strong>Invalid Imports:</strong> {stats.invalid_imports_count}</div>",
            f"        <div class='stat-card'><strong>Unused Imports:</strong> {stats.unused_imports_count}</div>",
            f"        <div class='stat-card'><strong>Relative Imports:</strong> {stats.relative_imports_count}</div>",
            f"        <div class='stat-card'><strong>Circular References:</strong> {stats.circular_refs_count}</div>",
            "    </div>",
            "",
            "    <h2>Most Common Imports</h2>",
            "    <table>",
            "        <tr><th>Module</th><th>Import Count</th></tr>"
        ]
        
        # Add most common imports
        for module, count in stats.most_common:
            html_content.append(f"        <tr><td>{module}</td><td>{count}</td></tr>")
        
        html_content.extend([
            "    </table>",
            "",
            "    <h2>Files with Most Imports</h2>",
            "    <table>",
            "        <tr><th>File</th><th>Import Count</th></tr>"
        ])
        
        # Add files with most imports
        for file, count in stats.files_with_most_imports:
            html_content.append(f"        <tr><td>{file}</td><td>{count}</td></tr>")
        
        # Add invalid imports section
        if invalid_imports:
            html_content.extend([
                "    </table>",
                "",
                "    <h2>Invalid Imports</h2>",
                "    <table>",
                "        <tr><th>File</th><th>Invalid Imports</th></tr>"
            ])
            for file, imports in invalid_imports.items():
                html_content.append(f"        <tr><td>{file}</td><td>{', '.join(imports)}</td></tr>")
        
        # Add unused imports section
        if unused_imports:
            html_content.extend([
                "    </table>",
                "",
                "    <h2>Unused Imports</h2>",
                "    <table>",
                "        <tr><th>File</th><th>Unused Imports</th></tr>"
            ])
            for file, imports in unused_imports.items():
                html_content.append(f"        <tr><td>{file}</td><td>{', '.join(imports)}</td></tr>")
        
        # Add relative imports section
        if relative_imports:
            html_content.extend([
                "    </table>",
                "",
                "    <h2>Relative Imports</h2>",
                "    <table>",
                "        <tr><th>File</th><th>Relative Imports</th></tr>"
            ])
            for file, imports in relative_imports.items():
                html_content.append(f"        <tr><td>{file}</td><td>{', '.join(imports)}</td></tr>")
        
        # Add circular references section
        if circular_refs:
            html_content.extend([
                "    </table>",
                "",
                "    <h2>Circular References</h2>",
                "    <table>",
                "        <tr><th>File</th><th>Cycle</th></tr>"
            ])
            for file, cycles in circular_refs.items():
                for cycle in cycles:
                    html_content.append(f"        <tr><td>{file}</td><td>{' -> '.join(cycle)}</td></tr>")
        
        # Add errors section
        if errors:
            html_content.extend([
                "    </table>",
                "",
                "    <h2>Errors</h2>",
                "    <table>",
                "        <tr><th>File</th><th>Error Type</th><th>Message</th><th>Line</th></tr>"
            ])
            for error in errors:
                line_info = f":{error.line_number}" if error.line_number else ""
                html_content.append(
                    f"        <tr><td>{error.file}{line_info}</td><td>{error.error_type}</td>"
                    f"<td>{error.message}</td><td>{error.line_number or ''}</td></tr>"
                )
        
        html_content.extend([
            "    </table>",
            "</body>",
            "</html>"
        ])
        
        # Write the report
        output_file.write_text('\n'.join(html_content), encoding='utf-8')


class MarkdownExporter:
    """Export results to Markdown format."""
    
    def export(
        self,
        stats: ImportStats,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        unused_imports: Dict[str, Set[str]],
        relative_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        errors: List[ValidationError],
        output_file: Path
    ) -> None:
        """Export analysis results to Markdown."""
        lines = [
            "# Import Analysis Report",
            "",
            "## Summary",
            "",
            f"- Total imports: {stats.total_imports}",
            f"- Unique imports: {stats.unique_imports}",
            f"- Average complexity score: {stats.complexity_score}",
            f"- Invalid imports: {stats.invalid_imports_count}",
            f"- Unused imports: {stats.unused_imports_count}",
            f"- Relative imports: {stats.relative_imports_count}",
            f"- Circular references: {stats.circular_refs_count}",
            "",
            "## Most Common Imports",
            "",
            "| Module | Import Count |",
            "|--------|--------------|"
        ]
        
        # Add most common imports
        for module, count in stats.most_common:
            lines.append(f"| {module} | {count} |")
        
        # Add files with most imports
        lines.extend([
            "",
            "## Files with Most Imports",
            "",
            "| File | Import Count |",
            "|------|--------------|"
        ])
        for file, count in stats.files_with_most_imports:
            lines.append(f"| {file} | {count} |")
        
        # Add invalid imports section
        if invalid_imports:
            lines.extend([
                "",
                "## Invalid Imports",
                "",
                "| File | Invalid Imports |",
                "|------|----------------|"
            ])
            for file, imports in invalid_imports.items():
                lines.append(f"| {file} | {', '.join(imports)} |")
        
        # Add unused imports section
        if unused_imports:
            lines.extend([
                "",
                "## Unused Imports",
                "",
                "| File | Unused Imports |",
                "|------|----------------|"
            ])
            for file, imports in unused_imports.items():
                lines.append(f"| {file} | {', '.join(imports)} |")
        
        # Add relative imports section
        if relative_imports:
            lines.extend([
                "",
                "## Relative Imports",
                "",
                "| File | Relative Imports |",
                "|------|-----------------|"
            ])
            for file, imports in relative_imports.items():
                lines.append(f"| {file} | {', '.join(imports)} |")
        
        # Add circular references section
        if circular_refs:
            lines.extend([
                "",
                "## Circular References",
                ""
            ])
            for file, cycles in circular_refs.items():
                lines.extend([
                    f"### In {file}",
                    "",
                    *[f"- {' -> '.join(cycle)}" for cycle in cycles],
                    ""
                ])
        
        # Add errors section
        if errors:
            lines.extend([
                "",
                "## Errors",
                "",
                "| File | Error Type | Message | Line |",
                "|------|------------|---------|------|"
            ])
            for error in errors:
                line_info = f":{error.line_number}" if error.line_number else ""
                lines.append(
                    f"| {error.file}{line_info} | {error.error_type} | {error.message} | {error.line_number or ''} |"
                )
        
        # Write the report
        output_file.write_text('\n'.join(lines), encoding='utf-8')


class JSONExporter:
    """Export results to JSON format."""
    
    def export(
        self,
        stats: ImportStats,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        unused_imports: Dict[str, Set[str]],
        relative_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        errors: List[ValidationError],
        output_file: Path
    ) -> None:
        """Export analysis results to JSON."""
        data = {
            'stats': {
                'total_imports': stats.total_imports,
                'unique_imports': stats.unique_imports,
                'complexity_score': stats.complexity_score,
                'invalid_imports_count': stats.invalid_imports_count,
                'unused_imports_count': stats.unused_imports_count,
                'relative_imports_count': stats.relative_imports_count,
                'circular_refs_count': stats.circular_refs_count,
                'most_common': stats.most_common,
                'files_with_most_imports': stats.files_with_most_imports
            },
            'import_graph': {
                source: list(targets)
                for source, targets in import_graph.items()
            },
            'invalid_imports': {
                source: list(targets)
                for source, targets in invalid_imports.items()
            },
            'unused_imports': {
                source: list(imports)
                for source, imports in unused_imports.items()
            },
            'relative_imports': {
                source: list(imports)
                for source, imports in relative_imports.items()
            },
            'circular_refs': circular_refs,
            'errors': [
                {
                    'file': str(error.file),
                    'error_type': error.error_type,
                    'message': error.message,
                    'line_number': error.line_number,
                    'context': error.context
                }
                for error in errors
            ]
        }
        
        output_file.write_text(
            json.dumps(data, indent=2),
            encoding='utf-8'
        )


class CSVExporter:
    """Export results to CSV format."""
    
    def export(
        self,
        stats: ImportStats,
        import_graph: ImportGraph,
        invalid_imports: Dict[str, Set[str]],
        unused_imports: Dict[str, Set[str]],
        relative_imports: Dict[str, Set[str]],
        circular_refs: CircularRefs,
        errors: List[ValidationError],
        output_file: Path
    ) -> None:
        """Export analysis results to CSV."""
        # Create directory for CSV files
        output_dir = output_file.parent / output_file.stem
        output_dir.mkdir(exist_ok=True)
        
        # Export stats
        with open(output_dir / 'stats.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Total Imports', stats.total_imports])
            writer.writerow(['Unique Imports', stats.unique_imports])
            writer.writerow(['Complexity Score', stats.complexity_score])
            writer.writerow(['Invalid Imports', stats.invalid_imports_count])
            writer.writerow(['Unused Imports', stats.unused_imports_count])
            writer.writerow(['Relative Imports', stats.relative_imports_count])
            writer.writerow(['Circular References', stats.circular_refs_count])
        
        # Export most common imports
        with open(output_dir / 'most_common.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Module', 'Count'])
            writer.writerows(stats.most_common)
        
        # Export files with most imports
        with open(output_dir / 'files_with_most_imports.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Import Count'])
            writer.writerows(stats.files_with_most_imports)
        
        # Export invalid imports
        with open(output_dir / 'invalid_imports.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Invalid Import'])
            for file, imports in invalid_imports.items():
                for imp in imports:
                    writer.writerow([file, imp])
        
        # Export unused imports
        with open(output_dir / 'unused_imports.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Unused Import'])
            for file, imports in unused_imports.items():
                for imp in imports:
                    writer.writerow([file, imp])
        
        # Export relative imports
        with open(output_dir / 'relative_imports.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Relative Import'])
            for file, imports in relative_imports.items():
                for imp in imports:
                    writer.writerow([file, imp])
        
        # Export circular references
        with open(output_dir / 'circular_refs.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Cycle'])
            for file, cycles in circular_refs.items():
                for cycle in cycles:
                    writer.writerow([file, ' -> '.join(cycle)])
        
        # Export errors
        with open(output_dir / 'errors.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['File', 'Error Type', 'Message', 'Line Number', 'Context'])
            for error in errors:
                writer.writerow([
                    error.file,
                    error.error_type,
                    error.message,
                    error.line_number or '',
                    error.context or ''
                ])


def create_exporter(format: ExportFormat) -> Exporter:
    """Factory function to create appropriate exporter."""
    if format == ExportFormat.MARKDOWN:
        return MarkdownExporter()
    elif format == ExportFormat.JSON:
        return JSONExporter()
    elif format == ExportFormat.CSV:
        return CSVExporter()
    elif format == ExportFormat.HTML:
        return HTMLExporter()
    
    else:
        raise ValueError(f"Unsupported export format: {format}") 