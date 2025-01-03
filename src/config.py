"""Configuration management for import validator."""
from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import Field
from pydantic_settings import BaseSettings
import tomli


def parse_requirements_file(file_path: Path) -> Set[str]:
    """Parse a requirements.txt file to get package names."""
    packages = set()
    if not file_path.exists():
        return packages
        
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Extract package name, ignoring version specifiers
                package = line.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip()
                if package:
                    packages.add(package)
    return packages

def parse_pyproject_toml(file_path: Path) -> Set[str]:
    """Parse a pyproject.toml file to get package names."""
    packages = set()
    if not file_path.exists():
        return packages
        
    with open(file_path, 'rb') as f:
        try:
            data = tomli.load(f)
            # Look for dependencies in different possible locations
            deps = data.get('project', {}).get('dependencies', [])
            deps.extend(data.get('tool', {}).get('poetry', {}).get('dependencies', {}).keys())
            deps.extend(data.get('build-system', {}).get('requires', []))
            
            for dep in deps:
                # Extract package name, ignoring version specifiers
                package = dep.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('~=')[0].strip()
                if package:
                    packages.add(package)
        except Exception:
            pass
    return packages


class ImportValidatorConfig(BaseSettings):
    """Configuration settings for the import validator."""
    
    # Thresholds and limits
    complexity_threshold: float = Field(
        default=10.0,
        description="Threshold for flagging high complexity imports"
    )
    max_edges_per_diagram: int = Field(
        default=100,
        description="Maximum number of edges to show in visualization diagrams"
    )
    
    # File patterns
    ignore_patterns: List[str] = Field(
        default=["__pycache__", "*.pyc", "*.pyo", "*.pyd", ".git", ".venv", "venv"],
        description="Patterns to ignore during file scanning"
    )
    
    # Dependencies
    requirements_file: Optional[Path] = Field(
        default=None,
        description="Path to requirements.txt file"
    )
    pyproject_file: Optional[Path] = Field(
        default=None,
        description="Path to pyproject.toml file"
    )
    valid_packages: Set[str] = Field(
        default={'pytest', 'unittest', 'nose', 'hypothesis'},
        description="Set of valid package names"
    )
    
    # Complexity weight factors
    weight_factors: Dict[str, float] = Field(
        default={
            "imports": 1.0,      # Base weight for number of imports
            "relative": 1.5,     # Weight for relative imports
            "unused": 2.0,       # Weight for unused imports
            "circular": 3.0      # Weight for circular dependencies
        },
        description="Weight factors for calculating complexity scores"
    )
    
    # Visualization settings
    visualization: Dict[str, str] = Field(
        default={
            "node_color": "lightblue",
            "edge_color": "gray",
            "font_size": "8",
            "node_size": "500"
        },
        description="Default visualization settings"
    )
    
    def load_dependencies(self) -> None:
        """Load dependencies from requirements.txt and/or pyproject.toml."""
        if self.requirements_file:
            self.valid_packages.update(parse_requirements_file(self.requirements_file))
        if self.pyproject_file:
            self.valid_packages.update(parse_pyproject_toml(self.pyproject_file))
    
    def merge_with(self, other: 'ImportValidatorConfig') -> 'ImportValidatorConfig':
        """Merge this config with another, preferring values from the other."""
        return ImportValidatorConfig(**{
            **self.model_dump(),
            **other.model_dump(exclude_unset=True)
        })
    
    class Config:
        """Pydantic configuration."""
        env_prefix = "IMPORT_VALIDATOR_"
        case_sensitive = False 