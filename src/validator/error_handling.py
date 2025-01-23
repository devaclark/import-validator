"""Error handling for import validator."""
from typing import List, Protocol, Dict, Any, runtime_checkable, Optional
from rich.console import Console
from .validator_types import ValidationError


@runtime_checkable
class ErrorHandler(Protocol):
    """Protocol for error handlers."""
    
    def handle_error(self, error: ValidationError) -> None:
        """Handle a validation error."""
        ...

    def get_errors(self) -> List[ValidationError]:
        """Get all accumulated errors."""
        ...


class ConsoleErrorHandler:
    """Error handler that outputs to the console using rich."""
    
    def __init__(self):
        self.console = Console(stderr=True)
        self.errors: List[ValidationError] = []

    def handle_error(self, error: ValidationError) -> None:
        """Handle a validation error by printing it to the console."""
        self.errors.append(error)
        
        # Format the error message
        location = f"{error.file}"
        if error.line_number is not None:
            location += f" (line {error.line_number})"
            
        message = f"[red]{error.error_type}[/red]: {error.message}"
        if error.context:
            message += f"\n  Context: {error.context}"
            
        self.console.print(f"{location}: {message}")

    def get_errors(self) -> List[ValidationError]:
        """Get all accumulated errors."""
        return self.errors.copy()


class FileErrorHandler:
    """Error handler that writes to a log file."""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.errors: List[ValidationError] = []

    def handle_error(self, error: ValidationError) -> None:
        """Handle a validation error by writing it to the log file."""
        self.errors.append(error)
        
        # Format the error message
        location = f"{error.file}"
        if error.line_number is not None:
            location += f" (line {error.line_number})"
            
        message = f"{error.error_type}: {error.message}"
        if error.context:
            message += f"\n  Context: {error.context}"
            
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"{location}: {message}\n")

    def get_errors(self) -> List[ValidationError]:
        """Get all accumulated errors."""
        return self.errors.copy()


class CompositeErrorHandler:
    """Error handler that delegates to multiple handlers."""
    
    def __init__(self, handlers: List[ErrorHandler]):
        self.handlers = handlers
        self.errors: List[ValidationError] = []

    def handle_error(self, error: ValidationError) -> None:
        """Handle a validation error by delegating to all handlers."""
        self.errors.append(error)
        for handler in self.handlers:
            handler.handle_error(error)

    def get_errors(self) -> List[ValidationError]:
        """Get all accumulated errors."""
        return self.errors.copy()


def format_error(error: ValidationError) -> str:
    """Format a validation error for display."""
    location = f"{error.file}"
    if error.line_number:
        location += f" (line {error.line_number})"
    if error.context:
        location += f" in {error.context}"
    return f"{location}: {error.message}"


def format_error_json(error: ValidationError) -> Dict[str, Any]:
    """Format a validation error as JSON."""
    location = f"{error.file}"
    if error.line_number:
        location += f" (line {error.line_number})"
    return {
        'location': location,
        'error_type': error.error_type,
        'message': error.message,
        'context': error.context
    } 