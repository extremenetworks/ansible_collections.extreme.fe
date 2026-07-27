# Spanning Tree Protocol (STP)

## Module: extreme.fe.extreme_fe_stp

Manages STP per-port settings on Fabric Engine devices.

---

Version added: 1.1.0

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

This module manages STP per-port settings on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports BPDU Guard, edge port, port priority, path cost, and per-port STP enable/disable.
- Uses `stp_instance` as the top-level scope parameter identifying the STP domain.

---

## [Notes](#table-of-contents)

- BPDU Guard requires STP to be active on the device.
- `stp_instance` is required and identifies the STP domain (use "0" for CIST/RSTP, or "0"-"63" for MSTP instances).
- LAG interfaces are not supported by the REST API; use physical ports in `slot:port` format.
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
| GET | /v0/configuration/stp | Get all STP domain configurations |
| PATCH | /v0/configuration/stp/{stp_name}/ports/{port} | Update per-port STP settings |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `stp_instance` | str | Yes | - | STP instance ("0" for CIST/RSTP, "0"-"63" for MSTP, also accepts "s0" format) |
| `config` | list of dict | No | - | Per-port STP entries |
| `config[].name` | str | Yes | - | Port identifier (`1:5` or `PORT:1:5`) |
| `config[].bpdu_guard_enabled` | bool | No | - | Enable BPDU Guard |
| `config[].recovery_timeout` | int | No | - | BPDU Guard recovery timeout (seconds) |
| `config[].is_edge_port` | bool | No | - | Configure as edge port |
| `config[].priority` | int | No | - | STP port priority |
| `config[].path_cost` | int | No | - | STP path cost |
| `config[].stp_enabled` | bool | No | - | Enable/disable STP on the port |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply STP settings incrementally without removing unspecified values. | GET, PATCH |
| `replaced` | Make supplied values authoritative for listed ports (omitted fields reset to defaults, except `path_cost`). | GET, PATCH |
| `overridden` | Like `replaced` but also resets other ports within the same STP instance to factory defaults (`path_cost` exception applies — see `replaced`). | GET, PATCH |
| `deleted` | Reset STP per-port settings to factory defaults (`path_cost` is left unchanged). | GET, PATCH |
| `gathered` | Read-only — return current STP per-port settings. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `stp.stp_domain` | str | STP domain name used |
| `stp.interfaces` | list | Per-port STP results (name, before, after, differences) |
| `stp.reset_ports` | list | Ports reset during overridden pre-pass |

---

## [Examples](#table-of-contents)

### Enable BPDU Guard on access ports

```yaml
- name: Enable BPDU Guard on ports 1:5 and 1:6
  extreme.fe.extreme_fe_stp:
    state: merged
    stp_instance: "0"
    config:
      - name: "1:5"
        bpdu_guard_enabled: true
        recovery_timeout: 60
      - name: "1:6"
        bpdu_guard_enabled: true
        is_edge_port: true
```

### Replace STP port settings

```yaml
- name: Enforce STP settings on port 1:10
  extreme.fe.extreme_fe_stp:
    state: replaced
    stp_instance: "0"
    config:
      - name: "1:10"
        priority: 64
        stp_enabled: true
        is_edge_port: false
```

### Gather STP configuration

```yaml
- name: Collect STP per-port settings
  extreme.fe.extreme_fe_stp:
    state: gathered
    stp_instance: "0"
  register: stp_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage STP on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current STP settings for CIST
      extreme.fe.extreme_fe_stp:
        state: gathered
        stp_instance: "0"
      register: stp_before

    - name: Enable BPDU Guard on access ports
      extreme.fe.extreme_fe_stp:
        state: merged
        stp_instance: "0"
        config:
          - name: "1:5"
            bpdu_guard_enabled: true
            recovery_timeout: 60
            is_edge_port: true
          - name: "1:6"
            bpdu_guard_enabled: true
            is_edge_port: true

    - name: Set port priority on uplinks
      extreme.fe.extreme_fe_stp:
        state: merged
        stp_instance: "0"
        config:
          - name: "1:1"
            priority: 32
          - name: "1:2"
            priority: 32

    - name: Reset STP settings on ports
      extreme.fe.extreme_fe_stp:
        state: deleted
        stp_instance: "0"
        config:
          - name: "1:5"
          - name: "1:6"
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
