"""Web bridge for Qt-JavaScript communication."""
import json
import logging
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSlot

# Set up logging using centralized configuration
logger = logging.getLogger(__name__)

class WebBridge(QObject):
    """Bridge for communication between Qt and JavaScript."""
    def __init__(self, app):
        super().__init__()
        self.app = app

    @pyqtSlot(str)
    def nodeSelected(self, node_data):
        """Handle node selection from D3."""
        data = json.loads(node_data)
        self.app.update_node_details(data)
        
    @pyqtSlot(str)
    def loadFileContents(self, file_path):
        """Handle file content loading request from D3."""
        self.app.load_file_contents(file_path)
