# Anycast Gateway

## Module: extreme.fe.extreme_fe_anycast_gateway

Manages Anycast Gateway interfaces on Fabric Engine devices.

---

Version added: 1.2.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Platform Constraints](#platform-constraints)
- [Parameters](#parameters)
- [State Behaviour Summary](#state-behaviour-summary)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

This module manages Anycast Gateway interfaces on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Resource identifier is `vlan_id`.
- Create-time fields are immutable after creation: `ip_address`, `mask_length`, `one_ip`, `vr_id`.
- The only updatable field on an existing interface is `enabled`.

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
| GET | /v0/configuration/anycast-gateway/interfaces | List all Anycast Gateway interfaces |
| POST | /v0/configuration/anycast-gateway/vlan/{vlan_id} | Create Anycast Gateway interface |
| PATCH | /v0/configuration/anycast-gateway/vlan/{vlan_id}/interface | Update interface (enabled only) |
| DELETE | /v0/configuration/anycast-gateway/vlan/{vlan_id} | Delete interface |
| GET | /v0/state/anycast-gateway/interfaces | Read operational interface state |

---

## [Platform Constraints](#table-of-contents)

- `vlan_id` range: 1-4094.
- `mask_length` can only be set when `one_ip=true`.
- Once created, immutable fields require delete + re-create to change.
- Module auto-disables interface before delete, as required by Fabric Engine devices.
- IPv6 Anycast is not supported by current firmware.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | Yes (merged/replaced/overridden) | - | Anycast interface config list |
| `config[].vlan_id` | int | Yes | - | VLAN ID (resource key) |
| `config[].ip_address` | str | No | - | IPv4 Anycast address (immutable) |
| `config[].mask_length` | int | No | - | IPv4 mask length (immutable) |
| `config[].one_ip` | bool | No | - | ONE-IP mode (immutable) |
| `config[].vr_id` | int | No | - | Virtual Router ID (immutable) |
| `config[].enabled` | bool | No | - | Interface admin state (patchable) |
| `gather_filter` | list of int | No | - | Limit gathered output to selected VLAN IDs |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create missing interfaces, patch `enabled` on existing interfaces. | GET, POST, PATCH |
| `replaced` | Reconcile listed interfaces; recreate (DELETE + POST) when immutable fields differ. | GET, DELETE, POST, PATCH |
| `overridden` | Delete unlisted interfaces, then apply `replaced` logic. | GET, DELETE, POST, PATCH |
| `deleted` | Delete listed interfaces; delete all if `config` omitted. | GET, DELETE, PATCH |
| `gathered` | Read-only output. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any interface was modified |
| `before` | list of dict | Interface config before changes |
| `after` | list of dict | Interface config after changes |
| `gathered` | list of dict | Gathered Anycast interface configuration |
| `anycast_gateways` | list of dict | Per-resource operation results |
| `api_responses` | dict | Raw REST API responses |

---

## [Examples](#table-of-contents)

### Gather interface state

```yaml
- name: Gather current Anycast Gateway configuration
  extreme.fe.extreme_fe_anycast_gateway:
    state: gathered
```

### Create interface

```yaml
- name: Create Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: merged
    config:
      - vlan_id: 100
        ip_address: 10.10.10.1
        mask_length: 24
        one_ip: true
        enabled: true
```

### Replace interface config

```yaml
- name: Replace Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: replaced
    config:
      - vlan_id: 100
        ip_address: 10.10.10.254
        mask_length: 24
        one_ip: true
        enabled: true
```

### Delete interfaces

```yaml
- name: Delete Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: deleted
    config:
      - vlan_id: 100

- name: Delete all Anycast GW interfaces
  extreme.fe.extreme_fe_anycast_gateway:
    state: deleted
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.


```yaml
- name: Manage Anycast Gateway interfaces
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current Anycast Gateway configuration
      extreme.fe.extreme_fe_anycast_gateway:
        state: gathered

    - name: Create Anycast GW on VLAN 100 (ONE-IP)
      extreme.fe.extreme_fe_anycast_gateway:
        state: merged
        config:
          - vlan_id: 100
            ip_address: 10.10.10.1
            mask_length: 24
            one_ip: true
            enabled: true

    - name: Replace Anycast GW on VLAN 100
      extreme.fe.extreme_fe_anycast_gateway:
        state: replaced
        config:
          - vlan_id: 100
            ip_address: 10.10.10.254
            mask_length: 24
            one_ip: true
            enabled: true

    - name: Override all Anycast GW interfaces
      extreme.fe.extreme_fe_anycast_gateway:
        state: overridden
        config:
          - vlan_id: 100
            ip_address: 10.10.10.1
            mask_length: 24
            one_ip: true
            enabled: true

    - name: Delete Anycast GW on VLAN 100
      extreme.fe.extreme_fe_anycast_gateway:
        state: deleted
        config:
          - vlan_id: 100

    - name: Delete all Anycast GW interfaces
      extreme.fe.extreme_fe_anycast_gateway:
        state: deleted
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
