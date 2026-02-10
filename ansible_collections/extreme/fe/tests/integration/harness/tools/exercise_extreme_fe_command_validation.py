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
