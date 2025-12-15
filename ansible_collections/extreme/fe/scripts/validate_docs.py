#!/usr/bin/env python3
"""
Validate module documentation for the extreme.fe Ansible collection.

Ensures every module has proper documentation blocks matching standards:
- DOCUMENTATION block
- EXAMPLES block  
- RETURN block (if applicable)
- Fully populated argument_spec
"""

import ast
import os
import re
import sys
from pathlib import Path
from typing import Optional


class ModuleDocValidator:
    """Validates Ansible module documentation."""
    
    REQUIRED_DOC_BLOCKS = ["DOCUMENTATION", "EXAMPLES"]
    OPTIONAL_DOC_BLOCKS = ["RETURN"]
    
    # Required fields in DOCUMENTATION
    REQUIRED_DOC_FIELDS = [
        "module",
        "short_description",
        "description",
        "author",
        "options",
    ]
    
    def __init__(self, module_path: Path):
        self.module_path = module_path
        self.content = ""
        self.errors: list[str] = []
        self.warnings: list[str] = []
        
    def load_module(self) -> bool:
        """Load the module content."""
        try:
            with open(self.module_path, 'r', encoding='utf-8') as f:
                self.content = f.read()
            return True
        except Exception as e:
            self.errors.append(f"Cannot read file: {e}")
            return False
    
    def validate_doc_blocks(self) -> None:
        """Validate that required documentation blocks exist."""
        for block_name in self.REQUIRED_DOC_BLOCKS:
            pattern = rf'^{block_name}\s*=\s*[\'\"r]'
            if not re.search(pattern, self.content, re.MULTILINE):
                self.errors.append(f"Missing required {block_name} block")
        
        for block_name in self.OPTIONAL_DOC_BLOCKS:
            pattern = rf'^{block_name}\s*=\s*[\'\"r]'
            if not re.search(pattern, self.content, re.MULTILINE):
                self.warnings.append(f"Missing optional {block_name} block")
    
    def extract_doc_block(self, block_name: str) -> Optional[str]:
        """Extract a documentation block content."""
        # Match patterns like: DOCUMENTATION = r"""...""" or DOCUMENTATION = """..."""
        patterns = [
            rf'{block_name}\s*=\s*r?"""(.*?)"""',
            rf"{block_name}\s*=\s*r?'''(.*?)'''",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.content, re.DOTALL)
            if match:
                return match.group(1)
        
        return None
    
    def validate_documentation_content(self) -> None:
        """Validate the content of the DOCUMENTATION block."""
        doc_content = self.extract_doc_block("DOCUMENTATION")
        
        if not doc_content:
            return  # Already reported as missing
        
        try:
            import yaml
            doc_data = yaml.safe_load(doc_content)
            
            if not isinstance(doc_data, dict):
                self.errors.append("DOCUMENTATION block is not a valid YAML dict")
                return
            
            # Check required fields
            for field in self.REQUIRED_DOC_FIELDS:
                if field not in doc_data:
                    self.errors.append(f"DOCUMENTATION missing required field: {field}")
            
            # Validate options if present
            if "options" in doc_data and doc_data["options"]:
                self._validate_options(doc_data["options"])
            
        except yaml.YAMLError as e:
            self.errors.append(f"DOCUMENTATION is not valid YAML: {e}")
        except ImportError:
            self.warnings.append("PyYAML not installed, cannot fully validate DOCUMENTATION")
    
    def _validate_options(self, options: dict) -> None:
        """Validate module options documentation."""
        if not isinstance(options, dict):
            self.errors.append("DOCUMENTATION options is not a dict")
            return
        
        for opt_name, opt_spec in options.items():
            if not isinstance(opt_spec, dict):
                self.warnings.append(f"Option '{opt_name}' has invalid spec")
                continue
            
            # Each option should have description
            if "description" not in opt_spec:
                self.warnings.append(f"Option '{opt_name}' missing description")
            
            # Type is recommended
            if "type" not in opt_spec:
                self.warnings.append(f"Option '{opt_name}' missing type")
    
    def validate_examples(self) -> None:
        """Validate the EXAMPLES block has content."""
        examples = self.extract_doc_block("EXAMPLES")
        
        if examples and examples.strip():
            # Check for at least one example
            if "- name:" not in examples and "name:" not in examples:
                self.warnings.append("EXAMPLES block should contain task examples")
    
    def validate_argument_spec(self) -> None:
        """Check if argument_spec is properly defined."""
        # Look for argument_spec definition
        if "argument_spec" not in self.content:
            self.errors.append("No argument_spec found in module")
            return
        
        # Check for AnsibleModule instantiation
        if "AnsibleModule" not in self.content:
            self.errors.append("AnsibleModule not used in module")
    
    def validate(self) -> tuple[list[str], list[str]]:
        """Run all validations and return errors and warnings."""
        if not self.load_module():
            return self.errors, self.warnings
        
        self.validate_doc_blocks()
        self.validate_documentation_content()
        self.validate_examples()
        self.validate_argument_spec()
        
        return self.errors, self.warnings


def find_collection_root() -> Path:
    """Find the collection root directory."""
    cwd = Path.cwd()
    
    if (cwd / "galaxy.yml").exists():
        return cwd
    
    if cwd.name == "scripts" and (cwd.parent / "galaxy.yml").exists():
        return cwd.parent
    
    ansible_env = os.environ.get("ANSIBLE")
    if ansible_env:
        ansible_path = Path(ansible_env)
        if (ansible_path / "galaxy.yml").exists():
            return ansible_path
    
    return cwd


def find_modules(root: Path) -> list[Path]:
    """Find all Python modules in the collection."""
    modules_dir = root / "plugins" / "modules"
    
    if not modules_dir.is_dir():
        return []
    
    modules = []
    for py_file in modules_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue  # Skip deprecated modules
        if py_file.name == "__init__.py":
            continue
        modules.append(py_file)
    
    return sorted(modules)


def main():
    """Main entry point."""
    print("=" * 60)
    print("Validating Extreme FE Module Documentation")
    print("=" * 60)
    
    root = find_collection_root()
    print(f"\nCollection root: {root}")
    
    modules = find_modules(root)
    
    if not modules:
        print("\n⚠️  No modules found in plugins/modules/")
        print("   This is expected if the collection is still in development.")
        sys.exit(0)
    
    print(f"\nFound {len(modules)} module(s) to validate")
    
    total_errors = 0
    total_warnings = 0
    failed_modules = []
    
    for module_path in modules:
        module_name = module_path.stem
        print(f"\n📦 Validating: {module_name}")
        
        validator = ModuleDocValidator(module_path)
        errors, warnings = validator.validate()
        
        for error in errors:
            print(f"   ❌ {error}")
        for warning in warnings:
            print(f"   ⚠️  {warning}")
        
        if errors:
            failed_modules.append(module_name)
            total_errors += len(errors)
        
        total_warnings += len(warnings)
        
        if not errors and not warnings:
            print("   ✅ All checks passed")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Modules checked: {len(modules)}")
    print(f"  Total errors:    {total_errors}")
    print(f"  Total warnings:  {total_warnings}")
    
    if failed_modules:
        print(f"\n❌ FAILED: {len(failed_modules)} module(s) have errors:")
        for mod in failed_modules:
            print(f"   - {mod}")
        sys.exit(1)
    else:
        print("\n✅ PASSED: All modules have valid documentation")
        sys.exit(0)


if __name__ == "__main__":
    main()
