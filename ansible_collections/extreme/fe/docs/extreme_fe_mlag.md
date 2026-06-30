# Multi-Chassis Link Aggregation Group (MLAG)

## Module: extreme.fe.extreme_fe_mlag

Manages MLAG configuration on Fabric Engine devices.

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

This module manages Multi-switch Link Aggregation (MLAG) configuration on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Configures MLAG peers, ports, and RSMLT (Routed Split Multi-Link Trunking) instances.
- Supports both configuration and state retrieval operations.

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
| GET | /v0/configuration/mlag/peers | List MLAG peers |
| PATCH | /v0/configuration/mlag/peers/{peer_id} | Configure peer |
| PUT | /v0/configuration/mlag/peers/{peer_id}/ports | Configure peer ports |
| GET | /v0/state/mlag/peers | Get peer state |
| GET | /v0/configuration/mlag/rsmlt | Get RSMLT config |
| PATCH | /v0/configuration/mlag/rsmlt/vlan/{vlan_id} | Configure RSMLT instance |
| GET | /v0/state/mlag/rsmlt | Get RSMLT state |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `present` | Operation state: `present`, `absent`, `gathered`, `merged`, `replaced`, `deleted` |
| `config` | dict | No | - | MLAG configuration parameters |
| `config.peers` | list of dict | No | - | List of MLAG peers to configure |
| `config.peers[].peer_id` | str | Yes | - | MLAG peer identifier |
| `config.peers[].peer_ip_address` | str | No | - | IP address of the MLAG peer |
| `config.peers[].local_ip_address` | str | No | - | Local IP address for MLAG communication |
| `config.peers[].local_vlan_id` | int | No | - | Local VLAN ID for MLAG/IST communication |
| `config.peers[].ports` | list of dict | No | - | MLAG ports (MLT IDs) for this peer |
| `config.peers[].ports[].port_id` | str | Yes | - | Port identifier (MLT ID on Fabric Engine devices) |
| `config.rsmlt` | dict | No | - | RSMLT configuration |
| `config.rsmlt.instances` | list of dict | No | - | RSMLT instances |
| `config.rsmlt.instances[].vlan_id` | int | Yes | - | VLAN ID for RSMLT instance |
| `config.rsmlt.instances[].enabled` | bool | No | `true` | Enable/disable RSMLT instance |
| `config.rsmlt.instances[].hold_up_timer` | int | No | `0` | Hold up timer in seconds (0-3600, 9999=infinity) |
| `config.rsmlt.instances[].hold_down_timer` | int | No | `0` | Hold down timer in seconds (0-3600) |
| `gather_filter` | dict | No | - | Filter for gathered information |
| `gather_filter.peer_ids` | list of str | No | - | Peer IDs to gather |
| `gather_filter.include_ports` | bool | No | `true` | Include port information |
| `gather_filter.include_rsmlt` | bool | No | `true` | Include RSMLT information |
| `gather_filter.include_state` | bool | No | `false` | Include state information |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `present` | Create/update MLAG peers and RSMLT instances. | GET, PATCH, PUT |
| `absent` | Remove MLAG configuration. | GET, PATCH, PUT |
| `merged` | Apply MLAG settings incrementally. | GET, PATCH, PUT |
| `replaced` | Make supplied values authoritative for listed peers/RSMLT instances. | GET, PATCH, PUT |
| `deleted` | Remove specified MLAG/RSMLT configuration. | GET, PATCH, PUT |
| `gathered` | Read-only — return current MLAG configuration and optional state. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `before` | dict | Configuration prior to execution |
| `after` | dict | Configuration after execution |
| `commands` | list | REST operations that were executed |
| `gathered` | dict | MLAG facts (gathered state) |

---

## [Examples](#table-of-contents)

### Configure MLAG peer

```yaml
- name: Configure MLAG peer
  extreme.fe.extreme_fe_mlag:
    state: present
    config:
      peers:
        - peer_id: Default
          peer_ip_address: 10.0.0.2
          local_vlan_id: 4000
          ports:
            - port_id: "10"
            - port_id: "11"
```

### Configure RSMLT

```yaml
- name: Configure RSMLT on VLAN 100
  extreme.fe.extreme_fe_mlag:
    state: present
    config:
      rsmlt:
        instances:
          - vlan_id: 100
            enabled: true
            hold_up_timer: 300
```

### Gather MLAG configuration

```yaml
- name: Collect MLAG information
  extreme.fe.extreme_fe_mlag:
    state: gathered
    gather_filter:
      include_ports: true
      include_rsmlt: true
      include_state: true
  register: mlag_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage MLAG on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current MLAG configuration
      extreme.fe.extreme_fe_mlag:
        state: gathered
        gather_filter:
          include_ports: true
          include_rsmlt: true
          include_state: true
      register: mlag_before

    - name: Configure MLAG peer
      extreme.fe.extreme_fe_mlag:
        state: present
        config:
          peers:
            - peer_id: Default
              peer_ip_address: 10.0.0.2
              local_vlan_id: 4000
              ports:
                - port_id: "10"
                - port_id: "11"

    - name: Configure RSMLT on VLAN 100
      extreme.fe.extreme_fe_mlag:
        state: present
        config:
          rsmlt:
            instances:
              - vlan_id: 100
                enabled: true
                hold_up_timer: 300
```

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
