"""Command-line interface for import validator."""
import argparse
import asyncio
from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser
from pathlib import Path
from typing import Optional
import sys

from rich.console import Console

from .config import ImportValidatorConfig
from .error_handling import ConsoleErrorHandler, FileErrorHandler, CompositeErrorHandler
from .validator_types import ExportFormat
from .validator import AsyncImportValidator


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate and analyze Python imports in a project"
    )
    
    parser.add_argument(
        "src_dir",
        help="Source directory to analyze"
    )
    parser.add_argument(
        "tests_dir",
        help="Tests directory to analyze"
    )
    
    # Output options
    parser.add_argument(
        "-o", "--output",
        help="Output file for the report",
        type=Path
    )
    parser.add_argument(
        "--format",
        help="Output format for the report",
        choices=[f.name.lower() for f in ExportFormat],
        default="markdown"
    )
    parser.add_argument(
        "--no-serve",
        help="Disable automatic server for HTML format",
        action="store_true"
    )
    parser.add_argument(
        "--port",
        help="Port to use for the local server (default: 8080)",
        type=int,
        default=8080
    )
    
    # Dependency options
    parser.add_argument(
        "--requirements",
        help="Path to requirements.txt file",
        type=Path
    )
    parser.add_argument(
        "--pyproject",
        help="Path to pyproject.toml file",
        type=Path
    )
    
    # Visualization options
    parser.add_argument(
        "--no-viz",
        help="Disable visualization generation",
        action="store_true"
    )
    
    # Error handling options
    parser.add_argument(
        "--log-file",
        help="Log file for errors",
        type=Path
    )
    
    # Configuration options
    parser.add_argument(
        "--config",
        help="Path to configuration file",
        type=Path
    )
    parser.add_argument(
        "--complexity-threshold",
        help="Threshold for flagging high complexity imports",
        type=float
    )
    parser.add_argument(
        "--max-edges",
        help="Maximum number of edges to show in visualization",
        type=int
    )
    
    args = parser.parse_args()
    
    # Set default output file based on format if not provided
    if args.output is None:
        extension = "md" if args.format == "markdown" else args.format
        args.output = Path(f"import_analysis.{extension}")
    
    return args


def create_error_handler(log_file: Optional[Path] = None) -> CompositeErrorHandler:
    """Create error handler based on configuration."""
    handlers = [ConsoleErrorHandler()]
    if log_file:
        handlers.append(FileErrorHandler(str(log_file)))
    return CompositeErrorHandler(handlers)


def load_config(args: argparse.Namespace) -> ImportValidatorConfig:
    """Load configuration from file and/or command line arguments."""
    # Start with default config
    config = ImportValidatorConfig()
    
    # Update from file if provided
    if args.config and args.config.exists():
        file_config = ImportValidatorConfig.parse_file(args.config)
        config = config.merge_with(file_config)
    
    # Update from command line arguments
    updates = {}
    if args.complexity_threshold is not None:
        updates['complexity_threshold'] = args.complexity_threshold
    if args.max_edges is not None:
        updates['max_edges_per_diagram'] = args.max_edges
    if args.requirements is not None:
        updates['requirements_file'] = args.requirements
    if args.pyproject is not None:
        updates['pyproject_file'] = args.pyproject
    
    if updates:
        config = config.merge_with(ImportValidatorConfig(**updates))
    
    # Load dependencies from requirements/pyproject files
    config.load_dependencies()
    
    return config


def serve_html(output_file: Path, port: int = 8080) -> None:
    """Start a local server to serve the HTML report."""
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(output_file.parent), **kwargs)
    
    server = HTTPServer(('localhost', port), Handler)
    url = f"http://localhost:{port}/{output_file.name}"
    viz_url = f"http://localhost:{port}/{output_file.stem}.viz.html"
    
    console = Console()
    console.print("\n[bold green]Server started![/bold green]")
    console.print("\n[bold]Report URLs:[/bold]")
    console.print(f"Main report: [link]{url}[/link]")
    console.print(f"Visualization: [link]{viz_url}[/link]")
    console.print("\nPress Ctrl+C to stop the server")
    
    # Open the browser
    webbrowser.open(url)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Shutting down server...[/bold yellow]")
        server.shutdown()


async def main() -> int:
    """Main entry point."""
    console = Console()
    
    try:
        # Parse arguments
        args = parse_args()
        
        # Create error handler
        error_handler = create_error_handler(args.log_file)
        
        # Load configuration
        config = load_config(args)
        
        # Create validator
        validator = AsyncImportValidator(
            src_dir=args.src_dir,
            tests_dir=args.tests_dir,
            config=config,
            error_handler=error_handler
        )
        
        # Run validation
        console.print("\n[bold blue]Starting import validation...[/bold blue]")
        await validator.validate_all()
        
        # Export results
        console.print("\n[bold blue]Exporting results...[/bold blue]")
        validator.export_results(
            format=ExportFormat[args.format.upper()],
            output_file=args.output,
            visualize=not args.no_viz
        )
        
        # Print summary
        stats = validator.generate_stats()
        console.print("\n[bold green]Validation complete![/bold green]")
        console.print(f"Total imports: {stats.total_imports}")
        console.print(f"Unique imports: {stats.unique_imports}")
        console.print(f"Average complexity score: {stats.complexity_score:.2f}")
        console.print(f"Invalid imports: {stats.invalid_imports_count}")
        console.print(f"Unused imports: {stats.unused_imports_count}")
        console.print(f"Relative imports: {stats.relative_imports_count}")
        console.print(f"Circular references: {stats.circular_refs_count}")
        console.print("\n[bold]Import Graph Statistics:[/bold]")
        console.print(f"Total nodes (files): {stats.total_nodes}")
        console.print(f"Total edges (import relationships): {stats.total_edges}")
        console.print(f"Average edges per node: {stats.total_edges / stats.total_nodes:.2f}" if stats.total_nodes > 0 else "No nodes in graph")
        
        # Check for errors
        errors = error_handler.get_errors()
        if errors:
            console.print(f"\n[bold red]Found {len(errors)} errors![/bold red]")
            return 1
        
        # Start server automatically for HTML format unless disabled
        if args.format == "html" and not args.no_serve:
            serve_html(args.output, args.port)
        
        return 0
        
    except Exception as e:
        console.print(f"\n[bold red]Error: {str(e)}[/bold red]")
        return 1


def run_main():
    """Synchronous wrapper for main function."""
    return asyncio.run(main())


if __name__ == "__main__":
    sys.exit(run_main()) 