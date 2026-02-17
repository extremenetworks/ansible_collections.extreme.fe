# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine interface VLAN membership."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote

import yaml

DOCUMENTATION = r"""
---
module: extreme_fe_l2_interfaces
short_description: Manage L2 interface VLAN membership on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Configure interface VLAN membership on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI plugin.
- Supports setting access/trunk mode, untagged VLANs, and tagged VLAN lists on physical or LAG interfaces.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
requirements:
- ansible.netcommon
options:
  interface:
    description:
    - Interface identifier, for example C(PORT:1:5) or C(LAG:10). When the type prefix is omitted, C(PORT) is assumed.
    type: str
  interface_type:
    description:
    - Interface type. Use together with C(interface_name) when the combined C(interface) parameter is not supplied.
    type: str
    choices:
    - PORT
    - LAG
  interface_name:
    description:
    - Interface name (for C(PORT) use slot/port notation such as C(1:5)).
    type: str
  port_type:
    description:
    - Interface VLAN mode.
    type: str
    choices:
    - ACCESS
    - TRUNK
  untagged_vlan:
    description:
    - VLAN ID for untagged traffic (port VLAN). Use C(0) to clear the untagged VLAN.
    type: int
  tagged_vlans:
    description:
    - Authoritative list of tagged (allowed) VLANs for the interface. Replaces any existing list.
    type: list
    elements: int
  add_tagged_vlans:
    description:
    - VLANs to add to the tagged list without removing other entries.
    type: list
    elements: int
  remove_tagged_vlans:
    description:
    - VLANs to remove from the tagged list without affecting other entries.
    type: list
    elements: int
  state:
    description:
    - Desired module operation.
    - '`merged` applies the provided parameters incrementally without removing unspecified VLAN membership.'
    - '`replaced` treats the supplied values as authoritative for the target interface.'
    - '`overridden` enforces the supplied values and clears the untagged VLAN and tagged membership when not provided.'
    - '`deleted` removes tagged VLAN membership (optionally limited to the supplied VLAN list) and clears the untagged VLAN when applicable.'
    - '`gathered` returns the current VLAN membership without applying changes.'
    type: str
    choices:
    - merged
    - replaced
    - overridden
    - deleted
    - gathered
    default: merged
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
# ## Create VLANs (if not already existing)
# # vlan create 5 type port-mstprstp 0
# # vlan create 6 type port-mstprstp 0
# # vlan create 20 type port-mstprstp 0
#
# ## Disable Auto-Sense on target ports (required before manual VLAN config)
# # auto-sense
# #   no enable port 1/5,1/7,1/8,1/10
# # exit
#
# ## Verify Configuration
# # show vlan basic
# # show vlan members

# -------------------------------------------------------------------------
# Task 1: Configure access port
# Description:
#   - Configure an interface as an access port in a specific VLAN
#   - Access ports for end devices on a single VLAN
# Prerequisites:
#   - VLAN 5 must exist
# -------------------------------------------------------------------------
# - name: "Task 1: Configure interface 1:5 as an access port in VLAN 5"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Set access port
  extreme.fe.extreme_fe_l2_interfaces:
    interface: PORT:1:5
    port_type: ACCESS
    untagged_vlan: 5
    tagged_vlans: []
    state: replaced

# -------------------------------------------------------------------------
# Task 2: Configure trunk port with tagged VLANs
# Description:
#   - Configure a trunk port with multiple tagged VLANs
#   - Trunk ports for switch-to-switch connections
# Prerequisites:
#   - VLANs 5 and 6 must exist
# -------------------------------------------------------------------------
# - name: "Task 2: Add VLANs 5 and 6 to trunk port 1:10"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Ensure trunk membership
  extreme.fe.extreme_fe_l2_interfaces:
    interface: PORT:1:10
    port_type: TRUNK
    untagged_vlan: 1
    tagged_vlans: [5, 6]
    state: replaced

# -------------------------------------------------------------------------
# Task 3: Remove VLAN from interface
# Description:
#   - Remove a specific tagged VLAN using 'remove_tagged_vlans' option
#   - Useful for cleaning up VLAN assignments
# Prerequisites:
#   - VLAN 20 must be added to port 1:7 first
# -------------------------------------------------------------------------
# - name: "Task 3: Remove VLAN 20 from interface 1:7"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Drop tagged VLAN 20
  extreme.fe.extreme_fe_l2_interfaces:
    interface: PORT:1:7
    remove_tagged_vlans: [20]
    state: merged

# -------------------------------------------------------------------------
# Task 4: Gather L2 interface configuration
# Description:
#   - Retrieve current L2 configuration (port type, VLANs)
# -------------------------------------------------------------------------
# - name: "Task 4: Gather VLAN configuration for interface 1:8"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather interface VLAN settings
  extreme.fe.extreme_fe_l2_interfaces:
    interface: PORT:1:8
    state: gathered
  register: l2_config
"""

RETURN = r"""
---
changed:
    description: Indicates whether any changes were made.
    returned: always
    type: bool
interface:
    description: VLAN settings reported by the switch for the target interface.
    returned: when state != deleted or when deleted modifies configuration
    type: dict
"""

ARGUMENT_SPEC = {
    "interface": {"type": "str"},
    "interface_type": {"type": "str", "choices": ["PORT", "LAG"]},
    "interface_name": {"type": "str"},
    "port_type": {"type": "str", "choices": ["ACCESS", "TRUNK"]},
    "untagged_vlan": {"type": "int"},
    "tagged_vlans": {"type": "list", "elements": "int"},
    "add_tagged_vlans": {"type": "list", "elements": "int"},
    "remove_tagged_vlans": {"type": "list", "elements": "int"},
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}

KNOWN_INTERFACE_TYPES: Set[str] = {"PORT", "LAG"}

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"


class FeL2InterfacesError(Exception):
    """Base exception for the L2 interface module."""

    def __init__(self, message: str, *, details: Optional[Dict[str, object]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, object]:
        data: Dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _parse_interface(module: AnsibleModule) -> Tuple[str, str]:
    iface_value = module.params.get("interface")
    iface_type = module.params.get("interface_type")
    iface_name = module.params.get("interface_name")

    if iface_type and iface_name:
        return iface_type.strip().upper(), iface_name.strip()

    if iface_value:
        raw = str(iface_value).strip()
        if not raw:
            raise FeL2InterfacesError("Interface value must not be empty")
        if ":" in raw:
            prefix, rest = raw.split(":", 1)
            prefix_upper = prefix.strip().upper()
            if prefix_upper in KNOWN_INTERFACE_TYPES:
                return prefix_upper, rest.strip()
        # default to PORT if type not provided
        return "PORT", raw

    raise FeL2InterfacesError(
        "Either 'interface' or both 'interface_type' and 'interface_name' must be provided"
    )


def _normalize_vlan_list(value: Optional[Iterable[object]]) -> List[int]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = yaml.safe_load(value)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            value = parsed
        else:
            value = [value]
    result: List[int] = []
    for item in value:
        if item is None:
            continue
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            raise FeL2InterfacesError(f"Unable to convert VLAN value '{item}' to an integer")
    return result


def _is_not_found_response(payload: Optional[object]) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    if code == 404:
        return True
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if isinstance(message, str) and "not found" in message.lower():
        return True
    return False


def _interface_path(iface_type: str, iface_name: str) -> str:
    return f"/v0/configuration/vlan/interfaces/type/{quote(iface_type)}/name/{quote(iface_name)}"


def get_interface_settings(connection: Connection, iface_type: str, iface_name: str) -> Optional[Dict[str, object]]:
    try:
        data = connection.send_request(None, path=_interface_path(iface_type, iface_name), method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        # REST response may return the settings directly or nested inside interfaceSettings
        if "interfaceSettings" in data and isinstance(data["interfaceSettings"], dict):
            return data["interfaceSettings"]
        return data
    raise FeL2InterfacesError(
        "Unexpected response when retrieving interface VLAN configuration", details={"response": data}
    )


def replace_interface_settings(
    connection: Connection,
    iface_type: str,
    iface_name: str,
    payload: Dict[str, object],
) -> None:
    connection.send_request(payload, path=_interface_path(iface_type, iface_name), method="PUT")


def _normalize_port_type(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip().upper()
        if stripped:
            return stripped
        return None
    raise FeL2InterfacesError(f"Unsupported port_type value '{value}' supplied")


def _normalize_vlan_value(value: Optional[object]) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise FeL2InterfacesError(f"Unable to convert VLAN value '{value}' to an integer")


def _build_desired_payload(
    module: AnsibleModule,
    existing: Dict[str, Any],
    state: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    params = module.params

    current_port_type = _normalize_port_type(existing.get("portType"))
    current_untagged = _normalize_vlan_value(existing.get("portVlan"))
    current_allowed = {int(v) for v in existing.get("allowedVlans") or []}

    desired_port_type = _normalize_port_type(params.get("port_type"))
    tagged_vlans = params.get("tagged_vlans")
    add_tagged = params.get("add_tagged_vlans")
    remove_tagged = params.get("remove_tagged_vlans")
    target_untagged = _normalize_vlan_value(params.get("untagged_vlan"))

    if state in (STATE_REPLACED, STATE_OVERRIDDEN):
        if tagged_vlans is None:
            raise FeL2InterfacesError(
                "'tagged_vlans' must be supplied when state is 'replaced' or 'overridden'."
            )
        if target_untagged is None:
            raise FeL2InterfacesError(
                "'untagged_vlan' must be supplied when state is 'replaced' or 'overridden'."
            )
        if add_tagged not in (None, []) or remove_tagged not in (None, []):
            raise FeL2InterfacesError(
                "'add_tagged_vlans' and 'remove_tagged_vlans' are not valid when state is 'replaced' or 'overridden'."
            )
        target_allowed: Set[int] = set(_normalize_vlan_list(tagged_vlans))
        if desired_port_type is None:
            desired_port_type = "TRUNK" if target_allowed else "ACCESS"
        if state == STATE_OVERRIDDEN:
            # Overridden enforces the supplied values exactly; no additional adjustments required.
            pass
    else:
        target_allowed = set(current_allowed)
        if tagged_vlans is not None:
            target_allowed = set(_normalize_vlan_list(tagged_vlans))
        target_allowed |= set(_normalize_vlan_list(add_tagged))
        target_allowed -= set(_normalize_vlan_list(remove_tagged))
        if target_untagged is None:
            target_untagged = current_untagged
        if desired_port_type is None:
            desired_port_type = current_port_type or ("TRUNK" if target_allowed else "ACCESS")

    if desired_port_type is None:
        desired_port_type = "TRUNK" if target_allowed else "ACCESS"

    payload: Dict[str, Any] = {
        "portType": desired_port_type,
        "allowedVlans": sorted(target_allowed),
    }
    if target_untagged is not None:
        payload["portVlan"] = target_untagged

    comparison_state: Dict[str, Any] = {
        "portType": desired_port_type,
        "portVlan": target_untagged,
        "allowedVlans": sorted(target_allowed),
    }
    return payload, comparison_state


def configure_interface(module: AnsibleModule, connection: Connection, state: str) -> Dict[str, object]:
    iface_type, iface_name = _parse_interface(module)
    existing = get_interface_settings(connection, iface_type, iface_name) or {}

    payload, desired_state = _build_desired_payload(module, existing, state)

    current_comparison = {
        "portType": _normalize_port_type(existing.get("portType")),
        "portVlan": _normalize_vlan_value(existing.get("portVlan")),
        "allowedVlans": sorted({int(v) for v in existing.get("allowedVlans") or []}),
    }

    if current_comparison == desired_state:
        return {"changed": False, "interface": existing or desired_state}

    if module.check_mode:
        return {"changed": True, "interface": desired_state}

    replace_interface_settings(connection, iface_type, iface_name, payload)
    final = get_interface_settings(connection, iface_type, iface_name) or desired_state
    return {"changed": True, "interface": final}


def delete_interface(module: AnsibleModule, connection: Connection) -> Dict[str, object]:
    iface_type, iface_name = _parse_interface(module)
    params = module.params

    existing = get_interface_settings(connection, iface_type, iface_name)
    if existing is None:
        return {"changed": False, "interface": None}

    current_port_type = _normalize_port_type(existing.get("portType"))
    current_untagged = _normalize_vlan_value(existing.get("portVlan"))
    current_allowed = {int(v) for v in existing.get("allowedVlans") or []}

    remove_list = set(_normalize_vlan_list(params.get("tagged_vlans")))
    remove_list |= set(_normalize_vlan_list(params.get("remove_tagged_vlans")))

    target_allowed: Set[int]
    if remove_list:
        target_allowed = current_allowed - remove_list
    else:
        target_allowed = set()

    target_untagged = current_untagged
    requested_untagged = params.get("untagged_vlan")
    if requested_untagged is not None:
        normalized_requested = _normalize_vlan_value(requested_untagged)
        if current_untagged == normalized_requested:
            target_untagged = 0
    elif not remove_list:
        target_untagged = 0

    desired_port_type = _normalize_port_type(params.get("port_type"))
    if desired_port_type is None:
        desired_port_type = current_port_type or ("ACCESS" if not target_allowed and target_untagged in (0, None) else "TRUNK")

    desired_state = {
        "portType": desired_port_type,
        "portVlan": target_untagged,
        "allowedVlans": sorted(target_allowed),
    }

    current_state = {
        "portType": current_port_type,
        "portVlan": current_untagged,
        "allowedVlans": sorted(current_allowed),
    }

    if current_state == desired_state:
        return {"changed": False, "interface": existing}

    payload: Dict[str, Any] = {
        "portType": desired_port_type,
        "allowedVlans": sorted(target_allowed),
        "portVlan": target_untagged if target_untagged is not None else 0,
    }

    if module.check_mode:
        return {"changed": True, "interface": desired_state}

    replace_interface_settings(connection, iface_type, iface_name, payload)
    final = get_interface_settings(connection, iface_type, iface_name) or desired_state
    return {"changed": True, "interface": final}


def gather_interface(module: AnsibleModule, connection: Connection) -> Dict[str, object]:
    iface_type, iface_name = _parse_interface(module)
    data = get_interface_settings(connection, iface_type, iface_name)
    return {"changed": False, "interface": data}


def run_module() -> None:
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
        required_one_of=[("interface", "interface_type")],
        required_together=[("interface_type", "interface_name")],
    )

    state = module.params["state"]

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == STATE_GATHERED:
            result = gather_interface(module, connection)
            module.exit_json(**result)
        elif state == STATE_DELETED:
            result = delete_interface(module, connection)
            module.exit_json(**result)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
            result = configure_interface(module, connection, state)
            module.exit_json(**result)
        else:
            raise FeL2InterfacesError(f"Unsupported state '{state}' supplied.")
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeL2InterfacesError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
