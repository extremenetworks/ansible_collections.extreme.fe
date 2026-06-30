# Power over Ethernet (PoE)

## Module: extreme.fe.extreme_fe_poe

Manages operations related to device power and port power configuration and retrieval on Fabric Engine devices.

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

This module retrieves and configures Power over Ethernet (PoE) settings for copper ports on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

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
| GET | /v0/state/capabilities/system/ports | Get port capabilities (PoE detection) |
| GET | /v0/configuration/poe-power/ports/{port} | Get PoE configuration |
| PATCH | /v0/configuration/poe-power/ports/{port} | Update PoE configuration |
| GET | /v0/state/poe-power/ports/{port} | Get PoE runtime state |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | No | - | Per-port PoE configuration |
| `config[].port` | str | Yes | - | Port identifier (slot:port) |
| `config[].enable` | bool | No | - | Enable/disable PoE on the port |
| `config[].power_limit` | int | No | - | Power limit in milliwatts |
| `config[].priority` | str | No | - | PoE priority: `LOW`, `HIGH`, `CRITICAL` |
| `config[].perpetual_poe` | bool | No | - | Enable Perpetual PoE |
| `config[].fast_poe` | bool | No | - | Enable Fast PoE |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply PoE settings incrementally on listed ports. | GET, PATCH |
| `replaced` | Make supplied values authoritative for listed ports. | GET, PATCH |
| `overridden` | Enforce supplied PoE config globally across all PoE-capable ports. | GET, PATCH |
| `deleted` | Reset PoE settings to device defaults on listed ports. | GET, PATCH |
| `gathered` | Read-only — return current PoE configuration and state. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `ports` | list | Per-port PoE details (config, state, differences) |
| `submitted` | dict | Operations submitted when changes were required |

---

## [Examples](#table-of-contents)

### Enable PoE on a port

```yaml
- name: Enable PoE with power limit on port 1:10
  extreme.fe.extreme_fe_poe:
    state: merged
    config:
      - port: "1:10"
        enable: true
        power_limit: 42000
        priority: HIGH
```

### Disable PoE on ports

```yaml
- name: Disable PoE on unused ports
  extreme.fe.extreme_fe_poe:
    state: deleted
    config:
      - port: "1:5"
      - port: "1:6"
```

### Gather PoE configuration

```yaml
- name: Collect PoE settings and state
  extreme.fe.extreme_fe_poe:
    state: gathered
  register: poe_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage PoE on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current PoE configuration
      extreme.fe.extreme_fe_poe:
        state: gathered
      register: poe_before

    - name: Enable PoE on access ports
      extreme.fe.extreme_fe_poe:
        state: merged
        config:
          - port: "1:10"
            enable: true
            power_limit: 42000
            priority: HIGH
          - port: "1:11"
            enable: true
            power_limit: 30000

    - name: Override PoE configuration globally
      extreme.fe.extreme_fe_poe:
        state: overridden
        config:
          - port: "1:10"
            enable: true
            power_limit: 42000
          - port: "1:11"
            enable: true
            power_limit: 30000

    - name: Reset PoE on unused ports
      extreme.fe.extreme_fe_poe:
        state: deleted
        config:
          - port: "1:5"
          - port: "1:6"
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
