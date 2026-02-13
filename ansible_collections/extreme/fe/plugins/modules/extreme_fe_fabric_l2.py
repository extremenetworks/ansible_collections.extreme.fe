# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine ISIDs via HTTPAPI."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional
from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text


DOCUMENTATION = r"""
module: extreme_fe_fabric_l2
short_description: Manage Fabric Engine ISIDs on ExtremeNetworks switches
version_added: '1.0.0'
description:
    - "Manage Layer 2 ISIDs (service instance identifiers) on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI plugin."
    - Supports provisioning CVLAN-backed ISIDs, updating friendly names, gathering existing definitions, and removing bindings.
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - "Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project."
    - Currently supports managing CVLAN-backed ISIDs. Additional ISID types may be implemented in future revisions.
    - Supports Ansible check mode for configuration states.
requirements:
    - ansible.netcommon
options:
  state:
        description:
            - Desired module operation.
            - "``merged`` ensures the supplied attributes are merged with the running configuration and creates the ISID when missing."
            - "``replaced`` treats the supplied values as authoritative for the targeted ISID."
            - "``overridden`` enforces the supplied values and clears the friendly name when it is omitted."
            - "``deleted`` removes the ISID binding from the device."
            - "``gathered`` returns current ISID data without making changes."
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
  isid:
    description:
      - Numeric service identifier (1-15999999).
      - Required when ``state`` is not ``gathered``.
    type: int
  isid_type:
    description:
      - ISID service type. Only ``CVLAN`` is currently supported.
    type: str
    choices: [CVLAN]
    default: CVLAN
  name:
    description:
      - Friendly name to associate with the ISID.
      - When ``state`` is ``overridden`` and ``name`` is omitted, the module clears the existing friendly name.
    type: str
  cvlan:
    description:
      - CVLAN identifier to bind to the ISID when ``isid_type`` is ``CVLAN``.
      - Required when creating a new ISID or when deleting an existing ISID whose CVLAN cannot be discovered automatically.
    type: int
  gather_filter:
    description:
      - Limit gathered output to this list of ISID identifiers.
      - When omitted, the module returns all configured ISIDs.
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
#
# Prerequisites:
#
# ## Create VLANs for ISID bindings (if not already existing)
# # vlan create 500 type port-mstprstp 0
# # vlan create 600 type port-mstprstp 0
# # vlan create 700 type port-mstprstp 0
#
# ## For Tasks 2-4 (replace/override/delete), create ISIDs first
# # vlan i-sid 500 500
# # vlan i-sid 600 600
# # vlan i-sid 700 700
#
# ## Verify Configuration
# # show vlan i-sid

# -------------------------------------------------------------------------
# Task 1: Provision ISID 500
# Description:
#   - Create or update an ISID entry with a specific CVLAN and name
#   - 'merged' state is non-destructive (adds/modifies without removing)
# Prerequisites:
#   - VLAN 500 must exist
# -------------------------------------------------------------------------
# - name: "Task 1: Merge ISID 500 bound to CVLAN 500"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Provision ISID 500
  extreme.fe.extreme_fe_fabric_l2:
    isid: 500
    cvlan: 500
    name: Campus-500
    state: merged

# -------------------------------------------------------------------------
# Task 2: Replace ISID 600 configuration
# Description:
#   - Enforce specific ISID configuration using 'replaced' state
#   - Ensures ISID matches exactly what is defined
# Prerequisites:
#   - VLAN 600 must exist
#   - ISID 600 should already exist
# -------------------------------------------------------------------------
# - name: "Task 2: Replace ISID 600 definition"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Ensure ISID 600 matches the reference configuration
  extreme.fe.extreme_fe_fabric_l2:
    isid: 600
    cvlan: 600
    name: Campus-Core-600
    state: replaced

# -------------------------------------------------------------------------
# Task 3: Override ISID 500 to remove the name
# Description:
#   - 'overridden' state replaces entire ISID configuration
#   - No 'name' parameter clears existing friendly name
# Prerequisites:
#   - ISID 500 must exist
# -------------------------------------------------------------------------
# - name: "Task 3: Clear the friendly name while keeping the CVLAN binding"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Remove ISID name
  extreme.fe.extreme_fe_fabric_l2:
    isid: 500
    cvlan: 500
    state: overridden

# -------------------------------------------------------------------------
# Task 4: Delete ISID 700
# Description:
#   - Remove an ISID configuration using 'deleted' state
#   - Unbinds CVLAN from ISID (VLAN is NOT deleted)
# Prerequisites:
#   - ISID 700 must exist
# -------------------------------------------------------------------------
# - name: "Task 4: Remove ISID 700"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Delete ISID 700
  extreme.fe.extreme_fe_fabric_l2:
    isid: 700
    cvlan: 700
    state: deleted

# -------------------------------------------------------------------------
# Task 5: Gather ISID information
# Description:
#   - Retrieve current ISID configuration (read-only operation)
# -------------------------------------------------------------------------
# - name: "Task 5: Gather the configured ISIDs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect ISID information
  extreme.fe.extreme_fe_fabric_l2:
    state: gathered
  register: isid_config
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made.
  returned: always
  type: bool
before:
  description: Configuration prior to module execution.
  returned: success and state != gathered
  type: dict
  sample:
    isid: 500
    name: Campus-500
    platformVlanId: 500
after:
  description: Configuration after module execution.
  returned: success and state != deleted and state != gathered
  type: dict
  sample:
    isid: 500
    name: Campus-500
    platformVlanId: 500
gathered:
  description: List of ISID entries discovered from the device.
  returned: when state == gathered
  type: list
  sample:
    - isid: 500
      name: Campus-500
      platformVlanId: 500
"""


ARGUMENT_SPEC = {
    "state": {"type": "str", "choices": ["merged", "replaced", "overridden", "deleted", "gathered"], "default": "merged"},
    "isid": {"type": "int"},
    "isid_type": {"type": "str", "choices": ["CVLAN"], "default": "CVLAN"},
    "name": {"type": "str"},
    "cvlan": {"type": "int"},
    "gather_filter": {"type": "list", "elements": "int"},
}


ISID_BASE_PATH = "/v0/configuration/spbm/l2/isid"


class FeFabricL2Error(Exception):
    """Base exception for the Fabric L2 module."""

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


def _extract_cvlan(data: Optional[Dict[str, object]]) -> Optional[int]:
    if not isinstance(data, dict):
        return None
    interfaces = data.get("interfaces")
    platform_vlan: Optional[object] = None
    if isinstance(interfaces, dict):
        platform_vlan = interfaces.get("platformVlanId") or interfaces.get("platform_vlan_id")
    if platform_vlan is None:
        platform_vlan = data.get("platformVlanId") or data.get("platform_vlan_id")
    if platform_vlan is None:
        return None
    try:
        return int(platform_vlan)
    except (TypeError, ValueError):
        return None


def _cvlan_delete_path(isid: int, cvlan: int) -> str:
    return "/".join(
        [
            ISID_BASE_PATH,
            quote(str(isid), safe=""),
            "cvlan",
            quote(str(cvlan), safe=""),
        ]
    )


def _isid_path(isid: int) -> str:
    return "/".join([ISID_BASE_PATH, quote(str(isid), safe="")])


def _ensure_list(payload: Optional[object]) -> List[Dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("isids", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def get_isid(connection: Connection, isid: int) -> Optional[Dict[str, object]]:
    path = _isid_path(isid)
    try:
        data = connection.send_request(None, path=path, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None:
        return None
    if _is_not_found_response(data):
        return None
    return data if isinstance(data, dict) else None


def list_isids(connection: Connection) -> List[Dict[str, object]]:
    try:
        payload = connection.send_request(None, path=ISID_BASE_PATH, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    return _ensure_list(payload)


def create_isid(
    connection: Connection,
    *,
    isid: int,
    isid_type: str,
    cvlan: Optional[int],
    name: Optional[str],
) -> None:
    payload: Dict[str, object] = {"isidType": isid_type, "isid": isid}
    if isid_type == "CVLAN":
        if cvlan is None:
            raise FeFabricL2Error("Parameter 'cvlan' is required when creating a CVLAN ISID")
        payload["platformVlanId"] = cvlan
    if name is not None:
        payload["name"] = name
    connection.send_request(payload, path=ISID_BASE_PATH, method="POST")


def update_isid_name(connection: Connection, *, isid: int, name: str) -> None:
    path = _isid_path(isid)
    payload = {"name": name}
    connection.send_request(payload, path=path, method="PATCH")


def delete_isid(connection: Connection, *, isid: int, cvlan: int) -> None:
    path = _cvlan_delete_path(isid, cvlan)
    connection.send_request(None, path=path, method="DELETE")


def _simulate_after_creation(isid: int, isid_type: str, cvlan: Optional[int], name: Optional[str]) -> Dict[str, object]:
    simulated = {"isid": isid, "isidType": isid_type}
    if cvlan is not None:
        simulated["platformVlanId"] = cvlan
    if name is not None:
        simulated["name"] = name
    return simulated


def _validate_isid_required(module: AnsibleModule) -> None:
    state = module.params["state"]
    if state in ("merged", "replaced", "overridden", "deleted") and module.params.get("isid") is None:
        raise FeFabricL2Error("Parameter 'isid' is required for state=%s" % state)


def ensure_configured(module: AnsibleModule, connection: Connection, *, state: str) -> Dict[str, object]:
    _validate_isid_required(module)

    isid = module.params.get("isid")
    isid_type = module.params["isid_type"]
    desired_name = module.params.get("name")
    desired_cvlan = module.params.get("cvlan")

    before = get_isid(connection, isid)
    before_data = deepcopy(before) if isinstance(before, dict) else None

    if before is None:
        if isid_type == "CVLAN" and desired_cvlan is None:
            raise FeFabricL2Error("Parameter 'cvlan' is required when creating a CVLAN ISID")
        if module.check_mode:
            after = _simulate_after_creation(isid, isid_type, desired_cvlan, desired_name)
            return {"changed": True, "before": None, "after": after}
        create_isid(
            connection,
            isid=isid,
            isid_type=isid_type,
            cvlan=desired_cvlan,
            name=desired_name,
        )
        after = get_isid(connection, isid)
        return {"changed": True, "before": None, "after": after}

    existing_type = (before.get("type") or before.get("isidType") or "").upper()
    if existing_type and existing_type != isid_type:
        raise FeFabricL2Error(
            f"ISID {isid} exists with type {existing_type}, which does not match requested {isid_type}"
        )

    current_cvlan = _extract_cvlan(before)
    current_name = before.get("name")

    change_requested = False
    refresh_after = False
    simulated_after = deepcopy(before)

    if desired_cvlan is not None and desired_cvlan != current_cvlan:
        change_requested = True
        if module.check_mode:
            simulated_after["platformVlanId"] = desired_cvlan
        else:
            if current_cvlan is None:
                raise FeFabricL2Error(
                    "Unable to determine existing CVLAN binding; provide the 'cvlan' parameter that matches the device"
                )
            delete_isid(connection, isid=isid, cvlan=current_cvlan)
            replacement_name = desired_name if desired_name is not None else current_name
            create_isid(
                connection,
                isid=isid,
                isid_type=isid_type,
                cvlan=desired_cvlan,
                name=replacement_name,
            )
            refresh_after = True

    target_name: Optional[str]
    if state == "overridden" and desired_name is None:
        target_name = ""
    else:
        target_name = desired_name

    if target_name is not None and (current_name or "") != target_name:
        change_requested = True
        if module.check_mode:
            simulated_after["name"] = target_name
        else:
            update_isid_name(connection, isid=isid, name=target_name)
            refresh_after = True

    if module.check_mode:
        after_data = simulated_after if change_requested else before_data
        return {"changed": change_requested, "before": before_data, "after": after_data}

    if not change_requested:
        return {"changed": False, "before": before_data, "after": before_data}

    after = get_isid(connection, isid) if refresh_after else before
    return {"changed": True, "before": before_data, "after": after}


def ensure_deleted(module: AnsibleModule, connection: Connection) -> Dict[str, object]:
    _validate_isid_required(module)

    isid = module.params.get("isid")
    supplied_cvlan = module.params.get("cvlan")

    current = get_isid(connection, isid)
    before = deepcopy(current) if isinstance(current, dict) else None

    if current is None:
        return {"changed": False, "before": None, "after": None}

    current_cvlan = _extract_cvlan(current)
    target_cvlan = supplied_cvlan or current_cvlan
    if target_cvlan is None:
        raise FeFabricL2Error("Unable to determine CVLAN bound to ISID; provide the 'cvlan' parameter")

    if module.check_mode:
        return {"changed": True, "before": before, "after": None}

    delete_isid(connection, isid=isid, cvlan=target_cvlan)
    return {"changed": True, "before": before, "after": None}


def ensure_gathered(module: AnsibleModule, connection: Connection) -> Dict[str, object]:
    gather_filter: Optional[List[int]] = module.params.get("gather_filter")
    isid_value: Optional[int] = module.params.get("isid")

    gathered: List[Dict[str, object]] = []

    if gather_filter:
        for candidate in gather_filter:
            record = get_isid(connection, candidate)
            if record:
                gathered.append(record)
    elif isid_value is not None:
        record = get_isid(connection, isid_value)
        if record:
            gathered.append(record)
    else:
        gathered = list_isids(connection)

    return {"changed": False, "gathered": gathered}


def run_module() -> None:
    required_if = [
        ("state", "merged", ["isid"]),
        ("state", "replaced", ["isid", "cvlan", "name"]),
        ("state", "overridden", ["isid", "cvlan"]),
        ("state", "deleted", ["isid"]),
    ]

    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        required_if=required_if,
        supports_check_mode=True,
    )

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    state = module.params["state"]

    try:
        if state == "gathered":
            result = ensure_gathered(module, connection)
        elif state == "deleted":
            result = ensure_deleted(module, connection)
        else:
            result = ensure_configured(module, connection, state=state)
        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeFabricL2Error as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
