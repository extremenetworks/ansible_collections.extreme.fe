# Simple Loop Prevention Protocol (SLPP)

## Module: extreme.fe.extreme_fe_slpp

Manages Simple Loop Prevention Protocol settings on Fabric Engine devices.

---

Version added: 1.1.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Parameters](#parameters)
- [State Behaviour Summary](#state-behaviour-summary)
- [Factory Defaults](#factory-defaults)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

This module manages global, per-VLAN, and per-port SLPP settings on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- SLPP detects and contains Layer-2 loops by sending special loop-detection frames and blocking or shutting down the offending port.
- Supports SLPP guard and packet reception detection modes.

---

## [Notes](#table-of-contents)

- Port identifiers must use slot:port notation such as `1:5`.
- On Fabric Engine devices, `enable_packet_rx` and `enable_guard` are mutually exclusive for a given port; the module will fail if both are set to `true`.
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
| GET | /v0/configuration/slpp | Get full SLPP configuration |
| PATCH | /v0/configuration/slpp | Update global SLPP settings |
| PATCH | /v0/configuration/slpp/vlan/{vlan_id} | Update per-VLAN settings |
| PATCH | /v0/configuration/slpp/ports/{port} | Update per-port settings |
| GET | /v0/state/slpp | Get live SLPP port state |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `global_settings` | dict | No | - | Global SLPP settings |
| `global_settings.enabled` | bool | No | - | Enable/disable SLPP globally |
| `config` | dict | No | - | SLPP configuration. Groups the two resource types the module manages; a task may configure either or both in one run |
| `config.vlans` | list of dict | No | - | Per-VLAN SLPP settings |
| `config.vlans[].vlan_id` | int | Yes | - | VLAN identifier |
| `config.vlans[].enabled` | bool | No | - | Enable/disable SLPP on this VLAN |
| `config.ports` | list of dict | No | - | Per-port SLPP settings |
| `config.ports[].name` | str | Yes | - | Port identifier (slot:port) |
| `config.ports[].enable_guard` | bool | No | - | Enable SLPP guard on the port |
| `config.ports[].guard_timeout` | int | No | - | SLPP guard timeout in seconds |
| `config.ports[].enable_packet_rx` | bool | No | - | Enable SLPP packet-rx detection |
| `config.ports[].packet_rx_threshold` | int | No | - | Packet-rx detection threshold |
| `vlans` | list of dict | No | - | **Deprecated** pre-1.2.1 form of `config.vlans`. Still accepted, warns, and cannot be combined with `config` |
| `ports` | list of dict | No | - | **Deprecated** pre-1.2.1 form of `config.ports`. Still accepted, warns, and cannot be combined with `config` |
| `gather_filter` | list of str | No | - | Limit gathered port output |
| `gather_vlan_filter` | list of int | No | - | Limit gathered VLAN output |
| `gather_state` | bool | No | `false` | Include live SLPP port state |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply provided settings incrementally. Fields not supplied are left untouched. | GET, PATCH |
| `replaced` | Make supplied values authoritative for targeted resources. Fields omitted from an entry are reset to their factory defaults, so partial configuration is valid input. | GET, PATCH |
| `overridden` | Replace running configuration; remove entries not provided. Omitted fields are reset to factory defaults, the same as `replaced`. | GET, PATCH |
| `deleted` | Remove specified per-port/VLAN overrides. | GET, PATCH |
| `gathered` | Read-only — return current SLPP configuration and optional state. | GET |

---

## [Factory Defaults](#table-of-contents)

These values are used to reset fields omitted from a `replaced` or `overridden`
entry, and as the reset payload for `deleted`.

| Field | Default Value | Source |
|-------|---------------|--------|
| `config.ports[].enable_guard` | `false` | OpenAPI `SlppPortSettings.enableGuard` |
| `config.ports[].guard_timeout` | `0` | Not in OpenAPI. Verified on device with `show slpp-guard` (Timeout column reads 0 on factory-default ports). The User Guide states 60 seconds, which does not match device behaviour |
| `config.ports[].enable_packet_rx` | `false` | OpenAPI `SlppPortSettings.enablePacketRx` |
| `config.ports[].packet_rx_threshold` | `1` | OpenAPI `SlppPortSettings.packetRxThreshold` |
| `config.vlans[].enabled` | `false` | OpenAPI `SlppVlanSettings.enabled` |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `before` | dict | Full SLPP configuration before changes. Returned for `merged`, `replaced`, `overridden`, `deleted` |
| `before.global_settings` | dict | Global SLPP configuration before changes |
| `before.ports_settings` | list | Per-port SLPP settings before changes |
| `before.vlans_settings` | list | Per-VLAN SLPP settings before changes |
| `after` | dict | Full SLPP configuration re-read from the device after changes. Same structure as `before`. Returned only when `changed` is true and not in check mode |
| `gathered` | dict | SLPP configuration gathered from the device. Same structure as `before`, narrowed by `gather_filter` and `gather_vlan_filter` when supplied. Returned for `state=gathered` |
| `global_settings` | dict | Global SLPP configuration |
| `vlans_settings` | list | Per-VLAN SLPP settings |
| `ports_settings` | list | Per-port SLPP settings |
| `port_updates` | list | Ports modified during execution |
| `port_removals` | list | Ports whose overrides were removed |
| `vlan_updates` | list | VLANs modified during execution |
| `vlan_removals` | list | VLANs whose overrides were removed |
| `ports_state` | list | Live SLPP port state |

---

## [Examples](#table-of-contents)

### Enable SLPP globally

```yaml
- name: Enable SLPP
  extreme.fe.extreme_fe_slpp:
    state: merged
    global_settings:
      enabled: true
```

### Configure SLPP guard on a port

```yaml
- name: Enable SLPP guard on port 1:5
  extreme.fe.extreme_fe_slpp:
    state: merged
    config:
      ports:
        - name: "1:5"
          enable_guard: true
```

### Gather SLPP configuration

```yaml
- name: Collect SLPP information
  extreme.fe.extreme_fe_slpp:
    state: gathered
    gather_state: true
  register: slpp_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage SLPP on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current SLPP configuration
      extreme.fe.extreme_fe_slpp:
        state: gathered
        gather_state: true
      register: slpp_before

    - name: Enable SLPP globally
      extreme.fe.extreme_fe_slpp:
        state: merged
        global_settings:
          enabled: true

    - name: Enable SLPP guard on access ports
      extreme.fe.extreme_fe_slpp:
        state: merged
        ports:
          - name: "1:5"
            enable_guard: true
          - name: "1:6"
            enable_guard: true

    - name: Remove SLPP overrides from ports
      extreme.fe.extreme_fe_slpp:
        state: deleted
        ports:
          - name: "1:5"
          - name: "1:6"
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
