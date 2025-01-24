"""UI components and styles for the Import Validator application."""

# Dark theme colors
DARK_THEME = """
QMainWindow, QWidget, QDialog {
    background-color: #1E1E1E;
    color: #D4D4D4;
}

QMessageBox, QDialog {
    background-color: #2D2D2D;
    border: 1px solid #3E3E3E;
}

QMessageBox QPushButton, QDialog QPushButton {
    background-color: #2D2D2D;
    color: #D4D4D4;
    border: 1px solid #3E3E3E;
    padding: 6px 12px;
    border-radius: 2px;
}

QMessageBox QPushButton:hover, QDialog QPushButton:hover {
    background-color: #3E3E3E;
}

QMessageBox QPushButton:pressed, QDialog QPushButton:pressed {
    background-color: #4E4E4E;
}

QMessageBox QLabel, QDialog QLabel {
    color: #D4D4D4;
}

QMenuBar {
    background-color: #2D2D2D;
    color: #D4D4D4;
}

QMenuBar::item:selected {
    background-color: #3E3E3E;
}

QMenu {
    background-color: #2D2D2D;
    color: #D4D4D4;
    border: 1px solid #3E3E3E;
}

QMenu::item:selected {
    background-color: #3E3E3E;
}

QToolBar {
    background-color: #2D2D2D;
    border: none;
    spacing: 2px;
    padding: 2px;
}

QToolButton {
    background-color: #2D2D2D;
    border: none;
    padding: 4px;
}

QToolButton:hover {
    background-color: #3E3E3E;
}

QLineEdit {
    background-color: #2D2D2D;
    color: #D4D4D4;
    border: 1px solid #3E3E3E;
    padding: 2px;
}

QPushButton {
    background-color: #2D2D2D;
    color: #D4D4D4;
    border: 1px solid #3E3E3E;
    padding: 4px 8px;
    border-radius: 2px;
}

QPushButton:hover {
    background-color: #3E3E3E;
}

QPushButton:disabled {
    background-color: #2D2D2D;
    color: #808080;
}

QTabWidget::pane {
    border: none;
}

QTabBar::tab {
    background-color: #2D2D2D;
    color: #D4D4D4;
    padding: 4px 8px;
    border: none;
    border-bottom: 2px solid transparent;
}

QTabBar::tab:selected {
    background-color: #1E1E1E;
    border-bottom: 2px solid #0E639C;
}

QTabBar::tab:hover:!selected {
    background-color: #3E3E3E;
}

QTreeWidget {
    background-color: #1E1E1E;
    color: #D4D4D4;
    border: none;
}

QTreeWidget::item {
    padding: 2px;
}

QTreeWidget::item:selected {
    background-color: #264F78;
}

QTreeWidget::item:hover {
    background-color: #2D2D2D;
}

QScrollBar:vertical {
    background-color: #1E1E1E;
    width: 12px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #424242;
    min-height: 20px;
    border-radius: 6px;
}

QScrollBar::handle:vertical:hover {
    background-color: #686868;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #1E1E1E;
    height: 12px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #424242;
    min-width: 20px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #686868;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}

QStatusBar {
    background-color: #2D2D2D;
    color: #D4D4D4;
}

QProgressDialog {
    background-color: #2D2D2D;
    color: #D4D4D4;
}

QProgressDialog QLabel {
    color: #D4D4D4;
}

QProgressDialog QPushButton {
    min-width: 80px;
}

QMessageBox {
    background-color: #2D2D2D;
}

QMessageBox QLabel {
    color: #D4D4D4;
}

QMessageBox QPushButton {
    min-width: 80px;
}
"""

# Splitter style for better visibility
SPLITTER_STYLE = """
QSplitter::handle {
    background-color: #2D2D2D;
}

QSplitter::handle:hover {
    background-color: #0E639C;
}
""" 