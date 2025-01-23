"""Tests for error handling functionality."""
import pytest
from pathlib import Path
from src.validator.error_handling import ConsoleErrorHandler, FileErrorHandler, CompositeErrorHandler, ErrorHandler, format_error, format_error_json
from src.validator.validator_types import ValidationError
from typing import List


@pytest.fixture
def sample_error():
    """Create a sample validation error."""
    return ValidationError(
        file=Path('test.py'),
        error_type='import_error',
        message='Invalid import',
        line_number=42,
        context='import invalid_module'
    )


def test_console_error_handler(sample_error, capsys):
    """Test console error handler."""
    handler = ConsoleErrorHandler()
    handler.handle_error(sample_error)
    
    # Check that error was stored
    errors = handler.get_errors()
    assert len(errors) == 1
    assert errors[0] == sample_error
    
    # Check console output
    captured = capsys.readouterr()
    assert 'test.py (line 42)' in captured.err
    assert 'import_error' in captured.err


def test_file_error_handler(sample_error, temp_dir):
    """Test file error handler."""
    log_file = temp_dir / "errors.log"
    handler = FileErrorHandler(str(log_file))
    handler.handle_error(sample_error)
    
    # Check that error was stored
    errors = handler.get_errors()
    assert len(errors) == 1
    assert errors[0] == sample_error
    
    # Check log file content
    content = log_file.read_text()
    assert 'test.py (line 42)' in content
    assert 'import_error' in content


def test_composite_error_handler(sample_error, temp_dir, capsys):
    """Test composite error handler."""
    # Create individual handlers
    console_handler = ConsoleErrorHandler()
    log_file = temp_dir / "errors.log"
    file_handler = FileErrorHandler(str(log_file))
    
    # Create composite handler
    composite = CompositeErrorHandler([console_handler, file_handler])
    composite.handle_error(sample_error)
    
    # Check that error was stored in composite handler
    errors = composite.get_errors()
    assert len(errors) == 1
    assert errors[0] == sample_error
    
    # Check that error was stored in individual handlers
    assert len(console_handler.get_errors()) == 1
    assert len(file_handler.get_errors()) == 1
    
    # Check console output
    captured = capsys.readouterr()
    assert 'test.py (line 42)' in captured.err
    assert 'import_error' in captured.err
    
    # Check log file content
    content = log_file.read_text()
    assert 'test.py (line 42)' in content
    assert 'import_error' in content


def test_error_handler_without_line_number(temp_dir):
    """Test error handler with error that has no line number."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='import_error',
        message='Invalid import'
    )
    
    # Test with console handler
    console_handler = ConsoleErrorHandler()
    console_handler.handle_error(error)
    errors = console_handler.get_errors()
    assert len(errors) == 1
    assert errors[0].line_number is None
    
    # Test with file handler
    log_file = temp_dir / "errors.log"
    file_handler = FileErrorHandler(str(log_file))
    file_handler.handle_error(error)
    content = log_file.read_text()
    assert 'test.py: import_error' in content


def test_error_handler_without_context(temp_dir):
    """Test error handler with error that has no context."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='import_error',
        message='Invalid import',
        line_number=42
    )
    
    # Test with console handler
    console_handler = ConsoleErrorHandler()
    console_handler.handle_error(error)
    errors = console_handler.get_errors()
    assert len(errors) == 1
    assert errors[0].context is None
    
    # Test with file handler
    log_file = temp_dir / "errors.log"
    file_handler = FileErrorHandler(str(log_file))
    file_handler.handle_error(error)
    content = log_file.read_text()
    assert 'Context' not in content


def test_error_handlers_multiple_errors(sample_error, temp_dir):
    """Test handling multiple errors."""
    error2 = ValidationError(
        file=Path('other.py'),
        error_type='circular_import_error',
        message='Circular dependency detected',
        line_number=10
    )
    
    # Test with console handler
    console_handler = ConsoleErrorHandler()
    console_handler.handle_error(sample_error)
    console_handler.handle_error(error2)
    errors = console_handler.get_errors()
    assert len(errors) == 2
    
    # Test with file handler
    log_file = temp_dir / "errors.log"
    file_handler = FileErrorHandler(str(log_file))
    file_handler.handle_error(sample_error)
    file_handler.handle_error(error2)
    errors = file_handler.get_errors()
    assert len(errors) == 2
    
    # Test with composite handler
    composite = CompositeErrorHandler([console_handler, file_handler])
    composite.handle_error(sample_error)
    composite.handle_error(error2)
    errors = composite.get_errors()
    assert len(errors) == 2


class ConcreteErrorHandler(ErrorHandler):
    """Concrete implementation of ErrorHandler protocol."""
    
    def __init__(self):
        self.errors: List[ValidationError] = []
    
    def handle_error(self, error: ValidationError) -> None:
        """Handle a validation error."""
        self.errors.append(error)
    
    def get_errors(self) -> List[ValidationError]:
        """Get all accumulated errors."""
        return self.errors.copy()


def test_error_handler_protocol():
    """Test error handler protocol."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='import_error',
        message='Invalid import',
        line_number=42,
        context='import statement'
    )
    
    handler = ConsoleErrorHandler()
    handler.handle_error(error)
    
    errors = handler.get_errors()
    assert len(errors) == 1
    assert errors[0].file_path == 'test.py'
    assert errors[0].error_type == 'import_error'
    assert errors[0].message == 'Invalid import'
    assert errors[0].line_number == 42
    assert errors[0].context == 'import statement'


def test_error_handler_without_line_number():
    """Test error handler without line number."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='import_error',
        message='Invalid import'
    )
    
    handler = ConsoleErrorHandler()
    handler.handle_error(error)
    
    errors = handler.get_errors()
    assert len(errors) == 1
    assert errors[0].file_path == 'test.py'
    assert errors[0].line_number is None


def test_error_handler_without_context():
    """Test error handler without context."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='import_error',
        message='Invalid import',
        line_number=42
    )
    
    handler = ConsoleErrorHandler()
    handler.handle_error(error)
    
    errors = handler.get_errors()
    assert len(errors) == 1
    assert errors[0].file_path == 'test.py'
    assert errors[0].context is None


def test_error_handlers_multiple_errors(sample_error, temp_dir):
    """Test handling multiple errors."""
    error2 = ValidationError(
        file=Path('other.py'),
        error_type='circular_import_error',
        message='Circular dependency detected',
        line_number=10
    )
    
    # Test with console handler
    console_handler = ConsoleErrorHandler()
    console_handler.handle_error(sample_error)
    console_handler.handle_error(error2)
    errors = console_handler.get_errors()
    assert len(errors) == 2
    
    # Test with file handler
    log_file = temp_dir / "errors.log"
    file_handler = FileErrorHandler(str(log_file))
    file_handler.handle_error(sample_error)
    file_handler.handle_error(error2)
    errors = file_handler.get_errors()
    assert len(errors) == 2
    
    # Test with composite handler
    composite = CompositeErrorHandler([console_handler, file_handler])
    composite.handle_error(sample_error)
    composite.handle_error(error2)
    errors = composite.get_errors()
    assert len(errors) == 2


def test_error_handler_protocol_implementation():
    """Test that error handlers implement the ErrorHandler protocol."""
    handlers = [
        ConsoleErrorHandler(),
        FileErrorHandler("test.log"),
        CompositeErrorHandler([])
    ]
    for handler in handlers:
        assert isinstance(handler, ErrorHandler)
        # Test protocol methods exist
        assert hasattr(handler, 'handle_error')
        assert hasattr(handler, 'get_errors')


def test_format_error_with_all_fields():
    """Test format_error with all fields present."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='TestError',
        message='Test message',
        line_number=42,
        context='test_function'
    )
    formatted = format_error(error)
    assert 'test.py' in formatted
    assert 'line 42' in formatted
    assert 'in test_function' in formatted
    assert 'Test message' in formatted


def test_format_error_json_with_all_fields():
    """Test format_error_json with all fields present."""
    error = ValidationError(
        file=Path('test.py'),
        error_type='TestError',
        message='Test message',
        line_number=42,
        context='test_function'
    )
    json_error = format_error_json(error)
    assert json_error['location'] == 'test.py (line 42)'
    assert json_error['error_type'] == 'TestError'
    assert json_error['message'] == 'Test message'


def test_composite_error_handler_with_multiple_handlers(tmp_path):
    """Test composite error handler with multiple handlers."""
    log_file = tmp_path / "test.log"
    console_handler = ConsoleErrorHandler()
    file_handler = FileErrorHandler(str(log_file))
    composite = CompositeErrorHandler([console_handler, file_handler])
    
    error = ValidationError(
        file=Path('test.py'),
        error_type='TestError',
        message='Test message'
    )
    composite.handle_error(error)
    
    # Check that both handlers received the error
    assert len(console_handler.get_errors()) == 1
    assert len(file_handler.get_errors()) == 1
    assert log_file.exists()


def test_file_error_handler_with_unicode_content(tmp_path):
    """Test file error handler with unicode content."""
    log_file = tmp_path / "test.log"
    handler = FileErrorHandler(str(log_file))
    
    error = ValidationError(
        file=Path('test.py'),
        error_type='TestError',
        message='Test message with unicode: 🐍',
        context='test_function'
    )
    handler.handle_error(error)
    
    assert log_file.exists()
    content = log_file.read_text(encoding='utf-8')
    assert '🐍' in content 