# Import Validator

A powerful static analysis tool that helps you maintain clean and efficient Python codebases by analyzing import dependencies. It detects issues like circular dependencies, unused imports, and invalid import statements while providing beautiful visualizations of your project's import structure.

## Key Features

🔍 **Import Analysis**

- Detects invalid and unused imports
- Identifies circular dependencies
- Calculates import complexity metrics
- Validates against project dependencies

📊 **Visualization**

- Interactive dependency graphs
- Customizable graph layouts
- Filterable by complexity and relationships
- Export-ready visualizations

📝 **Multiple Output Formats**

- HTML: Interactive visualization with detailed analysis
- JSON: Machine-readable format for CI/CD integration
- Markdown: Clean, readable reports
- CSV: Data-friendly format for further analysis

## Installation

```bash
pip install -e git+https://github.com/devaclark/import-validator.git#egg=import_validator
```

## Quick Start

Basic analysis with default settings:

```bash
import-validator path/to/src path/to/tests
```

## Usage Examples

### HTML Report with Interactive Visualization

```bash
import-validator src/ tests/ \
    --format html \
    --output report.html \
    --max-edges 1000 \
    --complexity-threshold 5.0
```

This generates an interactive HTML report with:

- Dependency visualization
- Import statistics
- Issue highlights
- Filterable graphs

### JSON Output for CI/CD Integration

```bash
import-validator src/ tests/ \
    --format json \
    --output analysis.json \
    --pyproject pyproject.toml
```

Perfect for:

- Automated analysis
- Custom tooling integration
- Data processing
- CI/CD pipelines

### Markdown Report for Documentation

```bash
import-validator src/ tests/ \
    --format markdown \
    --output analysis.md \
    --requirements requirements.txt
```

Generates a clean, readable report with:

- Summary statistics
- Issue listings
- Recommendations
- Import metrics

### CSV Export for Data Analysis

```bash
import-validator src/ tests/ \
    --format csv \
    --output imports.csv
```

Useful for:

- Spreadsheet analysis
- Data visualization
- Custom reporting
- Trend analysis

## Advanced Configuration

### Dependency Validation

```bash
# Using pyproject.toml
import-validator src/ tests/ --pyproject pyproject.toml

# Using requirements.txt
import-validator src/ tests/ --requirements requirements.txt
```

### Visualization Control

```bash
# Limit visualization complexity
import-validator src/ tests/ --max-edges 500

# Adjust complexity threshold
import-validator src/ tests/ --complexity-threshold 3.5

# Disable auto-server for HTML
import-validator src/ tests/ --no-serve

# Disable visualization generation
import-validator src/ tests/ --no-viz
```

### Error Handling

```bash
# Log errors to file
import-validator src/ tests/ --log-file errors.log
```

## Output Examples

### HTML Report

```json
{
    "stats": {
        "total_imports": 2981,
        "unique_imports": 459,
        "complexity_score": 6.65,
        "invalid_imports": 3,
        "unused_imports": 1611,
        "relative_imports": 531,
        "circular_refs": 0
    },
    "graph": {
        "nodes": 392,
        "edges": 752,
        "avg_edges_per_node": 1.92
    }
}
```

## Contributing

Contributions are welcome! Feel free to:

- Report issues
- Suggest features
- Submit pull requests

## License

MIT License - See [LICENSE](LICENSE) for details
