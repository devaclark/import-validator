# Import Validator

A powerful Python dependency analysis tool with an interactive GUI that helps developers understand, optimize, and maintain their project's import structure. Perfect for both small scripts and large-scale Python applications.

## Why Use Import Validator?

- **Untangle Complex Dependencies**: Visualize and understand how your Python modules interact
- **Optimize Import Structure**: Identify and fix circular dependencies, unused imports, and import conflicts
- **Improve Code Quality**: Get real-time feedback on import patterns and potential issues
- **Accelerate Development**: Navigate and understand large codebases more efficiently
- **Maintain Clean Architecture**: Ensure your project follows clean dependency principles

## Real-World Applications

### 1. Legacy Code Modernization

- Map out existing dependencies in legacy systems
- Identify areas for modularization
- Plan refactoring strategies with minimal impact
- Track improvements in dependency structure

Example workflow:

```bash
# Analyze legacy project
python -m src --project-path ./legacy_project --auto-scan

# Export baseline metrics
# Use GUI: Analysis Panel > Export > JSON
# Review in visualization panel
# Identify circular dependencies and unused imports
# Plan refactoring strategy
```

### 2. Microservices Development

- Ensure clean boundaries between services
- Validate import isolation
- Identify shared dependencies
- Maintain service independence

Example workflow:

```bash
# Analyze each microservice
python -m src --project-path ./service1 --auto-scan
# Review dependencies in GUI
# Export service boundaries
# Identify shared components
```

### 3. Code Quality Management

- Monitor dependency health over time
- Enforce architectural boundaries
- Prevent dependency creep
- Maintain codebase maintainability

Example workflow:

```bash
# Regular analysis
python -m src --project-path /path/to/your/project --auto-scan
# Review metrics in Analysis Panel
# Export reports for tracking
# Address any new issues
```

## Key Features

🚀 **Modern Interactive Interface**

- Beautiful dark-themed Qt GUI for comfortable long-term use
- Real-time dependency visualization with D3.js
- Split view with code editor and analysis panels
- Project-wide dependency graphing
- Syntax-highlighted code viewing and editing

🔍 **Smart Analysis Engine**

- Real-time import validation against project dependencies
- Detection of circular dependencies and import cycles
- Identification of unused and invalid imports
- Tracking of relative vs absolute imports
- Continuous analysis as you code

📊 **Developer Tools**

- Intelligent code completion
- Import statement validation
- Error detection and highlighting
- Quick file navigation
- Export analysis results for documentation

🔧 **Project Integration**

- Automatic project structure detection
- Support for requirements.txt and pyproject.toml
- Customizable ignore patterns
- Configurable analysis thresholds

## Installation

```bash
# Using pip (recommended for most users)
pip install import-validator

# Using poetry (for poetry-managed projects)
poetry add import-validator

# Development installation
git clone https://github.com/devaclark/import-validator.git
cd import-validator
poetry install
```

## Quick Start Guide

### GUI Mode

The GUI provides the most intuitive way to analyze your project:

```bash
# Launch and select project through GUI
python -m src

# Launch with specific project (auto-starts analysis)
python -m src --project-path /path/to/your/project --auto-scan
```

## GUI Interface Guide

The interface is divided into three main sections:

1. **Dependency Graph** (Left Panel)
   - Interactive visualization of project structure
   - Click nodes to explore modules
   - Zoom and pan for different views
   - Color coding for different dependency types
   - Filter and search capabilities

   Keyboard shortcuts:
   - `Ctrl + F`: Search modules
   - `+/-`: Zoom in/out
   - `Space`: Reset view
   - `Ctrl + Click`: Multi-select nodes

2. **Code Editor** (Right Top Panel)
   - Syntax highlighting
   - Real-time code analysis
   - Import validation
   - Quick navigation
   - Auto-completion support

   Keyboard shortcuts:
   - `Ctrl + S`: Save changes
   - `Ctrl + F`: Find in file
   - `Ctrl + /`: Toggle comment
   - `Ctrl + Space`: Trigger completion
   - `F12`: Go to definition

3. **Analysis Panel** (Right Bottom Panel)
   - Detailed metrics
   - Import analysis
   - Error reporting
   - Quick actions
   - Export options

   Features:
   - Real-time metrics updates
   - One-click issue fixing
   - Export in multiple formats
   - Custom metric thresholds
   - Filtering options

## Configuration

Configure through `pyproject.toml` or GUI settings:

```toml
# pyproject.toml
[tool.import-validator]
# Analysis settings
complexity_threshold = 10.0
max_edges = 100
allow_relative_imports = false

# Files to ignore
ignore_patterns = [
    "__pycache__",
    "*.pyc",
    ".git",
    "venv",
    ".venv"
]

# Advanced settings
max_depth = 5              # Maximum dependency depth to analyze
cache_results = true       # Enable result caching
parallel_analysis = true   # Enable parallel analysis

# Visualization settings
default_layout = "force"   # force, circular, or hierarchical
node_size = "auto"        # auto or fixed
edge_bundling = true      # Enable edge bundling for cleaner graphs
```

## Workflow Integration

### 1. Git Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/sh
python -m src --project-path . --auto-scan --check-only
```

### 2. CI Pipeline (GitHub Actions)

```yaml
name: Dependency Check
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install import-validator
      - run: python -m src --project-path . --auto-scan --check-only
```

### 3. VS Code Integration

Install the Import Validator extension for real-time analysis in VS Code.

## Troubleshooting Guide

### Common Issues

1. **Installation Problems**

   ```bash
   # If Qt installation fails
   pip install PyQt6 --no-cache-dir
   
   # If dependencies conflict
   pip install import-validator --no-deps
   pip install -r requirements.txt
   ```

2. **Performance Issues**
   - Reduce project scope using ignore patterns
   - Increase complexity threshold
   - Enable result caching
   - Use parallel analysis option

3. **Visualization Problems**
   - Clear browser cache if using server mode
   - Reduce max_edges if graph is too dense
   - Use filtering to focus on specific modules

### Error Messages

1. **"No Python files found"**
   - Check project path
   - Verify file extensions
   - Check ignore patterns

2. **"Unable to parse imports"**
   - Verify Python syntax
   - Check file encoding
   - Update Python version

3. **"Graph too complex"**
   - Increase max_edges setting
   - Use module filtering
   - Focus on specific directories

## Best Practices

1. **Project Analysis**
   - Start with a clean project directory
   - Ensure all dependencies are installed
   - Use auto-scan for initial analysis
   - Review and adjust ignore patterns

2. **Performance Tips**
   - Exclude test directories for faster analysis
   - Use ignore patterns for generated code
   - Configure complexity thresholds appropriately
   - Enable caching for large projects

3. **Integration Tips**
   - Run regular dependency checks
   - Export results for documentation
   - Use server mode for team access
   - Integrate with CI/CD pipelines

## System Requirements

- **Python**: 3.12.8 or higher
- **Qt**: 6.8.0 or higher
- **OS**: Windows/Linux/MacOS
- **Hardware**
  - Minimum: 4GB RAM, dual-core processor
  - Recommended: 8GB RAM, quad-core processor
- **Display**: 1920x1080 recommended for optimal GUI experience

## License

MIT License - See [LICENSE](LICENSE) for details
