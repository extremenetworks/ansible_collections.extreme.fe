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
    ports:
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
            native_vlan:
                description:
                    - Native VLAN identifier for trunk ports (0 to clear).
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
# ## Disable Auto-Sense on target ports (required before manual configuration)
# # auto-sense
# #   no enable port 1/5,1/6,1/7,1/8,1/9,1/10
# # exit
#
# ## Enable flow-control-mode boot flag (if using flow_control option)
# # boot config flags flow-control-mode
#
# ## Verify Configuration
# # show auto-sense status
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
    ports:
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

# -------------------------------------------------------------------------
# Task 3: Delete interface configuration overrides
# Description:
#   - Remove custom interface configurations using 'deleted' state
#   - Resets ports to default settings
# Prerequisites:
#   - Target ports must not be Auto-Sense enabled
# -------------------------------------------------------------------------
# - name: "Task 3: Remove interface overrides for ports 1:5 and 1:6"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Clear configuration
  extreme.fe.extreme_fe_interfaces:
    state: deleted
    ports:
      - name: "1:5"
      - name: "1:6"
"""

RETURN = r"""
---
changed:
    description: Indicates whether any changes were made.
    returned: always
    type: bool
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
    "ports": {
        "type": "list",
        "elements": "dict",
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
    "native_vlan": "nativeVlan",
    "ip_arp_inspection_trusted": "ipArpInspectionTrusted",
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


def get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeInterfacesError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def fetch_port_config_map(connection: Connection) -> Dict[str, Dict[str, Any]]:
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


def _normalize_port_payload(entry: Dict[str, Any], state: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for param, rest_key in PORT_FIELD_MAP.items():
        if param not in entry:
            continue
        value = entry.get(param)
        # Skip None values - API does not accept None for any typed field
        if value is None:
            continue
        if rest_key == "autoAdvertisementsList":
            # API expects an array - ensure we send a list copy
            if isinstance(value, list):
                payload[rest_key] = list(value)
        else:
            payload[rest_key] = value
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
            if state in (STATE_REPLACED, STATE_OVERRIDDEN):
                raise FeInterfacesError(
                    f"Port '{port_name}' must include at least one configurable attribute when state is '{state}'."
                )
            continue
        current_settings = current_map.get(port_name, {})
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
        response = connection.send_request(diff, path=f"/v0/configuration/ports/{port_name}", method="PATCH")
        if isinstance(response, dict) and response.get("errorCode"):
            raise FeInterfacesError(
                f"Failed to update interface {port_name}",
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
) -> Tuple[bool, List[str]]:
    if not ports:
        return False, []

    # Default values to reset port configuration (from OpenAPI schema)
    default_payload = {
        "enabled": True,
        "autoNegotiationEnabled": True,
        "autoAdvertisementsList": ["NONE"],
        "debounceTimer": 0,
        "channelized": False,
        "eee": False,
        "portMode": False,
        "flexUni": False,
    }

    changed = False
    removed_ports: List[str] = []
    for entry in ports:
        if "name" not in entry:
            raise FeInterfacesError("Each item in 'ports' must define 'name' when state is 'deleted'.")
        port_name = _normalize_port_name(entry["name"])
        existing_settings = current_map.get(port_name)

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
                    changed = True
                    removed_ports.append(port_name)
                current_map.pop(port_name, None)
                continue
            raise

        if isinstance(response, dict) and response.get("errorCode"):
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


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    try:
        connection = get_connection(module)
    except FeInterfacesError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    result: Dict[str, Any] = {"changed": False}

    try:
        state = module.params.get("state")
        if state == STATE_GATHERED:
            try:
                ports_state = gather_interface_state(connection, module.params.get("gather_filter"))
            except FeInterfacesError as exc:
                module.fail_json(**exc.to_fail_kwargs())
                return
            result["ports_state"] = ports_state
            module.exit_json(**result)

        if state not in {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED}:
            raise FeInterfacesError(f"Unsupported state '{state}' supplied.")

        current_map = fetch_port_config_map(connection)
        current_global = fetch_global_config(connection)
        initial_port_names = set(current_map.keys())

        desired_global = module.params.get("global_settings") or {}
        desired_admin = module.params.get("admin") or []
        desired_ports = module.params.get("ports") or []

        if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
            changed_global, merged_global = apply_global_settings(
                module,
                connection,
                desired_global,
                current_global,
                state,
            )
            if changed_global:
                result["changed"] = True
                result["global_settings"] = merged_global
        else:
            # STATE_DELETED
            if desired_global:
                raise FeInterfacesError("Global settings cannot be supplied when state is 'deleted'.")

        admin_changed = False
        if desired_admin:
            admin_changed, admin_ports = apply_port_admin(
                module,
                connection,
                desired_admin,
                current_map,
                state,
            )
            if admin_changed:
                result["changed"] = True
                result["admin_updates"] = admin_ports

        port_removals: List[str] = []
        port_updates: List[str] = []

        if state == STATE_DELETED:
            port_changed, removed_ports = delete_port_settings(
                module,
                connection,
                desired_ports,
                current_map,
            )
            if port_changed:
                result["changed"] = True
            port_removals.extend(removed_ports)
        else:
            port_changed, port_names = apply_port_settings(
                module,
                connection,
                desired_ports,
                current_map,
                state,
            )
            if port_changed:
                result["changed"] = True
                port_updates.extend(port_names)

            if state == STATE_OVERRIDDEN:
                desired_port_names = {
                    _normalize_port_name(entry["name"])
                    for entry in desired_ports
                    if isinstance(entry, dict) and "name" in entry
                }
                to_remove = [name for name in initial_port_names if name not in desired_port_names]
                if to_remove:
                    removal_entries = [{"name": name} for name in to_remove]
                    removal_changed, removed_ports = delete_port_settings(
                        module,
                        connection,
                        removal_entries,
                        current_map,
                    )
                    if removal_changed:
                        result["changed"] = True
                    port_removals.extend(removed_ports)

        if port_updates:
            result["port_updates"] = port_updates
        if port_removals:
            result["port_removals"] = sorted(set(port_removals))

        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeInterfacesError as exc:
        module.fail_json(**exc.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
