"""UI components and styles for the Import Validator application."""

# Dark theme colors
DARK_THEME = """
QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
QLineEdit, QTextEdit {
    background-color: #252526;
    border: 1px solid #2d2d2d;
    padding: 2px 4px;
    color: #d4d4d4;
}
QPushButton {
    background-color: #37373d;
    border: none;
    padding: 4px 12px;
    color: #d4d4d4;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #3d3d42;
}
QPushButton:disabled {
    background-color: #2d2d2d;
    color: #6e6e6e;
}
QSplitter::handle {
    background-color: #2d2d2d;
}
QTabWidget::pane {
    border: none;
}
QTabBar::tab {
    background-color: #2d2d2d;
    padding: 6px 12px;
    margin-right: 1px;
    color: #969696;
}
QTabBar::tab:selected {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border-top: 1px solid #37373d;
}
QTreeWidget {
    background-color: #252526;
    border: none;
    alternate-background-color: #1e1e1e;
}
QTreeWidget::item {
    padding: 2px;
    color: #d4d4d4;
}
QTreeWidget::item:selected {
    background-color: #37373d;
}
QHeaderView::section {
    background-color: #2d2d2d;
    color: #969696;
    padding: 4px;
    border: none;
}
QScrollBar:vertical {
    background-color: #1e1e1e;
    width: 14px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background-color: #424242;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #505050;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# Splitter style for better visibility
SPLITTER_STYLE = """
QSplitter::handle {
                background-color: #2d2d2d;
                border: 1px solid #37373d;
            }
QSplitter::handle:hover {
    background-color: #37373d;
}   
""" 