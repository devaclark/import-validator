"""Main entry point for the validator package."""
import sys
from .validator import run_server

def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        run_server()
    else:
        print("Usage: python -m validator --server")
        sys.exit(1)

if __name__ == "__main__":
    main() 