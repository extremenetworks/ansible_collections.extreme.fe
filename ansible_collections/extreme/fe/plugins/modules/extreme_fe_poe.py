# -*- coding: utf-8 -*-
"""Ansible module to manage PoE settings on ExtremeNetworks Fabric Engine switches."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote

DOCUMENTATION = r"""
---
module: extreme_fe_poe
short_description: Manage PoE settings on ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
  - Retrieve and configure Power over Ethernet (PoE) settings for copper ports on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI plugin.
  - Supports the standard Ansible network resource states to merge, replace, override, delete, or gather PoE configuration across PoE-capable ports.
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
  - Applicable only to Fabric Engine (VOSS) devices. Switch Engine (EXOS) attributes are intentionally excluded.
requirements:
  - ansible.netcommon
options:
  config:
    description:
      - Structured PoE definitions to manage.
      - Required when C(state) is C(merged), C(replaced), or C(deleted).
      - "With C(state=overridden) an empty list resets all PoE configuration for every discovered PoE-capable port."
    type: list
    elements: dict
    suboptions:
      port:
        description:
          - Identifier of the PoE-capable port (for example C(1:5)).
        type: str
        required: true
      enable:
        description:
          - Enable (true) or disable (false) PoE power on the port.
        type: bool
      power_limit:
        description:
          - Desired PoE power limit per port in milliwatts. Fabric Engine supports 3000-98000 inclusive.
        type: int
      priority:
        description:
          - Power management priority for the port.
        type: str
        choices: [LOW, HIGH, CRITICAL]
      perpetual_poe:
        description:
          - Enable or disable the Perpetual PoE feature.
        type: bool
      fast_poe:
        description:
          - Enable or disable Fast PoE startup.
        type: bool
  state:
    description:
      - Desired module operation.
      - C(merged) applies the supplied attributes incrementally to the listed ports without removing unspecified values.
      - C(replaced) enforces the supplied attributes on the listed ports while clearing unspecified values.
      - C(overridden) treats the supplied configuration as authoritative for every PoE-capable port, deleting configuration from ports that are not listed.
      - "C(deleted) removes PoE configuration from the listed ports (use C(state=overridden) with an empty C(config) list to reset all ports)."
      - C(gathered) returns current configuration and live PoE state information without applying changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
author:
  - ExtremeNetworks Networking Automation Team
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
# ## PoE power limits depend on the switch hardware and port classification:
# ## Classification Types and Max Power:
# #   - AF, AF_HIGH, PRE_AT: Max 15.4W (15400 mW)
# #   - AT, PRE_BT (PoE+):   Max 30W (30000 mW)
# #   - BT_TYPE3 (PoE++):    Max 60W (60000 mW)
# #   - BT_TYPE4 (PoE++):    Max 90W (90000 mW)
#
# ## The power_limit value must be within the range supported by your hardware.
# ## If you get "This PoE power limit is not available on this device", reduce
# ## the power_limit to match your port's maximum capability.
#
# ## Range for VOSS: 3000-98000 mW (3W to 98W)
#
# ## Verify Configuration
# # show poe-main-status
# # show poe-port-status <port>

# -------------------------------------------------------------------------
# Task 1: Merge PoE configuration on a port
# Description:
#   - Enable PoE on a port and set custom power limits
#   - 'merged' state is non-destructive (adds/modifies without removing)
# Note: power_limit is set to 30000 mW (30W) for PoE+ compatibility.
#       Adjust based on your hardware capability.
# -------------------------------------------------------------------------
# - name: "Task 1: Merge PoE attributes on a single port"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Ensure PoE enabled with a custom power limit
  extreme.fe.extreme_fe_poe:
    state: merged
    config:
      - port: "1:10"
        enable: true
        power_limit: 30000
        priority: HIGH

# -------------------------------------------------------------------------
# Task 2: Replace PoE configuration on multiple ports
# Description:
#   - Enforce specific PoE settings using 'replaced' state
#   - All PoE attributes for specified ports will match exactly
# -------------------------------------------------------------------------
# - name: "Task 2: Replace PoE configuration on multiple ports"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce desired attributes on selected ports
  extreme.fe.extreme_fe_poe:
    state: replaced
    config:
      - port: "1:5"
        enable: true
        fast_poe: true
      - port: "1:6"
        enable: false

# -------------------------------------------------------------------------
# Task 3: Override PoE configuration globally
# Description:
#   - 'overridden' state resets ALL PoE ports to defaults except those
#     explicitly configured
#
# !! WARNING !!
#   This will reset ALL PoE ports on the switch to their defaults!
#   Only ports explicitly listed in config will retain custom settings.
#   This may cause power interruption to connected PoE devices.
#   Use with caution in production environments.
#
# Note: power_limit is set to 15400 mW (15.4W) for basic PoE compatibility.
# -------------------------------------------------------------------------
# - name: "Task 3: Override PoE configuration for all PoE-capable ports"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Reset every PoE port to defaults except 1:10
  extreme.fe.extreme_fe_poe:
    state: overridden
    config:
      - port: "1:10"
        enable: true
        power_limit: 15400

# -------------------------------------------------------------------------
# Task 4: Delete (reset) PoE configuration on specific ports
# Description:
#   - Reset PoE settings to defaults on specific ports
#   - Unlike 'overridden', this only affects the specified ports
# -------------------------------------------------------------------------
# - name: "Task 4: Delete PoE configuration on specific ports"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Reset PoE settings to defaults on ports 1:5 and 1:6
  extreme.fe.extreme_fe_poe:
    state: deleted
    config:
      - port: "1:5"
      - port: "1:6"

# -------------------------------------------------------------------------
# Task 5: Gather PoE configuration and status
# Description:
#   - Retrieve current PoE configuration and runtime status
#   - Useful for monitoring power consumption and device status
# -------------------------------------------------------------------------
# - name: "Task 5: Gather PoE information for specific ports"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect PoE runtime details
  extreme.fe.extreme_fe_poe:
    state: gathered
    config:
      - port: "1:5"
      - port: "1:6"
      - port: "1:10"
  register: poe_info

- name: Display PoE status (clean format)
  ansible.builtin.debug:
    msg: "{{ poe_info.ports | to_nice_yaml }}"
"""

RETURN = r"""
---
changed:
  description: Indicates whether any configuration changes were made.
  returned: always
  type: bool
ports:
  description: Details for each processed port, including requested configuration, current settings, runtime state data, and detected differences.
  returned: always
  type: list
  elements: dict
submitted:
  description: Mapping of port names to the operations that were submitted when changes were required (empty when no change was needed).
  returned: when state != gathered
  type: dict
  sample:
    "1:10":
      operation: merged
      payload:
        enable: true
        powerLimit: 42000
      deleted: false
"""

ARGUMENT_SPEC = {
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "port": {"type": "str", "required": True},
            "enable": {"type": "bool"},
            "power_limit": {"type": "int"},
            "priority": {"type": "str", "choices": ["LOW", "HIGH", "CRITICAL"]},
            "perpetual_poe": {"type": "bool"},
            "fast_poe": {"type": "bool"},
        },
    },
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}

PORT_CAPABILITIES_PATH = "/v0/state/capabilities/system/ports"
PORT_CONFIG_BASE_PATH = "/v0/configuration/poe-power/ports"
PORT_STATE_BASE_PATH = "/v0/state/poe-power/ports"
SETTABLE_FIELDS = {
    "enable": "enable",
    "power_limit": "powerLimit",
    "priority": "priority",
    "perpetual_poe": "perpetualPoe",
    "fast_poe": "fastPoe",
}
POWER_LIMIT_RANGE = (3000, 98000)

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

REQUIRES_CONFIG: Set[str] = {STATE_MERGED, STATE_REPLACED, STATE_DELETED}


class FePoeError(Exception):
    """Raised for module validation issues."""

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


def _extract_error(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    message = (
        payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    )
    if code and isinstance(code, int) and code >= 400:
        return {
            "code": code,
            "message": message or "Device reported an error",
            "payload": payload,
        }
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported errors",
            "payload": payload,
            "errors": errors,
        }
    return None


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    payload: Optional[Any] = None,
    expect_content: bool = True,
) -> Any:
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
        )

    if response in (None, ""):
        return None if not expect_content else {}

    if isinstance(response, bytes):
        response = to_text(response)

    if isinstance(response, dict):
        error = _extract_error(response)
        if error:
            module.fail_json(msg=error.get("message"), details=error)

    return response


def _fetch_port_capabilities(
    module: AnsibleModule, connection: Connection
) -> Dict[str, Dict[str, Any]]:
    data = (
        _call_api(module, connection, method="GET", path=PORT_CAPABILITIES_PATH) or []
    )
    if not isinstance(data, list):
        raise FePoeError("Unexpected capabilities response", details={"payload": data})

    result: Dict[str, Dict[str, Any]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        port = entry.get("port")
        if isinstance(port, str):
            result[port] = entry
    return result


def _poe_capable(capability: Dict[str, Any]) -> bool:
    caps = capability.get("capabilities")
    if isinstance(caps, dict):
        if caps.get("poe"):
            return True
        if caps.get("poeMaxPower") is not None:
            return True
        if caps.get("poeMaxClassification") is not None:
            return True
    return False


def _normalize_config(
    state: str,
    raw_config: Optional[Iterable[Any]],
    available_ports: Set[str],
) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    order: List[str] = []
    config_by_port: Dict[str, Dict[str, Any]] = {}
    seen: Set[str] = set()

    entries = list(raw_config or [])
    if state in REQUIRES_CONFIG and not entries:
        raise FePoeError(
            "config is required when state in {0}".format(
                ", ".join(sorted(REQUIRES_CONFIG))
            )
        )

    for item in entries:
        if not isinstance(item, dict):
            raise FePoeError("Each config entry must be a dictionary of PoE attributes")

        port_value = item.get("port")
        port = str(port_value).strip() if port_value is not None else ""
        if not port:
            raise FePoeError("Each config entry must include a port identifier")
        if port in seen:
            raise FePoeError("Duplicate port entry detected", details={"port": port})
        if port not in available_ports:
            raise FePoeError("Port is not PoE-capable", details={"port": port})

        payload: Dict[str, Any] = {}
        requested: Dict[str, Any] = {}

        for param, field in SETTABLE_FIELDS.items():
            if param not in item:
                continue
            value = item.get(param)
            if value is None:
                continue
            if param == "power_limit":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise FePoeError(
                        "power_limit must be an integer",
                        details={"port": port, "received": value},
                    )
                min_limit, max_limit = POWER_LIMIT_RANGE
                if not (min_limit <= value <= max_limit):
                    raise FePoeError(
                        "power_limit must be between {0} and {1} mW".format(
                            min_limit, max_limit
                        ),
                        details={"port": port, "received": value},
                    )
            payload[field] = value
            requested[param] = value

        if state in {STATE_MERGED, STATE_REPLACED} and not payload:
            raise FePoeError(
                "At least one PoE attribute must be supplied per port when state in merged or replaced",
                details={"port": port},
            )

        if state == STATE_DELETED and payload:
            raise FePoeError(
                "config entries must not specify PoE attributes when state=deleted",
                details={"port": port},
            )

        order.append(port)
        seen.add(port)
        config_by_port[port] = {"payload": payload, "requested": requested}

    return order, config_by_port


def _port_path(port: str) -> str:
    return f"{PORT_CONFIG_BASE_PATH}/{quote(port, safe='')}"


def _port_state_path(port: str) -> str:
    return f"{PORT_STATE_BASE_PATH}/{quote(port, safe='')}"


def _fetch_port_settings(
    module: AnsibleModule, connection: Connection, port: str
) -> Dict[str, Any]:
    response = _call_api(module, connection, method="GET", path=_port_path(port))
    if isinstance(response, dict):
        return response
    raise FePoeError(
        "Unexpected port settings response", details={"port": port, "payload": response}
    )


def _fetch_port_state(
    module: AnsibleModule, connection: Connection, port: str
) -> Optional[Dict[str, Any]]:
    response = _call_api(module, connection, method="GET", path=_port_state_path(port))
    if response in (None, ""):
        return None
    if isinstance(response, dict):
        return response
    if isinstance(response, list) and response:
        first = response[0]
        if isinstance(first, dict):
            return first
    return None


def _default_payload(capability: Dict[str, Any]) -> Dict[str, Any]:
    caps = capability.get("capabilities") if isinstance(capability, dict) else {}
    power_limit = caps.get("poeMaxPower") if isinstance(caps, dict) else None
    if isinstance(power_limit, (int, float)):
        try:
            power_limit = int(power_limit)
        except (TypeError, ValueError):
            power_limit = None
    if power_limit is None:
        power_limit = POWER_LIMIT_RANGE[1]
    return {
        "enable": True,
        "powerLimit": power_limit,
        "priority": "LOW",
        "perpetualPoe": False,
        "fastPoe": False,
    }


def _port_snapshot(
    module: AnsibleModule,
    connection: Connection,
    port: str,
    capability: Dict[str, Any],
) -> Dict[str, Any]:
    current_settings = _fetch_port_settings(module, connection, port)
    port_result: Dict[str, Any] = {
        "port": port,
        "capability": capability,
        "current": current_settings,
    }
    runtime_state = _fetch_port_state(module, connection, port)
    if runtime_state is not None:
        port_result["state"] = runtime_state
    return port_result


def main() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    state = module.params["state"]
    raw_config = module.params.get("config")

    connection = Connection(module._socket_path)

    try:
        capabilities = _fetch_port_capabilities(module, connection)
    except FePoeError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    poe_capabilities = {
        port: info for port, info in capabilities.items() if _poe_capable(info)
    }
    if not poe_capabilities:
        if state == STATE_GATHERED:
            module.exit_json(
                changed=False,
                ports=[],
                msg="Device does not have PoE-capable ports. No PoE data to gather.",
            )
        module.fail_json(
            msg="Device does not report any PoE-capable ports via capabilities endpoint"
        )

    try:
        order, config_by_port = _normalize_config(
            state, raw_config, set(poe_capabilities)
        )
    except FePoeError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    results: List[Dict[str, Any]] = []
    submitted: Dict[str, Dict[str, Any]] = {}
    changed = False

    if state == STATE_GATHERED:
        target_ports = order if order else sorted(poe_capabilities)
        for port in target_ports:
            capability = poe_capabilities[port]
            results.append(_port_snapshot(module, connection, port, capability))
        module.exit_json(changed=False, ports=results)

    if state == STATE_DELETED:
        for port in order:
            capability = poe_capabilities[port]
            current = _fetch_port_settings(module, connection, port)
            port_result = {
                "port": port,
                "capability": capability,
                "current": current,
            }
            runtime_state = _fetch_port_state(module, connection, port)
            if runtime_state is not None:
                port_result["state"] = runtime_state

            target_payload = _default_payload(capability)
            differences = {}
            patch_payload: Dict[str, Any] = {}
            for field, target in target_payload.items():
                existing = current.get(field)
                if existing != target:
                    differences[field] = {"before": existing, "after": target}
                    patch_payload[field] = target

            if differences:
                changed = True
                port_result["differences"] = differences
                submitted[port] = {
                    "operation": state,
                    "payload": patch_payload,
                    "deleted": True,
                }
                if not module.check_mode:
                    _call_api(
                        module,
                        connection,
                        method="PATCH",
                        path=_port_path(port),
                        payload=patch_payload,
                        expect_content=False,
                    )
                    current = _fetch_port_settings(module, connection, port)
                    port_result["current"] = current
            else:
                port_result["differences"] = {}

            results.append(port_result)

        module.exit_json(changed=changed, ports=results, submitted=submitted)

    managed_ports = order
    for port in managed_ports:
        capability = poe_capabilities[port]
        current = _fetch_port_settings(module, connection, port)
        port_result: Dict[str, Any] = {
            "port": port,
            "capability": capability,
            "current": current,
            "requested": config_by_port[port].get("requested", {}),
        }
        runtime_state = _fetch_port_state(module, connection, port)
        if runtime_state is not None:
            port_result["state"] = runtime_state

        desired_payload = config_by_port[port]["payload"]

        if state == STATE_MERGED:
            differences: Dict[str, Dict[str, Any]] = {}
            patch_payload: Dict[str, Any] = {}
            for field, desired in desired_payload.items():
                existing = current.get(field)
                if existing != desired:
                    differences[field] = {"before": existing, "after": desired}
                    patch_payload[field] = desired

            if differences:
                changed = True
                port_result["differences"] = differences
                submitted[port] = {
                    "operation": state,
                    "payload": patch_payload,
                    "deleted": False,
                }
                if not module.check_mode:
                    _call_api(
                        module,
                        connection,
                        method="PATCH",
                        path=_port_path(port),
                        payload=patch_payload,
                        expect_content=False,
                    )
                    current = _fetch_port_settings(module, connection, port)
                    port_result["current"] = current
            else:
                port_result["differences"] = {}

            results.append(port_result)
            continue

        target_payload = _default_payload(capability)
        target_payload.update(desired_payload)

        differences = {}
        patch_payload: Dict[str, Any] = {}
        for field, target in target_payload.items():
            existing = current.get(field)
            if existing != target:
                differences[field] = {"before": existing, "after": target}
                patch_payload[field] = target

        if differences:
            changed = True
            port_result["differences"] = differences
            submitted[port] = {
                "operation": state,
                "payload": patch_payload,
                "deleted": False,
            }
            if not module.check_mode:
                _call_api(
                    module,
                    connection,
                    method="PATCH",
                    path=_port_path(port),
                    payload=patch_payload,
                    expect_content=False,
                )
                current = _fetch_port_settings(module, connection, port)
                port_result["current"] = current
        else:
            port_result["differences"] = {}

        results.append(port_result)

    if state == STATE_OVERRIDDEN:
        managed_set = set(managed_ports)
        leftover_ports = sorted(
            port for port in poe_capabilities if port not in managed_set
        )
        for port in leftover_ports:
            capability = poe_capabilities[port]
            current = _fetch_port_settings(module, connection, port)
            port_result = {
                "port": port,
                "capability": capability,
                "current": current,
            }
            runtime_state = _fetch_port_state(module, connection, port)
            if runtime_state is not None:
                port_result["state"] = runtime_state

            target_payload = _default_payload(capability)
            differences = {}
            patch_payload: Dict[str, Any] = {}
            for field, target in target_payload.items():
                existing = current.get(field)
                if existing != target:
                    differences[field] = {"before": existing, "after": target}
                    patch_payload[field] = target

            if differences:
                changed = True
                port_result["differences"] = differences
                submitted[port] = {
                    "operation": state,
                    "payload": patch_payload,
                    "deleted": True,
                }
                if not module.check_mode:
                    _call_api(
                        module,
                        connection,
                        method="PATCH",
                        path=_port_path(port),
                        payload=patch_payload,
                        expect_content=False,
                    )
                    current = _fetch_port_settings(module, connection, port)
                    port_result["current"] = current
            else:
                port_result["differences"] = {}

            results.append(port_result)

    module.exit_json(changed=changed, ports=results, submitted=submitted)


if __name__ == "__main__":
    main()
