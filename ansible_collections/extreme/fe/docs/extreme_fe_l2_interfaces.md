# Layer 2 Interfaces

## Module: extreme.fe.extreme_fe_l2_interfaces

Manages L2 interface settings on Fabric Engine devices.

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

- This module manages L2 interface settings on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.
- Supports VLAN membership (access/trunk mode, tagged/untagged VLANs) on one or more interfaces per task.

---

## [Notes](#table-of-contents)

- When `state=overridden`, the module resets interfaces not listed in `config` to device defaults; `config` must not be empty.
- Interfaces that cannot be reset during overridden (e.g., LACP LAGs) are skipped with a warning and returned in `skipped_interfaces`.
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
| GET | /v0/configuration/vlan/interfaces | Retrieve all interface VLAN settings |
| GET | /v0/configuration/vlan/interfaces/type/{type}/name/{name} | Get specific interface |
| PUT | /v0/configuration/vlan/interfaces/type/{type}/name/{name} | Update interface VLAN settings |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | No | - | L2 interface definitions |
| `config[].name` | str | Yes | - | Interface identifier (`1:5`, `PORT:1:5`, or `LAG:10`) |
| `config[].port_type` | str | No | - | VLAN mode: `ACCESS` or `TRUNK` |
| `config[].untagged_vlan` | int | No | - | VLAN ID for untagged traffic (0 to clear) |
| `config[].tagged_vlans` | list of int | No | - | Authoritative list of tagged VLANs |
| `config[].add_tagged_vlans` | list of int | No | - | VLANs to add (merged only) |
| `config[].remove_tagged_vlans` | list of int | No | - | VLANs to remove (merged/deleted only) |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply provided parameters incrementally without removing unspecified membership. | GET, PUT |
| `replaced` | Make supplied values authoritative for each listed interface. | GET, PUT |
| `overridden` | Like `replaced` but also resets unlisted interfaces to defaults. | GET, PUT |
| `deleted` | Remove tagged VLAN membership; reset all if no parameters given. | GET, PUT |
| `gathered` | Read-only — return current VLAN membership. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `interfaces` | list | Per-interface results (name, before, after, differences, changed) |
| `reset_interfaces` | list | Interfaces reset to defaults during overridden |
| `skipped_interfaces` | list | Interfaces that could not be reset (e.g. LACP LAGs) |

---

## [Examples](#table-of-contents)

### Configure access port

```yaml
- name: Set access port on interface 1:5
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:5"
        port_type: ACCESS
        untagged_vlan: 5
    state: replaced
```

### Configure trunk ports

```yaml
- name: Ensure trunk membership on two ports
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:10"
        port_type: TRUNK
        untagged_vlan: 1
        tagged_vlans: [5, 6]
      - name: "1:11"
        port_type: TRUNK
        untagged_vlan: 1
        tagged_vlans: [7, 8]
    state: replaced
```

### Add tagged VLANs incrementally

```yaml
- name: Add VLAN 20 to port 1:7
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:7"
        add_tagged_vlans: [20]
    state: merged
```

### Gather L2 interface settings

```yaml
- name: Collect all L2 interface settings
  extreme.fe.extreme_fe_l2_interfaces:
    state: gathered
  register: l2_config
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage L2 interfaces on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current L2 interface settings
      extreme.fe.extreme_fe_l2_interfaces:
        state: gathered
      register: l2_before

    - name: Configure access port
      extreme.fe.extreme_fe_l2_interfaces:
        config:
          - name: "1:5"
            port_type: ACCESS
            untagged_vlan: 5
        state: replaced

    - name: Configure trunk ports
      extreme.fe.extreme_fe_l2_interfaces:
        config:
          - name: "1:10"
            port_type: TRUNK
            untagged_vlan: 1
            tagged_vlans: [100, 200]
        state: replaced

    - name: Add tagged VLANs to a port
      extreme.fe.extreme_fe_l2_interfaces:
        config:
          - name: "1:7"
            add_tagged_vlans: [20, 30]
        state: merged
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
