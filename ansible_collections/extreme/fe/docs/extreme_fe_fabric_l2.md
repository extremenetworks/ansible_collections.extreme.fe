# Fabric L2 ISID

## Module: extreme.fe.extreme_fe_fabric_l2

Manages ISIDs on Fabric Engine devices.

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

This module manages Layer 2 ISIDs (service instance identifiers) on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports provisioning CVLAN-backed ISIDs, updating friendly names, gathering existing definitions, and removing bindings.

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
| GET | /v0/configuration/spbm/l2/isid | List all ISIDs |
| GET | /v0/configuration/spbm/l2/isid/{isid} | Get specific ISID |
| POST | /v0/configuration/spbm/l2/isid | Create ISID |
| PATCH | /v0/configuration/spbm/l2/isid/{isid} | Update ISID name |
| DELETE | /v0/configuration/spbm/l2/isid/{isid}/cvlan/{cvlan} | Delete ISID binding |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | No | - | ISID definitions |
| `config[].isid` | int | Yes | - | ISID number |
| `config[].name` | str | No | - | Friendly name for the ISID |
| `config[].cvlan` | int | No | - | CVLAN ID to bind |
| `config[].isid_type` | str | No | `CVLAN` | ISID type |
| `gather_filter` | list of int | No | - | Limit gathered output to these ISID numbers |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create ISIDs that don't exist; update name on existing. | GET, POST, PATCH |
| `replaced` | Make supplied ISID definitions authoritative. | GET, POST, PATCH, DELETE |
| `overridden` | Enforce exact set of ISIDs; delete unlisted. | GET, POST, PATCH, DELETE |
| `deleted` | Delete specified ISID bindings. | GET, DELETE |
| `gathered` | Read-only — return current ISID definitions. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `isids` | list | Per-ISID results (before/after state) |
| `deleted_isids` | list | ISIDs deleted by overridden state |
| `skipped_isids` | list | ISIDs that could not be deleted |
| `gathered` | list | ISID entries from the device (gathered) |

---

## [Examples](#table-of-contents)

### Create an ISID

```yaml
- name: Create ISID 500 on VLAN 500
  extreme.fe.extreme_fe_fabric_l2:
    state: merged
    config:
      - isid: 500
        name: Campus-500
        cvlan: 500
```

### Delete an ISID

```yaml
- name: Remove ISID 700 binding
  extreme.fe.extreme_fe_fabric_l2:
    state: deleted
    config:
      - isid: 700
        cvlan: 700
```

### Gather ISIDs

```yaml
- name: Collect ISID information
  extreme.fe.extreme_fe_fabric_l2:
    state: gathered
  register: isid_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage ISIDs on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current ISIDs
      extreme.fe.extreme_fe_fabric_l2:
        state: gathered
      register: isids_before

    - name: Create Campus ISID
      extreme.fe.extreme_fe_fabric_l2:
        state: merged
        config:
          - isid: 500
            name: Campus-500
            cvlan: 500

    - name: Override ISIDs (remove unlisted)
      extreme.fe.extreme_fe_fabric_l2:
        state: overridden
        config:
          - isid: 500
            name: Campus-500
            cvlan: 500
          - isid: 600
            name: Server-600
            cvlan: 600

    - name: Remove specific ISID binding
      extreme.fe.extreme_fe_fabric_l2:
        state: deleted
        config:
          - isid: 600
            cvlan: 600
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
