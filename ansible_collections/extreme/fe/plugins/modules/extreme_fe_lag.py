# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine LAGs via HTTPAPI."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

from typing import Any, Dict, List, Optional

DOCUMENTATION = r"""
---
module: extreme_fe_lag
short_description: Manage LAGs on ExtremeNetworks Fabric Engine switches
version_added: "1.3.0"
description:
    - "Create and delete Link Aggregation Groups (LAGs) on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI transport."
    - "Update Fabric Engine specific LAG attributes such as friendly names, load balancing algorithms, and Fabric Engine LACP keys."
    - "Add or remove member ports through the Fabric Engine LAG REST endpoints while propagating device errors back to Ansible."
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - "Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project."
    - "Only Fabric Engine (VOSS) LAG attributes and endpoints are used; Switch Engine (EXOS) parameters are intentionally unsupported."
    - "Fabric Engine does not support patching an existing LAG's aggregation mode; delete and recreate the LAG to modify ``mode``."
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired LAG operation.
            - "``merged`` creates the target LAG when missing and merges the supplied attributes and member ports."
            - "``replaced`` enforces the supplied member list and attributes for the target LAG, removing unstated members."
            - "``overridden`` clears member overrides that are not provided and applies the supplied attribute values (an empty ``member_ports`` list removes all members)."
            - "``deleted`` removes the specified LAG entirely or prunes the provided members when ``member_ports`` or ``remove_member_ports`` is supplied."
            - "``gathered`` returns the current LAG configuration without applying changes."
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    lag_id:
        description:
            - "LAG identifier (Fabric Engine MLT identifier)."
            - "Accepts string or integer values in the Fabric Engine supported range (1-512)."
        type: raw
    name:
        description:
            - "Friendly Fabric Engine name assigned to the LAG."
        type: str
    mode:
        description:
            - "Fabric Engine aggregation mode to use when creating the LAG."
        type: str
        choices: [STATIC, LACP, VLACP]
    lacp_key:
        description:
            - "Fabric Engine aggregation key used when the LAG operates in LACP or VLACP mode."
        type: str
    load_balance_algo:
        description:
            - "Load balancing algorithm applied to the Fabric Engine LAG."
        type: str
        choices: [L2, L3, L3_L4, CUSTOM, PORT]
    member_ports:
        description:
            - "List of member ports that participate in the LAG."
            - "With ``state: merged`` missing members are added while existing members remain unless ``purge_member_ports`` is true."
            - "With ``state: replaced`` or ``state: overridden`` the provided ports become authoritative; unspecified members are removed and an empty list clears all members."
            - "With ``state: deleted`` the provided ports are removed from the LAG without deleting the LAG itself."
        type: list
        elements: str
    add_member_ports:
        description:
            - "Incremental list of member ports to add to the LAG when ``state: merged``."
        type: list
        elements: str
    remove_member_ports:
        description:
            - "Incremental list of member ports to remove from the LAG when ``state: merged`` or ``state: deleted``."
        type: list
        elements: str
    purge_member_ports:
        description:
            - "Remove member ports that are not present in ``member_ports`` (only evaluated when ``state: merged``)."
            - "Requires ``member_ports`` when set to true."
        type: bool
        default: false
    gather_filter:
        description:
            - "Restrict gathered LAG results to these identifiers."
        type: list
        elements: str
"""

EXAMPLES = r"""
- name: Merge configuration for Fabric Engine LAG 10
    hosts: switches
    gather_facts: false
    tasks:
        - name: Create or update LAG 10 with initial members
            local.extreme_fe.extreme_fe_lag:
                state: merged
                lag_id: 10
                name: Uplink-LAG-10
                mode: LACP
                lacp_key: '10'
                member_ports:
                    - '1:1'
                    - '1:2'
                add_member_ports:
                    - '1:3'

- name: Merge LAG 11 and purge unspecified members
    hosts: switches
    gather_facts: false
    tasks:
        - name: Enforce membership for LAG 11 while removing strays
            local.extreme_fe.extreme_fe_lag:
                state: merged
                lag_id: 11
                member_ports:
                    - '1:7'
                    - '1:8'
                purge_member_ports: true

- name: Replace membership for Fabric Engine LAG 10
    hosts: switches
    gather_facts: false
    tasks:
        - name: Enforce the desired member set
            local.extreme_fe.extreme_fe_lag:
                state: replaced
                lag_id: 10
                member_ports:
                    - '1:1'
                    - '1:2'

- name: Override LAG 20 and clear existing members
    hosts: switches
    gather_facts: false
    tasks:
        - name: Remove all members while keeping the LAG definition
            local.extreme_fe.extreme_fe_lag:
                state: overridden
                lag_id: 20
                member_ports: []

- name: Delete Fabric Engine LAG 30
    hosts: switches
    gather_facts: false
    tasks:
        - name: Remove the entire LAG
            local.extreme_fe.extreme_fe_lag:
                state: deleted
                lag_id: 30

- name: Remove specific LAG members without deleting the LAG
    hosts: switches
    gather_facts: false
    tasks:
        - name: Prune members from LAG 40
            local.extreme_fe.extreme_fe_lag:
                state: deleted
                lag_id: 40
                remove_member_ports:
                    - '1:15'
                    - '1:16'

- name: Gather LAG configuration details
    hosts: switches
    gather_facts: false
    tasks:
        - name: Read LAG 10 configuration
            local.extreme_fe.extreme_fe_lag:
                state: gathered
                gather_filter:
                    - '10'
            register: lag_details

        - name: Show gathered LAG data
            ansible.builtin.debug:
                var: lag_details.lags
"""

RETURN = r"""
---
changed:
    description: "Indicates whether any changes were made."
    returned: always
    type: bool
lag:
    description: "Resulting LAG configuration returned by the Fabric Engine REST API."
    returned: when state in [merged, replaced, overridden, deleted] and the LAG exists after execution
    type: dict
lag_removed:
    description: "LAG configuration that was removed when the entire LAG was deleted."
    returned: when state == deleted and the target LAG was removed
    type: dict
member_additions:
    description: "Member ports that were added during execution."
    returned: when state in [merged, replaced, overridden] and member ports were added
    type: list
    elements: str
member_removals:
    description: "Member ports that were removed during execution."
    returned: when state in [merged, replaced, overridden, deleted] and member ports were removed
    type: list
    elements: str
lags:
    description: "List of LAG configuration dictionaries retrieved when ``state: gathered``."
    returned: when state == gathered
    type: list
    elements: dict
"""

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"


ARGUMENT_SPEC: Dict[str, Any] = {
    "state": {
        "type": "str",
        "choices": [STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED, STATE_GATHERED],
        "default": STATE_MERGED,
    },
    "lag_id": {"type": "raw"},
    "name": {"type": "str"},
    "mode": {"type": "str", "choices": ["STATIC", "LACP", "VLACP"]},
    "lacp_key": {"type": "str"},
    "load_balance_algo": {
        "type": "str",
        "choices": ["L2", "L3", "L3_L4", "CUSTOM", "PORT"],
    },
    "member_ports": {"type": "list", "elements": "str"},
    "add_member_ports": {"type": "list", "elements": "str"},
    "remove_member_ports": {"type": "list", "elements": "str"},
    "purge_member_ports": {"type": "bool", "default": False},
    "gather_filter": {"type": "list", "elements": "str"},
}


class FeLagError(Exception):
    """Base exception for Fabric Engine LAG module errors."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _is_not_found_response(payload: Optional[Any]) -> bool:
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


def _normalize_lag_id(value: Any) -> str:
    if value is None:
        raise FeLagError("Parameter 'lag_id' must be provided when state requires a LAG identifier")
    if isinstance(value, bool):
        raise FeLagError("Boolean values are not valid for 'lag_id'")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            raise FeLagError("Parameter 'lag_id' must not be empty")
        return trimmed
    return str(value)


def _unique_port_list(values: Optional[List[str]], *, param_name: str) -> List[str]:
    if not values:
        return []
    unique: List[str] = []
    seen = set()
    for raw in values:
        if not isinstance(raw, str):
            raise FeLagError(
                f"All entries in '{param_name}' must be strings",
                details={"invalid_value": raw},
            )
        port = raw.strip()
        if not port:
            raise FeLagError(f"Port names in '{param_name}' cannot be empty")
        if port not in seen:
            seen.add(port)
            unique.append(port)
    return unique


def _extract_member_ports(lag: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(lag, dict):
        return []
    raw = lag.get("memberPorts")
    if not isinstance(raw, list):
        return []
    members: List[str] = []
    for item in raw:
        if isinstance(item, str):
            members.append(item)
        elif item is not None:
            members.append(str(item))
    return members


def gather_lags(module: AnsibleModule, connection: Connection) -> List[Dict[str, Any]]:
    gather_filter = module.params.get("gather_filter")
    if gather_filter:
        results: List[Dict[str, Any]] = []
        for entry in gather_filter:
            lag_id = _normalize_lag_id(entry)
            config = get_lag_config(connection, lag_id)
            if config is not None:
                results.append(config)
        return results
    data = connection.send_request(None, path="/v0/configuration/lag", method="GET")
    if data is None or _is_not_found_response(data):
        return []
    if isinstance(data, list):
        result: List[Dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                result.append(item)
        return result
    raise FeLagError(
        "Unexpected response when retrieving LAG configuration summary",
        details={"response": data},
    )


def get_lag_config(connection: Connection, lag_id: str) -> Optional[Dict[str, Any]]:
    try:
        data = connection.send_request(
            None,
            path=f"/v0/configuration/lag/{lag_id}",
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
    raise FeLagError(
        "Unexpected response when retrieving LAG configuration",
        details={"response": data},
    )


def create_lag(connection: Connection, payload: Dict[str, Any]) -> None:
    connection.send_request(payload, path="/v0/configuration/lag", method="POST")


def update_lag(connection: Connection, lag_id: str, payload: Dict[str, Any]) -> None:
    if payload:
        connection.send_request(payload, path=f"/v0/configuration/lag/{lag_id}", method="PATCH")


def delete_lag(connection: Connection, lag_id: str) -> None:
    connection.send_request(None, path=f"/v0/configuration/lag/{lag_id}", method="DELETE")


def add_member_ports(connection: Connection, lag_id: str, ports: List[str]) -> None:
    if ports:
        connection.send_request(ports, path=f"/v0/configuration/lag/{lag_id}/memberPorts", method="POST")


def remove_member_ports(connection: Connection, lag_id: str, ports: List[str]) -> None:
    for port in ports:
        connection.send_request(
            None,
            path=f"/v0/configuration/lag/{lag_id}/memberPorts/{port}",
            method="DELETE",
        )


def ensure_configured(module: AnsibleModule, connection: Connection, state: str) -> Dict[str, Any]:
    lag_id = _normalize_lag_id(module.params.get("lag_id"))
    name = module.params.get("name")
    mode = module.params.get("mode")
    lacp_key = module.params.get("lacp_key")
    load_balance_algo = module.params.get("load_balance_algo")
    desired_members_param = module.params.get("member_ports")
    add_members_param = module.params.get("add_member_ports")
    remove_members_param = module.params.get("remove_member_ports")
    purge_members_param = module.params.get("purge_member_ports")

    desired_members: Optional[List[str]]
    add_members: List[str] = []
    remove_members: List[str] = []
    purge_members = False

    if state == STATE_MERGED:
        desired_members = _unique_port_list(desired_members_param, param_name="member_ports") if desired_members_param is not None else None
        add_members = _unique_port_list(add_members_param, param_name="add_member_ports")
        remove_members = _unique_port_list(remove_members_param, param_name="remove_member_ports")
        purge_members = bool(purge_members_param)
        if purge_members and desired_members is None:
            raise FeLagError("'purge_member_ports' requires 'member_ports' when state is 'merged'")
    elif state == STATE_REPLACED:
        if add_members_param:
            raise FeLagError("'add_member_ports' is not supported when state is 'replaced'")
        if remove_members_param:
            raise FeLagError("'remove_member_ports' is not supported when state is 'replaced'")
        if desired_members_param is None:
            raise FeLagError("'member_ports' is required when state is 'replaced'")
        desired_members = _unique_port_list(desired_members_param, param_name="member_ports")
        purge_members = True
    elif state == STATE_OVERRIDDEN:
        if add_members_param:
            raise FeLagError("'add_member_ports' is not supported when state is 'overridden'")
        if remove_members_param:
            raise FeLagError("'remove_member_ports' is not supported when state is 'overridden'")
        if desired_members_param is None:
            desired_members = []
        else:
            desired_members = _unique_port_list(desired_members_param, param_name="member_ports")
        purge_members = True
    else:
        raise FeLagError(f"Unsupported state '{state}' for configuration workflow")

    existing = get_lag_config(connection, lag_id)
    changed = False
    refreshed_required = False
    member_additions: List[str] = []
    member_removals: List[str] = []

    current: Dict[str, Any]
    if existing is None:
        changed = True
        initial_members: List[str] = []
        if desired_members is not None:
            initial_members.extend(desired_members)
        elif add_members:
            initial_members.extend(add_members)
        payload: Dict[str, Any] = {"lagId": lag_id}
        if name is not None:
            payload["name"] = name
        if mode is not None:
            payload["mode"] = mode
        if lacp_key is not None:
            payload["lacpKey"] = lacp_key
        if load_balance_algo is not None:
            payload["loadBalanceAlgo"] = load_balance_algo
        if initial_members:
            payload["memberPorts"] = initial_members
            member_additions.extend(initial_members)
        if module.check_mode:
            current = payload.copy()
            current.setdefault("memberPorts", list(initial_members))
        else:
            create_lag(connection, payload)
            refreshed_required = True
            current = get_lag_config(connection, lag_id) or payload
    else:
        current = existing.copy()
        update_payload: Dict[str, Any] = {}
        if name is not None and name != existing.get("name"):
            update_payload["name"] = name
        if lacp_key is not None and lacp_key != existing.get("lacpKey"):
            update_payload["lacpKey"] = lacp_key
        if load_balance_algo is not None and load_balance_algo != existing.get("loadBalanceAlgo"):
            update_payload["loadBalanceAlgo"] = load_balance_algo
        if mode is not None and mode != existing.get("mode"):
            raise FeLagError(
                "Changing LAG mode on Fabric Engine is not supported via PATCH; delete and recreate the LAG to modify the mode.",
                details={"current_mode": existing.get("mode"), "requested_mode": mode},
            )
        if update_payload:
            changed = True
            if module.check_mode:
                current.update(update_payload)
            else:
                update_lag(connection, lag_id, update_payload)
                refreshed_required = True
                refreshed = get_lag_config(connection, lag_id)
                if refreshed is not None:
                    current = refreshed
                else:
                    current.update(update_payload)

    current_members = _extract_member_ports(current)
    current_member_set = set(current_members)

    ports_to_add: List[str] = []
    if desired_members is not None:
        for port in desired_members:
            if port not in current_member_set:
                ports_to_add.append(port)
                current_member_set.add(port)
    for port in add_members:
        if port not in current_member_set:
            ports_to_add.append(port)
            current_member_set.add(port)

    ports_to_remove: List[str] = []
    if purge_members and desired_members is not None:
        desired_set = set(desired_members)
        for port in current_members:
            if port not in desired_set and port not in ports_to_remove:
                ports_to_remove.append(port)
    for port in remove_members:
        if port in current_members and port not in ports_to_remove:
            ports_to_remove.append(port)

    if ports_to_add or ports_to_remove:
        changed = True

    if ports_to_add:
        member_additions.extend(ports_to_add)
    if ports_to_remove:
        member_removals.extend(ports_to_remove)

    if module.check_mode:
        simulated_members = current_members.copy()
        for port in ports_to_add:
            if port not in simulated_members:
                simulated_members.append(port)
        for port in ports_to_remove:
            if port in simulated_members:
                simulated_members.remove(port)
        current["memberPorts"] = simulated_members
        result: Dict[str, Any] = {"changed": changed, "lag": current}
        if member_additions:
            result["member_additions"] = _unique_port_list(member_additions, param_name="member_additions")
        if member_removals:
            result["member_removals"] = _unique_port_list(member_removals, param_name="member_removals")
        return result

    if ports_to_add:
        add_member_ports(connection, lag_id, ports_to_add)
        refreshed_required = True
    if ports_to_remove:
        remove_member_ports(connection, lag_id, ports_to_remove)
        refreshed_required = True

    if refreshed_required:
        final_lag = get_lag_config(connection, lag_id)
    else:
        final_lag = get_lag_config(connection, lag_id) if changed else current

    result: Dict[str, Any] = {"changed": changed, "lag": final_lag or current}
    if member_additions:
        result["member_additions"] = _unique_port_list(member_additions, param_name="member_additions")
    if member_removals:
        result["member_removals"] = _unique_port_list(member_removals, param_name="member_removals")
    return result


def ensure_deleted(module: AnsibleModule, connection: Connection) -> Dict[str, Any]:
    lag_id = _normalize_lag_id(module.params.get("lag_id"))
    add_members_param = module.params.get("add_member_ports")
    if add_members_param:
        raise FeLagError("'add_member_ports' is not supported when state is 'deleted'")

    members_to_remove: List[str] = []
    member_ports_param = module.params.get("member_ports")
    remove_members_param = module.params.get("remove_member_ports")
    if member_ports_param is not None:
        members_to_remove.extend(_unique_port_list(member_ports_param, param_name="member_ports"))
    if remove_members_param:
        members_to_remove.extend(_unique_port_list(remove_members_param, param_name="remove_member_ports"))
    if members_to_remove:
        members_to_remove = _unique_port_list(members_to_remove, param_name="member_removals")

    existing = get_lag_config(connection, lag_id)
    if existing is None:
        return {"changed": False, "lag": None}

    if not members_to_remove:
        if module.check_mode:
            result: Dict[str, Any] = {
                "changed": True,
                "lag": None,
                "lag_removed": existing,
                "member_removals": _extract_member_ports(existing),
            }
            return result
        delete_lag(connection, lag_id)
        return {
            "changed": True,
            "lag": None,
            "lag_removed": existing,
            "member_removals": _extract_member_ports(existing),
        }

    current_members = _extract_member_ports(existing)
    current_member_set = set(current_members)
    ports_to_remove = [port for port in members_to_remove if port in current_member_set]
    if not ports_to_remove:
        return {"changed": False, "lag": existing}

    if module.check_mode:
        simulated_members = [port for port in current_members if port not in ports_to_remove]
        simulated = existing.copy()
        simulated["memberPorts"] = simulated_members
        return {
            "changed": True,
            "lag": simulated,
            "member_removals": ports_to_remove,
        }

    remove_member_ports(connection, lag_id, ports_to_remove)
    final_lag = get_lag_config(connection, lag_id)
    return {
        "changed": True,
        "lag": final_lag,
        "member_removals": ports_to_remove,
    }


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)
    module.required_if = [
        ["state", STATE_MERGED, ["lag_id"]],
        ["state", STATE_REPLACED, ["lag_id"]],
        ["state", STATE_OVERRIDDEN, ["lag_id"]],
        ["state", STATE_DELETED, ["lag_id"]],
    ]

    if not module._socket_path:
        module.fail_json(msg="HTTPAPI connection is required for this module")

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))
        return

    state = module.params.get("state")

    try:
        if state == STATE_GATHERED:
            lags = gather_lags(module, connection)
            module.exit_json(changed=False, lags=lags)
        if state == STATE_DELETED:
            result = ensure_deleted(module, connection)
            module.exit_json(**result)
        result = ensure_configured(module, connection, state)
        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeLagError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
