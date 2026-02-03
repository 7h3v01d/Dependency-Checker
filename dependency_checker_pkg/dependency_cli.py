# version 1.7

import argparse
import os
import sys
import logging
import venv
import subprocess
from typing import List, Dict, Tuple
from dependency_core import (
    scan_dependencies_logic, install_dependencies_logic, list_installed_packages,
    upgrade_package, install_package, check_dependencies, get_python_info,
    generate_requirements_logic, dependency_tree_logic, load_package_map
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def create_venv_if_needed(path: str, python_exe: str) -> Tuple[bool, str]:
    """Create a virtual environment in the specified path if none exists."""
    venv_path = os.path.join(path, '.venv')
    if os.path.exists(venv_path):
        logger.info(f"Virtual environment already exists at {venv_path}")
        return True, os.path.join(venv_path, 'Scripts' if sys.platform == 'win32' else 'bin', 'python')
    
    try:
        logger.info(f"Creating virtual environment at {venv_path}")
        venv.create(venv_path, with_pip=True)
        new_python_exe = os.path.join(venv_path, 'Scripts' if sys.platform == 'win32' else 'bin', 'python')
        # Upgrade pip in the new virtual environment
        subprocess.run([new_python_exe, '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)
        return True, new_python_exe
    except Exception as e:
        logger.error(f"Failed to create virtual environment: {e}")
        return False, python_exe

def prompt_for_installation(missing_deps: Dict[str, str], package_name_map: Dict[str, str]) -> List[str]:
    """Prompt user to select which dependencies to install."""
    selected_packages = []
    print("\nMissing dependencies found:")
    for pkg, src in missing_deps.items():
        display_name = package_name_map.get(pkg.lower(), pkg)
        print(f"- {display_name} (from {src})")
    print("\nWould you like to install these dependencies? (all/individual/none)")
    choice = input("Enter choice [all/individual/none]: ").strip().lower()
    
    if choice == 'all':
        return list(missing_deps.keys())
    elif choice == 'individual':
        for pkg in missing_deps:
            display_name = package_name_map.get(pkg.lower(), pkg)
            response = input(f"Install {display_name}? [y/n]: ").strip().lower()
            if response == 'y':
                selected_packages.append(pkg)
        return selected_packages
    else:
        return []

def main():
    parser = argparse.ArgumentParser(
        description="Python Dependency Manager: Scans, installs, and manages dependencies for Python projects.\n"
                    "Usage: python dependency_cli.py [path] <command> [options]",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "path",
        type=str,
        nargs="?",
        default=".",
        help="Path to the project folder (default: current directory).\n"
             "Use quotes for paths with spaces, e.g., \"C:/My Project\"."
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Scan subdirectories recursively (for scan, install, generate-requirements)."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output for installation process (for install)."
    )
    parser.add_argument(
        "--python",
        type=str,
        default=sys.executable,
        help="Python interpreter to use (e.g., 'python3.8' or 'C:\\Python38\\python.exe').\n"
             "Default: current Python executable."
    )
    parser.add_argument(
        "--create-venv",
        action="store_true",
        help="Create a virtual environment if none exists in the project folder (for install, generate-requirements)."
    )
    parser.add_argument(
        "--package-map",
        type=str,
        help="Path to a JSON file with custom import-to-PyPI package mappings."
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    subparsers.add_parser("scan", help="Scan the specified folder for missing dependencies.")
    
    install_parser = subparsers.add_parser("install", help="Install missing dependencies found in the specified folder.")
    install_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for each dependency before installing."
    )

    list_parser = subparsers.add_parser("list", help="List installed packages in the current environment.")
    list_parser.add_argument("--outdated", action="store_true", help="Show only outdated packages.")

    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade a package to the latest version.")
    upgrade_parser.add_argument("package", help="Package to upgrade (e.g., 'requests' or 'bs4').")

    install_pkg_parser = subparsers.add_parser("install-pkg", help="Install a package, optionally with a specific version.")
    install_pkg_parser.add_argument("package", help="Package to install (e.g., 'requests' or 'bs4').")
    install_pkg_parser.add_argument("--version", help="Specific version to install (e.g., '2.28.1').")

    subparsers.add_parser("check", help="Check for broken dependencies in the current environment.")

    generate_parser = subparsers.add_parser("generate-requirements", help="Generate a requirements.txt file from imports.")
    generate_parser.add_argument(
        "--output-file",
        default="requirements.txt",
        help="Output file name for requirements.txt (default: requirements.txt)."
    )

    tree_parser = subparsers.add_parser("tree", help="Display dependency tree using pipdeptree.")
    tree_parser.add_argument(
        "--format",
        choices=["text", "json", "json-tree", "dot", "pdf", "png", "svg"],
        default="text",
        help="Output format for dependency tree (default: text). Graph formats require GraphViz."
    )
    tree_parser.add_argument(
        "--package",
        help="Show dependency tree for a specific package (e.g., 'requests')."
    )
    tree_parser.add_argument(
        "--reverse",
        action="store_true",
        help="Show reverse dependency tree (packages that depend on the specified package)."
    )

    args = parser.parse_args()

    # Load package mappings
    package_name_map = load_package_map(args.package_map)

    python_info = get_python_info(args.python)
    logger.info(f"Python Version: {python_info['version']}")
    logger.info(f"Environment: {python_info['environment']} ({python_info['prefix']})")
    print()

    # Handle virtual environment creation
    python_exe = args.python
    if args.command in ["install", "generate-requirements"] and args.create_venv:
        success, new_python_exe = create_venv_if_needed(args.path, args.python)
        if success:
            python_exe = new_python_exe
            logger.info(f"Using Python executable from virtual environment: {python_exe}")
        else:
            logger.error("Continuing with original Python executable due to virtual environment creation failure.")

    if args.command in ["scan", "install", "generate-requirements"] and not os.path.isdir(args.path):
        logger.error(f"'{args.path}' is not a valid directory.")
        sys.exit(1)

    if args.command == "scan":
        logger.info(f"Scanning dependencies in '{args.path}'...")
        missing_deps, messages = scan_dependencies_logic(args.path, python_exe, recursive=args.recursive, python_version=python_info['version'], package_name_map=package_name_map)
        for msg in messages:
            print(msg)
        if not missing_deps:
            logger.info("No missing dependencies found.")
            sys.exit(0)
        logger.warning("Missing dependencies found. Use 'install' command to install them.")
        sys.exit(1)

    elif args.command == "install":
        logger.info(f"Scanning dependencies in '{args.path}'...")
        missing_deps, messages = scan_dependencies_logic(args.path, python_exe, recursive=args.recursive, python_version=python_info['version'], package_name_map=package_name_map)
        for msg in messages:
            print(msg)
        if not missing_deps:
            logger.info("No missing dependencies found.")
            sys.exit(0)
        
        # Interactive mode
        if args.interactive:
            packages_to_install = prompt_for_installation(missing_deps, package_name_map)
            if not packages_to_install:
                logger.info("No packages selected for installation.")
                sys.exit(0)
            missing_deps = {pkg: missing_deps[pkg] for pkg in packages_to_install}
        
        logger.info("Installing missing dependencies...")
        successful, failed, messages = install_dependencies_logic(missing_deps, python_exe, package_name_map=package_name_map, verbose=args.verbose)
        for msg in messages:
            print(msg)
        sys.exit(1 if failed else 0)

    elif args.command == "list":
        packages, messages = list_installed_packages(python_exe, outdated=args.outdated)
        for msg in messages:
            print(msg)
        if packages:
            print("\nInstalled packages:")
            for pkg in packages:
                version_info = f"{pkg['name']}=={pkg['version']}"
                if args.outdated and 'latest_version' in pkg:
                    version_info += f" (latest: {pkg['latest_version']})"
                print(f"- {version_info}")
        sys.exit(0)

    elif args.command == "upgrade":
        success, messages = upgrade_package(python_exe, args.package, package_name_map=package_name_map)
        for msg in messages:
            print(msg)
        sys.exit(0 if success else 1)

    elif args.command == "install-pkg":
        success, messages = install_package(python_exe, args.package, args.version, package_name_map=package_name_map)
        for msg in messages:
            print(msg)
        sys.exit(0 if success else 1)

    elif args.command == "check":
        success, messages = check_dependencies(python_exe)
        for msg in messages:
            print(msg)
        sys.exit(0 if success else 1)

    elif args.command == "generate-requirements":
        logger.info(f"Generating requirements.txt in '{args.path}'...")
        success, messages = generate_requirements_logic(args.path, python_exe, output_file=args.output_file, recursive=args.recursive, python_version=python_info['version'], package_name_map=package_name_map)
        for msg in messages:
            print(msg)
        sys.exit(0 if success else 1)

    elif args.command == "tree":
        success, messages = dependency_tree_logic(python_exe, output_format=args.format, package=args.package, reverse=args.reverse)
        for msg in messages:
            print(msg)
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()