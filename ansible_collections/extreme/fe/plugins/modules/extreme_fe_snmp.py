# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage the SNMP system name on Extreme Fabric Engine switches.

Module Architecture Overview
============================
This module manages the SNMP system name (sysName) on Extreme
Fabric Engine switches via the REST OpenAPI.

REST Endpoints used:
  GET   /v1/configuration/snmp
        → Retrieve SNMP settings (we extract only the 'name' field)
  PATCH /v0/configuration/snmp
        → Update SNMP common settings (we send only the 'name' field)

Fabric Engine constraints:
  - System name is a string, 0-255 characters
  - An empty string ("") effectively clears the system name
  - This is a singleton resource (one system name per device)

Supported states:
  - merged     : Set the system name if different from current
  - replaced   : Same as merged for this single-field singleton
  - overridden : Same as merged for this single-field singleton
  - deleted    : Clear the system name (reset to empty string)
  - gathered   : Read-only, returns current system name

Code Flow (run_module):
  1. Connect to switch via httpapi
  2. Fetch current SNMP config from the switch (GET /v1/configuration/snmp)
  3. Extract the 'name' field
  4. Based on the requested state, apply/delete/gather the system name
  5. Return results with changed status and current values
"""

from __future__ import annotations

# ── Module Documentation ──────────────────────────────────────────────────────

DOCUMENTATION = r"""
---
module: extreme_fe_snmp
short_description: Manage SNMP system name on Extreme Fabric Engine switches
description:
  - This module manages the SNMP system name (sysName) on Extreme
    Fabric Engine switches using the REST API.
  - Supports all five Ansible resource module states.
version_added: "1.2.0"
author:
  - Andreea-Lavinia Vraja (@avraja_extr)
options:
  config:
    description:
      - The SNMP system name configuration.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional for C(deleted) and C(gathered).
    type: dict
    suboptions:
      name:
        description:
          - The system name for this device.
          - String between 0 and 255 characters.
          - An empty string clears the system name.
          - Required when C(state) is C(merged), C(replaced), or C(overridden).
        type: str
  state:
    description:
      - The state of the configuration after module completion.
    type: str
    choices:
      - merged
      - replaced
      - overridden
      - deleted
      - gathered
    default: merged
notes:
  - Tested against Fabric Engine Version 9.3.2.
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI connection plugin.
  - The module manages the switch's SNMP system name only. An unset name is shown as C(""); clear it with
    C(deleted) or with an empty C(name).
  - SNMP community strings and SNMPv3 passwords are never returned; they are removed from every result and
    error message.
  - If the connection drops while the name is being written, the task reports C(changed=true) with
    C(details.outcome=unknown), because the change may have been applied. Run the task again to make sure.
  - A task that fails after the name was written reports C(changed=true).
  - Supports check mode and diff mode.
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc:

# =========================================================================
# Full playbook examples with prerequisites:
# To create a complete playbook, uncomment the lines starting with:
#   '# - name:', '# hosts:', '# gather_facts:', and '# tasks:'
# After uncommenting, realign indentation to conform to YAML format
# (playbook level at col 0, tasks indented under tasks:)
# =========================================================================

# -------------------------------------------------------------------------
# Task 1: Set system name
# -------------------------------------------------------------------------
# - name: "Task 1: Set SNMP system name"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Set system name
  extreme.fe.extreme_fe_snmp:
    state: merged
    config:
      name: "my-switch-01"

# -------------------------------------------------------------------------
# Task 2: Replace and clear system name
# -------------------------------------------------------------------------
# - name: "Task 2: Replace or clear SNMP system name"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Replace system name
  extreme.fe.extreme_fe_snmp:
    state: replaced
    config:
      name: "new-switch-name"

- name: Clear system name
  extreme.fe.extreme_fe_snmp:
    state: deleted

# -------------------------------------------------------------------------
# Task 3: Gather current system name
# -------------------------------------------------------------------------
# - name: "Task 3: Gather SNMP system name"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather current system name
  extreme.fe.extreme_fe_snmp:
    state: gathered
  register: snmp_info
"""

RETURN = r"""
changed:
  description: Indicates whether any configuration changes were made.
  returned: always
  type: bool
before:
  description:
    - SNMP configuration before any changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
after:
  description:
    - SNMP configuration after the task, equal to C(before) when nothing changed.
    - In check mode, the predicted configuration.
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
diff:
  description:
    - The C(before) and C(after) configuration, for C(--diff) mode.
  returned: when state is merged, replaced, overridden, or deleted and diff mode is enabled
  type: dict
gathered:
  description:
    - Current SNMP configuration gathered from the device.
    - Returned only for C(state=gathered).
    - When no system name is set, C(name) is the empty string, so the result can be applied
      back as O(config) with O(state=merged).
  returned: when state is gathered
  type: dict
snmp:
  description: SNMP system name configuration state with differences.
  returned: always
  type: dict
  contains:
    config:
      description: Current configuration (gathered state only)
      returned: when state is gathered
      type: dict
    before:
      description: Configuration before changes
      returned: when state is not gathered
      type: dict
    after:
      description: Configuration after changes
      returned: when state is not gathered
      type: dict
    differences:
      description: Fields that changed between before and after states
      returned: when state is not gathered
      type: dict
api_responses:
  description:
    - API responses captured from the device for debugging.
    - Secret values are removed. The SNMP community strings and the SNMPv3 authentication and
      encryption passwords are left out, while their non-secret siblings such as C(isEncrypted) are kept.
    - The secret values read from the device are also removed from every message text of a response.
      The error text of a failed read is replaced by a generic text, wherever it appears in the
      response (top level, list entries and nested wrappers), and so is a bare text answer or a bare text
      entry of an array answer or wrapper; status codes are kept.
    - Deprecated and will be removed in 2.0.0.
    - Use C(snmp.before) and C(snmp.after) for the configuration before and after a change, and
      C(gathered) or C(snmp.config) for C(state=gathered).
  returned: always
  type: dict
"""

# Type hints make the code self-documenting and help IDEs catch mistakes
import json
from typing import Any

# AnsibleModule — the core class every Ansible module must instantiate;
# it handles argument parsing, check mode, exit/fail, etc.
from ansible.module_utils.basic import AnsibleModule

# to_text — safely converts bytes/strings to unicode text
from ansible.module_utils.common.text.converters import to_text

# Connection — communicates with the device through the httpapi plugin;
# ConnectionError — raised when the device is unreachable or returns a transport error
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import http_status, is_answer_unknown_code

# ── Constants ─────────────────────────────────────────────────────────────────

# REST endpoints for reading SNMP settings — try v1 first, fall back to v0
# (some older Fabric Engine firmware versions only expose the v0 endpoint)
SNMP_GET_PATHS = ["/v1/configuration/snmp", "/v0/configuration/snmp"]

# REST endpoint for updating SNMP common settings (v0 for PATCH)
SNMP_PATCH_PATH = "/v0/configuration/snmp"

# Ansible parameter → REST API field name mapping
# (name maps directly — same key in both Ansible and REST API)

# Factory defaults — what a clean Fabric Engine device looks like
# When system name is cleared, Fabric Engine returns "none" (the string) or null.
# Both are normalized to "" in the Ansible output, so gathered can be applied back.
DEFAULTS = {
    "name": "",
}

# Secret fields of the SNMP GET payloads (OpenAPI system/snmp schemas, v0 and v1):
# v1v2.access[].community (SnmpAccess / SnmpCommunity) and
# v3.access[].authenticationPassword / encryptionPassword (Secret: isEncrypted + value).
# "secret" and "passphrase" are defensive. Matched on the key with '-'/'_' removed,
# case-insensitively. A key named in SECRET_KEYS, or ending in "password", is a secret:
# a scalar value is removed with its key, a dict value keeps only its SECRET_FLAG_KEYS.
SECRET_KEYS = {"community", "secret", "passphrase"}
SECRET_FLAG_KEYS = {"isencrypted"}

# Free-text fields of a response: device messages that can quote any value, a secret too.
FREE_TEXT_KEYS = ("errorMessage", "message", "detail", "error")
# Status fields are left out of secret scrubbing: a short secret (for example a
# community "4") would otherwise turn statusCode "400" into "********00" and hide
# the error from _extract_error().
STATUS_KEYS = ("errorCode", "statusCode", "code", "status")
# Stands in for the device text of a failed read, and for a secret value quoted in a message.
READ_ERROR_MARKER = "(device error text omitted)"
SECRET_MARKER = "********"

# State constants
STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# States that require config parameter
REQUIRES_CONFIG = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}

# ── Argument Spec ─────────────────────────────────────────────────────────────

ARGUMENT_SPEC = {
    "config": {
        "type": "dict",
        "options": {
            # name — the system name (sysName)
            # Fabric Engine supports 0-255 characters
            "name": {"type": "str"},
        },
    },
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}


# ── Custom Exception ──────────────────────────────────────────────────────────


class FeSnmpError(Exception):
    """Raised for SNMP module validation or response issues."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> dict[str, Any]:
        """Convert to keyword args for module.fail_json()."""
        data: dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# ── Helper Functions ──────────────────────────────────────────────────────────


def _extract_error(payload: Any) -> dict[str, Any] | None:
    """Extract error information from a REST response.

    This is called after every API request to detect failures that the
    device reports inside the JSON body (rather than via HTTP status code).

    Args:
        payload: The parsed JSON response from the device.

    Returns:
        A dict with error details if an error was found, or None if the
        response is successful.
    """
    if not isinstance(payload, dict):
        return None
    # Check for error status codes (400+ means an error)
    # Coerce string codes to int (device may return "404" as a string)
    for key in ("errorCode", "statusCode", "code"):
        val = payload.get(key)
        if isinstance(val, str) and val.isdigit():
            val = int(val)
        if isinstance(val, int) and val >= 400:
            return {
                "code": val,
                "message": payload.get(
                    "errorMessage",
                    payload.get("message", "Unknown error"),
                ),
            }
    # Check for errors list
    if payload.get("errors"):
        return {
            "code": 400,
            "message": str(payload["errors"]),
        }
    return None


def _is_secret_key(key: Any) -> bool:
    """Return True when a payload key holds a secret value."""
    if not isinstance(key, str):
        return False
    sanitized = key.replace("-", "").replace("_", "").lower()
    return sanitized in SECRET_KEYS or sanitized.endswith("password")


def _redact_secrets(payload: Any) -> Any:
    """Return a copy of payload with every secret leaf removed (not masked).

    Non-secret siblings are kept, e.g. communityIsEncrypted and the
    isEncrypted flag of a password object.
    """
    if isinstance(payload, dict):
        redacted: dict[Any, Any] = {}
        for key, value in payload.items():
            if not _is_secret_key(key):
                redacted[key] = _redact_secrets(value)
                continue
            if isinstance(value, dict):
                flags = {
                    k: v
                    for k, v in value.items()
                    if isinstance(k, str) and k.lower() in SECRET_FLAG_KEYS and not isinstance(v, (dict, list))
                }
                if flags:
                    redacted[key] = flags
        return redacted
    if isinstance(payload, list):
        return [_redact_secrets(item) for item in payload]
    return payload


def _redact_api_response(response: Any) -> Any:
    """Prepare a device response for api_responses without any secret value.

    A parsed JSON body is redacted by _redact_secrets(). The httpapi plugin
    returns text only for a body it could not parse as JSON, which may still
    quote a secret, so a non-empty text body is replaced by a placeholder.
    """
    if isinstance(response, (str, bytes)) and response:
        return "(non-JSON response body omitted)"
    return _redact_secrets(response)


def _collect_secrets(payload: Any, secrets: set[str], inside_secret: bool = False) -> None:
    """Add every secret value of payload (a parsed GET body) to secrets.

    A value is secret under a key matched by _is_secret_key(), e.g. a community
    string or the value of an SNMPv3 password object (not its isEncrypted flag).
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if inside_secret and isinstance(key, str) and key.lower() in SECRET_FLAG_KEYS:
                continue
            _collect_secrets(value, secrets, inside_secret or _is_secret_key(key))
    elif isinstance(payload, list):
        for item in payload:
            _collect_secrets(item, secrets, inside_secret)
    elif inside_secret and isinstance(payload, str) and payload:
        secrets.add(payload)


def _scrub_text(text: str, secrets: set[str]) -> str:
    """Replace every secret value in text, raw, JSON-escaped or repr-escaped, longest first."""
    forms = set()
    for value in secrets:
        forms.update((value, json.dumps(value)[1:-1], json.dumps(value, ensure_ascii=False)[1:-1], repr(value)[1:-1]))
    for form in sorted(forms, key=len, reverse=True):
        text = text.replace(form, SECRET_MARKER)
    return text


def _is_status_value(key: Any, value: Any) -> bool:
    """True for a numeric status/error code, which is kept as is (a text value is scrubbed)."""
    if key not in STATUS_KEYS:
        return False
    if isinstance(value, int) and not isinstance(value, bool):
        return True
    return isinstance(value, str) and value.strip().isdigit()


def _map_strings(payload: Any, func: Any) -> Any:
    """Return a copy of payload with func applied to every string leaf (status fields excepted)."""
    if isinstance(payload, dict):
        return {
            key: value if _is_status_value(key, value) else _map_strings(value, func) for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_map_strings(item, func) for item in payload]
    if isinstance(payload, str):
        return func(payload)
    return payload


def _suppress_read_error_text(payload: Any, in_error: bool = False) -> Any:
    """Replace the free-text error fields and errors lists at any depth by the generic marker.

    Covers a top-level error dict, an error array and nested response wrappers
    alike; numeric status fields are kept (see _map_strings()). The SNMP
    schemas have no data field with these names. Bare text entries of an
    array are replaced only *in_error*: inside a responses/items wrapper or a
    read answer that is not an SNMP object (see _sanitize_response()). An array
    of strings in the configuration itself, such as view[].oids, is data.
    """
    if isinstance(payload, dict):
        return {
            key: (
                _map_strings(value, lambda text: READ_ERROR_MARKER)
                if key in FREE_TEXT_KEYS + ("errors",)
                else _suppress_read_error_text(value, in_error or key in ("responses", "items"))
            )
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [
            READ_ERROR_MARKER if in_error and isinstance(item, str) else _suppress_read_error_text(item, in_error)
            for item in payload
        ]
    return payload


def _sanitize_response(response: Any, secrets: set[str], *, is_read: bool) -> Any:
    """Return the copy of a response that may be stored or reported.

    The secret values of a GET body are first added to secrets. The copy has the
    secret fields removed and every collected secret value scrubbed from its texts.
    For a read, the free-text error fields and the texts of an errors list are
    replaced by a generic marker at any depth (in list entries and nested
    wrappers too), as they may quote a secret not known yet. So are a bare
    text answer, and the bare text entries of an array answer or of a
    responses/items wrapper (an array of strings inside the configuration,
    such as view[].oids, is data and kept).
    """
    if isinstance(response, (dict, list)):
        _collect_secrets(response, secrets)
    sanitized = _map_strings(_redact_api_response(response), lambda text: _scrub_text(text, secrets))
    if is_read:
        # The SNMP configuration is an object: a bare text answer, or an array
        # answer (["Invalid community: ..."]), is device text, never SNMP data.
        if isinstance(sanitized, str):
            sanitized = READ_ERROR_MARKER
        else:
            sanitized = _suppress_read_error_text(sanitized, in_error=isinstance(sanitized, list))
    return sanitized


def _status_field(code: Any) -> dict[str, int]:
    """{'status_code': <HTTP status>}, or {} when *code* is not an HTTP status (100-599)."""
    status = http_status(code)
    return {"status_code": status} if status is not None else {}


def _read_error_text(path: str, code: Any) -> str:
    """Generic text of a failed read; the device text could quote a secret."""
    status = f" (HTTP {http_status(code)})" if http_status(code) is not None else ""
    return f"Failed to read the SNMP configuration from {path}{status}"


def _get_connection(module: AnsibleModule) -> Connection:
    """Establish and return the httpapi connection to the device.

    Validates that module._socket_path is set (httpapi connection)
    before constructing the Connection object.
    """
    if not getattr(module, "_socket_path", None):
        raise FeSnmpError(
            "Connection type httpapi is required for this module",
            details={"socket_path": getattr(module, "_socket_path", None)},
        )
    return Connection(module._socket_path)


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: dict[str, Any],
    response_key: str,
    secrets: set[str],
    payload: Any | None = None,
    expect_content: bool = True,
    changed: bool = False,
) -> Any:
    """Send a single REST API request to the device.

    Args:
        module:          The AnsibleModule instance.
        connection:      The device Connection object.
        method:          HTTP method (GET, PATCH, etc.).
        path:            REST API path.
        api_responses:   Dict to store raw responses for debugging.
        response_key:    Key name under which to store this response.
        secrets:         Secret values read from the device in this task; a GET adds
                         those of its body. They are scrubbed from every reported text.
        payload:         Request body data (for PATCH), or None for GET.
        expect_content:  If True, treat empty responses as empty dicts.
        changed:         Whether the task already changed the device (a re-read after
                         the PATCH): a failure then reports changed=true.

    Returns:
        The parsed response (dict, string, or None).
    """
    is_read = method == "GET"
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        # The exception text and .err can quote the device's response. A read
        # reports a generic text; a write (PATCH, which only ever sends 'name')
        # keeps the device text scrubbed of every secret value read earlier.
        code = getattr(exc, "code", None)
        # Only an HTTP status: a lost answer's JSON-RPC code or REQUEST_NOT_SENT is not one.
        status = _status_field(code)
        details: dict[str, Any] = dict(status)
        if is_read:
            msg = _read_error_text(path, code)
            api_responses[response_key] = dict(status, error=msg)
        else:
            msg = _scrub_text(to_text(exc), secrets)
            if is_answer_unknown_code(code):
                # No answer (a lost connection): the PATCH may have been applied.
                msg += ". The %s %s may have been applied before the answer was lost; check the system name." % (
                    method,
                    path,
                )
                details["outcome"] = "unknown"
                changed = True
        details["message"] = msg
        module.fail_json(
            msg=msg,
            code=code,
            details=details,
            api_responses=api_responses,
            changed=changed,
        )

    # Ensure response is a string if it came back as bytes
    if isinstance(response, bytes):
        response = to_text(response)

    # Store the response for debugging, without any secret value
    sanitized = _sanitize_response(response, secrets, is_read=is_read)
    api_responses[response_key] = sanitized

    # Handle empty responses (common for PATCH returning 204)
    if response in (None, ""):
        return None if not expect_content else {}

    # Check for application-level errors, on the sanitized copy only
    if isinstance(response, dict):
        error = _extract_error(sanitized)
        if error:
            if is_read:
                error = {"code": error.get("code"), "message": _read_error_text(path, error.get("code"))}
            module.fail_json(
                msg=error.get("message"),
                details=error,
                api_responses=api_responses,
                changed=changed,
            )

    return response


# ── Data-Fetching Functions ───────────────────────────────────────────────────


def _fetch_snmp_config(
    module: AnsibleModule,
    connection: Connection,
    api_responses: dict[str, Any],
    response_key: str,
    secrets: set[str],
    changed: bool = False,
) -> dict[str, Any]:
    """Fetch the SNMP configuration from the device.

    *changed* is True for the re-read after a PATCH: a failed read then
    reports changed=true, as the PATCH already changed the device.

    Tries GET /v1/configuration/snmp first, falls back to /v0 if v1
    returns no data or 404 (matching the facts module fallback pattern).
    The secret values of every body read are added to secrets, and a failed
    read is reported generically (see _call_api).
    """
    last_idx = len(SNMP_GET_PATHS) - 1
    for i, path in enumerate(SNMP_GET_PATHS):
        # Store each attempt under a distinct key (e.g. get_snmp_v1, get_snmp_v0)
        version = path.split("/")[1]  # "v1" or "v0"
        attempt_key = f"{response_key}_{version}"

        if i < last_idx:
            # Non-last path: treat 404 as non-fatal, fall through to next
            try:
                raw = connection.send_request(None, path=path, method="GET")
            except ConnectionError as exc:
                # Only continue to next path if error code is 404. The exception
                # text and .err can quote the device's response: generic text only.
                code = getattr(exc, "code", None)
                msg = _read_error_text(path, code)
                api_responses[attempt_key] = dict(_status_field(code), error=msg)
                if code == 404:
                    continue
                else:
                    # For any other error, fail immediately
                    module.fail_json(
                        msg=msg,
                        code=code,
                        details=dict(_status_field(code), message=msg),
                        api_responses=api_responses,
                        changed=changed,
                    )
            api_responses[attempt_key] = _sanitize_response(raw, secrets, is_read=True)
            if isinstance(raw, dict):
                # Fall back when v1 returns an application-level not-found payload.
                error = _extract_error(api_responses[attempt_key])
                if error:
                    if error.get("code") == 404:
                        continue
                    msg = _read_error_text(path, error.get("code"))
                    module.fail_json(
                        msg=msg,
                        details={"code": error.get("code"), "message": msg},
                        api_responses=api_responses,
                        changed=changed,
                    )
                if raw:
                    return raw
        else:
            # Last path: use _call_api (fail on error)
            raw = _call_api(
                module,
                connection,
                method="GET",
                path=path,
                api_responses=api_responses,
                response_key=attempt_key,
                secrets=secrets,
                changed=changed,
            )
            if isinstance(raw, dict) and raw:
                return raw
    return {}


# ── Output Formatter ──────────────────────────────────────────────────────────


def _normalize_name(raw_name: Any) -> str:
    """Normalize the system name from the REST API.

    Fabric Engine returns the literal string "none" or null when no system name
    is configured. This function normalizes both to "" (the value that clears
    the name), so a gathered result can be applied back with merged.
    A non-empty, non-"none" string is returned as-is.
    """
    if raw_name is None:
        return ""
    if isinstance(raw_name, str) and raw_name.lower() in ("", "none"):
        return ""
    return raw_name


def _to_ansible_output(snmp_data: dict[str, Any]) -> dict[str, Any]:
    """Convert REST SNMP response to Ansible output format.

    Extracts only the 'name' field from the full SNMP settings.

    Args:
        snmp_data: The raw SnmpGetSettingsV1 dict from the REST API.

    Returns:
        A dict with 'name' (str, "" when no system name is set).
    """
    return {
        "name": _normalize_name(snmp_data.get("name")),
    }


# ── Diff / Comparison ─────────────────────────────────────────────────────────


def _compute_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compute the differences between before and after states.

    Returns a dict of fields that changed with their old and new values.
    """
    diff: dict[str, Any] = {}
    for key in ("name",):
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            diff[key] = {"before": old_val, "after": new_val}
    return diff


def _exit_action(module: AnsibleModule, result: dict[str, Any], before: dict[str, Any], after: dict[str, Any]) -> None:
    """Exit an action state with before, after and differences, and the diff in --diff mode."""
    result["snmp"] = {"before": before, "after": after, "differences": _compute_diff(before, after)}
    result["before"] = before
    result["after"] = after
    if module._diff:
        result["diff"] = {"before": before, "after": after}
    module.exit_json(**result)


# ── Main Entry Point ──────────────────────────────────────────────────────────


def run_module() -> None:
    """Main module entry point — state dispatch and execution."""
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    # Establish connection to the device
    try:
        connection = _get_connection(module)
    except FeSnmpError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    # Get module parameters
    state = module.params["state"]
    config = module.params.get("config") or {}

    # Validate: merged/replaced/overridden require config
    if state in REQUIRES_CONFIG and not config:
        module.fail_json(msg=f"value of config parameter must not be empty for state {state}")

    # Initialize result structure
    result: dict[str, Any] = {
        "changed": False,
        "api_responses": {},
    }
    # Secret values of every SNMP body read in this task, scrubbed from every reported text
    secrets: set[str] = set()

    # Fetch current SNMP config from the device
    current_raw = _fetch_snmp_config(module, connection, result["api_responses"], "configuration_before", secrets)
    current = _to_ansible_output(current_raw)

    # ── GATHERED — read-only, just return current config ─────────
    if state == STATE_GATHERED:
        result["snmp"] = {"config": current}
        result["gathered"] = current
        module.exit_json(**result)
        return

    # ── MERGED / REPLACED / OVERRIDDEN ───────────────────────────
    # For this single-field singleton, all three behave identically:
    # set the system name to the desired value.
    #
    # Why are they identical? Because there's only ONE writable field.
    # - merged: "set what the user specified" → set name
    # - replaced: "set specified + reset omitted to defaults" → only name exists, so same
    # - overridden: "enforce entire config" → only name exists, so same
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
        desired_name = config.get("name")

        if desired_name is None:
            # config provided but 'name' key is missing — fail with a clear
            # message so playbook mistakes are easy to detect.
            module.fail_json(
                msg=f"value of config parameter must not be empty for state {state} (set config.name; use an empty string "
                "to clear the system name)",
            )
            return

        if len(desired_name) > 255:
            module.fail_json(
                msg=f"config.name must be 0-255 characters, got {len(desired_name)}",
            )
            return

        current_name = current.get("name")

        # Normalize for comparison: "" and "none" both mean no system name
        normalized_desired = _normalize_name(desired_name)
        if normalized_desired == current_name:
            # No change needed — idempotent
            _exit_action(module, result, current, current)
            return

        # Change needed
        result["changed"] = True

        if not module.check_mode:
            # PATCH the system name
            patch_payload = {"name": desired_name}
            _call_api(
                module,
                connection,
                method="PATCH",
                path=SNMP_PATCH_PATH,
                payload=patch_payload,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key="patch",
                secrets=secrets,
            )
            # Re-read to get actual after state
            after_raw = _fetch_snmp_config(
                module,
                connection,
                result["api_responses"],
                "configuration_after",
                secrets,
                changed=True,
            )
            after = _to_ansible_output(after_raw)
        else:
            # Check mode — predict after state
            after = {"name": normalized_desired}

        _exit_action(module, result, current, after)
        return

    # ── DELETED — reset system name to empty/none ─────────────────
    # Deleted clears the system name by sending an empty string ("") to
    # the REST API. Fabric Engine stores this as "none" internally.
    # The module normalizes the result to "" in output.
    if state == STATE_DELETED:
        current_name = current.get("name")
        default_name = DEFAULTS["name"]  # "" (normalized factory default)

        if current_name == default_name:
            # Already at factory default — nothing to do
            _exit_action(module, result, current, current)
            return

        # Need to clear the system name
        result["changed"] = True

        if not module.check_mode:
            # Send empty string to REST API to clear the name
            # (Fabric Engine stores it as "none"/null internally)
            patch_payload = {"name": ""}
            _call_api(
                module,
                connection,
                method="PATCH",
                path=SNMP_PATCH_PATH,
                payload=patch_payload,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key="patch_delete",
                secrets=secrets,
            )
            # Re-read to get actual after state
            after_raw = _fetch_snmp_config(
                module,
                connection,
                result["api_responses"],
                "configuration_after",
                secrets,
                changed=True,
            )
            after = _to_ansible_output(after_raw)
        else:
            # Check mode — predict after state (cleared = "")
            after = {"name": DEFAULTS["name"]}

        _exit_action(module, result, current, after)
        return


def main() -> None:
    """Module entry point called by Ansible."""
    run_module()


if __name__ == "__main__":
    main()
