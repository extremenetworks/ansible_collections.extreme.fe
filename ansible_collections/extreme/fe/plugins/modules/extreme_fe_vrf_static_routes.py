# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Ansible module to manage static routes on Extreme Fabric Engine (VOSS)
switches.

REST API endpoints used:
  POST   /v0/configuration/vrf/{vr_name}/route
         — create a static route
  GET    /v0/configuration/vrf/{vr_name}/route
         — list static routes for a VRF
  PATCH  /v0/configuration/vrf/{vr_name}/route/
           {prefix_type}/{prefix}/{prefix_len}/{next_hop}
         — update a static route (next-hop variant)
  DELETE /v0/configuration/vrf/{vr_name}/route/
           {prefix_type}/{prefix}/{prefix_len}/{next_hop}
         — delete a static route (next-hop variant)
  PATCH  /v0/configuration/vrf/{vr_name}/route/
           {prefix_type}/{prefix}/{prefix_len}/interface/
           type/{local_iftype}/name/{local_ifname}
         — update a static route (interface variant)
  DELETE /v0/configuration/vrf/{vr_name}/route/
           {prefix_type}/{prefix}/{prefix_len}/interface/
           type/{local_iftype}/name/{local_ifname}
         — delete a static route (interface variant)
  PATCH  /v0/configuration/vrf/{vr_name}/route/
           {prefix_type}/{prefix}/{prefix_len}/{next_hop}/
           interface/type/{local_iftype}/name/{local_ifname}
         — update a static route (next-hop + interface variant)
  DELETE /v0/configuration/vrf/{vr_name}/route/
           {prefix_type}/{prefix}/{prefix_len}/{next_hop}/
           interface/type/{local_iftype}/name/{local_ifname}
         — delete a static route (next-hop + interface variant)
  GET    /v0/configuration/route
         — list all static routes across all VRFs
  GET    /v0/state/route
         — list dynamically learned routes
  GET    /v0/state/route/summary
         — route count summary per VRF

Writable fields (POST — create-time):
  prefix            — destination IP address (nested object)
  nextHop           — next-hop IP address (nested object)
  localInterfaceType — interface type (IPv6 only on VOSS)
  localInterfaceName — interface name (IPv6 only on VOSS)
  name              — optional route name (0-64 chars, VOSS only)
  preference        — administrative distance (1-255 for VOSS)
  weight            — route metric (1-65535 for VOSS)
  enabled           — route enabled/disabled (VOSS only)
  blackhole         — blackhole route flag

Writable fields (PATCH — update):
  enabled           — the only field updatable after creation

Read-only fields returned in output:
  defaultRoute      — true if prefix is 0.0.0.0/0 or ::/0
"""

from __future__ import annotations

# json — used for serializing/deserializing REST API request and response bodies
import json as _json
# ip_address / IPv6Address — standard library helpers for validating IP addresses
# and distinguishing IPv4 from IPv6 routes
from ipaddress import ip_address, IPv6Address
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
# Shared VRF name normalization logic
from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_vrf_utils import (
    normalize_vrf_name,
)

# ── Ansible module metadata ─────────────────────────────────────────────────

DOCUMENTATION = r"""
module: extreme_fe_vrf_static_routes
short_description: Manage static routes on Extreme Fabric Engine switches
version_added: "1.2.0"
description:
  - Create, update, delete, and query static routes on Extreme Fabric
    Engine (VOSS) switches via the REST API.
  - Supports all five Ansible resource module states.
  - Uses a nested configuration structure grouped by VRF, address
    family, and destination prefix — matching the vendor-standard
    pattern used by Cisco IOS, NX-OS, Arista EOS, and Juniper Junos.
  - A static route is uniquely identified by the combination of VRF
    name, address family, destination prefix, next-hop address, and
    optionally a local interface.
  - The only field that can be updated after creation is C(enabled).
    All other fields (C(admin_distance), C(weight), C(name),
    C(blackhole)) are set at creation time. For C(state=replaced)
    and C(state=overridden), changing these fields triggers a
    DELETE followed by re-POST.
author:
  - Extreme Networks
notes:
  - Requires the C(ansible.netcommon) collection and the
    C(extreme_fe) HTTPAPI connection plugin.
  - On VOSS, C(interface_type) and C(interface) are read-only for
    IPv4 routes. These fields are only accepted for IPv6 routes
    (needed for link-local next-hop addresses).
  - The C(admin_distance) range on VOSS is 1-255 for static routes.
    The broader range 0-65534 applies to EXOS only.
  - The C(weight) range on VOSS is 1-65535.
  - VRF names are limited to 1-16 characters on VOSS firmware.
  - The C(default_route) field is auto-detected by the device when
    the prefix is 0.0.0.0/0 (IPv4) or ::/0 (IPv6) and is returned
    as read-only output.
  - The C(blackhole) and C(forward_router_address) fields are
    mutually exclusive — a blackhole route has no next hop.
requirements:
  - ansible.netcommon
options:
  config:
    description:
      - List of VRF-scoped route configuration entries.
      - Each entry contains a VRF name and a list of address
        families, each containing routes and their next hops.
    type: list
    elements: dict
    suboptions:
      vrf:
        description:
          - Name of the VRF (Virtual Routing and Forwarding instance).
          - Must be 1-16 characters on VOSS.
        type: str
        required: true
      address_families:
        description:
          - List of address family entries (IPv4 or IPv6).
        type: list
        elements: dict
        suboptions:
          afi:
            description:
              - Address family identifier.
            type: str
            required: true
            choices:
              - ipv4
              - ipv6
          routes:
            description:
              - List of destination prefix entries.
            type: list
            elements: dict
            suboptions:
              prefix:
                description:
                  - Destination IP address (without mask).
                  - Example IPv4 C(10.0.0.0), IPv6 C(2001:db8::).
                type: str
                required: true
              prefix_len:
                description:
                  - Prefix mask length in bits.
                  - Range 0-32 for IPv4, 0-128 for IPv6.
                type: int
                required: true
              next_hops:
                description:
                  - List of next-hop entries for this prefix.
                type: list
                elements: dict
                suboptions:
                  forward_router_address:
                    description:
                      - Next-hop IP address.
                      - Mutually exclusive with C(blackhole).
                    type: str
                  interface_type:
                    description:
                      - Type of local interface for the next hop.
                      - Only accepted for IPv6 routes on VOSS.
                      - Required when using link-local IPv6
                        next-hop addresses.
                    type: str
                    choices:
                      - port
                      - vlan
                      - ip_tunnel
                      - oob
                  interface:
                    description:
                      - Local interface name or ID.
                      - For C(vlan) type, this is the VLAN ID.
                      - For C(port) type, the physical port name.
                      - Only accepted for IPv6 routes on VOSS.
                    type: str
                  admin_distance:
                    description:
                      - Administrative distance (preference).
                      - Range 1-255 on VOSS.
                      - Lower values are preferred.
                      - Set at creation time only (not patchable).
                    type: int
                  weight:
                    description:
                      - Route metric (cost).
                      - Range 1-65535 on VOSS.
                      - Used for route selection when the same
                        prefix is learned from the same protocol.
                      - Set at creation time only (not patchable).
                    type: int
                  name:
                    description:
                      - Optional name for the route.
                      - Maximum 64 characters. VOSS only.
                      - Set at creation time only (not patchable).
                    type: str
                  enabled:
                    description:
                      - Whether the route is enabled.
                      - VOSS only. The only field that can be
                        updated after creation via PATCH.
                    type: bool
                  blackhole:
                    description:
                      - Whether this is a blackhole (null) route.
                      - Mutually exclusive with
                        C(forward_router_address).
                      - Set at creation time only (not patchable).
                    type: bool
  state:
    description:
      - The desired state of the static route configuration.
    type: str
    choices:
      - merged
      - replaced
      - overridden
      - deleted
      - gathered
    default: merged
  gather_filter:
    description:
      - List of VRF names to limit gathered output.
      - When omitted, all VRFs are returned.
    type: list
    elements: str
  gather_dynamic:
    description:
      - When C(true) and C(state=gathered), also return
        dynamically learned routes from the routing table.
    type: bool
    default: false
  gather_summary:
    description:
      - When C(true) and C(state=gathered), also return the
        route count summary per VRF.
    type: bool
    default: false
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
# Task 1: Create a static route (merged)
# -------------------------------------------------------------------------
# - name: "Task 1: Create static route"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Create a static route (merged)
  extreme.fe.extreme_fe_vrf_static_routes:
    state: merged
    config:
      - vrf: globalrouter
        address_families:
          - afi: ipv4
            routes:
              - prefix: "10.0.0.0"
                prefix_len: 24
                next_hops:
                  - forward_router_address: "192.168.1.1"
                    admin_distance: 10
                    weight: 1
                    enabled: true

# -------------------------------------------------------------------------
# Task 2: Replace and override route sets
# -------------------------------------------------------------------------
# - name: "Task 2: Replace and override routes"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Replace routes for a prefix (replaced)
  extreme.fe.extreme_fe_vrf_static_routes:
    state: replaced
    config:
      - vrf: vrf101
        address_families:
          - afi: ipv4
            routes:
              - prefix: "10.0.0.0"
                prefix_len: 24
                next_hops:
                  - forward_router_address: "192.168.2.1"
                    admin_distance: 5

- name: Override all routes (overridden)
  extreme.fe.extreme_fe_vrf_static_routes:
    state: overridden
    config:
      - vrf: globalrouter
        address_families:
          - afi: ipv4
            routes:
              - prefix: "10.0.0.0"
                prefix_len: 24
                next_hops:
                  - forward_router_address: "192.168.1.1"

# -------------------------------------------------------------------------
# Task 3: Delete route configuration
# -------------------------------------------------------------------------
# - name: "Task 3: Delete route configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Delete specific routes (deleted)
  extreme.fe.extreme_fe_vrf_static_routes:
    state: deleted
    config:
      - vrf: vrf101
        address_families:
          - afi: ipv4
            routes:
              - prefix: "10.0.0.0"
                prefix_len: 24
                next_hops:
                  - forward_router_address: "192.168.1.1"

- name: Delete all routes on a VRF (deleted)
  extreme.fe.extreme_fe_vrf_static_routes:
    state: deleted
    config:
      - vrf: vrf101

# -------------------------------------------------------------------------
# Task 4: Gather route data
# -------------------------------------------------------------------------
# - name: "Task 4: Gather route data"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather all static routes (gathered)
  extreme.fe.extreme_fe_vrf_static_routes:
    state: gathered

- name: Gather with dynamic routes and summary
  extreme.fe.extreme_fe_vrf_static_routes:
    state: gathered
    gather_filter:
      - globalrouter
    gather_dynamic: true
    gather_summary: true

# -------------------------------------------------------------------------
# Task 5: IPv6 and blackhole route examples
# -------------------------------------------------------------------------
# - name: "Task 5: IPv6 and blackhole route examples"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Create an IPv6 route with local interface
  extreme.fe.extreme_fe_vrf_static_routes:
    state: merged
    config:
      - vrf: globalrouter
        address_families:
          - afi: ipv6
            routes:
              - prefix: "2001:db8::"
                prefix_len: 32
                next_hops:
                  - forward_router_address: "fe80::1"
                    interface_type: vlan
                    interface: "100"

- name: Create a blackhole route
  extreme.fe.extreme_fe_vrf_static_routes:
    state: merged
    config:
      - vrf: globalrouter
        address_families:
          - afi: ipv4
            routes:
              - prefix: "192.168.99.0"
                prefix_len: 24
                next_hops:
                  - blackhole: true
"""

RETURN = r"""
before:
  description:
    - Full resource configuration before changes.
    - Returned for action states (merged, replaced, overridden,
      deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
  contains:
    vrf:
      description: VRF name.
      type: str
    address_families:
      description: Per-address-family route data.
      type: list
      elements: dict
      contains:
        afi:
          description: Address family (ipv4 or ipv6).
          type: str
        routes:
          description: Route entries.
          type: list
          elements: dict
          contains:
            prefix:
              description: Destination IP address.
              type: str
            prefix_len:
              description: Prefix mask length.
              type: int
            next_hops:
              description: Next-hop entries.
              type: list
              elements: dict
              contains:
                forward_router_address:
                  description: Next-hop IP address.
                  type: str
                interface_type:
                  description: Local interface type.
                  type: str
                interface:
                  description: Local interface name.
                  type: str
                admin_distance:
                  description: Administrative distance.
                  type: int
                weight:
                  description: Route metric.
                  type: int
                name:
                  description: Route name.
                  type: str
                enabled:
                  description: Route enabled status.
                  type: bool
                blackhole:
                  description: Blackhole route flag.
                  type: bool
                default_route:
                  description: >-
                    True if this is a default route
                    (0.0.0.0/0 or ::/0).
                  type: bool
after:
  description:
    - Full resource configuration after changes.
    - Only returned when the module made changes and not in check mode.
  returned: when changed and not check_mode
  type: list
  elements: dict
gathered:
  description:
    - Resource configuration gathered from the device.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
differences:
  description:
    - Fields that changed between before and after states.
    - Only returned when the module made changes and not in check mode.
    - Contains added_count, removed_count, modified_count, and
      per-route field-level changes.
  returned: when changed and not check_mode
  type: dict
dynamic_routes:
  description: >-
    Dynamically learned routes. Only returned when
    C(gather_dynamic=true).
  returned: when gather_dynamic is true
  type: list
route_summary:
  description: >-
    Route count summary per VRF. Only returned when
    C(gather_summary=true).
  returned: when gather_summary is true
  type: list
api_responses:
  description: Raw REST API responses for debugging.
  returned: always
  type: dict
changed:
  description: Whether any route was modified.
  returned: always
  type: bool
"""

# ── Constants ────────────────────────────────────────────────────────────────

# REST endpoint templates
# VRF-scoped route collection (GET all, POST create)
ROUTE_LIST_PATH = "/v0/configuration/vrf/{vr_name}/route"

# Route with next-hop (PATCH, DELETE)
ROUTE_NH_PATH = (
    "/v0/configuration/vrf/{vr_name}/route"
    "/{prefix_type}/{prefix}/{prefix_len}/{next_hop}"
)

# Route with local interface only (PATCH, DELETE)
ROUTE_IF_PATH = (
    "/v0/configuration/vrf/{vr_name}/route"
    "/{prefix_type}/{prefix}/{prefix_len}"
    "/interface/type/{local_iftype}/name/{local_ifname}"
)

# Route with next-hop + local interface (PATCH, DELETE)
ROUTE_NH_IF_PATH = (
    "/v0/configuration/vrf/{vr_name}/route"
    "/{prefix_type}/{prefix}/{prefix_len}/{next_hop}"
    "/interface/type/{local_iftype}/name/{local_ifname}"
)

# Cross-VRF static route list (GET only)
ROUTE_ALL_PATH = "/v0/configuration/route"

# Dynamic route state (GET only)
ROUTE_STATE_PATH = "/v0/state/route"

# Route summary (GET only)
ROUTE_SUMMARY_PATH = "/v0/state/route/summary"

# Ansible → REST field name mapping for next-hop level fields
FIELD_MAP: Dict[str, str] = {
    "admin_distance": "preference",
    "weight": "weight",
    "name": "name",
    "enabled": "enabled",
    "blackhole": "blackhole",
}

# Interface type Ansible → REST enum mapping
IF_TYPE_MAP: Dict[str, str] = {
    "port": "PORT",
    "vlan": "VLAN",
    "ip_tunnel": "IP_TUNNEL",
    "oob": "OOB",
}

# REST → Ansible interface type mapping
IF_TYPE_MAP_REV: Dict[str, str] = {v: k for k, v in IF_TYPE_MAP.items()}

# Factory defaults for the only patchable field
# preference, weight, name, blackhole are create-time only
FULL_DEFAULTS: Dict[str, Any] = {
    "enabled": True,  # VOSS default: routes are enabled
}

# Defaults applied to POST payloads when the user omits the field.
# The VOSS REST API defaults omitted weight to 0 which violates the
# minimum (1), so we must always send at least weight=1.
# Also used by replaced/overridden to detect when create-time fields
# should be reset to device defaults (DELETE + re-POST).
CREATE_DEFAULTS: Dict[str, Any] = {
    "weight": 1,
    "blackhole": False,
}

# VRF name length limit on VOSS firmware
VRF_NAME_MAX_LEN = 16

# VOSS-specific ranges for static route fields
ADMIN_DISTANCE_MIN = 1
ADMIN_DISTANCE_MAX = 255
WEIGHT_MIN = 1
WEIGHT_MAX = 65535
ROUTE_NAME_MAX_LEN = 64
PREFIX_LEN_MAX_IPV4 = 32
PREFIX_LEN_MAX_IPV6 = 128

# Management VRF — routes are skipped during bulk operations.
# Protected in state=overridden (when pruning VRFs not in config) and
# state=deleted with no config (delete-all).  GlobalRouter routes are
# NOT protected.  Users can still explicitly target MgmtRouter in
# state=merged, state=replaced, or state=deleted with a specific
# config entry.
SYSTEM_VRFS = {"MgmtRouter"}

# Re-export for backward compatibility; actual logic is in module_utils.
_normalize_vrf_name = normalize_vrf_name

# State constants
STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# ── Argument spec ────────────────────────────────────────────────────────────

_NEXT_HOP_SPEC: Dict[str, Any] = {
    "forward_router_address": {"type": "str"},
    "interface_type": {
        "type": "str",
        "choices": ["port", "vlan", "ip_tunnel", "oob"],
    },
    "interface": {"type": "str"},
    "admin_distance": {"type": "int"},
    "weight": {"type": "int"},
    "name": {"type": "str"},
    "enabled": {"type": "bool"},
    "blackhole": {"type": "bool"},
}

_ROUTE_SPEC: Dict[str, Any] = {
    "prefix": {"type": "str", "required": True},
    "prefix_len": {"type": "int", "required": True},
    "next_hops": {
        "type": "list",
        "elements": "dict",
        "options": dict(_NEXT_HOP_SPEC),
    },
}

_AF_SPEC: Dict[str, Any] = {
    "afi": {
        "type": "str",
        "required": True,
        "choices": ["ipv4", "ipv6"],
    },
    "routes": {
        "type": "list",
        "elements": "dict",
        "options": dict(_ROUTE_SPEC),
    },
}

_CONFIG_SPEC: Dict[str, Any] = {
    "vrf": {"type": "str", "required": True},
    "address_families": {
        "type": "list",
        "elements": "dict",
        "options": dict(_AF_SPEC),
    },
}

ARGUMENT_SPEC: Dict[str, Any] = {
    "config": {
        "type": "list",
        "elements": "dict",
        "options": dict(_CONFIG_SPEC),
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
    "gather_dynamic": {"type": "bool", "default": False},
    "gather_summary": {"type": "bool", "default": False},
}


# ── Custom exception ─────────────────────────────────────────────────────────


class FeStaticRouteError(Exception):
    """Custom exception for static route module errors."""

    def __init__(
        self,
        message: str,
        *,
        details: Optional[Dict[str, object]] = None,
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, object]:
        data: Dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# ── Helper functions ─────────────────────────────────────────────────────────
# These utility functions handle common tasks: detecting errors in REST
# responses, establishing the device connection, and sending API requests.


def _is_not_found_response(payload: Any) -> bool:
    """Check if a REST response indicates a 'not found' condition."""
    if payload is None:
        return True
    if isinstance(payload, dict):
        status = payload.get("status") or payload.get("httpStatusCode")
        try:
            if status and int(status) == 404:
                return True
        except (ValueError, TypeError):
            pass
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
    # Check HTTP status code fields
    status = payload.get("status") or payload.get("httpStatusCode")
    try:
        if status and int(status) >= 400:
            msg = payload.get("message") or payload.get("msg") or str(payload)
            return "HTTP {0}: {1}".format(status, msg)
    except (ValueError, TypeError):
        pass
    # Check errorCode / statusCode / code fields
    for code_key in ("errorCode", "statusCode", "code"):
        code_val = payload.get(code_key)
        try:
            if code_val is not None and int(code_val) >= 400:
                msg = (
                    payload.get("errorMessage")
                    or payload.get("message")
                    or payload.get("detail")
                    or str(payload)
                )
                return "HTTP {0}: {1}".format(code_val, msg)
        except (ValueError, TypeError):
            pass
    # Check for errors list
    if "errors" in payload and payload["errors"]:
        msgs = [
            (e.get("message", str(e)) if isinstance(e, dict) else str(e))
            for e in payload["errors"]
        ]
        return "; ".join(msgs)
    # Check for error key (guard against null/empty)
    if "error" in payload:
        err = payload["error"]
        if err:
            if isinstance(err, dict):
                return err.get("message", str(err))
            return str(err)
    return None


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    payload: Any = None,
    api_responses: Dict[str, Any],
    response_key: str,
) -> Any:
    """Send a REST API request and record the response.

    Args:
        module:         AnsibleModule instance (for fail_json).
        connection:     HTTPAPI Connection object.
        method:         HTTP method (GET, POST, PATCH, DELETE).
        path:           REST API path.
        payload:        Request body (dict or None).
        api_responses:  Dict to store raw responses for debugging.
        response_key:   Key name to store this response under.

    Returns:
        Parsed response payload, or None.
    """
    try:
        raw = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        exc_code = getattr(exc, "code", None)
        # Treat GET+404 as "no data" instead of hard-failing — the
        # endpoint may not exist for VRFs without routes.
        if method == "GET" and exc_code == 404:
            api_responses[response_key] = {
                "method": method,
                "path": path,
                "body": None,
                "note": "404 treated as empty",
            }
            return None
        # Treat GET errors gracefully for known non-fatal cases:
        # - "does not exist" / "not found": VRF or resource absent,
        #   treated as empty for all GET endpoints.
        # - "not supported": only for optional state endpoints
        #   (/v0/state/route, /v0/state/route/summary) that may
        #   not exist on all device models.
        if method == "GET":
            err_text = to_text(exc).lower()
            if "does not exist" in err_text or "not found" in err_text:
                api_responses[response_key] = {
                    "method": method,
                    "path": path,
                    "body": None,
                    "note": "resource does not exist, treated as empty",
                }
                return None
            if "not supported" in err_text and (
                    ROUTE_STATE_PATH in path
                    or ROUTE_SUMMARY_PATH in path
                ):
                api_responses[response_key] = {
                    "method": method,
                    "path": path,
                    "body": None,
                    "note": "endpoint not supported on this device",
                }
                return None
        # For POST/PATCH, propagate "duplicate route" errors as
        # FeStaticRouteError so callers can handle them gracefully
        # (e.g. fall back to PATCH).  The VOSS HTTPAPI may raise
        # ConnectionError for 4xx responses before we get to parse
        # the body.  Only match when the error text explicitly
        # mentions "duplicate" to avoid misclassifying unrelated
        # 422 failures (e.g. "Invalid route cost").
        if method in ("POST", "PATCH"):
            err_text = to_text(exc).lower()
            if "duplicate" in err_text:
                api_responses[response_key] = {
                    "method": method,
                    "path": path,
                    "body": None,
                    "note": "duplicate route (ConnectionError)",
                }
                raise FeStaticRouteError(
                    "{0} {1}: {2}".format(method, path, to_text(exc)),
                    details={"code": exc_code},
                )
        module.fail_json(
            msg=(
                "REST API call failed: {0} {1}: {2}".format(method, path, to_text(exc))
            ),
            code=exc_code,
            err=getattr(exc, "err", None),
            api_responses=api_responses,
        )

    # Parse response body
    parsed = None
    if raw is not None:
        if isinstance(raw, (dict, list)):
            parsed = raw
        elif isinstance(raw, str):
            try:
                parsed = _json.loads(raw)
            except (ValueError, TypeError):
                parsed = raw

    api_responses[response_key] = {
        "method": method,
        "path": path,
        "body": parsed,
    }

    # Check for errors in the parsed response
    if parsed is not None and isinstance(parsed, (dict, list)):
        if isinstance(parsed, dict):
            err = _extract_error(parsed)
            if err:
                raise FeStaticRouteError(
                    "{0} {1} returned an error: {2}".format(method, path, err),
                    details={"response": parsed},
                )

    return parsed


# ── REST ↔ Ansible transformation helpers ────────────────────────────────────
# These functions translate between REST API field names (camelCase) and
# Ansible parameter names (snake_case). This bidirectional mapping is needed
# because the device speaks one format and Ansible users expect another.


def _rest_route_to_ansible(
    rest_route: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert a single REST IpStaticRoute object to Ansible format.

    REST nests prefix/nextHop as objects with ipAddressType and
    address fields.  This flattens them to the Ansible parameter
    names.
    """
    nh: Dict[str, Any] = {}

    # Next-hop address
    next_hop_obj = rest_route.get("nextHop")
    if next_hop_obj and isinstance(next_hop_obj, dict):
        addr = next_hop_obj.get("address")
        if addr:
            nh["forward_router_address"] = addr

    # Local interface
    if_type = rest_route.get("localInterfaceType")
    if if_type and if_type != "NONE":
        nh["interface_type"] = IF_TYPE_MAP_REV.get(if_type, if_type)
    if_name = rest_route.get("localInterfaceName")
    if if_name:
        nh["interface"] = if_name

    # Scalar fields via FIELD_MAP
    for ansible_key, rest_key in FIELD_MAP.items():
        val = rest_route.get(rest_key)
        if val is not None:
            nh[ansible_key] = val

    # Read-only: defaultRoute
    default_route = rest_route.get("defaultRoute")
    if default_route is not None:
        nh["default_route"] = default_route

    # Extract prefix info for the route-level fields
    prefix_obj = rest_route.get("prefix")
    prefix_str = ""
    prefix_len = 0
    afi = "ipv4"
    if prefix_obj and isinstance(prefix_obj, dict):
        prefix_str = prefix_obj.get("address", "")
        prefix_len = prefix_obj.get("maskLength", 0)
        ip_type = prefix_obj.get("ipAddressType", "IPv4")
        afi = "ipv6" if ip_type == "IPv6" else "ipv4"

    return {
        "afi": afi,
        "prefix": prefix_str,
        "prefix_len": prefix_len,
        "next_hop": nh,
    }


def _group_rest_routes(
    rest_routes: List[Dict[str, Any]],
    vrf_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Group a list of REST route objects into the nested Ansible
    output structure: VRF > address_families > routes > next_hops.

    If vrf_name is provided, all routes are assigned to that VRF.
    Otherwise, routes must have a 'vrName' key (cross-VRF endpoint).
    """
    # Build nested dict: vrf -> afi -> (prefix, prefix_len) -> [nh]
    tree: Dict[str, Dict[str, Dict[Tuple[str, int], List[Dict[str, Any]]]]] = {}

    for rest_route in rest_routes:
        vrf = _normalize_vrf_name(vrf_name or rest_route.get("vrName", "GlobalRouter"))
        parsed = _rest_route_to_ansible(rest_route)
        afi = parsed["afi"]
        prefix = parsed["prefix"]
        prefix_len = parsed["prefix_len"]
        nh = parsed["next_hop"]

        if vrf not in tree:
            tree[vrf] = {}
        if afi not in tree[vrf]:
            tree[vrf][afi] = {}
        key = (prefix, prefix_len)
        if key not in tree[vrf][afi]:
            tree[vrf][afi][key] = []
        tree[vrf][afi][key].append(nh)

    # Convert tree to list structure
    result: List[Dict[str, Any]] = []
    for vrf_key in sorted(tree.keys()):
        afs: List[Dict[str, Any]] = []
        for afi_key in sorted(tree[vrf_key].keys()):
            routes_list: List[Dict[str, Any]] = []
            for pfx, plen in sorted(tree[vrf_key][afi_key].keys()):
                routes_list.append(
                    {
                        "prefix": pfx,
                        "prefix_len": plen,
                        "next_hops": tree[vrf_key][afi_key][(pfx, plen)],
                    }
                )
            afs.append({"afi": afi_key, "routes": routes_list})
        result.append({"vrf": vrf_key, "address_families": afs})

    return result


def _nh_label(nh: Dict[str, Any]) -> str:
    """Build a human-readable label for a next-hop entry (for response_keys)."""
    fwd = nh.get("forward_router_address")
    if fwd:
        ifn = nh.get("interface")
        if ifn:
            return "{0}_via_{1}_{2}".format(fwd, nh.get("interface_type", ""), ifn)
        return fwd
    if nh.get("blackhole"):
        return "blackhole"
    ifn = nh.get("interface")
    if ifn:
        return "if_{0}_{1}".format(nh.get("interface_type", ""), ifn)
    return "unknown"


def _build_route_key(
    afi: str,
    prefix: str,
    prefix_len: int,
    nh: Dict[str, Any],
) -> Tuple[str, str, int, str, str, str]:
    """Build a unique key tuple for a route entry.

    Key: (afi, prefix, prefix_len, forward_router_address,
          interface_type, interface)
    """
    return (
        afi,
        prefix,
        prefix_len,
        nh.get("forward_router_address") or "",
        nh.get("interface_type") or "",
        nh.get("interface") or "",
    )


# ── Diff / Comparison ───────────────────────────────────────────────────────
# Compares the "before" (current device state) with the "after" (desired state)
# to determine what changes need to be made. This drives idempotency — if
# before == after, no API calls are needed.

# Fields compared per next-hop for differences output
_NH_DIFF_FIELDS = ("admin_distance", "weight", "name", "enabled", "blackhole",
                   "forward_router_address", "interface_type", "interface",
                   "default_route")


def _flatten_grouped(
    grouped: List[Dict[str, Any]],
) -> Dict[Tuple, Dict[str, Any]]:
    """Flatten grouped route structure into a dict keyed by route key."""
    flat: Dict[Tuple, Dict[str, Any]] = {}
    for vrf_entry in grouped:
        vrf = vrf_entry.get("vrf", "")
        for af in vrf_entry.get("address_families", []):
            afi = af.get("afi", "")
            for route in af.get("routes", []):
                prefix = route.get("prefix", "")
                prefix_len = route.get("prefix_len", 0)
                for nh in route.get("next_hops", []):
                    key = (vrf, _build_route_key(afi, prefix, prefix_len, nh))
                    flat[key] = nh
    return flat


def _compute_diff(
    before: List[Dict[str, Any]],
    after: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute differences between before and after static route states.

    Returns a dict with added, removed, and modified route counts and details.
    """
    before_flat = _flatten_grouped(before)
    after_flat = _flatten_grouped(after)

    before_keys = set(before_flat)
    after_keys = set(after_flat)

    added = sorted(k for k in after_keys - before_keys)
    removed = sorted(k for k in before_keys - after_keys)

    modified = []
    for key in sorted(before_keys & after_keys):
        old_nh = before_flat[key]
        new_nh = after_flat[key]
        field_diffs = {}
        for field in _NH_DIFF_FIELDS:
            old_val = old_nh.get(field)
            new_val = new_nh.get(field)
            if old_val != new_val:
                field_diffs[field] = {"before": old_val, "after": new_val}
        if field_diffs:
            vrf, route_key = key
            entry = {
                "vrf": vrf,
                "afi": route_key[0],
                "prefix": route_key[1],
                "prefix_len": route_key[2],
                "changes": field_diffs,
            }
            # Include next-hop identity fields when present
            if route_key[3]:
                entry["forward_router_address"] = route_key[3]
            if route_key[4]:
                entry["interface_type"] = route_key[4]
            if route_key[5]:
                entry["interface"] = route_key[5]
            modified.append(entry)

    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "modified_count": len(modified),
        "modified": modified,
    }


# ── Ansible → REST payload builders ─────────────────────────────────────────
# These functions convert Ansible parameters into the JSON payloads expected
# by the device REST API (POST for create, PATCH for update).


def _build_post_payload(
    afi: str,
    prefix: str,
    prefix_len: int,
    nh: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a REST POST body (IpStaticRoute) from Ansible params."""
    ip_type = "IPv6" if afi == "ipv6" else "IPv4"

    payload: Dict[str, Any] = {
        "prefix": {
            "ipAddressType": ip_type,
            "address": prefix,
            "maskLength": prefix_len,
        },
    }

    # Next-hop address
    fwd = nh.get("forward_router_address")
    if fwd:
        payload["nextHop"] = {
            "ipAddressType": ip_type,
            "address": fwd,
        }
    elif nh.get("blackhole"):
        # Blackhole routes require a sentinel next-hop for the REST API
        payload["nextHop"] = {
            "ipAddressType": ip_type,
            "address": "0.0.0.0" if ip_type == "IPv4" else "::",
        }

    # Local interface (IPv6 only on VOSS)
    if_type = nh.get("interface_type")
    if_name = nh.get("interface")
    if if_type:
        payload["localInterfaceType"] = IF_TYPE_MAP.get(if_type, if_type.upper())
    if if_name:
        payload["localInterfaceName"] = if_name

    # Scalar fields — apply CREATE_DEFAULTS for omitted values
    for ansible_key, rest_key in FIELD_MAP.items():
        val = nh.get(ansible_key)
        if val is None:
            val = CREATE_DEFAULTS.get(ansible_key)
        if val is not None:
            payload[rest_key] = val

    return payload


def _build_route_path(
    vrf: str,
    afi: str,
    prefix: str,
    prefix_len: int,
    nh: Dict[str, Any],
) -> str:
    """Build the REST path for PATCH/DELETE of a specific route.

    Selects the correct endpoint variant based on whether the route
    has a next-hop address, local interface, or both.
    """
    ip_type = "IPv6" if afi == "ipv6" else "IPv4"
    fwd = nh.get("forward_router_address", "")
    if_type = nh.get("interface_type", "")
    if_name = nh.get("interface", "")

    params = {
        "vr_name": quote(vrf, safe=""),
        "prefix_type": quote(ip_type, safe=""),
        "prefix": quote(prefix, safe=""),
        "prefix_len": prefix_len,
    }

    if fwd and if_type and if_name:
        # next-hop + interface variant
        params["next_hop"] = quote(fwd, safe="")
        params["local_iftype"] = quote(
            IF_TYPE_MAP.get(if_type, if_type.upper()), safe=""
        )
        params["local_ifname"] = quote(if_name, safe="")
        return ROUTE_NH_IF_PATH.format(**params)
    elif fwd:
        # next-hop only variant
        params["next_hop"] = quote(fwd, safe="")
        return ROUTE_NH_PATH.format(**params)
    elif if_type and if_name:
        # interface only variant
        params["local_iftype"] = quote(
            IF_TYPE_MAP.get(if_type, if_type.upper()), safe=""
        )
        params["local_ifname"] = quote(if_name, safe="")
        return ROUTE_IF_PATH.format(**params)
    else:
        # Blackhole route — use AFI-appropriate placeholder next-hop
        placeholder = "::" if afi == "ipv6" else "0.0.0.0"
        params["next_hop"] = quote(placeholder, safe="")
        return ROUTE_NH_PATH.format(**params)


# ── Data-fetching functions ──────────────────────────────────────────────────
# These functions retrieve the current configuration from the device via
# REST GET requests and normalize the response into Python data structures.


def _fetch_vrf_routes(
    module: AnsibleModule,
    connection: Connection,
    vrf: str,
    api_responses: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """GET /v0/configuration/vrf/{vr_name}/route — static routes
    for a single VRF.
    """
    path = ROUTE_LIST_PATH.format(vr_name=quote(vrf, safe=""))
    data = _call_api(
        module,
        connection,
        method="GET",
        path=path,
        api_responses=api_responses,
        response_key="get_routes_{0}".format(vrf),
    )
    if data is None or _is_not_found_response(data):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("routes", "route", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def _fetch_all_routes(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """GET /v0/configuration/route — all static routes across all
    VRFs.
    """
    data = _call_api(
        module,
        connection,
        method="GET",
        path=ROUTE_ALL_PATH,
        api_responses=api_responses,
        response_key="get_all_routes",
    )
    if data is None or _is_not_found_response(data):
        return []
    if isinstance(data, list):
        return data
    return []


def _fetch_state_routes(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
) -> Optional[List[Dict[str, Any]]]:
    """GET /v0/state/route — dynamically learned routes.

    Returns ``None`` when the endpoint is not supported (404 / not found),
    or a (possibly empty) list on success.
    """
    data = _call_api(
        module,
        connection,
        method="GET",
        path=ROUTE_STATE_PATH,
        api_responses=api_responses,
        response_key="get_state_routes",
    )
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, list):
        return data
    return None


def _fetch_route_summary(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
) -> Optional[List[Dict[str, Any]]]:
    """GET /v0/state/route/summary — route count summary.

    Returns ``None`` when the endpoint is not supported (404 / not found),
    or a (possibly empty) list on success.
    """
    data = _call_api(
        module,
        connection,
        method="GET",
        path=ROUTE_SUMMARY_PATH,
        api_responses=api_responses,
        response_key="get_route_summary",
    )
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, list):
        return data
    return None


# ── Validation helpers ───────────────────────────────────────────────────────


def _validate_config(
    module: AnsibleModule,
    config: List[Dict[str, Any]],
) -> None:
    """Pre-flight validation of config entries.

    Checks VOSS-specific constraints that are stricter than the
    OpenAPI spec ranges.
    """
    seen_vrfs: set = set()
    for entry in config:
        vrf = entry["vrf"]
        if not vrf or len(vrf) > VRF_NAME_MAX_LEN:
            module.fail_json(
                msg=(
                    "VRF name must be 1-{0} characters, "
                    "got '{1}' ({2} chars)".format(
                        VRF_NAME_MAX_LEN,
                        vrf,
                        len(vrf) if vrf else 0,
                    )
                )
            )
        if vrf.lower() in seen_vrfs:
            module.fail_json(
                msg="Duplicate VRF name '{0}' in config list".format(vrf)
            )
        seen_vrfs.add(vrf.lower())

        afs = entry.get("address_families") or []
        for af in afs:
            afi = af["afi"]
            routes = af.get("routes") or []
            max_plen = PREFIX_LEN_MAX_IPV6 if afi == "ipv6" else PREFIX_LEN_MAX_IPV4

            seen_prefixes: set = set()
            for route in routes:
                prefix_key = (route.get("prefix", ""), route.get("prefix_len", 0))
                if prefix_key in seen_prefixes:
                    module.fail_json(
                        msg=(
                            "Duplicate route {0}/{1} in VRF '{2}' "
                            "address-family '{3}'".format(
                                prefix_key[0], prefix_key[1], vrf, afi
                            )
                        )
                    )
                seen_prefixes.add(prefix_key)
                _validate_route(module, afi, max_plen, route)


def _validate_route(
    module: AnsibleModule,
    afi: str,
    max_plen: int,
    route: Dict[str, Any],
) -> None:
    """Validate a single route entry."""
    prefix_len = route["prefix_len"]
    if prefix_len < 0 or prefix_len > max_plen:
        module.fail_json(
            msg=(
                "prefix_len must be 0-{0} for {1}, "
                "got {2}".format(max_plen, afi, prefix_len)
            )
        )

    nhs = route.get("next_hops") or []
    seen_nhs: set = set()
    for nh in nhs:
        nh_key = (
            nh.get("forward_router_address"),
            nh.get("interface_type"),
            nh.get("interface"),
        )
        if nh_key in seen_nhs:
            module.fail_json(
                msg=(
                    "Duplicate next-hop entry for prefix "
                    "'{0}/{1}': forward_router_address={2}, "
                    "interface_type={3}, interface={4}".format(
                        route["prefix"],
                        route["prefix_len"],
                        nh_key[0],
                        nh_key[1],
                        nh_key[2],
                    )
                )
            )
        seen_nhs.add(nh_key)
        _validate_next_hop(module, afi, nh)


def _validate_next_hop(
    module: AnsibleModule,
    afi: str,
    nh: Dict[str, Any],
) -> None:
    """Validate a single next-hop entry."""
    fwd = nh.get("forward_router_address")
    blackhole = nh.get("blackhole", False)

    # blackhole and forward_router_address are mutually exclusive
    if blackhole and fwd:
        module.fail_json(
            msg=("blackhole and forward_router_address are " "mutually exclusive")
        )

    # blackhole routes must not have interface fields
    if blackhole and (nh.get("interface_type") or nh.get("interface")):
        module.fail_json(
            msg=("blackhole routes cannot specify interface_type " "or interface")
        )

    # At least one of forward_router_address or blackhole is
    # required for creating a route
    if not fwd and not blackhole:
        if_type = nh.get("interface_type")
        if_name = nh.get("interface")
        if not (if_type and if_name):
            module.fail_json(
                msg=(
                    "Each next_hop must specify "
                    "forward_router_address, blackhole, "
                    "or interface_type + interface"
                )
            )

    # IPv4: reject interface_type/interface (read-only on VOSS)
    if afi == "ipv4":
        if nh.get("interface_type") or nh.get("interface"):
            module.fail_json(
                msg=(
                    "interface_type and interface are "
                    "read-only for IPv4 routes on VOSS. "
                    "These fields are only accepted for "
                    "IPv6 routes."
                )
            )

    # IPv6: link-local next-hops require interface_type + interface
    if afi == "ipv6" and fwd:
        try:
            addr = ip_address(fwd)
            if isinstance(addr, IPv6Address) and addr.is_link_local:
                if_type = nh.get("interface_type")
                if_name = nh.get("interface")
                if not (if_type and if_name):
                    module.fail_json(
                        msg=(
                            "IPv6 link-local next-hop '{0}' requires "
                            "interface_type and interface to be "
                            "specified".format(fwd)
                        )
                    )
        except ValueError:
            pass  # Invalid address will be caught by the device

    # admin_distance range (VOSS: 1-255)
    ad = nh.get("admin_distance")
    if ad is not None:
        if ad < ADMIN_DISTANCE_MIN or ad > ADMIN_DISTANCE_MAX:
            module.fail_json(
                msg=(
                    "admin_distance must be {0}-{1} on VOSS,"
                    " got {2}".format(
                        ADMIN_DISTANCE_MIN,
                        ADMIN_DISTANCE_MAX,
                        ad,
                    )
                )
            )

    # weight range (VOSS: 1-65535)
    wt = nh.get("weight")
    if wt is not None:
        if wt < WEIGHT_MIN or wt > WEIGHT_MAX:
            module.fail_json(
                msg=(
                    "weight must be {0}-{1} on VOSS, "
                    "got {2}".format(WEIGHT_MIN, WEIGHT_MAX, wt)
                )
            )

    # name length (max 64 chars)
    name = nh.get("name")
    if name is not None and len(name) > ROUTE_NAME_MAX_LEN:
        module.fail_json(
            msg=(
                "name must be 0-{0} characters, got {1} "
                "chars".format(ROUTE_NAME_MAX_LEN, len(name))
            )
        )

    # interface requires interface_type and vice versa
    if_type = nh.get("interface_type")
    if_name = nh.get("interface")
    if (if_type and not if_name) or (if_name and not if_type):
        module.fail_json(
            msg=("interface_type and interface must both " "be specified together")
        )


# ── Diff / comparison logic ─────────────────────────────────────────────────


def _nh_create_time_differs(
    desired: Dict[str, Any],
    current: Dict[str, Any],
    use_defaults: bool = False,
) -> bool:
    """Check if any create-time-only fields differ between desired
    and current next-hop entries.

    These fields can only be set at POST time and cannot be
    PATCHed.  A difference requires DELETE + re-POST.

    When *use_defaults* is True (replaced/overridden), omitted
    desired fields are compared against their factory default
    instead of being skipped.  This ensures that non-default
    values on the device are reset when the user omits them.
    """
    create_time_fields = [
        "admin_distance",
        "weight",
        "name",
        "blackhole",
    ]
    for field in create_time_fields:
        desired_val = desired.get(field)
        if desired_val is None:
            if use_defaults:
                # For replaced/overridden: substitute factory default.
                # Fields not in CREATE_DEFAULTS (admin_distance, name)
                # are left to the device — only compare if we have a
                # known default.
                desired_val = CREATE_DEFAULTS.get(field)
                if desired_val is None:
                    continue
            else:
                continue
        current_val = current.get(field)
        if desired_val != current_val:
            return True
    return False


# ── State handlers ───────────────────────────────────────────────────────────
# Each function below implements one Ansible "state" (gathered, deleted,
# merged, replaced, overridden). They are called from main() based on the
# user's chosen state. This keeps main() short and readable.


def _handle_gathered(
    module: AnsibleModule,
    connection: Connection,
    result: Dict[str, Any],
) -> None:
    """Handle state=gathered — read-only, no changes."""
    gather_filter = module.params.get("gather_filter")
    gather_dynamic = module.params.get("gather_dynamic", False)
    gather_summary = module.params.get("gather_summary", False)

    # Normalize gather_filter VRF names — VOSS stores user VRF names
    # in lowercase, but system VRFs like GlobalRouter keep canonical casing.
    if gather_filter:
        for v in gather_filter:
            normalized = _normalize_vrf_name(v)
            if v != normalized and v.lower() != v:
                module.warn(
                    "VRF name '{0}' is not in canonical form. "
                    "VOSS stores user VRF names in lowercase, but system VRFs require canonical casing; "
                    "the name will be converted to '{1}'.".format(v, normalized)
                )
        gather_filter = [_normalize_vrf_name(v) for v in gather_filter]

    # Fetch static routes
    if gather_filter:
        all_rest: List[Dict[str, Any]] = []
        for vrf in gather_filter:
            vrf_routes = _fetch_vrf_routes(
                module,
                connection,
                vrf,
                result["api_responses"],
            )
            # Tag each route with VRF name for grouping (copy to avoid
            # mutating api_responses)
            for r in vrf_routes:
                tagged = dict(r)
                tagged["_vrf"] = vrf
                all_rest.append(tagged)
        # Group using VRF tag
        grouped = _group_rest_routes_tagged(all_rest)
    else:
        raw = _fetch_all_routes(module, connection, result["api_responses"])
        grouped = _group_rest_routes(raw)

    result["gathered"] = grouped

    # Optional: dynamic routes
    if gather_dynamic:
        raw_state = _fetch_state_routes(module, connection, result["api_responses"])
        result["dynamic_routes"] = raw_state if raw_state is not None else []
        if raw_state is None:
            module.warn(
                "Dynamic route data is unavailable — the /v0/state/route "
                "endpoint may not be supported on this device."
            )

    # Optional: summary
    if gather_summary:
        raw_summary = _fetch_route_summary(module, connection, result["api_responses"])
        result["route_summary"] = raw_summary if raw_summary is not None else []
        if raw_summary is None:
            module.warn(
                "Route summary is unavailable — the /v0/state/route/summary "
                "endpoint may not be supported on this device."
            )


def _group_rest_routes_tagged(
    rest_routes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Group REST routes that have been tagged with _vrf key."""
    for r in rest_routes:
        if "_vrf" in r:
            r["vrName"] = r.pop("_vrf")
    return _group_rest_routes(rest_routes)


def _handle_merged(
    module: AnsibleModule,
    connection: Connection,
    config: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Handle state=merged — additive, only supplied fields sent."""
    for entry in config:
        vrf = entry["vrf"]
        # Fetch current routes for this VRF
        current_rest = _fetch_vrf_routes(
            module, connection, vrf, result["api_responses"]
        )
        current_grouped = _group_rest_routes(current_rest, vrf_name=vrf)
        current_map = _build_nh_map(current_grouped, vrf)

        afs = entry.get("address_families") or []
        for af in afs:
            afi = af["afi"]
            routes = af.get("routes") or []
            for route in routes:
                prefix = route["prefix"]
                prefix_len = route["prefix_len"]
                nhs = route.get("next_hops") or []
                for nh in nhs:
                    rkey = _build_route_key(afi, prefix, prefix_len, nh)
                    cur = current_map.get(rkey)
                    if cur is None:
                        # Route does not exist — create it
                        _create_route(
                            module,
                            connection,
                            vrf,
                            afi,
                            prefix,
                            prefix_len,
                            nh,
                            result,
                        )
                    else:
                        # Route exists — check create-time fields first
                        if _nh_create_time_differs(nh, cur):
                            # Create-time fields differ — DELETE + re-POST.
                            # Preserve current values for create-time fields
                            # the user did not specify (merged semantics).
                            merged_nh = dict(nh)
                            for field in ("admin_distance", "weight",
                                          "name", "blackhole"):
                                if merged_nh.get(field) is None and cur.get(field) is not None:
                                    merged_nh[field] = cur[field]
                            _delete_route(
                                module,
                                connection,
                                vrf,
                                afi,
                                prefix,
                                prefix_len,
                                cur,
                                result,
                            )
                            _create_route(
                                module,
                                connection,
                                vrf,
                                afi,
                                prefix,
                                prefix_len,
                                merged_nh,
                                result,
                            )
                        else:
                            # Only PATCH if enabled differs
                            _patch_if_enabled_differs(
                                module,
                                connection,
                                vrf,
                                afi,
                                prefix,
                                prefix_len,
                                nh,
                                cur,
                                result,
                            )


def _handle_replaced(
    module: AnsibleModule,
    connection: Connection,
    config: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Handle state=replaced — authoritative per-resource.

    For each dest prefix in config, the desired next_hops list IS
    the final state.  Extra next-hops on the device are deleted.
    Create-time field changes trigger DELETE + re-POST.
    """
    for entry in config:
        vrf = entry["vrf"]
        current_rest = _fetch_vrf_routes(
            module, connection, vrf, result["api_responses"]
        )
        current_grouped = _group_rest_routes(current_rest, vrf_name=vrf)
        current_map = _build_nh_map(current_grouped, vrf)

        # Pre-index current next-hops by (afi, prefix, prefix_len)
        # to avoid scanning the entire map for each desired prefix.
        prefix_index: Dict[
            Tuple[str, str, int],
            Dict[Tuple[str, str, int, str, str, str], Dict[str, Any]],
        ] = {}
        for rkey, cur_nh in current_map.items():
            pkey = (rkey[0], rkey[1], rkey[2])
            if pkey not in prefix_index:
                prefix_index[pkey] = {}
            prefix_index[pkey][rkey] = cur_nh

        afs = entry.get("address_families") or []
        for af in afs:
            afi = af["afi"]
            routes = af.get("routes") or []
            for route in routes:
                prefix = route["prefix"]
                prefix_len = route["prefix_len"]
                desired_nhs = route.get("next_hops") or []

                # Build keys for desired next-hops
                desired_keys = set()
                for nh in desired_nhs:
                    desired_keys.add(_build_route_key(afi, prefix, prefix_len, nh))

                # Delete current next-hops not in desired
                pkey = (afi, prefix, prefix_len)
                for rkey, cur_nh in prefix_index.get(pkey, {}).items():
                    if rkey not in desired_keys:
                        _delete_route(
                            module,
                            connection,
                            vrf,
                            afi,
                            prefix,
                            prefix_len,
                            cur_nh,
                            result,
                        )

                # Create or update desired next-hops
                for nh in desired_nhs:
                    rkey = _build_route_key(afi, prefix, prefix_len, nh)
                    cur = current_map.get(rkey)
                    _replace_single_nh(
                        module,
                        connection,
                        vrf,
                        afi,
                        prefix,
                        prefix_len,
                        nh,
                        cur,
                        result,
                    )


def _handle_overridden(
    module: AnsibleModule,
    connection: Connection,
    config: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Handle state=overridden — authoritative globally.

    Like replaced, but also deletes routes on VRFs/AFIs/prefixes
    NOT listed in config.

    To avoid redundant API calls, the overridden handler fetches
    all routes once, performs deletions, then re-fetches each
    config-listed VRF once to get the post-deletion state for the
    replaced logic (rather than delegating to _handle_replaced
    which would re-fetch per VRF independently).
    """
    # Fetch all routes across all VRFs
    all_rest = _fetch_all_routes(module, connection, result["api_responses"])
    all_map = _build_nh_map_cross_vrf(all_rest)

    # Build set of desired route keys (vrf, afi, prefix,
    # prefix_len, fwd, if_type, if_name)
    desired_keys: set = set()
    for entry in config:
        vrf = entry["vrf"]
        afs = entry.get("address_families") or []
        for af in afs:
            afi = af["afi"]
            routes = af.get("routes") or []
            for route in routes:
                prefix = route["prefix"]
                prefix_len = route["prefix_len"]
                nhs = route.get("next_hops") or []
                for nh in nhs:
                    key = (vrf,) + _build_route_key(afi, prefix, prefix_len, nh)
                    desired_keys.add(key)

    # Delete all routes not in desired set (skip system VRFs)
    for full_key, (vrf, cur_nh) in all_map.items():
        if vrf in SYSTEM_VRFS:
            continue
        if full_key not in desired_keys:
            afi = full_key[1]
            prefix = full_key[2]
            prefix_len = full_key[3]
            _delete_route(
                module,
                connection,
                vrf,
                afi,
                prefix,
                prefix_len,
                cur_nh,
                result,
            )

    # Apply replaced logic for desired routes — re-fetch each
    # config-listed VRF once to get post-deletion state.
    for entry in config:
        vrf = entry["vrf"]
        current_rest = _fetch_vrf_routes(
            module, connection, vrf, result["api_responses"]
        )
        current_grouped = _group_rest_routes(current_rest, vrf_name=vrf)
        current_map = _build_nh_map(current_grouped, vrf)

        afs = entry.get("address_families") or []
        for af in afs:
            afi = af["afi"]
            routes = af.get("routes") or []
            for route in routes:
                prefix = route["prefix"]
                prefix_len = route["prefix_len"]
                desired_nhs = route.get("next_hops") or []

                # Create or update desired next-hops
                for nh in desired_nhs:
                    rkey = _build_route_key(afi, prefix, prefix_len, nh)
                    cur = current_map.get(rkey)
                    _replace_single_nh(
                        module,
                        connection,
                        vrf,
                        afi,
                        prefix,
                        prefix_len,
                        nh,
                        cur,
                        result,
                    )


def _handle_deleted(
    module: AnsibleModule,
    connection: Connection,
    config: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Handle state=deleted — delete specified routes.

    If config lists VRF without address_families, delete all routes
    on that VRF.  If config is empty, delete all routes on all
    VRFs.
    """
    if not config:
        # Delete all routes across all VRFs (skip system VRFs)
        all_rest = _fetch_all_routes(module, connection, result["api_responses"])
        all_map = _build_nh_map_cross_vrf(all_rest)
        for full_key, (vrf, cur_nh) in all_map.items():
            if vrf in SYSTEM_VRFS:
                continue
            afi = full_key[1]
            prefix = full_key[2]
            prefix_len = full_key[3]
            _delete_route(
                module,
                connection,
                vrf,
                afi,
                prefix,
                prefix_len,
                cur_nh,
                result,
            )
        return

    for entry in config:
        vrf = entry["vrf"]
        afs = entry.get("address_families")

        # Fetch once per VRF and reuse for all AFI/prefix/NH lookups
        current_rest = _fetch_vrf_routes(
            module,
            connection,
            vrf,
            result["api_responses"],
        )

        if not afs:
            # No AFs specified — delete all routes on this VRF
            for rest_route in current_rest:
                parsed = _rest_route_to_ansible(rest_route)
                _delete_route(
                    module,
                    connection,
                    vrf,
                    parsed["afi"],
                    parsed["prefix"],
                    parsed["prefix_len"],
                    parsed["next_hop"],
                    result,
                )
            continue

        for af in afs:
            afi = af["afi"]
            routes = af.get("routes")

            if not routes:
                # Delete all routes for this AFI on this VRF
                for rest_route in current_rest:
                    parsed = _rest_route_to_ansible(rest_route)
                    if parsed["afi"] == afi:
                        _delete_route(
                            module,
                            connection,
                            vrf,
                            afi,
                            parsed["prefix"],
                            parsed["prefix_len"],
                            parsed["next_hop"],
                            result,
                        )
                continue

            current_grouped = _group_rest_routes(current_rest, vrf_name=vrf)
            current_map = _build_nh_map(current_grouped, vrf)

            for route in routes:
                prefix = route["prefix"]
                prefix_len = route["prefix_len"]
                nhs = route.get("next_hops")

                if not nhs:
                    # Delete all next-hops for this prefix
                    for rkey, cur_nh in current_map.items():
                        if (
                            rkey[0] == afi
                            and rkey[1] == prefix
                            and rkey[2] == prefix_len
                        ):
                            _delete_route(
                                module,
                                connection,
                                vrf,
                                afi,
                                prefix,
                                prefix_len,
                                cur_nh,
                                result,
                            )
                    continue

                # Delete only matching NHs
                for nh in nhs:
                    rkey = _build_route_key(afi, prefix, prefix_len, nh)
                    if rkey in current_map:
                        _delete_route(
                            module,
                            connection,
                            vrf,
                            afi,
                            prefix,
                            prefix_len,
                            nh,
                            result,
                        )


# ── Route operation helpers ──────────────────────────────────────────────────


def _create_route(
    module: AnsibleModule,
    connection: Connection,
    vrf: str,
    afi: str,
    prefix: str,
    prefix_len: int,
    nh: Dict[str, Any],
    result: Dict[str, Any],
    use_defaults: bool = False,
) -> None:
    """POST a new static route.

    If POST returns a 'Duplicate route' error (HTTP 422), the route
    already exists despite not appearing in the GET response (known
    API inconsistency on GlobalRouter).  Fall back to PATCH for the
    enabled field in that case.

    Args:
        use_defaults: When True (replaced/overridden), treat omitted
            enabled as FULL_DEFAULTS["enabled"] in the duplicate-route
            fallback.  When False (merged), only patch enabled if the
            user explicitly specified it.
    """
    if module.check_mode:
        result["changed"] = True
        return

    payload = _build_post_payload(afi, prefix, prefix_len, nh)
    path = ROUTE_LIST_PATH.format(vr_name=quote(vrf, safe=""))
    try:
        _call_api(
            module,
            connection,
            method="POST",
            path=path,
            payload=payload,
            api_responses=result["api_responses"],
            response_key="post_{0}_{1}_{2}_{3}".format(
                vrf,
                prefix,
                prefix_len,
                _nh_label(nh),
            ),
        )
        result["changed"] = True
    except FeStaticRouteError as exc:
        if "duplicate" in str(exc).lower():
            # Route exists despite GET returning empty — fall back
            # to PATCH for the enabled field.  For merged, only patch
            # when the user explicitly specified it.  For replaced/
            # overridden, default to FULL_DEFAULTS["enabled"].
            desired_enabled = nh.get("enabled")
            if desired_enabled is None and use_defaults:
                desired_enabled = FULL_DEFAULTS["enabled"]
            if desired_enabled is not None:
                patch_path = _build_route_path(
                    vrf, afi, prefix, prefix_len, nh,
                )
                _call_api(
                    module,
                    connection,
                    method="PATCH",
                    path=patch_path,
                    payload={"enabled": desired_enabled},
                    api_responses=result["api_responses"],
                    response_key="patch_fallback_{0}_{1}_{2}_{3}".format(
                        vrf, prefix, prefix_len, _nh_label(nh),
                    ),
                )
                result["changed"] = True
            # If enabled was not specified, route already exists —
            # treat as idempotent (no change).
        else:
            raise


def _delete_route(
    module: AnsibleModule,
    connection: Connection,
    vrf: str,
    afi: str,
    prefix: str,
    prefix_len: int,
    nh: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """DELETE a static route."""
    if module.check_mode:
        result["changed"] = True
        return

    path = _build_route_path(vrf, afi, prefix, prefix_len, nh)
    _call_api(
        module,
        connection,
        method="DELETE",
        path=path,
        api_responses=result["api_responses"],
        response_key="delete_{0}_{1}_{2}_{3}".format(
            vrf,
            prefix,
            prefix_len,
            _nh_label(nh),
        ),
    )
    result["changed"] = True


def _patch_if_enabled_differs(
    module: AnsibleModule,
    connection: Connection,
    vrf: str,
    afi: str,
    prefix: str,
    prefix_len: int,
    desired_nh: Dict[str, Any],
    current_nh: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    """PATCH the enabled field if it differs from current."""
    desired_enabled = desired_nh.get("enabled")
    if desired_enabled is None:
        return
    current_enabled = current_nh.get("enabled")
    if desired_enabled == current_enabled:
        return

    if module.check_mode:
        result["changed"] = True
        return

    path = _build_route_path(vrf, afi, prefix, prefix_len, current_nh)
    _call_api(
        module,
        connection,
        method="PATCH",
        path=path,
        payload={"enabled": desired_enabled},
        api_responses=result["api_responses"],
        response_key="patch_enabled_{0}_{1}_{2}_{3}".format(
            vrf,
            prefix,
            prefix_len,
            _nh_label(current_nh),
        ),
    )
    result["changed"] = True


def _replace_single_nh(
    module: AnsibleModule,
    connection: Connection,
    vrf: str,
    afi: str,
    prefix: str,
    prefix_len: int,
    desired_nh: Dict[str, Any],
    current_nh: Optional[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """Apply replaced logic for a single next-hop entry.

    If the route does not exist, create it.
    If only enabled differs, PATCH.
    If create-time fields differ, DELETE + re-POST.
    For replaced, also apply FULL_DEFAULTS for omitted patchable
    fields.
    """
    if current_nh is None:
        # Route does not exist — create
        _create_route(
            module,
            connection,
            vrf,
            afi,
            prefix,
            prefix_len,
            desired_nh,
            result,
            use_defaults=True,
        )
        return

    # Check if create-time fields differ — for replaced/overridden,
    # compare omitted fields against factory defaults.
    if _nh_create_time_differs(desired_nh, current_nh, use_defaults=True):
        # DELETE + re-POST
        _delete_route(
            module,
            connection,
            vrf,
            afi,
            prefix,
            prefix_len,
            current_nh,
            result,
        )
        _create_route(
            module,
            connection,
            vrf,
            afi,
            prefix,
            prefix_len,
            desired_nh,
            result,
            use_defaults=True,
        )
        return

    # Only patchable field is enabled
    # For replaced: default to FULL_DEFAULTS if not specified
    desired_enabled = desired_nh.get("enabled")
    if desired_enabled is None:
        desired_enabled = FULL_DEFAULTS["enabled"]

    current_enabled = current_nh.get("enabled")
    if desired_enabled != current_enabled:
        if module.check_mode:
            result["changed"] = True
            return
        path = _build_route_path(vrf, afi, prefix, prefix_len, current_nh)
        _call_api(
            module,
            connection,
            method="PATCH",
            path=path,
            payload={"enabled": desired_enabled},
            api_responses=result["api_responses"],
            response_key="replace_patch_{0}_{1}_{2}_{3}".format(
                vrf, prefix, prefix_len, _nh_label(current_nh),
            ),
        )
        result["changed"] = True


# ── Next-hop map builders ────────────────────────────────────────────────────


def _build_nh_map(
    grouped: List[Dict[str, Any]],
    target_vrf: str,
) -> Dict[Tuple[str, str, int, str, str, str], Dict[str, Any]]:
    """Build a lookup map of current next-hops for a single VRF.

    Key: (afi, prefix, prefix_len, fwd, if_type, if_name)
    Value: next-hop dict (Ansible format)
    """
    nh_map: Dict[Tuple[str, str, int, str, str, str], Dict[str, Any]] = {}
    for vrf_entry in grouped:
        if vrf_entry.get("vrf") != target_vrf:
            continue
        for af in vrf_entry.get("address_families", []):
            afi = af["afi"]
            for route in af.get("routes", []):
                prefix = route["prefix"]
                prefix_len = route["prefix_len"]
                for nh in route.get("next_hops", []):
                    rkey = _build_route_key(afi, prefix, prefix_len, nh)
                    nh_map[rkey] = nh
    return nh_map


def _build_nh_map_cross_vrf(
    rest_routes: List[Dict[str, Any]],
) -> Dict[
    Tuple[str, str, str, int, str, str, str],
    Tuple[str, Dict[str, Any]],
]:
    """Build a lookup map of all routes across all VRFs.

    Key: (vrf, afi, prefix, prefix_len, fwd, if_type, if_name)
    Value: (vrf, next-hop dict in Ansible format)
    """
    nh_map: Dict[
        Tuple[str, str, str, int, str, str, str],
        Tuple[str, Dict[str, Any]],
    ] = {}
    for rest_route in rest_routes:
        vrf = _normalize_vrf_name(rest_route.get("vrName", "GlobalRouter"))
        parsed = _rest_route_to_ansible(rest_route)
        afi = parsed["afi"]
        prefix = parsed["prefix"]
        prefix_len = parsed["prefix_len"]
        nh = parsed["next_hop"]
        rkey = _build_route_key(afi, prefix, prefix_len, nh)
        full_key = (vrf,) + rkey
        nh_map[full_key] = (vrf, nh)
    return nh_map


# ── main() entry point ──────────────────────────────────────────────────────


def main() -> None:
    """Module entry point — validate params and dispatch state."""
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
    )

    # Validate connection type
    if not module._socket_path:
        module.fail_json(msg=("Connection type httpapi is required for " "this module"))

    connection = Connection(module._socket_path)
    state = module.params["state"]
    config = module.params.get("config") or []

    # Config is required for merged, replaced, overridden
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN) and not config:
        module.fail_json(msg=("'config' is required when state is '{0}'".format(state)))

    # Pre-flight validation of config entries
    if config:
        _validate_config(module, config)
        # Normalize VRF names — VOSS stores user VRF names in lowercase
        # and the REST API is case-sensitive.  System VRFs like
        # GlobalRouter must keep their canonical casing.
        for entry in config:
            normalized = _normalize_vrf_name(entry["vrf"])
            if entry["vrf"] != normalized:
                if entry["vrf"].lower() != entry["vrf"]:
                    module.warn(
                        "VRF name '{0}' is not in canonical form. "
                        "VOSS stores user VRF names in lowercase, but system VRFs require canonical casing; "
                        "the name will be converted to '{1}'.".format(
                            entry["vrf"], normalized
                        )
                    )
            entry["vrf"] = normalized

    result: Dict[str, Any] = {
        "changed": False,
        "api_responses": {},
    }

    try:
        # STATE: GATHERED
        if state == STATE_GATHERED:
            _handle_gathered(module, connection, result)
            module.exit_json(**result)
            return

        # Capture "before" state — full resource config before changes
        before_raw = _fetch_all_routes(
            module, connection, result["api_responses"]
        )
        result["before"] = _group_rest_routes(before_raw)

        # STATE: DELETED
        if state == STATE_DELETED:
            _handle_deleted(module, connection, config, result)

        # STATE: OVERRIDDEN
        elif state == STATE_OVERRIDDEN:
            _handle_overridden(module, connection, config, result)

        # STATE: REPLACED
        elif state == STATE_REPLACED:
            _handle_replaced(module, connection, config, result)

        # STATE: MERGED
        elif state == STATE_MERGED:
            _handle_merged(module, connection, config, result)

        # Capture "after" state when changes were made
        if result["changed"] and not module.check_mode:
            after_raw = _fetch_all_routes(
                module, connection, result["api_responses"]
            )
            result["after"] = _group_rest_routes(after_raw)
            result["differences"] = _compute_diff(
                result["before"], result["after"]
            )

        module.exit_json(**result)

    except FeStaticRouteError as exc:
        module.fail_json(
            **exc.to_fail_kwargs(),
            api_responses=result.get("api_responses", {}),
        )
    except ConnectionError as exc:
        module.fail_json(
            msg="Connection error: {0}".format(to_text(exc)),
            api_responses=result.get("api_responses", {}),
        )


if __name__ == "__main__":
    main()
