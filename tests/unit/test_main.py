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
from src.validator.qt_app import ImportValidatorApp
from src.validator.file_system_interface import FileSystemInterface
from tests.unit.conftest import MockFileSystem

# Mock Qt components at module level
pytestmark = pytest.mark.usefixtures("mock_qt")

@pytest.fixture
def mock_qt(monkeypatch):
    """Mock Qt components to prevent GUI from opening."""
    # Mock QApplication
    mock_app = Mock()
    mock_app.exec = Mock(return_value=0)
    mock_app.instance = Mock(return_value=None)
    monkeypatch.setattr('PyQt6.QtWidgets.QApplication', Mock(return_value=mock_app))
    
    # Mock QMainWindow
    mock_window = Mock()
    monkeypatch.setattr('PyQt6.QtWidgets.QMainWindow', Mock(return_value=mock_window))
    
    # Mock QWebEngineView
    mock_web_view = Mock()
    mock_web_view.page = Mock(return_value=Mock())
    monkeypatch.setattr('PyQt6.QtWebEngineWidgets.QWebEngineView', Mock(return_value=mock_web_view))
    
    # Mock QWebChannel
    mock_channel = Mock()
    monkeypatch.setattr('PyQt6.QtWebChannel.QWebChannel', Mock(return_value=mock_channel))
    
    # Mock event loop
    mock_loop = AsyncMock()
    mock_loop.run_forever = Mock(return_value=0)
    monkeypatch.setattr('qasync.QEventLoop', Mock(return_value=mock_loop))
    
    return {
        'app': mock_app,
        'window': mock_window,
        'web_view': mock_web_view,
        'channel': mock_channel,
        'loop': mock_loop
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

def test_parse_args():
    """Test argument parsing."""
    # Test default arguments
    args = parse_args([])
    assert args.project_path is None
    assert args.auto_scan is False
    assert args.server is False
    
    # Test with project path
    args = parse_args(['--project-path', 'test/path'])
    assert args.project_path == Path('test/path')
    assert args.auto_scan is False
    assert args.server is False
    
    # Test with auto-scan
    args = parse_args(['--auto-scan'])
    assert args.project_path is None
    assert args.auto_scan is True
    assert args.server is False
    
    # Test with server mode
    args = parse_args(['--server'])
    assert args.project_path is None
    assert args.auto_scan is False
    assert args.server is True
    
    # Test with all arguments
    args = parse_args(['--project-path', 'test/path', '--auto-scan', '--server'])
    assert args.project_path == Path('test/path')
    assert args.auto_scan is True
    assert args.server is True

@pytest.mark.asyncio
async def test_run_with_project_path(mock_qt):
    """Test running with project path."""
    args = parse_args(['--project-path', 'test/path'])
    with patch('src.validator.qt_app.ImportValidatorApp') as mock_app:
        await run(args)
        mock_app.assert_called_once()

@pytest.mark.asyncio
async def test_run_with_auto_scan(mock_qt):
    """Test running with auto-scan."""
    args = parse_args(['--auto-scan'])
    with patch('src.validator.qt_app.ImportValidatorApp') as mock_app:
        await run(args)
        mock_app.assert_called_once()

@pytest.mark.asyncio
async def test_run_with_server_mode(mock_qt):
    """Test running in server mode."""
    args = parse_args(['--server'])
    
    async def mock_server():
        return 0
        
    with patch('src.validator.qt_app.start_server', mock_server):
        result = await run(args)
        assert result == 0

@pytest.mark.asyncio
async def test_run_with_invalid_args(mock_qt):
    """Test running with invalid arguments."""
    args = parse_args(['--project-path', 'nonexistent/path'])
    with pytest.raises(FileNotFoundError):
        await run(args)

@pytest.mark.asyncio
async def test_run_with_custom_fs(mock_qt):
    """Test running with custom file system."""
    mock_fs = MockFileSystem(base_dir=Path("."), mock_files={})
    args = parse_args([])
    config = ImportValidatorConfig(base_dir=Path("."))
    validator = AsyncImportValidator(config=config, fs=mock_fs)
    app = ImportValidatorApp(validator)
    assert app is not None

@pytest.mark.asyncio
async def test_run_with_project_validation(mock_qt):
    """Test running with project validation."""
    mock_validator = Mock()
    mock_validator.validate_all = AsyncMock(return_value=ValidationResults())
    with patch('src.validator.AsyncImportValidator', return_value=mock_validator):
        args = parse_args(['--project-path', 'test/path', '--auto-scan'])
        await run(args)
        mock_validator.validate_all.assert_called_once()

@pytest.mark.asyncio
async def test_cleanup(mock_qt):
    """Test proper cleanup of Qt components."""
    args = parse_args([])
    with patch('src.validator.qt_app.ImportValidatorApp') as mock_app:
        await run(args)
        mock_app.assert_called_once()
        mock_qt['web_view'].deleteLater.assert_called_once()
        mock_qt['channel'].deleteLater.assert_called_once()

@pytest.mark.asyncio
async def test_run_main():
    """Test main entry point."""
    with patch('sys.argv', ['script.py']):
        with patch('src.validator.qt_app.ImportValidatorApp') as mock_app:
            with patch('asyncio.run') as mock_run:
                main()
                mock_run.assert_called_once()

@pytest.mark.asyncio
async def test_run_with_error_handling(mock_qt):
    """Test error handling during run."""
    args = parse_args([])
    with patch('src.validator.qt_app.ImportValidatorApp', side_effect=Exception("Test error")):
        with pytest.raises(Exception, match="Test error"):
            await run(args)

@pytest.mark.asyncio
async def test_run_keyboard_interrupt():
    """Test keyboard interrupt handling."""
    args = parse_args([])
    with patch('src.validator.qt_app.ImportValidatorApp', side_effect=KeyboardInterrupt):
        with patch('sys.exit') as mock_exit:
            await run(args)
            mock_exit.assert_called_once_with(1)

@pytest.mark.asyncio
async def test_run_error(mock_qt):
    """Test run with an error."""
    args = parse_args([])
    with patch('src.validator.qt_app.ImportValidatorApp', side_effect=Exception("Test error")):
        with patch('sys.exit') as mock_exit:
            with pytest.raises(Exception, match="Test error"):
                await run(args)
            mock_exit.assert_called_once_with(1)

@pytest.mark.asyncio
async def test_run_export_error(mock_qt):
    """Test export error handling."""
    args = parse_args(['--export', 'json', '--output', 'test.json'])
    with patch('src.validator.qt_app.ImportValidatorApp', side_effect=Exception("Export error")):
        with pytest.raises(Exception, match="Export error"):
            await run(args)

@pytest.mark.asyncio
async def test_run_validation_error(mock_qt):
    """Test validation error handling."""
    mock_validator = AsyncMock()
    mock_validator.validate_all.side_effect = ValidationError("Validation error")
    mock_validator.initialize = AsyncMock()

    with patch('src.validator.AsyncImportValidator', return_value=mock_validator):
        args = parse_args(['--project-path', 'test/path'])
        with pytest.raises(ValidationError, match="Validation error"):
            await run(args)

@pytest.mark.asyncio
async def test_run_validator_initialization_error(mock_qt):
    """Test validator initialization error handling."""
    mock_validator = AsyncMock()
    mock_validator.initialize.side_effect = Exception("Initialization error")

    with patch('src.validator.AsyncImportValidator', return_value=mock_validator):
        args = parse_args(['--project_path', 'test/path'])
        with pytest.raises(Exception, match="Initialization error"):
            await run(args)

@pytest.mark.asyncio
async def test_run_no_output_file(mock_qt):
    """Test run without output file."""
    args = parse_args(['--project-path', 'test/path'])
    with patch('src.validator.qt_app.ImportValidatorApp') as mock_app:
        await run(args)
        mock_app.assert_called_once()

@pytest.mark.asyncio
async def test_run_circular_refs_found(mock_qt):
    """Test run when circular references are found."""
    mock_validator = AsyncMock()
    results = ValidationResults()
    results.circular_references = {'module_a': ['module_b']}
    mock_validator.validate_all.return_value = results

    with patch('src.validator.AsyncImportValidator', return_value=mock_validator):
        args = parse_args(['--project-path', 'test/path', '--auto-scan'])
        await run(args)

@pytest.mark.asyncio
async def test_run_complexity_threshold_exceeded(mock_qt):
    """Test run when complexity threshold is exceeded."""
    mock_validator = AsyncMock()
    results = ValidationResults()
    results.import_stats = ImportStats(complexity_score=5.0)
    mock_validator.validate_all.return_value = results

    with patch('src.validator.AsyncImportValidator', return_value=mock_validator):
        args = parse_args(['--project-path', 'test/path', '--auto-scan'])
        await run(args)

@pytest.mark.asyncio
async def test_main(mock_args, test_files, temp_dir):
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
            self.server = False
    
    with patch('src.__main__.parse_args', return_value=MockArgs()), \
         patch('src.__main__.run', AsyncMock(return_value=0)), \
         patch('asyncio.run', return_value=0):
        exit_code = await main()
        assert exit_code == 0

@pytest.mark.asyncio
async def test_main_empty_graph(monkeypatch, tmp_path):
    """Test main function with empty source directory."""
    src_dir = tmp_path / 'src'
    src_dir.mkdir()
    
    # Create a test file in src_dir to validate
    test_py = src_dir / "test.py"
    test_py.write_text("def test(): pass")
    
    class MockArgs:
        def __init__(self):
            self.project_path = str(src_dir)
            self.output = 'import_analysis.json'
            self.export = 'json'
            self.auto_scan = True
            self.server = False
    
    with patch('src.__main__.parse_args', return_value=MockArgs()), \
         patch('src.__main__.run', return_value=0), \
         patch('asyncio.run', return_value=0):
        result = main()
        assert result == 0

@pytest.mark.asyncio
async def test_main_error_handling(monkeypatch):
    """Test main function error handling."""
    def mock_parse_args():
        raise Exception('Test error')
    
    with patch('src.__main__.parse_args', side_effect=mock_parse_args):
        result = main()
        assert result == 1

@pytest.mark.asyncio
async def test_main_with_html_output(monkeypatch, test_files, temp_dir):
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
            self.server = False
    
    with patch('src.__main__.parse_args', return_value=MockArgs()), \
         patch('src.__main__.run', return_value=0), \
         patch('asyncio.run', return_value=0):
        exit_code = main()
        assert exit_code == 0 