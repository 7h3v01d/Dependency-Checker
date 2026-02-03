# Version 1.7

import os
import subprocess
import re
import sys
import json
from typing import List, Dict, Tuple, Set, Optional
from importlib import resources

# --- Configuration Data ---
# Mappings for common import names to PyPI package names
PACKAGE_NAME_MAP = {
    "bs4": "beautifulsoup4",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "osgeo": "gdal",
    "magic": "python-magic",
    "lxml": "lxml",
    "pycrypto": "pycryptodome",
    "Crypto": "pycryptodome",
    "torch": "pytorch",
    "mpl": "matplotlib",
    "pd": "pandas",
    "np": "numpy",
    "tf": "tensorflow",
    "django": "Django",
    "flask": "Flask"
}

def load_standard_library_modules(python_version: str) -> Set[str]:
    """
    Load standard library modules for the given Python version from JSON files.
    Returns a set of module names in lowercase.
    """
    version_map = {
        "3.8": "stdlib_3_8.json",
        "3.9": "stdlib_3_9.json",
        "3.10": "stdlib_3_10.json",
        "3.11": "stdlib_3_11.json",
        "3.12": "stdlib_3_12.json"
    }
    # Default to Python 3.12 if version not found
    filename = version_map.get(python_version[:3], "stdlib_3_12.json")
    
    try:
        # Use importlib.resources to access files in the data directory
        with resources.open_text("dependency_checker_pkg.data", filename) as f:
            modules = json.load(f)
        if not isinstance(modules, list):
            raise ValueError(f"Standard library file {filename} must contain a JSON array.")
        return {m.lower() for m in modules}
    except Exception as e:
        print(f"Warning: Failed to load standard library modules from {filename}: {e}")
        # Fallback to Python 3.12 standard library
        with resources.open_text("dependency_checker_pkg.data", "stdlib_3_12.json") as f:
            modules = json.load(f)
        return {m.lower() for m in modules}

def load_package_map(file_path: Optional[str] = None) -> Dict[str, str]:
    """
    Load custom package mappings from a JSON file, merging with default PACKAGE_NAME_MAP.
    If file_path is None or invalid, return default PACKAGE_NAME_MAP.
    """
    package_map = PACKAGE_NAME_MAP.copy()
    if file_path and os.path.isfile(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                custom_map = json.load(f)
            if not isinstance(custom_map, dict):
                raise ValueError("Custom package map must be a JSON object.")
            package_map.update({k.lower(): v for k, v in custom_map.items()})
        except Exception as e:
            print(f"Warning: Failed to load package map from {file_path}: {e}")
    return package_map

# --- Core Functions ---

def _run_pip_command(python_exe: str, command_args: List[str]) -> Tuple[int, str, str]:
    """
    Helper to run a pip command using the specified Python executable and capture its output.
    Returns (returncode, stdout, stderr).
    """
    try:
        process = subprocess.run(
            [python_exe, '-m', 'pip'] + command_args,
            capture_output=True,
            text=True,
            check=False,
            encoding='utf-8', errors='ignore'
        )
        return process.returncode, process.stdout, process.stderr
    except FileNotFoundError:
        return 1, "", f"Error: Python executable '{python_exe}' not found. Ensure it is installed and in your PATH."
    except Exception as e:
        return 1, "", f"An unexpected error occurred while running pip: {e}"

def check_package_installed(python_exe: str, package_name: str, package_name_map: Optional[Dict[str, str]] = None) -> bool:
    """
    Checks if a package is installed using the specified Python executable.
    Uses common mappings for import names that differ from PyPI names.
    """
    if package_name_map is None:
        package_name_map = PACKAGE_NAME_MAP

    returncode, stdout, stderr = _run_pip_command(python_exe, ['show', package_name])
    if returncode == 0 and "Name:" in stdout:
        return True

    mapped_name = package_name_map.get(package_name.lower())
    if mapped_name:
        returncode, stdout, stderr = _run_pip_command(python_exe, ['show', mapped_name])
        if returncode == 0 and "Name:" in stdout:
            return True

    return False

def get_package_version(python_exe: str, package_name: str, package_name_map: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Gets the installed version of a package using the specified Python executable.
    Returns None if the package is not installed.
    """
    if package_name_map is None:
        package_name_map = PACKAGE_NAME_MAP

    pypi_name = package_name_map.get(package_name.lower(), package_name)
    returncode, stdout, stderr = _run_pip_command(python_exe, ['show', pypi_name])
    if returncode == 0 and "Version:" in stdout:
        for line in stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(": ")[1].strip()
    return None

def extract_imports_from_file(file_path: str) -> Set[str]:
    """
    Extracts top-level module names from import statements in a Python file.
    Handles 'import foo' and 'from foo import bar'.
    """
    imported_modules = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                match_import = re.match(r'^\s*import\s+([a-zA-Z0-9_]+)(\s+as\s+[a-zA-Z0-9_]+)?\s*$', line)
                if match_import:
                    module_name = match_import.group(1)
                    if module_name:
                        imported_modules.add(module_name)
                    continue
                match_from_import = re.match(r'^\s*from\s+([a-zA-Z0-9_]+)\s+import\b', line)
                if match_from_import:
                    module_name = match_from_import.group(1)
                    if module_name and not module_name.startswith('.'):
                        imported_modules.add(module_name)
    except Exception as e:
        print(f"  Warning: Could not parse {file_path} for imports: {e}")
    return imported_modules

def scan_dependencies_logic(folder_path: str, python_exe: str, recursive: bool = True, python_version: Optional[str] = None, package_name_map: Optional[Dict[str, str]] = None) -> Tuple[Dict[str, str], List[str]]:
    """
    Scans a folder for Python files and requirements.txt to identify dependencies.
    Returns (missing_dependencies_dict, scan_summary_messages).
    """
    if python_version is None:
        python_info = get_python_info(python_exe)
        python_version = python_info['version']
    standard_lib_modules = load_standard_library_modules(python_version)
    if package_name_map is None:
        package_name_map = PACKAGE_NAME_MAP

    missing_dependencies = {}
    scan_summary_messages = []
    found_dependencies_to_check = False

    scan_summary_messages.append(f"Scanning folder: {folder_path} with Python: {python_exe} (version {python_version})")

    walk_generator = os.walk(folder_path)
    if not recursive:
        try:
            root, dirs, files = next(walk_generator)
            walk_generator = [(root, dirs, files)]
        except StopIteration:
            scan_summary_messages.append("\nSelected folder is empty or contains no relevant files.")
            return missing_dependencies, scan_summary_messages

    for root, _, files in walk_generator:
        for file in files:
            if file == 'requirements.txt':
                found_dependencies_to_check = True
                req_file_path = os.path.join(root, file)
                scan_summary_messages.append(f"\n--- Checking '{file}' ({os.path.relpath(req_file_path, folder_path)}) ---")
                try:
                    with open(req_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                package_name = re.split(r'[<>=~]', line)[0].strip()
                                if package_name:
                                    scan_summary_messages.append(f"  Checking '{package_name}'...")
                                    if not check_package_installed(python_exe, package_name, package_name_map):
                                        display_name = package_name_map.get(package_name.lower(), package_name)
                                        missing_dependencies[package_name] = f'requirements.txt ({os.path.relpath(req_file_path, folder_path)})'
                                        scan_summary_messages.append(f"  ❌ Missing: {display_name}")
                                    else:
                                        display_name = package_name_map.get(package_name.lower(), package_name)
                                        scan_summary_messages.append(f"  ✅ Installed: {display_name}")
                except Exception as e:
                    scan_summary_messages.append(f"  Error reading {req_file_path}: {e}")

            elif file.endswith('.py'):
                py_file_path = os.path.join(root, file)
                if file == '__init__.py' and os.path.getsize(py_file_path) < 50:
                    continue

                found_dependencies_to_check = True
                scan_summary_messages.append(f"\n--- Checking '{file}' ({os.path.relpath(py_file_path, folder_path)}) for imports ---")
                imported_modules = extract_imports_from_file(py_file_path)

                for module in imported_modules:
                    module_lower = module.lower()
                    if module_lower in standard_lib_modules:
                        scan_summary_messages.append(f"  (Skipping built-in/standard: {module})")
                        continue

                    is_local_module = False
                    if os.path.exists(os.path.join(folder_path, module + '.py')) or \
                       os.path.exists(os.path.join(folder_path, module)) or \
                       os.path.exists(os.path.join(root, module + '.py')) or \
                       os.path.exists(os.path.join(root, module)):
                        is_local_module = True

                    if is_local_module:
                        scan_summary_messages.append(f"  (Skipping local module: {module})")
                        continue

                    display_module_name = package_name_map.get(module.lower(), module)
                    scan_summary_messages.append(f"  Checking '{display_module_name}' (from import)...")
                    if not check_package_installed(python_exe, module, package_name_map):
                        if module not in missing_dependencies:
                            missing_dependencies[module] = f'import in {os.path.relpath(py_file_path, folder_path)}'
                            scan_summary_messages.append(f"  ❌ Missing: {display_module_name}")
                    else:
                        scan_summary_messages.append(f"  ✅ Installed: {display_module_name}")

    if not found_dependencies_to_check and not missing_dependencies:
        scan_summary_messages.append("\nNo 'requirements.txt' files or Python files with significant imports found.")
    elif missing_dependencies:
        scan_summary_messages.append("\n--- Scan Complete ---")
        scan_summary_messages.append("\nSummary of Missing Dependencies:")
        for pkg, src in missing_dependencies.items():
            display_pkg_name = package_name_map.get(pkg.lower(), pkg)
            scan_summary_messages.append(f"- {display_pkg_name} (from {src})")
    else:
        scan_summary_messages.append("\n--- Scan Complete ---")
        scan_summary_messages.append("\nAll detected dependencies are installed! ✅")

    return missing_dependencies, scan_summary_messages

def generate_requirements_logic(folder_path: str, python_exe: str, output_file: str = "requirements.txt", recursive: bool = True, python_version: Optional[str] = None, package_name_map: Optional[Dict[str, str]] = None) -> Tuple[bool, List[str]]:
    """
    Generates a requirements.txt file based on imports in Python files.
    Returns (success, messages).
    """
    if python_version is None:
        python_info = get_python_info(python_exe)
        python_version = python_info['version']
    standard_lib_modules = load_standard_library_modules(python_version)
    if package_name_map is None:
        package_name_map = PACKAGE_NAME_MAP

    messages = []
    dependencies = set()

    messages.append(f"Generating requirements.txt from imports in '{folder_path}' with Python: {python_exe} (version {python_version})")

    walk_generator = os.walk(folder_path)
    if not recursive:
        try:
            root, dirs, files = next(walk_generator)
            walk_generator = [(root, dirs, files)]
        except StopIteration:
            messages.append("\nSelected folder is empty or contains no relevant files.")
            return False, messages

    for root, _, files in walk_generator:
        for file in files:
            if file.endswith('.py') and (file != '__init__.py' or os.path.getsize(os.path.join(root, file)) >= 50):
                py_file_path = os.path.join(root, file)
                messages.append(f"\n--- Scanning '{file}' ({os.path.relpath(py_file_path, folder_path)}) for imports ---")
                imported_modules = extract_imports_from_file(py_file_path)
                for module in imported_modules:
                    module_lower = module.lower()
                    if module_lower in standard_lib_modules:
                        messages.append(f"  (Skipping built-in/standard: {module})")
                        continue
                    is_local_module = False
                    if os.path.exists(os.path.join(folder_path, module + '.py')) or \
                       os.path.exists(os.path.join(folder_path, module)) or \
                       os.path.exists(os.path.join(root, module + '.py')) or \
                       os.path.exists(os.path.join(root, module)):
                        is_local_module = True
                    if is_local_module:
                        messages.append(f"  (Skipping local module: {module})")
                        continue
                    if check_package_installed(python_exe, module, package_name_map):
                        version = get_package_version(python_exe, module, package_name_map)
                        pypi_name = package_name_map.get(module.lower(), module)
                        dependencies.add(f"{pypi_name}=={version}" if version else pypi_name)
                        messages.append(f"  ✅ Found: {pypi_name} (version: {version or 'unknown'})")
                    else:
                        messages.append(f"  ❌ Not installed: {package_name_map.get(module.lower(), module)} (skipping from requirements)")

    if not dependencies:
        messages.append("\nNo external dependencies found to include in requirements.txt.")
        return False, messages

    try:
        output_path = os.path.join(folder_path, output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Generated by dependency manager\n")
            for dep in sorted(dependencies):
                f.write(f"{dep}\n")
        messages.append(f"\nSuccessfully generated '{output_file}' with {len(dependencies)} dependencies.")
        return True, messages
    except Exception as e:
        messages.append(f"\nError writing '{output_file}': {e}")
        return False, messages

def dependency_tree_logic(python_exe: str, output_format: str = "text", package: Optional[str] = None, reverse: bool = False) -> Tuple[bool, List[str]]:
    """
    Generates a dependency tree using pipdeptree.
    Returns (success, messages).
    """
    messages = []
    command_args = ['-m', 'pipdeptree']
    if output_format == "json":
        command_args.append('--json')
    elif output_format == "json-tree":
        command_args.append('--json-tree')
    elif output_format in ["dot", "pdf", "png", "svg"]:
        command_args.extend(['--graph-output', output_format])
    if package:
        command_args.extend(['--packages', package])
    if reverse:
        command_args.append('--reverse')

    returncode, stdout, stderr = _run_pip_command(python_exe, command_args)
    messages.append(f"Generating dependency tree with format '{output_format}'{' for package ' + package if package else ''}{' (reverse)' if reverse else ''}...")
    if returncode == 0:
        messages.append(stdout)
        messages.append(f"✅ Dependency tree generated successfully.")
        if output_format in ["dot", "pdf", "png", "svg"]:
            messages.append(f"Output saved as 'dependencies.{output_format}'")
        return True, messages
    else:
        messages.append(f"❌ Failed to generate dependency tree: {stderr}")
        messages.append("HINT: Ensure 'pipdeptree' is installed (pip install pipdeptree) and GraphViz is installed for graph outputs.")
        return False, messages

def install_dependencies_logic(missing_dependencies: Dict[str, str], python_exe: str, package_name_map: Optional[Dict[str, str]] = None, verbose: bool = False) -> Tuple[List[str], List[str], List[str]]:
    """
    Performs pip installations for missing dependencies, skipping standard library modules.
    Returns (successful_installs, failed_installs, installation_messages).
    """
    if package_name_map is None:
        package_name_map = PACKAGE_NAME_MAP

    python_info = get_python_info(python_exe)
    standard_lib_modules = load_standard_library_modules(python_info['version'])

    installation_messages = []
    successful_installs = []
    failed_installs = []

    if not missing_dependencies:
        installation_messages.append("No missing dependencies to install.")
        return successful_installs, failed_installs, installation_messages

    installation_messages.append("\n--- Starting Installation ---")

    packages_to_install_pypi_names = []
    original_missing_keys = []
    for pkg in missing_dependencies:
        if pkg.lower() in standard_lib_modules:
            installation_messages.append(f"  Skipping '{pkg}' (standard library module, no installation needed).")
            continue
        packages_to_install_pypi_names.append(package_name_map.get(pkg.lower(), pkg))
        original_missing_keys.append(pkg)

    for i, pypi_package_name in enumerate(packages_to_install_pypi_names):
        original_module_name = original_missing_keys[i]
        installation_messages.append(f"Installing '{pypi_package_name}'...")
        if verbose:
            print(f"DEBUG: Attempting to install: {pypi_package_name}")

        returncode, stdout, stderr = _run_pip_command(python_exe, ['install', pypi_package_name])

        if returncode == 0:
            installation_messages.append(f"  ✅ Successfully installed: {pypi_package_name}")
            successful_installs.append(pypi_package_name)
        else:
            error_output = stderr
            if "Microsoft Visual C++ 14.0 or greater is required" in error_output:
                error_output += "\n  (HINT: Install Microsoft C++ Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/)"
            elif "No matching distribution found for" in error_output:
                error_output += f"\n  (HINT: '{pypi_package_name}' may be a standard library module or unavailable on PyPI.)"
            elif "Permission denied" in error_output or "Access is denied" in error_output:
                error_output += "\n  (HINT: Run as administrator or check permissions.)"
            elif "Connection aborted" in error_output or "Failed to establish a new connection" in error_output:
                error_output += "\n  (HINT: Check your internet connection.)"

            installation_messages.append(f"  ❌ Failed to install {pypi_package_name}:\n{error_output}")
            failed_installs.append(pypi_package_name)

        if verbose:
            print(f"DEBUG: Installation of {pypi_package_name} finished with return code {returncode}")

    installation_messages.append("\n--- Installation Summary ---")
    if successful_installs:
        installation_messages.append(f"Successfully installed: {', '.join(successful_installs)}")
    if failed_installs:
        installation_messages.append(f"Failed to install: {', '.join(failed_installs)}")
    else:
        installation_messages.append("All missing dependencies installed successfully! ✅")

    return successful_installs, failed_installs, installation_messages

def list_installed_packages(python_exe: str, outdated: bool = False) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    List installed packages using pip list.
    If outdated=True, only show outdated packages.
    Returns (packages, messages).
    """
    command = ["list", "--format=json"]
    if outdated:
        command.append("--outdated")
    returncode, stdout, stderr = _run_pip_command(python_exe, command)
    packages = []
    messages = []
    if returncode == 0:
        try:
            packages = json.loads(stdout)
            messages.append(f"Found {len(packages)} {'outdated' if outdated else 'installed'} packages.")
        except json.JSONDecodeError:
            messages.append(f"Error parsing pip list output: {stdout}")
    else:
        messages.append(f"Error listing packages: {stderr}")
    return packages, messages

def upgrade_package(python_exe: str, package_name: str, package_name_map: Optional[Dict[str, str]] = None) -> Tuple[bool, List[str]]:
    """
    Upgrade a package to the latest version.
    Returns (success, messages).
    """
    if package_name_map is None:
        package_name_map = PACKAGE_NAME_MAP
    python_info = get_python_info(python_exe)
    standard_lib_modules = load_standard_library_modules(python_info['version'])
    pypi_name = package_name_map.get(package_name.lower(), package_name)
    if pypi_name.lower() in standard_lib_modules:
        return False, [f"Cannot upgrade '{pypi_name}' (standard library module)."]
    returncode, stdout, stderr = _run_pip_command(python_exe, ["install", "--upgrade", pypi_name])
    messages = [f"Upgrading '{pypi_name}'..."]
    if returncode == 0:
        messages.append(f"  ✅ Successfully upgraded: {pypi_name}")
    else:
        messages.append(f"  ❌ Failed to upgrade {pypi_name}: {stderr}")
    return returncode == 0, messages

def install_package(python_exe: str, package_name: str, version: Optional[str] = None, package_name_map: Optional[Dict[str, str]] = None) -> Tuple[bool, List[str]]:
    """
    Install a package, optionally with a specific version.
    Returns (success, messages).
    """
    if package_name_map is None:
        package_name_map = PACKAGE_NAME_MAP
    python_info = get_python_info(python_exe)
    standard_lib_modules = load_standard_library_modules(python_info['version'])
    pypi_name = package_name_map.get(package_name.lower(), package_name)
    if pypi_name.lower() in standard_lib_modules:
        return False, [f"Cannot install '{pypi_name}' (standard library module)."]
    package_spec = f"{pypi_name}=={version}" if version else pypi_name
    returncode, stdout, stderr = _run_pip_command(python_exe, ["install", package_spec])
    messages = [f"Installing '{package_spec}'..."]
    if returncode == 0:
        messages.append(f"  ✅ Successfully installed: {package_spec}")
    else:
        messages.append(f"  ❌ Failed to install {package_spec}: {stderr}")
    return returncode == 0, messages

def check_dependencies(python_exe: str) -> Tuple[bool, List[str]]:
    """
    Check for broken dependencies using pip check.
    Returns (success, messages).
    """
    returncode, stdout, stderr = _run_pip_command(python_exe, ["check"])
    messages = [f"Dependency check result: {stdout.strip() or 'No output'}"]
    if returncode != 0:
        messages.append(f"Error checking dependencies: {stderr}")
    return returncode == 0, messages

def get_python_info(python_exe: str) -> Dict[str, str]:
    """
    Get information about the specified Python environment.
    Returns a dictionary with version and environment details.
    """
    try:
        process = subprocess.run(
            [python_exe, '-c', 'import sys; print(sys.version.split()[0]); print(sys.prefix); print(sys.base_prefix)'],
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8', errors='ignore'
        )
        output = process.stdout.strip().split('\n')
        version = output[0]
        prefix = output[1]
        base_prefix = output[2]
        is_venv = prefix != base_prefix
        return {
            "version": version,
            "environment": "virtual" if is_venv else "global",
            "prefix": prefix
        }
    except Exception as e:
        return {
            "version": "3.12",  # Default to 3.12 for standard library fallback
            "environment": "unknown",
            "prefix": f"Error: {e}"
        }

if __name__ == "__main__":
    print("--- Testing dependency_core.py directly ---")
    test_folder = os.path.join(os.getcwd(), "test_project_for_core")
    python_exe = sys.executable

    print(f"Scanning current directory: {test_folder} with Python: {python_exe}")

    if not os.path.exists(test_folder):
        os.makedirs(test_folder)
    with open(os.path.join(test_folder, "script.py"), "w") as f:
        f.write("import requests\nfrom bs4 import BeautifulSoup\nimport numpy\nimport os\n")
    with open(os.path.join(test_folder, "requirements.txt"), "w") as f:
        f.write("pandas\nscipy\n")

    missing, scan_output = scan_dependencies_logic(test_folder, python_exe, recursive=True)
    for msg in scan_output:
        print(msg)

    if missing:
        print("\nAttempting to install missing dependencies...")
        success, failed, install_output = install_dependencies_logic(missing, python_exe, verbose=True)
        for msg in install_output:
            print(msg)

    print("\nGenerating requirements.txt...")
    success, gen_output = generate_requirements_logic(test_folder, python_exe)
    for msg in gen_output:
        print(msg)

    print("\nGenerating dependency tree...")
    success, tree_output = dependency_tree_logic(python_exe, output_format="text")
    for msg in tree_output:
        print(msg)