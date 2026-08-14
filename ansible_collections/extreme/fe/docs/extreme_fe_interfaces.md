# Ethernet Interfaces

## Module: extreme.fe.extreme_fe_interfaces

Manages Ethernet interfaces on Fabric Engine devices.

---

Version added: 1.0.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Parameters](#parameters)
- [State Behaviour Summary](#state-behaviour-summary)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

Through this module administrative state, global interface settings, and per-port attributes can be configured on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- The module supports enabling or disabling multiple ports, adjusting global port flags, and tuning per-port features such as speed, duplex, EEE, and Fabric Engine specific options.

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
| GET | /v0/configuration/ports | Retrieve all port configurations |
| PUT | /v0/configuration/ports | Update multiple port admin statuses |
| PATCH | /v0/configuration/ports/{port} | Update specific port settings |
| GET | /v0/configuration/ports/global | Get global port settings |
| PATCH | /v0/configuration/ports/global | Update global port settings |
| GET | /v1/state/ports | Get port state |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `global_settings` | dict | No | - | Fabric Engine global port settings |
| `global_settings.flow_control_mode` | bool | No | - | Enable/disable global flow control |
| `global_settings.advanced_feature_bandwidth_reservation` | str | No | - | Loopback bandwidth reservation (`DISABLE`, `LOW`, `HIGH`, `VIM`) |
| `admin` | list of dict | No | - | Bulk admin enable/disable operations |
| `admin[].name` | str | Yes | - | Port identifier (slot:port) |
| `admin[].enabled` | bool | Yes | - | Administrative status |
| `config` | list of dict | No | - | Per-port configuration settings. Aliased as `ports`, the pre-1.2.1 name, which is deprecated but still accepted |
| `config[].name` | str | Yes | - | Port identifier (slot:port) |
| `config[].enabled` | bool | No | - | Administrative status |
| `config[].description` | str | No | - | Interface description (max 255 chars) |
| `config[].speed` | str | No | - | Speed override (`0M`, `10M`, `100M`, `1G`, `2.5G`, `5G`, `10G`, `20G`, `25G`, `40G`, `50G`, `100G`, `400G`, `AUTO`) |
| `config[].duplex` | str | No | - | Duplex setting (`HALF_DUPLEX`, `FULL_DUPLEX`, `NONE`) |
| `config[].auto_negotiation` | bool | No | - | Toggle auto-negotiation |
| `config[].auto_advertisements` | list of str | No | - | Authoritative list of auto-negotiation advertisements |
| `config[].flow_control` | str | No | - | Flow control mode (`ENABLE`, `DISABLE`) |
| `config[].debounce_timer` | int | No | - | Debounce timer in ms (0-300000) |
| `config[].channelized` | bool | No | - | Enable/disable channelization on supported fiber ports |
| `config[].fec` | str | No | - | Forward error correction mode (`NONE`, `CLAUSE_74`, `CLAUSE_91_108`, `AUTO`) |
| `config[].eee` | bool | No | - | Energy Efficient Ethernet |
| `config[].port_mode` | bool | No | - | Tagging mode (true = trunk) |
| `config[].flex_uni` | bool | No | - | Flex UNI mode |
| `config[].native_vlan` | int | No | - | Native VLAN for trunk ports (1-4094). `0` is accepted but is currently a no-op: the device rejects every value the module could use to clear the assignment (`0` with HTTP 422, JSON null with "None is not of type integer", and `1` unless the port is already a VLAN 1 member), so the field is omitted instead. **No state can clear an existing assignment** — `replaced` and `overridden` leave it in place when omitted, and `deleted` drops it from the reset payload for the same reason, so removing a native VLAN has to be done from the CLI. Other values are rejected before the request is sent |
| `config[].ip_arp_inspection_trusted` | bool | No | - | Mark interface as trusted for ARP inspection |
| `gather_filter` | list of str | No | - | Limit gathered output to these ports |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply supplied interface changes incrementally. | GET, PUT, PATCH |
| `replaced` | Make supplied values authoritative for targeted interfaces. | GET, PUT, PATCH |
| `overridden` | Enforce supplied definitions; clear unlisted overrides. | GET, PUT, PATCH |
| `deleted` | Remove supplied interface configuration and overrides. | GET, PUT, PATCH |
| `gathered` | Read-only — return interface state. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `before` | list | Per-port configuration before the task ran. Returned for every state except `gathered`. Ports named in `config` are re-read individually so they carry the full field set; elsewhere the bulk listing may omit fields it treats as unset (typically `description`) — missing means not reported, not cleared |
| `after` | list | Per-port configuration after the task ran, re-read from the device. Omitted when nothing changed or in check mode. Built the same way as `before`, so the two are directly comparable |
| `global_settings` | dict | Resulting global port configuration |
| `admin_updates` | list | Ports whose admin status was changed |
| `port_updates` | list | Ports whose attributes were modified |
| `port_removals` | list | Ports whose overrides were removed |
| `ports_state` | list | Interface state details (gathered) |

---

## [Examples](#table-of-contents)

### Disable multiple ports

```yaml
- name: Disable selected ports
  extreme.fe.extreme_fe_interfaces:
    state: merged
    admin:
      - name: "1:5"
        enabled: false
      - name: "1:6"
        enabled: false
```

### Configure port attributes

```yaml
- name: Tune interface attributes
  extreme.fe.extreme_fe_interfaces:
    state: replaced
    config:
      - name: "1:5"
        description: Server uplink
        auto_negotiation: false
        speed: 100M
        duplex: FULL_DUPLEX
        port_mode: true
        native_vlan: 200
```

### Gather interface state

```yaml
- name: Collect interface information
  extreme.fe.extreme_fe_interfaces:
    state: gathered
    gather_filter:
      - "1:1"
      - "1:2"
  register: iface_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage interfaces on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current interface state
      extreme.fe.extreme_fe_interfaces:
        state: gathered
      register: ifaces_before

    - name: Disable unused ports
      extreme.fe.extreme_fe_interfaces:
        state: merged
        admin:
          - name: "1:5"
            enabled: false
          - name: "1:6"
            enabled: false

    - name: Configure server uplink
      extreme.fe.extreme_fe_interfaces:
        state: replaced
        config:
          - name: "1:10"
            description: Server uplink
            speed: 1G
            duplex: FULL_DUPLEX
            port_mode: true
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
