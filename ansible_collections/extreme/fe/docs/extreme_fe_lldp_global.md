# Link Layer Discovery Protocol (LLDP) - Global Settings

## Module: extreme.fe.extreme_fe_lldp_global

Manages global LLDP settings on Fabric Engine devices.

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

This module manages device-wide LLDP timer settings on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

---

## [Notes](#table-of-contents)

- `overridden` is functionally equivalent to `replaced` because LLDP global is a singleton.
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
| GET | /v0/configuration/lldp | Get global LLDP configuration |
| PATCH | /v0/configuration/lldp | Update global LLDP configuration |
| GET | /v0/state/lldp | Get LLDP operational state |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | dict | No | - | Global LLDP configuration |
| `config.advertisement_interval` | int | No | - | LLDP advertisement interval in seconds |
| `config.hold_multiplier` | int | No | - | Multiplier for TTL calculation |
| `gather_state` | bool | No | `false` | Include LLDP operational state |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply provided timer settings incrementally. | GET, PATCH |
| `replaced` | Make supplied values authoritative for global LLDP config. | GET, PATCH |
| `overridden` | Same as `replaced` (singleton resource). | GET, PATCH |
| `deleted` | Reset supplied attributes to device defaults; all if `config` omitted. | GET, PATCH |
| `gathered` | Read-only — return current global LLDP configuration. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `lldp.before` | dict | LLDP config before changes |
| `lldp.after` | dict | LLDP config after changes |
| `lldp.config` | dict | Current LLDP config (gathered) |
| `lldp.differences` | dict | Changed attributes with before/after values |
| `lldp.state` | dict | LLDP operational state |
| `submitted` | dict | Payload submitted to the device |
| `api_responses` | dict | Raw API responses |

---

## [Examples](#table-of-contents)

### Update LLDP timers

```yaml
- name: Set LLDP advertisement interval
  extreme.fe.extreme_fe_lldp_global:
    state: merged
    config:
      advertisement_interval: 60
      hold_multiplier: 4
```

### Reset LLDP to defaults

```yaml
- name: Reset all LLDP timer settings
  extreme.fe.extreme_fe_lldp_global:
    state: deleted
```

### Gather LLDP configuration

```yaml
- name: Collect LLDP global settings
  extreme.fe.extreme_fe_lldp_global:
    state: gathered
    gather_state: true
  register: lldp_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage global LLDP on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current LLDP settings
      extreme.fe.extreme_fe_lldp_global:
        state: gathered
        gather_state: true
      register: lldp_before

    - name: Set LLDP advertisement interval and hold multiplier
      extreme.fe.extreme_fe_lldp_global:
        state: merged
        config:
          advertisement_interval: 60
          hold_multiplier: 4

    - name: Reset all LLDP timer settings to defaults
      extreme.fe.extreme_fe_lldp_global:
        state: deleted
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
