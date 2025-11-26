# -*- coding: utf-8 -*-
"""Ansible module to gather ExtremeNetworks Fabric Engine facts via HTTPAPI."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils._text import to_text

from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import quote

import re

DOCUMENTATION = r"""
module: extreme_fe_facts
short_description: Gather facts from ExtremeNetworks Fabric Engine switches
version_added: 1.2.0
description:
- Collect state, hardware, interface, configuration, and neighbor facts from
  ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI plugin.
- Optionally gather structured network resource data for interfaces, VLANs, routing,
  and other subsystems to support idempotent automation plays.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped
  with this project.
- Targets Fabric Engine (VOSS) platforms. Resources not available on Fabric Engine are
  skipped automatically.
options:
  gather_subset:
    description:
    - List of fact subsets to collect. Use ``all`` to gather every supported subset.
      Prefix a subset with ``!`` to exclude it when ``all`` is specified.
    - Supported subsets: ``default``, ``hardware``, ``interfaces``, ``config``, ``neighbors``.
    type: list
    elements: str
    default: [default]
  gather_network_resources:
    description:
    - List of network resource names to collect. Use ``all`` to gather every supported
      resource. Resources that are unavailable on the device are ignored.
    - Supported resources: ``interfaces``, ``l2_interfaces``, ``l3_interfaces``, ``vlans``,
      ``lag_interfaces``, ``vrfs``, ``static_routes``, ``ospfv2``, ``vrrp``, ``lldp``, ``cdp``,
      ``ntp``, ``dns``, ``snmp_server``, ``syslog``, ``anycast_gateway``, ``isid``.
    type: list
    elements: str
requirements:
- ansible.netcommon
"""

EXAMPLES = r"""
- name: Gather default Fabric Engine facts
  hosts: switches
  gather_facts: false
  tasks:
    - name: Collect basic device information
      extreme_fe_facts:
      register: facts

- name: Gather hardware facts only
  hosts: switches
  gather_facts: false
  tasks:
    - name: Collect hardware inventory
      extreme_fe_facts:
        gather_subset:
          - hardware
      register: fe_hw

- name: Gather configuration facts and VLAN/L3 resources
  hosts: switches
  gather_facts: false
  tasks:
    - name: Collect config and resource data
      extreme_fe_facts:
        gather_subset:
          - config
          - neighbors
        gather_network_resources:
          - vlans
          - l3_interfaces
      register: device_data

- name: Gather every supported fact subset and resource
  hosts: switches
  gather_facts: false
  tasks:
    - name: Collect full set of facts
      extreme_fe_facts:
        gather_subset: [all]
        gather_network_resources: [all]
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made. Always ``false``.
  returned: always
  type: bool
ansible_facts:
  description: Structured fact data collected from the device.
  returned: always
  type: dict
  contains:
    extreme_fe_facts:
      description: Fact data grouped by subset name.
      type: dict
    extreme_fe_facts_network_resources:
      description: Network resource data keyed by resource name.
      type: dict
    extreme_fe_facts_gathered_subsets:
      description: List of fact subsets that were gathered.
      type: list
    extreme_fe_facts_gathered_network_resources:
      description: Network resources that were successfully gathered.
      type: list
"""


ARGUMENT_SPEC = {
    "gather_subset": {"type": "list", "elements": "str", "default": ["default"]},
    "gather_network_resources": {"type": "list", "elements": "str"},
}

VALID_SUBSETS: Set[str] = {"default", "hardware", "interfaces", "config", "neighbors"}
VALID_RESOURCES: Set[str] = {
    "interfaces",
    "l2_interfaces",
    "l3_interfaces",
    "vlans",
    "lag_interfaces",
    "vrfs",
    "static_routes",
    "ospfv2",
    "vrrp",
    "lldp",
    "cdp",
    "ntp",
    "dns",
    "snmp_server",
    "syslog",
    "anycast_gateway",
    "isid",
}

PORT_NAME_KEYS: Set[str] = {
    "port",
    "portid",
    "portname",
    "ifname",
    "interface",
    "interfacename",
    "lagportname",
    "memberport",
    "untaggedport",
}
PORT_LIST_KEYS: Set[str] = {
    "ports",
    "memberports",
    "taggedports",
    "untaggedports",
    "allowedports",
}

_VRF_NAME_CACHE: Optional[Set[str]] = None


class FeFactsError(Exception):
    """Base exception for the extreme_fe_facts module."""

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
    if isinstance(message, str):
        lowered = message.lower()
        if "not found" in lowered or "does not exist" in lowered:
            return True
    return False


def _normalize_subset_requests(values: Optional[Iterable[str]]) -> Set[str]:
    if not values:
        return {"default"}
    includes: Set[str] = set()
    excludes: Set[str] = set()
    saw_all = False
    for raw in values:
        if raw is None:
            continue
        item = str(raw).strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered == "all":
            saw_all = True
            includes.update(VALID_SUBSETS)
            continue
        if lowered.startswith("!"):
            name = lowered[1:]
            if name not in VALID_SUBSETS:
                raise FeFactsError(f"Unsupported subset '{item}'")
            excludes.add(name)
            continue
        if lowered not in VALID_SUBSETS:
            raise FeFactsError(f"Unsupported subset '{item}'")
        includes.add(lowered)
    if not includes and not saw_all:
        includes.add("default")
    result = includes - excludes
    if not result and saw_all:
        # Could happen if all subsets were excluded; return empty set.
        return set()
    return result


def _normalize_resource_requests(values: Optional[Iterable[str]]) -> Set[str]:
    if not values:
        return set()
    includes: Set[str] = set()
    excludes: Set[str] = set()
    saw_all = False
    for raw in values:
        if raw is None:
            continue
        item = str(raw).strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered == "all":
            saw_all = True
            includes.update(VALID_RESOURCES)
            continue
        if lowered.startswith("!"):
            name = lowered[1:]
            if name not in VALID_RESOURCES:
                raise FeFactsError(f"Unsupported network resource '{item}'")
            excludes.add(name)
            continue
        if lowered not in VALID_RESOURCES:
            raise FeFactsError(f"Unsupported network resource '{item}'")
        includes.add(lowered)
    if saw_all:
        includes.update(VALID_RESOURCES)
    result = includes - excludes
    return result


def _http_get(connection: Connection, path: str) -> Optional[Any]:
    try:
        data = connection.send_request(None, path=path, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise FeFactsError(
            f"Failed to retrieve data from {path}", details={"error": to_text(exc)}
        )
    if data is None:
        return None
    if _is_not_found_response(data):
        return None
    return data


def _normalize_port_name(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    if not trimmed:
        return trimmed
    prefix = ""
    remainder = trimmed
    if ":" in trimmed:
        maybe_prefix, maybe_rest = trimmed.split(":", 1)
        if maybe_prefix.isalpha() and maybe_rest:
            prefix = f"{maybe_prefix.upper()}:" if maybe_prefix else ""
            remainder = maybe_rest
    parts = [part for part in re.split(r"[:/\\]+", remainder) if part]
    if not parts:
        normalized = remainder
    else:
        normalized = ":".join(part.strip() for part in parts)
    if prefix:
        return prefix + normalized
    return normalized


def _normalize_ports(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key, value in list(payload.items()):
            sanitized = key.replace("-", "").replace("_", "").lower()
            if sanitized in PORT_NAME_KEYS and isinstance(value, str):
                payload[key] = _normalize_port_name(value)
            elif sanitized in PORT_LIST_KEYS and isinstance(value, list):
                normalized_list: List[Any] = []
                for item in value:
                    if isinstance(item, str):
                        normalized_list.append(_normalize_port_name(item))
                    else:
                        normalized_list.append(_normalize_ports(item))
                payload[key] = normalized_list
            else:
                payload[key] = _normalize_ports(value)
        return payload
    if isinstance(payload, list):
        return [_normalize_ports(item) for item in payload]
    return payload


def _normalize_payload(payload: Optional[Any]) -> Optional[Any]:
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return _normalize_ports(payload)
    return payload


def _merge_dicts(**kwargs: Optional[Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is not None:
            data[key] = value
    return data


def _get_vrf_names(connection: Connection) -> Set[str]:
    global _VRF_NAME_CACHE
    if _VRF_NAME_CACHE is not None:
        return set(_VRF_NAME_CACHE)
    data = _http_get(connection, "/v0/configuration/vrf")
    names: Set[str] = set()
    if isinstance(data, dict):
        for value in data.values():
            names.update(_extract_vrf_names(value))
    elif isinstance(data, list):
        names.update(_extract_vrf_names(data))
    if not names:
        names.add("GlobalRouter")
    _VRF_NAME_CACHE = names
    return set(names)


def _extract_vrf_names(payload: Any) -> Set[str]:
    names: Set[str] = set()
    if isinstance(payload, dict):
        candidate = (
            payload.get("vrName")
            or payload.get("vr")
            or payload.get("vr_name")
            or payload.get("name")
        )
        if candidate:
            names.add(str(candidate))
        for value in payload.values():
            names.update(_extract_vrf_names(value))
    elif isinstance(payload, list):
        for item in payload:
            names.update(_extract_vrf_names(item))
    elif isinstance(payload, str):
        if payload:
            names.add(payload)
    return names


def gather_default_subset(connection: Connection) -> Dict[str, Any]:
    system = _normalize_payload(_http_get(connection, "/v0/state/system"))
    services = _normalize_payload(_http_get(connection, "/v0/state/system-services"))
    reboot = _normalize_payload(_http_get(connection, "/v0/state/system/reboot"))
    return _merge_dicts(system=system, system_services=services, reboot=reboot)


def gather_hardware_subset(connection: Connection) -> Dict[str, Any]:
    fans = _normalize_payload(_http_get(connection, "/v0/state/system/fans"))
    power = _normalize_payload(_http_get(connection, "/v0/state/system/power-supplies"))
    poe = _normalize_payload(_http_get(connection, "/v0/state/poe-power/ports"))
    return _merge_dicts(fans=fans, power_supplies=power, poe=poe)


def gather_interfaces_subset(connection: Connection) -> Dict[str, Any]:
    ports = _normalize_payload(
        _http_get(connection, "/v1/state/ports") or _http_get(connection, "/v0/state/ports")
    )
    capabilities = _normalize_payload(
        _http_get(connection, "/v0/state/capabilities/system/ports")
    )
    return _merge_dicts(ports=ports, port_capabilities=capabilities)


def gather_config_subset(connection: Connection) -> Dict[str, Any]:
    services = _normalize_payload(_http_get(connection, "/v0/configuration/system-services"))
    mgmt = _normalize_payload(
        _http_get(connection, "/v1/configuration/mgmt-interface")
        or _http_get(connection, "/v0/configuration/mgmt-interface")
    )
    images = _normalize_payload(_http_get(connection, "/v0/configuration/system/images"))
    isids = _gather_isid_data(connection)
    return _merge_dicts(
        system_services=services,
        mgmt_interface=mgmt,
        images=images,
        isids=isids,
    )


def gather_neighbors_subset(connection: Connection) -> Dict[str, Any]:
    lldp = _normalize_payload(_http_get(connection, "/v0/state/lldp"))
    cdp = _normalize_payload(_http_get(connection, "/v0/state/cdp"))
    fabric_attach = _normalize_payload(_http_get(connection, "/v0/state/fabric-attach"))
    return _merge_dicts(lldp=lldp, cdp=cdp, fabric_attach=fabric_attach)


SUBSET_HANDLERS = {
    "default": gather_default_subset,
    "hardware": gather_hardware_subset,
    "interfaces": gather_interfaces_subset,
    "config": gather_config_subset,
    "neighbors": gather_neighbors_subset,
}


def gather_interfaces_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/ports"))


def gather_l2_interfaces_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/vlan/ports"))


def gather_l3_interfaces_resource(connection: Connection) -> Dict[str, Any]:
    payload = _http_get(connection, "/v0/configuration/vlan")
    if payload is None:
        return {}

    normalized = _normalize_payload(payload)
    entries: List[Dict[str, Any]]
    if isinstance(normalized, list):
        entries = [item for item in normalized if isinstance(item, dict)]
    elif isinstance(normalized, dict):
        entries = [normalized]
    else:
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    for item in entries:
        vrf = str(
            item.get("vrName")
            or item.get("vr")
            or item.get("vr_name")
            or item.get("vrf")
            or "GlobalRouter"
        )
        vlan_id = item.get("id") or item.get("vlanId") or item.get("vlan_id")
        key = str(vlan_id) if vlan_id is not None else str(item.get("name") or "unknown")
        result.setdefault(vrf, {})[key] = item

    return result


def gather_vlans_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/vlan"))


def gather_lag_interfaces_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/lag"))


def gather_vrfs_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/vrf"))


def gather_static_routes_resource(connection: Connection) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for vrf in sorted(_get_vrf_names(connection)):
        path = f"/v0/configuration/vrf/{quote(vrf, safe='')}/route"
        result[vrf] = _normalize_payload(_http_get(connection, path))
    return result


def gather_ospfv2_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/ospf"))


def gather_vrrp_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/vrrp"))


def gather_lldp_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/lldp"))


def gather_cdp_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/cdp"))


def gather_ntp_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/ntp"))


def gather_dns_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/dns"))


def gather_snmp_resource(connection: Connection) -> Any:
    payload = _http_get(connection, "/v1/configuration/snmp")
    if payload is None:
        payload = _http_get(connection, "/v0/configuration/snmp")
    return _normalize_payload(payload)


def gather_syslog_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/syslog"))


def gather_anycast_gateway_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/anycast-gateway"))


def gather_isid_resource(connection: Connection) -> Any:
    return _gather_isid_data(connection)


RESOURCE_HANDLERS = {
    "interfaces": gather_interfaces_resource,
    "l2_interfaces": gather_l2_interfaces_resource,
    "l3_interfaces": gather_l3_interfaces_resource,
    "vlans": gather_vlans_resource,
    "lag_interfaces": gather_lag_interfaces_resource,
    "vrfs": gather_vrfs_resource,
    "static_routes": gather_static_routes_resource,
    "ospfv2": gather_ospfv2_resource,
    "vrrp": gather_vrrp_resource,
    "lldp": gather_lldp_resource,
    "cdp": gather_cdp_resource,
    "ntp": gather_ntp_resource,
    "dns": gather_dns_resource,
    "snmp_server": gather_snmp_resource,
    "syslog": gather_syslog_resource,
    "anycast_gateway": gather_anycast_gateway_resource,
    "isid": gather_isid_resource,
}


def _gather_isid_data(connection: Connection) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    all_isids = _normalize_payload(_http_get(connection, "/v0/configuration/spbm/l2/isid"))
    if all_isids is not None:
        result["list"] = all_isids

    cvlan = _normalize_payload(_http_get(connection, "/v0/configuration/spbm/l2/isid/cvlan"))
    if cvlan is not None:
        result["cvlan"] = cvlan

    suni = _normalize_payload(_http_get(connection, "/v0/configuration/spbm/l2/isid/suni"))
    if suni is not None:
        result["suni"] = suni

    tuni = _normalize_payload(_http_get(connection, "/v0/configuration/spbm/l2/isid/tuni"))
    if tuni is not None:
        result["tuni"] = tuni

    return result


def main() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    gather_subset_param = module.params.get("gather_subset")
    gather_resources_param = module.params.get("gather_network_resources")

    try:
        subsets = _normalize_subset_requests(gather_subset_param)
        resources = _normalize_resource_requests(gather_resources_param)

        connection = Connection(module._socket_path)

        subset_results: Dict[str, Any] = {}
        for subset in sorted(subsets):
            handler = SUBSET_HANDLERS.get(subset)
            if not handler:
                continue
            data = handler(connection)
            subset_results[subset] = data if data is not None else {}

        resource_results: Dict[str, Any] = {}
        for resource in sorted(resources):
            handler = RESOURCE_HANDLERS.get(resource)
            if not handler:
                continue
            data = handler(connection)
            resource_results[resource] = data if data is not None else {}

        ansible_facts = {
            "extreme_fe_facts": subset_results,
            "extreme_fe_facts_network_resources": resource_results,
            "extreme_fe_facts_gathered_subsets": sorted(subsets),
            "extreme_fe_facts_gathered_network_resources": sorted(resources),
        }

        module.exit_json(changed=False, ansible_facts=ansible_facts)

    except FeFactsError as exc:
        module.fail_json(**exc.to_fail_kwargs())
    except ConnectionError as exc:
        module.fail_json(msg=f"Unable to communicate with device: {to_text(exc)}")
    except Exception as exc:
        module.fail_json(msg=f"Unexpected error: {to_text(exc)}")


if __name__ == "__main__":
    main()
