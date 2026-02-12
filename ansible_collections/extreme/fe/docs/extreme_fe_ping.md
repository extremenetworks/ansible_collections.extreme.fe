# extreme_fe_ping

```yaml

module: extreme_fe_ping
short_description: Execute ICMP ping requests on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
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

```