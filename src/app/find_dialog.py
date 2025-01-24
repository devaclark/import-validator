"""Find dialog for text search functionality."""
import logging
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, 
                           QPushButton, QCheckBox, QLabel)
from PyQt6.QtCore import Qt, pyqtSignal

# Set up logging using centralized configuration
logger = logging.getLogger(__name__)

class FindDialog(QDialog):
    """Dialog for finding text in the code editor."""
    
    findNext = pyqtSignal(str, bool, bool)  # text, case sensitive, whole words
    findPrev = pyqtSignal(str, bool, bool)
    findAll = pyqtSignal(str, bool, bool)
    
    def __init__(self, parent=None):
        """Initialize the find dialog.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Find")
        self.setModal(False)
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Create search input
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)
        
        search_label = QLabel("Find:")
        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self.update_find_button)
        self.search_input.returnPressed.connect(self.find_next)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        
        layout.addLayout(search_layout)
        
        # Create options
        options_layout = QHBoxLayout()
        options_layout.setSpacing(8)
        
        self.case_sensitive = QCheckBox("Case sensitive")
        self.whole_words = QCheckBox("Whole words")
        
        options_layout.addWidget(self.case_sensitive)
        options_layout.addWidget(self.whole_words)
        options_layout.addStretch()
        
        layout.addLayout(options_layout)
        
        # Create buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)
        
        self.find_next_button = QPushButton("Find Next")
        self.find_next_button.setEnabled(False)
        self.find_next_button.clicked.connect(self.find_next)
        
        self.find_prev_button = QPushButton("Find Previous")
        self.find_prev_button.setEnabled(False)
        self.find_prev_button.clicked.connect(self.find_prev)
        
        self.find_all_button = QPushButton("Find All")
        self.find_all_button.setEnabled(False)
        self.find_all_button.clicked.connect(self.find_all)
        
        button_layout.addWidget(self.find_next_button)
        button_layout.addWidget(self.find_prev_button)
        button_layout.addWidget(self.find_all_button)
        
        layout.addLayout(button_layout)
        
        # Set focus to search input
        self.search_input.setFocus()
        
    def update_find_button(self, text):
        """Update find button state based on search text.
        
        Args:
            text: Current search text
        """
        enabled = bool(text.strip())
        self.find_next_button.setEnabled(enabled)
        self.find_prev_button.setEnabled(enabled)
        self.find_all_button.setEnabled(enabled)
        
    def find_next(self):
        """Emit signal to find next occurrence."""
        text = self.search_input.text()
        if text:
            self.findNext.emit(
                text,
                self.case_sensitive.isChecked(),
                self.whole_words.isChecked()
            )
            
    def find_prev(self):
        """Emit signal to find previous occurrence."""
        text = self.search_input.text()
        if text:
            self.findPrev.emit(
                text,
                self.case_sensitive.isChecked(),
                self.whole_words.isChecked()
            )
            
    def find_all(self):
        """Emit signal to find all occurrences."""
        text = self.search_input.text()
        if text:
            self.findAll.emit(
                text,
                self.case_sensitive.isChecked(),
                self.whole_words.isChecked()
            )
            
    def showEvent(self, event):
        """Handle dialog show event.
        
        Args:
            event: Show event
        """
        super().showEvent(event)
        # Select all text in search input
        self.search_input.selectAll()
        self.search_input.setFocus()
        
    def keyPressEvent(self, event):
        """Handle key press events.
        
        Args:
            event: Key event
        """
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event) 