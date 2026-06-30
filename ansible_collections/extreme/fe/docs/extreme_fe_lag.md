# Link Aggregation Group (LAG)

## Module: extreme.fe.extreme_fe_lag

Manages LAG configuration on Fabric Engine devices.

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

Through this module, Link Aggregation Groups (LAGs) can be created and deleted on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- The module updates LAG attributes such as friendly names, load balancing algorithms, and LACP keys.
- Adds or removes member ports through the Fabric Engine LAG REST endpoints.

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
| GET | /v0/configuration/lag | List all LAGs |
| GET | /v0/configuration/lag/{lag_id} | Get LAG config |
| POST | /v0/configuration/lag | Create LAG |
| PATCH | /v0/configuration/lag/{lag_id} | Update LAG attributes |
| DELETE | /v0/configuration/lag/{lag_id} | Delete LAG |
| POST | /v0/configuration/lag/{lag_id}/memberPorts | Add member ports |
| DELETE | /v0/configuration/lag/{lag_id}/memberPorts/{port} | Remove member port |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `lag_id` | raw | Yes | - | LAG identifier |
| `name` | str | No | - | Friendly name for the LAG |
| `mode` | str | No | - | Aggregation mode: `STATIC`, `LACP`, or `VLACP` |
| `lacp_key` | str | No | - | LACP key for the LAG |
| `load_balance_algo` | str | No | - | Load balancing algorithm: `L2`, `L3`, `L3_L4`, `CUSTOM`, `PORT` |
| `member_ports` | list of str | No | - | Authoritative list of member ports |
| `add_member_ports` | list of str | No | - | Ports to add to the LAG |
| `remove_member_ports` | list of str | No | - | Ports to remove from the LAG |
| `purge_member_ports` | bool | No | `false` | Remove ports not in `member_ports` |
| `gather_filter` | list of str | No | - | Limit gathered output to these LAG IDs |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create LAG if missing; add/update attributes and members incrementally. | GET, POST, PATCH, DELETE |
| `replaced` | Make supplied attributes and members authoritative for the LAG. | GET, POST, PATCH, DELETE |
| `overridden` | Like `replaced`; removes unlisted member ports. | GET, POST, PATCH, DELETE |
| `deleted` | Delete the LAG entirely or remove specified members. | GET, DELETE |
| `gathered` | Read-only — return current LAG configuration. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `lag` | dict | Resulting LAG configuration |
| `lag_removed` | dict | LAG configuration that was deleted |
| `member_additions` | list | Ports that were added |
| `member_removals` | list | Ports that were removed |
| `lags` | list | LAG configurations (gathered) |

---

## [Examples](#table-of-contents)

### Create a LAG with member ports

```yaml
- name: Create LAG 10 with member ports
  extreme.fe.extreme_fe_lag:
    state: merged
    lag_id: 10
    name: Core-Uplink
    mode: LACP
    member_ports:
      - "1:1"
      - "1:2"
```

### Add ports to existing LAG

```yaml
- name: Add port to LAG 10
  extreme.fe.extreme_fe_lag:
    state: merged
    lag_id: 10
    add_member_ports:
      - "1:3"
```

### Delete a LAG

```yaml
- name: Remove LAG 10
  extreme.fe.extreme_fe_lag:
    state: deleted
    lag_id: 10
```

### Gather LAG configuration

```yaml
- name: Collect LAG information
  extreme.fe.extreme_fe_lag:
    state: gathered
  register: lag_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage LAGs on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current LAGs
      extreme.fe.extreme_fe_lag:
        state: gathered
      register: lags_before

    - name: Create core uplink LAG
      extreme.fe.extreme_fe_lag:
        state: merged
        lag_id: 10
        name: Core-Uplink
        mode: LACP
        member_ports:
          - "1:1"
          - "1:2"

    - name: Delete unused LAG
      extreme.fe.extreme_fe_lag:
        state: deleted
        lag_id: 20
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
