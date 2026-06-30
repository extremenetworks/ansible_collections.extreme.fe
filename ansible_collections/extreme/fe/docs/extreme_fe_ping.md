# ICMP Ping

## Module: extreme.fe.extreme_fe_ping

Sends a ping from a Fabric Engine device to the given host.

---

Version added: 1.0.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Parameters](#parameters)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

This module transmits ICMP echo requests from Fabric Engine devices to the given host using the REST API endpoints exposed through the OpenAPI Server.

- Supports VRF-specific pings, management interface contexts, scoped IPv6 probes, and explicit egress interface selection.
- Returns detailed per-packet telemetry and fails when the switch reports any timeout or unsuccessful probe.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| POST | /v0/operation/system/ping/{host_type}/host/{host}/:transmit | Execute ping operation |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `host` | str | Yes | - | Destination hostname or IP address |
| `host_type` | str | No | - | Host identifier type: `hostname`, `IPv4`, `IPv6` |
| `count` | int | No | - | Number of ICMP echo requests to send |
| `datasize` | int | No | - | Payload size in bytes (28-9216 IPv4, up to 51200 IPv6) |
| `transmission_interval` | int | No | - | Interval between probes in seconds |
| `timeout_interval` | int | No | - | Response timeout in seconds |
| `source_ip_address` | raw | No | - | Source IPv4/IPv6 address |
| `scope_id` | int | No | - | IPv6 scope circuit identifier |
| `management_type` | str | No | - | Management context: `OOB`, `VLAN`, `CLIP`, `AUTO` |
| `vrf` | str | No | - | VRF context (use `GlobalRouter` for default) |
| `interface` | dict | No | - | Explicit egress interface specification |
| `interface.type` | str | Yes | - | Interface type: `GIGABITETHERNET`, `TUNNEL`, `VLAN` |
| `interface.port` | str | No | - | Port name (slot:port) when type is GIGABITETHERNET |
| `interface.tunnel_id` | int | No | - | Tunnel ID when type is TUNNEL |
| `interface.vlan_id` | int | No | - | VLAN ID when type is VLAN |
| `service_probe_instance` | int | No | - | Service probe instance (IPv4 only) |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Always false — ping does not modify device state |
| `response` | dict | Ping execution details reported by the device |

---

## [Examples](#table-of-contents)

### Basic ping

```yaml
- name: Ping peer switch via management interface
  extreme.fe.extreme_fe_ping:
    host: 10.0.0.1
    count: 3
    management_type: AUTO
```

### Ping through a specific VRF

```yaml
- name: Ping gateway through VRF
  extreme.fe.extreme_fe_ping:
    host: 192.168.1.1
    count: 5
    vrf: my-vrf
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Network connectivity checks
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Ping default gateway
      extreme.fe.extreme_fe_ping:
        host: 10.0.0.1
        count: 3
        management_type: AUTO
      register: ping_result

    - name: Display ping results
      ansible.builtin.debug:
        var: ping_result.response
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
