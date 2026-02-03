import pytest
import os
import sys
import subprocess
import json
from unittest.mock import patch
from dependency_cli import create_venv_if_needed, prompt_for_installation
from dependency_core import load_package_map, load_standard_library_modules, PACKAGE_NAME_MAP

@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory for testing."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    return str(project_dir)

@pytest.fixture
def custom_package_map(tmp_path):
    """Create a temporary custom package map JSON file."""
    map_file = tmp_path / "package_map.json"
    custom_map = {"custom_module": "custom-package"}
    with open(map_file, 'w', encoding='utf-8') as f:
        json.dump(custom_map, f)
    return str(map_file)

def test_create_venv_if_needed_new_venv(temp_project_dir):
    """Test creating a new virtual environment."""
    success, python_exe = create_venv_if_needed(temp_project_dir, sys.executable)
    assert success is True
    assert os.path.exists(python_exe)
    assert os.path.exists(os.path.join(temp_project_dir, '.venv'))
    # Verify pip is upgraded
    result = subprocess.run([python_exe, '-m', 'pip', '--version'], capture_output=True, text=True)
    assert result.returncode == 0

def test_create_venv_if_needed_existing_venv(temp_project_dir):
    """Test handling an existing virtual environment."""
    # Create a virtual environment manually
    venv_path = os.path.join(temp_project_dir, '.venv')
    subprocess.run([sys.executable, '-m', 'venv', venv_path], check=True)
    success, python_exe = create_venv_if_needed(temp_project_dir, sys.executable)
    assert success is True
    assert python_exe == os.path.join(venv_path, 'Scripts' if sys.platform == 'win32' else 'bin', 'python')

@patch('builtins.input', side_effect=['all'])
def test_prompt_for_installation_all(mock_input):
    """Test interactive mode selecting all packages."""
    missing_deps = {'requests': 'requirements.txt', 'bs4': 'script.py'}
    selected = prompt_for_installation(missing_deps, PACKAGE_NAME_MAP)
    assert set(selected) == {'requests', 'bs4'}

@patch('builtins.input', side_effect=['individual', 'y', 'n'])
def test_prompt_for_installation_individual(mock_input):
    """Test interactive mode selecting individual packages."""
    missing_deps = {'requests': 'requirements.txt', 'bs4': 'script.py'}
    selected = prompt_for_installation(missing_deps, PACKAGE_NAME_MAP)
    assert selected == ['requests']

@patch('builtins.input', side_effect=['none'])
def test_prompt_for_installation_none(mock_input):
    """Test interactive mode selecting no packages."""
    missing_deps = {'requests': 'requirements.txt', 'bs4': 'script.py'}
    selected = prompt_for_installation(missing_deps, PACKAGE_NAME_MAP)
    assert selected == []

def test_load_package_map_default():
    """Test loading default package map when no file is provided."""
    package_map = load_package_map(None)
    assert package_map == PACKAGE_NAME_MAP
    assert "bs4" in package_map and package_map["bs4"] == "beautifulsoup4"

def test_load_package_map_custom(custom_package_map):
    """Test loading custom package map from JSON file."""
    package_map = load_package_map(custom_package_map)
    assert "custom_module" in package_map and package_map["custom_module"] == "custom-package"
    assert "bs4" in package_map and package_map["bs4"] == "beautifulsoup4"

def test_load_package_map_invalid_file():
    """Test loading an invalid package map file."""
    with patch('builtins.print') as mock_print:
        package_map = load_package_map("nonexistent.json")
        assert package_map == PACKAGE_NAME_MAP
        mock_print.assert_called_with("Warning: Failed to load package map from nonexistent.json: [Errno 2] No such file or directory: 'nonexistent.json'")

def test_load_standard_library_modules_python_3_8():
    """Test loading standard library modules for Python 3.8."""
    modules = load_standard_library_modules("3.8.0")
    assert "zoneinfo" in modules
    assert "tomllib" not in modules

def test_load_standard_library_modules_python_3_11():
    """Test loading standard library modules for Python 3.11."""
    modules = load_standard_library_modules("3.11.0")
    assert "tomllib" in modules
    assert "zoneinfo" in modules

def test_load_standard_library_modules_unknown_version():
    """Test loading standard library modules for an unknown Python version."""
    with patch('builtins.print') as mock_print:
        modules = load_standard_library_modules("3.7.0")
        assert "tomllib" in modules  # Python 3.12 fallback
        assert len(modules) == len(json.load(open("dependency_checker_pkg/data/stdlib_3_12.json")))