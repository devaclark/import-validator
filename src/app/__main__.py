"""Main entry point for the Import Validator application."""
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import QApplication
import qasync

from .main_window import ImportValidatorApp
from src.validator.logging_config import setup_logging

# Set up logging
logger = logging.getLogger(__name__)

async def main(project_path: Optional[str] = None, auto_scan: bool = False):
    """Main entry point for the Qt application.
    
    Args:
        project_path: Optional path to project to analyze
        auto_scan: Whether to automatically start scanning
    """
    try:
        # Ensure logging is set up
        setup_logging()
        logger.debug("Starting Import Validator application")
        
        app = QApplication.instance() or QApplication(sys.argv)
        
        # Create and setup Qt event loop
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # Create main window
        window = ImportValidatorApp()
        window.window.show()  # Show the window

        if project_path:
            # Convert project_path to string if it's a Path object
            path_str = str(project_path) if project_path else ""
            logger.debug(f"Setting project path: {path_str}")
            # Set the project path
            window.path_input.setText(path_str)
            window.scan_button.setEnabled(True)
            
            # If auto-scan is enabled, schedule the scan
            if auto_scan:
                logger.debug("Auto-scan enabled, scheduling scan")
                loop.call_later(0.1, lambda: asyncio.create_task(window.scan_project()))

        # Run event loop
        with loop:
            return loop.run_forever()
            
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
        raise

def run_app():
    """Run the application."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run_app() 