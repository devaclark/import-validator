"""Centralized logging configuration for the validator package."""
import logging
import sys
from pathlib import Path

def setup_logging():
    """Set up logging configuration for all modules."""
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

    # Configure root logger
    root_logger = logging.getLogger('validator')
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Prevent propagation to root logger to avoid duplicate logs
    root_logger.propagate = False

    return root_logger 