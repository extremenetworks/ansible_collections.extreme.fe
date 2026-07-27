# Virtual LANs (VLANs)

## Module: extreme.fe.extreme_fe_vlans

Manages VLANs on Fabric Engine devices.

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

This module manages VLANs on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports creating VLANs, ensuring LAG/ISIS membership, deleting VLANs, and collecting VLAN facts.

---

## [Notes](#table-of-contents)

- Use `extreme_fe_fabric_l2` to manage ISID to VLAN associations.
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
| GET | /v0/configuration/vlan/{vlan_id} | Retrieve specific VLAN |
| POST | /v0/configuration/vrf/{vr_name}/vlan | Create VLAN |
| PATCH | /v0/configuration/vlan/{vlan_id} | Update VLAN |
| DELETE | /v0/configuration/vrf/{vr_name}/vlan/{vlan_id} | Delete VLAN |
| POST | /v0/operation/vlan/{vlan_id}/interfaces/:add | Add interface membership |
| POST | /v0/operation/vlan/{vlan_id}/interfaces/:remove | Remove interface membership |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `vlan_id` | int | No | - | VLAN identifier (1-4094) |
| `vlan_name` | str | No | - | Friendly name for the VLAN |
| `vlan_type` | str | No | `PORT_MSTP_RSTP` | VLAN type identifier |
| `stp_name` | str | No | - | Auto-bind STP instance name |
| `vr_name` | str | No | `GlobalRouter` | Virtual router context |
| `gather_filter` | list of int | No | - | Limit gathered VLAN facts to these VLAN IDs |
| `lag_interfaces` | list of dict | No | - | LAG memberships to add to the VLAN |
| `lag_interfaces[].name` | str | Yes | - | LAG identifier |
| `lag_interfaces[].tag` | str | No | `tagged` | `tagged` or `untagged` |
| `remove_lag_interfaces` | list of dict | No | - | LAG memberships to remove |
| `remove_lag_interfaces[].name` | str | Yes | - | LAG identifier |
| `remove_lag_interfaces[].tag` | str | No | `tagged` | `tagged` or `untagged` |
| `isis_logical_interfaces` | list of dict | No | - | ISIS logical interfaces to add |
| `isis_logical_interfaces[].name` | str | Yes | - | ISIS logical interface identifier |
| `isis_logical_interfaces[].tag` | str | No | `tagged` | `tagged` or `untagged` |
| `remove_isis_logical_interfaces` | list of dict | No | - | ISIS logical interfaces to remove |
| `remove_isis_logical_interfaces[].name` | str | Yes | - | ISIS logical interface identifier |
| `remove_isis_logical_interfaces[].tag` | str | No | `tagged` | `tagged` or `untagged` |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create VLAN if missing; add memberships incrementally. | GET, POST, PATCH |
| `replaced` | Make supplied memberships authoritative for the VLAN. | GET, POST, PATCH |
| `overridden` | Clear memberships not provided while applying supplied definitions. | GET, POST, PATCH, DELETE |
| `deleted` | Remove the VLAN from the device. | GET, DELETE |
| `gathered` | Read-only output. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `vlan` | dict | VLAN details when applying configuration changes |
| `vlans` | list | List of VLAN data when state is gathered |

---

## [Examples](#table-of-contents)

### Create or update VLAN with LAG membership

```yaml
- name: Ensure VLAN 20 exists with core LAG membership
  extreme.fe.extreme_fe_vlans:
    state: merged
    vlan_id: 20
    vlan_name: Campus-20
    vr_name: GlobalRouter
    lag_interfaces:
      - name: "10"
        tag: tagged
```

### Delete a VLAN

```yaml
- name: Remove VLAN 200
  extreme.fe.extreme_fe_vlans:
    state: deleted
    vlan_id: 200
    vr_name: GlobalRouter
```

### Gather VLAN configuration

```yaml
- name: Collect VLAN information
  extreme.fe.extreme_fe_vlans:
    state: gathered
    gather_filter: [20, 200]
  register: vlan_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage VLANs on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current VLAN configuration
      extreme.fe.extreme_fe_vlans:
        state: gathered
      register: vlans_before

    - name: Create Campus VLAN with LAG membership
      extreme.fe.extreme_fe_vlans:
        state: merged
        vlan_id: 20
        vlan_name: Campus-20
        vr_name: GlobalRouter
        lag_interfaces:
          - name: "10"
            tag: tagged

    - name: Replace VLAN membership
      extreme.fe.extreme_fe_vlans:
        state: replaced
        vlan_id: 200
        vr_name: GlobalRouter
        lag_interfaces:
          - name: "10"
            tag: tagged

    - name: Remove a VLAN
      extreme.fe.extreme_fe_vlans:
        state: deleted
        vlan_id: 200
        vr_name: GlobalRouter
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
