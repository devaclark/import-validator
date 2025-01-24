"""Code editor component with syntax highlighting and code intelligence."""
import logging
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                               QHBoxLayout, QWidget, QFileDialog, QLineEdit, QLabel, 
                               QSplitter, QTextEdit, QProgressDialog, QTabWidget,
                               QScrollArea, QFrame, QTreeWidget, QTreeWidgetItem,
                               QStatusBar, QDialog, QCheckBox, QMessageBox, QToolBar)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QUrl, pyqtSlot, QObject, QSize
from PyQt6.QtGui import QFont, QPalette, QColor, QShortcut, QKeySequence
from PyQt6.Qsci import QsciScintilla, QsciLexerPython, QsciAPIs
import jedi
import keyword

from .find_dialog import FindDialog
# Set up logging using centralized configuration
logger = logging.getLogger(__name__)

class CodeEditor(QsciScintilla):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set up the editor
        self.setup_editor()
        self.setup_style()
        self.setup_margins()
        self.setup_autocomplete()
        self.setup_keyboard_shortcuts()
        self.setup_toolbar()
        
        # Initialize Jedi for code intelligence
        self.jedi_script = None
        
        # Track file path and modification state
        self.current_file = None
        self.is_modified = False
        self.modificationChanged.connect(self._handle_modification)
        
    def setup_editor(self):
        # Enable UTF-8
        self.setUtf8(True)
        
        # Enable brace matching
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)
        
        # Enable auto-indent
        self.setAutoIndent(True)
        self.setIndentationGuides(True)
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        
        # Enable code folding
        self.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle)
        
        # Enable line wrapping
        self.setWrapMode(QsciScintilla.WrapMode.WrapWord)
        
        # Enable multiple cursors and selections through standard QScintilla methods
        self.SendScintilla(QsciScintilla.SCI_SETMULTIPLESELECTION, 1)
        self.SendScintilla(QsciScintilla.SCI_SETMULTIPASTE, 1)
        self.SendScintilla(QsciScintilla.SCI_SETADDITIONALSELECTIONTYPING, 1)
        
        # Set selection mode
        self.SendScintilla(QsciScintilla.SCI_SETSELECTIONMODE, 0)  # Stream selection
        
        # Enable line numbers with sufficient margin width
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "0000")  # Width for up to 9999 lines
        
        # Enable markers for errors/warnings
        self.setMarginType(1, QsciScintilla.MarginType.SymbolMargin)
        self.setMarginWidth(1, 16)
        self.setMarginMarkerMask(1, 0b1111)  # Allow all marker types
        
        # Set up markers using simple ASCII characters
        # Error marker (using 'x')
        self.markerDefine(b'x', 0)
        self.setMarkerBackgroundColor(QColor("#FF0000"), 0)
        self.setMarkerForegroundColor(QColor("#FFFFFF"), 0)
        
        # Warning marker (using '!')
        self.markerDefine(b'!', 1)
        self.setMarkerBackgroundColor(QColor("#FFA500"), 1)
        self.setMarkerForegroundColor(QColor("#FFFFFF"), 1)
        
        # Enable edge mode (vertical line at column 80)
        self.setEdgeMode(QsciScintilla.EdgeMode.EdgeLine)
        self.setEdgeColumn(80)
        self.setEdgeColor(QColor("#2d2d2d"))
        
        # Set up auto-completion
        self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(True)
        
        # Set up call tips
        self.setCallTipsStyle(QsciScintilla.CallTipsStyle.CallTipsContext)
        self.setCallTipsVisible(0)
        
        # Set up indicators for search results
        self.indicatorDefine(QsciScintilla.IndicatorStyle.RoundBoxIndicator, 0)
        self.setIndicatorForegroundColor(QColor("#569CD6"), 0)
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
    def setup_style(self):
        # Set up the Python lexer
        self.lexer = QsciLexerPython()
        self.lexer.setDefaultFont(QFont("Consolas", 10))
        
        # Set dark theme colors
        self.lexer.setDefaultPaper(QColor("#1e1e1e"))
        self.lexer.setDefaultColor(QColor("#d4d4d4"))
        
        # Python syntax colors (VS Code-like)
        self.lexer.setColor(QColor("#569cd6"), QsciLexerPython.Keyword)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.DoubleQuotedString)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.SingleQuotedString)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleDoubleQuotedString)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.TripleSingleQuotedString)
        self.lexer.setColor(QColor("#6a9955"), QsciLexerPython.Comment)
        self.lexer.setColor(QColor("#6a9955"), QsciLexerPython.CommentBlock)
        self.lexer.setColor(QColor("#b5cea8"), QsciLexerPython.Number)
        self.lexer.setColor(QColor("#4ec9b0"), QsciLexerPython.ClassName)
        self.lexer.setColor(QColor("#dcdcaa"), QsciLexerPython.FunctionMethodName)
        self.lexer.setColor(QColor("#d4d4d4"), QsciLexerPython.Operator)
        self.lexer.setColor(QColor("#9cdcfe"), QsciLexerPython.Identifier)
        self.lexer.setColor(QColor("#c586c0"), QsciLexerPython.Decorator)
        
        # Set all background colors
        for style in range(128):
            self.lexer.setPaper(QColor("#1e1e1e"), style)
        
        self.setLexer(self.lexer)
        
        # Set selection colors
        self.setSelectionBackgroundColor(QColor("#264f78"))
        self.setSelectionForegroundColor(QColor("#ffffff"))
        
        # Current line highlight
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#282828"))
        self.setCaretForegroundColor(QColor("#d4d4d4"))
        
        # Set the caret (cursor) style
        self.SendScintilla(QsciScintilla.SCI_SETCARETSTYLE, QsciScintilla.CARETSTYLE_LINE)
        self.SendScintilla(QsciScintilla.SCI_SETCARETWIDTH, 2)
        
    def setup_margins(self):
        # Line numbers
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "0000")
        self.setMarginsForegroundColor(QColor("#858585"))
        self.setMarginsBackgroundColor(QColor("#1e1e1e"))
        
        # Folding margin
        self.setMarginType(2, QsciScintilla.MarginType.SymbolMargin)
        self.setMarginWidth(2, 15)
        self.setMarginSensitivity(2, True)
        self.setFoldMarginColors(QColor("#1e1e1e"), QColor("#1e1e1e"))
        
    def setup_autocomplete(self):
        # Enable autocompletion
        self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(True)
        
        # Set up Python APIs
        self.api = QsciAPIs(self.lexer)
        
        # Add Python keywords
        for kw in keyword.kwlist:
            self.api.add(kw)
        
        # Prepare the API
        self.api.prepare()
        
    def update_code_intelligence(self, file_path, code):
        """Update code intelligence for the current file."""
        self.jedi_script = jedi.Script(code, path=file_path)
        
    def keyPressEvent(self, event):
        # Handle autocompletion
        if event.key() == Qt.Key.Key_Period:
            super().keyPressEvent(event)
            self.show_completions()
            return
            
        super().keyPressEvent(event)
        
    def show_completions(self):
        """Show code completions using Jedi."""
        if not self.jedi_script:
            return
            
        # Get cursor position
        line, col = self.getCursorPosition()
        
        try:
            # Get completions from Jedi
            completions = self.jedi_script.complete(line + 1, col)
            
            # Format completions for Scintilla
            if completions:
                self.showUserList(1, [c.name for c in completions])
        except Exception:
            pass

    def save_file(self):
        if not self.current_file or not self.isModified():
            return
            
        try:
            with open(self.current_file, 'w', encoding='utf-8') as f:
                f.write(self.text())
            self.setModified(False)
            if hasattr(self, 'save_callback'):
                self.save_callback()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")
    
    def show_find_dialog(self):
        """Show an improved find dialog."""
        find_dialog = QDialog(self)
        find_dialog.setWindowTitle("Find")
        find_dialog.setFixedWidth(300)
        find_dialog.setStyleSheet("""
            QDialog {
                background-color: #252526;
                color: #d4d4d4;
            }
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #3c3c3c;
                color: #d4d4d4;
                padding: 4px;
                selection-background-color: #264f78;
            }
            QCheckBox {
                color: #d4d4d4;
            }
            QPushButton {
                background-color: #37373d;
                border: none;
                color: #d4d4d4;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #45454d;
            }
        """)
        
        layout = QVBoxLayout(find_dialog)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Search input with label
        input_layout = QHBoxLayout()
        search_label = QLabel("Find:")
        search_input = QLineEdit()
        search_input.setPlaceholderText("Enter search text...")
        input_layout.addWidget(search_label)
        input_layout.addWidget(search_input)
        layout.addLayout(input_layout)
        
        # Options
        options_layout = QVBoxLayout()
        case_sensitive = QCheckBox("Match case")
        whole_words = QCheckBox("Whole words")
        wrap_search = QCheckBox("Wrap around")
        wrap_search.setChecked(True)
        regex = QCheckBox("Regular expression")
        
        options_layout.addWidget(case_sensitive)
        options_layout.addWidget(whole_words)
        options_layout.addWidget(wrap_search)
        options_layout.addWidget(regex)
        layout.addLayout(options_layout)
        
        # Results label
        results_label = QLabel("")
        results_label.setStyleSheet("color: #888;")
        layout.addWidget(results_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        find_next = QPushButton("Find Next")
        find_prev = QPushButton("Find Previous")
        find_all = QPushButton("Find All")
        button_layout.addWidget(find_prev)
        button_layout.addWidget(find_next)
        button_layout.addWidget(find_all)
        layout.addLayout(button_layout)
        
        # Store last search position and state
        last_line = 0
        last_index = 0
        total_found = 0
        search_in_progress = False
        
        # Set up search indicator
        self.setIndicatorDrawUnder(True)
        self.setIndicatorForegroundColor(QColor("#264f78"), 0)  # VS Code selection blue
        self.setIndicatorOutlineColor(QColor("#264f78"), 0)
        
        def update_results(count, clear=False):
            if clear:
                results_label.setText("")
                results_label.setStyleSheet("color: #888;")
                # Clear all indicators
                self.clearIndicatorRange(0, 0, self.lines(), self.lineLength(self.lines() - 1), 0)
            elif count > 0:
                results_label.setText(f"Found {count} matches")
                results_label.setStyleSheet("color: #89d185;")  # Light green
            else:
                results_label.setText("No matches found")
                results_label.setStyleSheet("color: #f48771;")  # Light red
        
        def do_find(forward=True, from_start=False):
            nonlocal last_line, last_index, total_found, search_in_progress
            if search_in_progress:
                return
                
            text = search_input.text()
            if not text:
                update_results(0, clear=True)
                return
            
            search_in_progress = True
            try:
                # Get current position or start position
                if from_start:
                    if forward:
                        line, index = 0, 0
                    else:
                        # For backward search, start from end of document
                        line = self.lines() - 1
                        index = len(self.text(line))
                else:
                    line, index = self.getCursorPosition()
                    # Move cursor position based on direction
                    if forward:
                        # Move one character forward to avoid finding the same match
                        index += 1
                    else:
                        # For backward search, start from current position
                        if index > 0:
                            index -= 1
                        elif line > 0:
                            line -= 1
                            index = len(self.text(line))
                
                # Clear previous indicators
                self.clearIndicatorRange(0, 0, self.lines(), self.lineLength(self.lines() - 1), 0)
                
                found = self.findFirst(text, 
                                     regex.isChecked(), 
                                     case_sensitive.isChecked(),
                                     whole_words.isChecked(), 
                                     True,  # wrap
                                     forward,
                                     line,
                                     index)
                
                if found:
                    # Highlight current selection
                    line_from, index_from, line_to, index_to = self.getSelection()
                    self.fillIndicatorRange(line_from, index_from, line_to, index_to, 0)
                    
                    # Update last position
                    last_line, last_index = self.getCursorPosition()
                    if total_found == 0:  # Only count on first find
                        total_found = count_occurrences(text)
                    update_results(total_found)
                else:
                    update_results(0)
            finally:
                search_in_progress = False
        
        def count_occurrences(text):
            """Count occurrences without moving cursor."""
            if not text:
                return 0
            
            # Store current position
            current_line, current_index = self.getCursorPosition()
            current_selection = self.getSelection()
            
            count = 0
            # Start from beginning
            found = self.findFirst(text, 
                                 regex.isChecked(), 
                                 case_sensitive.isChecked(),
                                 whole_words.isChecked(), 
                                 False,  # Don't wrap
                                 True,   # Forward
                                 0,      # Start line
                                 0)      # Start index
            
            while found:
                count += 1
                # Get current match position
                line, index = self.getCursorPosition()
                # Move to end of match to find next
                _, _, line_to, index_to = self.getSelection()
                self.setCursorPosition(line_to, index_to)
                found = self.findNext()
            
            # Restore original position and selection
            self.setCursorPosition(current_line, current_index)
            if current_selection[0] != -1:  # If there was a selection
                self.setSelection(*current_selection)
            
            return count
        
        def do_find_all():
            """Highlight all matches in the document."""
            text = search_input.text()
            if not text:
                update_results(0, clear=True)
                return
            
            # Clear previous indicators
            self.clearIndicatorRange(0, 0, self.lines(), self.lineLength(self.lines() - 1), 0)
            
            # Store current position
            current_line, current_index = self.getCursorPosition()
            current_selection = self.getSelection()
            
            # Find and highlight all matches
            count = 0
            found = self.findFirst(text, 
                                 regex.isChecked(), 
                                 case_sensitive.isChecked(),
                                 whole_words.isChecked(), 
                                 False,  # Don't wrap
                                 True,   # Forward
                                 0,      # Start line
                                 0)      # Start index
            
            while found:
                # Get the selection and mark it
                line_from, index_from, line_to, index_to = self.getSelection()
                self.fillIndicatorRange(line_from, index_from, line_to, index_to, 0)
                count += 1
                
                # Move to end of match to find next
                self.setCursorPosition(line_to, index_to)
                found = self.findNext()
            
            # Restore original position and selection
            self.setCursorPosition(current_line, current_index)
            if current_selection[0] != -1:  # If there was a selection
                self.setSelection(*current_selection)
            
            update_results(count)
        
        def on_text_changed():
            """Handle text changes in search input."""
            nonlocal total_found
            total_found = 0  # Reset count
            update_results(0, clear=True)  # Clear results label and highlights
        
        # Connect signals
        find_next.clicked.connect(lambda: do_find(forward=True))
        find_prev.clicked.connect(lambda: do_find(forward=False))
        find_all.clicked.connect(do_find_all)
        search_input.returnPressed.connect(lambda: do_find(forward=True))
        search_input.textChanged.connect(on_text_changed)
        
        # Set focus to search input
        search_input.setFocus()
        
        find_dialog.setModal(False)
        find_dialog.show()
    
    def toggle_comment(self):
        # Get the selection or current line
        if self.hasSelectedText():
            start_line, start_col, end_line, end_col = self.getSelection()
        else:
            line, _ = self.getCursorPosition()
            start_line = end_line = line
            start_col = end_col = 0
        
        # Determine if we should comment or uncomment
        should_comment = True
        for line in range(start_line, end_line + 1):
            text = self.text(line)
            if text.lstrip().startswith('#'):
                should_comment = False
                break
        
        # Begin undo action
        self.beginUndoAction()
        
        try:
            for line in range(start_line, end_line + 1):
                text = self.text(line)
                if should_comment:
                    self.setSelection(line, 0, line, 0)
                    self.replaceSelectedText('# ' + text)
                else:
                    if text.lstrip().startswith('#'):
                        pos = text.find('#')
                        self.setSelection(line, pos, line, pos + 2)
                        self.replaceSelectedText('')
        finally:
            self.endUndoAction()
    
    def _handle_modification(self, modified):
        self.is_modified = modified
        if hasattr(self, 'modification_callback'):
            self.modification_callback(modified)

    def setup_keyboard_shortcuts(self):
        # Save
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save_file)
        
        # Find
        find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        find_shortcut.activated.connect(self.show_find_dialog)
        
        # Comment/Uncomment
        comment_shortcut = QShortcut(QKeySequence("Ctrl+/"), self)
        comment_shortcut.activated.connect(self.toggle_comment)
        
        # Additional editor shortcuts using standard key bindings
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY, 
                          ord('Z') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_UNDO)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('Y') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_REDO)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('C') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_COPY)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('V') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_PASTE)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('X') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_CUT)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('A') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_SELECTALL)

    def setup_toolbar(self):
        """Set up the editor toolbar."""
        self.toolbar = QToolBar()
        self.toolbar.setFixedHeight(28)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setStyleSheet("""
            QToolBar {
                spacing: 2px;
                background: #2d2d2d;
                border: none;
                border-bottom: 1px solid #1e1e1e;
                padding: 2px;
            }
            QToolButton {
                background: transparent;
                border: none;
                padding: 4px;
                color: #d4d4d4;
                font-size: 14px;
            }
            QToolButton:hover {
                background: #3d3d42;
            }
            QToolButton:pressed {
                background: #434346;
            }
            QToolBar::separator {
                background: #404040;
                width: 1px;
                margin: 4px 4px;
            }
        """)

        # Add actions
        save_action = self.toolbar.addAction("💾")
        save_action.setToolTip("Save (Ctrl+S)")
        save_action.triggered.connect(self.save_file)

        self.toolbar.addSeparator()

        undo_action = self.toolbar.addAction("↩")
        undo_action.setToolTip("Undo (Ctrl+Z)")
        undo_action.triggered.connect(self.undo)

        redo_action = self.toolbar.addAction("↪")
        redo_action.setToolTip("Redo (Ctrl+Y)")
        redo_action.triggered.connect(self.redo)

        self.toolbar.addSeparator()

        cut_action = self.toolbar.addAction("✂")
        cut_action.setToolTip("Cut (Ctrl+X)")
        cut_action.triggered.connect(self.cut)

        copy_action = self.toolbar.addAction("📋")
        copy_action.setToolTip("Copy (Ctrl+C)")
        copy_action.triggered.connect(self.copy)

        paste_action = self.toolbar.addAction("📌")
        paste_action.setToolTip("Paste (Ctrl+V)")
        paste_action.triggered.connect(self.paste)

        self.toolbar.addSeparator()

        find_action = self.toolbar.addAction("🔍")
        find_action.setToolTip("Find (Ctrl+F)")
        find_action.triggered.connect(self.show_find_dialog)

        comment_action = self.toolbar.addAction("//")
        comment_action.setToolTip("Toggle Comment (Ctrl+/)")
        comment_action.triggered.connect(self.toggle_comment)

        indent_action = self.toolbar.addAction("→")
        indent_action.setToolTip("Indent (Tab)")
        indent_action.triggered.connect(self.indent)

        unindent_action = self.toolbar.addAction("←")
        unindent_action.setToolTip("Unindent (Shift+Tab)")
        unindent_action.triggered.connect(self.unindent)

        # Add toolbar to parent layout
        if isinstance(self.parent(), QWidget):
            layout = self.parent().layout()
            if layout:
                layout.insertWidget(0, self.toolbar)

    def indent(self):
        """Indent the selected lines or current line."""
        if self.hasSelectedText():
            # Get selection
            line_from, index_from, line_to, index_to = self.getSelection()
            
            # Begin undo action
            self.beginUndoAction()
            
            try:
                # Indent each line in selection
                for line in range(line_from, line_to + 1):
                    self.insertAt("    ", line, 0)
            finally:
                self.endUndoAction()
        else:
            # Indent current line
            line, _ = self.getCursorPosition()
            self.insertAt("    ", line, 0)

    def unindent(self):
        """Unindent the selected lines or current line."""
        if self.hasSelectedText():
            # Get selection
            line_from, index_from, line_to, index_to = self.getSelection()
            
            # Begin undo action
            self.beginUndoAction()
            
            try:
                # Unindent each line in selection
                for line in range(line_from, line_to + 1):
                    text = self.text(line)
                    if text.startswith("    "):
                        self.setSelection(line, 0, line, 4)
                        self.removeSelectedText()
                    elif text.startswith("\t"):
                        self.setSelection(line, 0, line, 1)
                        self.removeSelectedText()
            finally:
                self.endUndoAction()
        else:
            # Unindent current line
            line, _ = self.getCursorPosition()
            text = self.text(line)
            if text.startswith("    "):
                self.setSelection(line, 0, line, 4)
                self.removeSelectedText()
            elif text.startswith("\t"):
                self.setSelection(line, 0, line, 1)
                self.removeSelectedText()

    """Code editor with syntax highlighting and code intelligence."""
    
    def __init__(self, parent=None):
        """Initialize the code editor."""
        super().__init__(parent)
        
        # Set up editor properties
        self.setUtf8(True)
        self.setFont(QFont("Consolas", 10))
        self.setMarginsFont(QFont("Consolas", 10))
        
        # Enable line numbers
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "000")
        self.setMarginsForegroundColor(QColor("#808080"))
        self.setMarginsBackgroundColor(QColor("#1E1E1E"))
        
        # Set up Python lexer
        self.lexer = QsciLexerPython(self)
        self.lexer.setDefaultFont(QFont("Consolas", 10))
        self.setLexer(self.lexer)
        
        # Set up colors
        self.setCaretForegroundColor(QColor("#FFFFFF"))
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#2D2D2D"))
        
        # Set up selection colors
        self.setSelectionBackgroundColor(QColor("#264F78"))
        self.setSelectionForegroundColor(QColor("#FFFFFF"))
        
        # Set up indentation
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setIndentationGuides(True)
        self.setAutoIndent(True)
        
        # Set up toolbar
        self.toolbar = QToolBar()
        self.setup_toolbar()
        
        # Set up code intelligence
        self.setup_code_intelligence()
        
        # Initialize Jedi for code intelligence
        self.jedi_script = None
        
        # Track file path and modification state
        self.current_file = None
        self.is_modified = False
        self.modificationChanged.connect(self._handle_modification)
        
    def setup_editor(self):
        """Set up editor settings."""
        # Enable UTF-8
        self.setUtf8(True)
        
        # Set up lexer for Python syntax highlighting
        lexer = QsciLexerPython()
        lexer.setDefaultFont(QFont("Consolas", 10))
        self.setLexer(lexer)
        
        # Enable line numbers
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "000")
        
        # Enable folding markers
        self.setMarginType(1, QsciScintilla.MarginType.SymbolMargin)
        self.setMarginWidth(1, 15)
        self.setMarginSensitivity(1, True)
        self.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle)
        
        # Set up markers
        # Error marker (using 'x')
        self.markerDefine(b'x', 0)
        self.setMarkerBackgroundColor(QColor("#FF0000"), 0)
        self.setMarkerForegroundColor(QColor("#FFFFFF"), 0)
        
        # Warning marker (using '!')
        self.markerDefine(b'!', 1)
        self.setMarkerBackgroundColor(QColor("#FFA500"), 1)
        self.setMarkerForegroundColor(QColor("#FFFFFF"), 1)
        
        # Enable edge mode (vertical line at column 80)
        self.setEdgeMode(QsciScintilla.EdgeMode.EdgeLine)
        self.setEdgeColumn(80)
        self.setEdgeColor(QColor("#2d2d2d"))
        
        # Set up auto-completion
        self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(True)
        
        # Set up call tips
        self.setCallTipsStyle(QsciScintilla.CallTipsStyle.CallTipsContext)
        self.setCallTipsVisible(0)
        
        # Set up indicators for search results
        self.indicatorDefine(QsciScintilla.IndicatorStyle.RoundBoxIndicator, 0)
        self.setIndicatorForegroundColor(QColor("#569CD6"), 0)
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
    def setup_style(self):
        """Set up editor styling."""
        # Set dark theme colors
        self.setPaper(QColor("#1e1e1e"))  # Background
        self.setColor(QColor("#d4d4d4"))  # Default text
        
        # Set selection colors
        self.setSelectionBackgroundColor(QColor("#264f78"))
        self.setSelectionForegroundColor(QColor("#ffffff"))
        
        # Set caret style
        self.setCaretWidth(2)
        self.setCaretForegroundColor(QColor("#569CD6"))
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#282828"))
        
        # Set indentation guides
        self.setIndentationGuides(True)
        self.setIndentationGuidesBackgroundColor(QColor("#2d2d2d"))
        self.setIndentationGuidesForegroundColor(QColor("#2d2d2d"))
        
        # Set tab width and indentation
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setIndentationWidth(4)
        self.setAutoIndent(True)
        self.setBackspaceUnindents(True)
        
    def setup_margins(self):
        """Set up editor margins."""
        # Line number margin
        self.setMarginLineNumbers(0, True)
        self.setMarginWidth(0, "000")
        self.setMarginBackgroundColor(0, QColor("#1e1e1e"))
        self.setMarginsForegroundColor(QColor("#858585"))
        
        # Folding margin
        self.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle, 1)
        self.setMarginWidth(1, 15)
        self.setMarginBackgroundColor(1, QColor("#1e1e1e"))
        self.setFoldMarginColors(QColor("#1e1e1e"), QColor("#1e1e1e"))
        
    def setup_autocomplete(self):
        """Set up code autocompletion."""
        self.api = QsciAPIs(self.lexer())
        
        # Add Python keywords
        for kw in keyword.kwlist:
            self.api.add(kw)
            
        # Add common Python builtins
        for builtin in dir(__builtins__):
            if not builtin.startswith('_'):
                self.api.add(builtin)
                
        self.api.prepare()
        
    def setup_keyboard_shortcuts(self):
        """Set up keyboard shortcuts."""
        # Save
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save_file)
        
        # Find
        find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        find_shortcut.activated.connect(self.show_find_dialog)
        
        # Comment/Uncomment
        comment_shortcut = QShortcut(QKeySequence("Ctrl+/"), self)
        comment_shortcut.activated.connect(self.toggle_comment)
        
        # Additional editor shortcuts using standard key bindings
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY, 
                          ord('Z') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_UNDO)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('Y') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_REDO)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('C') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_COPY)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('V') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_PASTE)
        self.SendScintilla(QsciScintilla.SCI_ASSIGNCMDKEY,
                          ord('X') + (QsciScintilla.SCMOD_CTRL << 16),
                          QsciScintilla.SCI_CUT)
                          
    def setup_toolbar(self):
        """Set up the editor toolbar."""
        self.toolbar = QToolBar()
        self.toolbar.setFixedHeight(28)
        self.toolbar.setIconSize(QSize(16, 16))
        self.toolbar.setStyleSheet("""
            QToolBar {
                spacing: 2px;
                background: #2d2d2d;
                border: none;
                border-bottom: 1px solid #1e1e1e;
                padding: 2px;
            }
            QToolButton {
                background: transparent;
                border: none;
                padding: 4px;
                color: #d4d4d4;
                font-size: 14px;
            }
            QToolButton:hover {
                background: #3d3d42;
            }
            QToolButton:pressed {
                background: #434346;
            }
            QToolBar::separator {
                background: #404040;
                width: 1px;
                margin: 4px 4px;
            }
        """)

        # Add actions
        save_action = self.toolbar.addAction("💾")
        save_action.setToolTip("Save (Ctrl+S)")
        save_action.triggered.connect(self.save_file)

        self.toolbar.addSeparator()

        undo_action = self.toolbar.addAction("↩")
        undo_action.setToolTip("Undo (Ctrl+Z)")
        undo_action.triggered.connect(self.undo)

        redo_action = self.toolbar.addAction("↪")
        redo_action.setToolTip("Redo (Ctrl+Y)")
        redo_action.triggered.connect(self.redo)

        self.toolbar.addSeparator()

        comment_action = self.toolbar.addAction("//")
        comment_action.setToolTip("Toggle Comment (Ctrl+/)")
        comment_action.triggered.connect(self.toggle_comment)
        
    def setup_code_intelligence(self):
        """Set up code intelligence features."""
        # Enable auto-completion
        self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(True)
        
        # Enable call tips
        self.setCallTipsStyle(QsciScintilla.CallTipsStyle.CallTipsNoContext)
        self.setCallTipsVisible(0)
        
    def show_find_dialog(self):
        """Show the find dialog."""
        find_dialog = FindDialog(self)
        find_dialog.show()
        
    def toggle_comment(self):
        """Toggle comment on selected lines."""
        # Get current selection or current line
        if self.hasSelectedText():
            line_from, index_from, line_to, index_to = self.getSelection()
        else:
            line_from = line_to = self.getCursorPosition()[0]
            index_from = index_to = 0
            
        # Store original cursor position
        original_pos = self.getCursorPosition()
        
        # Begin undo action
        self.beginUndoAction()
        
        try:
            # Process each line in selection
            for line in range(line_from, line_to + 1):
                line_text = self.text(line)
                stripped_text = line_text.lstrip()
                indent = len(line_text) - len(stripped_text)
                
                if stripped_text.startswith('#'):
                    # Uncomment: remove first # and one space if present
                    new_text = line_text[:indent] + stripped_text[1:].lstrip(' ')
                else:
                    # Comment: add # with space
                    new_text = line_text[:indent] + '# ' + stripped_text
                    
                # Replace line
                self.setSelection(line, 0, line, len(line_text))
                self.replaceSelectedText(new_text)
        finally:
            # End undo action
            self.endUndoAction()
            
        # Restore cursor position
        self.setCursorPosition(*original_pos)
        
    def save_file(self):
        """Save the current file."""
        if self.current_file:
            try:
                with open(self.current_file, 'w', encoding='utf-8') as f:
                    f.write(self.text())
                self.setModified(False)
            except Exception as e:
                logger.error(f"Error saving file: {e}")
                
    def _handle_modification(self, modified):
        """Handle modification state changes."""
        self.is_modified = modified
        
    def update_code_intelligence(self, file_path, content):
        """Update code intelligence for the current file."""
        try:
            self.current_file = file_path
            self.jedi_script = jedi.Script(code=content, path=file_path)
        except Exception as e:
            logger.error(f"Error updating code intelligence: {e}")
            self.jedi_script = None 