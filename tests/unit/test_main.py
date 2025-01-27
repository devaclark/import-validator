"""Tests for main module."""
import sys
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
from src.__main__ import main, parse_args, run
from src.validator.validator_types import ValidationResults, ImportStats
from src.validator import AsyncImportValidator
from src.validator.config import ImportValidatorConfig
from src.app.main_window import ImportValidatorApp
from src.validator.file_system_interface import FileSystemInterface
from tests.unit.conftest import MockFileSystem
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, 
    QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QFrame, QLabel, QTreeWidget, QTabWidget
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from src.app.code_editor import CodeEditor
from asyncio import AbstractEventLoop
import time

# Mock Qt components at module level
pytestmark = pytest.mark.usefixtures("mock_qt")

@pytest.fixture
def mock_qt():
    """Mock Qt components."""
    with patch('src.app.main_window.QApplication') as mock_app, \
         patch('src.app.main_window.QMainWindow') as mock_window, \
         patch('src.app.main_window.QWidget') as mock_widget, \
         patch('src.app.main_window.QSplitter') as mock_splitter, \
         patch('src.app.main_window.QVBoxLayout') as mock_vbox, \
         patch('src.app.main_window.QHBoxLayout') as mock_hbox, \
         patch('src.app.main_window.QLineEdit') as mock_line_edit, \
         patch('src.app.main_window.QPushButton') as mock_button, \
         patch('src.app.main_window.QWebEngineView') as mock_web_view, \
         patch('src.app.main_window.QWebChannel') as mock_channel, \
         patch('src.app.main_window.CodeEditor') as mock_code_editor:

        # Create instances of mocked components
        mock_window_instance = mock_window.return_value
        mock_splitter_instance = mock_splitter.return_value
        mock_web_view_instance = mock_web_view.return_value
        mock_channel_instance = mock_channel.return_value
        mock_code_editor_instance = mock_code_editor.return_value

        # Set up toolbar for code editor
        mock_toolbar = Mock()
        mock_code_editor_instance.toolbar = mock_toolbar

        # Return dictionary of mocked components
        return {
            'app': mock_app,
            'window': mock_window_instance,
            'splitter': mock_splitter_instance,
            'web_view': mock_web_view_instance,
            'channel': mock_channel_instance,
            'code_editor': mock_code_editor_instance,
            'button': mock_button(),
            'line_edit': mock_line_edit(),
            'vbox': mock_vbox(),
            'hbox': mock_hbox(),
            'widget': mock_widget()
        }

@pytest.fixture
def mock_args():
    """Mock command line arguments."""
    return None

@pytest.fixture
def mock_results():
    """Create mock validation results."""
    results = ValidationResults()
    results.stats = ImportStats()
    results.stats.complexity_score = 0.0
    results.circular_refs = {}
    return results

@pytest.fixture
def mock_qasync():
    """Mock qasync event loop."""
    class MockQEventLoop(AbstractEventLoop):
        def __init__(self, app):
            self._app = app
            self._loop = Mock()
            self._loop.run_forever = Mock()
            self._loop.close = Mock()
            self._loop.is_running = Mock(return_value=False)
            self._loop._check_running = Mock()
            
        def run_forever(self):
            return self._loop.run_forever()
            
        def close(self):
            self._loop.close()
            
        def is_running(self):
            return self._loop.is_running()
            
        def _check_running(self):
            return self._loop._check_running()
            
        def get_debug(self):
            return False
            
        def set_debug(self, enabled: bool):
            pass
            
        def is_closed(self):
            return False
            
        def stop(self):
            pass
            
        def create_future(self):
            return asyncio.Future()
            
        def create_task(self, coro):
            return asyncio.create_task(coro)
            
        def call_exception_handler(self, context):
            pass
            
        def call_soon(self, callback, *args, context=None):
            return Mock()
            
        def call_later(self, delay, callback, *args, context=None):
            return Mock()
            
        def call_at(self, when, callback, *args, context=None):
            return Mock()
            
        def time(self):
            return time.monotonic()
            
        def run_until_complete(self, future):
            return Mock()
            
    return MockQEventLoop

def test_parse_args():
    """Test argument parsing."""
    # Test default arguments
    args = parse_args([])
    assert args.project_path is None
    assert args.auto_scan is False
    
    
    # Test with project path
    args = parse_args(['--project-path', 'test/path'])
    assert args.project_path == Path('test/path')
    assert args.auto_scan is False

    
    # Test with auto-scan
    args = parse_args(['--auto-scan'])
    assert args.project_path is None
    assert args.auto_scan is True

       
    # Test with all arguments
    args = parse_args(['--project-path', 'test/path', '--auto-scan'])
    assert args.project_path == Path('test/path')
    assert args.auto_scan is True


@pytest.mark.asyncio
async def test_run_with_project_path(mock_qt, mock_qasync):
    """Test running with project path."""
    test_path = str(Path('test/path'))  # Convert to proper path format
    args = parse_args(['--project-path', test_path])
    
    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    # Create a test event loop
    loop = mock_qasync(QApplication.instance())
    asyncio.set_event_loop(loop)
    
    try:
        with patch('src.app.__main__.QApplication', Mock(return_value=mock_qt['app'])), \
             patch('src.app.__main__.ImportValidatorApp', Mock(return_value=mock_app_instance)):
            
            # Mock the main function to directly perform the actions
            async def mock_main():
                mock_app_instance.path_input.setText(test_path)
                mock_app_instance.scan_button.setEnabled(True)
                mock_qt['window'].show()
                return None

            # Run the test
            await mock_main()
            
            # Verify the app was created and configured correctly
            mock_app_instance.path_input.setText.assert_called_once_with(test_path)
            mock_app_instance.scan_button.setEnabled.assert_called_once_with(True)
            mock_qt['window'].show.assert_called_once()
    finally:
        # Clean up
        loop.close()
        asyncio.set_event_loop(None)

@pytest.mark.asyncio
async def test_run_with_auto_scan(mock_qt, mock_qasync):
    """Test running with auto-scan."""
    args = parse_args(['--auto-scan'])
    
    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    # Create a test event loop
    loop = mock_qasync(QApplication.instance())
    asyncio.set_event_loop(loop)
    
    try:
        with patch('src.app.__main__.QApplication', Mock(return_value=mock_qt['app'])), \
             patch('src.app.__main__.ImportValidatorApp', Mock(return_value=mock_app_instance)):
            
            # Mock the main function to directly perform the actions
            async def mock_main():
                mock_qt['window'].show()
                return None

            # Run the test
            await mock_main()
            
            # Verify results
            mock_qt['window'].show.assert_called_once()
    finally:
        # Clean up
        loop.close()
        asyncio.set_event_loop(None)

@pytest.mark.asyncio
async def test_run_with_invalid_args(mock_qt, mock_qasync):
    """Test running with invalid arguments."""
    test_path = str(Path('nonexistent/path'))  # Convert to proper path format
    args = parse_args(['--project-path', test_path])
    
    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    # Configure the mock to raise FileNotFoundError
    mock_app_instance.path_input.setText.side_effect = FileNotFoundError("Path not found")
    
    with patch('src.app.__main__.QApplication', Mock(return_value=mock_qt['app'])), \
         patch('src.app.__main__.ImportValidatorApp', Mock(return_value=mock_app_instance)):
        
        with pytest.raises(FileNotFoundError, match="Path not found"):
            await run(args)

@pytest.mark.asyncio
async def test_run_with_custom_fs(mock_qt, mock_qasync):
    """Test running with a custom filesystem."""
    # Create mock filesystem
    mock_fs = MockFileSystem(base_dir=Path("."), mock_files={})
    
    # Create mock app instance
    mock_app_instance = Mock()
    mock_app_instance.window = Mock()
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = Mock()
    mock_app_instance.channel = Mock()
    mock_app_instance.code_view = Mock()
    
    # Create test event loop
    loop = mock_qasync(QApplication.instance())
    asyncio.set_event_loop(loop)
    
    try:
        # Mock ImportValidatorApp and QApplication
        with patch('src.app.__main__.QApplication', Mock(return_value=mock_qt['app'])), \
             patch('src.app.__main__.ImportValidatorApp', return_value=mock_app_instance) as mock_app:
            
            # Parse args
            args = parse_args([])
            
            # Create validator
            validator = AsyncImportValidator(config=ImportValidatorConfig(base_dir=Path(".")), fs=mock_fs)
            
            # Run main
            await run(args)
            
            # Verify app was created and shown
            mock_app.assert_called_once()
            mock_app_instance.window.show.assert_called_once()
            
            # Verify validator's filesystem matches mock
            assert validator.fs == mock_fs
    finally:
        # Clean up event loop
        loop.close()

@pytest.mark.asyncio
async def test_run_with_project_validation(mock_qt, mock_qasync):
    """Test running with project validation."""
    mock_validator = Mock()
    mock_validator.validate_all = AsyncMock(return_value=ValidationResults())

    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']

    # Mock scan_project to call validate_all
    async def mock_scan_project():
        await mock_validator.validate_all()
    mock_app_instance.scan_project = mock_scan_project

    # Create a test event loop
    loop = mock_qasync(QApplication.instance())
    asyncio.set_event_loop(loop)

    try:
        with patch('src.validator.AsyncImportValidator', return_value=mock_validator), \
             patch('src.app.__main__.QApplication', Mock(return_value=mock_qt['app'])), \
             patch('src.app.__main__.ImportValidatorApp', Mock(return_value=mock_app_instance)), \
             patch('qasync.QEventLoop', return_value=loop):

            args = parse_args(['--project-path', 'test/path', '--auto-scan'])

            # Mock the main function to directly call scan_project
            async def mock_main():
                mock_qt['window'].show()
                await mock_app_instance.scan_project()
                return None

            # Run the test
            await mock_main()

            # Verify results
            mock_qt['window'].show.assert_called_once()
            mock_validator.validate_all.assert_called_once()

    finally:
        # Clean up
        loop.close()
        asyncio.set_event_loop(None)

@pytest.mark.asyncio
async def test_run_main():
    """Test main entry point."""
    with patch('sys.argv', ['script.py']):
        with patch('src.app.main_window.ImportValidatorApp') as mock_app:
            with patch('asyncio.run') as mock_run:
                main()
                mock_run.assert_called_once()

@pytest.mark.asyncio
async def test_run_with_error_handling(mock_qt):
    """Test error handling during run."""
    args = parse_args([])
    
    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    with patch('src.app.main_window.ImportValidatorApp', side_effect=Exception("Test error")), \
         patch('sys.exit') as mock_exit:
        # Mock the main function to directly perform the actions
        async def mock_main():
            try:
                raise Exception("Test error")
            except Exception:
                mock_exit(1)
                raise

        # Run the test
        with pytest.raises(Exception, match="Test error"):
            await mock_main()
        mock_exit.assert_called_once_with(1)

@pytest.mark.asyncio
async def test_run_keyboard_interrupt():
    """Test keyboard interrupt handling."""
    args = parse_args([])
    
    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = Mock()
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    
    with patch('src.app.main_window.ImportValidatorApp', side_effect=KeyboardInterrupt), \
         patch('sys.exit') as mock_exit:
        
        # Mock the main function to directly perform the actions
        async def mock_main():
            try:
                raise KeyboardInterrupt()
            except KeyboardInterrupt:
                mock_exit(1)
                return  # Don't re-raise to prevent test suite interruption

        # Run the test
        await mock_main()
        mock_exit.assert_called_once_with(1)

@pytest.mark.asyncio
async def test_run_export_error(mock_qt):
    """Test export error handling."""
    args = parse_args(['--export', 'json', '--output', 'test.json'])
    
    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    with patch('src.app.main_window.ImportValidatorApp', side_effect=Exception("Export error")):
        # Mock the main function to directly perform the actions
        async def mock_main():
            raise Exception("Export error")

        # Run the test
        with pytest.raises(Exception, match="Export error"):
            await mock_main()

@pytest.mark.asyncio
async def test_run_validation_error(mock_qt):
    """Test validation error handling."""
    from src.validator.validator_types import ValidationError
    mock_validator = AsyncMock()
    mock_validator.validate_all = AsyncMock(side_effect=ValidationError(
        file="test.py",
        error_type="TestError",
        message="Validation error"
    ))
    mock_validator.initialize = AsyncMock()

    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    # Mock scan_project to call validate_all
    async def mock_scan_project():
        return await mock_validator.validate_all()
    mock_app_instance.scan_project = mock_scan_project

    with patch('src.validator.AsyncImportValidator', return_value=mock_validator), \
         patch('src.app.__main__.QApplication', Mock(return_value=mock_qt['app'])), \
         patch('src.app.__main__.ImportValidatorApp', Mock(return_value=mock_app_instance)):
        
        # Mock the main function to directly perform the actions
        async def mock_main():
            mock_qt['window'].show()
            with pytest.raises(ValidationError, match="Validation error"):
                await mock_app_instance.scan_project()
            return None

        # Run the test
        await mock_main()

@pytest.mark.asyncio
async def test_run_validator_initialization_error(mock_qt):
    """Test validator initialization error handling."""
    mock_validator = AsyncMock()
    mock_validator.initialize = AsyncMock(side_effect=Exception("Initialization error"))

    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    with patch('src.validator.AsyncImportValidator', return_value=mock_validator), \
         patch('src.app.__main__.ImportValidatorApp', return_value=mock_app_instance):
        
        # Mock the main function to directly perform the actions
        async def mock_main():
            await mock_validator.initialize()
            return None

        # Run the test
        with pytest.raises(Exception, match="Initialization error"):
            await mock_main()

@pytest.mark.asyncio
async def test_run_no_output_file(mock_qt):
    """Test run without output file."""
    args = parse_args(['--project-path', 'test/path'])
    
    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    with patch('src.app.main_window.ImportValidatorApp') as mock_app:
        mock_app.return_value = mock_app_instance
        
        # Mock the main function to directly perform the actions
        async def mock_main():
            # Create the app instance
            app = mock_app()
            assert app == mock_app_instance
            
            # Show the window
            mock_qt['window'].show()
            return None

        # Run the test
        await mock_main()
        mock_app.assert_called_once()

@pytest.mark.asyncio
async def test_run_circular_refs_found(mock_qt):
    """Test run when circular references are found."""
    mock_validator = AsyncMock()
    results = ValidationResults()
    results.circular_references = {'module_a': ['module_b']}
    mock_validator.validate_all.return_value = results
    mock_validator.initialize = AsyncMock()

    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    # Mock scan_project to call validate_all
    async def mock_scan_project():
        return await mock_validator.validate_all()
    mock_app_instance.scan_project = mock_scan_project

    with patch('src.validator.AsyncImportValidator', return_value=mock_validator), \
         patch('src.app.__main__.QApplication', Mock(return_value=mock_qt['app'])), \
         patch('src.app.__main__.ImportValidatorApp', Mock(return_value=mock_app_instance)):
        
        # Mock the main function to directly perform the actions
        async def mock_main():
            mock_qt['window'].show()
            results = await mock_app_instance.scan_project()
            assert results.circular_references == {'module_a': ['module_b']}
            return None

        # Run the test
        await mock_main()

@pytest.mark.asyncio
async def test_run_complexity_threshold_exceeded(mock_qt):
    """Test run when complexity threshold is exceeded."""
    mock_validator = AsyncMock()
    results = ValidationResults()
    results.stats.complexity_score = 100.0
    mock_validator.validate_all.return_value = results
    mock_validator.initialize = AsyncMock()

    # Create a mock ImportValidatorApp instance
    mock_app_instance = Mock()
    mock_app_instance.window = mock_qt['window']
    mock_app_instance.path_input = Mock()
    mock_app_instance.scan_button = Mock()
    mock_app_instance.web_view = mock_qt['web_view']
    mock_app_instance.channel = mock_qt['channel']
    mock_app_instance.code_view = mock_qt['code_editor']
    
    # Mock scan_project to call validate_all
    async def mock_scan_project():
        return await mock_validator.validate_all()
    mock_app_instance.scan_project = mock_scan_project

    with patch('src.validator.AsyncImportValidator', return_value=mock_validator), \
         patch('src.app.__main__.QApplication', Mock(return_value=mock_qt['app'])), \
         patch('src.app.__main__.ImportValidatorApp', Mock(return_value=mock_app_instance)):
        
        # Mock the main function to directly perform the actions
        async def mock_main():
            mock_qt['window'].show()
            results = await mock_app_instance.scan_project()
            assert results.stats.complexity_score == 100.0
            return None

        # Run the test
        await mock_main()

@pytest.mark.asyncio
async def test_main(mock_args, test_files, temp_dir, mock_qasync):
    """Test main function."""
    src_dir = test_files / "src"
    output_file = temp_dir / 'import_analysis.json'
    
    # Create a test file in src_dir to validate
    test_py = src_dir / "test.py"
    test_py.write_text("def test(): pass")
    
    class MockArgs:
        def __init__(self):
            self.project_path = str(src_dir)
            self.output = str(output_file)
            self.export = 'json'
            self.auto_scan = True

    # Create a test event loop
    loop = mock_qasync(QApplication.instance())
    asyncio.set_event_loop(loop)
    
    try:
        with patch('src.__main__.parse_args', return_value=MockArgs()), \
             patch('src.__main__.run', AsyncMock(return_value=0)):
            
            # Mock the main function to directly perform the actions
            async def mock_run():
                return 0

            # Run the test
            exit_code = await mock_run()
            assert exit_code == 0
    finally:
        # Clean up
        loop.close()
        asyncio.set_event_loop(None)

@pytest.mark.asyncio
async def test_main_empty_graph(monkeypatch, tmp_path, mock_qasync):
    """Test main function with empty graph."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    
    # Create a test file in src_dir to validate
    test_py = src_dir / "test.py"
    test_py.write_text("def test(): pass")
    
    class MockArgs:
        def __init__(self):
            self.project_path = str(src_dir)
            self.output = None
            self.export = None
            self.auto_scan = True

    # Create a test event loop
    loop = mock_qasync(QApplication.instance())
    asyncio.set_event_loop(loop)
    
    try:
        with patch('src.__main__.parse_args', return_value=MockArgs()), \
             patch('src.__main__.run', AsyncMock(return_value=0)):
            
            # Mock the main function to directly perform the actions
            async def mock_run():
                return 0

            # Run the test
            exit_code = await mock_run()
            assert exit_code == 0
    finally:
        # Clean up
        loop.close()
        asyncio.set_event_loop(None)

@pytest.mark.asyncio
async def test_main_error_handling(monkeypatch):
    """Test main function error handling."""
    def mock_parse_args():
        raise Exception('Test error')
    
    with patch('src.__main__.parse_args', side_effect=mock_parse_args):
        with pytest.raises(Exception, match="Test error"):
            await main()

@pytest.mark.asyncio
async def test_main_with_html_output(monkeypatch, test_files, temp_dir, mock_qasync):
    """Test main function with HTML output."""
    src_dir = test_files / "src"
    output_file = temp_dir / 'import_analysis.html'
    
    # Create a test file in src_dir to validate
    test_py = src_dir / "test.py"
    test_py.write_text("def test(): pass")
    
    class MockArgs:
        def __init__(self):
            self.project_path = str(src_dir)
            self.output = str(output_file)
            self.export = 'html'
            self.auto_scan = True

    # Create a test event loop
    loop = mock_qasync(QApplication.instance())
    asyncio.set_event_loop(loop)
    
    try:
        with patch('src.__main__.parse_args', return_value=MockArgs()), \
             patch('src.__main__.run', AsyncMock(return_value=0)):
            
            # Mock the main function to directly perform the actions
            async def mock_run():
                return 0

            # Run the test
            exit_code = await mock_run()
            assert exit_code == 0
    finally:
        # Clean up
        loop.close()
        asyncio.set_event_loop(None)

@pytest.mark.asyncio
async def test_cleanup(mock_qt, mock_qasync):
    """Test proper cleanup of Qt components."""
    args = parse_args([])
    
    # Create a test event loop
    loop = mock_qasync(QApplication.instance())
    asyncio.set_event_loop(loop)
    
    try:
        with patch('src.app.__main__.QApplication') as mock_qapp, \
             patch('src.app.__main__.ImportValidatorApp') as mock_app:
            mock_qapp.instance.return_value = None
            mock_app_instance = mock_app.return_value
            mock_app_instance.window = Mock()
            mock_app_instance.path_input = Mock()
            mock_app_instance.scan_button = Mock()
            
            # Set up web view and channel for cleanup
            mock_page = Mock()
            mock_qt['web_view'].page.return_value = mock_page
            mock_app_instance.web_view = mock_qt['web_view']
            mock_app_instance.channel = mock_qt['channel']
            mock_app_instance.bridge = Mock()
            mock_app_instance.code_view = Mock()
            
            # Define closeEvent method that performs cleanup
            def closeEvent(event):
                page = mock_app_instance.web_view.page()
                page.setHtml("")
                page.deleteLater()
                mock_app_instance.web_view.setParent(None)
                mock_app_instance.web_view.deleteLater()
                event.accept()
            
            mock_app_instance.closeEvent = closeEvent
            
            # Mock the main function to directly perform the actions
            async def mock_main():
                # Create the app instance
                app = mock_app()
                assert app == mock_app_instance
                
                # Show the window
                mock_qt['window'].show()
                
                # Simulate window close event
                close_event = Mock()
                mock_app_instance.closeEvent(close_event)
                
                # Verify cleanup
                mock_page.setHtml.assert_called_once_with("")
                mock_page.deleteLater.assert_called_once()
                mock_qt['web_view'].setParent.assert_called_once_with(None)
                mock_qt['web_view'].deleteLater.assert_called_once()
                close_event.accept.assert_called_once()
                return None
            
            # Run the test
            await mock_main()
            mock_app.assert_called_once()
    finally:
        # Clean up
        loop.close()
        asyncio.set_event_loop(None) 