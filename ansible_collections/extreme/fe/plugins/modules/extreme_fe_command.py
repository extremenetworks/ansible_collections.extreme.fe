# -*- coding: utf-8 -*-
"""Ansible module to execute Fabric Engine CLI commands via HTTPAPI."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils._text import to_text

from typing import Dict, List, Optional

DOCUMENTATION = r"""
module: extreme_fe_command
short_description: Execute CLI commands on ExtremeNetworks Fabric Engine switches
version_added: 1.2.0
description:
- Execute one or more CLI commands on ExtremeNetworks Fabric Engine (VOSS) switches using the
  custom ``extreme_fe`` HTTPAPI plugin.
- Ensures the commands run in the order provided and submits them as a single REST operation to
  ``/v0/operation/system/cli``.
- Returns the CLI output for every command and fails when any command reports an error.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped
  with this project.
- Designed for Fabric Engine (VOSS) targets; other platforms are not supported.
requirements:
- ansible.netcommon
options:
  commands:
    description:
    - Ordered list of CLI commands to execute on the device.
    - Commands are sent as a single REST payload so execution order is preserved.
    required: true
    type: list
    elements: str
  continue_on_failure:
    description:
    - Continue executing commands after a failure is reported for a previous entry.
    - The module still fails when any command returns a non-200 status code, but the switch
      may execute subsequent commands when this option is true.
    type: bool
    default: false
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc:

# =========================================================================
# Full playbook examples:
# See examples/extreme_fe_command_examples.yml for complete playbooks
# =========================================================================

# -------------------------------------------------------------------------
# Task 1: Execute CLI commands with strict error handling
# Description:
#   - This example demonstrates how to execute a sequence of CLI commands
#     on a Fabric Engine switch. By default, execution stops immediately
#     if any command fails, ensuring that configuration errors are caught
#     early and the switch state remains predictable.
# -------------------------------------------------------------------------
# - name: "Task 1: Execute CLI commands with strict stop-on-failure"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Run CLI commands
  extreme.fe.extreme_fe_command:
    commands:
      - enable
      - configure terminal
      - show vlan basic
  register: cli_result

# -------------------------------------------------------------------------
# Task 2: Execute CLI commands with continue on failure
# Description:
#   - This example shows how to use the 'continue_on_failure' option to
#     execute multiple CLI commands even if some fail. This is useful when
#     running commands that may not apply to all switches (e.g., enabling
#     super-user mode which may already be active or not available).
# -------------------------------------------------------------------------
# - name: "Task 2: Execute CLI commands with continue on failure"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Execute CLI sequence with continue on failure
  extreme.fe.extreme_fe_command:
    commands:
      - enable
      - enable super-user-mode
      - show vlan basic
    continue_on_failure: true
"""

RETURN = r"""
changed:
  description: Indicates the module executed CLI commands on the device. Always true.
  returned: always
  type: bool
responses:
  description: Results returned by the device for each CLI command.
  returned: always
  type: list
  elements: dict
  contains:
    command:
      description: CLI command that was issued.
      type: str
    output:
      description: CLI output as a list of lines for better readability.
      type: list
      elements: str
    status_code:
      description: HTTP-style status code reported for the CLI command.
      type: int
metadata:
  description: Aggregated success, failure, and skip counters reported by the device (if any).
  returned: when provided by the device
  type: dict
"""

ARGUMENT_SPEC = {
    "commands": {"type": "list", "elements": "str", "required": True},
    "continue_on_failure": {"type": "bool", "default": False},
}

CLI_ENDPOINT = "/v0/operation/system/cli"


class FeCommandError(Exception):
    """Raised when the device returns an unexpected or failed CLI response."""

    def __init__(self, message: str, *, details: Optional[Dict[str, object]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, object]:
        payload: Dict[str, object] = {"msg": to_text(self)}
        if self.details:
            payload["details"] = self.details
        return payload


def _validated_commands(commands: List[str]) -> List[str]:
    normalized: List[str] = []
    for idx, entry in enumerate(commands):
        if entry is None:
            raise FeCommandError(
                "Command entries must be strings",
                details={"index": idx, "entry": entry},
            )
        command_text = to_text(entry, errors="surrogate_then_replace")
        if not command_text.strip():
            raise FeCommandError(
                "Command entries must not be empty",
                details={"index": idx},
            )
        normalized.append(command_text)
    if not normalized:
        raise FeCommandError("At least one CLI command must be supplied")
    return normalized


def _output_to_lines(output: Optional[str]) -> List[str]:
    """Convert raw CLI output string to a list of lines for better readability."""
    if output is None:
        return []
    text = to_text(output, errors="surrogate_then_replace")
    # Split on newlines, strip trailing carriage returns from each line
    lines = [line.rstrip('\r') for line in text.split('\n')]
    return lines


def _build_cli_path(continue_on_failure: bool) -> str:
    if continue_on_failure:
        return f"{CLI_ENDPOINT}?continue_on_failure=true"
    return CLI_ENDPOINT


def _normalize_response(
    response: Dict[str, object],
    *,
    commands: List[str],
) -> Dict[str, object]:
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list):
        raise FeCommandError(
            "Device returned an unexpected CLI response format",
            details={"response": response},
        )
    if len(data) != len(commands):
        raise FeCommandError(
            "Device returned a different number of CLI responses than commands submitted",
            details={"requested": len(commands), "received": len(data), "response": response},
        )

    normalized: List[Dict[str, object]] = []
    failures: List[Dict[str, object]] = []

    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise FeCommandError(
                "Device returned a malformed CLI response entry",
                details={"index": idx, "entry": entry},
            )
        command = to_text(entry.get("cliInput") or commands[idx], errors="surrogate_then_replace")
        status = entry.get("statusCode")
        output = entry.get("cliOutput")
        output_lines = _output_to_lines(output)
        normalized_entry: Dict[str, object] = {
            "command": command,
            "status_code": status,
            "output": output_lines,
        }
        normalized.append(normalized_entry)
        if status != 200:
            failures.append({
                "index": idx,
                "command": command,
                "status_code": status,
                "output": output_lines,
            })

    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else None
    if failures:
        raise FeCommandError(
            "One or more CLI commands failed",
            details={"failures": failures, "metadata": metadata},
        )

    result: Dict[str, object] = {"responses": normalized}
    if metadata is not None:
        result["metadata"] = metadata
    return result


def execute_cli_commands(
    connection: Connection,
    *,
    commands: List[str],
    continue_on_failure: bool,
) -> Dict[str, object]:
    path = _build_cli_path(continue_on_failure)
    payload: List[str] = commands
    raw_response = connection.send_request(payload, path=path, method="POST")
    if raw_response is None:
        raise FeCommandError("Device returned an empty response to the CLI request")
    if not isinstance(raw_response, dict):
        raise FeCommandError(
            "Device returned an unexpected payload for CLI execution",
            details={"response": raw_response},
        )
    return _normalize_response(raw_response, commands=commands)


def main() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    try:
        commands = _validated_commands(module.params["commands"] or [])
    except FeCommandError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    continue_on_failure: bool = bool(module.params.get("continue_on_failure"))

    if module.check_mode:
        module.exit_json(changed=True, responses=[{"command": cmd, "status_code": None, "output": []} for cmd in commands])

    connection = Connection(module._socket_path)
    try:
        result = execute_cli_commands(
            connection,
            commands=commands,
            continue_on_failure=continue_on_failure,
        )
    except FeCommandError as exc:
        module.fail_json(**exc.to_fail_kwargs())
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
        )

    module.exit_json(changed=True, **result)


if __name__ == "__main__":
    main()
