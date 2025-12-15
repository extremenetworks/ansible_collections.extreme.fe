#!/usr/bin/env python3
"""Exercise extreme_fe_command validation guardrails under coverage."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
COLLECTIONS_BASE = HERE.parents[6]
REPO_ROOT = HERE.parents[7]

for candidate in (str(REPO_ROOT), str(COLLECTIONS_BASE)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import types

if "ansible" not in sys.modules:
    sys.modules["ansible"] = types.ModuleType("ansible")

if "ansible.module_utils" not in sys.modules:
    module_utils_pkg = types.ModuleType("ansible.module_utils")
    sys.modules["ansible.module_utils"] = module_utils_pkg
else:
    module_utils_pkg = sys.modules["ansible.module_utils"]

if "ansible.module_utils.basic" not in sys.modules:
    basic_mod = types.ModuleType("ansible.module_utils.basic")

    class _StubAnsibleModule:  # pylint: disable=too-few-public-methods
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401 - stub only
            raise RuntimeError("Ansible runtime not available in validation script")

    basic_mod.AnsibleModule = _StubAnsibleModule  # type: ignore[attr-defined]
    sys.modules["ansible.module_utils.basic"] = basic_mod
    setattr(module_utils_pkg, "basic", basic_mod)

if "ansible.module_utils.connection" not in sys.modules:
    connection_mod = types.ModuleType("ansible.module_utils.connection")

    class _StubConnection:  # pylint: disable=too-few-public-methods
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401 - stub only
            raise RuntimeError("HTTPAPI connection not available in validation script")

    class _StubConnectionError(Exception):
        pass

    connection_mod.Connection = _StubConnection  # type: ignore[attr-defined]
    connection_mod.ConnectionError = _StubConnectionError  # type: ignore[attr-defined]
    sys.modules["ansible.module_utils.connection"] = connection_mod
    setattr(module_utils_pkg, "connection", connection_mod)

if "ansible.module_utils._text" not in sys.modules:
    text_mod = types.ModuleType("ansible.module_utils._text")

    def _stub_to_text(value, errors="strict") -> str:  # noqa: D401 - stub
        if value is None:
            return ""
        return str(value)

    text_mod.to_text = _stub_to_text  # type: ignore[attr-defined]
    sys.modules["ansible.module_utils._text"] = text_mod
    setattr(module_utils_pkg, "_text", text_mod)

_bootstrapped = os.environ.get("EXTREME_FE_VALIDATION_UNDER_COV") == "1"
if not _bootstrapped:
    try:
        import coverage as _cov_probe  # type: ignore
    except Exception:
        _cov_probe = None  # type: ignore
    else:
        os.environ["EXTREME_FE_VALIDATION_UNDER_COV"] = "1"
        os.execv(sys.executable, [sys.executable, "-m", "coverage", "run", "--append", __file__])

try:
    import coverage  # type: ignore
except Exception:  # pragma: no cover - best effort hook
    coverage = None  # type: ignore

cov = None
if coverage is not None and not _bootstrapped:
    try:
        data_file = os.environ.get("COVERAGE_FILE")
        cov = coverage.Coverage(data_file=data_file, auto_data=True)
        cov.start()
    except Exception:
        cov = None

from ansible_collections.extreme.fe.plugins.modules.extreme_fe_command import (
    FeCommandError,
    _validated_commands,
)

SCENARIOS = (
    ([None], "Command entries must be strings"),
    ([""], "Command entries must not be empty"),
    ([], "At least one CLI command must be supplied"),
)

errors = []
for payload, expected in SCENARIOS:
    try:
        _validated_commands(payload)
    except FeCommandError as exc:
        if expected not in str(exc):
            errors.append(
                f"Payload {payload!r} raised {exc!r}; expected message containing {expected!r}"
            )
    else:
        errors.append(f"Payload {payload!r} unexpectedly passed validation")

if cov is not None:
    cov.stop()
    try:
        cov.save()
    except Exception:
        pass

if errors:
    for entry in errors:
        sys.stderr.write(entry + "\n")
    sys.exit(1)

sys.exit(0)
