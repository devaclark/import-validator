"""Configuration management for import validator."""
from pathlib import Path
from typing import Dict, List, Optional, Set, Union
from pydantic import Field
from pydantic_settings import BaseSettings
import tomli
from dataclasses import dataclass, field
import os
import yaml
import toml
import logging
from .logging_config import setup_logging

# Set up logging using centralized configuration
logger = logging.getLogger('validator.config')

@dataclass
class ImportValidatorConfig:
    """Configuration for import validator."""
    base_dir: Path = field(default_factory=Path.cwd)
    src_dir: Optional[Union[str, Path]] = field(default=None)
    tests_dir: Optional[Union[str, Path]] = field(default=None)
    pyproject_file: Optional[Union[str, Path]] = field(default=None)
    requirements_file: Optional[Union[str, Path]] = field(default=None)
    complexity_threshold: float = field(default=10.0)
    max_edges_per_diagram: int = field(default=100)
    ignore_patterns: Set[str] = field(default_factory=lambda: {
        "__pycache__",
        "*.pyc",
        ".git",
        "venv",
        ".venv",
        "build",
        "dist",
        "*.egg-info"
    })
    valid_packages: Set[str] = field(default_factory=set)  # No default packages
    weight_factors: Dict[str, float] = field(default_factory=lambda: {
        'imports': 1.0,
        'relative': 1.5,
        'unused': 2.0,
        'circular': 4.0,
        'edges': 1.0,
        'invalid': 2.0
    })
    _requirements: Set[str] = field(default_factory=set)
    _pyproject_dependencies: Set[str] = field(default_factory=set)

    def __post_init__(self):
        """Convert paths to absolute paths after initialization."""
        # Convert base_dir to absolute path
        self.base_dir = Path(self.base_dir).absolute()

        # Set default source and test directories if not provided
        if self.src_dir is None:
            self.src_dir = self.base_dir / "src"
        else:
            self.src_dir = Path(self.src_dir)
            if not self.src_dir.is_absolute():
                self.src_dir = self.base_dir / self.src_dir

        if self.tests_dir is None:
            self.tests_dir = self.base_dir / "tests"
        else:
            self.tests_dir = Path(self.tests_dir)
            if not self.tests_dir.is_absolute():
                self.tests_dir = self.base_dir / self.tests_dir

        # Handle optional file paths
        if self.pyproject_file is not None:
            self.pyproject_file = Path(self.pyproject_file)
            if not self.pyproject_file.is_absolute():
                self.pyproject_file = self.base_dir / self.pyproject_file

        if self.requirements_file is not None:
            self.requirements_file = Path(self.requirements_file)
            if not self.requirements_file.is_absolute():
                self.requirements_file = self.base_dir / self.requirements_file

        # Initialize from files if they exist
        self._requirements = self.parse_requirements_file()
        self._pyproject_dependencies = self.parse_pyproject_toml()
        
        # Update valid packages with requirements and dependencies
        self.update_valid_packages()
        
        # Ensure all default weight factors are present
        default_weight_factors = {
            'imports': 1.0,
            'relative': 1.5,
            'unused': 2.0,
            'circular': 4.0,
            'edges': 1.0,
            'invalid': 2.0
        }
        # Preserve any custom weight factors while ensuring defaults exist
        self.weight_factors = {**default_weight_factors, **self.weight_factors}

    def clean_package_name(self, package_spec: str) -> str:
        """Clean package name by removing version specifiers and extras."""
        # Remove any trailing comments
        package_spec = package_spec.split('#')[0].strip()
        
        # Handle empty strings
        if not package_spec:
            return ''
            
        # Remove environment markers (e.g., "; python_version >= '3.8'")
        package_spec = package_spec.split(';')[0].strip()
            
        # Remove version specifiers and extras
        package_name = package_spec.split('[')[0]  # Remove extras
        package_name = package_name.split('>=')[0]  # Remove >= version
        package_name = package_name.split('<=')[0]  # Remove <= version
        package_name = package_name.split('==')[0]  # Remove == version
        package_name = package_name.split('!=')[0]  # Remove != version
        package_name = package_name.split('~=')[0]  # Remove ~= version
        package_name = package_name.split('>')[0]   # Remove > version
        package_name = package_name.split('<')[0]   # Remove < version
        package_name = package_name.split('^')[0]   # Remove ^ version (used by poetry)
        
        # Clean up any remaining whitespace and quotes
        package_name = package_name.strip().strip('"\'')
        
        # Preserve original case
        return package_name

    @property
    def requirements(self) -> Set[str]:
        """Get requirements."""
        return self._requirements

    @requirements.setter
    def requirements(self, value: Set[str]) -> None:
        """Set requirements."""
        self._requirements = value

    @property
    def pyproject_dependencies(self) -> Set[str]:
        """Get dependencies from pyproject.toml."""
        return self._pyproject_dependencies

    @pyproject_dependencies.setter
    def pyproject_dependencies(self, value: Set[str]) -> None:
        """Set pyproject dependencies."""
        self._pyproject_dependencies = value

    def parse_pyproject_toml(self) -> Set[str]:
        """Parse pyproject.toml file and extract package names."""
        if not self.pyproject_file or not self.pyproject_file.exists():
            return set()

        try:
            with open(self.pyproject_file, 'rb') as f:
                pyproject_data = tomli.load(f)
                packages = set()
                
                # Get main dependencies from poetry section
                poetry_deps = pyproject_data.get('tool', {}).get('poetry', {}).get('dependencies', {})
                if isinstance(poetry_deps, dict):
                    packages.update(poetry_deps.keys())
                    logger.debug(f"Found tool poetry dependencies: {poetry_deps.keys()}")
                elif isinstance(poetry_deps, list):
                    packages.update(poetry_deps)
                    logger.debug(f"Found tool poetry dependencies: {poetry_deps}")
                
                # Get dev dependencies from poetry dev group
                dev_deps = pyproject_data.get('tool', {}).get('poetry', {}).get('group', {}).get('dev', {}).get('dependencies', {})
                if isinstance(dev_deps, dict):
                    packages.update(dev_deps.keys())
                    logger.debug(f"Found dev dependencies: {dev_deps.keys()}")
                elif isinstance(dev_deps, list):
                    packages.update(dev_deps)
                    logger.debug(f"Found dev dependencies: {dev_deps}")
                
                # Clean package names but preserve case
                cleaned_packages = {
                    self.clean_package_name(dep)
                    for dep in packages 
                    if dep != 'python'  # Exclude python itself
                }
                
                logger.debug(f"Found dependencies in pyproject.toml: {cleaned_packages}")
                return cleaned_packages
                
        except Exception as e:
            logger.error(f"Error parsing pyproject.toml: {e}")
            return set()

    def parse_requirements_file(self) -> Set[str]:
        """Parse requirements.txt file and extract package names."""
        if not self.requirements_file or not self.requirements_file.exists():
            return set()

        try:
            content = self.requirements_file.read_text()
            packages = set()
            
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                package = self.clean_package_name(line)
                if package:
                    packages.add(package)
            
            return packages
        except Exception as e:
            logger.error(f"Error parsing requirements.txt: {e}")
            return set()

    def update_valid_packages(self) -> None:
        """Update valid packages from pyproject.toml and requirements.txt."""
        self.valid_packages.update(self.requirements)
        self.valid_packages.update(self.pyproject_dependencies)

    def get_weight_factor(self, factor_name: str) -> float:
        """Get weight factor by name."""
        return self.weight_factors.get(factor_name, 1.0)

    def __str__(self):
        """Return a string representation of the configuration."""
        return (
            f"ImportValidatorConfig(complexity_threshold={self.complexity_threshold}, "
            f"max_edges_per_diagram={self.max_edges_per_diagram}, "
            f"ignore_patterns={self.ignore_patterns}, "
            f"valid_packages={self.valid_packages}, "
            f"weight_factors={self.weight_factors}, "
            f"requirements_file={self.requirements_file}, "
            f"pyproject_file={self.pyproject_file})"
        )

    async def initialize(self) -> None:
        """Initialize the configuration by loading from file if specified."""
        if self.config_file and os.path.exists(self.config_file):
            await self._load_config()

    async def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            with open(self.config_file, 'r') as f:
                config_data = yaml.safe_load(f)
                if not config_data:
                    return

                if 'weight_factors' in config_data:
                    self.weight_factors.update(config_data['weight_factors'])
                if 'ignore_patterns' in config_data:
                    self.ignore_patterns.update(config_data['ignore_patterns'])
                if 'ignore_imports' in config_data:
                    self.ignore_imports.update(config_data['ignore_imports'])
                if 'ignore_unused' in config_data:
                    self.ignore_unused.update(config_data['ignore_unused'])
                if 'ignore_relative' in config_data:
                    self.ignore_relative.update(config_data['ignore_relative'])
                if 'ignore_circular' in config_data:
                    self.ignore_circular.update(config_data['ignore_circular'])
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            # Continue with default configuration 