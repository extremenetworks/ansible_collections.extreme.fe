# -*- coding: utf-8 -*-
"""Ansible module to execute ping operations on ExtremeNetworks Fabric Engine switches."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

from ipaddress import ip_address
from typing import Dict, Optional
from urllib.parse import quote

DOCUMENTATION = r"""
module: extreme_fe_ping
short_description: Execute ICMP ping requests on ExtremeNetworks Fabric Engine switches
version_added: 1.3.0
description:
- Transmit ICMP echo requests from ExtremeNetworks Fabric Engine (VOSS) switches using the custom ``extreme_fe`` HTTPAPI plugin.
- Supports VRF specific pings, management interface contexts, scoped IPv6 probes, and explicit egress interface selection.
- Returns detailed per-packet telemetry and fails when the switch reports any timeout or unsuccessful probe.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
- Service probe assisted pings are limited to IPv4 and instance ``1`` on Fabric Engine.
requirements:
- ansible.netcommon
options:
  host:
    description:
    - Destination hostname or IP address.
    type: str
    required: true
  host_type:
    description:
    - Explicitly set the host identifier type when autodetection is not desired.
    type: str
    choices: [hostname, IPv4, IPv6]
  count:
    description:
    - Number of ICMP echo requests to send.
    type: int
  datasize:
    description:
    - Payload size in bytes for each probe. Fabric Engine supports 28-9216 for IPv4 and up to 51200 for IPv6.
    type: int
  transmission_interval:
    description:
    - Interval between probes in seconds.
    type: int
  timeout_interval:
    description:
    - Response timeout in seconds.
    type: int
  source_ip_address:
    description:
    - Source IPv4/IPv6 address. Cannot be combined with ``management_type`` or service probe operations.
    type: raw
  scope_id:
    description:
    - IPv6 scope circuit identifier. Only valid for IPv6 destinations.
    type: int
  management_type:
    description:
    - Management context to source the ping from.
    type: str
    choices: [OOB, VLAN, CLIP, AUTO]
  vrf:
    description:
    - VRF context to use. Use ``GlobalRouter`` for the default VRF.
    type: str
  interface:
    description:
    - Explicit egress interface specification. Cannot be combined with ``management_type``.
    type: dict
    suboptions:
      type:
        description:
        - Interface type identifier.
        type: str
        choices: [GIGABITETHERNET, TUNNEL, VLAN]
        required: true
      port:
        description:
        - Interface name when ``type`` is ``GIGABITETHERNET`` (slot:port notation).
        type: str
      tunnel_id:
        description:
        - Tunnel identifier when ``type`` is ``TUNNEL``.
        type: int
      vlan_id:
        description:
        - VLAN identifier when ``type`` is ``VLAN``.
        type: int
  service_probe_instance:
    description:
    - Service probe instance used to source the ping (IPv4 only).
    type: int
return_values:
  response:
    description: Parsed response payload returned by the Fabric Engine REST API.
    returned: success
    type: dict
"""

EXAMPLES = r"""
- name: Ping an IPv4 host from GlobalRouter
  hosts: switches
  gather_facts: false
  tasks:
    - name: Run IPv4 ping
      extreme_fe_ping:
        host: 10.0.10.1
        count: 5
        datasize: 64
        vrf: GlobalRouter

- name: Ping an IPv6 host from a management VLAN context
  hosts: switches
  gather_facts: false
  tasks:
    - name: Run IPv6 ping through mgmt VLAN
      extreme_fe_ping:
        host: 2001:db8:100::1
        management_type: VLAN
        timeout_interval: 10
        transmission_interval: 2

- name: Ping using a specific egress interface
  hosts: switches
  gather_facts: false
  tasks:
    - name: Use port 1:5 as the source interface
      extreme_fe_ping:
        host: server01.example.com
        interface:
          type: GIGABITETHERNET
          port: "1:5"
        count: 3
"""

RETURN = r"""
response:
  description: Ping execution details reported by the device.
  returned: success
  type: dict
changed:
  description: Always false because ping does not modify device state.
  returned: always
  type: bool
"""

ARGUMENT_SPEC = {
    "host": {"type": "str", "required": True},
    "host_type": {"type": "str", "choices": ["hostname", "IPv4", "IPv6"]},
    "count": {"type": "int"},
    "datasize": {"type": "int"},
    "transmission_interval": {"type": "int"},
    "timeout_interval": {"type": "int"},
    "source_ip_address": {"type": "raw"},
    "scope_id": {"type": "int"},
    "management_type": {"type": "str", "choices": ["OOB", "VLAN", "CLIP", "AUTO"]},
    "vrf": {"type": "str"},
    "interface": {
        "type": "dict",
        "options": {
            "type": {"type": "str", "choices": ["GIGABITETHERNET", "TUNNEL", "VLAN"], "required": True},
            "port": {"type": "str"},
            "tunnel_id": {"type": "int"},
            "vlan_id": {"type": "int"},
        },
    },
    "service_probe_instance": {"type": "int"},
}

SUPPORTED_INTERFACE_KEYS = {
    "GIGABITETHERNET": "port",
    "TUNNEL": "tunnel_id",
    "VLAN": "vlan_id",
}


class ExtremeFePingError(Exception):
    """Custom exception for ping module errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)

    def to_fail_kwargs(self) -> Dict[str, object]:
        return {"msg": to_text(self)}


def _determine_host_type(host: str, explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    try:
        addr = ip_address(host)
    except ValueError:
        return "hostname"
    return "IPv4" if addr.version == 4 else "IPv6"


def _to_general_ip(value: object) -> Dict[str, object]:
    if isinstance(value, dict):
        lower = {k.lower(): v for k, v in value.items()}
        address = lower.get("address")
        ip_type = lower.get("ipaddresstype") or lower.get("type")
        if not address:
            raise ExtremeFePingError("source_ip_address dictionary must include 'address'")
        try:
            addr = ip_address(str(address))
        except ValueError as exc:
            raise ExtremeFePingError(f"Invalid source IP address '{address}'") from exc
        if ip_type:
            ip_type = str(ip_type)
            if ip_type not in {"IPv4", "IPv6"}:
                raise ExtremeFePingError("source_ip_address 'ipAddressType' must be 'IPv4' or 'IPv6'")
            if (addr.version == 4 and ip_type != "IPv4") or (addr.version == 6 and ip_type != "IPv6"):
                raise ExtremeFePingError("source_ip_address type does not match the address")
        return {"ipAddressType": "IPv4" if addr.version == 4 else "IPv6", "address": str(addr)}
    if isinstance(value, str):
        try:
            addr = ip_address(value)
        except ValueError as exc:
            raise ExtremeFePingError(f"Invalid source IP address '{value}'") from exc
        return {"ipAddressType": "IPv4" if addr.version == 4 else "IPv6", "address": str(addr)}
    raise ExtremeFePingError("source_ip_address must be a string or mapping")


def _build_interface_payload(data: Optional[Dict[str, object]]) -> Optional[Dict[str, object]]:
    if not data:
        return None
    iface_type = data.get("type")
    if not iface_type:
        raise ExtremeFePingError("interface.type is required")
    iface_type = str(iface_type).upper()
    if iface_type not in SUPPORTED_INTERFACE_KEYS:
        raise ExtremeFePingError(f"Unsupported interface type '{iface_type}'")
    key_name = SUPPORTED_INTERFACE_KEYS[iface_type]
    value = data.get(key_name)
    if value is None:
        raise ExtremeFePingError(f"interface.{key_name} is required when interface.type is '{iface_type}'")
    payload: Dict[str, object] = {"interfaceType": iface_type}
    if iface_type == "GIGABITETHERNET":
        payload["port"] = str(value)
    elif iface_type == "TUNNEL":
        payload["tunnelId"] = int(value)
    elif iface_type == "VLAN":
        payload["vlanId"] = int(value)
    return payload


def _ping_path(host_type: str, host: str) -> str:
    return "/v0/operation/system/ping/{host_type}/host/{host}/:transmit".format(
        host_type=quote(host_type, safe=""),
        host=quote(host, safe=""),
    )


def validate_parameters(module: AnsibleModule, host_type: str) -> None:
    params = module.params
    management_type = params.get("management_type")
    interface = params.get("interface")
    source_ip = params.get("source_ip_address")
    scope_id = params.get("scope_id")
    vrf = params.get("vrf")
    service_probe = params.get("service_probe_instance")

    if management_type:
        if source_ip or interface or scope_id or vrf:
            raise ExtremeFePingError(
                "management_type cannot be combined with source_ip_address, scope_id, vrf, or interface"
            )
    if scope_id is not None and host_type != "IPv6":
        raise ExtremeFePingError("scope_id can only be used with IPv6 destinations")
    if interface and management_type:
        raise ExtremeFePingError("interface cannot be used together with management_type")
    if service_probe is not None:
        if management_type or vrf or source_ip or interface or scope_id:
            raise ExtremeFePingError(
                "service_probe_instance cannot be combined with other context parameters"
            )
        if host_type != "IPv4":
            raise ExtremeFePingError("service_probe_instance is only supported for IPv4 destinations")
        if int(service_probe) != 1:
            raise ExtremeFePingError("Only service probe instance 1 is supported on Fabric Engine")

    count = params.get("count")
    if count is not None and not (1 <= count <= 9999):
        raise ExtremeFePingError("count must be between 1 and 9999 for Fabric Engine")
    datasize = params.get("datasize")
    if datasize is not None and datasize < 0:
        raise ExtremeFePingError("datasize must be a non-negative integer")
    transmission_interval = params.get("transmission_interval")
    if transmission_interval is not None and not (1 <= transmission_interval <= 60):
        raise ExtremeFePingError("transmission_interval must be between 1 and 60")
    timeout_interval = params.get("timeout_interval")
    if timeout_interval is not None and not (1 <= timeout_interval <= 120):
        raise ExtremeFePingError("timeout_interval must be between 1 and 120")


def build_payload(module: AnsibleModule, host_type: str) -> Dict[str, object]:
    params = module.params
    payload: Dict[str, object] = {}

    if params.get("count") is not None:
        payload["count"] = int(params["count"])
    if params.get("datasize") is not None:
        payload["datasize"] = int(params["datasize"])
    if params.get("transmission_interval") is not None:
        payload["transmissionInterval"] = int(params["transmission_interval"])
    if params.get("timeout_interval") is not None:
        payload["timeoutInterval"] = int(params["timeout_interval"])
    if params.get("scope_id") is not None:
        payload["scopeId"] = int(params["scope_id"])
    if params.get("management_type"):
        payload["managementType"] = params["management_type"]
    if params.get("vrf"):
        payload["vrf"] = params["vrf"]
    if params.get("service_probe_instance") is not None:
        payload["serviceProbeInstance"] = int(params["service_probe_instance"])

    if params.get("source_ip_address"):
        payload["sourceIpAddress"] = _to_general_ip(params["source_ip_address"])

    interface_payload = _build_interface_payload(params.get("interface"))
    if interface_payload:
        payload["interface"] = interface_payload

    # Fabric Engine requires IPv6 datasize lower bound 28; for IPv4 the same lower bound applies.
    if params.get("datasize") is not None and params["datasize"] < 28:
        raise ExtremeFePingError("datasize must be at least 28 bytes on Fabric Engine")

    if params.get("datasize") is not None and host_type == "IPv4" and params["datasize"] > 9216:
        raise ExtremeFePingError("datasize must be <= 9216 bytes for IPv4 on Fabric Engine")
    if params.get("datasize") is not None and host_type == "IPv6" and params["datasize"] > 51200:
        raise ExtremeFePingError("datasize must be <= 51200 bytes for IPv6 on Fabric Engine")

    return payload


def interpret_ping_response(response: Optional[Dict[str, object]]) -> Optional[str]:
    if not isinstance(response, dict):
        return "Device returned an unexpected response payload"

    if response.get("result") == "FAIL":
        return "Service probe reported failure"

    if response.get("isTimeout"):
        return "Ping timed out" if response.get("packetsReceived", 0) == 0 else "Ping partially timed out"

    transmitted = response.get("packetsTransmitted")
    received = response.get("packetsReceived")
    if isinstance(transmitted, int) and transmitted > 0 and isinstance(received, int):
        if received == 0:
            return "All ping probes were lost"
    return None


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    if module.check_mode:
        module.exit_json(changed=False, skipped=True, msg="Check mode: ping not executed")

    host = module.params["host"].strip()
    if not host:
        module.fail_json(msg="host must not be empty")
    host_type = _determine_host_type(host, module.params.get("host_type"))

    try:
        validate_parameters(module, host_type)
    except ExtremeFePingError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    try:
        payload = build_payload(module, host_type)
    except ExtremeFePingError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        response = connection.send_request(
            payload,
            path=_ping_path(host_type, host),
            method="POST",
        )
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except ExtremeFePingError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    failure_reason = interpret_ping_response(response)
    if failure_reason:
        module.fail_json(msg=failure_reason, response=response)

    module.exit_json(changed=False, response=response)


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
