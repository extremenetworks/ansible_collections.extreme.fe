# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Ansible module to manage VRFs on Extreme Fabric Engine (VOSS) switches.

REST API endpoints used:
  GET    /v0/configuration/vrf              — list all VRFs
  POST   /v0/configuration/vrf              — create a new VRF
  GET    /v0/configuration/vrf/{vr_name}    — get a single VRF by name
  PATCH  /v0/configuration/vrf/{vr_name}    — update VRF settings (ipRoutingEnabled)
  DELETE /v0/configuration/vrf/{vr_name}    — delete a VRF

Writable fields:
  name              — VRF name (string, 1-32 chars, identifier/required)
  ipRoutingEnabled  — enable/disable IP routing on this VRF (boolean, VOSS only)

Read-only fields returned in output:
  id, isMgmt, dynamic, vr_type, port_list, dynamic_port_list, vlan_id_list
"""

from __future__ import annotations

# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any, Dict, List, Optional
# quote() is used to safely encode characters in REST URL path segments
from urllib.parse import quote

# AnsibleModule — the core class every Ansible module must instantiate;
# it handles argument parsing, check mode, exit/fail, etc.
from ansible.module_utils.basic import AnsibleModule
# Connection — communicates with the device through the httpapi plugin;
# ConnectionError — raised when the device is unreachable or returns a transport error
from ansible.module_utils.connection import Connection, ConnectionError
# to_text — safely converts bytes/strings to unicode text
from ansible.module_utils.common.text.converters import to_text
# Shared VRF name normalization logic
from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_vrf_utils import (
    normalize_vrf_name,
)

# ── Ansible module metadata ──────────────────────────────────────────────────

DOCUMENTATION = r"""
module: extreme_fe_vrf
short_description: Manage VRFs on Extreme Fabric Engine switches
version_added: "1.2.0"
description:
  - Create, update, delete, and query Virtual Routing and Forwarding (VRF)
    instances on Extreme Fabric Engine (VOSS) switches via the REST API.
  - Supports all five Ansible resource module states.
  - Each VRF is identified by its C(name) (1-32 characters).
  - The only writable configuration field is C(ip_routing_enabled).
author:
  - Extreme Networks
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI
    connection plugin.
  - The C(GlobalRouter) VRF always exists on the device and cannot be deleted.
  - VRFs of type VR are not supported on VOSS (only VRF type is valid).
  - Port associations are read-only in this module; use brouter interfaces to
    associate ports with VRFs.
requirements:
  - ansible.netcommon
options:
  state:
    description:
      - Desired VRF operation state.
      - C(merged) creates VRFs that do not exist and updates settings on existing
        VRFs without removing unlisted VRFs.
      - C(replaced) makes the provided settings authoritative for each listed
        VRF. Omitted writable fields are reset to factory defaults.
      - C(overridden) enforces the exact set of VRFs — unlisted user VRFs are
        deleted, listed VRFs are created or updated to match config.
      - C(deleted) removes the specified VRFs. If C(config) is omitted, all
        user-created VRFs are deleted.
      - C(gathered) returns current VRF information without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - List of VRF configurations to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional for C(deleted) (omit to delete all user VRFs) and C(gathered).
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - VRF name (1-16 characters). This is the resource identifier.
          - The OpenAPI spec defines maxLength 32, but the device firmware
            enforces a 16-character limit.
        type: str
        required: true
      ip_routing_enabled:
        description:
          - Enable or disable IP routing on this VRF.
          - Applicable to Fabric Engine (VOSS) only.
        type: bool
  gather_filter:
    description:
      - Limit gathered VRF facts to these VRF names.
    type: list
    elements: str
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
# Task 1: Gather VRF configuration
# -------------------------------------------------------------------------
# - name: "Task 1: Gather VRF configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather current VRF configuration
  extreme.fe.extreme_fe_vrf:
    state: gathered

# -------------------------------------------------------------------------
# Task 2: Create or replace VRFs
# -------------------------------------------------------------------------
# - name: "Task 2: Create or replace VRFs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Create VRF with routing
  extreme.fe.extreme_fe_vrf:
    state: merged
    config:
      - name: customer-a
        ip_routing_enabled: true

- name: Replace VRF config
  extreme.fe.extreme_fe_vrf:
    state: replaced
    config:
      - name: customer-a

# -------------------------------------------------------------------------
# Task 3: Override and delete VRFs
# -------------------------------------------------------------------------
# - name: "Task 3: Override and delete VRFs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Override all VRFs
  extreme.fe.extreme_fe_vrf:
    state: overridden
    config:
      - name: customer-a
        ip_routing_enabled: true
      - name: customer-b
        ip_routing_enabled: false

- name: Delete VRFs
  extreme.fe.extreme_fe_vrf:
    state: deleted
    config:
      - name: customer-a
      - name: customer-b

- name: Delete all user-created VRFs
  extreme.fe.extreme_fe_vrf:
    state: deleted
"""

RETURN = r"""
before:
  description:
    - Full VRF resource configuration before changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
after:
  description:
    - Full VRF resource configuration after changes.
    - Only returned when the module made changes.
  returned: when changed
  type: list
  elements: dict
gathered:
  description:
    - VRF configuration gathered from the device.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
vrfs:
  description: Per-resource VRF operation results with differences.
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: VRF name (resource identifier).
      type: str
    config:
      description: VRF configuration (returned by C(gathered) state).
      type: dict
      returned: when state is gathered
    before:
      description: VRF configuration before the operation.
      type: dict
      returned: when state is not gathered
    after:
      description: VRF configuration after the operation.
      type: dict
      returned: when state is not gathered
    changed:
      description: Whether this VRF was modified.
      type: bool
      returned: when state is not gathered
    differences:
      description: Fields that changed between before and after states.
      type: dict
      returned: when state is not gathered
api_responses:
  description: Raw REST API responses for debugging.
  returned: always
  type: dict
changed:
  description: Whether any VRF was modified.
  returned: always
  type: bool
"""

# ── Constants ─────────────────────────────────────────────────────────────────

# REST endpoint for the VRF collection
VRF_LIST_PATH = "/v0/configuration/vrf"

# REST endpoint template for a single VRF (by name)
VRF_SINGLE_PATH = "/v0/configuration/vrf/{vr_name}"

# Ansible parameter → REST API field name mapping
FIELD_MAP = {
    "name": "name",  # VRF name (identifier, 1-32 chars)
    "ip_routing_enabled": "ipRoutingEnabled",  # Enable IP routing (VOSS only)
}

# Reverse map: REST → Ansible field names
FIELD_MAP_REV = {v: k for k, v in FIELD_MAP.items()}

# Factory defaults for writable fields — used by replaced/overridden/deleted
# The OpenAPI spec has no explicit default for ipRoutingEnabled.
# On VOSS, newly created VRFs have IP routing enabled by default
# (confirmed by creating a VRF via REST without ipRoutingEnabled and
# reading back the resource — the device returns ipRoutingEnabled: true).
FULL_DEFAULTS: Dict[str, Any] = {
    "ip_routing_enabled": True,  # IP routing enabled at factory default
}

# System VRFs that cannot be deleted (always present on VOSS)
# Stored lowercase to match normalized VRF name lookups.
SYSTEM_VRFS = {"globalrouter", "mgmtrouter"}

# Re-export for backward compatibility; actual logic is in module_utils.
_normalize_vrf_name = normalize_vrf_name

# State constants
STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# ── Argument spec ─────────────────────────────────────────────────────────────

ARGUMENT_SPEC: Dict[str, Any] = {
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "ip_routing_enabled": {"type": "bool"},
        },
    },
    "state": {
        "type": "str",
        "choices": [
            STATE_MERGED,
            STATE_REPLACED,
            STATE_OVERRIDDEN,
            STATE_DELETED,
            STATE_GATHERED,
        ],
        "default": STATE_MERGED,
    },
    "gather_filter": {"type": "list", "elements": "str"},
}

# ── Custom exception ─────────────────────────────────────────────────────────


class FeVrfError(Exception):
    """Custom exception for VRF module errors."""

    def __init__(
        self, message: str, *, details: Optional[Dict[str, object]] = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, object]:
        data: Dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# ── Helper functions ──────────────────────────────────────────────────────────
# These utility functions handle common tasks: detecting errors in REST
# responses, establishing the device connection, and sending API requests.


def _is_not_found_response(payload: Any) -> bool:
    """Check if REST response indicates a 'not found' condition."""
    if payload is None:
        return True
    if isinstance(payload, dict):
        # Check for error status codes
        status = payload.get("status") or payload.get("httpStatusCode")
        if status and int(status) == 404:
            return True
        # Check for error messages indicating not found
        errors = payload.get("errors") or payload.get("error")
        if errors:
            err_str = str(errors).lower()
            if "not found" in err_str or "does not exist" in err_str:
                return True
    return False


def _extract_error(payload: Any) -> Optional[str]:
    """Extract error message from REST response, if present."""
    if not isinstance(payload, dict):
        return None
    # Check HTTP status code
    status = payload.get("status") or payload.get("httpStatusCode")
    if status and int(status) >= 400:
        msg = payload.get("message") or payload.get("msg") or str(payload)
        return f"HTTP {status}: {msg}"
    # Check for errors list
    errors = payload.get("errors")
    if errors:
        return str(errors)
    return None


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    payload: Any = None,
    expect_content: bool = True,
    api_responses: Dict[str, Any],
    response_key: str,
) -> Any:
    """
    Send a REST API request and record the response.

    Parameters:
        module:         AnsibleModule instance (for fail_json on error)
        connection:     HTTPAPI Connection object
        method:         HTTP method (GET, POST, PATCH, DELETE)
        path:           REST API path
        payload:        Request body (dict for JSON, None for no body)
        expect_content: Whether to expect a response body
        api_responses:  Dict to store raw API responses for debugging
        response_key:   Key name to store this response under
    Returns:
        Parsed response payload, or None if no content expected
    """
    try:
        raw = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        module.fail_json(
            msg=f"REST API call failed: {method} {path}: {to_text(exc)}",
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=api_responses,
        )

    # Parse response body — send_request returns already-parsed JSON
    # which can be a dict, list, str, or None
    parsed = None
    if raw is not None:
        if isinstance(raw, (dict, list)):
            parsed = raw
        elif isinstance(raw, str):
            import json as _json

            try:
                parsed = _json.loads(raw)
            except (ValueError, TypeError):
                parsed = raw

    api_responses[response_key] = {
        "method": method,
        "path": path,
        "body": parsed,
    }

    # Check for errors
    if expect_content and parsed is not None:
        err = _extract_error(parsed)
        if err:
            raise FeVrfError(
                f"{method} {path} returned an error: {err}",
                details={"response": parsed},
            )

    return parsed


# ── Data-fetching functions ───────────────────────────────────────────────────
# These functions retrieve the current configuration from the device via
# REST GET requests and normalize the response into Python data structures.


def _fetch_all_vrfs(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
    response_key: str = "get_all_vrfs",
) -> List[Dict[str, Any]]:
    """
    GET /v0/configuration/vrf — retrieve all VRFs from the device.

    Returns a list of VRF dicts as returned by the REST API.
    """
    data = _call_api(
        module,
        connection,
        method="GET",
        path=VRF_LIST_PATH,
        expect_content=True,
        api_responses=api_responses,
        response_key=response_key,
    )

    if data is None or _is_not_found_response(data):
        return []

    # The response is a JSON array of VRF objects
    if isinstance(data, list):
        return data

    # Some responses wrap the list in a dict
    if isinstance(data, dict):
        for key in ("vrfs", "vrf", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]

    return []


def _fetch_single_vrf(
    module: AnsibleModule,
    connection: Connection,
    vrf_name: str,
    api_responses: Dict[str, Any],
    response_key: str = "get_vrf",
) -> Optional[Dict[str, Any]]:
    """
    GET /v0/configuration/vrf/{vr_name} — retrieve a single VRF by name.

    Returns the VRF dict or None if not found.
    """
    path = VRF_SINGLE_PATH.format(vr_name=quote(vrf_name, safe=""))
    data = _call_api(
        module,
        connection,
        method="GET",
        path=path,
        expect_content=True,
        api_responses=api_responses,
        response_key=response_key,
    )

    if data is None or _is_not_found_response(data):
        return None

    return data


# ── Output formatter ───────────────────────────────────────────────────────
# Converts raw REST API responses (device field names) into Ansible-friendly
# output format (snake_case field names matching the module's argument spec).


def _to_ansible_output(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single REST API VRF dict to Ansible output format.

    Maps REST field names to Ansible parameter names and includes
    read-only fields for informational output.
    """
    result: Dict[str, Any] = {}

    # Writable fields (REST → Ansible)
    result["name"] = raw.get("name")
    result["ip_routing_enabled"] = raw.get("ipRoutingEnabled")

    # Read-only fields (informational)
    result["id"] = raw.get("id")
    result["is_mgmt"] = raw.get("isMgmt")
    result["dynamic"] = raw.get("dynamic")
    result["vr_type"] = raw.get("vrType")
    result["port_list"] = raw.get("portList", [])
    result["dynamic_port_list"] = raw.get("dynamicPortList", [])
    result["vlan_id_list"] = raw.get("vlanIdList", [])

    return result


def _to_ansible_list(raw_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert a list of REST VRF dicts to Ansible output format."""
    return [_to_ansible_output(r) for r in raw_list]


# ── Diff / comparison logic ──────────────────────────────────────────────────
# Compares the "before" (current device state) with the "after" (desired state)
# to determine what changes need to be made. This drives idempotency — if
# before == after, no API calls are needed.


def _compute_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare before and after VRF dicts, returning fields that differ.

    Only compares writable fields (ip_routing_enabled). The identifier
    field (name) is excluded — it is already reported separately.
    """
    diff: Dict[str, Any] = {}
    for ansible_field in FIELD_MAP:
        if ansible_field == "name":
            continue
        val_before = before.get(ansible_field)
        val_after = after.get(ansible_field)
        if val_before != val_after:
            diff[ansible_field] = {"before": val_before, "after": val_after}
    return diff


def _is_user_vrf(vrf: Dict[str, Any]) -> bool:
    """
    Check if a VRF is user-created (not a system VRF).

    System VRFs (globalrouter, mgmtrouter) cannot be deleted.
    """
    name = vrf.get("name", "").lower()
    if name in SYSTEM_VRFS:
        return False
    # Dynamic VRFs (created by protocols) should not be managed
    if vrf.get("dynamic") or vrf.get("is_mgmt"):
        return False
    return True


# ── Payload builders ───────────────────────────────────────────────────────
# These functions convert Ansible parameters into the JSON payloads expected
# by the device REST API (POST for create, PATCH for update).


def _build_create_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a POST payload for creating a new VRF.

    The REST API expects: {name: str, vrType: "VRF", ipRoutingEnabled: bool}
    """
    payload: Dict[str, Any] = {
        "name": entry["name"],
        "vrType": "VRF",  # VOSS only supports VRF type (not VR)
    }

    # Only include ipRoutingEnabled if explicitly specified
    if entry.get("ip_routing_enabled") is not None:
        payload["ipRoutingEnabled"] = entry["ip_routing_enabled"]

    return payload


def _build_patch_payload(
    desired: Dict[str, Any],
    current: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Build a PATCH payload for updating an existing VRF.

    Only includes fields that differ from current state.
    Returns None if no changes are needed.
    """
    patch: Dict[str, Any] = {}

    # Only writable field: ipRoutingEnabled
    desired_routing = desired.get("ip_routing_enabled")
    if desired_routing is not None:
        current_routing = current.get("ip_routing_enabled")
        if desired_routing != current_routing:
            patch["ipRoutingEnabled"] = desired_routing

    if not patch:
        return None
    return patch


def _build_replaced_payload(
    desired: Dict[str, Any],
    current: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Build a PATCH payload for replaced state.

    Includes ALL writable fields — user-supplied values for specified fields,
    FULL_DEFAULTS for omitted fields. Returns None if no changes needed.
    """
    # Build complete desired state: user values + defaults for omitted
    complete: Dict[str, Any] = {}
    for field, default_val in FULL_DEFAULTS.items():
        user_val = desired.get(field)
        complete[field] = user_val if user_val is not None else default_val

    # Compare with current and build PATCH payload
    patch: Dict[str, Any] = {}
    for ansible_field, value in complete.items():
        rest_field = FIELD_MAP[ansible_field]
        current_val = current.get(ansible_field)
        if value != current_val:
            patch[rest_field] = value

    if not patch:
        return None
    return patch


# ── State handler functions (extracted for complexity reduction) ───────────────
# Each function below implements one Ansible "state" (gathered, deleted,
# merged, replaced, overridden). They are called from main() based on the
# user's chosen state. This keeps main() short and readable.


def _handle_gathered(
    module: AnsibleModule,
    connection: Connection,
    gather_filter: list,
    result: Dict[str, Any],
) -> None:
    """Handle state=gathered — read-only, return current VRF state."""
    raw_list = _fetch_all_vrfs(module, connection, result["api_responses"])
    all_vrfs = _to_ansible_list(raw_list)

    if gather_filter:
        for f in gather_filter:
            normalized = _normalize_vrf_name(f)
            if f != normalized and f.lower() != f:
                module.warn(
                    "VRF name '{0}' is not in canonical form. "
                    "VOSS stores user VRF names in lowercase, but system VRFs require canonical casing; "
                    "the name will be converted to '{1}'.".format(f, normalized)
                )
        filter_set = {_normalize_vrf_name(f).lower() for f in gather_filter}
        all_vrfs = [v for v in all_vrfs if v["name"].lower() in filter_set]

    result["gathered"] = sorted(all_vrfs, key=lambda x: x["name"])
    result["vrfs"] = [{"name": v["name"], "config": v} for v in result["gathered"]]


def _handle_deleted(
    module: AnsibleModule,
    connection: Connection,
    config: list,
    current_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Handle state=deleted — remove VRFs."""
    if config:
        names_to_delete = [e["name"].lower() for e in config]
    else:
        names_to_delete = [
            name for name, vrf in current_map.items() if _is_user_vrf(vrf)
        ]

    for vrf_name in names_to_delete:
        vrf_result: Dict[str, Any] = {"name": vrf_name}

        if vrf_name not in current_map:
            vrf_result["before"] = {}
            vrf_result["after"] = {}
            vrf_result["changed"] = False
            vrf_result["differences"] = {}
            result["vrfs"].append(vrf_result)
            continue

        current = current_map[vrf_name]
        vrf_result["before"] = current

        if vrf_name in SYSTEM_VRFS:
            module.fail_json(
                msg=f"Cannot delete system VRF '{vrf_name}'. "
                f"System VRFs ({', '.join(sorted(SYSTEM_VRFS))}) "
                "are always present on the device.",
                api_responses=result["api_responses"],
            )

        result["changed"] = True
        vrf_result["changed"] = True

        if not module.check_mode:
            path = VRF_SINGLE_PATH.format(vr_name=quote(vrf_name, safe=""))
            _call_api(
                module,
                connection,
                method="DELETE",
                path=path,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key=f"delete_{vrf_name}",
            )
        vrf_result["after"] = {}

        vrf_result["differences"] = _compute_diff(
            vrf_result["before"], vrf_result["after"]
        )
        result["vrfs"].append(vrf_result)


def _handle_overridden_prepass(
    module: AnsibleModule,
    connection: Connection,
    config: list,
    current_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Handle state=overridden pre-pass: delete unlisted user VRFs."""
    config_names = {e["name"].lower() for e in config}
    for vrf_name, current in current_map.items():
        if vrf_name in config_names:
            continue
        if not _is_user_vrf(current):
            continue

        vrf_result = {
            "name": vrf_name,
            "before": current,
            "changed": True,
        }
        result["changed"] = True

        if not module.check_mode:
            path = VRF_SINGLE_PATH.format(vr_name=quote(vrf_name, safe=""))
            _call_api(
                module,
                connection,
                method="DELETE",
                path=path,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key=f"override_delete_{vrf_name}",
            )
        vrf_result["after"] = {}

        vrf_result["differences"] = _compute_diff(
            vrf_result["before"], vrf_result["after"]
        )
        result["vrfs"].append(vrf_result)


def _handle_merge_replace(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    config: list,
    current_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Handle state=merged/replaced/overridden per-entry processing."""
    for entry in config:
        vrf_name = _normalize_vrf_name(entry["name"])
        vrf_result = {"name": vrf_name}
        current = current_map.get(vrf_name.lower())

        if current is None:
            # VRF does not exist — create it
            vrf_result["before"] = {}
            result["changed"] = True
            vrf_result["changed"] = True

            if not module.check_mode:
                create_payload = _build_create_payload(entry)
                _call_api(
                    module,
                    connection,
                    method="POST",
                    path=VRF_LIST_PATH,
                    payload=create_payload,
                    expect_content=False,
                    api_responses=result["api_responses"],
                    response_key=f"create_{vrf_name}",
                )
                after_raw = _fetch_single_vrf(
                    module,
                    connection,
                    vrf_name,
                    result["api_responses"],
                    response_key=f"after_{vrf_name}",
                )
                vrf_result["after"] = (
                    _to_ansible_output(after_raw) if after_raw else {}
                )
            else:
                predicted: Dict[str, Any] = {"name": vrf_name}
                routing = entry.get("ip_routing_enabled")
                predicted["ip_routing_enabled"] = (
                    routing if routing is not None else True
                )
                predicted["vr_type"] = "VRF"
                vrf_result["after"] = predicted

            vrf_result["differences"] = _compute_diff(
                vrf_result["before"], vrf_result["after"]
            )
            result["vrfs"].append(vrf_result)
            continue

        # VRF exists — update if needed
        vrf_result["before"] = current

        if state == STATE_MERGED:
            patch = _build_patch_payload(entry, current)
        else:
            patch = _build_replaced_payload(entry, current)

        if patch is None:
            vrf_result["after"] = current
            vrf_result["changed"] = False
            vrf_result["differences"] = {}
            result["vrfs"].append(vrf_result)
            continue

        result["changed"] = True
        vrf_result["changed"] = True

        if not module.check_mode:
            path = VRF_SINGLE_PATH.format(vr_name=quote(vrf_name, safe=""))
            _call_api(
                module,
                connection,
                method="PATCH",
                path=path,
                payload=patch,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key=f"patch_{vrf_name}",
            )
            after_raw = _fetch_single_vrf(
                module,
                connection,
                vrf_name,
                result["api_responses"],
                response_key=f"after_{vrf_name}",
            )
            vrf_result["after"] = (
                _to_ansible_output(after_raw) if after_raw else current
            )
        else:
            predicted = dict(current)
            for rest_field, value in patch.items():
                ansible_field = FIELD_MAP_REV.get(rest_field, rest_field)
                predicted[ansible_field] = value
            vrf_result["after"] = predicted

        vrf_result["differences"] = _compute_diff(
            vrf_result["before"], vrf_result["after"]
        )
        result["vrfs"].append(vrf_result)


def _capture_after_state(
    module: AnsibleModule,
    connection: Connection,
    current_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Fetch or predict the module-level after state."""
    def _predict():
        amap = dict(current_map)
        for vrf_res in result["vrfs"]:
            n = vrf_res["name"]
            if vrf_res.get("after"):
                amap[n.lower()] = vrf_res["after"]
            else:
                amap.pop(n.lower(), None)
        return sorted(amap.values(), key=lambda x: x["name"])

    if not module.check_mode:
        try:
            after_raw = _fetch_all_vrfs(
                module, connection, result["api_responses"], "configuration_after"
            )
            result["after"] = sorted(
                _to_ansible_list(after_raw), key=lambda x: x["name"]
            )
        except (ConnectionError, FeVrfError):
            result["after"] = _predict()
    else:
        result["after"] = _predict()


# ── Main entry point ─────────────────────────────────────────────────────────


def main() -> None:
    """Module entry point — dispatch based on state."""

    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
    )

    if not module._socket_path:
        module.fail_json(msg="Connection type httpapi is required for this module")

    connection = Connection(module._socket_path)
    state = module.params["state"]
    config = module.params.get("config") or []
    gather_filter = module.params.get("gather_filter") or []

    # Validate: merged/replaced/overridden require config
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN) and not config:
        module.fail_json(msg="'config' is required when state is '{0}'".format(state))

    # Validate: no duplicate VRF names in config
    if config:
        seen: set = set()
        for entry in config:
            vrf_name = entry["name"]
            if not vrf_name or len(vrf_name) > 16:
                module.fail_json(
                    msg="VRF name must be 1-16 characters, got '{0}' ({1} chars)".format(
                        vrf_name, len(vrf_name) if vrf_name else 0
                    )
                )
            normalized = _normalize_vrf_name(vrf_name)
            if vrf_name != normalized:
                if vrf_name.lower() != vrf_name:
                    module.warn(
                        "VRF name '{0}' is not in canonical form. "
                        "VOSS stores user VRF names in lowercase, but system VRFs require canonical casing; "
                        "the name will be converted to '{1}'.".format(
                            vrf_name, normalized
                        )
                    )
                entry["name"] = normalized
            if normalized.lower() in seen:
                module.fail_json(
                    msg="Duplicate VRF name '{0}' in config list".format(vrf_name)
                )
            seen.add(normalized.lower())

    result: Dict[str, Any] = {
        "changed": False,
        "vrfs": [],
        "api_responses": {},
    }

    try:
        # ── GATHERED ──────────────────────────────────────────────────────
        if state == STATE_GATHERED:
            _handle_gathered(module, connection, gather_filter, result)
            module.exit_json(**result)
            return

        # ── Fetch current state for change-making states ──────────────────
        raw_list = _fetch_all_vrfs(
            module, connection, result["api_responses"], "configuration_before"
        )
        current_map: Dict[str, Dict[str, Any]] = {}
        for raw in raw_list:
            vrf_out = _to_ansible_output(raw)
            name = vrf_out.get("name")
            if not isinstance(name, str) or not name:
                continue
            current_map[name.lower()] = vrf_out

        result["before"] = sorted(current_map.values(), key=lambda x: x["name"])

        # ── DELETED ───────────────────────────────────────────────────────
        if state == STATE_DELETED:
            _handle_deleted(module, connection, config, current_map, result)
            if result["changed"]:
                _capture_after_state(module, connection, current_map, result)
            module.exit_json(**result)
            return

        # ── OVERRIDDEN pre-pass ───────────────────────────────────────────
        if state == STATE_OVERRIDDEN:
            _handle_overridden_prepass(module, connection, config, current_map, result)

        # ── MERGED / REPLACED / OVERRIDDEN — per-entry ────────────────────
        _handle_merge_replace(module, connection, state, config, current_map, result)

        # ── Capture after state ───────────────────────────────────────────
        if result["changed"]:
            _capture_after_state(module, connection, current_map, result)

        module.exit_json(**result)

    except FeVrfError as exc:
        module.fail_json(**exc.to_fail_kwargs(), api_responses=result["api_responses"])
    except ConnectionError as exc:
        module.fail_json(
            msg=f"Connection error: {to_text(exc)}",
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=result["api_responses"],
        )


if __name__ == "__main__":
    main()
