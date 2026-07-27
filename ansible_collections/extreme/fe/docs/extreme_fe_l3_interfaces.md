# Layer 3 Interfaces

## Module: extreme.fe.extreme_fe_l3_interfaces

Manages Layer 3 interfaces on Fabric Engine devices.

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

This module manages IPv4 and IPv6 addresses on VLAN and loopback interfaces of Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

---

## [Notes](#table-of-contents)

- VLANs and loopbacks must exist prior to invoking this module; creation is out of scope.
- In `state=overridden`, system-protected VLANs (dynamic, management, BROUTER) are skipped with a warning instead of being cleared.
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
| GET | /v0/configuration/vlan | Retrieve all VLANs |
| GET | /v0/configuration/vlan/{vlan_id}/address | Get VLAN addresses |
| PUT | /v0/configuration/vlan/{vlan_id}/address | Update VLAN addresses |
| GET | /v0/configuration/loopback | Retrieve all loopbacks |
| PUT | /v0/configuration/loopback/{id} | Update loopback addresses |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | No | - | Layer 3 interface definitions |
| `config[].name` | str | No | - | Interface identifier (e.g. `VLAN 20`, `Loopback 10`) |
| `config[].type` | str | No | - | Interface type: `vlan` or `loopback` |
| `config[].vlan_id` | int | No | - | VLAN identifier for routed VLAN interfaces |
| `config[].loopback_id` | int | No | - | Loopback identifier |
| `config[].vrf` | str | No | - | VRF name (documentation only) |
| `config[].ipv4` | list of raw | No | - | IPv4 addresses (CIDR strings or dicts) |
| `config[].ipv6` | list of raw | No | - | IPv6 addresses (CIDR strings or dicts) |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Add/update addresses incrementally. | GET, PUT |
| `replaced` | Make supplied addresses authoritative for listed interfaces. | GET, PUT |
| `overridden` | Enforce supplied addresses globally; clear unlisted interfaces. | GET, PUT |
| `deleted` | Remove addresses from listed interfaces. | GET, PUT |
| `gathered` | Read-only — return current L3 interface configuration. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `interfaces` | list | Final L3 interface configuration |
| `before` | list | Interface configuration before changes |
| `after` | list | Interface configuration after changes |
| `differences` | list | Per-interface change details |

---

## [Examples](#table-of-contents)

### Add IPv4 address to a VLAN

```yaml
- name: Ensure VLAN 20 has 10.0.1.101/24
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - vlan_id: 20
        ipv4:
          - 10.0.1.101/24
    state: merged
```

### Replace addresses on a VLAN

```yaml
- name: Replace address list on VLAN 200
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - vlan_id: 200
        ipv4:
          - 10.10.200.1/24
        ipv6:
          - 2001:db8:200::1/64
    state: replaced
```

### Delete addresses from a loopback

```yaml
- name: Clear loopback IPs
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - loopback_id: 5
    state: deleted
```

### Gather L3 interfaces

```yaml
- name: Collect routed interface addressing
  extreme.fe.extreme_fe_l3_interfaces:
    state: gathered
  register: routed_interfaces
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage L3 interfaces on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current L3 interface configuration
      extreme.fe.extreme_fe_l3_interfaces:
        state: gathered
      register: l3_before

    - name: Add IPv4 address to VLAN 20
      extreme.fe.extreme_fe_l3_interfaces:
        config:
          - vlan_id: 20
            ipv4:
              - 10.0.1.101/24
        state: merged

    - name: Replace addresses on VLAN 200
      extreme.fe.extreme_fe_l3_interfaces:
        config:
          - vlan_id: 200
            ipv4:
              - 10.10.200.1/24
            ipv6:
              - 2001:db8:200::1/64
        state: replaced

    - name: Clear loopback addresses
      extreme.fe.extreme_fe_l3_interfaces:
        config:
          - loopback_id: 5
        state: deleted
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
