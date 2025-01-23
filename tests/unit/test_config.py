"""Tests for configuration management."""
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
from src.validator.config import ImportValidatorConfig
from src.validator.validator_types import ImportStats


def test_clean_package_name():
    """Test package name cleaning function."""
    config = ImportValidatorConfig()
    assert config.clean_package_name('package1>=1.0.0') == 'package1'
    assert config.clean_package_name('package2<=2.0.0') == 'package2'
    assert config.clean_package_name('package3==3.0.0') == 'package3'
    assert config.clean_package_name('package4>4.0.0') == 'package4'
    assert config.clean_package_name('package5<5.0.0') == 'package5'
    assert config.clean_package_name('package6~=6.0.0') == 'package6'
    assert config.clean_package_name('package7 ; python_version >= "3.8"') == 'package7'
    assert config.clean_package_name('package8  # comment') == 'package8'
    assert config.clean_package_name('"quoted-package"') == 'quoted-package'


def test_parse_requirements_file(mock_requirements):
    """Test parsing requirements.txt file."""
    config = ImportValidatorConfig(requirements_file=mock_requirements)
    packages = config.parse_requirements_file()
    assert packages == {'pytest', 'networkx', 'rich', 'pydantic-settings'}


def test_parse_requirements_file_nonexistent():
    """Test parsing non-existent requirements file."""
    config = ImportValidatorConfig(requirements_file=Path('nonexistent.txt'))
    packages = config.parse_requirements_file()
    assert packages == set()


def test_parse_requirements_file_error():
    """Test error handling when reading requirements.txt fails."""
    with patch('pathlib.Path.read_text', side_effect=Exception('Read error')):
        config = ImportValidatorConfig(requirements_file=Path('requirements.txt'))
        packages = config.parse_requirements_file()
        assert packages == set()


def test_parse_pyproject_toml(mock_pyproject):
    """Test parsing pyproject.toml file."""
    config = ImportValidatorConfig(pyproject_file=mock_pyproject)
    packages = config.parse_pyproject_toml()
    assert packages == {'networkx', 'rich', 'pydantic'} 