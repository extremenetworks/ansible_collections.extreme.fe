# CI Pipeline Documentation

## Overview

The `extreme.fe` Ansible collection uses GitHub Actions for continuous integration and continuous delivery (CI/CD).

## Workflow Files

### Main CI Workflow

**File:** `.github/workflows/collection-ci.yml`

This is the primary CI workflow that runs on:
- Push to `main`, `develop`, or `release/**` branches
- Pull requests to `main` or `develop`
- Manual trigger via `workflow_dispatch`

## Pipeline Jobs

### 1. Validate Structure

Ensures the collection has all required directories and files:

**Required Directories:**
- `plugins/modules/`
- `plugins/httpapi/`
- `plugins/module_utils/`
- `roles/`
- `docs/`
- `tests/`
- `meta/`

**Required Files:**
- `galaxy.yml`
- `meta/runtime.yml`
- `README.md`
- `LICENSE`

**Script:** `scripts/validate_structure.py`

### 2. Validate Galaxy Metadata

Validates `galaxy.yml` contains:
- All mandatory fields (namespace, name, version, authors, description)
- Semantic versioning (e.g., `1.0.0`)
- Lowercase namespace and name

### 3. Python Linting

Runs the following Python linters:

| Tool | Purpose | Config File |
|------|---------|-------------|
| flake8 | Style guide enforcement | `.flake8` |
| isort | Import sorting | `.isort.cfg` |
| black | Code formatting | Default settings |
| mypy | Type checking (optional) | Default settings |

### 4. YAML Linting

Uses `yamllint` with configuration from `.yamllint.yml` to validate all YAML files in the collection.

### 5. Ansible Lint

Runs `ansible-lint` with configuration from `.ansible-lint` to check:
- Playbook best practices
- Role conventions
- FQCN (Fully Qualified Collection Names) usage

### 6. Validate Module Documentation

Ensures every module in `plugins/modules/` has:
- `DOCUMENTATION` block with required fields
- `EXAMPLES` block with task examples
- `RETURN` block (optional but recommended)
- Properly defined `argument_spec`

**Script:** `scripts/validate_docs.py`

### 7. Ansible Sanity Tests

Runs `ansible-test sanity` across multiple Ansible versions:
- stable-2.15
- stable-2.16
- stable-2.17

Tests include:
- Python syntax validation
- YAML validation
- Documentation validation
- Import testing
- Module validation

### 8. Unit Tests

Runs unit tests using:
- `pytest` for `tests/unit/` directory
- `ansible-test units` in Docker

Tested on Python versions:
- 3.10
- 3.11
- 3.12

### 9. Build Collection

Creates the collection artifact using:
```bash
ansible-galaxy collection build --force
```

The artifact is uploaded as a GitHub Actions artifact with 30-day retention.

### 10. CI Summary

Provides a summary of all job results and fails the pipeline if critical jobs failed.

## Running CI Locally

### Prerequisites

```bash
pip install ansible-core ansible-lint ansible-test
pip install flake8 isort black mypy yamllint
pip install pytest pytest-cov pyyaml
```

### Running Validation Scripts

```bash
# Validate structure
python scripts/validate_structure.py

# Validate module documentation
python scripts/validate_docs.py
```

### Running Linters

```bash
# Python linting
flake8 plugins/ scripts/ --config=.flake8
isort --check-only --diff plugins/ scripts/
black --check --diff plugins/ scripts/

# YAML linting
yamllint -c .yamllint.yml .

# Ansible linting
ansible-lint --config-file .ansible-lint
```

### Running Ansible Tests

```bash
# Sanity tests (requires Docker)
ansible-test sanity --docker -v --color

# Unit tests
ansible-test units --docker -v --color

# Or with pytest
pytest tests/unit/ -v
```

### Building the Collection

```bash
ansible-galaxy collection build --force
```

## Configuration Files

| File | Purpose |
|------|---------|
| `.flake8` | Flake8 Python linter configuration |
| `.isort.cfg` | isort import sorter configuration |
| `.ansible-lint` | Ansible-lint configuration |
| `.yamllint.yml` | yamllint YAML linter configuration |
| `galaxy.yml` | Collection metadata |
| `meta/runtime.yml` | Ansible version requirements |

## Troubleshooting

### Common Issues

1. **Sanity test failures**
   - Ensure all Python files have proper syntax
   - Check that module documentation is valid YAML
   - Verify imports are correct

2. **Module validation failures**
   - Add `DOCUMENTATION`, `EXAMPLES`, and `RETURN` blocks
   - Define `argument_spec` in modules
   - Use `AnsibleModule` class

3. **Linting failures**
   - Run `black --diff` to see formatting changes
   - Run `isort --diff` to see import ordering issues
   - Use `flake8` to identify style issues

### Skip CI for a Commit

Add `[skip ci]` or `[ci skip]` to your commit message:
```bash
git commit -m "Update docs [skip ci]"
```

## Best Practices

1. **Before pushing:**
   - Run linters locally
   - Run validation scripts
   - Test your changes

2. **Pull requests:**
   - Ensure all CI checks pass
   - Address any warnings
   - Update documentation if needed

3. **Module development:**
   - Always include complete documentation
   - Add unit tests for new functionality
   - Follow Ansible module guidelines

## References

- [Ansible Collection Development](https://docs.ansible.com/ansible/latest/dev_guide/developing_collections.html)
- [ansible-test Documentation](https://docs.ansible.com/ansible/latest/dev_guide/testing_running_locally.html)
