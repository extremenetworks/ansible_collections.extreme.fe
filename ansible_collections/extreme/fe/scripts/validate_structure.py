#!/usr/bin/env python3
"""
Validate the structure of the extreme.fe Ansible collection.

Ensures required directories and files exist as specified in the
collection quality standards
"""

import os
import sys
from pathlib import Path

# Required directories that must exist
REQUIRED_DIRECTORIES = [
    "plugins/modules",
    "plugins/httpapi",
    "plugins/module_utils",
    "roles",
    "docs",
    "tests",
    "meta",
]

# Required files that must exist
REQUIRED_FILES = [
    "galaxy.yml",
    "meta/runtime.yml",
    "README.md",
    "LICENSE",
]

# Optional but recommended directories
OPTIONAL_DIRECTORIES = [
    "plugins/inventory",
    "plugins/lookup",
    "plugins/filter",
    "tests/unit",
    "tests/integration",
]


def find_collection_root() -> Path:
    """Find the collection root directory."""
    # Try current directory first
    cwd = Path.cwd()
    
    # Check if we're in the collection root
    if (cwd / "galaxy.yml").exists():
        return cwd
    
    # Check if we're in the scripts directory
    if cwd.name == "scripts" and (cwd.parent / "galaxy.yml").exists():
        return cwd.parent
    
    # Check environment variable
    ansible_env = os.environ.get("ANSIBLE")
    if ansible_env:
        ansible_path = Path(ansible_env)
        if (ansible_path / "galaxy.yml").exists():
            return ansible_path
    
    # Default: assume we're in the collection root
    return cwd


def validate_directories(root: Path) -> list[str]:
    """Validate that all required directories exist."""
    errors = []
    
    for dir_path in REQUIRED_DIRECTORIES:
        full_path = root / dir_path
        if not full_path.is_dir():
            errors.append(f"Missing required directory: {dir_path}")
    
    return errors


def validate_files(root: Path) -> list[str]:
    """Validate that all required files exist."""
    errors = []
    
    for file_path in REQUIRED_FILES:
        full_path = root / file_path
        if not full_path.is_file():
            errors.append(f"Missing required file: {file_path}")
    
    return errors


def check_optional(root: Path) -> list[str]:
    """Check for optional but recommended directories."""
    warnings = []
    
    for dir_path in OPTIONAL_DIRECTORIES:
        full_path = root / dir_path
        if not full_path.is_dir():
            warnings.append(f"Optional directory not found: {dir_path}")
    
    return warnings


def validate_galaxy_yml(root: Path) -> list[str]:
    """Validate galaxy.yml has required fields."""
    errors = []
    galaxy_path = root / "galaxy.yml"
    
    if not galaxy_path.exists():
        return ["galaxy.yml not found"]
    
    try:
        import yaml
        with open(galaxy_path, 'r') as f:
            galaxy_data = yaml.safe_load(f)
        
        required_fields = [
            "namespace",
            "name", 
            "version",
            "authors",
            "description",
        ]
        
        for field in required_fields:
            if field not in galaxy_data or not galaxy_data[field]:
                errors.append(f"galaxy.yml missing required field: {field}")
        
        # Validate namespace and name are lowercase
        if "namespace" in galaxy_data:
            if galaxy_data["namespace"] != galaxy_data["namespace"].lower():
                errors.append("galaxy.yml: namespace must be lowercase")
        
        if "name" in galaxy_data:
            if galaxy_data["name"] != galaxy_data["name"].lower():
                errors.append("galaxy.yml: name must be lowercase")
        
        # Validate semantic version
        if "version" in galaxy_data:
            import re
            semver_pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$'
            if not re.match(semver_pattern, str(galaxy_data["version"])):
                errors.append(f"galaxy.yml: version '{galaxy_data['version']}' is not semantic versioning")
        
    except yaml.YAMLError as e:
        errors.append(f"galaxy.yml is not valid YAML: {e}")
    except ImportError:
        errors.append("PyYAML not installed, cannot validate galaxy.yml content")
    
    return errors


def validate_runtime_yml(root: Path) -> list[str]:
    """Validate meta/runtime.yml exists and is valid."""
    errors = []
    runtime_path = root / "meta" / "runtime.yml"
    
    if not runtime_path.exists():
        return ["meta/runtime.yml not found"]
    
    try:
        import yaml
        with open(runtime_path, 'r') as f:
            runtime_data = yaml.safe_load(f)
        
        if "requires_ansible" not in runtime_data:
            errors.append("meta/runtime.yml missing 'requires_ansible' field")
        
    except yaml.YAMLError as e:
        errors.append(f"meta/runtime.yml is not valid YAML: {e}")
    except ImportError:
        pass  # PyYAML validation is optional
    
    return errors


def main():
    """Main entry point."""
    print("=" * 60)
    print("Validating Extreme FE Ansible Collection Structure")
    print("=" * 60)
    
    root = find_collection_root()
    print(f"\nCollection root: {root}")
    
    all_errors = []
    all_warnings = []
    
    # Validate directories
    print("\n📁 Checking required directories...")
    dir_errors = validate_directories(root)
    all_errors.extend(dir_errors)
    for error in dir_errors:
        print(f"  ❌ {error}")
    if not dir_errors:
        print("  ✅ All required directories present")
    
    # Validate files
    print("\n📄 Checking required files...")
    file_errors = validate_files(root)
    all_errors.extend(file_errors)
    for error in file_errors:
        print(f"  ❌ {error}")
    if not file_errors:
        print("  ✅ All required files present")
    
    # Validate galaxy.yml
    print("\n🌌 Validating galaxy.yml...")
    galaxy_errors = validate_galaxy_yml(root)
    all_errors.extend(galaxy_errors)
    for error in galaxy_errors:
        print(f"  ❌ {error}")
    if not galaxy_errors:
        print("  ✅ galaxy.yml is valid")
    
    # Validate runtime.yml
    print("\n⚙️  Validating meta/runtime.yml...")
    runtime_errors = validate_runtime_yml(root)
    all_errors.extend(runtime_errors)
    for error in runtime_errors:
        print(f"  ❌ {error}")
    if not runtime_errors:
        print("  ✅ meta/runtime.yml is valid")
    
    # Check optional directories
    print("\n📋 Checking optional directories...")
    warnings = check_optional(root)
    all_warnings.extend(warnings)
    for warning in warnings:
        print(f"  ⚠️  {warning}")
    if not warnings:
        print("  ✅ All optional directories present")
    
    # Summary
    print("\n" + "=" * 60)
    if all_errors:
        print(f"❌ FAILED: {len(all_errors)} error(s) found")
        for error in all_errors:
            print(f"   - {error}")
        sys.exit(1)
    else:
        print("✅ PASSED: Collection structure is valid")
        if all_warnings:
            print(f"   ({len(all_warnings)} warning(s))")
        sys.exit(0)


if __name__ == "__main__":
    main()
