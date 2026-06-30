# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Ansible module to manage SPBM Layer 3 VSN (L3VSN / IPVPN) on Extreme
Fabric Engine (VOSS) switches.

REST API endpoints used:
  GET    /v0/configuration/spbm/l3vsn/vrf
         — list all L3VSN VPN instances across all VRFs
  POST   /v0/configuration/spbm/l3vsn/vrf/{vr_name}
         — create an IPv4 or IPv6 VPN instance for a VRF
  GET    /v0/configuration/spbm/l3vsn/vrf/{vr_name}
         — get L3VSN config for a specific VRF (returns array of instances)
  PATCH  /v0/configuration/spbm/l3vsn/vrf/{vr_name}/ipvpn-type/{ipvpn_type}
         — update VPN instance settings (isid, vpnEnabled, isidName)
  DELETE /v0/configuration/spbm/l3vsn/vrf/{vr_name}/ipvpn-type/{ipvpn_type}
         — delete a VPN instance for a VRF

Writable fields (POST / create):
  ipvpnType            — "IPv4" or "IPv6" (required for creation)
  isid                 — I-SID number, 0-15999999 (0 = unset / GlobalRouter;
                          values 16000000+ are reserved for dynamic L2 I-SIDs)
  vpnEnabled           — enable IP VPN node (requires EP1/Premier license)
  isidName             — descriptive name for the I-SID (0-64 chars)
  mvpn.enabled         — enable MVPN on this VRF (create-time only)
  mvpn.forwardCacheTimeout — MVPN forward cache timeout in seconds (create-time only)

Writable fields (PATCH / update):
  isid, vpnEnabled, isidName
  NOTE: mvpn settings are NOT in the PATCH schema (L3VsnUpdateSettings).
        They can only be set at creation time.

Read-only fields returned in output:
  vrf_name, ipvpn_type  (identifiers)
"""

from __future__ import annotations

# copy — used to deep-copy data structures so we can compare before/after without mutation
import copy
# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any, Dict, List, Optional, Tuple
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

# ── Ansible module metadata ──────────────────────────────────────────────────

DOCUMENTATION = r"""
module: extreme_fe_spbm_l3vsn
short_description: Manage SPBM L3VSN (IPVPN) on Extreme Fabric Engine switches
version_added: "1.2.0"
description:
  - Create, update, delete, and query SPBM Layer 3 Virtual Services Network
    (L3VSN / IPVPN) instances on Extreme Fabric Engine (VOSS) switches via
    the REST API.
  - Supports all five Ansible resource module states.
  - Configuration is grouped by VRF name with nested C(ipv4) and C(ipv6)
    sub-dictionaries, each representing one VPN instance.
  - MVPN settings (C(mvpn)) can only be set at creation time; they cannot
    be modified after the VPN instance exists.
  - For GlobalRouter (GRT), the I-SID is always 0 and cannot be changed.
    The C(vpn_enabled) field controls IP Shortcuts admin status on GRT.
author:
  - Extreme Networks
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI
    connection plugin.
  - Setting C(vpn_enabled=true) requires an EP1 or Premier license on the
    device. If the license is missing, the API returns an error which this
    module re-wraps with a clear message.
  - The PATCH endpoint only supports updating C(isid), C(vpn_enabled), and
    C(isid_name). The C(mvpn) settings are immutable after creation — to
    change them, delete the VPN instance and recreate it.
  - Filter I-SID lists (under the same REST path prefix) are NOT managed by
    this module. They will be handled by a future ISIS management module.
requirements:
  - ansible.netcommon
options:
  state:
    description:
      - Desired operation state.
      - C(merged) creates VPN instances that do not exist and updates settings
        on existing instances without removing unlisted ones.
      - C(replaced) makes the provided settings authoritative for each listed
        VRF. Omitted patchable fields are reset to factory defaults.
      - C(overridden) enforces the exact set of VPN instances globally —
        unlisted VPN instances are deleted, listed ones are created or updated.
      - C(deleted) removes VPN instances. If C(config) is omitted, all VPN
        instances across all VRFs are deleted. If a VRF entry has no C(ipv4)
        or C(ipv6) keys, both types are deleted for that VRF.
      - C(gathered) returns current L3VSN information without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - List of L3VSN configurations grouped by VRF.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional for C(deleted) (omit to delete all VPN instances) and C(gathered).
    type: list
    elements: dict
    suboptions:
      vrf_name:
        description:
          - VRF name (1-16 characters). This is the resource identifier.
          - Use C(GlobalRouter) for the default routing instance (GRT).
        type: str
        required: true
      ipv4:
        description:
          - IPv4 VPN instance settings for this VRF.
        type: dict
        suboptions:
          isid:
            description:
              - I-SID number (0-15999999). Value 0 means unset.
              - For GlobalRouter, I-SID is always 0.
            type: int
          vpn_enabled:
            description:
              - Enable the IP VPN node. Requires EP1/Premier license.
              - For GlobalRouter, this controls IP Shortcuts admin status.
            type: bool
          isid_name:
            description:
              - Descriptive name for the I-SID (0-64 characters).
            type: str
          mvpn:
            description:
              - MVPN (Multicast VPN) settings. These can only be set at
                creation time and cannot be modified after the VPN instance
                exists.
            type: dict
            suboptions:
              enabled:
                description:
                  - Enable MVPN on this VRF.
                  - For GlobalRouter, this controls Multicast over SPB.
                type: bool
              forward_cache_timeout:
                description:
                  - MVPN forward cache timeout in seconds (10-86400).
                type: int
      ipv6:
        description:
          - IPv6 VPN instance settings for this VRF.
        type: dict
        suboptions:
          isid:
            description:
              - I-SID number (0-15999999). Value 0 means unset.
              - For GlobalRouter, I-SID is always 0.
            type: int
          vpn_enabled:
            description:
              - Enable the IP VPN node. Requires EP1/Premier license.
            type: bool
          isid_name:
            description:
              - Descriptive name for the I-SID (0-64 characters).
            type: str
          mvpn:
            description:
              - MVPN (Multicast VPN) settings. These can only be set at
                creation time and cannot be modified after the VPN instance
                exists.
            type: dict
            suboptions:
              enabled:
                description:
                  - Enable MVPN on this VRF.
                type: bool
              forward_cache_timeout:
                description:
                  - MVPN forward cache timeout in seconds (10-86400).
                type: int
  gather_filter:
    description:
      - Limit gathered output to these VRF names.
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
# Task 1: Gather L3VSN configuration
# -------------------------------------------------------------------------
# - name: "Task 1: Gather L3VSN configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather current L3VSN configuration
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: gathered

# -------------------------------------------------------------------------
# Task 2: Create L3VSN instances
# -------------------------------------------------------------------------
# - name: "Task 2: Create L3VSN instances"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Create L3VSN for customer VRF
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: merged
    config:
      - vrf_name: customer-a
        ipv4:
          isid: 100
          vpn_enabled: true
          isid_name: cust-a-v4

- name: Create dual-stack L3VSN with MVPN
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: merged
    config:
      - vrf_name: customer-a
        ipv4:
          isid: 100
          vpn_enabled: true
          mvpn:
            enabled: true
            forward_cache_timeout: 300
        ipv6:
          isid: 200
          vpn_enabled: true

# -------------------------------------------------------------------------
# Task 3: Replace or override L3VSN instances
# -------------------------------------------------------------------------
# - name: "Task 3: Replace or override L3VSN configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Replace L3VSN config
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: replaced
    config:
      - vrf_name: customer-a
        ipv4:
          isid: 100
          vpn_enabled: true

- name: Override all L3VSN instances
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: overridden
    config:
      - vrf_name: customer-a
        ipv4:
          isid: 100
          vpn_enabled: true

# -------------------------------------------------------------------------
# Task 4: Delete L3VSN instances
# -------------------------------------------------------------------------
# - name: "Task 4: Delete L3VSN instances"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Delete IPv6 VPN instance for a VRF
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: deleted
    config:
      - vrf_name: customer-a
        ipv6: {}

- name: Delete all L3VSN for a VRF
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: deleted
    config:
      - vrf_name: customer-a

- name: Delete all L3VSN
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: deleted
"""

RETURN = r"""
before:
  description:
    - Full L3VSN resource configuration before changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
after:
  description:
    - Full L3VSN resource configuration after changes.
    - Only returned when the module made changes.
  returned: when changed
  type: list
  elements: dict
gathered:
  description:
    - L3VSN configuration gathered from the device.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
l3vsn:
  description: Per-resource L3VSN operation results with differences.
  returned: always
  type: list
  elements: dict
  contains:
    vrf_name:
      description: VRF name (resource identifier).
      type: str
    config:
      description: L3VSN configuration (returned by C(gathered) state).
      type: dict
      returned: when state is gathered
    before:
      description: L3VSN configuration before the operation.
      type: dict
      returned: when state is not gathered
    after:
      description: L3VSN configuration after the operation.
      type: dict
      returned: when state is not gathered
    changed:
      description: Whether this VRF's L3VSN was modified.
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
  description: Whether any L3VSN configuration was modified.
  returned: always
  type: bool
"""

# ── Constants ─────────────────────────────────────────────────────────────────

# REST endpoint to list all L3VSN VPN instances across all VRFs
L3VSN_LIST_PATH = "/v0/configuration/spbm/l3vsn/vrf"

# REST endpoint template to get/create L3VSN for a specific VRF
L3VSN_VRF_PATH = "/v0/configuration/spbm/l3vsn/vrf/{vr_name}"

# REST endpoint template to update/delete a specific VPN instance
L3VSN_INSTANCE_PATH = (
    "/v0/configuration/spbm/l3vsn/vrf/{vr_name}/ipvpn-type/{ipvpn_type}"
)

# Address type constants matching the REST API enum
IPV4 = "IPv4"
IPV6 = "IPv6"

# Both address types for iteration
ADDRESS_TYPES = (IPV4, IPV6)

# Ansible parameter key → address type mapping
ANSIBLE_KEY_TO_TYPE = {"ipv4": IPV4, "ipv6": IPV6}

# Address type → Ansible parameter key mapping
TYPE_TO_ANSIBLE_KEY = {IPV4: "ipv4", IPV6: "ipv6"}

# Maximum I-SID value for set (creation/update) operations.
# Values above 16000000 are reserved for dynamically-added L2 instances.
MAX_ISID_SET = 15999999

# Minimum valid I-SID for non-GRT VRFs (0 is reserved for GRT/unset)
MIN_ISID_NON_GRT = 1

# Maximum I-SID name length (from OpenAPI: maxLength 64)
MAX_ISID_NAME_LEN = 64

# MVPN forward cache timeout range (from OpenAPI: min 10, max 86400)
MVPN_FCT_MIN = 10
MVPN_FCT_MAX = 86400

# MVPN forward cache timeout default (from device factory default)
MVPN_FCT_DEFAULT = 210

# Factory defaults for patchable fields — used by replaced/overridden/deleted.
# NOTE: isid, vpnEnabled, and isidName are patchable via the REST API.
# isidName requires isid to be included in the same PATCH body for the device
# to accept it.  MVPN can only be set at creation time.
DEFAULTS: Dict[str, Any] = {
    "isid": 0,  # 0 means unset (from IsidZero schema)
    "vpn_enabled": False,  # default: false (from OpenAPI)
    "isid_name": "",  # default empty (from OpenAPI)
}

# FULL_DEFAULTS contains all patchable fields with their factory defaults.
# Omitted fields in replaced/overridden state are reset to these values.
FULL_DEFAULTS: Dict[str, Any] = dict(DEFAULTS)

# State constants
STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# ── Argument spec ─────────────────────────────────────────────────────────────

# MVPN sub-options (shared between ipv4 and ipv6)
_MVPN_SPEC: Dict[str, Any] = {
    "enabled": {"type": "bool"},
    "forward_cache_timeout": {"type": "int"},
}

# Per-address-family VPN instance sub-options
_INSTANCE_SPEC: Dict[str, Any] = {
    "isid": {"type": "int"},
    "vpn_enabled": {"type": "bool"},
    "isid_name": {"type": "str"},
    "mvpn": {
        "type": "dict",
        "options": _MVPN_SPEC,
    },
}

ARGUMENT_SPEC: Dict[str, Any] = {
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "vrf_name": {"type": "str", "required": True},
            "ipv4": {"type": "dict", "options": dict(_INSTANCE_SPEC)},
            "ipv6": {"type": "dict", "options": dict(_INSTANCE_SPEC)},
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


class FeSpbmL3vsnError(Exception):
    """Custom exception for L3VSN module errors."""

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
    """Check if a REST response indicates a 'not found' condition (404)."""
    if payload is None:
        return True
    if isinstance(payload, dict):
        status = payload.get("status") or payload.get("httpStatusCode")
        if status and int(status) == 404:
            return True
        errors = payload.get("errors") or payload.get("error")
        if errors:
            err_str = str(errors).lower()
            if "not found" in err_str or "does not exist" in err_str:
                return True
    return False


def _extract_error(payload: Any) -> Optional[str]:
    """Extract an error message from a REST response, if present."""
    if not isinstance(payload, dict):
        return None
    status = payload.get("status") or payload.get("httpStatusCode")
    if status and int(status) >= 400:
        msg = payload.get("message") or payload.get("msg") or str(payload)
        return "HTTP {0}: {1}".format(status, msg)
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
    allow_not_found: bool = False,
    api_responses: Dict[str, Any],
    response_key: str,
) -> Any:
    """
    Send a REST API request, record the response, and check for errors.

    Parameters:
        module:         AnsibleModule instance (for fail_json on connection error)
        connection:     HTTPAPI Connection object
        method:         HTTP method (GET, POST, PATCH, DELETE)
        path:           REST API path
        payload:        Request body (dict for JSON, None for no body)
        expect_content: Whether to expect/check a response body for errors
        allow_not_found: When True, HTTP 404 responses are treated as
                         non-fatal and the function returns None
        api_responses:  Dict to store raw API responses for debugging
        response_key:   Key name to store this response under
    Returns:
        Parsed response payload, or None if no content / not found
    Raises:
        FeSpbmL3vsnError: If the API returns an application-level error
    """
    try:
        raw = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        if allow_not_found and getattr(exc, "code", None) == 404:
            api_responses[response_key] = {
                "method": method,
                "path": path,
                "body": None,
            }
            return None
        exc_msg = to_text(exc)
        exc_lower = exc_msg.lower()
        if "license" in exc_lower or "premier" in exc_lower:
            module.fail_json(
                msg="vpnEnabled requires an EP1/Premier license on the "
                "device. {0} {1} returned: {2}".format(method, path, exc_msg),
                code=getattr(exc, "code", None),
                err=getattr(exc, "err", None),
                api_responses=api_responses,
            )
        module.fail_json(
            msg="REST API call failed: {0} {1}: {2}".format(method, path, exc_msg),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=api_responses,
        )

    # Parse response — send_request returns already-parsed JSON (dict/list/str/None)
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

    # Short-circuit for not-found responses in the body (some devices return
    # 200 with a JSON body containing status/httpStatusCode=404)
    if allow_not_found and parsed is not None and _is_not_found_response(parsed):
        return None

    # Check for application-level errors in the response body
    if expect_content and parsed is not None:
        err = _extract_error(parsed)
        if err:
            # Re-wrap license errors with a clearer message
            if isinstance(parsed, dict):
                err_lower = str(parsed).lower()
                if "license" in err_lower or "premier" in err_lower:
                    raise FeSpbmL3vsnError(
                        "vpnEnabled requires an EP1/Premier license on the "
                        "device. {0} {1} returned: {2}".format(method, path, err),
                        details={"response": parsed},
                    )
            raise FeSpbmL3vsnError(
                "{0} {1} returned an error: {2}".format(method, path, err),
                details={"response": parsed},
            )

    return parsed


# ── Data-fetching functions ───────────────────────────────────────────────────


def _fetch_all_l3vsn(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
    response_key: str = "get_all_l3vsn",
) -> List[Dict[str, Any]]:
    """
    GET /v0/configuration/spbm/l3vsn/vrf — retrieve all L3VSN VPN instances.

    Returns a flat list of L3Vsn objects, each containing:
      vrName, ipvpnType, isid, vpnEnabled, isidName, mvpn
    Multiple entries may share the same vrName (one per ipvpnType).
    """
    data = _call_api(
        module,
        connection,
        method="GET",
        path=L3VSN_LIST_PATH,
        expect_content=True,
        allow_not_found=True,
        api_responses=api_responses,
        response_key=response_key,
    )

    if data is None:
        return []

    # Response is a JSON array of L3Vsn objects
    if isinstance(data, list):
        return data

    # Some responses wrap the list in a dict
    if isinstance(data, dict):
        for key in ("l3vsn", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]

    return []


def _fetch_vrf_l3vsn(
    module: AnsibleModule,
    connection: Connection,
    vrf_name: str,
    api_responses: Dict[str, Any],
    response_key: str = "get_vrf_l3vsn",
) -> List[Dict[str, Any]]:
    """
    GET /v0/configuration/spbm/l3vsn/vrf/{vr_name} — retrieve L3VSN
    instances for a specific VRF.

    Returns an array of L3VsnSettings objects (one per ipvpnType).
    """
    path = L3VSN_VRF_PATH.format(vr_name=quote(vrf_name, safe=""))
    data = _call_api(
        module,
        connection,
        method="GET",
        path=path,
        expect_content=True,
        allow_not_found=True,
        api_responses=api_responses,
        response_key=response_key,
    )

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        return [data]

    return []


# ── Output formatter ─────────────────────────────────────────────────────────
# Converts raw REST API responses (device field names) into Ansible-friendly
# output format (snake_case field names matching the module's argument spec).


def _instance_to_ansible(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single REST VPN instance dict to Ansible output format.

    Maps REST field names to Ansible parameter names.
    """
    result: Dict[str, Any] = {}
    result["isid"] = raw.get("isid")
    result["vpn_enabled"] = raw.get("vpnEnabled")
    result["isid_name"] = raw.get("isidName", "")

    # MVPN sub-object
    mvpn_raw = raw.get("mvpn")
    if mvpn_raw and isinstance(mvpn_raw, dict):
        result["mvpn"] = {
            "enabled": mvpn_raw.get("enabled"),
            "forward_cache_timeout": mvpn_raw.get("forwardCacheTimeout"),
        }
    else:
        result["mvpn"] = {
            "enabled": None,
            "forward_cache_timeout": None,
        }

    return result


def _to_ansible_output(raw_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert the flat REST response list into grouped-by-VRF Ansible output.

    The GET /v0/configuration/spbm/l3vsn/vrf response returns one entry per
    VPN instance (e.g. VRF "A" with IPv4 and IPv6 yields two entries).
    This function groups them into:
      [{"vrf_name": "A", "ipv4": {...}, "ipv6": {...}}, ...]
    """
    # Group entries by VRF name (preserving insertion order)
    grouped: Dict[str, Dict[str, Any]] = {}

    for raw in raw_list:
        vrf_name = raw.get("vrName", "")
        ipvpn_type = raw.get("ipvpnType", "")

        if vrf_name not in grouped:
            grouped[vrf_name] = {"vrf_name": vrf_name}

        ansible_key = TYPE_TO_ANSIBLE_KEY.get(ipvpn_type)
        if ansible_key:
            grouped[vrf_name][ansible_key] = _instance_to_ansible(raw)

    return list(grouped.values())


def _build_current_map(
    ansible_list: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Build a lookup map: vrf_name (lowercase) → grouped Ansible output dict.

    Uses case-insensitive keys because VOSS normalises VRF names to
    lowercase, so the device-returned name may differ in case from the
    user-provided name.
    """
    return {entry["vrf_name"].lower(): entry for entry in ansible_list}


# ── Validation helpers ────────────────────────────────────────────────────────


def _validate_config(module: AnsibleModule, config: List[Dict[str, Any]]) -> None:
    """
    Validate config entries before sending any API requests.

    Checks: VRF name length, duplicate VRF names, I-SID ranges, I-SID name
    length, MVPN forward cache timeout range, GlobalRouter I-SID constraint.
    """
    seen_vrfs: set = set()

    for entry in config:
        vrf_name = entry["vrf_name"]

        # VRF name length (OpenAPI says 32, firmware enforces 16)
        if not vrf_name or len(vrf_name) > 16:
            module.fail_json(
                msg="VRF name must be 1-16 characters, got '{0}' ({1} chars)".format(
                    vrf_name, len(vrf_name) if vrf_name else 0
                )
            )

        # Duplicate VRF names (device normalizes VRF names case-insensitively)
        vrf_key = vrf_name.lower()
        if vrf_key in seen_vrfs:
            module.fail_json(
                msg="Duplicate VRF name '{0}' in config list".format(vrf_name)
            )
        seen_vrfs.add(vrf_key)

        is_grt = vrf_key == "globalrouter"

        # Validate each address family (ipv4, ipv6)
        for af_key in ("ipv4", "ipv6"):
            af_config = entry.get(af_key)
            if af_config is None:
                continue

            # I-SID validation
            isid = af_config.get("isid")
            if isid is not None:
                if is_grt and isid != 0:
                    module.fail_json(
                        msg="GlobalRouter I-SID must be 0, got {0} in {1}".format(
                            isid, af_key
                        )
                    )
                if (
                    not is_grt
                    and isid != 0
                    and (isid < MIN_ISID_NON_GRT or isid > MAX_ISID_SET)
                ):
                    module.fail_json(
                        msg="I-SID must be 0 (unset) or {0}-{1} for set "
                        "operations, got {2} in {3} for VRF '{4}'".format(
                            MIN_ISID_NON_GRT, MAX_ISID_SET, isid, af_key, vrf_name
                        )
                    )

            # I-SID name length
            isid_name = af_config.get("isid_name")
            if isid_name is not None and len(isid_name) > MAX_ISID_NAME_LEN:
                module.fail_json(
                    msg="isid_name must be 0-{0} characters, got {1} chars "
                    "in {2} for VRF '{3}'".format(
                        MAX_ISID_NAME_LEN, len(isid_name), af_key, vrf_name
                    )
                )

            # MVPN forward cache timeout range
            mvpn = af_config.get("mvpn")
            if mvpn:
                fct = mvpn.get("forward_cache_timeout")
                if fct is not None and (fct < MVPN_FCT_MIN or fct > MVPN_FCT_MAX):
                    module.fail_json(
                        msg="mvpn.forward_cache_timeout must be {0}-{1}, "
                        "got {2} in {3} for VRF '{4}'".format(
                            MVPN_FCT_MIN, MVPN_FCT_MAX, fct, af_key, vrf_name
                        )
                    )


# ── Diff / comparison logic ──────────────────────────────────────────────────
# Compares the "before" (current device state) with the "after" (desired state)
# to determine what changes need to be made. This drives idempotency — if
# before == after, no API calls are needed.


def _diff_instance(
    before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compare before and after dicts for a single VPN instance.

    Returns a dict of fields that differ: {field: {before: x, after: y}}.
    Only compares patchable fields (isid, vpn_enabled, isid_name) plus
    mvpn for informational output.
    """
    diff: Dict[str, Any] = {}
    before = before or {}
    after = after or {}

    for field in ("isid", "vpn_enabled", "isid_name"):
        val_b = before.get(field)
        val_a = after.get(field)
        if val_b != val_a:
            diff[field] = {"before": val_b, "after": val_a}

    # MVPN comparison (informational — these fields are create-time only)
    mvpn_b = before.get("mvpn") or {}
    mvpn_a = after.get("mvpn") or {}
    mvpn_diff: Dict[str, Any] = {}
    for field in ("enabled", "forward_cache_timeout"):
        val_b = mvpn_b.get(field)
        val_a = mvpn_a.get(field)
        if val_b != val_a:
            mvpn_diff[field] = {"before": val_b, "after": val_a}
    if mvpn_diff:
        diff["mvpn"] = mvpn_diff

    return diff


def _compute_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare before and after grouped-by-VRF dicts.

    Returns differences per address family:
      {"ipv4": {field_diffs}, "ipv6": {field_diffs}}
    """
    diff: Dict[str, Any] = {}
    for af_key in ("ipv4", "ipv6"):
        af_diff = _diff_instance(before.get(af_key), after.get(af_key))
        if af_diff:
            diff[af_key] = af_diff
    return diff


# ── Payload builders ─────────────────────────────────────────────────────────
# These functions convert Ansible parameters into the JSON payloads expected
# by the device REST API (POST for create, PATCH for update).


def _build_create_payload(af_config: Dict[str, Any], ipvpn_type: str) -> Dict[str, Any]:
    """
    Build a POST payload for creating a new VPN instance.

    The REST API expects the L3VsnCreateObject schema:
      {ipvpnType (required), isid, vpnEnabled, isidName, mvpn}
    """
    payload: Dict[str, Any] = {
        "ipvpnType": ipvpn_type,
    }

    # Patchable fields — only include if explicitly specified
    if af_config.get("isid") is not None:
        payload["isid"] = af_config["isid"]

    if af_config.get("vpn_enabled") is not None:
        payload["vpnEnabled"] = af_config["vpn_enabled"]

    if af_config.get("isid_name") is not None:
        payload["isidName"] = af_config["isid_name"]

    # MVPN settings — only settable at creation time
    mvpn = af_config.get("mvpn")
    if mvpn:
        mvpn_payload: Dict[str, Any] = {}
        if mvpn.get("enabled") is not None:
            mvpn_payload["enabled"] = mvpn["enabled"]
        if mvpn.get("forward_cache_timeout") is not None:
            mvpn_payload["forwardCacheTimeout"] = mvpn["forward_cache_timeout"]
        if mvpn_payload:
            payload["mvpn"] = mvpn_payload

    return payload


def _build_merged_patch(
    af_config: Dict[str, Any], current: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Build a PATCH payload for merged state.

    Only includes user-supplied fields that differ from current state.
    Returns None if no changes are needed.
    NOTE: mvpn fields are excluded — the PATCH schema does not support them.
    isidName requires isid in the same PATCH body; device ignores it otherwise.
    """
    patch: Dict[str, Any] = {}

    if af_config.get("isid") is not None:
        if af_config["isid"] != current.get("isid"):
            patch["isid"] = af_config["isid"]

    if af_config.get("vpn_enabled") is not None:
        if af_config["vpn_enabled"] != current.get("vpn_enabled"):
            patch["vpnEnabled"] = af_config["vpn_enabled"]

    if af_config.get("isid_name") is not None:
        if af_config["isid_name"] != current.get("isid_name"):
            patch["isidName"] = af_config["isid_name"]
            # Also include current isid — device requires it alongside isidName
            if "isid" not in patch:
                patch["isid"] = current.get("isid", 0)

    return patch if patch else None


def _build_replaced_patch(
    af_config: Dict[str, Any], current: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Build a PATCH payload for replaced/overridden state.

    Includes ALL patchable fields — user-supplied values for specified fields,
    FULL_DEFAULTS for omitted fields. Returns None if no changes needed.
    NOTE: isidName requires isid in the same PATCH body; mvpn is POST-only.
    """
    # Build complete desired state: user values + defaults for omitted
    desired_isid = af_config.get("isid")
    desired_isid = desired_isid if desired_isid is not None else FULL_DEFAULTS["isid"]

    desired_vpn = af_config.get("vpn_enabled")
    desired_vpn = (
        desired_vpn if desired_vpn is not None else FULL_DEFAULTS["vpn_enabled"]
    )

    desired_isid_name = af_config.get("isid_name")
    desired_isid_name = (
        desired_isid_name
        if desired_isid_name is not None
        else FULL_DEFAULTS["isid_name"]
    )

    # Compare with current and build patch
    patch: Dict[str, Any] = {}

    if desired_isid != current.get("isid"):
        patch["isid"] = desired_isid

    if desired_vpn != current.get("vpn_enabled"):
        patch["vpnEnabled"] = desired_vpn

    if desired_isid_name != current.get("isid_name"):
        patch["isidName"] = desired_isid_name
        # Device requires isid alongside isidName in the PATCH body
        if "isid" not in patch:
            patch["isid"] = current.get("isid", 0)

    return patch if patch else None


# ── Extracted helper functions for main() ─────────────────────────────────────
# Each function below implements one Ansible "state" (gathered, deleted,
# merged, replaced, overridden). They are called from main() based on the
# user's chosen state. This keeps main() short and readable.


def _handle_gathered(
    module: AnsibleModule,
    connection: Connection,
    gather_filter: List[str],
    result: Dict[str, Any],
) -> None:
    """Handle the GATHERED state — read-only, return current L3VSN state."""
    raw_list = _fetch_all_l3vsn(module, connection, result["api_responses"])
    all_vrfs = _to_ansible_output(raw_list)

    if gather_filter:
        filter_set = {f.lower() for f in gather_filter}
        all_vrfs = [v for v in all_vrfs if v["vrf_name"].lower() in filter_set]

    result["gathered"] = sorted(all_vrfs, key=lambda x: x["vrf_name"])
    result["l3vsn"] = [
        {"vrf_name": v["vrf_name"], "config": v} for v in result["gathered"]
    ]
    module.exit_json(**result)


def _handle_deleted(
    module: AnsibleModule,
    connection: Connection,
    config: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    all_vrfs: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Handle the DELETED state — remove VPN instances."""
    if config:
        delete_targets = _resolve_delete_targets(config)
    else:
        delete_targets = _resolve_delete_all(current_map)

    for vrf_name, af_types_to_delete in delete_targets:
        if vrf_name.lower() == "globalrouter":
            continue
        _delete_one_vrf(
            module, connection, vrf_name, af_types_to_delete,
            current_map, result,
        )

    # Capture module-level "after" for deleted state
    if result["changed"]:
        _capture_after_state_deleted(
            module, connection, all_vrfs, result
        )

    module.exit_json(**result)


def _delete_one_vrf(
    module: AnsibleModule,
    connection: Connection,
    vrf_name: str,
    af_types_to_delete: List[str],
    current_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Execute deletion of address families for a single VRF."""
    vrf_result: Dict[str, Any] = {"vrf_name": vrf_name}
    current = current_map.get(vrf_name.lower(), {"vrf_name": vrf_name})
    api_vrf_name = current.get("vrf_name", vrf_name)
    vrf_result["vrf_name"] = api_vrf_name
    vrf_result["before"] = current

    vrf_changed = False

    for ipvpn_type in af_types_to_delete:
        af_key = TYPE_TO_ANSIBLE_KEY[ipvpn_type]
        if af_key not in current:
            continue
        vrf_changed = True
        result["changed"] = True
        if not module.check_mode:
            path = L3VSN_INSTANCE_PATH.format(
                vr_name=quote(api_vrf_name, safe=""),
                ipvpn_type=quote(ipvpn_type, safe=""),
            )
            _call_api(
                module, connection, method="DELETE", path=path,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key="delete_{0}_{1}".format(vrf_name, af_key),
            )

    vrf_result["changed"] = vrf_changed
    _set_deleted_after_state(
        module, connection, vrf_name, api_vrf_name, af_types_to_delete,
        current, vrf_changed, vrf_result, result,
    )
    vrf_result["differences"] = _compute_diff(
        vrf_result["before"], vrf_result["after"]
    )
    result["l3vsn"].append(vrf_result)


def _set_deleted_after_state(
    module: AnsibleModule,
    connection: Connection,
    vrf_name: str,
    api_vrf_name: str,
    af_types_to_delete: List[str],
    current: Dict[str, Any],
    vrf_changed: bool,
    vrf_result: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """Set the after state for a deleted VRF entry."""
    if vrf_changed and not module.check_mode:
        after_raw = _fetch_vrf_l3vsn(
            module, connection, api_vrf_name,
            result["api_responses"],
            response_key="after_{0}".format(vrf_name),
        )
        if after_raw:
            after_grouped = {"vrf_name": api_vrf_name}
            for inst in after_raw:
                ipvpn_t = inst.get("ipvpnType", "")
                ak = TYPE_TO_ANSIBLE_KEY.get(ipvpn_t)
                if ak:
                    after_grouped[ak] = _instance_to_ansible(inst)
            vrf_result["after"] = after_grouped
        else:
            vrf_result["after"] = {"vrf_name": api_vrf_name}
    elif vrf_changed and module.check_mode:
        predicted = dict(current)
        for ipvpn_type in af_types_to_delete:
            ak = TYPE_TO_ANSIBLE_KEY[ipvpn_type]
            predicted.pop(ak, None)
        vrf_result["after"] = predicted
    else:
        vrf_result["after"] = current


def _capture_after_state_deleted(
    module: AnsibleModule,
    connection: Connection,
    all_vrfs: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Capture module-level after state for deleted operations."""
    def _predict():
        after_map = {v["vrf_name"].lower(): copy.deepcopy(v) for v in all_vrfs}
        for vrf_res in result["l3vsn"]:
            vname = vrf_res["vrf_name"]
            if vrf_res.get("after"):
                after_map[vname.lower()] = vrf_res["after"]
            else:
                after_map.pop(vname.lower(), None)
        return sorted(after_map.values(), key=lambda x: x["vrf_name"])

    if not module.check_mode:
        try:
            after_raw = _fetch_all_l3vsn(
                module, connection, result["api_responses"],
                "configuration_after",
            )
            result["after"] = sorted(
                _to_ansible_output(after_raw), key=lambda x: x["vrf_name"],
            )
        except (ConnectionError, FeSpbmL3vsnError):
            result["after"] = _predict()
    else:
        result["after"] = _predict()


def _handle_overridden_prepass(
    module: AnsibleModule,
    connection: Connection,
    config: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    """OVERRIDDEN pre-pass: delete unlisted VPN instances.

    Returns (override_before, override_deletes).
    """
    override_before: Dict[str, Dict[str, Any]] = {
        k: dict(v) for k, v in current_map.items()
    }

    config_af_set: set = set()
    config_vrf_lower: set = set()
    for entry in config:
        vrf_name = entry["vrf_name"]
        config_vrf_lower.add(vrf_name.lower())
        for af_key in ("ipv4", "ipv6"):
            if entry.get(af_key) is not None:
                config_af_set.add(
                    (vrf_name.lower(), ANSIBLE_KEY_TO_TYPE[af_key])
                )

    override_deletes: Dict[str, List[str]] = {}
    for vrf_name, current in current_map.items():
        if current.get("vrf_name", "").lower() == "globalrouter":
            continue
        for af_key in ("ipv4", "ipv6"):
            if af_key not in current:
                continue
            ipvpn_type = ANSIBLE_KEY_TO_TYPE[af_key]
            if (vrf_name, ipvpn_type) in config_af_set:
                continue
            override_deletes.setdefault(vrf_name, []).append(af_key)

    _execute_overridden_deletes(
        module, connection, override_deletes, current_map,
        override_before, config_vrf_lower, result,
    )

    return override_before, override_deletes


def _execute_overridden_deletes(
    module: AnsibleModule,
    connection: Connection,
    override_deletes: Dict[str, List[str]],
    current_map: Dict[str, Dict[str, Any]],
    override_before: Dict[str, Dict[str, Any]],
    config_vrf_lower: set,
    result: Dict[str, Any],
) -> None:
    """Execute batched deletions for overridden pre-pass."""
    for vrf_name, af_keys_to_delete in override_deletes.items():
        current = current_map[vrf_name]
        device_vrf_name = current.get("vrf_name", vrf_name)
        result["changed"] = True

        if not module.check_mode:
            for af_key in af_keys_to_delete:
                ipvpn_type = ANSIBLE_KEY_TO_TYPE[af_key]
                path = L3VSN_INSTANCE_PATH.format(
                    vr_name=quote(device_vrf_name, safe=""),
                    ipvpn_type=quote(ipvpn_type, safe=""),
                )
                _call_api(
                    module, connection, method="DELETE", path=path,
                    expect_content=False,
                    api_responses=result["api_responses"],
                    response_key="override_delete_{0}_{1}".format(
                        vrf_name, af_key
                    ),
                )

        for af_key in af_keys_to_delete:
            current.pop(af_key, None)

        if vrf_name not in config_vrf_lower:
            _emit_override_unlisted_result(
                module, connection, vrf_name, device_vrf_name,
                current, override_before, result,
            )


def _emit_override_unlisted_result(
    module: AnsibleModule,
    connection: Connection,
    vrf_name: str,
    device_vrf_name: str,
    current: Dict[str, Any],
    override_before: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Emit a result entry for VRFs not in config during overridden pre-pass."""
    before_snapshot = override_before.get(
        vrf_name, {"vrf_name": device_vrf_name}
    )
    if not module.check_mode:
        after_raw = _fetch_vrf_l3vsn(
            module, connection, device_vrf_name,
            result["api_responses"],
            response_key="override_after_{0}".format(vrf_name),
        )
        after_grouped: Dict[str, Any] = {"vrf_name": device_vrf_name}
        for inst in after_raw:
            ipvpn_t = inst.get("ipvpnType", "")
            ak = TYPE_TO_ANSIBLE_KEY.get(ipvpn_t)
            if ak:
                after_grouped[ak] = _instance_to_ansible(inst)
    else:
        after_grouped = dict(current)

    vrf_result: Dict[str, Any] = {
        "vrf_name": device_vrf_name,
        "before": before_snapshot,
        "after": after_grouped,
        "changed": True,
    }
    vrf_result["differences"] = _compute_diff(
        vrf_result["before"], vrf_result["after"]
    )
    result["l3vsn"].append(vrf_result)


def _process_af_create(
    module: AnsibleModule,
    connection: Connection,
    entry: Dict[str, Any],
    vrf_name: str,
    api_vrf_name: str,
    af_key: str,
    af_config: Dict[str, Any],
    state: str,
    result: Dict[str, Any],
) -> None:
    """Handle creation of a VPN instance that does not exist (POST)."""
    ipvpn_type = ANSIBLE_KEY_TO_TYPE[af_key]

    if state in (STATE_REPLACED, STATE_OVERRIDDEN):
        desired_vpn = af_config.get("vpn_enabled")
        if desired_vpn is None:
            desired_vpn = FULL_DEFAULTS["vpn_enabled"]
        desired_isid = af_config.get("isid")
        if desired_isid is None:
            desired_isid = FULL_DEFAULTS["isid"]
        is_grt = vrf_name.lower() == "globalrouter"
        if desired_vpn and desired_isid == 0 and not is_grt:
            raise FeSpbmL3vsnError(
                "Cannot enable VPN on VRF '{0}' ({1}) without "
                "an I-SID. Add 'isid' to your config — in "
                "state={2}, any field you leave out is reset "
                "to its default (isid defaults to 0).".format(
                    vrf_name, af_key, state
                )
            )

    result["changed"] = True

    if not module.check_mode:
        post_payload = _build_create_payload(af_config, ipvpn_type)
        path = L3VSN_VRF_PATH.format(
            vr_name=quote(api_vrf_name, safe="")
        )
        _call_api(
            module, connection, method="POST", path=path,
            payload=post_payload, expect_content=False,
            api_responses=result["api_responses"],
            response_key="create_{0}_{1}".format(vrf_name, af_key),
        )


def _process_af_update(
    module: AnsibleModule,
    connection: Connection,
    entry: Dict[str, Any],
    vrf_name: str,
    api_vrf_name: str,
    af_key: str,
    af_config: Dict[str, Any],
    current_af: Dict[str, Any],
    state: str,
    result: Dict[str, Any],
) -> bool:
    """Handle update of an existing VPN instance (PATCH). Returns True if changed."""
    mvpn_cfg = af_config.get("mvpn")
    if mvpn_cfg and any(v is not None for v in mvpn_cfg.values()):
        raise FeSpbmL3vsnError(
            "MVPN settings cannot be modified after creation. "
            "VRF '{0}' ({1}) already has a VPN instance. To "
            "change MVPN settings, delete the instance and "
            "recreate it.".format(vrf_name, af_key)
        )

    if state == STATE_MERGED:
        patch = _build_merged_patch(af_config, current_af)
    else:
        _validate_replaced_vpn_isid(vrf_name, af_key, af_config, state)
        patch = _build_replaced_patch(af_config, current_af)

    if patch is not None:
        result["changed"] = True
        if not module.check_mode:
            ipvpn_type = ANSIBLE_KEY_TO_TYPE[af_key]
            path = L3VSN_INSTANCE_PATH.format(
                vr_name=quote(api_vrf_name, safe=""),
                ipvpn_type=quote(ipvpn_type, safe=""),
            )
            _call_api(
                module, connection, method="PATCH", path=path,
                payload=patch, expect_content=False,
                api_responses=result["api_responses"],
                response_key="patch_{0}_{1}".format(vrf_name, af_key),
            )
        return True
    return False


def _validate_replaced_vpn_isid(
    vrf_name: str, af_key: str, af_config: Dict[str, Any], state: str
) -> None:
    """Pre-validate vpn_enabled=true requires a non-zero isid for replaced/overridden."""
    desired_vpn = af_config.get("vpn_enabled")
    if desired_vpn is None:
        desired_vpn = FULL_DEFAULTS["vpn_enabled"]
    desired_isid = af_config.get("isid")
    if desired_isid is None:
        desired_isid = FULL_DEFAULTS["isid"]
    is_grt = vrf_name.lower() == "globalrouter"
    if desired_vpn and desired_isid == 0 and not is_grt:
        raise FeSpbmL3vsnError(
            "Cannot enable VPN on VRF '{0}' ({1}) without "
            "an I-SID. Add 'isid' to your config — in "
            "state={2}, any field you leave out is reset "
            "to its default (isid defaults to 0).".format(
                vrf_name, af_key, state
            )
        )


def _handle_merge_replace(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    config: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
    override_before: Optional[Dict[str, Dict[str, Any]]] = None,
    override_deletes: Optional[Dict[str, List[str]]] = None,
) -> None:
    """Process listed entries for MERGED / REPLACED / OVERRIDDEN states."""
    for entry in config:
        vrf_name = entry["vrf_name"]
        vrf_result: Dict[str, Any] = {"vrf_name": vrf_name}
        current = current_map.get(vrf_name.lower(), {"vrf_name": vrf_name})
        api_vrf_name = current.get("vrf_name", vrf_name)
        vrf_result["vrf_name"] = api_vrf_name

        if (
            state == STATE_OVERRIDDEN
            and override_before is not None
            and vrf_name.lower() in override_before
        ):
            vrf_result["before"] = override_before[vrf_name.lower()]
        else:
            vrf_result["before"] = current

        vrf_changed = (
            state == STATE_OVERRIDDEN
            and override_deletes is not None
            and vrf_name.lower() in override_deletes
        )

        for af_key in ("ipv4", "ipv6"):
            af_config = entry.get(af_key)
            if af_config is None:
                continue

            current_af = current.get(af_key)
            if current_af is not None and current_af.get("isid", 0) == 0:
                current_af = None

            if current_af is None:
                _process_af_create(
                    module, connection, entry, vrf_name, api_vrf_name,
                    af_key, af_config, state, result,
                )
                vrf_changed = True
            else:
                changed = _process_af_update(
                    module, connection, entry, vrf_name, api_vrf_name,
                    af_key, af_config, current_af, state, result,
                )
                if changed:
                    vrf_changed = True

        vrf_result["changed"] = vrf_changed

        _set_merge_replace_after(
            module, connection, entry, vrf_name, api_vrf_name,
            current, state, vrf_changed, vrf_result, result,
        )
        vrf_result["differences"] = _compute_diff(
            vrf_result["before"], vrf_result["after"]
        )
        result["l3vsn"].append(vrf_result)


def _set_merge_replace_after(
    module: AnsibleModule,
    connection: Connection,
    entry: Dict[str, Any],
    vrf_name: str,
    api_vrf_name: str,
    current: Dict[str, Any],
    state: str,
    vrf_changed: bool,
    vrf_result: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """Set the after state for a merge/replace/override entry."""
    if vrf_changed and not module.check_mode:
        after_raw = _fetch_vrf_l3vsn(
            module, connection, api_vrf_name,
            result["api_responses"],
            response_key="after_{0}".format(vrf_name),
        )
        after_grouped: Dict[str, Any] = {"vrf_name": api_vrf_name}
        for inst in after_raw:
            ipvpn_t = inst.get("ipvpnType", "")
            ak = TYPE_TO_ANSIBLE_KEY.get(ipvpn_t)
            if ak:
                after_grouped[ak] = _instance_to_ansible(inst)
        vrf_result["after"] = after_grouped
    elif vrf_changed and module.check_mode:
        vrf_result["after"] = _predict_after_check_mode(
            entry, current, state
        )
    else:
        vrf_result["after"] = current


def _predict_after_check_mode(
    entry: Dict[str, Any],
    current: Dict[str, Any],
    state: str,
) -> Dict[str, Any]:
    """Predict after state in check mode for a single VRF entry."""
    predicted = dict(current)
    for af_key in ("ipv4", "ipv6"):
        af_config = entry.get(af_key)
        if af_config is None:
            continue
        current_af = current.get(af_key)
        if current_af is not None and current_af.get("isid", 0) == 0:
            current_af = None
        if current_af is None:
            predicted[af_key] = _predict_created_instance(af_config)
        else:
            predicted[af_key] = _predict_updated_instance(
                af_config, current_af, state
            )
    return predicted


def _predict_created_instance(af_config: Dict[str, Any]) -> Dict[str, Any]:
    """Predict the state of a newly created VPN instance."""
    predicted_af: Dict[str, Any] = {}
    for field in ("isid", "vpn_enabled"):
        val = af_config.get(field)
        predicted_af[field] = (
            val if val is not None else FULL_DEFAULTS.get(field)
        )
    predicted_af["isid_name"] = af_config.get("isid_name", "")
    mvpn = af_config.get("mvpn") or {}
    predicted_af["mvpn"] = {
        "enabled": mvpn.get("enabled", False),
        "forward_cache_timeout": mvpn.get(
            "forward_cache_timeout", MVPN_FCT_DEFAULT
        ),
    }
    if (
        af_config.get("isid_name") is None
        and predicted_af.get("isid", 0) != 0
    ):
        predicted_af["isid_name"] = "ISID-{0}".format(predicted_af["isid"])
    return predicted_af


def _predict_updated_instance(
    af_config: Dict[str, Any],
    current_af: Dict[str, Any],
    state: str,
) -> Dict[str, Any]:
    """Predict the state of an updated VPN instance."""
    predicted_af = dict(current_af)
    if state == STATE_MERGED:
        for field in ("isid", "vpn_enabled", "isid_name"):
            val = af_config.get(field)
            if val is not None:
                predicted_af[field] = val
    else:
        for field in ("isid", "vpn_enabled", "isid_name"):
            val = af_config.get(field)
            predicted_af[field] = (
                val if val is not None else FULL_DEFAULTS.get(field)
            )
    if (
        af_config.get("isid") is not None
        and af_config.get("isid_name") is None
        and predicted_af.get("isid") != current_af.get("isid")
        and predicted_af.get("isid", 0) != 0
    ):
        predicted_af["isid_name"] = "ISID-{0}".format(predicted_af["isid"])
    return predicted_af


def _capture_after_state(
    module: AnsibleModule,
    connection: Connection,
    all_vrfs: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Capture module-level after state when changes were made."""
    def _predict():
        after_map = {v["vrf_name"].lower(): copy.deepcopy(v) for v in all_vrfs}
        for vrf_res in result["l3vsn"]:
            vname = vrf_res["vrf_name"]
            if vrf_res.get("after"):
                after_map[vname.lower()] = vrf_res["after"]
            else:
                after_map.pop(vname.lower(), None)
        return sorted(after_map.values(), key=lambda x: x["vrf_name"])

    if not module.check_mode:
        try:
            after_raw = _fetch_all_l3vsn(
                module, connection, result["api_responses"],
                "configuration_after",
            )
            result["after"] = sorted(
                _to_ansible_output(after_raw), key=lambda x: x["vrf_name"],
            )
        except (ConnectionError, FeSpbmL3vsnError):
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

    # Config validation guard — merged/replaced/overridden require config
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN) and not config:
        module.fail_json(msg="'config' is required when state is '{0}'".format(state))

    # Pre-flight validation of config entries
    if config:
        _validate_config(module, config)

    result: Dict[str, Any] = {
        "changed": False,
        "l3vsn": [],
        "api_responses": {},
    }

    try:
        # ── GATHERED — read-only ──────────────────────────────────────────
        if state == STATE_GATHERED:
            _handle_gathered(module, connection, gather_filter, result)
            return

        # ── Fetch current state for change-making states ──────────────────
        raw_list = _fetch_all_l3vsn(
            module, connection, result["api_responses"], "configuration_before"
        )
        all_vrfs = _to_ansible_output(raw_list)
        current_map = _build_current_map(all_vrfs)

        result["before"] = copy.deepcopy(sorted(all_vrfs, key=lambda x: x["vrf_name"]))

        # ── DELETED ───────────────────────────────────────────────────────
        if state == STATE_DELETED:
            _handle_deleted(
                module, connection, config, current_map, all_vrfs, result
            )
            return

        # ── OVERRIDDEN pre-pass ───────────────────────────────────────────
        override_before: Optional[Dict[str, Dict[str, Any]]] = None
        override_deletes: Optional[Dict[str, List[str]]] = None
        if state == STATE_OVERRIDDEN:
            override_before, override_deletes = _handle_overridden_prepass(
                module, connection, config, current_map, result
            )

        # ── MERGED / REPLACED / OVERRIDDEN — per-entry loop ──────────────
        _handle_merge_replace(
            module, connection, state, config, current_map, result,
            override_before=override_before,
            override_deletes=override_deletes,
        )

        # ── Capture after state ───────────────────────────────────────────
        if result["changed"]:
            _capture_after_state(module, connection, all_vrfs, result)

        module.exit_json(**result)

    except FeSpbmL3vsnError as exc:
        module.fail_json(**exc.to_fail_kwargs(), api_responses=result["api_responses"])
    except ConnectionError as exc:
        module.fail_json(
            msg="Connection error: {0}".format(to_text(exc)),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=result["api_responses"],
        )


# ── Delete target resolution helpers ─────────────────────────────────────────


def _resolve_delete_targets(
    config: List[Dict[str, Any]],
) -> List[Tuple[str, List[str]]]:
    """
    Resolve which VPN instances to delete based on user config.

    Three levels:
      - vrf_name + ipv4/ipv6 specified → delete only specified types
      - vrf_name only (no ipv4/ipv6)   → delete both IPv4 and IPv6
      - empty config                   → handled by _resolve_delete_all()
    """
    targets: List[Tuple[str, List[str]]] = []

    for entry in config:
        vrf_name = entry["vrf_name"]
        has_ipv4 = entry.get("ipv4") is not None
        has_ipv6 = entry.get("ipv6") is not None

        if has_ipv4 or has_ipv6:
            # Delete only the specified address families
            af_types: List[str] = []
            if has_ipv4:
                af_types.append(IPV4)
            if has_ipv6:
                af_types.append(IPV6)
            targets.append((vrf_name, af_types))
        else:
            # No address family specified → delete both types
            targets.append((vrf_name, [IPV4, IPV6]))

    return targets


def _resolve_delete_all(
    current_map: Dict[str, Dict[str, Any]],
) -> List[Tuple[str, List[str]]]:
    """
    Build delete targets for all existing VPN instances across all VRFs.

    Used when state=deleted and config is empty or omitted.
    """
    targets: List[Tuple[str, List[str]]] = []

    for vrf_name, current in current_map.items():
        # Skip GlobalRouter — its L3VSN entry is system-managed
        if current.get("vrf_name", "").lower() == "globalrouter":
            continue
        # Use device-returned VRF name (not the lowercased dict key)
        device_vrf_name = current.get("vrf_name", vrf_name)
        af_types: List[str] = []
        for af_key in ("ipv4", "ipv6"):
            if af_key in current:
                af_types.append(ANSIBLE_KEY_TO_TYPE[af_key])
        if af_types:
            targets.append((device_vrf_name, af_types))

    return targets


if __name__ == "__main__":
    main()
