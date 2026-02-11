# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine VLANs via HTTPAPI."""

from __future__ import annotations

import copy

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils._text import to_text

from typing import Any, Dict, List, Optional, Set, Tuple

DOCUMENTATION = r"""
module: extreme_fe_vlans
short_description: Manage VLANs on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Create, update, remove, and query VLANs on ExtremeNetworks Fabric Engine switches using
  the custom ``extreme_fe`` HTTPAPI plugin.
- Supports creating VLANs, ensuring membership, deleting VLANs, and collecting VLAN facts.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped
  with this project.
requirements:
- ansible.netcommon
options:
    state:
        description:
        - Desired VLAN operation.
        - ``merged`` applies the supplied attributes and membership changes incrementally without removing unspecified values.
        - ``replaced`` makes the provided data authoritative for the listed memberships.
        - ``overridden`` clears memberships that are not provided while applying the supplied definitions.
        - ``deleted`` removes the VLAN from the device.
        - ``gathered`` returns current VLAN information without applying changes.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
  vlan_id:
    description:
    - Numeric VLAN identifier (1-4094).
    type: int
  vlan_name:
    description:
    - Friendly name assigned to the VLAN.
    type: str
  vlan_type:
    description:
    - VLAN type identifier required on Fabric Engine platforms.
    - Defaults to PORT_MSTP_RSTP when omitted.
    type: str
    default: PORT_MSTP_RSTP
  i_sid:
    description:
    - I-SID (Service Instance Identifier) to associate with the VLAN.
    - Required when adding SMLT LAGs to a VLAN in an SPB fabric.
    - Range 1-15999999 for user-configurable values.
    type: int
  stp_name:
    description:
    - Auto-bind STP instance name associated with the VLAN.
    - Leave undefined to target the device default (instance 0).
    type: str
  vr_name:
    description:
    - Virtual router/forwarding context the VLAN belongs to.
    type: str
    default: GlobalRouter
  gather_filter:
    description:
    - Limit gathered VLAN facts to these VLAN identifiers.
    type: list
    elements: int
    lag_interfaces:
        description:
        - LAG memberships to ensure present on the VLAN. Use ``tag`` to choose tagged or untagged membership.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                - LAG identifier to manage. Use the numeric LAG ID as reported by the device.
                type: str
                required: true
            tag:
                description:
                - Apply the LAG as a tagged or untagged VLAN member.
                type: str
                choices: [tagged, untagged]
                default: tagged
    remove_lag_interfaces:
        description:
        - LAG memberships to remove from the VLAN when performing merge-style operations.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                - LAG identifier to remove. Use the numeric LAG ID as reported by the device.
                type: str
                required: true
            tag:
                description:
                - Membership type to remove (tagged or untagged).
                type: str
                choices: [tagged, untagged]
                default: tagged
    isis_logical_interfaces:
        description:
        - ISIS logical interfaces to ensure present on the VLAN.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                - Logical interface identifier (for example ``1`` or ``10``).
                type: str
                required: true
            tag:
                description:
                - Assign the logical interface as tagged or untagged within the VLAN.
                type: str
                choices: [tagged, untagged]
                default: tagged
    remove_isis_logical_interfaces:
        description:
        - ISIS logical interface memberships to remove from the VLAN.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                - Logical interface identifier to remove.
                type: str
                required: true
            tag:
                description:
                - Membership type to remove (tagged or untagged).
                type: str
                choices: [tagged, untagged]
                default: tagged
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc:

# =========================================================================
# Full playbook examples with prerequisites:
# To create a complete playbook, uncomment the lines starting with:
#   '# - name:', '# hosts:', '# gather_facts:', and '# tasks:'
# After uncommenting, realign indentation to conform to YAML format
# (playbook level at col 0, tasks indented under 'tasks:')
# =========================================================================
#
# Prerequisites:
#
# ## LAG/MLT dependencies - create LAGs/MLTs before adding them to VLANs
# ## (LAG = OpenAPI term, MLT = CLI term - they are the same thing)
# # mlt 10 enable
# # mlt 11 enable
#
# ## I-SID Requirement:
# # When using SMLT LAGs/MLTs, VLANs MUST have an I-SID association
# # BEFORE adding the LAG/MLT interfaces. The module supports
# # setting i_sid directly, or you can create them via CLI.
#
# # Create the VLAN with I-SID:
# # vlan create 200 name VLAN-200 type port-mstprstp 0
# # vlan i-sid 200 20020
#
# ## Verify Configuration
# # show vlan basic
# # show vlan i-sid
# # show mlt

# -------------------------------------------------------------------------
# Task 1: Create or update VLAN with I-SID and LAG/MLT membership
# Description:
#   - Create a VLAN with I-SID and add LAG/MLT interfaces
#   - 'merged' state is non-destructive (adds/modifies without removing)
#   - i_sid parameter associates the VLAN with an I-SID for SPB fabric
# Prerequisites:
#   - LAG/MLT 10 must exist
# -------------------------------------------------------------------------
# - name: "Task 1: Merge VLAN 20 with I-SID and tagged membership"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Ensure VLAN 20 exists with I-SID and core LAG/MLT membership
  extreme.fe.extreme_fe_vlans:
    state: merged
    vlan_id: 20
    vlan_name: Campus-20
    i_sid: 2020
    vr_name: GlobalRouter
    lag_interfaces:
      - name: "10"
        tag: tagged

# -------------------------------------------------------------------------
# Task 2: Replace VLAN membership with I-SID
# Description:
#   - Enforce specific LAG/MLT membership using 'replaced' state
#   - All interface membership will match exactly what is defined
#   - i_sid ensures the VLAN has proper SPB fabric association
# Prerequisites:
#   - LAG/MLT 10 must exist
# -------------------------------------------------------------------------
# - name: "Task 2: Replace VLAN 200 membership with a specific LAG/MLT"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce tagged membership set with I-SID
  extreme.fe.extreme_fe_vlans:
    state: replaced
    vlan_id: 200
    i_sid: 20020
    vr_name: GlobalRouter
    lag_interfaces:
      - name: "10"
        tag: tagged

# -------------------------------------------------------------------------
# Task 3: Remove specific LAG/MLT from VLAN
# Description:
#   - Remove a specific LAG/MLT from a VLAN while preserving others
#   - 'remove_lag_interfaces' option is used with merged state
# -------------------------------------------------------------------------
# - name: "Task 3: Remove a LAG/MLT from VLAN 200"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Drop LAG/MLT 11 from VLAN 200
  extreme.fe.extreme_fe_vlans:
    state: merged
    vlan_id: 200
    vr_name: GlobalRouter
    remove_lag_interfaces:
      - name: "11"
        tag: tagged

# -------------------------------------------------------------------------
# Task 4: Gather VLAN configuration
# Description:
#   - Retrieve current configuration for specific VLANs
#   - gather_filter limits query to specific VLAN IDs
# -------------------------------------------------------------------------
# - name: "Task 4: Gather VLAN 20 configuration snapshot"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect VLAN information
  extreme.fe.extreme_fe_vlans:
    state: gathered
    gather_filter: [20]
  register: vlan_info

- name: Display VLAN configuration
  ansible.builtin.debug:
    var: vlan_info.vlans
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made.
  returned: always
  type: bool
vlan:
    description: Details for the VLAN processed when the module applies configuration changes or deletes the VLAN.
    returned: when state in [merged, replaced, overridden, deleted]
  type: dict
vlans:
  description: List of VLAN data returned when state is gathered.
  returned: when state == gathered
  type: list
"""

ARGUMENT_SPEC = {
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
    "vlan_id": {"type": "int"},
    "vlan_name": {"type": "str"},
    "vlan_type": {"type": "str", "default": "PORT_MSTP_RSTP"},
    "i_sid": {"type": "int"},
    "stp_name": {"type": "str", "default": None},
    "vr_name": {"type": "str", "default": "GlobalRouter"},
    "gather_filter": {"type": "list", "elements": "int"},
    "lag_interfaces": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "tag": {"type": "str", "choices": ["tagged", "untagged"], "default": "tagged"},
        },
    },
    "remove_lag_interfaces": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "tag": {"type": "str", "choices": ["tagged", "untagged"], "default": "tagged"},
        },
    },
    "isis_logical_interfaces": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "tag": {"type": "str", "choices": ["tagged", "untagged"], "default": "tagged"},
        },
    },
    "remove_isis_logical_interfaces": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "tag": {"type": "str", "choices": ["tagged", "untagged"], "default": "tagged"},
        },
    },
}


class FeVlansError(Exception):
    """Base exception for module-level errors."""

    def __init__(self, message: str, *, details: Optional[Dict[str, object]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, object]:
        data: Dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _is_not_found_response(payload: Optional[object]) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    if code == 404:
        return True
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if isinstance(message, str):
        lowered = message.lower()
        if "not found" in lowered or "does not exist" in lowered:
            return True
    return False


TAG_VALUE_MAP = {"tagged": "TAG", "untagged": "UNTAG"}
INTERFACE_TYPE_LAG = "LAG"
INTERFACE_TYPE_ISIS = "ISIS_LOGICAL_INTERFACE"
_SUCCESS_STATUS_CODES = {200, 201, 202, 204}


def _normalize_state(value: str) -> str:
    normalized = value.lower()
    if normalized in {"present", "absent"}:
        raise FeVlansError(
            "State '%s' is no longer supported. Use 'merged', 'replaced', 'overridden', 'deleted', or 'gathered'."
            % value
        )
    return normalized


def _normalize_membership_entry(option: str, entry: object) -> Optional[Tuple[str, str]]:
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if name is None or str(name).strip() == "":
        raise FeVlansError(f"Interface name is required for '{option}' entries")
    tag_choice = str(entry.get("tag", "tagged")).lower()
    tag_value = TAG_VALUE_MAP.get(tag_choice)
    if tag_value is None:
        raise FeVlansError(f"Unsupported tag value '{tag_choice}' for interface '{name}'")
    return str(name), tag_value


def _key_to_entry(key: Tuple[str, str]) -> Dict[str, str]:
    interface_type, interface_name = key
    return {"interfaceType": interface_type, "interfaceName": interface_name}


def _sanitize_membership(entries: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    sanitized: List[Dict[str, str]] = []
    if not entries:
        return sanitized
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        interface_type = entry.get("interfaceType")
        interface_name = entry.get("interfaceName")
        if not interface_type or not interface_name:
            continue
        sanitized.append(
            {
                "interfaceType": str(interface_type),
                "interfaceName": str(interface_name),
            }
        )
    return sanitized


def _membership_key(entry: Dict[str, str]) -> Tuple[str, str]:
    return (str(entry.get("interfaceType", "")).upper(), str(entry.get("interfaceName", "")))


def _remove_membership_entry(entries: List[Dict[str, str]], key: Tuple[str, str]) -> bool:
    removed = False
    filtered: List[Dict[str, str]] = []
    for entry in entries:
        if not removed and _membership_key(entry) == key:
            removed = True
            continue
        filtered.append(entry)
    if removed:
        entries[:] = filtered
    return removed


def _validate_multi_status(operation: str, vlan_id: int, response: Any) -> None:
    if response in (None, ""):
        return
    entries = response
    if isinstance(entries, dict):
        # multi-status replies typically echo the original request entries
        for key in ("interfaces", "entries", "items", "results"):
            candidate = entries.get(key)
            if isinstance(candidate, list):
                entries = candidate
                break
    if not isinstance(entries, list):
        return
    failures: List[Dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        status = item.get("statusCode")
        try:
            status_int = int(status) if status is not None else None
        except (TypeError, ValueError):
            status_int = None
        if status_int is None or status_int not in _SUCCESS_STATUS_CODES:
            failures.append(
                {
                    "interfaceType": item.get("interfaceType"),
                    "interfaceName": item.get("interfaceName"),
                    "tagType": item.get("tagType"),
                    "statusCode": status,
                    "errorMessage": item.get("errorMessage"),
                }
            )
    if failures:
        raise FeVlansError(
            f"Failed to {operation} VLAN membership for VLAN {vlan_id}",
            details={"failures": failures},
        )


def _membership_operations_for_merge(
    module: AnsibleModule,
) -> Tuple[Dict[str, List[Dict[str, str]]], Dict[str, List[Dict[str, str]]]]:
    additions = {"TAG": [], "UNTAG": []}
    removals = {"TAG": [], "UNTAG": []}
    addition_options = (
        ("lag_interfaces", INTERFACE_TYPE_LAG),
        ("isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    )
    removal_options = (
        ("remove_lag_interfaces", INTERFACE_TYPE_LAG),
        ("remove_isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    )

    for option, interface_type in addition_options:
        entries = module.params.get(option) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            normalized = _normalize_membership_entry(option, entry)
            if normalized is None:
                continue
            name, tag_value = normalized
            payload = {
                "interfaceType": interface_type,
                "interfaceName": name,
            }
            additions[tag_value].append(payload)

    for option, interface_type in removal_options:
        entries = module.params.get(option) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            normalized = _normalize_membership_entry(option, entry)
            if normalized is None:
                continue
            name, tag_value = normalized
            payload = {
                "interfaceType": interface_type,
                "interfaceName": name,
            }
            removals[tag_value].append(payload)
    return additions, removals


def _membership_operations_authoritative(
    module: AnsibleModule,
    existing: Dict[str, Any],
    *,
    purge_missing: bool,
) -> Tuple[Dict[str, List[Dict[str, str]]], Dict[str, List[Dict[str, str]]]]:
    desired_sets: Dict[Tuple[str, str], Optional[Set[Tuple[str, str]]]] = {}
    explicit_removals: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}
    for tag_value in ("TAG", "UNTAG"):
        for iface_type in (INTERFACE_TYPE_LAG, INTERFACE_TYPE_ISIS):
            desired_sets[(tag_value, iface_type)] = None
            explicit_removals[(tag_value, iface_type)] = set()

    current_combination_sets: Dict[Tuple[str, str], Set[Tuple[str, str]]] = {}
    for tag_value, source in (
        ("TAG", existing.get("taggedInterfaces")),
        ("UNTAG", existing.get("untaggedInterfaces")),
    ):
        for entry in _sanitize_membership(source):
            key = _membership_key(entry)
            combo = (tag_value, key[0])
            current_combination_sets.setdefault(combo, set()).add(key)

    addition_options = (
        ("lag_interfaces", INTERFACE_TYPE_LAG),
        ("isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    )
    removal_options = (
        ("remove_lag_interfaces", INTERFACE_TYPE_LAG),
        ("remove_isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    )

    for option, interface_type in addition_options:
        entries = module.params.get(option)
        if entries is None:
            if purge_missing:
                for tag_value in ("TAG", "UNTAG"):
                    if desired_sets[(tag_value, interface_type)] is None:
                        desired_sets[(tag_value, interface_type)] = set()
            continue
        if not isinstance(entries, list):
            continue
        for raw_entry in entries:
            normalized = _normalize_membership_entry(option, raw_entry)
            if normalized is None:
                continue
            name, tag_value = normalized
            key = (interface_type, name)
            combo = (tag_value, interface_type)
            desired_container = desired_sets.get(combo)
            if desired_container is None:
                desired_container = set()
                desired_sets[combo] = desired_container
            desired_container.add(key)

    for option, interface_type in removal_options:
        entries = module.params.get(option) or []
        if not isinstance(entries, list):
            continue
        for raw_entry in entries:
            normalized = _normalize_membership_entry(option, raw_entry)
            if normalized is None:
                continue
            name, tag_value = normalized
            key = (interface_type, name)
            combo = (tag_value, interface_type)
            explicit_removals[combo].add(key)

    additions_sets: Dict[str, Set[Tuple[str, str]]] = {"TAG": set(), "UNTAG": set()}
    removals_sets: Dict[str, Set[Tuple[str, str]]] = {"TAG": set(), "UNTAG": set()}

    combinations = set(current_combination_sets.keys()) | set(desired_sets.keys()) | set(explicit_removals.keys())

    for combo in combinations:
        tag_value, iface_type = combo
        current_keys = current_combination_sets.get(combo, set())
        desired_keys_optional = desired_sets.get(combo)
        removal_keys = set(explicit_removals.get(combo, set()))
        addition_keys: Set[Tuple[str, str]] = set()
        if desired_keys_optional is not None:
            desired_keys = desired_keys_optional
            addition_keys = desired_keys - current_keys
            removal_keys.update(current_keys - desired_keys)
        additions_sets[tag_value].update(addition_keys)
        removals_sets[tag_value].update(removal_keys)

    additions = {
        tag_value: [_key_to_entry(key) for key in sorted(additions_sets[tag_value])]
        for tag_value in ("TAG", "UNTAG")
    }
    removals = {
        tag_value: [_key_to_entry(key) for key in sorted(removals_sets[tag_value])]
        for tag_value in ("TAG", "UNTAG")
    }

    return additions, removals


def _resolve_membership_operations(
    module: AnsibleModule,
    existing: Dict[str, Any],
    state: str,
) -> Tuple[Dict[str, List[Dict[str, str]]], Dict[str, List[Dict[str, str]]]]:
    normalized = state.lower()
    if normalized == "merged":
        return _membership_operations_for_merge(module)
    if normalized == "replaced":
        return _membership_operations_authoritative(module, existing, purge_missing=False)
    if normalized == "overridden":
        return _membership_operations_authoritative(module, existing, purge_missing=True)
    return {"TAG": [], "UNTAG": []}, {"TAG": [], "UNTAG": []}


def _apply_membership_changes(
    module: AnsibleModule,
    connection: Connection,
    vlan_id: int,
    existing: Dict[str, Any],
    additions: Dict[str, List[Dict[str, str]]],
    removals: Dict[str, List[Dict[str, str]]],
) -> Tuple[bool, Dict[str, Any], bool]:
    current_tagged = _sanitize_membership(existing.get("taggedInterfaces"))
    current_untagged = _sanitize_membership(existing.get("untaggedInterfaces"))

    tagged_keys = {_membership_key(entry) for entry in current_tagged}
    untagged_keys = {_membership_key(entry) for entry in current_untagged}

    lag_add_payload: List[Dict[str, str]] = []
    lag_remove_payload: List[Dict[str, str]] = []
    patch_required = False
    membership_changed = False
    tagged_changed = False
    untagged_changed = False

    for tag_value in ("TAG", "UNTAG"):
        target_list = current_tagged if tag_value == "TAG" else current_untagged
        target_keys = tagged_keys if tag_value == "TAG" else untagged_keys

        for entry in additions[tag_value]:
            key = _membership_key(entry)
            if key in target_keys:
                continue
            target_keys.add(key)
            target_list.append(entry.copy())
            membership_changed = True
            if entry["interfaceType"] == INTERFACE_TYPE_LAG:
                lag_add_payload.append({"tagType": tag_value, **entry})
            else:
                patch_required = True
            if tag_value == "TAG":
                tagged_changed = True
            else:
                untagged_changed = True

        for entry in removals[tag_value]:
            key = _membership_key(entry)
            if key not in target_keys:
                continue
            target_keys.remove(key)
            removed = _remove_membership_entry(target_list, key)
            if not removed:
                continue
            membership_changed = True
            if entry["interfaceType"] == INTERFACE_TYPE_LAG:
                lag_remove_payload.append({"tagType": tag_value, **entry})
            else:
                patch_required = True
            if tag_value == "TAG":
                tagged_changed = True
            else:
                untagged_changed = True

    if not membership_changed:
        return False, existing, False

    working_copy = copy.deepcopy(existing) if existing else {}
    working_copy["taggedInterfaces"] = current_tagged
    working_copy["untaggedInterfaces"] = current_untagged

    if module.check_mode:
        return True, working_copy, False

    if lag_add_payload:
        response = connection.send_request(
            lag_add_payload,
            path=f"/v0/operation/vlan/{vlan_id}/interfaces/:add",
            method="POST",
        )
        _validate_multi_status("add", vlan_id, response)

    if lag_remove_payload:
        response = connection.send_request(
            lag_remove_payload,
            path=f"/v0/operation/vlan/{vlan_id}/interfaces/:remove",
            method="POST",
        )
        _validate_multi_status("remove", vlan_id, response)

    if patch_required:
        payload: Dict[str, Any] = {}
        if tagged_changed:
            payload["taggedInterfaces"] = current_tagged
        if untagged_changed:
            payload["untaggedInterfaces"] = current_untagged
        if payload:
            update_vlan(connection, vlan_id, payload)

    return True, working_copy, True


def gather_vlans(module: AnsibleModule, connection: Connection) -> List[Dict[str, object]]:
    gather_filter: Optional[List[int]] = module.params.get("gather_filter")
    if gather_filter:
        result: List[Dict[str, object]] = []
        for vlan_id in gather_filter:
            vlan = get_vlan_config(connection, vlan_id)
            if vlan is not None:
                result.append(vlan)
        return result
    data = connection.send_request(None, path="/v0/configuration/vlan", method="GET")
    if data is None or _is_not_found_response(data):
        return []
    if isinstance(data, list):
        return data
    raise FeVlansError(
        "Unexpected response when retrieving VLAN summary", details={"response": data}
    )


def get_vlan_config(connection: Connection, vlan_id: int) -> Optional[Dict[str, object]]:
    try:
        data = connection.send_request(
            None,
            path=f"/v0/configuration/vlan/{vlan_id}",
            method="GET",
        )
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        return data
    raise FeVlansError(
        "Unexpected response when retrieving VLAN configuration", details={"response": data}
    )


def create_vlan(
    connection: Connection,
    vr_name: str,
    vlan_id: int,
    vlan_name: Optional[str],
    vlan_type: Optional[str],
    stp_name: Optional[str],
    tagged: Optional[List[Dict[str, object]]] = None,
    untagged: Optional[List[Dict[str, object]]] = None,
) -> None:
    payload: Dict[str, object] = {"id": vlan_id}
    if vlan_type:
        payload["vlanType"] = vlan_type
    if stp_name is not None:
        payload["stpName"] = stp_name
    else:
        payload["stpName"] = ""
    if vlan_name is not None:
        payload["name"] = vlan_name
    connection.send_request(payload, path=f"/v0/configuration/vrf/{vr_name}/vlan", method="POST")


def update_vlan(connection: Connection, vlan_id: int, payload: Dict[str, object]) -> None:
    if payload:
        connection.send_request(payload, path=f"/v0/configuration/vlan/{vlan_id}", method="PATCH")


def delete_vlan(connection: Connection, vr_name: str, vlan_id: int) -> None:
    connection.send_request(None, path=f"/v0/configuration/vrf/{vr_name}/vlan/{vlan_id}", method="DELETE")


def get_vlan_isid(connection: Connection, vlan_id: int) -> Optional[int]:
    """Get the I-SID associated with a VLAN, if any."""
    try:
        # Query all ISIDs and find the one for this VLAN
        data = connection.send_request(None, path="/v0/configuration/spbm/l2/isid", method="GET")
        if isinstance(data, list):
            for isid_entry in data:
                if isid_entry.get("platformVlanId") == vlan_id:
                    return isid_entry.get("isid")
        elif isinstance(data, dict):
            items = data.get("items", data.get("data", []))
            for isid_entry in items:
                if isid_entry.get("platformVlanId") == vlan_id:
                    return isid_entry.get("isid")
    except ConnectionError:
        pass
    return None


def create_vlan_isid(connection: Connection, vlan_id: int, i_sid: int) -> None:
    """Create an I-SID association for a VLAN (CVLAN type)."""
    payload = {
        "isidType": "CVLAN",
        "isid": i_sid,
        "platformVlanId": vlan_id,
    }
    connection.send_request(payload, path="/v0/configuration/spbm/l2/isid", method="POST")


def ensure_config(module: AnsibleModule, connection: Connection, state: str) -> Dict[str, object]:
    vlan_id = module.params.get("vlan_id")
    if vlan_id is None:
        raise FeVlansError("Parameter 'vlan_id' must be provided for VLAN configuration states")

    vr_name = module.params["vr_name"]
    vlan_name = module.params.get("vlan_name")
    vlan_type = module.params.get("vlan_type")
    stp_name = module.params.get("stp_name")

    existing_raw = get_vlan_config(connection, vlan_id)
    changed = False
    refresh_needed = False

    if existing_raw is None:
        changed = True
        if module.check_mode:
            existing: Dict[str, Any] = {"id": vlan_id, "vrName": vr_name}
            if vlan_name is not None:
                existing["name"] = vlan_name
            if vlan_type is not None:
                existing["vlanType"] = vlan_type
            if stp_name is not None:
                existing["stpName"] = stp_name
        else:
            create_vlan(connection, vr_name, vlan_id, vlan_name, vlan_type, stp_name)
            existing = get_vlan_config(connection, vlan_id) or {"id": vlan_id, "vrName": vr_name}
    else:
        existing = copy.deepcopy(existing_raw)

    update_payload: Dict[str, object] = {}
    if vlan_name is not None and vlan_name != existing.get("name"):
        update_payload["name"] = vlan_name
        existing["name"] = vlan_name
    if vlan_type is not None and vlan_type != existing.get("vlanType"):
        update_payload["vlanType"] = vlan_type
        existing["vlanType"] = vlan_type
    if stp_name is not None and stp_name != existing.get("stpName"):
        update_payload["stpName"] = stp_name
        existing["stpName"] = stp_name

    if update_payload:
        changed = True
        if not module.check_mode:
            update_vlan(connection, vlan_id, update_payload)
            refresh_needed = True

    # Handle I-SID configuration
    i_sid = module.params.get("i_sid")
    if i_sid is not None:
        current_isid = get_vlan_isid(connection, vlan_id)
        if current_isid != i_sid:
            changed = True
            if not module.check_mode:
                if current_isid is None:
                    create_vlan_isid(connection, vlan_id, i_sid)
                # Note: If i-sid already exists but differs, user must delete it first via CLI
                # The API doesn't support updating i-sid directly
            existing["i_sid"] = i_sid

    additions, removals = _resolve_membership_operations(module, existing, state)

    membership_ops_requested = any(additions.values()) or any(removals.values())
    if membership_ops_requested:
        membership_changed, existing, requires_refresh = _apply_membership_changes(
            module,
            connection,
            vlan_id,
            existing,
            additions,
            removals,
        )
        if membership_changed:
            changed = True
            if requires_refresh:
                refresh_needed = True

    if not module.check_mode and refresh_needed:
        refreshed = get_vlan_config(connection, vlan_id)
        if refreshed is not None:
            existing = refreshed

    return {"changed": changed, "vlan": existing}


def ensure_absent(module: AnsibleModule, connection: Connection) -> Dict[str, object]:
    vlan_id = module.params.get("vlan_id")
    if vlan_id is None:
        raise FeVlansError("Parameter 'vlan_id' must be provided when state=deleted")

    vr_name = module.params["vr_name"]

    existing = get_vlan_config(connection, vlan_id)
    if existing is None:
        return {"changed": False, "vlan": None}

    if module.check_mode:
        return {"changed": True, "vlan": existing}

    delete_vlan(connection, vr_name, vlan_id)
    return {"changed": True, "vlan": existing}


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)
    module.required_if = [
        ["state", "merged", ["vlan_id"]],
        ["state", "replaced", ["vlan_id"]],
        ["state", "overridden", ["vlan_id"]],
        ["state", "deleted", ["vlan_id"]],
    ]

    state = module.params["state"]
    normalized_state = _normalize_state(state).lower()

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if normalized_state == "gathered":
            data = gather_vlans(module, connection)
            module.exit_json(changed=False, vlans=data)
        elif normalized_state == "deleted":
            result = ensure_absent(module, connection)
            module.exit_json(**result)
        else:
            result = ensure_config(module, connection, normalized_state)
            module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeVlansError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
