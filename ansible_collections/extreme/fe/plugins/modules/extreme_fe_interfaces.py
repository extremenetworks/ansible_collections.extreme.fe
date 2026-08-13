# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine Ethernet interfaces."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

from typing import Any, Dict, Iterable, List, Optional, Tuple

DOCUMENTATION = r"""
---
module: extreme_fe_interfaces
short_description: Manage Ethernet interfaces on ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
    - Configure administrative state, global interface settings, and per-port attributes on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI plugin.
    - Supports enabling or disabling multiple ports, adjusting Fabric Engine global port flags, and tuning per-port features such as speed, duplex, Energy Efficient Ethernet, and Fabric Engine specific options.
    - Provides standard Ansible network resource states including C(merged), C(replaced), C(overridden), C(deleted), and C(gathered). The C(gathered) state reads interface status from the high-version C(/v1/state/ports) REST endpoints.
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - Ports are supplied through the C(config) list. The parameter was named
      C(ports) before 1.2.1; that name still works as a deprecated alias so
      existing playbooks keep running.
    - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
    - Port names must use slot and port notation such as C(1:5).
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired module operation.
            - C(merged) applies the supplied interface changes incrementally without removing unspecified configuration.
            - C(replaced) treats the supplied values as authoritative for the targeted interfaces.
            - C(overridden) enforces the supplied definitions and clears interface overrides that are not provided.
            - C(deleted) removes the supplied interface configuration, disabling the listed settings and port overrides.
            - C(gathered) returns interface state information without applying changes.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    global_settings:
        description:
            - Fabric Engine global port settings to apply.
        type: dict
        suboptions:
            flow_control_mode:
                description:
                    - Enable or disable the Fabric Engine global flow control flag.
                type: bool
            advanced_feature_bandwidth_reservation:
                description:
                    - Reserve loopback bandwidth for advanced features (Fabric Engine only).
                type: str
                choices: [DISABLE, LOW, HIGH, VIM]
    admin:
        description:
            - Administrative enable/disable operations to apply across ports using the bulk C(/configuration/ports) endpoint.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as C(1:5)).
                type: str
                required: true
            enabled:
                description:
                    - Desired administrative status for the interface.
                type: bool
                required: true
    config:
        aliases:
            - ports
        description:
            - Per-port configuration settings applied through C(/configuration/ports/{port}).
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as C(1:5)).
                type: str
                required: true
            enabled:
                description:
                    - Administrative status for the port.
                type: bool
            description:
                description:
                    - Textual description for the interface (max 255 characters).
                type: str
            speed:
                description:
                    - Operational speed override when auto-negotiation is disabled.
                type: str
                choices: [0M, 10M, 100M, 1G, 2.5G, 5G, 10G, 20G, 25G, 40G, 50G, 100G, 400G, AUTO]
            duplex:
                description:
                    - Duplex setting when auto-negotiation is disabled.
                type: str
                choices: [HALF_DUPLEX, FULL_DUPLEX, NONE]
            auto_negotiation:
                description:
                    - Toggle auto-negotiation for the interface.
                type: bool
            auto_advertisements:
                description:
                    - Authoritative list of auto-negotiation advertisements.
                type: list
                elements: str
                choices: [NONE, 10-HALF, 10-FULL, 100-HALF, 100-FULL, 1000-HALF, 1000-FULL, 2500-FULL, 5000-FULL, 10000-HALF, 10000-FULL, 25000-HALF, 25000-FULL, 40000-FULL, 50000-FULL, 100000-FULL, 400000-FULL]
            flow_control:
                description:
                    - Interface level flow control mode (when global flow control is enabled).
                type: str
                choices: [ENABLE, DISABLE]
            debounce_timer:
                description:
                    - Debounce timer value in milliseconds (0-300000).
                type: int
            channelized:
                description:
                    - Enable or disable channelization on supported Fabric Engine fiber ports.
                type: bool
            fec:
                description:
                    - Forward error correction mode.
                type: str
                choices: [NONE, CLAUSE_74, CLAUSE_91_108, AUTO]
            eee:
                description:
                    - Enable or disable Energy Efficient Ethernet.
                type: bool
            port_mode:
                description:
                    - Enable Fabric Engine tagging mode on the port (true indicates trunk behaviour).
                type: bool
            flex_uni:
                description:
                    - Enable or disable Fabric Engine Flex UNI mode on the port.
                    - Device default is false; if omitted the existing setting is left unchanged, and C(state=deleted) resets it to the device default (false).
                type: bool
                version_added: "1.1.0"
            native_vlan:
                description:
                    - Native VLAN identifier for trunk ports. Valid VLAN IDs are 1-4094.
                    - "C(0) is accepted for backwards compatibility but is currently a
                      no-op. The device rejects every value the module could use to clear
                      the assignment - C(0) with HTTP 422, JSON null with 'None is not of
                      type integer', and C(1) unless the port is already a member of
                      VLAN 1 - so the field is omitted from the request instead. Clearing
                      a native VLAN requires the port to be a member of VLAN 1 and has no
                      REST equivalent."
                    - "Not reset by C(replaced) or C(overridden) for the same reason: an
                      omitted C(native_vlan) leaves the current assignment in place."
                    - "C(deleted) cannot clear it either. The reset payload drops fields
                      whose factory default is null, because the device rejects a typed
                      null, so C(nativeVlan) is never sent and the port keeps its current
                      native VLAN. Removing a native VLAN has to be done from the CLI."
                    - Any other value outside 1-4094 is rejected before the request is sent.
                type: int
            ip_arp_inspection_trusted:
                description:
                    - Mark the interface as trusted for ARP inspection.
                type: bool
    gather_filter:
        description:
            - Limit gathered interface state to these port names.
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
#
# Prerequisites:
#
# ## Disable link-debounce on target ports (required before disabling ports)
# # interface gigabitEthernet 1/5-1/10
# #   no link-debounce
# # exit
#
# ## Disable Autosense on target ports (required before manual configuration)
# # autosense
# #   no enable port 1/5,1/6,1/7,1/8,1/9,1/10
# # exit
#
# ## Enable flow-control-mode boot flag (if using flow_control option)
# # boot config flags flow-control-mode
#
# ## Verify Configuration
# # show autosense status
# # show interfaces gigabitEthernet config 1/5-1/10

# -------------------------------------------------------------------------
# Task 1: Disable multiple ports using merged state
# Description:
#   - Administratively disable a range of ports
#   - 'merged' state is non-destructive (only modifies specified attributes)
# Prerequisites:
#   - Link debounce must be disabled on target ports
# -------------------------------------------------------------------------
# - name: "Task 1: Disable ports 1:5 through 1:10 using merged state"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Disable selected ports
  extreme.fe.extreme_fe_interfaces:
    state: merged
    admin:
      - name: "1:5"
        enabled: false
      - name: "1:6"
        enabled: false
      - name: "1:7"
        enabled: false
      - name: "1:8"
        enabled: false
      - name: "1:9"
        enabled: false
      - name: "1:10"
        enabled: false

# -------------------------------------------------------------------------
# Task 2: Replace interface configuration
# Description:
#   - Enforce specific interface settings using 'replaced' state
#   - All attributes set exactly as defined
# Prerequisites:
#   - Port must be a member of native_vlan (if specified)
#   - flow-control-mode boot flag enabled (if using flow_control)
# -------------------------------------------------------------------------
# - name: "Task 2: Replace configuration for ports 1:5 and 1:6"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Tune interface attributes
  extreme.fe.extreme_fe_interfaces:
    state: replaced
    config:
      - name: "1:5"
        description: Server uplink
        auto_negotiation: false
        speed: 100M
        duplex: FULL_DUPLEX
        flow_control: DISABLE
        ip_arp_inspection_trusted: true
        port_mode: true
        native_vlan: 200
      - name: "1:6"
        description: Backup uplink
        auto_negotiation: true
        flow_control: ENABLE
        flex_uni: false

# -------------------------------------------------------------------------
# Task 3: Delete interface configuration overrides
# Description:
#   - Remove custom interface configurations using 'deleted' state
#   - Resets ports to default settings
# Prerequisites:
#   - Target ports must not be Autosense enabled
# -------------------------------------------------------------------------
# - name: "Task 3: Remove interface overrides for ports 1:5 and 1:6"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Clear configuration
  extreme.fe.extreme_fe_interfaces:
    state: deleted
    config:
      - name: "1:5"
      - name: "1:6"
"""

RETURN = r"""
---
changed:
    description: Indicates whether any changes were made.
    returned: always
    type: bool
before:
    description:
        - Per-port configuration on the device before the task ran.
        - Captured for every state except C(gathered).
        - Built from the bulk ports endpoint, which can leave out fields it
          considers unset - C(description) is the usual one. Ports named in
          C(config) are re-read individually first, so they carry the full
          field set; for the rest of the switch a missing field means the
          bulk listing did not report it, not that the port has no value for
          it.
    returned: when state is not gathered
    type: list
    elements: dict
after:
    description:
        - Per-port configuration on the device after the task ran.
        - Re-read from the device, so it reflects what the device actually
          applied rather than what was requested. Not returned when nothing
          changed or in check mode, since it would repeat C(before).
        - Built the same way as C(before), including the individual re-read of
          the ports named in C(config), so the two snapshots carry the same
          field set and diffing them is meaningful.
    returned: when changed and not in check mode
    type: list
    elements: dict
global_settings:
    description: Resulting global port configuration after applying changes.
    returned: when state in [merged, replaced, overridden] and global settings requested
    type: dict
admin_updates:
    description: Ports whose administrative status was changed during execution.
    returned: when state in [merged, replaced, overridden, deleted] and admin operations provided
    type: list
    elements: dict
port_updates:
    description: Ports whose per-port attributes were modified.
    returned: when state in [merged, replaced, overridden] and per-port operations provided
    type: list
    elements: dict
port_removals:
    description: Ports whose interface overrides were removed during execution.
    returned: when state in [overridden, deleted]
    type: list
    elements: dict
ports_state:
    description: Interface state details returned from the C(/v1/state/ports) API.
    returned: when state == gathered
    type: list
    elements: dict
"""

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# Native VLAN bounds. The OpenAPI EthernetInterface schema declares
# nativeVlan as minimum 0 / maximum 4094, but none of the values the module
# could use to clear the assignment is accepted by the device:
#   nativeVlan = 0     -> HTTP 422 "Port with name <port> is not member of
#                         VLAN ID 0"
#   nativeVlan = null  -> rejected, "None is not of type integer"
#   nativeVlan = 1     -> fails unless the port is already a member of VLAN 1
# So 0 is accepted as input and the field is OMITTED from the payload rather
# than sent -- see _normalize_port_payload(). That makes native_vlan: 0 a
# no-op today; clearing a native VLAN requires the port to be a member of
# VLAN 1 and has no clean REST equivalent.
NATIVE_VLAN_CLEAR = 0
NATIVE_VLAN_MIN = 1
NATIVE_VLAN_MAX = 4094


ARGUMENT_SPEC = {
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
    "global_settings": {
        "type": "dict",
        "options": {
            "flow_control_mode": {"type": "bool"},
            "advanced_feature_bandwidth_reservation": {
                "type": "str",
                "choices": ["DISABLE", "LOW", "HIGH", "VIM"],
            },
        },
    },
    "admin": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "enabled": {"type": "bool", "required": True},
        },
    },
    # Renamed from 'ports' to 'config' so every resource module in the
    # collection uses the same parameter name. The old name stays as a
    # deprecated alias, so existing playbooks keep working and Ansible
    # resolves both to module.params["config"].
    "config": {
        "type": "list",
        "elements": "dict",
        "aliases": ["ports"],
        "deprecated_aliases": [
            {"name": "ports", "version": "2.0.0", "collection_name": "extreme.fe"},
        ],
        "options": {
            "name": {"type": "str", "required": True},
            "enabled": {"type": "bool"},
            "description": {"type": "str"},
            "speed": {
                "type": "str",
                "choices": [
                    "0M",
                    "10M",
                    "100M",
                    "1G",
                    "2.5G",
                    "5G",
                    "10G",
                    "20G",
                    "25G",
                    "40G",
                    "50G",
                    "100G",
                    "400G",
                    "AUTO",
                ],
            },
            "duplex": {
                "type": "str",
                "choices": ["HALF_DUPLEX", "FULL_DUPLEX", "NONE"],
            },
            "auto_negotiation": {"type": "bool"},
            "auto_advertisements": {
                "type": "list",
                "elements": "str",
                "choices": [
                    "NONE",
                    "10-HALF",
                    "10-FULL",
                    "100-HALF",
                    "100-FULL",
                    "1000-HALF",
                    "1000-FULL",
                    "2500-FULL",
                    "5000-FULL",
                    "10000-HALF",
                    "10000-FULL",
                    "25000-HALF",
                    "25000-FULL",
                    "40000-FULL",
                    "50000-FULL",
                    "100000-FULL",
                    "400000-FULL",
                ],
            },
            "flow_control": {
                "type": "str",
                "choices": ["ENABLE", "DISABLE"],
            },
            "debounce_timer": {"type": "int"},
            "channelized": {"type": "bool"},
            "fec": {
                "type": "str",
                "choices": ["NONE", "CLAUSE_74", "CLAUSE_91_108", "AUTO"],
            },
            "eee": {"type": "bool"},
            "port_mode": {"type": "bool"},
            "flex_uni": {"type": "bool"},
            "native_vlan": {"type": "int"},
            "ip_arp_inspection_trusted": {"type": "bool"},
        },
    },
    "gather_filter": {"type": "list", "elements": "str"},
}

GLOBAL_FIELD_MAP = {
    "flow_control_mode": "flowControlMode",
    "advanced_feature_bandwidth_reservation": "advancedFeatureBandwidthReservation",
}

PORT_FIELD_MAP = {
    "enabled": "enabled",
    "description": "description",
    "speed": "speed",
    "duplex": "duplex",
    "auto_negotiation": "autoNegotiationEnabled",
    "auto_advertisements": "autoAdvertisementsList",
    "flow_control": "flowControl",
    "debounce_timer": "debounceTimer",
    "channelized": "channelized",
    "fec": "fec",
    "eee": "eee",
    "port_mode": "portMode",
    "flex_uni": "flexUni",
    "native_vlan": "nativeVlan",
    "ip_arp_inspection_trusted": "ipArpInspectionTrusted",
}

# Factory defaults for ALL port attributes -- used by replaced/overridden/deleted
# to reset omitted fields. Verified via OpenAPI spec (EthernetInterface schema).
# NOTE: physical-layer fields (speed, duplex, autoAdvertisementsList, fec) are
# hardware-specific and set to None so they are NOT force-reset. Forcing them
# breaks links or errors on some hardware (e.g. autoAdvertisementsList=["NONE"]
# disables auto-negotiation and drops live links; speed=100M is rejected on 10G
# ports; fec=NONE is rejected where FEC is unsupported). Auto-negotiation
# (reset to True below) governs the actual speed/duplex/advertisement.
PORT_FULL_DEFAULTS = {
    "enabled": True,                        # default: true
    "description": "",                       # no explicit default; empty string clears
    "autoNegotiationEnabled": True,          # default: true
    "autoAdvertisementsList": None,          # hardware-specific; not force-reset
    "flowControl": "DISABLE",               # default: DISABLE
    "debounceTimer": 0,                      # default: 0
    "channelized": False,                    # default: false
    "fec": None,                             # hardware-specific; not force-reset
    "eee": False,                            # default: false
    "portMode": False,                       # default: false
    "flexUni": False,                        # default: false
    # None here means "never sent", NOT "cleared". The device rejects a typed
    # null ("None is not of type integer"), rejects 0 with HTTP 422, and
    # rejects 1 unless the port already belongs to VLAN 1 -- so no state can
    # clear a native VLAN over REST. Reset drops the field and the port keeps
    # whatever it has; clearing one has to be done from the CLI.
    "nativeVlan": None,
    "ipArpInspectionTrusted": False,         # no explicit default; false is factory
    "speed": None,                           # hardware-specific; not force-reset
    "duplex": None,                          # hardware-specific; not force-reset
}

# What a reset actually puts on the wire. The device rejects a typed null, so
# fields whose factory default is None are dropped and simply left alone --
# see the nativeVlan note above. Shared by the reset itself and by the
# hydration that decides whether a port needs an individual read first, so the
# two can never disagree about which fields matter.
PORT_RESET_PAYLOAD: Dict[str, Any] = {
    key: value for key, value in PORT_FULL_DEFAULTS.items() if value is not None
}


class FeInterfacesError(Exception):
    """Base exception for interface module errors."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _normalize_port_name(raw: str) -> str:
    if not isinstance(raw, str):
        raise FeInterfacesError("Port name must be a string in slot:port format")
    value = raw.strip()
    if not value:
        raise FeInterfacesError("Port name must not be empty")
    return value


def _list_equal(first: Optional[Iterable[Any]], second: Optional[Iterable[Any]]) -> bool:
    if first is None and second is None:
        return True
    if first is None or second is None:
        return False
    first_list = list(first)
    second_list = list(second)
    if len(first_list) != len(second_list):
        return False
    return sorted(first_list) == sorted(second_list)


def _bulk_record_answers(payload: Dict[str, Any],
                         settings: Optional[Dict[str, Any]]) -> bool:
    """True when the bulk record carries every key this payload compares.

    The bulk ports listing omits fields it treats as unset -- description is
    the usual one -- so a diff against it can be wrong for those fields. It is
    only wrong for keys it does not carry, though, so a port whose payload
    touches nothing missing can be diffed straight from the bulk data and
    needs no individual read.
    """
    if not settings:
        return False
    return all(key in settings for key in payload)


def _hydrate_ports(
    connection: Connection,
    current_map: Dict[str, Dict[str, Any]],
    entries: List[Dict[str, Any]],
    state: str,
) -> None:
    """Re-read the individual ports whose bulk record is not good enough.

    Run before the before-snapshot is taken so the snapshot shows the same
    fields the diff is computed from, rather than whatever the bulk listing
    happened to include. Ports the bulk record already answers are skipped, so
    a long config list does not turn into one GET per port for no gain.
    """
    for entry in entries or []:
        name = entry.get("name")
        if name is None:
            continue
        port_name = _normalize_port_name(name)
        if state == STATE_DELETED:
            # A deleted entry is just {'name': ...}, so it builds no payload.
            # The fields that matter are the ones the reset writes, and those
            # decide both the snapshot and whether the port is already clean.
            payload = PORT_RESET_PAYLOAD
        else:
            payload = _normalize_port_payload(entry, state)
        if not payload or _bulk_record_answers(payload, current_map.get(port_name)):
            continue
        full_settings = _fetch_single_port(connection, port_name)
        if full_settings:
            current_map[port_name] = full_settings


def _already_at_defaults(
    existing_settings: Optional[Dict[str, Any]],
    default_payload: Dict[str, Any],
) -> bool:
    """True when a reset would be a no-op for this port.

    Only the fields the reset payload actually sends are compared -- fields
    dropped from it (those whose factory default is null, such as nativeVlan)
    are not reset either way, so they cannot make a difference.

    An unknown port returns False so the reset is still attempted; the caller
    handles a 404 from the device.
    """
    if not existing_settings:
        return False
    for key, default_value in default_payload.items():
        current_value = existing_settings.get(key)
        if key == "autoAdvertisementsList":
            if not _list_equal(current_value, default_value):
                return False
        elif current_value != default_value:
            return False
    return True


def get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeInterfacesError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def fetch_port_config_map(connection: Connection) -> Dict[str, Dict[str, Any]]:
    """GET /v0/configuration/ports -- retrieve all port settings (bulk)."""
    data = connection.send_request(None, path="/v0/configuration/ports", method="GET")
    if data is None:
        return {}
    if not isinstance(data, list):
        raise FeInterfacesError(
            "Unexpected response when retrieving port configuration",
            details={"response": data},
        )
    result: Dict[str, Dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        settings = item.get("settings")
        if not isinstance(settings, dict):
            settings = {}
        result[name] = settings
    return result


def _fetch_single_port(connection: Connection, port_name: str) -> Dict[str, Any]:
    """GET /v0/configuration/ports/{port} -- retrieve full settings for one port.

    The per-port endpoint returns all fields including description,
    which the bulk endpoint may omit. Used for accurate diff comparison.
    """
    try:
        data = connection.send_request(
            None, path="/v0/configuration/ports/%s" % port_name, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return {}
        raise
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def fetch_global_config(connection: Connection) -> Dict[str, Any]:
    try:
        data = connection.send_request(None, path="/v0/configuration/ports/global", method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return {}
        raise
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise FeInterfacesError(
            "Unexpected response when retrieving global port settings",
            details={"response": data},
        )
    return data


def apply_global_settings(
    module: AnsibleModule,
    connection: Connection,
    desired: Dict[str, Any],
    current: Dict[str, Any],
    state: str,
) -> Tuple[bool, Dict[str, Any]]:
    if state == STATE_DELETED:
        if desired:
            raise FeInterfacesError("Global settings cannot be supplied when state is 'deleted'.")
        return False, current
    if not desired:
        return False, current

    payload: Dict[str, Any] = {}
    for param, rest_key in GLOBAL_FIELD_MAP.items():
        if param not in desired:
            continue
        value = desired.get(param)
        if value is None and rest_key not in current:
            continue
        if current.get(rest_key) != value:
            payload[rest_key] = value

    if not payload:
        return False, current

    if module.check_mode:
        new_config = current.copy()
        new_config.update(payload)
        return True, new_config

    connection.send_request(payload, path="/v0/configuration/ports/global", method="PATCH")
    merged = current.copy()
    merged.update(payload)
    return True, merged


def apply_port_admin(
    module: AnsibleModule,
    connection: Connection,
    operations: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    state: str,
) -> Tuple[bool, List[str]]:
    if not operations:
        return False, []

    updates: List[Dict[str, Any]] = []
    changed_ports: List[str] = []
    for op in operations:
        port_name = _normalize_port_name(op["name"])
        desired_enabled = op.get("enabled")
        if desired_enabled is None and state == STATE_DELETED:
            desired_enabled = False
        current_enabled = None
        if port_name in current_map:
            current_enabled = current_map[port_name].get("enabled")
        if desired_enabled is None:
            continue
        if current_enabled is None or bool(current_enabled) != bool(desired_enabled):
            updates.append({"port": port_name, "enabled": bool(desired_enabled)})
            changed_ports.append(port_name)
            # reflect locally to keep downstream comparisons consistent
            current_map.setdefault(port_name, {})["enabled"] = bool(desired_enabled)

    if not updates:
        return False, []

    if module.check_mode:
        return True, changed_ports

    response = connection.send_request(updates, path="/v0/configuration/ports", method="PUT")
    if isinstance(response, dict) and response.get("errorCode"):
        raise FeInterfacesError(
            "Failed to update administrative state for interfaces",
            details=response,
        )
    return True, changed_ports


def _validate_native_vlan(module: AnsibleModule, ports: List[Dict[str, Any]]) -> None:
    """Reject out-of-range native_vlan values before any REST call is made.

    Valid input is 0 (clear the assignment) or a real VLAN ID 1-4094.
    Catching this locally gives the user a clear message instead of an
    opaque HTTP 422 from the device.
    """
    for entry in ports or []:
        value = entry.get("native_vlan")
        # Not supplied, or the documented "clear" sentinel -- nothing to check.
        if value is None or value == NATIVE_VLAN_CLEAR:
            continue
        if value < NATIVE_VLAN_MIN or value > NATIVE_VLAN_MAX:
            module.fail_json(
                msg=(
                    "native_vlan must be {0} (clear the native VLAN assignment) "
                    "or a VLAN ID between {1} and {2}, got {3} on port '{4}'".format(
                        NATIVE_VLAN_CLEAR, NATIVE_VLAN_MIN, NATIVE_VLAN_MAX,
                        value, entry.get("name"),
                    )
                )
            )


def _normalize_port_payload(entry: Dict[str, Any], state: str) -> Dict[str, Any]:
    """Build REST payload from user config entry.

    For merged: only user-supplied fields are included.
    For replaced/overridden: all PORT_FIELD_MAP fields are included,
    using PORT_FULL_DEFAULTS for omitted fields.

    Note: Ansible pre-populates all sub-options with None even when the
    user did not supply them. We detect "user supplied" via value != None.
    """
    payload: Dict[str, Any] = {}
    for param, rest_key in PORT_FIELD_MAP.items():
        value = entry.get(param)
        if value is not None:
            # native_vlan=0 requests "clear". VOSS has no clean clear that
            # works regardless of VLAN 1 membership (nativeVlan=0 is rejected,
            # and nativeVlan=1 fails when the port is not a member of VLAN 1),
            # so omit the field: no-op in merged, harmless on reset. Clearing
            # the native VLAN requires the port to be a member of VLAN 1.
            if param == "native_vlan" and value == 0:
                continue
            if rest_key == "autoAdvertisementsList":
                if isinstance(value, list):
                    payload[rest_key] = list(value)
            else:
                payload[rest_key] = value
        elif state in (STATE_REPLACED, STATE_OVERRIDDEN):
            # User omitted this field — reset to factory default
            default_value = PORT_FULL_DEFAULTS.get(rest_key)
            # Never send None to the API (device rejects typed null values)
            if default_value is not None:
                payload[rest_key] = default_value
    return payload


def apply_port_settings(
    module: AnsibleModule,
    connection: Connection,
    ports: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    state: str,
) -> Tuple[bool, List[str]]:
    if not ports:
        return False, []

    changed_ports: List[str] = []
    for entry in ports:
        port_name = _normalize_port_name(entry["name"])
        payload = _normalize_port_payload(entry, state)
        if not payload:
            continue

        # Sub-issue D fix: use per-port GET for accurate current state.
        # The bulk endpoint may omit fields like description, causing
        # false diffs on subsequent runs. This runs in check mode too --
        # it is a read, and skipping it would leave check mode diffing
        # against the incomplete bulk data and predicting changes that a
        # real run would not make.
        #
        # _hydrate_ports() has normally already done this for the ports in
        # config, so the guard below usually short-circuits; it stays here
        # because this function is also reachable with a map that was never
        # hydrated. Ports whose bulk record carries every key the payload
        # compares are diffed from it directly, with no request at all.
        current_settings = current_map.get(port_name, {})
        if not _bulk_record_answers(payload, current_settings):
            full_settings = _fetch_single_port(connection, port_name)
            if full_settings:
                current_settings = full_settings
                current_map[port_name] = full_settings

        diff: Dict[str, Any] = {}
        for key, desired_value in payload.items():
            if key == "autoAdvertisementsList":
                current_value = current_settings.get(key)
                if _list_equal(current_value, desired_value):
                    continue
                diff[key] = desired_value
            else:
                current_value = current_settings.get(key)
                if current_value == desired_value:
                    continue
                diff[key] = desired_value
        if not diff:
            continue
        if module.check_mode:
            changed_ports.append(port_name)
            continue
        response = connection.send_request(
            diff, path="/v0/configuration/ports/%s" % port_name, method="PATCH")
        if isinstance(response, dict) and response.get("errorCode"):
            raise FeInterfacesError(
                "Failed to update interface %s" % port_name,
                details=response,
            )
        changed_ports.append(port_name)
        stored = current_map.setdefault(port_name, {}).copy()
        stored.update(diff)
        current_map[port_name] = stored
    if not changed_ports:
        return False, []
    return True, changed_ports


def delete_port_settings(
    module: AnsibleModule,
    connection: Connection,
    ports: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    graceful: bool = False,
) -> Tuple[bool, List[str]]:
    if not ports:
        return False, []

    default_payload = PORT_RESET_PAYLOAD

    changed = False
    removed_ports: List[str] = []
    for entry in ports:
        if "name" not in entry:
            raise FeInterfacesError("Each item in 'config' must define 'name' when state is 'deleted'.")
        port_name = _normalize_port_name(entry["name"])
        existing_settings = current_map.get(port_name)

        # A port already sitting at its defaults needs no reset. Without this
        # every run PUTs to every targeted port and reports changed, which
        # matters most for overridden -- it sweeps every port the task did
        # not list, so the cost is one PUT per port on the device.
        if _already_at_defaults(existing_settings, default_payload):
            continue

        # The bulk listing omits some fields, description among them, so a
        # port can look different purely because the data is incomplete --
        # a missing description reads as None against a default of "".
        # Confirm against the per-port endpoint before writing, unless the
        # record already carries every field the reset compares, which is the
        # case for ports _hydrate_ports() has been through. Ports that
        # already looked clean skipped out above, so this costs one GET only
        # where a PUT would otherwise have been issued.
        if existing_settings is not None and not _bulk_record_answers(
                default_payload, existing_settings):
            full_settings = _fetch_single_port(connection, port_name)
            if full_settings:
                existing_settings = full_settings
                current_map[port_name] = full_settings
                if _already_at_defaults(existing_settings, default_payload):
                    continue

        if module.check_mode:
            if existing_settings is not None:
                changed = True
                removed_ports.append(port_name)
                current_map.pop(port_name, None)
            continue

        try:
            # Use PUT with default values to reset port configuration
            # DELETE method is not supported by the API for ports
            response = connection.send_request(default_payload, path=f"/v0/configuration/ports/{port_name}", method="PUT")
        except ConnectionError as exc:
            if getattr(exc, "code", None) == 404:
                if existing_settings is not None:
                    # The port was in the listing when the task started, so
                    # treat the reset as already done rather than failing a
                    # task with nothing left to do.
                    changed = True
                    removed_ports.append(port_name)
                    current_map.pop(port_name, None)
                    continue
                # Not in the bulk listing either. That listing covers every
                # port on the device, so the name does not exist -- almost
                # always a typo. Swallowing it would let a misspelled port
                # report success while nothing was reset, and every other
                # state fails on the same bad name.
                if graceful:
                    module.warn(
                        f"Skipped reset of interface {port_name}: not found on the device")
                    current_map.pop(port_name, None)
                    continue
                raise FeInterfacesError(
                    f"Interface {port_name} does not exist on the device. "
                    "Check the port name in 'config'."
                )
            # graceful: reserved ports (e.g. Insight ports) cannot be reset;
            # skip them with a warning instead of failing the whole task.
            if graceful:
                module.warn(f"Skipped reset of interface {port_name}: {to_text(exc)}")
                current_map.pop(port_name, None)
                continue
            raise

        if isinstance(response, dict) and response.get("errorCode"):
            if graceful:
                module.warn(
                    "Skipped reset of interface %s: %s"
                    % (port_name, response.get("errorMessage", response.get("errorCode")))
                )
                current_map.pop(port_name, None)
                continue
            raise FeInterfacesError(
                f"Failed to reset configuration for interface {port_name}",
                details=response,
            )

        if existing_settings is not None or response is not None:
            changed = True
            removed_ports.append(port_name)
        current_map.pop(port_name, None)

    return changed, removed_ports


def gather_interface_state(
    connection: Connection,
    gather_filter: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    params: Optional[List[str]] = gather_filter or None
    if params:
        results: List[Dict[str, Any]] = []
        for raw in params:
            port_name = _normalize_port_name(raw)
            data = connection.send_request(None, path=f"/v1/state/ports/{port_name}", method="GET")
            if isinstance(data, dict):
                results.append({"name": port_name, "settings": data})
        return results

    data = connection.send_request(None, path="/v1/state/ports", method="GET")
    if data is None:
        return []
    if not isinstance(data, list):
        raise FeInterfacesError(
            "Unexpected response when retrieving interface state",
            details={"response": data},
        )
    return data


def _handle_gathered(module: AnsibleModule, connection: Connection) -> Dict[str, Any]:
    """Handle state=gathered: read-only, return interface state."""
    ports_state = gather_interface_state(
        connection, module.params.get("gather_filter"))
    return {"changed": False, "ports_state": ports_state}


def _handle_overridden_prepass(
    module: AnsibleModule,
    connection: Connection,
    desired_ports: List[Dict[str, Any]],
    initial_port_names: Iterable[str],
    current_map: Dict[str, Dict[str, Any]],
    result: Dict[str, Any],
) -> List[str]:
    """Reset ports not listed in desired_ports (overridden pre-pass)."""
    desired_port_names = {
        _normalize_port_name(entry["name"])
        for entry in desired_ports
        if isinstance(entry, dict) and "name" in entry
    }
    to_remove = [name for name in initial_port_names
                 if name not in desired_port_names]
    if not to_remove:
        return []
    removal_entries = [{"name": name} for name in to_remove]
    removal_changed, removed_ports = delete_port_settings(
        module, connection, removal_entries, current_map, graceful=True)
    if removal_changed:
        result["changed"] = True
    return removed_ports


def _to_ansible_port_output(name: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Convert port settings to Ansible output format."""
    out: Dict[str, Any] = {"name": name}
    for ansible_key, rest_key in PORT_FIELD_MAP.items():
        out[ansible_key] = settings.get(rest_key)
    return out


def _capture_before_snapshot(
    current_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Capture before-state snapshot from current port config map."""
    return [_to_ansible_port_output(name, settings)
            for name, settings in sorted(current_map.items())]


def _handle_action_states(
    module: AnsibleModule,
    connection: Connection,
    state: str,
) -> Dict[str, Any]:
    """Handle merged/replaced/overridden/deleted states."""
    # Pre-flight range check -- fail before touching the device.
    _validate_native_vlan(module, module.params.get("config") or [])

    current_map = fetch_port_config_map(connection)
    current_global = fetch_global_config(connection)
    initial_port_names = set(current_map.keys())

    desired_global = module.params.get("global_settings") or {}
    desired_admin = module.params.get("admin") or []
    desired_ports = module.params.get("config") or []

    # Fill in the ports the task will write before snapshotting them, so
    # 'before' reports the same fields the diff is computed against instead of
    # showing None for anything the bulk listing left out.
    _hydrate_ports(connection, current_map, desired_ports, state)

    # Sub-issue F fix: capture before snapshot
    before_snapshot = _capture_before_snapshot(current_map)

    result: Dict[str, Any] = {"changed": False, "before": before_snapshot}

    # Global settings
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
        changed_global, merged_global = apply_global_settings(
            module, connection, desired_global, current_global, state)
        if changed_global:
            result["changed"] = True
            result["global_settings"] = merged_global
    else:
        if desired_global:
            raise FeInterfacesError(
                "Global settings cannot be supplied when state is 'deleted'.")

    # Admin operations
    if desired_admin:
        admin_changed, admin_ports = apply_port_admin(
            module, connection, desired_admin, current_map, state)
        if admin_changed:
            result["changed"] = True
            result["admin_updates"] = admin_ports

    # Port operations
    port_removals: List[str] = []
    port_updates: List[str] = []

    if state == STATE_DELETED:
        port_changed, removed_ports = delete_port_settings(
            module, connection, desired_ports, current_map)
        if port_changed:
            result["changed"] = True
        port_removals.extend(removed_ports)
    else:
        port_changed, port_names = apply_port_settings(
            module, connection, desired_ports, current_map, state)
        if port_changed:
            result["changed"] = True
            port_updates.extend(port_names)

        if state == STATE_OVERRIDDEN:
            removed = _handle_overridden_prepass(
                module, connection, desired_ports,
                initial_port_names, current_map, result)
            port_removals.extend(removed)

    if port_updates:
        result["port_updates"] = port_updates
    if port_removals:
        result["port_removals"] = sorted(set(port_removals))

    # Sub-issue F fix: capture after snapshot when changes were made
    if result["changed"] and not module.check_mode:
        after_map = fetch_port_config_map(connection)
        # Hydrated the same way as 'before', so the two snapshots carry the
        # same field set and a diff between them is meaningful.
        _hydrate_ports(connection, after_map, desired_ports, state)
        result["after"] = _capture_before_snapshot(after_map)

    return result


def run_module() -> None:
    """Module entry point with state dispatch."""
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    try:
        connection = get_connection(module)
    except FeInterfacesError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    try:
        state = module.params.get("state")
        if state == STATE_GATHERED:
            result = _handle_gathered(module, connection)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED):
            result = _handle_action_states(module, connection, state)
        else:
            raise FeInterfacesError(
                "Unsupported state '%s' supplied." % state)
        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeInterfacesError as exc:
        module.fail_json(**exc.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
