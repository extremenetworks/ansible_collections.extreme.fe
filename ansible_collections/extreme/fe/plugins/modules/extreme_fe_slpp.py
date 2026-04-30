# -*- coding: utf-8 -*-
"""Ansible module to manage Extreme Fabric Engine SLPP settings.

Module Architecture Overview
============================
This module manages SLPP (Simple Loop Prevention Protocol) on Extreme
Fabric Engine (VOSS) switches via the REST OpenAPI.

SLPP prevents Layer-2 loops by sending detection frames and taking action
(blocking/shutting down ports) when a loop is detected.

The module supports three configuration scopes:
  1. Global   - Enable/disable SLPP system-wide  (/v0/configuration/slpp)
  2. Per-VLAN - Enable/disable SLPP on individual VLANs
  3. Per-Port - Configure guard and packet-rx on individual ports

Supported states:
  - merged     : Incremental update (add/change settings, keep the rest)
  - replaced   : Authoritative for specified resources (all fields required)
  - overridden : Full replacement (unspecified entries get removed)
  - deleted    : Reset specified entries back to factory defaults
  - gathered   : Read-only, returns current config + optional live state

Code Flow (run_module):
  1. Connect to switch via httpapi
  2. Fetch current SLPP config from the switch
  3. Based on the requested state, apply/delete/gather settings
  4. Return results with changed status and current values
"""

from __future__ import annotations

# ── Standard Ansible imports ──────────────────────────────────────────────────
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

# ── Type hints for readability ────────────────────────────────────────────────
from typing import Any, Dict, Iterable, List, Optional, Tuple

DOCUMENTATION = r"""
---
module: extreme_fe_slpp
short_description: Manage Fabric Engine SLPP (Simple Loop Prevention Protocol) settings
version_added: 1.1.0
description:
    - Manage global, per-VLAN, and per-port SLPP settings on ExtremeNetworks Fabric Engine
      switches using the custom C(extreme_fe) HTTPAPI plugin.
    - SLPP detects and contains Layer-2 loops by sending special loop-detection frames and
      blocking or shutting down the offending port and/or VLAN context upon loop detection.
    - Supports SLPP guard (blocks the port on loop detection) and SLPP packet reception
      detection modes.  On VOSS, enabling both packet-rx and guard on the same port
      simultaneously is not allowed.
    - Provides a gathered mode that reports the full configuration and live SLPP port state
      from C(/v0/state/slpp).
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin
      shipped with this project.
    - Port identifiers must use slot:port notation such as C(1:5).
    - On Fabric Engine B(VOSS), enabling both C(enable_packet_rx) and C(enable_guard) on the
      same port at the same time is not allowed.  The module will raise an error if both are
      set to C(true) in the same port entry.
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired module operation.
            - C(merged) applies the provided settings as an incremental merge.
            - C(replaced) makes the supplied values authoritative for the targeted resources.
            - C(overridden) replaces the running configuration with the supplied values and
              removes entries that are not provided.
            - C(deleted) removes the specified per-port and per-VLAN overrides.
            - C(gathered) returns the current configuration (and optional state payloads)
              without making changes.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    global_settings:
        description:
            - Global SLPP settings applied through C(/v0/configuration/slpp).
        type: dict
        suboptions:
            enabled:
                description:
                    - Enable or disable SLPP globally on the switch.
                type: bool
    vlans:
        description:
            - Per-VLAN SLPP settings applied through C(/v0/configuration/slpp/vlan/{vlan_id}).
        type: list
        elements: dict
        suboptions:
            vlan_id:
                description:
                    - VLAN identifier (1-4094).
                type: int
                required: true
            enabled:
                description:
                    - Enable or disable SLPP on this VLAN.
                type: bool
    ports:
        description:
            - Per-port SLPP settings applied through C(/v0/configuration/slpp/ports/{port}).
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as C(1:5)).
                type: str
                required: true
            enable_guard:
                description:
                    - Enable SLPP guard on the specified port.  When a loop is detected the
                      port is disabled.  Cannot be enabled at the same time as C(enable_packet_rx).
                type: bool
            guard_timeout:
                description:
                    - Time in seconds a port remains disabled after SLPP guard triggers.
                      A value of C(0) means the port will never be automatically re-enabled.
                      Valid range is C(0) or C(10-65535).
                type: int
            enable_packet_rx:
                description:
                    - Enable SLPP packet reception detection on the specified port.
                      This setting is applicable to Fabric Engine (VOSS) only.
                      Cannot be enabled at the same time as C(enable_guard).
                type: bool
            packet_rx_threshold:
                description:
                    - Number of SLPP packets received before action is taken.
                      Valid range is C(1-500).  Default is C(1).
                      This setting is applicable to Fabric Engine (VOSS) only.
                type: int
    gather_filter:
        description:
            - Optional list of port identifiers used to limit gathered configuration
              and state output.
        type: list
        elements: str
    gather_vlan_filter:
        description:
            - Optional list of VLAN IDs used to limit gathered VLAN configuration output.
        type: list
        elements: int
    gather_state:
        description:
            - When true, include data from C(/v0/state/slpp) in the result.
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
#
# Prerequisites:
#
# ## SLPP must be enabled globally before per-port or per-VLAN settings take effect
# # show slpp
# # show slpp interface
#
# -------------------------------------------------------------------------
# Task 1: Enable SLPP globally and on specific VLANs
# Description:
#   - This example demonstrates how to enable SLPP globally and activate
#     loop detection on specific VLANs using the 'merged' state.
# Prerequisites:
#   - Target VLANs must exist on the switch
# -------------------------------------------------------------------------
# - name: "Task 1: Enable SLPP globally and on VLANs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enable SLPP globally and activate on VLANs 100 and 200
  extreme.fe.extreme_fe_slpp:
    state: merged
    global_settings:
      enabled: true
    vlans:
      - vlan_id: 100
        enabled: true
      - vlan_id: 200
        enabled: true

# -------------------------------------------------------------------------
# Task 2: Configure SLPP guard on edge ports
# Description:
#   - This example configures SLPP guard on specific edge ports where
#     unmanaged switches or rogue devices may create loops.  When a loop
#     is detected the port is disabled and auto-recovers after 120 seconds.
# Prerequisites:
#   - SLPP must be enabled globally
#   - Target ports must exist
# -------------------------------------------------------------------------
# - name: "Task 2: Configure SLPP guard on edge ports"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enable SLPP guard with 120-second recovery on edge ports
  extreme.fe.extreme_fe_slpp:
    state: merged
    ports:
      - name: "1:5"
        enable_guard: true
        guard_timeout: 120
      - name: "1:6"
        enable_guard: true
        guard_timeout: 120

# -------------------------------------------------------------------------
# Task 3: Configure SLPP packet-rx detection
# Description:
#   - This example enables SLPP packet reception detection with a
#     threshold of 3 packets before action is taken.
# Prerequisites:
#   - SLPP must be enabled globally
#   - Cannot have enable_guard active on the same port
# -------------------------------------------------------------------------
# - name: "Task 3: Configure SLPP packet-rx detection"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enable SLPP packet-rx detection on port 1:10
  extreme.fe.extreme_fe_slpp:
    state: merged
    ports:
      - name: "1:10"
        enable_packet_rx: true
        packet_rx_threshold: 3

# -------------------------------------------------------------------------
# Task 4: Configure SLPP guard with no auto-recovery (manual restore)
# Description:
#   - This example sets guard_timeout to 0 so once a loop is detected
#     the port stays disabled until an operator manually re-enables it.
# -------------------------------------------------------------------------
# - name: "Task 4: Configure SLPP guard with manual recovery"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enable SLPP guard with manual recovery on port 1:7
  extreme.fe.extreme_fe_slpp:
    state: merged
    ports:
      - name: "1:7"
        enable_guard: true
        guard_timeout: 0

# -------------------------------------------------------------------------
# Task 5: Replace per-port SLPP configuration
# Description:
#   - This example enforces exact port settings using 'replaced' state.
#     All port fields must be provided.
# -------------------------------------------------------------------------
# - name: "Task 5: Replace SLPP port configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce exact SLPP guard settings on port 1:5
  extreme.fe.extreme_fe_slpp:
    state: replaced
    ports:
      - name: "1:5"
        enable_guard: true
        guard_timeout: 60
        enable_packet_rx: false
        packet_rx_threshold: 1

# -------------------------------------------------------------------------
# Task 6: Delete SLPP overrides from ports and VLANs
# Description:
#   - This example removes SLPP configuration from specific ports
#     and VLANs using the 'deleted' state.
# -------------------------------------------------------------------------
# - name: "Task 6: Remove SLPP overrides"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Remove SLPP configuration from ports and VLANs
  extreme.fe.extreme_fe_slpp:
    state: deleted
    ports:
      - name: "1:5"
      - name: "1:6"
    vlans:
      - vlan_id: 100
      - vlan_id: 200

# -------------------------------------------------------------------------
# Task 7: Gather SLPP configuration and state
# Description:
#   - This example retrieves the current SLPP configuration and live
#     guard state from the switch.  Useful for auditing and incident review.
# -------------------------------------------------------------------------
# - name: "Task 7: Gather SLPP configuration and state"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect SLPP information including guard state
  extreme.fe.extreme_fe_slpp:
    state: gathered
    gather_state: true
    gather_filter:
      - "1:5"
      - "1:6"
  register: slpp_info
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made.
  returned: always
  type: bool
global_settings:
  description: Resulting global SLPP configuration after any updates.
  returned: when state == gathered or when global settings changed/queried
  type: dict
vlans_settings:
  description: List of per-VLAN SLPP settings with normalized field names.
  returned: when state == gathered or VLAN settings changed/queried
  type: list
ports_settings:
  description: List of per-port SLPP settings with normalized field names.
  returned: when state == gathered or port settings changed/queried
  type: list
port_updates:
  description: Ports that were modified during execution.
  returned: when port settings changed
  type: list
port_removals:
  description: Ports whose overrides were removed when using C(state=deleted) or C(state=overridden).
  returned: when port overrides were cleared
  type: list
vlan_updates:
  description: VLANs that were modified during execution.
  returned: when VLAN settings changed
  type: list
vlan_removals:
  description: VLANs whose overrides were removed when using C(state=deleted) or C(state=overridden).
  returned: when VLAN overrides were cleared
  type: list
ports_state:
  description: SLPP state payload returned from C(/v0/state/slpp) when requested.
  returned: when gather_state is true
  type: list
"""

# ─── Argument Spec ────────────────────────────────────────────────────────────
# Defines every parameter the module accepts.  Ansible validates user input
# against this spec before the module code runs.

ARGUMENT_SPEC: Dict[str, Any] = {
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
    "global_settings": {
        "type": "dict",
        "options": {
            "enabled": {"type": "bool"},
        },
    },
    "vlans": {
        "type": "list",
        "elements": "dict",
        "options": {
            "vlan_id": {"type": "int", "required": True},
            "enabled": {"type": "bool"},
        },
    },
    "ports": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "enable_guard": {"type": "bool"},
            "guard_timeout": {"type": "int"},
            "enable_packet_rx": {"type": "bool"},
            "packet_rx_threshold": {"type": "int"},
        },
    },
    "gather_filter": {"type": "list", "elements": "str"},
    "gather_vlan_filter": {"type": "list", "elements": "int"},
    "gather_state": {"type": "bool", "default": False},
}

# ─── Field Maps ───────────────────────────────────────────────────────────────
# These dictionaries translate between Ansible parameter names (snake_case)
# and the REST API JSON field names (camelCase).
#
# Example: The user writes  enable_guard: true  in their playbook,
#          which gets sent as  {"enableGuard": true}  to the switch API.

PORT_FIELD_MAP: Dict[str, str] = {
    "enable_guard": "enableGuard",  # SLPP guard on/off
    "guard_timeout": "guardTimeout",  # Seconds before auto-recovery (0 = manual)
    "enable_packet_rx": "enablePacketRx",  # Packet-rx detection on/off
    "packet_rx_threshold": "packetRxThreshold",  # Packets before action (1-500)
}

VLAN_FIELD_MAP: Dict[str, str] = {
    "enabled": "enabled",  # SLPP on/off for a specific VLAN
}

# ─── State Constants ──────────────────────────────────────────────────────────
# These match the 'state' parameter values the user provides in their playbook.

STATE_MERGED = "merged"  # Incremental update (default)
STATE_REPLACED = "replaced"  # Authoritative per-resource (all fields required)
STATE_OVERRIDDEN = "overridden"  # Full replace; unspecified entries get removed
STATE_DELETED = "deleted"  # Reset entries to factory defaults
STATE_GATHERED = "gathered"  # Read-only; no changes made


# ─── Exception ────────────────────────────────────────────────────────────────
# Custom exception that carries an optional 'details' dict.  When caught in
# run_module(), it gets converted to Ansible's fail_json() format.


class FeSlppError(Exception):
    """Base exception for SLPP module errors."""

    def __init__(
        self, message: str, *, details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# ─── Helpers ──────────────────────────────────────────────────────────────────
# Small utility functions used throughout the module.


def _normalize_port_name(raw: str) -> str:
    """Strip whitespace from port names (e.g. ' 1:5 ' → '1:5')."""
    if not isinstance(raw, str):
        raise FeSlppError("Port name must be a string in slot:port format")
    value = raw.strip()
    if not value:
        raise FeSlppError("Port name must not be empty")
    return value


def _validate_port_entry(entry: Dict[str, Any]) -> None:
    """Validate mutual exclusivity of enable_guard and enable_packet_rx.

    On VOSS, a port cannot have both guard and packet-rx active at the
    same time.  This check runs before any API call to give a clear error.
    """
    guard = entry.get("enable_guard")
    pkt_rx = entry.get("enable_packet_rx")
    if guard is True and pkt_rx is True:
        port_name = entry.get("name", "unknown")
        raise FeSlppError(
            f"Port '{port_name}': cannot enable both enable_guard and "
            f"enable_packet_rx simultaneously on Fabric Engine (VOSS)."
        )


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge 'updates' into 'base', returning a new dict.

    Used to combine the current switch config with the user's desired changes
    so we can track the final expected state after each operation.
    """
    merged = dict(base)
    for key, value in updates.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# ─── Port Payload Building ────────────────────────────────────────────────────
# These functions convert the user's Ansible parameters into the JSON payload
# format expected by the switch REST API.


def _build_port_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Convert user-supplied port parameters to REST API JSON payload.

    Only includes fields that the user actually specified (non-None).
    """
    payload: Dict[str, Any] = {}
    for param, rest_key in PORT_FIELD_MAP.items():
        if param not in entry:
            continue
        value = entry.get(param)
        if value is None:
            continue
        payload[rest_key] = value
    return payload


def _build_vlan_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Convert user-supplied VLAN parameters to REST API JSON payload."""
    payload: Dict[str, Any] = {}
    for param, rest_key in VLAN_FIELD_MAP.items():
        if param not in entry:
            continue
        value = entry.get(param)
        if value is None:
            continue
        payload[rest_key] = value
    return payload


# ─── Output Transformation ────────────────────────────────────────────────────
# These functions convert the switch's camelCase JSON responses back into
# snake_case format for the Ansible output, so results look consistent
# with what the user wrote in their playbook.


def _transform_ports_output(
    port_map: Dict[str, Dict[str, Any]],
    gather_filter: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    names: Iterable[str]
    if gather_filter:
        normalized = []
        for item in gather_filter:
            try:
                normalized.append(_normalize_port_name(item))
            except FeSlppError:
                raise FeSlppError(
                    "gather_filter contains invalid port identifier: %r" % item
                )
        names = normalized
    else:
        names = sorted(port_map.keys())
    result: List[Dict[str, Any]] = []
    for name in names:
        settings = port_map.get(name)
        if not isinstance(settings, dict):
            continue
        transformed: Dict[str, Any] = {}
        for param, rest_key in PORT_FIELD_MAP.items():
            if rest_key in settings:
                transformed[param] = settings.get(rest_key)
        result.append({"name": name, "settings": transformed})
    return result


def _transform_vlans_output(
    vlan_map: Dict[int, Dict[str, Any]],
    vlan_filter: Optional[Iterable[int]] = None,
) -> List[Dict[str, Any]]:
    ids: Iterable[int]
    if vlan_filter:
        ids = vlan_filter
    else:
        ids = sorted(vlan_map.keys())
    result: List[Dict[str, Any]] = []
    for vlan_id in ids:
        settings = vlan_map.get(vlan_id)
        if not isinstance(settings, dict):
            continue
        transformed: Dict[str, Any] = {}
        for param, rest_key in VLAN_FIELD_MAP.items():
            if rest_key in settings:
                transformed[param] = settings.get(rest_key)
        result.append({"vlan_id": vlan_id, "settings": transformed})
    return result


# ─── Connection ───────────────────────────────────────────────────────────────
# Establishes the httpapi connection to the switch.
# The connection is managed by Ansible's persistent connection framework;
# we just retrieve it here using the socket path.


def get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeSlppError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


# ─── Fetch Current Configuration ──────────────────────────────────────────────
# Reads the full SLPP configuration from the switch in a single GET call.
# The response contains global settings, per-port settings, and per-VLAN
# settings all bundled together.  We parse it into three separate structures
# for easier handling downstream.


def fetch_slpp_config(
    connection: Connection,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """Fetch the full SLPP configuration.

    Returns:
        (global_settings, port_map, vlan_map)
    """
    data = connection.send_request(None, path="/v0/configuration/slpp", method="GET")
    if data is None:
        return {}, {}, {}
    if not isinstance(data, dict):
        raise FeSlppError(
            "Unexpected response when retrieving SLPP configuration",
            details={"response": data},
        )

    # Parse ports - build a dict keyed by port name (e.g. '1:5') for O(1) lookups
    ports_payload = data.get("ports")
    port_map: Dict[str, Dict[str, Any]] = {}
    if isinstance(ports_payload, list):
        for entry in ports_payload:
            if not isinstance(entry, dict):
                continue
            name = entry.get("portName")
            if not isinstance(name, str):
                continue
            settings = entry.get("portSettings")
            if isinstance(settings, dict):
                port_map[_normalize_port_name(name)] = dict(settings)

    # Parse VLANs - build a dict keyed by VLAN ID (int) for O(1) lookups
    vlans_payload = data.get("vlans")
    vlan_map: Dict[int, Dict[str, Any]] = {}
    if isinstance(vlans_payload, list):
        for entry in vlans_payload:
            if not isinstance(entry, dict):
                continue
            vlan_id = entry.get("vlanId")
            if not isinstance(vlan_id, int):
                continue
            vlan_settings: Dict[str, Any] = {
                k: v for k, v in entry.items() if k != "vlanId"
            }
            vlan_map[vlan_id] = vlan_settings

    # Global settings - just the top-level 'enabled' flag
    global_payload: Dict[str, Any] = {}
    enabled = data.get("enabled")
    if enabled is not None:
        global_payload["enabled"] = enabled

    return global_payload, port_map, vlan_map


# ─── Apply Global Settings ────────────────────────────────────────────────────
# Compares the desired global settings with the current ones on the switch.
# Only sends a PATCH if there is an actual difference (idempotent).


def apply_global_settings(
    module: AnsibleModule,
    connection: Connection,
    desired: Dict[str, Any],
    current: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    if not desired:
        return False, current

    diff: Dict[str, Any] = {}
    for param in ("enabled",):
        if param in desired and desired[param] is not None:
            if current.get(param) != desired[param]:
                diff[param] = desired[param]

    if not diff:
        return False, current

    if module.check_mode:
        merged = _deep_merge(current, diff)
        return True, merged

    connection.send_request(diff, path="/v0/configuration/slpp", method="PATCH")
    merged = _deep_merge(current, diff)
    return True, merged


# ─── Apply VLAN Settings ──────────────────────────────────────────────────────
# Iterates over the user's VLAN entries and applies changes one VLAN at a time.
# For 'replaced'/'overridden' states, all VLAN fields must be specified.
# Only sends a PATCH when values actually differ from the switch (idempotent).


def apply_vlan_settings(
    module: AnsibleModule,
    connection: Connection,
    operations: List[Dict[str, Any]],
    current_map: Dict[int, Dict[str, Any]],
    state_mode: str,
) -> Tuple[bool, Dict[int, Dict[str, Any]], List[int]]:
    if not operations:
        return False, current_map, []

    changed = False
    updated_vlans: List[int] = []
    require_full_definition = state_mode in (STATE_REPLACED, STATE_OVERRIDDEN)

    for entry in operations:
        vlan_id = entry["vlan_id"]
        if require_full_definition:
            missing = [
                param
                for param in VLAN_FIELD_MAP
                if param not in entry or entry[param] is None
            ]
            if missing:
                raise FeSlppError(
                    "VLAN {vlan} requires values for {fields} when state is '{state}'.".format(
                        vlan=vlan_id,
                        fields=", ".join(sorted(missing)),
                        state=state_mode,
                    )
                )
        payload = _build_vlan_payload(entry)
        if not payload:
            continue

        current_settings = current_map.get(vlan_id, {})
        diff: Dict[str, Any] = {}
        for key, value in payload.items():
            if current_settings.get(key) != value:
                diff[key] = value
        if not diff:
            continue

        if module.check_mode:
            changed = True
            updated_vlans.append(vlan_id)
            current_map[vlan_id] = _deep_merge(current_settings, diff)
            continue

        response = connection.send_request(
            diff,
            path=f"/v0/configuration/slpp/vlan/{vlan_id}",
            method="PATCH",
        )
        if isinstance(response, dict) and response.get("errorCode"):
            raise FeSlppError(
                f"Failed to update SLPP settings for VLAN {vlan_id}",
                details=response,
            )
        changed = True
        updated_vlans.append(vlan_id)
        current_map[vlan_id] = _deep_merge(current_settings, diff)
    return changed, current_map, updated_vlans


# ─── Apply Port Settings ──────────────────────────────────────────────────────
# Iterates over the user's port entries and applies changes one port at a time.
# Validates guard/packet-rx mutual exclusivity before touching the API.
# For 'replaced'/'overridden' states, all port fields must be specified.
# Only sends a PATCH when values actually differ from the switch (idempotent).


def apply_port_settings(
    module: AnsibleModule,
    connection: Connection,
    operations: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    state_mode: str,
) -> Tuple[bool, Dict[str, Dict[str, Any]], List[str]]:
    if not operations:
        return False, current_map, []

    changed = False
    updated_ports: List[str] = []
    require_full_definition = state_mode in (STATE_REPLACED, STATE_OVERRIDDEN)

    for entry in operations:
        port_name = _normalize_port_name(entry["name"])
        _validate_port_entry(entry)

        if require_full_definition:
            missing = [
                param
                for param in PORT_FIELD_MAP
                if param not in entry or entry[param] is None
            ]
            if missing:
                raise FeSlppError(
                    "Port '{port}' requires values for {fields} when state is '{state}'.".format(
                        port=port_name,
                        fields=", ".join(sorted(missing)),
                        state=state_mode,
                    )
                )
        payload = _build_port_payload(entry)
        if not payload:
            continue

        current_settings = current_map.get(port_name, {})

        # For merged state, also validate mutual exclusion against
        # the effective config (current + user input).  The user
        # might enable guard without explicitly disabling packet-rx
        # when the port already has packet-rx enabled.
        if state_mode == STATE_MERGED:
            effective_guard = payload.get(
                "enableGuard", current_settings.get("enableGuard", False)
            )
            effective_pkt_rx = payload.get(
                "enablePacketRx", current_settings.get("enablePacketRx", False)
            )
            if effective_guard is True and effective_pkt_rx is True:
                raise FeSlppError(
                    f"Port '{port_name}': enabling enable_guard would "
                    f"conflict with enable_packet_rx which is already "
                    f"active.  Set enable_packet_rx: false explicitly."
                )

        diff: Dict[str, Any] = {}
        for key, value in payload.items():
            if current_settings.get(key) != value:
                diff[key] = value
        if not diff:
            continue

        if module.check_mode:
            changed = True
            updated_ports.append(port_name)
            current_map[port_name] = _deep_merge(current_settings, diff)
            continue

        response = connection.send_request(
            diff,
            path=f"/v0/configuration/slpp/ports/{port_name}",
            method="PATCH",
        )
        if isinstance(response, dict) and response.get("errorCode"):
            raise FeSlppError(
                f"Failed to update SLPP settings for port {port_name}",
                details=response,
            )
        changed = True
        updated_ports.append(port_name)
        current_map[port_name] = _deep_merge(current_settings, diff)
    return changed, current_map, updated_ports


# ─── Delete Port Override ─────────────────────────────────────────────────────
# "Deleting" a port override doesn't actually remove it from the switch;
# instead, it resets all SLPP fields to their factory defaults:
#   enableGuard=false, guardTimeout=0, enablePacketRx=false, packetRxThreshold=1
# This is because the VOSS API doesn't support DELETE on individual port entries.


def _delete_port_override(
    module: AnsibleModule,
    connection: Connection,
    port_name: str,
    current_map: Dict[str, Dict[str, Any]],
) -> bool:
    existing_settings = current_map.get(port_name)
    defaults: Dict[str, Any] = {
        "enableGuard": False,
        "guardTimeout": 0,
        "enablePacketRx": False,
        "packetRxThreshold": 1,
    }

    # Already at defaults — nothing to change
    if existing_settings is not None:
        already_default = all(
            existing_settings.get(k) == v for k, v in defaults.items()
        )
        if already_default:
            return False
    elif existing_settings is None:
        return False

    if module.check_mode:
        current_map.pop(port_name, None)
        return True

    response = connection.send_request(
        defaults,
        path=f"/v0/configuration/slpp/ports/{port_name}",
        method="PATCH",
    )
    if isinstance(response, dict) and response.get("errorCode"):
        raise FeSlppError(
            f"Failed to reset SLPP settings for port {port_name}",
            details=response,
        )
    current_map.pop(port_name, None)
    return True


def delete_port_settings(
    module: AnsibleModule,
    connection: Connection,
    operations: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    graceful: bool = False,
) -> Tuple[bool, Dict[str, Dict[str, Any]], List[str]]:
    """Reset listed ports to SLPP defaults.

    When *graceful* is True, REST API rejections (FeSlppError) for
    individual ports are logged as warnings instead of failing the
    task.  This is used only for the overridden-state removal of
    ports that the user did not list — Insight / auto-sense /
    reserved ports may reject the reset, and skipping them keeps
    the rest of the overridden operation intact.  Transport-level
    errors (ConnectionError) are never suppressed.

    Skipped port names are logged via module.warn() so callers
    can detect incomplete overrides.
    """
    if not operations:
        return False, current_map, []

    changed = False
    removed_ports: List[str] = []
    for entry in operations:
        port_name = _normalize_port_name(entry["name"])
        try:
            if _delete_port_override(module, connection, port_name, current_map):
                changed = True
                removed_ports.append(port_name)
        except FeSlppError as exc:
            if graceful:
                module.warn(
                    "Overridden: skipped port %s — device rejected reset (%s); "
                    "port may be an Insight, auto-sense, or restricted port"
                    % (port_name, str(exc))
                )
                continue
            raise
    return changed, current_map, removed_ports


# ─── Delete VLAN Override ─────────────────────────────────────────────────────
# Similar to port deletion - resets the VLAN SLPP setting to defaults
# (enabled=false) since the API doesn't support DELETE on VLAN entries.


def _delete_vlan_override(
    module: AnsibleModule,
    connection: Connection,
    vlan_id: int,
    current_map: Dict[int, Dict[str, Any]],
) -> bool:
    existing_settings = current_map.get(vlan_id)
    defaults: Dict[str, Any] = {"enabled": False}

    # Already at defaults — nothing to change
    if existing_settings is not None:
        already_default = all(
            existing_settings.get(k) == v for k, v in defaults.items()
        )
        if already_default:
            return False
    elif existing_settings is None:
        return False

    if module.check_mode:
        current_map.pop(vlan_id, None)
        return True

    response = connection.send_request(
        defaults,
        path=f"/v0/configuration/slpp/vlan/{vlan_id}",
        method="PATCH",
    )
    if isinstance(response, dict) and response.get("errorCode"):
        raise FeSlppError(
            f"Failed to reset SLPP settings for VLAN {vlan_id}",
            details=response,
        )
    current_map.pop(vlan_id, None)
    return True


def delete_vlan_settings(
    module: AnsibleModule,
    connection: Connection,
    operations: List[Dict[str, Any]],
    current_map: Dict[int, Dict[str, Any]],
) -> Tuple[bool, Dict[int, Dict[str, Any]], List[int]]:
    if not operations:
        return False, current_map, []

    changed = False
    removed_vlans: List[int] = []
    for entry in operations:
        vlan_id = entry["vlan_id"]
        if _delete_vlan_override(module, connection, vlan_id, current_map):
            changed = True
            removed_vlans.append(vlan_id)
    return changed, current_map, removed_vlans


# ─── Gather State ─────────────────────────────────────────────────────────────
# Fetches the live SLPP state from /v0/state/slpp (read-only endpoint).
# This is separate from the configuration endpoint and shows real-time
# guard status (e.g., whether a port is currently blocked due to a loop).
# The 'gather_filter' parameter lets users limit output to specific ports.


def gather_slpp_state(
    connection: Connection,
    gather_filter: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    data = connection.send_request(None, path="/v0/state/slpp", method="GET")
    if data is None:
        return []
    if not isinstance(data, dict):
        raise FeSlppError(
            "Unexpected response when retrieving SLPP state",
            details={"response": data},
        )
    ports_data = data.get("ports")
    if not isinstance(ports_data, list):
        return []

    filter_set: Optional[set] = None
    if gather_filter:
        filter_set = set()
        for item in gather_filter:
            try:
                filter_set.add(_normalize_port_name(item))
            except FeSlppError:
                raise FeSlppError(
                    "gather_filter contains invalid port identifier: %r" % item
                )

    results: List[Dict[str, Any]] = []
    for entry in ports_data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("portName")
        if not isinstance(name, str):
            continue
        normalized_name = _normalize_port_name(name)
        if filter_set is not None and normalized_name not in filter_set:
            continue
        state_entry: Dict[str, Any] = {"name": normalized_name}
        safe_guard = entry.get("safeGuard")
        if isinstance(safe_guard, dict):
            state_entry["safe_guard"] = {
                "origin": safe_guard.get("origin"),
                "status": safe_guard.get("status"),
                "timer_count": safe_guard.get("timerCount"),
            }
        results.append(state_entry)
    return results


# ─── Main Module Logic ────────────────────────────────────────────────────────
# This is the entry point.  The flow is:
#   1. Create AnsibleModule and validate user input against ARGUMENT_SPEC
#   2. Connect to the switch via httpapi
#   3. Fetch current config from the switch (one GET call)
#   4. Branch based on the requested state:
#      - gathered  → return current config, no changes
#      - merged/replaced/overridden → apply global, port, and VLAN changes
#      - deleted   → reset specified ports/VLANs to defaults
#   5. Optionally fetch live state if gather_state=true
#   6. Return results via module.exit_json()


def run_module() -> None:
    # Step 1: Create module instance (validates user input automatically)
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    # Step 2: Establish connection to the switch
    try:
        connection = get_connection(module)
    except FeSlppError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    result: Dict[str, Any] = {"changed": False}

    try:
        # Step 3: Read user parameters
        state = module.params.get("state")
        gather_filter = module.params.get("gather_filter") or None
        gather_vlan_filter = module.params.get("gather_vlan_filter") or None
        gather_state = bool(module.params.get("gather_state"))

        # Step 4: Fetch the current SLPP configuration from the switch
        current_global, port_map, vlan_map = fetch_slpp_config(connection)

        # ── Gathered (read-only — return current config, make no changes) ─
        if state == STATE_GATHERED:
            result["global_settings"] = dict(current_global)
            result["ports_settings"] = _transform_ports_output(port_map, gather_filter)
            result["vlans_settings"] = _transform_vlans_output(
                vlan_map, gather_vlan_filter
            )
            if gather_state:
                result["ports_state"] = gather_slpp_state(connection, gather_filter)
            module.exit_json(**result)

        # Collect the user's desired configuration
        desired_global = module.params.get("global_settings") or {}
        desired_ports = module.params.get("ports") or []
        desired_vlans = module.params.get("vlans") or []
        # Snapshot current entries (used by 'overridden' to detect extras to remove)
        initial_port_names = set(port_map.keys())
        initial_vlan_ids = set(vlan_map.keys())

        # ── Merged / Replaced / Overridden — apply changes ───────────────
        if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
            # Global settings
            changed_global, current_global = apply_global_settings(
                module,
                connection,
                desired_global,
                current_global,
            )
            if changed_global:
                result["changed"] = True
            if changed_global or (desired_global and module.check_mode):
                result["global_settings"] = dict(current_global)

        elif state == STATE_DELETED:
            if desired_global:
                raise FeSlppError(
                    "Global settings cannot be supplied when state='deleted'."
                )
        else:
            raise FeSlppError(f"Unsupported state '{state}' supplied.")

        # ── Port operations ──────────────────────────────────────────────
        # For 'deleted': reset ports to defaults
        # For 'overridden': apply desired + remove ports not in desired list
        updated_ports: List[str] = []
        removed_ports: List[str] = []

        if state == STATE_DELETED:
            changed_ports, port_map, removed_ports = delete_port_settings(
                module,
                connection,
                desired_ports,
                port_map,
            )
        else:
            changed_ports, port_map, updated_ports = apply_port_settings(
                module,
                connection,
                desired_ports,
                port_map,
                state,
            )
            if state == STATE_OVERRIDDEN:
                desired_port_names = {
                    _normalize_port_name(entry["name"])
                    for entry in desired_ports
                    if "name" in entry
                }
                to_remove = [
                    name
                    for name in initial_port_names
                    if name not in desired_port_names
                ]
                if to_remove:
                    removal_entries = [{"name": name} for name in to_remove]
                    removal_changed, port_map, removal_list = delete_port_settings(
                        module,
                        connection,
                        removal_entries,
                        port_map,
                        graceful=True,
                    )
                    if removal_changed:
                        changed_ports = True
                    removed_ports.extend(removal_list)

        if changed_ports:
            result["changed"] = True
        if updated_ports:
            result["port_updates"] = updated_ports
        if removed_ports:
            result["port_removals"] = removed_ports

        if (changed_ports or (desired_ports and module.check_mode)) and updated_ports:
            result["ports_settings"] = _transform_ports_output(
                {name: port_map.get(name, {}) for name in updated_ports},
                updated_ports,
            )

        # ── VLAN operations ──────────────────────────────────────────────
        # Same pattern as ports: delete resets, overridden removes extras
        updated_vlans: List[int] = []
        removed_vlans: List[int] = []

        if state == STATE_DELETED:
            changed_vlans, vlan_map, removed_vlans = delete_vlan_settings(
                module,
                connection,
                desired_vlans,
                vlan_map,
            )
        else:
            changed_vlans, vlan_map, updated_vlans = apply_vlan_settings(
                module,
                connection,
                desired_vlans,
                vlan_map,
                state,
            )
            if state == STATE_OVERRIDDEN:
                desired_vlan_ids = {
                    entry["vlan_id"] for entry in desired_vlans if "vlan_id" in entry
                }
                to_remove = [
                    vid for vid in initial_vlan_ids if vid not in desired_vlan_ids
                ]
                if to_remove:
                    removal_entries = [{"vlan_id": vid} for vid in to_remove]
                    removal_changed, vlan_map, removal_list = delete_vlan_settings(
                        module,
                        connection,
                        removal_entries,
                        vlan_map,
                    )
                    if removal_changed:
                        changed_vlans = True
                    removed_vlans.extend(removal_list)

        if changed_vlans:
            result["changed"] = True
        if updated_vlans:
            result["vlan_updates"] = updated_vlans
        if removed_vlans:
            result["vlan_removals"] = removed_vlans

        if (changed_vlans or (desired_vlans and module.check_mode)) and updated_vlans:
            result["vlans_settings"] = _transform_vlans_output(
                {vid: vlan_map.get(vid, {}) for vid in updated_vlans},
                updated_vlans,
            )

        # ── Optional live state gathering (from /v0/state/slpp) ──────────
        # Shows real-time guard status (blocked ports, timers, etc.)
        if gather_state:
            if gather_filter:
                state_filter: Optional[List[str]] = list(gather_filter)
            elif updated_ports:
                state_filter = updated_ports
            elif removed_ports:
                state_filter = removed_ports
            else:
                state_filter = None
            result["ports_state"] = gather_slpp_state(connection, state_filter)

        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeSlppError as exc:
        module.fail_json(**exc.to_fail_kwargs())


def main() -> None:
    """Standard Ansible module entry point."""
    run_module()


if __name__ == "__main__":
    main()
