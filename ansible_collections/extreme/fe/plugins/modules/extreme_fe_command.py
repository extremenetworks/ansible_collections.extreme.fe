# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to execute Fabric Engine CLI commands via HTTPAPI."""

from __future__ import annotations

DOCUMENTATION = r"""
module: extreme_fe_command
short_description: Execute CLI commands on ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
- Execute one or more CLI commands on ExtremeNetworks Fabric Engine switches using the
  custom C(extreme_fe) HTTPAPI plugin.
- Ensures the commands run in the order provided and submits them as a single REST operation to
  C(/v0/operation/system/cli).
- When the device stops that operation early after a command it reports with status 400 but that
  still produced output that is not a CLI error (for example C(show sys-info)), the module sends the commands the
  device skipped in follow-up operations, in order, so the batch completes.
- Returns the CLI output for every command and fails when any command reports an error.
author:
- Bjorn Haas (@bhaas_extr)
notes:
- Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped
  with this project.
- Designed for Fabric Engine targets; other platforms are not supported.
- Some commands, for example C(show sys-info), return status 400 together with complete output. The module
  treats them as successful with a warning (see C(cli_warnings) in the return values).
- With C(continue_on_failure=false) the device stops a batch at the first command that does not return 200 and
  reports every following command as 409 (not executed). When that first command is a 400 with output that is not a
  CLI error, the module re-sends the skipped commands in follow-up requests until the batch completes. The follow-up requests
  start without any CLI mode that an earlier command of the batch entered, so a batch whose later commands depend
  on such a mode should set C(continue_on_failure=true), which keeps everything in one request.
- A command that fails for real (a 400 without output, a 400 whose output is a CLI error message, that is a line
  starting with C(%) such as C(% Invalid input detected), or with the word C(Error) and a colon as in the answer to
  C(vlan delete) on a missing VLAN, or any other non-200 status) still stops the batch and fails the task; the commands
  after it are not re-sent.
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
      may execute subsequent commands when this option is true. The failed result still
      returns C(responses) for every command, so the output of the commands that succeeded
      can be read.
    - When false, the device stops the batch at the first command that does not return 200. A command that
      returns 400 with output that is not a CLI error is accepted by the module, which then re-sends the
      commands the device skipped; any other non-200 status, or a 400 whose output is a CLI error, stops the
      batch and fails the task.
    type: bool
    default: false
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc:

# =========================================================================
# Full playbook examples:
# To create a complete playbook, uncomment the lines starting with:
#   '# - name:', '# hosts:', '# gather_facts:', and '# tasks:'
# After uncommenting, realign indentation to conform to YAML format
# (playbook level at col 0, tasks indented under tasks:)
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
  description:
  - Indicates the module executed CLI commands on the device. Always true when the task succeeds.
  - When the task fails, true if at least one command was executed before the failure (it returned 200, or 400
    with output that is not a CLI error), so a failed batch that already ran configuration commands is not reported
    as unchanged.
  - A failed task lists the commands that ran in C(details.executed). When a follow-up request re-sending skipped
    commands fails, the commands of the failed request are listed in C(details.unknown), because they may or may not
    have run, so check the device before retrying. Only when the device answered 409 (not executed) for that request
    are they listed in C(details.not_executed) instead.
  - A response with a malformed entry, to the first request or to a follow-up one, still counts the commands its
    well-formed entries confirm (200, or 400 with output that is not a CLI error) as executed, with C(changed=true); only the other commands
    of that request are listed in C(details.unknown).
  - When the response to the first request cannot be read (empty, malformed or with the wrong number of entries)
    and confirms no execution, or the first request fails without an HTTP status (a lost connection, for
    example), C(changed) stays false and every position is listed in C(details.unknown), with an empty
    C(details.executed). An explicit HTTP error of the first request is reported as before.
  - A response with fewer or more entries than commands submitted counts a command as executed only when a
    confirming result names it in C(cliInput) and that command text occurs once in the request; the other commands
    of that request are listed in C(details.unknown). The details of a malformed response never carry the response
    itself, which holds command text and output.
  - These three lists hold the 0-based positions of the commands in C(commands), not the command text, so a
    password-bearing command is never copied into them.
  returned: always
  type: bool
responses:
  description:
  - Results returned by the device for each CLI command, one entry per command in C(commands) order.
  - Also returned when the task fails because a command failed, with an entry for every command, the failed
    one included, so the output of the commands that succeeded can still be read (for example with
    C(ignore_errors)). Not returned when the device response cannot be read or a request fails without
    results; C(details) then lists the commands by position.
  returned: always, except when no readable response was received
  type: list
  elements: dict
  contains:
    command:
      description: CLI command that was issued.
      type: str
    output:
      description:
      - CLI output as a list of lines for better readability, without line terminators.
      - An empty list when the command produced no output.
      type: list
      elements: str
    status_code:
      description: HTTP-style status code reported for the CLI command (200, 400, or 409).
      type: int
    warning:
      description: Warning message when the device returned status 400 with output that is not a CLI error.
      type: str
      returned: when status_code is 400 with output that is not a CLI error
cli_warnings:
  description:
  - List of commands that returned status 400 with output that is not a CLI error, treated as successful with
    warning.
  - A 400 whose output is a CLI error (a line starting with C(%) or with the word C(Error) and a colon) fails the
    command instead and is not listed here.
  returned: when any command returns a 400 with output that is not a CLI error
  type: list
  elements: dict
metadata:
  description:
  - Aggregated success, failure, and skip counters reported by the device (if any).
  - When the module re-sent skipped commands, the counters of all requests are combined and C(skipped) counts only
    the commands that were never executed.
  returned: when provided by the device
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown

ARGUMENT_SPEC = {
    "commands": {"type": "list", "elements": "str", "required": True},
    "continue_on_failure": {"type": "bool", "default": False},
}

CLI_ENDPOINT = "/v0/operation/system/cli"


class FeCommandError(Exception):
    """Raised when the device returns an unexpected or failed CLI response."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, object] | None = None,
        changed: bool = False,
        batch_executed: list[int] | None = None,
        result: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        self.changed = changed
        # Positions, within the failed request, of the commands its response still
        # confirms as executed (see _send_batch()); offset by execute_cli_commands().
        self.batch_executed = list(batch_executed or [])
        # Top-level result keys a failure still returns (responses, cli_warnings,
        # metadata), so the output of the commands that succeeded is not lost.
        self.result = dict(result or {})

    def to_fail_kwargs(self) -> dict[str, object]:
        payload: dict[str, object] = dict(self.result)
        payload["msg"] = to_text(self)
        if self.details:
            payload["details"] = self.details
        if self.changed:
            payload["changed"] = True
        return payload


def _validated_commands(commands: list[str]) -> list[str]:
    normalized: list[str] = []
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


def _output_to_lines(output: str | None) -> list[str]:
    """Convert raw CLI output string to a list of lines for better readability.

    No output (None or an empty string) is an empty list, not one empty line.
    splitlines() drops the line terminators, CRLF included, and does not add an
    empty last line for output that ends with a newline.
    """
    if output is None:
        return []
    text = to_text(output, errors="surrogate_then_replace")
    if not text:
        return []
    return text.splitlines()


def _build_cli_path(continue_on_failure: bool) -> str:
    if continue_on_failure:
        return f"{CLI_ENDPOINT}?continue_on_failure=true"
    return CLI_ENDPOINT


def _normalize_response(
    response: dict[str, object],
    *,
    commands: list[str],
) -> dict[str, object]:
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list):
        raise FeCommandError(
            "Device returned an unexpected CLI response format",
            details={"response_type": type(data).__name__},
        )
    if len(data) != len(commands):
        raise FeCommandError(
            "Device returned a different number of CLI responses than commands submitted",
            details={"requested": len(commands), "received": len(data)},
        )

    normalized: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise FeCommandError(
                "Device returned a malformed CLI response entry",
                # Only the type: a malformed entry can be bare command text or output.
                details={"index": idx, "entry_type": type(entry).__name__},
            )
        command = to_text(entry.get("cliInput") or commands[idx], errors="surrogate_then_replace")
        status = entry.get("statusCode")
        output = entry.get("cliOutput")
        output_lines = _output_to_lines(output)
        has_output = bool(output_lines and any(line.strip() for line in output_lines))
        normalized_entry: dict[str, object] = {
            "command": command,
            "status_code": status,
            "output": output_lines,
        }
        normalized.append(normalized_entry)
        if status == 200:
            pass
        elif status == 400 and has_output and not _is_cli_error_output(output_lines):
            # Device returned 400 with output that is not a CLI error (e.g. show sys-info).
            # Treat as a warning rather than a failure. A 400 whose output is a
            # CLI error ("% Invalid input ...") is a failure like any other.
            normalized_entry["warning"] = (
                "Device returned status 400 but produced CLI output; treating as successful with warning"
            )
            warnings.append(
                {
                    "index": idx,
                    "command": command,
                    "status_code": status,
                    "output": output_lines,
                }
            )
        else:
            # 409 (conflict), 400 without output, or any other non-200 status
            failures.append(
                {
                    "index": idx,
                    "command": command,
                    "status_code": status,
                    "output": output_lines,
                }
            )

    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else None
    result: dict[str, object] = {"responses": normalized}
    if warnings:
        result["cli_warnings"] = warnings
    if metadata is not None:
        result["metadata"] = metadata
    if failures:
        # Commands that returned 200 (or an accepted 400) were executed before the
        # failure, so the task did change the device: report changed=true then.
        # They are listed by position in commands, not by text: a command can carry
        # a password, and this field is new detail no caller expects to contain one.
        executed = [
            idx for idx, entry in enumerate(normalized) if entry.get("status_code") == 200 or "warning" in entry
        ]
        # The failed result carries the same top-level keys as a successful one:
        # every command's entry in responses, the failed one included,
        # so a playbook that ignores the failure can still read the output of the
        # commands that succeeded.
        raise FeCommandError(
            "One or more CLI commands failed",
            details={"failures": failures, "cli_warnings": warnings, "metadata": metadata, "executed": executed},
            changed=bool(executed),
            result=result,
        )
    return result


def _has_output(entry: dict[str, object]) -> bool:
    """Return True when a raw device entry carries at least one non-blank line of CLI output."""
    lines = _output_to_lines(entry.get("cliOutput"))  # type: ignore[arg-type]
    return any(line.strip() for line in lines)


def _is_cli_error_output(lines: list[str]) -> bool:
    """Return True when CLI output carries a Fabric Engine error message.

    The CLI reports an error on a line starting with '%', for example
    "% Invalid input detected at '^' marker." for an unknown command, or with
    'Error:' after a terminal bell, for example "\x07Error: Invalid VLAN ID" for
    'vlan delete' on a missing VLAN. The device answers both with status 400,
    like the output-with-400 of show sys-info.
    """
    for line in lines:
        text = line.replace("\x07", "").strip()
        if text.startswith("%") or text.lower().startswith("error:"):
            return True
    return False


def _is_accepted_400(entry: object) -> bool:
    """Return True for a 400 entry with real output and no CLI error (successful with warning)."""
    if not (isinstance(entry, dict) and entry.get("statusCode") == 400 and _has_output(entry)):
        return False
    return not _is_cli_error_output(_output_to_lines(entry.get("cliOutput")))  # type: ignore[arg-type]


def _skipped_tail_start(data: list[object]) -> int | None:
    """Return the index of the first skipped command when the device stopped at an accepted 400.

    With continue_on_failure=false the device stops at the first non-200 entry and
    reports every following command as 409 (not executed). When that first non-200
    entry is a 400 the module accepts (output, no CLI error), the 409 entries are only
    collateral damage and the commands must be sent again. Returns None when there
    is nothing to re-issue: the batch completed, it stopped at a genuine failure, or
    the trailing entries are not all 409.
    """
    for idx, entry in enumerate(data):
        if isinstance(entry, dict) and entry.get("statusCode") == 200:
            continue
        # First non-200 entry: only an accepted 400 followed by nothing but 409s qualifies.
        tail = data[idx + 1 :]
        if _is_accepted_400(entry) and tail and all(isinstance(e, dict) and e.get("statusCode") == 409 for e in tail):
            return idx + 1
        return None
    return None


def _identified_executions(batch: list[str], data: list[object]) -> list[int]:
    """Positions in *batch* that a response with the wrong entry count reliably confirms as executed.

    A result confirms an execution (200, or an accepted 400) and names its
    command in cliInput. It identifies a position only when that command text
    occurs exactly once in the batch; a repeated command, a result without
    cliInput, or one naming nothing submitted identifies nothing.
    """
    texts = [to_text(command).strip() for command in batch]
    positions: set[int] = set()
    for entry in data:
        if not isinstance(entry, dict) or not (entry.get("statusCode") == 200 or _is_accepted_400(entry)):
            continue
        cli_input = entry.get("cliInput")
        if not isinstance(cli_input, str):
            continue
        matches = [idx for idx, text in enumerate(texts) if text == cli_input.strip()]
        if len(matches) == 1:
            positions.add(matches[0])
    return sorted(positions)


def _send_batch(connection: Connection, path: str, batch: list[str]) -> dict[str, object]:
    """POST one batch of commands and return the validated raw response."""
    raw_response = connection.send_request(batch, path=path, method="POST")
    if raw_response is None:
        raise FeCommandError("Device returned an empty response to the CLI request")
    # The details of these failures never carry the raw response: it holds the
    # command text and output, which can contain a password.
    if not isinstance(raw_response, dict):
        raise FeCommandError(
            "Device returned an unexpected payload for CLI execution",
            details={"response_type": type(raw_response).__name__},
        )
    data = raw_response.get("data")
    if not isinstance(data, list):
        raise FeCommandError(
            "Device returned an unexpected CLI response format",
            details={"response_type": type(data).__name__},
        )
    if len(data) != len(batch):
        # Positions no longer identify commands once entries are missing or
        # extra, so a confirmed execution is matched by its cliInput instead.
        raise FeCommandError(
            "Device returned a different number of CLI responses than commands submitted",
            details={"requested": len(batch), "received": len(data)},
            batch_executed=_identified_executions(batch, data),
        )
    # Validated here, inside the caller's try, so a malformed entry keeps the
    # commands already executed and marks the rest unknown. The well-formed
    # entries of the same response that confirm an execution (200, or an accepted
    # 400) are kept too, so only the unconfirmed commands become unknown.
    malformed = [idx for idx, entry in enumerate(data) if not isinstance(entry, dict)]
    if malformed:
        confirmed = [
            idx
            for idx, entry in enumerate(data)
            if isinstance(entry, dict) and (entry.get("statusCode") == 200 or _is_accepted_400(entry))
        ]
        raise FeCommandError(
            "Device returned a malformed CLI response entry",
            # Only the type: a malformed entry can be bare command text or output.
            details={"index": malformed[0], "entry_type": type(data[malformed[0]]).__name__},
            batch_executed=confirmed,
        )
    return raw_response


def _merge_metadata(rounds: list[dict[str, object] | None], data: list[object]) -> dict[str, object] | None:
    """Combine the per-request device counters; commands that were re-issued no longer count as skipped."""
    reported = [m for m in rounds if isinstance(m, dict)]
    if not reported:
        return None
    merged: dict[str, object] = dict(reported[-1])
    for key in ("succeeded", "failed"):
        if all(isinstance(m.get(key), int) for m in reported):
            merged[key] = sum(m[key] for m in reported)  # type: ignore[misc]
    if "skipped" in merged:
        merged["skipped"] = sum(1 for e in data if isinstance(e, dict) and e.get("statusCode") == 409)
    return merged


def _resend_failure(exc: Exception, done_count: int, total: int) -> FeCommandError:
    """Build the error for a failed request after commands were executed (changed=true).

    The first *done_count* of the *total* commands were executed by earlier
    requests (0 for the first request); the request that failed carried the rest,
    of which its own response may still confirm some (exc.batch_executed, from a
    response with a malformed entry). A failed request does not prove its other
    commands did not run: the device can execute them and the response can still
    be lost, or _send_batch() can reject an empty or malformed answer that came
    back after they ran. They are reported as details.unknown, unless the device
    answered 409 (not executed) for the request, which confirms they were skipped
    (details.not_executed). Commands are listed by their position in commands,
    never by text, since a command can carry a password.
    """
    confirmed = {done_count + idx for idx in getattr(exc, "batch_executed", [])}
    executed = list(range(done_count)) + sorted(confirmed)
    pending = [idx for idx in range(done_count, total) if idx not in confirmed]
    code = getattr(exc, "code", None)
    if done_count:
        message = (
            "The request re-sending the %d skipped command(s) failed after %d command(s) had been executed: %s"
            % (
                total - done_count,
                len(executed),
                to_text(exc).rstrip(". "),
            )
        )
    else:
        message = "The CLI request failed after %d command(s) had been executed: %s" % (
            len(executed),
            to_text(exc).rstrip(". "),
        )
    details: dict[str, object] = {"executed": executed, "code": code}
    if code == 409:
        details["not_executed"] = pending
        message += ". The device reported the re-sent command(s) as not executed (409)."
    else:
        details["unknown"] = pending
        message += (
            ". The outcome of the other %d command(s) of that request is unknown, they may or may not have run;"
            " check the device before retrying." % len(pending)
        )
    return FeCommandError(message, details=details, changed=True)


def execute_cli_commands(
    connection: Connection,
    *,
    commands: list[str],
    continue_on_failure: bool,
) -> dict[str, object]:
    path = _build_cli_path(continue_on_failure)
    pending = commands
    merged_data: list[object] = []
    round_metadata: list[dict[str, object] | None] = []
    while True:
        try:
            raw_response = _send_batch(connection, path, pending)
        except (FeCommandError, ConnectionError) as exc:
            if not merged_data and not getattr(exc, "batch_executed", None):
                # The first request was answered but its response could not be
                # read (an FeCommandError), or the connection failed without an
                # HTTP status (lost after sending, for example): any command may
                # have run, so every position is unknown (changed stays false, as
                # nothing is confirmed). An explicit HTTP error, such as 409, keeps
                # its own handling.
                ambiguous = isinstance(exc, FeCommandError) or answer_unknown(exc)
                if ambiguous:
                    raise FeCommandError(
                        "%s. The outcome of the %d submitted command(s) is unknown, they may or may not have run;"
                        " check the device before retrying." % (to_text(exc).rstrip(". "), len(commands)),
                        details=dict(
                            getattr(exc, "details", None) or {}, executed=[], unknown=list(range(len(commands)))
                        ),
                    ) from exc
                raise
            raise _resend_failure(exc, len(merged_data), len(commands)) from exc
        data: list[object] = raw_response["data"]  # type: ignore[assignment]
        metadata = raw_response.get("metadata")
        round_metadata.append(metadata if isinstance(metadata, dict) else None)
        restart = None if continue_on_failure else _skipped_tail_start(data)
        if restart is None:
            merged_data.extend(data)
            break
        # The device stopped after a command the module accepts (an accepted 400) and
        # skipped the rest. Keep what ran, then send the skipped commands again. Every
        # round executes at least its first command, so this loop always terminates.
        merged_data.extend(data[:restart])
        pending = pending[restart:]
    response: dict[str, object] = {"data": merged_data}
    if len(round_metadata) == 1:
        if round_metadata[0] is not None:
            response["metadata"] = round_metadata[0]
    else:
        merged_metadata = _merge_metadata(round_metadata, merged_data)
        if merged_metadata is not None:
            response["metadata"] = merged_metadata
    return _normalize_response(response, commands=commands)


def main() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    try:
        commands = _validated_commands(module.params["commands"] or [])
    except FeCommandError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    continue_on_failure: bool = bool(module.params.get("continue_on_failure"))

    if module.check_mode:
        module.exit_json(
            changed=True, responses=[{"command": cmd, "status_code": None, "output": []} for cmd in commands]
        )

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
