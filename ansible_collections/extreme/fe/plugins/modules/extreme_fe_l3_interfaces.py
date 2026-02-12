# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine Layer 3 interfaces."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

from ipaddress import IPv4Interface, IPv6Interface, ip_network
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

DOCUMENTATION = r"""
module: extreme_fe_l3_interfaces
short_description: Manage Layer 3 interfaces on ExtremeNetworks Fabric Engine switches
version_added: 1.2.0
description:
- Configure IPv4 and IPv6 addressing on VLAN and loopback interfaces of ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI transport.
- Supports declarative merge, replace, override, delete, and gather operations modeled after the Ansible ``ios_l3_interfaces`` and ``junos_l3_interfaces`` modules.
- Updates rely on the Fabric Engine REST resources ``/v0/configuration/vlan/{vlan_id}/address`` and ``/v0/configuration/loopback/{id}`` as defined in ``nos-openapi-09-15-2025.yaml``.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
- VLANs and loopbacks must exist prior to invoking this module; creation is out of scope.
requirements:
- ansible.netcommon
options:
  config:
    description:
    - List of Layer 3 interface definitions to manage.
    - When omitted with ``state: gathered``, the module returns all VLAN and loopback interfaces that have IP addressing configured.
    type: list
    elements: dict
    suboptions:
      name:
        description:
        - Interface identifier for readability, such as ``VLAN 20`` or ``Loopback 10``.
        - When ``type`` is not supplied, the module attempts to infer the interface type and identifier from ``name``.
        type: str
      type:
        description:
        - Interface type to operate on.
        type: str
        choices: [vlan, loopback]
      vlan_id:
        description:
        - VLAN identifier for routed VLAN interfaces (SVIs).
        type: int
      loopback_id:
        description:
        - Loopback identifier for Fabric Engine loopback interfaces.
        type: int
      vrf:
        description:
        - Optional VRF name for documentation purposes only; changes are not pushed through this module.
        type: str
      ipv4:
        description:
        - IPv4 addresses to manage on the interface.
        - Accepts CIDR strings (for example ``10.0.1.1/24``) or dictionaries with ``address`` and ``prefix``/``mask``/``mask_length`` keys.
        type: list
        elements: raw
      ipv6:
        description:
        - IPv6 addresses to manage on the interface.
        - Accepts CIDR strings or dictionaries with ``address`` and ``prefix``/``mask_length`` keys.
        type: list
        elements: raw
  state:
    description:
    - Desired module operation.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
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
## Create VLANs (if not already existing)
# vlan create 20 type port-mstprstp 0
# vlan create 200 type port-mstprstp 0
#
## Give VLANs descriptive names
# vlan name 20 "VLAN-20"
# vlan name 200 "VLAN-200"
#
## Create loopback interface 5
# interface loopback 5
#   ip address 1.1.1.5 255.255.255.255
# exit
#
## Enable IP routing (if not already enabled)
# ip routing
#
## Make VLANs IP interfaces (add dummy IPs to enable L3)
# interface vlan 20
#   ip address 10.0.20.1 255.255.255.0
# exit
# interface vlan 200
#   ip address 10.0.200.1 255.255.255.0
# exit
#
## Verify Configuration
# show ip interface
# show ipv6 interface
# show interfaces loopback

# -------------------------------------------------------------------------
# Task 1: Merge IPv4 address on VLAN interface
# Description:
#   - This example demonstrates how to add an IPv4 address to a VLAN
#     interface using the 'merged' state. Existing addresses are preserved.
# -------------------------------------------------------------------------
# - name: "Task 1: Merge IPv4 address on VLAN 20"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Ensure VLAN 20 has 10.0.1.101/24 configured
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - vlan_id: 20
        name: VLAN 20
        ipv4:
          - address: 10.0.1.101
            prefix: 24
    state: merged

# -------------------------------------------------------------------------
# Task 2: Replace interface addresses with IPv4 and IPv6
# Description:
#   - This example shows how to replace all addresses on a VLAN interface
#     with a new set of IPv4 and IPv6 addresses using 'replaced' state.
# -------------------------------------------------------------------------
# - name: "Task 2: Replace IPv4 and IPv6 addresses on VLAN 200"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Replace address list
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - vlan_id: 200
        name: VLAN 200
        ipv4:
          - 10.10.200.1/24
        ipv6:
          - 2001:db8:200::1/64
    state: replaced

# -------------------------------------------------------------------------
# Task 3: Delete all addresses from loopback interface
# Description:
#   - This example demonstrates how to remove all IP addresses from a
#     loopback interface using the 'deleted' state.
# -------------------------------------------------------------------------
# - name: "Task 3: Remove all addressing from loopback 5"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Clear loopback IPs
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - loopback_id: 5
        name: Loopback 5
    state: deleted

# -------------------------------------------------------------------------
# Task 4: Gather Layer 3 interface configuration
# Description:
#   - This example shows how to collect current Layer 3 interface
#     configuration using 'gathered' state without making changes.
# -------------------------------------------------------------------------
# - name: "Task 4: Gather configured Layer 3 interfaces"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect routed interface addressing
  extreme.fe.extreme_fe_l3_interfaces:
    state: gathered
  register: routed_interfaces
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made.
  returned: always
  type: bool
interfaces:
  description: Final Layer 3 interface configuration after the module ran (or gathered data when ``state: gathered``).
  returned: always
  type: list
  elements: dict
  sample:
  - type: vlan
    vlan_id: 20
    name: VLAN 20
    ipv4:
      - 10.0.1.101/24
    ipv6: []
"""

ARGUMENT_SPEC = {
    "config": {"type": "list", "elements": "dict"},
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}

SUPPORTED_TYPES = {"vlan", "loopback"}


def _extract_error_code(payload: Optional[object]) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        return int(code)
    if isinstance(code, int):
        return code
    return None


def _is_not_found_response(payload: Optional[object]) -> bool:
    code = _extract_error_code(payload)
    if code == 404:
        return True
    if isinstance(payload, dict):
        message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
        if isinstance(message, str) and "not exist" in message.lower():
            return True
    return False


def _is_error_response(payload: Optional[object]) -> bool:
    code = _extract_error_code(payload)
    if code is not None and code >= 400:
        return True
    return False


class ExtremeFeL3InterfacesError(Exception):
    """Base exception for the L3 interface module."""

    def __init__(self, message: str, *, details: Optional[Dict[str, object]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, object]:
        data: Dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


class InterfaceId:
    """Represents a normalized interface identifier."""

    def __init__(self, if_type: str, identifier: int, name: Optional[str] = None, vrf: Optional[str] = None) -> None:
        self.type = if_type
        self.identifier = identifier
        self.name = name
        self.vrf = vrf

    def key(self) -> Tuple[str, int]:
        return self.type, self.identifier

    def to_result_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {"type": self.type}
        if self.type == "vlan":
            data["vlan_id"] = self.identifier
        elif self.type == "loopback":
            data["loopback_id"] = self.identifier
        if self.name:
            data["name"] = self.name
        if self.vrf:
            data["vrf"] = self.vrf
        return data


def dotted_netmask_to_prefix(mask: str) -> int:
    try:
        network = ip_network(f"0.0.0.0/{mask}")
    except ValueError as exc:
        raise ExtremeFeL3InterfacesError(f"Invalid IPv4 netmask '{mask}'") from exc
    return int(network.prefixlen)


def normalize_ipv4_entry(value: object) -> Tuple[str, str, int]:
    if isinstance(value, str):
        data = value.strip()
        if "/" not in data:
            raise ExtremeFeL3InterfacesError(f"IPv4 address '{value}' must include prefix length")
        addr, prefix = data.split("/", 1)
        prefixlen = int(prefix)
    elif isinstance(value, dict):
        addr = value.get("address") or value.get("addr")
        if not addr:
            raise ExtremeFeL3InterfacesError("IPv4 address dictionary must include 'address'")
        if "prefix" in value and value["prefix"] is not None:
            prefixlen = int(value["prefix"])
        elif "mask_length" in value and value["mask_length"] is not None:
            prefixlen = int(value["mask_length"])
        elif "maskLength" in value and value["maskLength"] is not None:
            prefixlen = int(value["maskLength"])
        elif "mask" in value and value["mask"]:
            prefixlen = dotted_netmask_to_prefix(str(value["mask"]))
        else:
            raise ExtremeFeL3InterfacesError("IPv4 address dictionary must include prefix or mask")
    else:
        raise ExtremeFeL3InterfacesError(f"Unsupported IPv4 address type: {type(value).__name__}")

    try:
        iface = IPv4Interface(f"{addr}/{prefixlen}")
    except ValueError as exc:
        raise ExtremeFeL3InterfacesError(f"Invalid IPv4 interface '{addr}/{prefixlen}'") from exc
    return "ipv4", str(iface.ip), int(iface.network.prefixlen)


def normalize_ipv6_entry(value: object) -> Tuple[str, str, int]:
    if isinstance(value, str):
        data = value.strip()
        if "/" not in data:
            raise ExtremeFeL3InterfacesError(f"IPv6 address '{value}' must include prefix length")
        addr, prefix = data.split("/", 1)
        prefixlen = int(prefix)
    elif isinstance(value, dict):
        addr = value.get("address") or value.get("addr")
        if not addr:
            raise ExtremeFeL3InterfacesError("IPv6 address dictionary must include 'address'")
        if "prefix" in value and value["prefix"] is not None:
            prefixlen = int(value["prefix"])
        elif "mask_length" in value and value["mask_length"] is not None:
            prefixlen = int(value["mask_length"])
        elif "maskLength" in value and value["maskLength"] is not None:
            prefixlen = int(value["maskLength"])
        else:
            raise ExtremeFeL3InterfacesError("IPv6 address dictionary must include prefix")
    else:
        raise ExtremeFeL3InterfacesError(f"Unsupported IPv6 address type: {type(value).__name__}")

    try:
        iface = IPv6Interface(f"{addr}/{prefixlen}")
    except ValueError as exc:
        raise ExtremeFeL3InterfacesError(f"Invalid IPv6 interface '{addr}/{prefixlen}'") from exc
    return "ipv6", str(iface.ip), int(iface.network.prefixlen)


def normalize_interface_addresses(entry: Dict[str, object]) -> Set[str]:
    addresses: Set[str] = set()
    for item in entry.get("ipv4") or []:
        family, addr, prefix = normalize_ipv4_entry(item)
        addresses.add(f"{family}:{addr}/{prefix}")
    for item in entry.get("ipv6") or []:
        family, addr, prefix = normalize_ipv6_entry(item)
        addresses.add(f"{family}:{addr}/{prefix}")
    return addresses


def set_from_payload(address_list: Iterable[object], *, is_vlan: bool) -> Set[str]:
    results: Set[str] = set()
    for item in address_list or []:
        payload = item
        if is_vlan:
            if not isinstance(item, dict):
                continue
            payload = item.get("address")
        if not isinstance(payload, dict):
            continue
        ip_type = payload.get("ipAddressType") or payload.get("ip_type")
        address = payload.get("address")
        mask = payload.get("maskLength") or payload.get("mask_length")
        if not ip_type or not address or mask is None:
            continue
        if ip_type == "IPv4":
            family = "ipv4"
        elif ip_type == "IPv6":
            family = "ipv6"
        else:
            continue
        results.add(f"{family}:{address}/{int(mask)}")
    return results


def addresses_to_payload(addresses: Set[str], *, is_vlan: bool) -> List[Dict[str, object]]:
    payload: List[Dict[str, object]] = []
    for entry in sorted(addresses):
        family, value = entry.split(":", 1)
        addr, prefix = value.split("/", 1)
        base = {
            "ipAddressType": "IPv4" if family == "ipv4" else "IPv6",
            "address": addr,
            "maskLength": int(prefix),
        }
        if is_vlan:
            payload.append({"address": base})
        else:
            payload.append(base)
    return payload


def infer_interface(entry: Dict[str, object]) -> InterfaceId:
    if_type = entry.get("type")
    if if_type:
        if_type = str(if_type).strip().lower()
        if if_type not in SUPPORTED_TYPES:
            raise ExtremeFeL3InterfacesError(f"Unsupported interface type '{if_type}'")
    name = entry.get("name")
    vlan_id = entry.get("vlan_id")
    loopback_id = entry.get("loopback_id")
    if if_type == "vlan" or (if_type is None and vlan_id is not None):
        if vlan_id is None:
            if name and name.lower().startswith("vlan"):
                try:
                    vlan_id = int(name.split()[1])
                except Exception as exc:
                    raise ExtremeFeL3InterfacesError(
                        "Unable to infer VLAN identifier from name; specify 'vlan_id'"
                    ) from exc
            else:
                raise ExtremeFeL3InterfacesError("'vlan_id' is required for VLAN interfaces")
        return InterfaceId("vlan", int(vlan_id), name=name, vrf=entry.get("vrf"))
    if if_type == "loopback" or (if_type is None and loopback_id is not None):
        if loopback_id is None:
            if name and name.lower().startswith("loopback"):
                try:
                    loopback_id = int(name.split()[1])
                except Exception as exc:
                    raise ExtremeFeL3InterfacesError(
                        "Unable to infer loopback identifier from name; specify 'loopback_id'"
                    ) from exc
            else:
                raise ExtremeFeL3InterfacesError("'loopback_id' is required for loopback interfaces")
        return InterfaceId("loopback", int(loopback_id), name=name, vrf=entry.get("vrf"))
    if name:
        lower = name.lower()
        if lower.startswith("vlan"):
            parts = lower.split()
            if len(parts) >= 2:
                try:
                    return InterfaceId("vlan", int(parts[1]), name=name, vrf=entry.get("vrf"))
                except Exception as exc:
                    raise ExtremeFeL3InterfacesError(
                        "Unable to infer VLAN identifier from name; specify 'type' and 'vlan_id'"
                    ) from exc
        if lower.startswith("loopback"):
            parts = lower.split()
            if len(parts) >= 2:
                try:
                    return InterfaceId("loopback", int(parts[1]), name=name, vrf=entry.get("vrf"))
                except Exception as exc:
                    raise ExtremeFeL3InterfacesError(
                        "Unable to infer loopback identifier from name; specify 'type' and 'loopback_id'"
                    ) from exc
    raise ExtremeFeL3InterfacesError("Unable to determine interface type; specify 'type'")


def vlan_path(vlan_id: int) -> str:
    return f"/v0/configuration/vlan/{vlan_id}"


def vlan_address_path(vlan_id: int) -> str:
    return f"/v0/configuration/vlan/{vlan_id}/address"


def loopback_path(loopback_id: int) -> str:
    return f"/v0/configuration/loopback/{loopback_id}"


def get_vlan_info(connection: Connection, vlan_id: int) -> Optional[Dict[str, object]]:
    try:
        data = connection.send_request(None, path=vlan_path(vlan_id), method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if _is_not_found_response(data):
        return None
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            f"Failed to retrieve VLAN {vlan_id} details",
            details={"response": data},
        )
    if isinstance(data, dict):
        return data
    return None


def put_vlan_addresses(connection: Connection, vlan_id: int, addresses: Set[str]) -> None:
    payload = {"addressList": addresses_to_payload(addresses, is_vlan=True)}
    data = connection.send_request(payload, path=vlan_address_path(vlan_id), method="PUT")
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            f"Failed to update VLAN {vlan_id} addressing",
            details={"response": data},
        )


def get_loopbacks(connection: Connection) -> List[Dict[str, object]]:
    try:
        data = connection.send_request(None, path="/v0/configuration/loopback", method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            "Failed to retrieve loopback interfaces",
            details={"response": data},
        )
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def get_loopback_info(loopbacks: Sequence[Dict[str, object]], loopback_id: int) -> Optional[Dict[str, object]]:
    for item in loopbacks:
        if int(item.get("id", -1)) == loopback_id:
            return item
    return None


def put_loopback_addresses(connection: Connection, loopback_id: int, addresses: Set[str]) -> None:
    # Per the OpenAPI spec: "An empty request means that IP address configuration
    # will be deleted for that loopback interface."
    # When the address set is empty, send {} instead of {"ipAddressList": []}
    # to properly delete the loopback interface.
    if not addresses:
        payload: Dict[str, object] = {}
    else:
        payload = {"ipAddressList": addresses_to_payload(addresses, is_vlan=False)}
    data = connection.send_request(payload, path=loopback_path(loopback_id), method="PUT")
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            f"Failed to update loopback {loopback_id} addressing",
            details={"response": data},
        )


def build_result_entry(interface: InterfaceId, addresses: Set[str]) -> Dict[str, object]:
    data = interface.to_result_dict()
    ipv4_list: List[str] = []
    ipv6_list: List[str] = []
    for entry in sorted(addresses):
        family, value = entry.split(":", 1)
        if family == "ipv4":
            ipv4_list.append(value)
        else:
            ipv6_list.append(value)
    data["ipv4"] = ipv4_list
    data["ipv6"] = ipv6_list
    return data


def gather_all(
    connection: Connection,
    *,
    filter_map: Optional[Dict[Tuple[str, int], InterfaceId]] = None,
) -> Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]]:
    results: Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]] = {}

    # Gather VLAN addressing.
    vlan_targets = [value for value in (filter_map or {}).values() if value.type == "vlan"] if filter_map else []
    if vlan_targets:
        for target in vlan_targets:
            info = get_vlan_info(connection, target.identifier)
            address_set = set_from_payload((info or {}).get("addressList", []), is_vlan=True)
            iface = InterfaceId(
                "vlan",
                target.identifier,
                name=target.name or (info or {}).get("name"),
                vrf=(info or {}).get("vrName"),
            )
            results[iface.key()] = (iface, address_set)
    elif filter_map is None or any(key[0] == "vlan" for key in (filter_map or {})):
        # Discover all VLANs when no filter is provided.
        try:
            vlan_list = connection.send_request(None, path="/v0/configuration/vlan", method="GET")
        except ConnectionError as exc:
            if getattr(exc, "code", None) == 404:
                vlan_list = []
            else:
                raise
        if _is_error_response(vlan_list):
            raise ExtremeFeL3InterfacesError(
                "Failed to retrieve VLAN inventory",
                details={"response": vlan_list},
            )
        if isinstance(vlan_list, list):
            for item in vlan_list:
                if not isinstance(item, dict):
                    continue
                vlan_id = item.get("vlanId") or item.get("vlan_id") or item.get("id")
                if vlan_id is None:
                    continue
                iface = InterfaceId(
                    "vlan",
                    int(vlan_id),
                    name=item.get("name"),
                    vrf=item.get("vrName"),
                )
                if filter_map is not None and iface.key() not in filter_map:
                    continue
                address_set = set_from_payload(item.get("addressList", []), is_vlan=True)
                results[iface.key()] = (iface, address_set)

    # Gather loopback addressing
    if filter_map is None or any(key[0] == "loopback" for key in (filter_map or {})):
        loopbacks = get_loopbacks(connection)
        for item in loopbacks:
            loopback_id = int(item.get("id", -1))
            iface = InterfaceId("loopback", loopback_id, name=item.get("name"), vrf=item.get("vrName"))
            address_set = set_from_payload(item.get("ipAddressList", []), is_vlan=False)
            if filter_map is not None and iface.key() not in filter_map:
                continue
            results[iface.key()] = (iface, address_set)

    # For VLAN gather when filter_map None and no addresses found, results stays empty
    return results


def gather_selected(connection: Connection, interfaces: List[InterfaceId]) -> Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]]:
    mapping: Dict[Tuple[str, int], InterfaceId] = {item.key(): item for item in interfaces}
    gathered = gather_all(connection, filter_map=mapping)
    # For VLAN entries not returned (because gather_all skip), fetch individually now
    for iface in interfaces:
        key = iface.key()
        if key in gathered:
            continue
        if iface.type == "vlan":
            info = get_vlan_info(connection, iface.identifier)
            if info is None:
                raise ExtremeFeL3InterfacesError(f"VLAN {iface.identifier} does not exist")
            derived = InterfaceId(
                "vlan",
                iface.identifier,
                name=iface.name or info.get("name"),
                vrf=info.get("vrName"),
            )
            addresses = set_from_payload(info.get("addressList", []), is_vlan=True)
            gathered[key] = (derived, addresses)
        elif iface.type == "loopback":
            loopbacks = get_loopbacks(connection)
            item = get_loopback_info(loopbacks, iface.identifier)
            if item is None:
                raise ExtremeFeL3InterfacesError(f"Loopback {iface.identifier} does not exist")
            derived = InterfaceId(
                "loopback",
                iface.identifier,
                name=iface.name or item.get("name"),
                vrf=item.get("vrName"),
            )
            addresses = set_from_payload(item.get("ipAddressList", []), is_vlan=False)
            gathered[key] = (derived, addresses)
    return gathered


def compute_final_sets(
    state: str,
    config_map: Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]],
    existing_map: Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]],
) -> Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]]:
    final: Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]] = {}
    if state == "overridden":
        # All existing interfaces not in config are cleared
        for key, (iface, current) in existing_map.items():
            desired = config_map.get(key)
            if desired:
                final[key] = (desired[0], set(desired[1]))
            else:
                final[key] = (iface, set())
        # Ensure config entries not in existing are included
        for key, value in config_map.items():
            if key not in final:
                final[key] = (value[0], set(value[1]))
        return final

    if state == "replaced":
        for key, value in config_map.items():
            final[key] = (value[0], set(value[1]))
        return final

    if state == "merged":
        for key, value in config_map.items():
            current = existing_map.get(key)
            combined = set(current[1]) if current else set()
            combined |= set(value[1])
            final[key] = (value[0], combined)
        return final

    if state == "deleted":
        for key, value in config_map.items():
            current = existing_map.get(key)
            if not current:
                final[key] = (value[0], set())
                continue
            if value[1]:
                remaining = set(current[1]) - set(value[1])
            else:
                remaining = set()
            final[key] = (current[0], remaining)
        return final

    # gathered handled elsewhere
    return {}


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    state = module.params["state"]
    config = module.params.get("config") or []

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == "gathered":
            interfaces: List[InterfaceId] = []
            if config:
                for item in config:
                    iface = infer_interface(item)
                    interfaces.append(iface)
                gathered = gather_selected(connection, interfaces)
            else:
                gathered = gather_all(connection)
            result_list = [build_result_entry(iface, addresses) for iface, addresses in gathered.values()]
            module.exit_json(changed=False, interfaces=result_list)

        # normalize config input
        config_map: Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]] = {}
        for item in config:
            iface = infer_interface(item)
            addresses = normalize_interface_addresses(item)
            config_map[iface.key()] = (iface, addresses)

        if not config_map and state in {"merged", "replaced", "deleted"}:
            raise ExtremeFeL3InterfacesError("'config' is required for the selected state")

        if state == "overridden":
            existing = gather_all(connection)
            for key, (iface, _) in config_map.items():
                if key not in existing:
                    if iface.type == "vlan":
                        raise ExtremeFeL3InterfacesError(f"VLAN {iface.identifier} does not exist")
                    if iface.type == "loopback":
                        raise ExtremeFeL3InterfacesError(f"Loopback {iface.identifier} does not exist")
        else:
            existing = gather_selected(connection, [value[0] for value in config_map.values()])
        final_sets = compute_final_sets(state, config_map, existing)

        changed = False
        results: Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]] = {}
        for key, (iface, desired_set) in final_sets.items():
            current_set = existing.get(key, (iface, set()))[1]
            if desired_set != current_set:
                changed = True
                if not module.check_mode:
                    if iface.type == "vlan":
                        put_vlan_addresses(connection, iface.identifier, desired_set)
                    elif iface.type == "loopback":
                        put_loopback_addresses(connection, iface.identifier, desired_set)
            results[key] = (iface, desired_set)

        # When deleted/merged/replaced result_map for interfaces not touched but existing: ensure output covers all
        output_map = existing.copy()
        output_map.update(results)

        result_list = [build_result_entry(iface, addresses) for iface, addresses in output_map.values()]
        module.exit_json(changed=changed, interfaces=result_list)

    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except ExtremeFeL3InterfacesError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
