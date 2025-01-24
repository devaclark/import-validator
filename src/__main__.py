"""Main module for import validator."""
import asyncio
import logging
from pathlib import Path
from typing import Optional
import sys
import argparse

from src.validator.validator import AsyncImportValidator
from src.validator.config import ImportValidatorConfig
from src.exporters import create_exporter
from src.validator.validator_types import ExportFormat, ValidationResults
from src.app.__main__ import main as qt_main
from src.validator.logging_config import setup_logging
logger = logging.getLogger(__name__)

def parse_args(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Import Validator')
    parser.add_argument('--project-path', type=str, help='Path to project to analyze')
    parser.add_argument('--auto-scan', action='store_true', help='Automatically scan the project on startup')
    parser.add_argument('--export', type=str, choices=['json', 'csv', 'html', 'md'], help='Export format')
    parser.add_argument('--output', type=str, help='Output file path')
    args = parser.parse_args(args)
    if args.project_path:
        args.project_path = Path(args.project_path)
    return args

async def run(args):
    """Run the validator."""
    if args.project_path:
        from src.app.__main__ import main
        await main(project_path=args.project_path, auto_scan=args.auto_scan)
    else:
        from src.app.__main__ import main
        await main()

def main():
    """Main entry point."""
    args = parse_args()
    setup_logging()
    logger.debug("Starting Import Validator CLI")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == '__main__':
    main() 