# Import Validator

A tool to validate and visualize Python import dependencies in your project.

## Features

- Detects invalid imports
- Identifies unused imports
- Finds circular dependencies
- Generates interactive visualizations
- Supports requirements.txt and pyproject.toml for dependency validation
- Multiple output formats (HTML, JSON, Markdown, CSV)

## Installation

### Local Development Installation

```bash
# Clone the repository
git clone https://github.com/your-username/import-validator.git
cd import-validator

# Install in editable mode
pip install -e .
```

### Usage

Basic usage:

```bash
import-validator /path/to/src /path/to/tests
```

With additional options:

```bash
# Specify output format
import-validator /path/to/src /path/to/tests --format html

# Use requirements file for validation
import-validator /path/to/src /path/to/tests --requirements requirements.txt

# Use pyproject.toml for validation
import-validator /path/to/src /path/to/tests --pyproject pyproject.toml

# Specify output file
import-validator /path/to/src /path/to/tests -o report.html
```

### Output Formats

- HTML: Interactive visualization with D3.js
- JSON: Detailed analysis in JSON format
- Markdown: Human-readable report
- CSV: Tabular data for further processing

### Configuration

You can configure the validator using command-line arguments:

```bash
# Set complexity threshold
import-validator /path/to/src /path/to/tests --complexity-threshold 5.0

# Limit edges in visualization
import-validator /path/to/src /path/to/tests --max-edges 200

# Disable visualization
import-validator /path/to/src /path/to/tests --no-viz

# Disable auto-server for HTML
import-validator /path/to/src /path/to/tests --no-serve
```

## License

MIT License
