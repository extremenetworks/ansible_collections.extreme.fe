# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Ansible module to manage Anycast Gateway interfaces on Extreme Fabric Engine (VOSS) switches.

REST API endpoints used:
  GET    /v0/configuration/anycast-gateway/interfaces          — list all interfaces
  POST   /v0/configuration/anycast-gateway/vlan/{vlan_id}      — create interface
  PATCH  /v0/configuration/anycast-gateway/vlan/{vlan_id}/interface — update enabled
  DELETE /v0/configuration/anycast-gateway/vlan/{vlan_id}      — delete interface
  GET    /v0/state/anycast-gateway/interfaces                  — operational state

Writable fields (POST only — immutable after creation):
  ipAddress.address    — IPv4 address of the anycast gateway
  ipAddress.maskLength — IPv4 mask length (0-32)
  oneIp                — ONE-IP mode (bool, default false)
  vrId                 — Virtual Router ID (int, 1-255, optional)

Writable fields (PATCH):
  enabled              — Administrative status (bool, default false)

Read-only fields returned in output:
  vlan_id, mac_address, l2vsn_isid, oper_state
"""

from __future__ import annotations

# ipaddress — standard library module for validating and comparing IP addresses/networks
import ipaddress
# time — used for retry delays when PATCH follows POST (API timing)
import time as _time
# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any, Dict, List, Optional

# AnsibleModule — the core class every Ansible module must instantiate;
# it handles argument parsing, check mode, exit/fail, etc.
from ansible.module_utils.basic import AnsibleModule
# Connection — communicates with the device through the httpapi plugin;
# ConnectionError — raised when the device is unreachable or returns a transport error
from ansible.module_utils.connection import Connection, ConnectionError
# to_text — safely converts bytes/strings to unicode text
from ansible.module_utils.common.text.converters import to_text

# ── Ansible module metadata ──────────────────────────────────────────────────

DOCUMENTATION = r"""
module: extreme_fe_anycast_gateway
short_description: Manage Anycast Gateway interfaces on Extreme Fabric Engine switches
version_added: "1.2.0"
description:
  - Create, update, delete, and query Anycast Gateway interfaces on Extreme
    Fabric Engine (VOSS) switches via the REST API.
  - Supports all five Ansible resource module states.
  - Each Anycast Gateway interface is identified by its C(vlan_id).
  - Writable fields at creation (immutable after): C(ip_address), C(mask_length),
    C(one_ip), C(vr_id).
  - Only C(enabled) can be updated on an existing interface via PATCH.
author:
  - Extreme Networks
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI
    connection plugin.
  - Once created, C(ip_address), C(mask_length), C(one_ip), and C(vr_id) cannot
    be changed. Use C(state=replaced) (DELETE + re-POST) to change these fields.
  - C(state=merged) will fail if you try to change immutable fields on an existing
    interface. Use C(state=replaced) or delete the interface first.
  - For C(state=replaced) and C(state=overridden), omitted immutable fields are
    treated as "don't care" — only provided immutable fields are compared for
    differences. If you want to enforce specific immutable values on an existing
    interface, provide all immutable fields or use C(state=deleted) first.
  - C(mask_length) can only be specified when C(one_ip=true). VOSS constraint:
    "IP Address mask allowed only with Anycast Gateway ONE-IP."
  - The module automatically disables an interface (C(enabled=false)) before
    deleting it, as required by VOSS.
  - IPv6 Anycast is currently not supported by the device firmware.
requirements:
  - ansible.netcommon
options:
  state:
    description:
      - Desired operation state.
      - C(merged) creates interfaces that do not exist and updates C(enabled) on
        existing interfaces. Fails if immutable fields differ.
      - C(replaced) makes the provided config authoritative per listed interface.
        If immutable fields differ, the interface is deleted and recreated.
      - C(overridden) deletes unlisted interfaces, then applies C(replaced) logic
        to listed ones.
      - C(deleted) removes the specified interfaces. If C(config) is omitted, all
        Anycast Gateway interfaces are deleted.
      - C(gathered) returns current interface information without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - List of Anycast Gateway interface configurations to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional for C(deleted) (omit to delete all) and C(gathered).
    type: list
    elements: dict
    suboptions:
      vlan_id:
        description:
          - VLAN ID (1-4094). This is the resource identifier.
        type: int
        required: true
      ip_address:
        description:
          - IPv4 address of the Anycast Gateway interface.
          - Immutable after creation. Use C(state=replaced) to change.
        type: str
      mask_length:
        description:
          - IPv4 subnet mask length (0-32).
          - Only allowed when C(one_ip=true).
          - Immutable after creation. Use C(state=replaced) to change.
        type: int
      enabled:
        description:
          - Administrative status of the Anycast Gateway on the VLAN.
          - This is the only field that can be updated on an existing interface.
        type: bool
      one_ip:
        description:
          - Enable ONE-IP mode. VOSS only.
          - Immutable after creation. Use C(state=replaced) to change.
        type: bool
      vr_id:
        description:
          - Virtual Router ID (1-255). VOSS only.
          - If omitted at creation, the device uses the default GW MAC.
          - Immutable after creation. Use C(state=replaced) to change.
        type: int
  gather_filter:
    description:
      - Limit gathered results to these VLAN IDs.
    type: list
    elements: int
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
# Task 1: Gather all Anycast Gateway interfaces
# -------------------------------------------------------------------------
# - name: "Task 1: Gather Anycast Gateway interfaces"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather current Anycast Gateway configuration
  extreme.fe.extreme_fe_anycast_gateway:
    state: gathered

# -------------------------------------------------------------------------
# Task 2: Gather selected VLANs only
# -------------------------------------------------------------------------
# - name: "Task 2: Gather Anycast Gateway for selected VLANs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather Anycast GW for VLANs 100 and 200
  extreme.fe.extreme_fe_anycast_gateway:
    state: gathered
    gather_filter:
      - 100
      - 200

# -------------------------------------------------------------------------
# Task 3: Create Anycast Gateway interfaces
# -------------------------------------------------------------------------
# - name: "Task 3: Create Anycast Gateway interfaces"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Create Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: merged
    config:
      - vlan_id: 100
        ip_address: 10.10.10.1
        mask_length: 24
        one_ip: true
        enabled: true

- name: Create Anycast GW with ONE-IP and VRID
  extreme.fe.extreme_fe_anycast_gateway:
    state: merged
    config:
      - vlan_id: 200
        ip_address: 192.168.1.1
        mask_length: 24
        one_ip: true
        vr_id: 21
        enabled: true

# -------------------------------------------------------------------------
# Task 4: Replace/override Anycast Gateway interfaces
# -------------------------------------------------------------------------
# - name: "Task 4: Replace or override Anycast Gateway configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Replace Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: replaced
    config:
      - vlan_id: 100
        ip_address: 10.10.10.254
        mask_length: 24
        one_ip: true
        enabled: true

- name: Override all Anycast GW interfaces
  extreme.fe.extreme_fe_anycast_gateway:
    state: overridden
    config:
      - vlan_id: 100
        ip_address: 10.10.10.1
        mask_length: 24
        one_ip: true
        enabled: true

# -------------------------------------------------------------------------
# Task 5: Delete Anycast Gateway interfaces
# -------------------------------------------------------------------------
# - name: "Task 5: Delete Anycast Gateway interfaces"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Delete Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: deleted
    config:
      - vlan_id: 100

- name: Delete all Anycast GW interfaces
  extreme.fe.extreme_fe_anycast_gateway:
    state: deleted
"""

RETURN = r"""
before:
  description:
    - Full Anycast Gateway resource configuration before changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
after:
  description:
    - Full Anycast Gateway resource configuration after changes.
    - Only returned when the module made changes.
  returned: when changed
  type: list
  elements: dict
gathered:
  description:
    - Anycast Gateway configuration gathered from the device.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
anycast_gateways:
  description: Per-resource Anycast Gateway operation results with differences.
  returned: when state is not gathered
  type: list
  elements: dict
  contains:
    vlan_id:
      description: VLAN ID (resource identifier).
      type: int
    before:
      description: Interface configuration before the operation.
      type: dict
    after:
      description: Interface configuration after the operation.
      type: dict
    changed:
      description: Whether this interface was modified.
      type: bool
    differences:
      description: Fields that changed with before/after values.
      type: dict
api_responses:
  description: Raw REST API responses for debugging.
  returned: always
  type: dict
changed:
  description: Whether any interface was modified.
  returned: always
  type: bool
"""

# ── Constants ─────────────────────────────────────────────────────────────────

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# REST API paths
AG_LIST_PATH = "/v0/configuration/anycast-gateway/interfaces"
AG_VLAN_PATH = "/v0/configuration/anycast-gateway/vlan/{vlan_id}"
AG_PATCH_PATH = "/v0/configuration/anycast-gateway/vlan/{vlan_id}/interface"
AG_STATE_PATH = "/v0/state/anycast-gateway/interfaces"

# Factory defaults
FACTORY_DEFAULTS = {
    "enabled": False,
    "one_ip": False,
}

# Fields set at creation that cannot be PATCHed
IMMUTABLE_FIELDS = {"ip_address", "mask_length", "one_ip", "vr_id"}

# Writable fields for diff comparison (exclude identifier and read-only)
DIFF_FIELDS = ("ip_address", "mask_length", "enabled", "one_ip", "vr_id")

# Argument spec
ARGUMENT_SPEC = {
    "state": {
        "type": "str",
        "default": STATE_MERGED,
        "choices": [
            STATE_MERGED,
            STATE_REPLACED,
            STATE_OVERRIDDEN,
            STATE_DELETED,
            STATE_GATHERED,
        ],
    },
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "vlan_id": {"type": "int", "required": True},
            "ip_address": {"type": "str"},
            "mask_length": {"type": "int"},
            "enabled": {"type": "bool"},
            "one_ip": {"type": "bool"},
            "vr_id": {"type": "int"},
        },
    },
    "gather_filter": {
        "type": "list",
        "elements": "int",
    },
}


# ── Custom Exception ─────────────────────────────────────────────────────────


class FeAnycastGwError(Exception):
    """Raised for module-specific errors."""

    def __init__(self, msg: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(msg)
        self.msg = msg
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"msg": self.msg}
        if self.details:
            kwargs["details"] = self.details
        return kwargs


# ── REST API Helper ───────────────────────────────────────────────────────────
# This utility function handles communication with the device's REST API.
# It sends HTTP requests (GET, POST, PATCH, DELETE) and processes responses.


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: Dict[str, Any],
    response_key: str,
    payload: Any = None,
) -> Any:
    """Send a single REST API request.

    Args:
        module:         The AnsibleModule instance.
        connection:     The device Connection object.
        method:         HTTP method (GET, POST, PATCH, DELETE).
        path:           REST API path.
        payload:        Request body (dict for JSON, None for no body).
        api_responses:  Dict to store raw API responses for debugging.
        response_key:   Key name to store this response under.

    Returns:
        Parsed response payload, or None if no content.
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

    if parsed is not None and isinstance(parsed, (dict, list)):
        err = _extract_error(parsed)
        if err:
            raise FeAnycastGwError(
                f"{method} {path} returned an error: {err}",
                details={"response": parsed},
            )

    return parsed


def _extract_error(data: Any) -> Optional[str]:
    """Extract an error message from a REST response, if present."""
    if not isinstance(data, dict):
        return None
    # Check for errorCode/statusCode/code pattern (VOSS REST convention)
    code = data.get("errorCode") or data.get("statusCode") or data.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    message = data.get("errorMessage") or data.get("message") or data.get("detail")
    if code and isinstance(code, int) and code >= 400:
        return message or "Device reported an error (code {0})".format(code)
    # Check for error/errors keys
    if "error" in data and data["error"]:
        err = data["error"]
        if isinstance(err, dict):
            return err.get("message", str(err))
        return str(err)
    if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
        msgs = [
            e.get("message", str(e)) if isinstance(e, dict) else str(e)
            for e in data["errors"]
        ]
        return "; ".join(msgs)
    return None


# ── Disable-before-Delete Helper ──────────────────────────────────────────────


def _disable_and_delete(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    current: Optional[Dict[str, Any]],
    api_responses: Dict[str, Any],
    response_prefix: str,
) -> None:
    """Disable an Anycast GW interface (if enabled) then DELETE it.

    VOSS requires enabled=false before DELETE is allowed.
    """
    if current and current.get("enabled"):
        patch_path = AG_PATCH_PATH.format(vlan_id=vid)
        _call_api(
            module,
            connection,
            method="PATCH",
            path=patch_path,
            payload={"enabled": False},
            api_responses=api_responses,
            response_key=f"{response_prefix}_disable_{vid}",
        )
    del_path = AG_VLAN_PATH.format(vlan_id=vid)
    _call_api(
        module,
        connection,
        method="DELETE",
        path=del_path,
        api_responses=api_responses,
        response_key=f"{response_prefix}_{vid}",
    )


# ── Data-Fetching Functions ───────────────────────────────────────────────────
# These functions retrieve the current configuration from the device via
# REST GET requests and normalize the response into Python data structures.


def _fetch_all_interfaces(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
    response_key: str = "get_all",
) -> List[Dict[str, Any]]:
    """Fetch all Anycast Gateway interfaces from the device."""
    raw = _call_api(
        module,
        connection,
        method="GET",
        path=AG_LIST_PATH,
        api_responses=api_responses,
        response_key=response_key,
    )
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if not raw:
            return []
        # Handle dict wrappers (data, items, interfaces, etc.)
        for key in ["data", "items", "interfaces", "anycast_gateways"]:
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    return []


def _fetch_state_interfaces(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
    response_key: str = "get_state",
) -> Dict[int, Dict[str, Any]]:
    """Fetch operational state for all Anycast Gateway interfaces.

    Returns a dict keyed by vlan_id with state data.
    """
    raw = _call_api(
        module,
        connection,
        method="GET",
        path=AG_STATE_PATH,
        api_responses=api_responses,
        response_key=response_key,
    )
    state_map: Dict[int, Dict[str, Any]] = {}
    if isinstance(raw, list):
        for entry in raw:
            vid = entry.get("vlanId")
            if vid is not None:
                state_map[vid] = entry
    elif isinstance(raw, dict):
        # Handle dict wrappers (data, items, state, etc.)
        list_data = None
        for key in ["data", "items", "state", "interfaces", "anycast_gateways"]:
            if key in raw and isinstance(raw[key], list):
                list_data = raw[key]
                break
        if list_data:
            for entry in list_data:
                vid = entry.get("vlanId")
                if vid is not None:
                    state_map[vid] = entry
    return state_map


# ── Output Converters ─────────────────────────────────────────────────────────
# Converts raw REST API responses (device field names) into Ansible-friendly
# output format (snake_case field names matching the module's argument spec).


def _to_ansible_output(
    raw: Dict[str, Any], state_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Convert a single REST InterfaceAnycastGateway to Ansible output format."""
    ip_obj = raw.get("ipAddress") or {}
    result: Dict[str, Any] = {
        "vlan_id": raw.get("vlanId"),
        "enabled": raw.get("enabled"),
        "one_ip": raw.get("oneIp"),
        "vr_id": raw.get("vrId"),
        "mac_address": raw.get("macAddress"),
        "l2vsn_isid": raw.get("L2vsnIsid"),
    }
    if isinstance(ip_obj, dict):
        result["ip_address"] = ip_obj.get("address")
        result["mask_length"] = ip_obj.get("maskLength")
    else:
        result["ip_address"] = None
        result["mask_length"] = None

    # Merge operational state if available
    if state_data:
        result["oper_state"] = state_data.get("operState")
    else:
        result["oper_state"] = None

    return result


def _to_ansible_list(
    raw_list: List[Dict[str, Any]],
    state_map: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Convert a list of REST responses to Ansible output format."""
    results = []
    for raw in raw_list:
        vid = raw.get("vlanId")
        s = state_map.get(vid) if state_map else None
        results.append(_to_ansible_output(raw, s))
    return results


# ── Diff / Comparison ─────────────────────────────────────────────────────────
# Compares the "before" (current device state) with the "after" (desired state)
# to determine what changes need to be made. This drives idempotency — if
# before == after, no API calls are needed.


def _compute_diff(
    before: Dict[str, Any], after: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Compute differences between before and after states.

    Only compares writable/meaningful fields, excluding the identifier
    and read-only fields.
    """
    diff: Dict[str, Any] = {}
    for key in DIFF_FIELDS:
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            diff[key] = {"before": old_val, "after": new_val}
    return diff


def _immutable_fields_differ(
    entry: Dict[str, Any], current: Dict[str, Any]
) -> List[str]:
    """Check if any immutable (POST-only) fields differ.

    Returns a list of field names that differ, or empty list if all match.
    Only checks fields that the user explicitly provided (not None).
    """
    diffs = []
    for field in IMMUTABLE_FIELDS:
        desired = entry.get(field)
        if desired is None:
            continue
        current_val = current.get(field)
        if desired != current_val:
            diffs.append(field)
    return diffs


# ── Payload Builders ──────────────────────────────────────────────────────────
# These functions convert Ansible parameters into the JSON payloads expected
# by the device REST API (POST for create, PATCH for update).


def _build_post_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build the AnycastGatewayInterfaceCreate POST payload.

    The POST schema (AnycastGatewayInterfaceCreate) only supports:
      ipAddress, oneIp, vrId.
    The 'enabled' field is NOT part of the POST schema — it must be
    set via a separate PATCH after creation.

    Args:
        entry: User config dict with Ansible field names.

    Returns:
        REST-ready dict for POST.
    """
    payload: Dict[str, Any] = {}

    # IP address (required for POST)
    ip_addr = entry.get("ip_address")
    mask_len = entry.get("mask_length")
    if ip_addr is not None:
        ip_obj: Dict[str, Any] = {"address": ip_addr}
        if mask_len is not None:
            ip_obj["maskLength"] = mask_len
        payload["ipAddress"] = ip_obj

    # oneIp
    one_ip = entry.get("one_ip")
    if one_ip is not None:
        payload["oneIp"] = one_ip

    # vrId
    vr_id = entry.get("vr_id")
    if vr_id is not None:
        payload["vrId"] = vr_id

    # NOTE: 'enabled' is intentionally NOT included here.
    # The AnycastGatewayInterfaceCreate schema does not support it.
    # Use _patch_enabled_after_create() after POST to set enabled.

    return payload


def _patch_enabled_after_create(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    enabled: bool,
    api_responses: Dict[str, Any],
) -> None:
    """PATCH the enabled field after POST creation, with retry.

    After POST creates an Anycast Gateway interface, VOSS needs a brief
    moment before the IP interface is visible to the PATCH endpoint.
    This function retries the PATCH up to 5 times with a short delay to
    handle this timing issue (HTTP 422 "IP interface not found").

    NOTE: If the VLAN does not have a real IP interface configured (via
    L3 interfaces / ip address command), PATCH enabled will always fail
    with "IP interface not found" regardless of retries. In that case,
    the error message includes guidance to configure L3 interface first.
    """
    patch_path = AG_PATCH_PATH.format(vlan_id=vid)
    patch_payload = {"enabled": enabled}
    max_retries = 5
    retry_delay = 3.0  # seconds

    for attempt in range(max_retries):
        try:
            raw = connection.send_request(
                patch_payload, path=patch_path, method="PATCH"
            )
            # Parse string responses
            if isinstance(raw, str):
                import json as _json
                try:
                    raw = _json.loads(raw)
                except (ValueError, TypeError):
                    pass
            # Fail fast on in-band error payloads
            if isinstance(raw, dict):
                err = _extract_error(raw)
                if err:
                    module.fail_json(
                        msg="REST API error on PATCH {0}: {1}".format(patch_path, err),
                        api_responses=api_responses,
                    )
            # Success — record response and return
            api_responses["patch_enabled_{0}".format(vid)] = {
                "method": "PATCH",
                "path": patch_path,
                "body": raw,
                "attempt": attempt + 1,
            }
            return
        except ConnectionError as exc:
            code = getattr(exc, "code", None)
            # HTTP 422 = IP interface not yet visible — retry
            if code == 422 and attempt < max_retries - 1:
                _time.sleep(retry_delay)
                continue
            # Final attempt or non-retryable error — fail
            err_text = to_text(exc)
            if "IP interface not found" in err_text:
                err_text = (
                    "{0}. The VLAN must have a real IP interface configured "
                    "(via L3 interfaces module or 'interface vlan {1}; ip address ...') "
                    "before Anycast Gateway can be enabled."
                ).format(err_text, vid)
            module.fail_json(
                msg=(
                    "Failed to PATCH enabled on Anycast Gateway vlan_id={0} "
                    "after POST creation: {1}"
                ).format(vid, err_text),
                code=code,
                err=getattr(exc, "err", None),
                api_responses=api_responses,
            )


def _build_patch_payload(
    entry: Dict[str, Any],
    current: Dict[str, Any],
    use_factory_defaults: bool = False,
) -> Optional[Dict[str, Any]]:
    """Build PATCH payload for updating enabled status.

    Args:
        entry:                User config dict.
        current:              Current device state dict.
        use_factory_defaults: When True (for replaced/overridden),
            treat omitted ``enabled`` as the factory default (False)
            instead of "no change".

    Returns None if no changes are needed (idempotent).
    """
    desired_enabled = entry.get("enabled")
    if desired_enabled is None:
        if use_factory_defaults:
            desired_enabled = FACTORY_DEFAULTS["enabled"]
        else:
            return None

    current_enabled = current.get("enabled")
    if desired_enabled == current_enabled:
        return None

    return {"enabled": desired_enabled}


# ── Validation ────────────────────────────────────────────────────────────────


def _validate_ip_address(module: AnsibleModule, entry: Dict[str, Any]) -> None:
    """Validate that ip_address is a valid IPv4 address."""
    addr = entry.get("ip_address")
    if addr is None:
        return
    try:
        parsed = ipaddress.ip_address(addr)
    except ValueError:
        module.fail_json(
            msg="Invalid IP address '{0}' for vlan_id {1}".format(
                addr, entry.get("vlan_id")
            )
        )
    if parsed.version != 4:
        module.fail_json(
            msg="IPv6 Anycast is not supported. "
            "Address '{0}' for vlan_id {1} must be IPv4".format(
                addr, entry.get("vlan_id")
            )
        )


def _validate_mask_length(module: AnsibleModule, entry: Dict[str, Any]) -> None:
    """Validate mask_length is within range."""
    mask = entry.get("mask_length")
    if mask is None:
        return
    if not 0 <= mask <= 32:
        module.fail_json(
            msg="mask_length must be 0-32, got {0} for vlan_id {1}".format(
                mask, entry.get("vlan_id")
            )
        )


def _validate_vlan_id(module: AnsibleModule, entry: Dict[str, Any]) -> None:
    """Validate vlan_id is within range."""
    vid = entry.get("vlan_id")
    if vid is None:
        return
    if not 1 <= vid <= 4094:
        module.fail_json(msg="vlan_id must be 1-4094, got {0}".format(vid))


def _validate_vr_id(module: AnsibleModule, entry: Dict[str, Any]) -> None:
    """Validate vr_id is within range."""
    vr_id = entry.get("vr_id")
    if vr_id is None:
        return
    if not 1 <= vr_id <= 255:
        module.fail_json(
            msg="vr_id must be 1-255, got {0} for vlan_id {1}".format(
                vr_id, entry.get("vlan_id")
            )
        )


def _validate_mask_requires_one_ip(
    module: AnsibleModule, entry: Dict[str, Any]
) -> None:
    """Validate that mask_length requires one_ip=true (VOSS constraint).

    Only enforced when one_ip is explicitly provided in the entry.
    If one_ip is omitted, the existing device value may already be true.
    """
    mask = entry.get("mask_length")
    if mask is None:
        return
    one_ip = entry.get("one_ip")
    if one_ip is None:
        # one_ip not specified — skip validation (device may already have it set)
        return
    if not one_ip:
        module.fail_json(
            msg="IP Address mask allowed only with Anycast Gateway ONE-IP. "
            "Set one_ip=true when mask_length is specified "
            "(vlan_id {0})".format(entry.get("vlan_id"))
        )


def _validate_entry(module: AnsibleModule, entry: Dict[str, Any]) -> None:
    """Run all validations on a single config entry."""
    _validate_vlan_id(module, entry)
    _validate_ip_address(module, entry)
    _validate_mask_length(module, entry)
    _validate_vr_id(module, entry)
    _validate_mask_requires_one_ip(module, entry)


# ── Predict After State (check mode) ─────────────────────────────────────────


def _predict_after_create(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Predict the after state for a newly created interface."""
    predicted: Dict[str, Any] = {
        "vlan_id": entry["vlan_id"],
        "ip_address": entry.get("ip_address"),
        "mask_length": entry.get("mask_length"),
        "enabled": entry.get("enabled", FACTORY_DEFAULTS["enabled"]),
        "one_ip": entry.get("one_ip", FACTORY_DEFAULTS["one_ip"]),
        "vr_id": entry.get("vr_id"),
        "mac_address": None,
        "l2vsn_isid": None,
        "oper_state": None,
    }
    return predicted


def _predict_after_patch(
    entry: Dict[str, Any],
    current: Dict[str, Any],
    use_factory_defaults: bool = False,
) -> Dict[str, Any]:
    """Predict the after state for a PATCH (enabled toggle)."""
    predicted = dict(current)
    desired_enabled = entry.get("enabled")
    if desired_enabled is None and use_factory_defaults:
        desired_enabled = FACTORY_DEFAULTS["enabled"]
    if desired_enabled is not None:
        predicted["enabled"] = desired_enabled
    return predicted


def _predict_after_replaced(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Predict the after state for replaced (DELETE + re-POST)."""
    return _predict_after_create(entry)


# ── Handler helpers (extracted from main to reduce cyclomatic complexity) ─────
# Each function below implements one Ansible "state" (gathered, deleted,
# merged, replaced, overridden). They are called from main() based on the
# user's chosen state. This keeps main() short and readable.


def _handle_gathered(
    module: AnsibleModule,
    connection: Connection,
    gather_filter: List[int],
    result: Dict[str, Any],
) -> None:
    """Handle the GATHERED state — read-only, return current state."""
    raw_list = _fetch_all_interfaces(
        module, connection, result["api_responses"]
    )
    state_map = _fetch_state_interfaces(
        module, connection, result["api_responses"]
    )
    all_ifs = _to_ansible_list(raw_list, state_map)

    if gather_filter:
        filter_set = set(gather_filter)
        all_ifs = [i for i in all_ifs if i["vlan_id"] in filter_set]

    result["gathered"] = sorted(all_ifs, key=lambda x: x["vlan_id"])
    result.pop("anycast_gateways", None)
    module.exit_json(**result)


def _handle_deleted(
    module: AnsibleModule,
    connection: Connection,
    config: List[Dict[str, Any]],
    current_map: Dict[int, Dict[str, Any]],
    state_map: Dict[int, Any],
    result: Dict[str, Any],
) -> None:
    """Handle the DELETED state — remove interfaces."""
    if config:
        vids_to_delete = [e["vlan_id"] for e in config]
    else:
        # Delete ALL anycast gateway interfaces
        vids_to_delete = list(current_map.keys())

    for vid in vids_to_delete:
        gw_result: Dict[str, Any] = {"vlan_id": vid}

        if vid not in current_map:
            gw_result["before"] = {}
            gw_result["after"] = {}
            gw_result["changed"] = False
            gw_result["differences"] = {}
            result["anycast_gateways"].append(gw_result)
            continue

        gw_result["before"] = current_map[vid]
        gw_result["after"] = {}
        gw_result["changed"] = True
        result["changed"] = True

        if not module.check_mode:
            _disable_and_delete(
                module,
                connection,
                vid,
                current_map.get(vid),
                result["api_responses"],
                "delete",
            )

        gw_result["differences"] = _compute_diff(
            gw_result["before"], gw_result["after"]
        )
        result["anycast_gateways"].append(gw_result)

    # Capture module-level "after" for deleted state
    if result["changed"]:
        def _predict_after_del():
            amap = dict(current_map)
            for gw_res in result["anycast_gateways"]:
                vid = gw_res["vlan_id"]
                if gw_res.get("after"):
                    amap[vid] = gw_res["after"]
                else:
                    amap.pop(vid, None)
            return sorted(amap.values(), key=lambda x: x["vlan_id"])

        if not module.check_mode:
            try:
                final_raw = _fetch_all_interfaces(
                    module, connection, result["api_responses"], "after_all"
                )
                final_state = _fetch_state_interfaces(
                    module, connection, result["api_responses"], "state_after_all"
                )
                result["after"] = sorted(
                    _to_ansible_list(final_raw, final_state),
                    key=lambda x: x["vlan_id"],
                )
            except (ConnectionError, FeAnycastGwError):
                result["after"] = _predict_after_del()
        else:
            result["after"] = _predict_after_del()

    module.exit_json(**result)


def _handle_overridden_prepass(
    module: AnsibleModule,
    connection: Connection,
    config: List[Dict[str, Any]],
    current_map: Dict[int, Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """OVERRIDDEN pre-pass: delete interfaces not in desired config."""
    config_vids = {e["vlan_id"] for e in config}
    for vid, current in current_map.items():
        if vid in config_vids:
            continue
        # Delete this interface — not in desired config
        gw_result: Dict[str, Any] = {
            "vlan_id": vid,
            "before": current,
            "after": {},
            "changed": True,
        }
        result["changed"] = True

        if not module.check_mode:
            _disable_and_delete(
                module,
                connection,
                vid,
                current,
                result["api_responses"],
                "override_delete",
            )

        gw_result["differences"] = _compute_diff(
            gw_result["before"], gw_result["after"]
        )
        result["anycast_gateways"].append(gw_result)


def _try_fallback_get(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    state_map: Dict[int, Any],
    current_map: Dict[int, Dict[str, Any]],
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Try a filtered GET when bulk GET missed an interface.

    The bulk GET /v0/configuration/anycast-gateway/interfaces may not return
    recently-created interfaces due to a known VOSS API timing issue.  This
    function uses the same endpoint with the vlan_id query parameter to ask
    the device specifically about the target VLAN.  If that also fails, it
    falls back to the state endpoint as a last resort.

    Returns the parsed current output if found, else None.
    """
    # Strategy 1: Use the bulk endpoint with vlan_id query filter.
    # The OpenAPI spec confirms: GET /v0/configuration/anycast-gateway/interfaces?vlan_id=N
    fallback_path = AG_LIST_PATH + "?vlan_id={0}".format(vid)
    single_raw = None
    try:
        single_raw = connection.send_request(
            None, path=fallback_path, method="GET"
        )
    except ConnectionError as exc:
        code = getattr(exc, "code", None)
        # Only treat not-found / transient cases as "missing"; fail on everything else.
        if code not in (404, 422):
            module.fail_json(
                msg="REST API call failed: GET {0}: {1}".format(fallback_path, to_text(exc)),
                code=code,
                err=getattr(exc, "err", None),
                api_responses=result["api_responses"],
            )
        single_raw = None

    # Parse string responses
    if isinstance(single_raw, str):
        import json as _json
        try:
            single_raw = _json.loads(single_raw)
        except (ValueError, TypeError):
            pass

    result["api_responses"]["get_filtered_{0}".format(vid)] = {
        "method": "GET",
        "path": fallback_path,
        "body": single_raw,
    }

    # Fail fast if the device returned an in-band error payload.
    if isinstance(single_raw, dict):
        err = _extract_error(single_raw)
        if err:
            module.fail_json(
                msg="REST API error on fallback GET {0}: {1}".format(fallback_path, err),
                api_responses=result["api_responses"],
            )

    # Try to extract interface data from the filtered response
    iface_data = _extract_iface_from_response(single_raw, vid)

    # Strategy 2: If filtered config GET failed, try the state endpoint.
    # The state endpoint may have the interface even if config does not.
    if iface_data is None:
        state_path = AG_STATE_PATH
        state_raw = None
        try:
            state_raw = connection.send_request(
                None, path=state_path, method="GET"
            )
        except ConnectionError:
            state_raw = None

        if isinstance(state_raw, str):
            import json as _json
            try:
                state_raw = _json.loads(state_raw)
            except (ValueError, TypeError):
                pass

        result["api_responses"]["get_state_fallback_{0}".format(vid)] = {
            "method": "GET",
            "path": state_path,
            "body": state_raw,
        }

        # The state endpoint returns a list — find our VLAN
        if isinstance(state_raw, list):
            for entry in state_raw:
                if isinstance(entry, dict) and entry.get("vlanId") == vid:
                    iface_data = entry
                    break
        elif isinstance(state_raw, dict):
            for wrap_key in ("data", "items", "state", "interfaces",
                             "anycast_gateways"):
                wrapped = state_raw.get(wrap_key)
                if isinstance(wrapped, list):
                    for entry in wrapped:
                        if isinstance(entry, dict) and entry.get("vlanId") == vid:
                            iface_data = entry
                            break
                    if iface_data:
                        break

    if (
        iface_data
        and isinstance(iface_data, dict)
        and iface_data.get("vlanId") == vid
    ):
        current = _to_ansible_output(
            iface_data, state_map.get(vid)
        )
        current_map[vid] = current
        # Update module-level "before" to include
        # this interface missed by the bulk GET.
        result["before"] = sorted(
            current_map.values(),
            key=lambda x: x["vlan_id"],
        )
        return current
    return None


def _extract_iface_from_response(raw: Any, vid: int) -> Optional[Dict[str, Any]]:
    """Extract interface data for a specific vlan_id from a REST response."""
    if raw is None:
        return None
    # Direct list response
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and entry.get("vlanId") == vid:
                return entry
        return None
    # Dict response — check if it IS the interface
    if isinstance(raw, dict):
        if raw.get("vlanId") == vid:
            return raw
        # Check for error responses
        err = _extract_error(raw)
        if err:
            return None
        # Unwrap common wrappers
        for wrap_key in ("data", "items", "interfaces", "anycast_gateways"):
            wrapped = raw.get(wrap_key)
            if isinstance(wrapped, list):
                for entry in wrapped:
                    if isinstance(entry, dict) and entry.get("vlanId") == vid:
                        return entry
            elif isinstance(wrapped, dict) and wrapped.get("vlanId") == vid:
                return wrapped
    return None


def _process_entry_replaced(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    entry: Dict[str, Any],
    current: Dict[str, Any],
    modified_vids: List[int],
    gw_result: Dict[str, Any],
    result: Dict[str, Any],
) -> bool:
    """Handle REPLACED/OVERRIDDEN for an existing interface.

    Returns True if processing is complete (caller should continue to next entry).
    """
    # Check if immutable fields differ → need DELETE + re-POST
    immutable_diffs = _immutable_fields_differ(entry, current)

    # Also check if enabled differs (use factory defaults
    # for omitted fields in replaced/overridden)
    patch = _build_patch_payload(entry, current, use_factory_defaults=True)

    if not immutable_diffs and patch is None:
        # No changes needed — idempotent
        gw_result["after"] = current
        gw_result["changed"] = False
        gw_result["differences"] = {}
        result["anycast_gateways"].append(gw_result)
        return True

    if not immutable_diffs and patch is not None:
        # Only enabled changed — just PATCH
        result["changed"] = True
        gw_result["changed"] = True

        if not module.check_mode:
            modified_vids.append(vid)
            patch_path = AG_PATCH_PATH.format(vlan_id=vid)
            _call_api(
                module,
                connection,
                method="PATCH",
                path=patch_path,
                payload=patch,
                api_responses=result["api_responses"],
                response_key=f"replace_patch_{vid}",
            )
        gw_result["after"] = _predict_after_patch(
            entry, current, use_factory_defaults=True
        )
    else:
        # Immutable fields differ → DELETE + re-POST
        result["changed"] = True
        gw_result["changed"] = True

        # Default missing immutable fields from current config
        # to ensure POST payload is complete after DELETE
        merged_entry = dict(entry)
        for field in IMMUTABLE_FIELDS:
            if merged_entry.get(field) is None and current.get(field) is not None:
                merged_entry[field] = current[field]
        # For replaced/overridden, omitted enabled resets to
        # factory default (False), not preserved from current.
        if merged_entry.get("enabled") is None:
            merged_entry["enabled"] = FACTORY_DEFAULTS["enabled"]

        if not module.check_mode:
            modified_vids.append(vid)
            # DELETE existing (disable first if enabled)
            _disable_and_delete(
                module,
                connection,
                vid,
                current,
                result["api_responses"],
                "replace_delete",
            )
            # POST new
            post_payload = _build_post_payload(merged_entry)
            post_path = AG_VLAN_PATH.format(vlan_id=vid)
            _call_api(
                module,
                connection,
                method="POST",
                path=post_path,
                payload=post_payload,
                api_responses=result["api_responses"],
                response_key=f"replace_post_{vid}",
            )

            # POST does not support 'enabled' — PATCH it if non-default.
            desired_enabled = merged_entry.get("enabled")
            if desired_enabled is not None and desired_enabled != FACTORY_DEFAULTS["enabled"]:
                _patch_enabled_after_create(
                    module, connection, vid, desired_enabled,
                    result["api_responses"],
                )

        gw_result["after"] = _predict_after_replaced(merged_entry)
    return False


def _handle_merge_replace(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    config: List[Dict[str, Any]],
    current_map: Dict[int, Dict[str, Any]],
    state_map: Dict[int, Any],
    result: Dict[str, Any],
) -> List[int]:
    """MERGED/REPLACED/OVERRIDDEN per-entry processing. Returns modified_vids."""
    modified_vids: List[int] = []

    for entry in config:
        vid = entry["vlan_id"]
        gw_result: Dict[str, Any] = {"vlan_id": vid}
        current = current_map.get(vid)

        if current is None:
            # Bulk GET may not return all interfaces (known VOSS API
            # timing issue where recently-created interfaces are not
            # immediately visible).  Always try a targeted GET before
            # concluding the interface doesn't exist.
            current = _try_fallback_get(
                module, connection, vid, state_map, current_map, result
            )

        if current is None:
            # Interface does not exist — CREATE (POST)
            # Validate required fields for POST (interface creation)
            if entry.get("ip_address") is None:
                module.fail_json(
                    msg=(
                        "ip_address is required to create a new Anycast Gateway "
                        "interface (vlan_id={0})"
                    ).format(vid),
                    api_responses=result["api_responses"],
                )

            gw_result["before"] = {}
            result["changed"] = True
            gw_result["changed"] = True

            if not module.check_mode:
                modified_vids.append(vid)
                post_payload = _build_post_payload(entry)
                path = AG_VLAN_PATH.format(vlan_id=vid)

                # Wrap POST to provide a clear error for one_ip conflict.
                # We call connection.send_request directly (rather than
                # _call_api) so that ConnectionError is catchable here —
                # _call_api calls fail_json on HTTP errors immediately.
                try:
                    post_raw = connection.send_request(
                        post_payload, path=path, method="POST"
                    )
                except ConnectionError as exc:
                    err_msg = to_text(exc)
                    code = getattr(exc, "code", None)
                    result["api_responses"][f"post_{vid}"] = {
                        "method": "POST",
                        "path": path,
                        "error": err_msg,
                        "code": code,
                    }
                    if entry.get("one_ip") and (
                        "IP interface already configured" in err_msg
                        or "already configured" in err_msg.lower()
                    ):
                        module.fail_json(
                            msg=(
                                "Cannot create Anycast Gateway with one_ip=true "
                                "on VLAN {0}: {1}. ONE-IP mode requires the VLAN "
                                "to have no existing IP interface. Remove the IP "
                                "interface first (using extreme_fe_l3_interfaces "
                                "with state=deleted) or use one_ip=false."
                            ).format(vid, err_msg),
                            api_responses=result["api_responses"],
                        )
                    module.fail_json(
                        msg=f"REST API call failed: POST {path}: {err_msg}",
                        code=code,
                        err=getattr(exc, "err", None),
                        api_responses=result["api_responses"],
                    )
                else:
                    # Parse and record successful response
                    parsed = post_raw
                    if isinstance(post_raw, str):
                        import json as _json
                        try:
                            parsed = _json.loads(post_raw)
                        except (ValueError, TypeError):
                            pass
                    result["api_responses"][f"post_{vid}"] = {
                        "method": "POST",
                        "path": path,
                        "body": parsed,
                    }
                    # Check for in-band error payload
                    if isinstance(parsed, dict):
                        err = _extract_error(parsed)
                        if err:
                            if entry.get("one_ip") and (
                                "IP interface already configured" in err
                                or "already configured" in err.lower()
                            ):
                                module.fail_json(
                                    msg=(
                                        "Cannot create Anycast Gateway with one_ip=true "
                                        "on VLAN {0}: {1}. ONE-IP mode requires the VLAN "
                                        "to have no existing IP interface. Remove the IP "
                                        "interface first (using extreme_fe_l3_interfaces "
                                        "with state=deleted) or use one_ip=false."
                                    ).format(vid, err),
                                    api_responses=result["api_responses"],
                                )
                            module.fail_json(
                                msg=f"POST {path} returned an error: {err}",
                                api_responses=result["api_responses"],
                            )

                # POST does not support 'enabled' — if enabled=true was
                # requested, PATCH it separately (with retry for timing).
                desired_enabled = entry.get("enabled")
                if desired_enabled is not None and desired_enabled != FACTORY_DEFAULTS["enabled"]:
                    _patch_enabled_after_create(
                        module, connection, vid, desired_enabled,
                        result["api_responses"],
                    )

            gw_result["after"] = _predict_after_create(entry)

            gw_result["differences"] = _compute_diff(
                gw_result["before"], gw_result["after"]
            )
            result["anycast_gateways"].append(gw_result)
            continue

        # Interface EXISTS — update or recreate
        gw_result["before"] = current

        if state == STATE_MERGED:
            # Merged: only PATCH enabled. Fail if immutable fields differ.
            immutable_diffs = _immutable_fields_differ(entry, current)
            if immutable_diffs:
                module.fail_json(
                    msg=(
                        "Cannot update immutable fields {0} on existing "
                        "Anycast Gateway interface (vlan_id={1}). "
                        "Use state=replaced to recreate, or state=deleted first."
                    ).format(immutable_diffs, vid),
                    api_responses=result["api_responses"],
                )

            patch = _build_patch_payload(entry, current)
            if patch is None:
                # No changes needed
                gw_result["after"] = current
                gw_result["changed"] = False
                gw_result["differences"] = {}
                result["anycast_gateways"].append(gw_result)
                continue

            result["changed"] = True
            gw_result["changed"] = True

            if not module.check_mode:
                modified_vids.append(vid)
                patch_path = AG_PATCH_PATH.format(vlan_id=vid)
                _call_api(
                    module,
                    connection,
                    method="PATCH",
                    path=patch_path,
                    payload=patch,
                    api_responses=result["api_responses"],
                    response_key=f"patch_{vid}",
                )
            gw_result["after"] = _predict_after_patch(entry, current)

        else:
            # REPLACED / OVERRIDDEN — authoritative per-resource
            if _process_entry_replaced(
                module, connection, vid, entry, current,
                modified_vids, gw_result, result
            ):
                continue

        gw_result["differences"] = _compute_diff(
            gw_result["before"], gw_result["after"]
        )
        result["anycast_gateways"].append(gw_result)

    return modified_vids


def _capture_after_state(
    module: AnsibleModule,
    connection: Connection,
    current_map: Dict[int, Dict[str, Any]],
    modified_vids: List[int],
    result: Dict[str, Any],
) -> None:
    """Batch-fetch final state and capture module-level 'after'."""
    # ── Batch fetch after all operations (accurate final state) ───
    if result["changed"] and modified_vids and not module.check_mode:
        try:
            after_raw = _fetch_all_interfaces(
                module,
                connection,
                result["api_responses"],
                "after_batch_fetch",
            )
            after_state = _fetch_state_interfaces(
                module,
                connection,
                result["api_responses"],
                "state_after_batch_fetch",
            )
            for gw_res in result["anycast_gateways"]:
                res_vid = gw_res["vlan_id"]
                if res_vid not in modified_vids:
                    continue
                for r in after_raw:
                    if r.get("vlanId") == res_vid:
                        gw_res["after"] = _to_ansible_output(
                            r, after_state.get(res_vid)
                        )
                        gw_res["differences"] = _compute_diff(
                            gw_res["before"], gw_res["after"]
                        )
                        break
        except (ConnectionError, FeAnycastGwError):
            # If batch fetch fails, keep predicted values
            pass

    # Capture module-level "after" state when changes were made
    if result["changed"]:
        def _predict_after_action():
            amap = dict(current_map)
            for gw_res in result["anycast_gateways"]:
                vid = gw_res["vlan_id"]
                if gw_res.get("after"):
                    amap[vid] = gw_res["after"]
                else:
                    amap.pop(vid, None)
            return sorted(amap.values(), key=lambda x: x["vlan_id"])

        if not module.check_mode:
            try:
                final_raw = _fetch_all_interfaces(
                    module, connection, result["api_responses"], "after_all"
                )
                final_state = _fetch_state_interfaces(
                    module, connection, result["api_responses"], "state_after_all"
                )
                result["after"] = sorted(
                    _to_ansible_list(final_raw, final_state),
                    key=lambda x: x["vlan_id"],
                )
            except (ConnectionError, FeAnycastGwError):
                result["after"] = _predict_after_action()
        else:
            result["after"] = _predict_after_action()


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

    # Validate: no duplicate VLAN IDs in config
    if config:
        seen: set = set()
        for entry in config:
            vid = entry["vlan_id"]
            if vid in seen:
                module.fail_json(msg="Duplicate vlan_id {0} in config list".format(vid))
            seen.add(vid)

    # Validate all config entries
    for entry in config:
        _validate_entry(module, entry)

    result: Dict[str, Any] = {
        "changed": False,
        "anycast_gateways": [],
        "api_responses": {},
    }

    try:
        if state == STATE_GATHERED:
            _handle_gathered(module, connection, gather_filter, result)
            return

        # ── Fetch current state for change-making states ──────────────
        raw_list = _fetch_all_interfaces(
            module, connection, result["api_responses"], "configuration_before"
        )
        state_map = _fetch_state_interfaces(
            module, connection, result["api_responses"], "state_before"
        )
        current_map: Dict[int, Dict[str, Any]] = {}
        for raw in raw_list:
            out = _to_ansible_output(raw, state_map.get(raw.get("vlanId")))
            current_map[out["vlan_id"]] = out

        # Capture module-level "before" state
        result["before"] = sorted(current_map.values(), key=lambda x: x["vlan_id"])

        if state == STATE_DELETED:
            _handle_deleted(module, connection, config, current_map, state_map, result)
            return

        if state == STATE_OVERRIDDEN:
            _handle_overridden_prepass(
                module, connection, config, current_map, result
            )

        modified_vids = _handle_merge_replace(
            module, connection, state, config, current_map, state_map, result
        )

        _capture_after_state(module, connection, current_map, modified_vids, result)

        module.exit_json(**result)

    except FeAnycastGwError as exc:
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
