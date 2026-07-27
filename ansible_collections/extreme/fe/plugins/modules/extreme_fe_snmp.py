# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ansible module to manage the SNMP system name on Extreme Fabric Engine switches.

Module Architecture Overview
============================
This module manages the SNMP system name (sysName) on Extreme
Fabric Engine (VOSS) switches via the REST OpenAPI.

REST Endpoints used:
  GET   /v1/configuration/snmp
        → Retrieve SNMP settings (we extract only the 'name' field)
  PATCH /v0/configuration/snmp
        → Update SNMP common settings (we send only the 'name' field)

VOSS constraints:
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

# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any, Dict, Optional

# AnsibleModule — the core class every Ansible module must instantiate;
# it handles argument parsing, check mode, exit/fail, etc.
from ansible.module_utils.basic import AnsibleModule
# Connection — communicates with the device through the httpapi plugin;
# ConnectionError — raised when the device is unreachable or returns a transport error
from ansible.module_utils.connection import Connection, ConnectionError
# to_text — safely converts bytes/strings to unicode text
from ansible.module_utils.common.text.converters import to_text

# ── Module Documentation ──────────────────────────────────────────────────────

DOCUMENTATION = r"""
---
module: extreme_fe_snmp
short_description: Manage SNMP system name on Extreme Fabric Engine switches
description:
  - This module manages the SNMP system name (sysName) on Extreme
    Fabric Engine (VOSS) switches using the REST API.
  - Supports all five Ansible resource module states.
version_added: "1.2.0"
author:
  - Extreme Networks
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
  - This module targets Fabric Engine (VOSS) only.
  - Uses GET /v1/configuration/snmp to read the current system name,
    falling back to GET /v0/configuration/snmp if v1 returns no data.
  - Uses PATCH /v0/configuration/snmp to update the system name.
  - The system name is a singleton resource (one per device).
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
    - SNMP configuration after changes.
    - Only returned when the module made changes.
  returned: when changed
  type: dict
gathered:
  description:
    - Current SNMP configuration gathered from the device.
    - Returned only for C(state=gathered).
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
  description: Raw API responses captured from the device for debugging.
  returned: always
  type: dict
"""


# ── Constants ─────────────────────────────────────────────────────────────────

# REST endpoints for reading SNMP settings — try v1 first, fall back to v0
# (some older VOSS firmware versions only expose the v0 endpoint)
SNMP_GET_PATHS = ["/v1/configuration/snmp", "/v0/configuration/snmp"]

# REST endpoint for updating SNMP common settings (v0 for PATCH)
SNMP_PATCH_PATH = "/v0/configuration/snmp"

# Ansible parameter → REST API field name mapping
# (name maps directly — same key in both Ansible and REST API)

# Factory defaults — what a clean VOSS device looks like
# When system name is cleared, VOSS returns "none" (the string) or null.
# We normalize both to None in Ansible output.
DEFAULTS = {
    "name": None,
}

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
            # VOSS supports 0-255 characters
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

    def __init__(
        self, message: str, *, details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        """Convert to keyword args for module.fail_json()."""
        data: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# ── Helper Functions ──────────────────────────────────────────────────────────


def _extract_error(payload: Any) -> Optional[Dict[str, Any]]:
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
    if "errors" in payload and payload["errors"]:
        return {
            "code": 400,
            "message": str(payload["errors"]),
        }
    return None


def _get_connection(module: AnsibleModule) -> Connection:
    """Establish and return the httpapi connection to the device.

    Validates that module._socket_path is set (httpapi connection)
    before constructing the Connection object.
    """
    if not getattr(module, "_socket_path", None):
        raise FeSnmpError(
            "Could not establish connection to device — "
            "no socket path (is ansible_connection=httpapi set?)",
            details={"socket_path": getattr(module, "_socket_path", None)},
        )
    return Connection(module._socket_path)


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: Dict[str, Any],
    response_key: str,
    payload: Optional[Any] = None,
    expect_content: bool = True,
) -> Any:
    """Send a single REST API request to the device.

    Args:
        module:          The AnsibleModule instance.
        connection:      The device Connection object.
        method:          HTTP method (GET, PATCH, etc.).
        path:            REST API path.
        api_responses:   Dict to store raw responses for debugging.
        response_key:    Key name under which to store this response.
        payload:         Request body data (for PATCH), or None for GET.
        expect_content:  If True, treat empty responses as empty dicts.

    Returns:
        The parsed response (dict, string, or None).
    """
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=api_responses,
        )

    # Ensure response is a string if it came back as bytes
    if isinstance(response, bytes):
        response = to_text(response)

    # Store raw response for debugging
    api_responses[response_key] = response

    # Handle empty responses (common for PATCH returning 204)
    if response in (None, ""):
        return None if not expect_content else {}

    # Check for application-level errors
    if isinstance(response, dict):
        error = _extract_error(response)
        if error:
            module.fail_json(
                msg=error.get("message"),
                details=error,
                api_responses=api_responses,
            )

    return response


# ── Data-Fetching Functions ───────────────────────────────────────────────────


def _fetch_snmp_config(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
    response_key: str,
) -> Dict[str, Any]:
    """Fetch the SNMP configuration from the device.

    Tries GET /v1/configuration/snmp first, falls back to /v0 if v1
    returns no data or 404 (matching the facts module fallback pattern).
    """
    last_idx = len(SNMP_GET_PATHS) - 1
    for i, path in enumerate(SNMP_GET_PATHS):
        # Store each attempt under a distinct key (e.g. get_snmp_v1, get_snmp_v0)
        version = path.split("/")[1]  # "v1" or "v0"
        attempt_key = f"{response_key}_{version}"

        if i < last_idx:
            # Non-last path: treat 404 as non-fatal, fall through to next
            try:
                raw = connection.send_request(
                    None, path=path, method="GET"
                )
            except ConnectionError as exc:
                # Only continue to next path if error code is 404
                code = getattr(exc, "code", None)
                api_responses[attempt_key] = {
                    "error": to_text(exc),
                    "code": code,
                }
                if code == 404:
                    continue
                else:
                    # For any other error, fail immediately
                    module.fail_json(
                        msg=to_text(exc),
                        code=code,
                        err=getattr(exc, "err", None),
                        api_responses=api_responses,
                    )
            api_responses[attempt_key] = raw
            if isinstance(raw, dict):
                # Fall back when v1 returns an application-level not-found payload.
                error = _extract_error(raw)
                if error:
                    if error.get("code") == 404:
                        continue
                    module.fail_json(
                        msg=error.get("message"),
                        details=error,
                        api_responses=api_responses,
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
            )
            if isinstance(raw, dict) and raw:
                return raw
    return {}


# ── Output Formatter ──────────────────────────────────────────────────────────


def _normalize_name(raw_name: Any) -> Optional[str]:
    """Normalize the system name from the REST API.

    VOSS returns the literal string "none" or null when no system name
    is configured. This function normalizes both to Python None.
    A non-empty, non-"none" string is returned as-is.
    """
    if raw_name is None:
        return None
    if isinstance(raw_name, str) and raw_name.lower() in ("", "none"):
        return None
    return raw_name


def _to_ansible_output(snmp_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert REST SNMP response to Ansible output format.

    Extracts only the 'name' field from the full SNMP settings.

    Args:
        snmp_data: The raw SnmpGetSettingsV1 dict from the REST API.

    Returns:
        A dict with 'name' (str or None).
    """
    return {
        "name": _normalize_name(snmp_data.get("name")),
    }


# ── Diff / Comparison ─────────────────────────────────────────────────────────


def _compute_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the differences between before and after states.

    Returns a dict of fields that changed with their old and new values.
    """
    diff: Dict[str, Any] = {}
    for key in ("name",):
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            diff[key] = {"before": old_val, "after": new_val}
    return diff


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
        module.fail_json(msg="'config' is required when state is '{0}'".format(state))

    # Initialize result structure
    result: Dict[str, Any] = {
        "changed": False,
        "api_responses": {},
    }

    # Fetch current SNMP config from the device
    current_raw = _fetch_snmp_config(
        module, connection, result["api_responses"], "configuration_before"
    )
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
                msg="config.name is required for state={0}. "
                    "Use an empty string to clear the system name.".format(state),
            )
            return

        if len(desired_name) > 255:
            module.fail_json(
                msg="config.name must be 0-255 characters, got {0}".format(
                    len(desired_name)
                ),
            )
            return

        current_name = current.get("name")

        # Normalize for comparison: treat empty string as "clear" (None)
        normalized_desired = _normalize_name(desired_name)
        if normalized_desired == current_name:
            # No change needed — idempotent
            result["snmp"] = {
                "before": current,
                "after": current,
                "differences": {},
            }
            result["before"] = current
            module.exit_json(**result)
            return

        # Change needed
        result["changed"] = True
        result["snmp"] = {"before": current}

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
            )
            # Re-read to get actual after state
            after_raw = _fetch_snmp_config(
                module,
                connection,
                result["api_responses"],
                "configuration_after",
            )
            result["snmp"]["after"] = _to_ansible_output(after_raw)
        else:
            # Check mode — predict after state
            result["snmp"]["after"] = {"name": normalized_desired}

        result["snmp"]["differences"] = _compute_diff(current, result["snmp"]["after"])
        result["before"] = current
        result["after"] = result["snmp"]["after"]
        module.exit_json(**result)
        return

    # ── DELETED — reset system name to empty/none ─────────────────
    # Deleted clears the system name by sending an empty string ("") to
    # the REST API. VOSS stores this as "none" internally.
    # The module normalizes the result to Python None in output.
    if state == STATE_DELETED:
        current_name = current.get("name")
        default_name = DEFAULTS["name"]  # None (normalized factory default)

        if current_name == default_name:
            # Already at factory default — nothing to do
            result["snmp"] = {
                "before": current,
                "after": current,
                "differences": {},
            }
            result["before"] = current
            module.exit_json(**result)
            return

        # Need to clear the system name
        result["changed"] = True
        result["snmp"] = {"before": current}

        if not module.check_mode:
            # Send empty string to REST API to clear the name
            # (VOSS stores it as "none"/null internally)
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
            )
            # Re-read to get actual after state
            after_raw = _fetch_snmp_config(
                module,
                connection,
                result["api_responses"],
                "configuration_after",
            )
            result["snmp"]["after"] = _to_ansible_output(after_raw)
        else:
            # Check mode — predict after state (cleared = None)
            result["snmp"]["after"] = {"name": None}

        result["snmp"]["differences"] = _compute_diff(current, result["snmp"]["after"])
        result["before"] = current
        result["after"] = result["snmp"]["after"]
        module.exit_json(**result)
        return


def main() -> None:
    """Module entry point called by Ansible."""
    run_module()


if __name__ == "__main__":
    main()
