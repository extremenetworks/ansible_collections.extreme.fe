# Link Layer Discovery Protocol (LLDP) - Interface Settings

## Module: extreme.fe.extreme_fe_lldp_interfaces

Manages LLDP interface settings on Fabric Engine devices.

---

Version added: 1.0.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Parameters](#parameters)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

This module manages LLDP interface-level settings on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports LLDP transmit/receive control, advertised TLVs, location data, and MED network policy entries.

---

## [Notes](#table-of-contents)

- On Fabric Engine, `transmit_enabled` and `receive_enabled` must use the same value; if only one is supplied, the module mirrors it to the other.
- If LLDP transmit or receive is disabled, the device ignores advertisement/location attributes in the same request; the module submits only the basic LLDP enable flags in that case.
- When `med_policy` is supplied, it is treated as the authoritative list for that interface because the device API replaces the full MED policy list.
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
| GET | /v0/configuration/lldp | Get all LLDP port configurations |
| PUT | /v0/configuration/lldp/ports/{port} | Configure LLDP on port |
| PUT | /v0/configuration/lldp/ports/{port}/med-policy | Configure MED policy |
| GET | /v0/state/lldp/ports/{port} | Get LLDP neighbor state |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `interfaces` | list of dict | No | - | Per-port LLDP settings |
| `interfaces[].name` | str | Yes | - | Port identifier (slot:port) |
| `interfaces[].transmit_enabled` | bool | No | - | Enable LLDP transmit |
| `interfaces[].receive_enabled` | bool | No | - | Enable LLDP receive |
| `interfaces[].advertise` | dict | No | - | TLVs to advertise |
| `interfaces[].advertise.system_capabilities` | bool | No | - | Advertise system capabilities |
| `interfaces[].advertise.system_description` | bool | No | - | Advertise system description |
| `interfaces[].advertise.system_name` | bool | No | - | Advertise system name |
| `interfaces[].advertise.port_description` | bool | No | - | Advertise port description |
| `interfaces[].advertise.management_address` | bool | No | - | Advertise management address |
| `interfaces[].advertise.med_capabilities` | bool | No | - | Advertise MED capabilities |
| `interfaces[].advertise.med_power` | bool | No | - | Advertise MED power |
| `interfaces[].advertise.dot3_mac_phy` | bool | No | - | Advertise 802.3 MAC/PHY |
| `interfaces[].advertise.location` | bool | No | - | Advertise MED location |
| `interfaces[].advertise.network_policy` | bool | No | - | Advertise MED network policy |
| `interfaces[].advertise.inventory` | bool | No | - | Advertise MED inventory |
| `interfaces[].location` | dict | No | - | LLDP-MED location data |
| `interfaces[].location.civic_address` | str | No | - | Civic address |
| `interfaces[].location.ecs_elin` | str | No | - | ELIN identifier |
| `interfaces[].location.coordinate` | str | No | - | Geographic coordinate |
| `interfaces[].med_policy` | list of dict | No | - | MED network policies (authoritative list) |
| `interfaces[].med_policy[].type` | str | Yes | - | Policy type: `VOICE`, `VOICE_SIGNALING`, `GUEST_VOICE`, `GUEST_VOICE_SIGNALING`, `SOFT_PHONE_VOICE`, `VIDEO_CONFERENCING`, `STREAMING_VIDEO`, `VIDEO_SIGNALING` |
| `interfaces[].med_policy[].dscp` | int | Yes | - | DSCP value |
| `interfaces[].med_policy[].priority` | int | Yes | - | 802.1p priority |
| `interfaces[].med_policy[].tagged` | bool | Yes | - | Whether traffic is tagged |
| `interfaces[].med_policy[].vlan_id` | int | Yes | - | VLAN ID |
| `gather_filter` | list of str | No | - | Limit gathered output to these ports |
| `gather_state` | bool | No | `false` | Include LLDP neighbor state |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `interfaces_settings` | list | Normalized LLDP settings per interface |
| `interface_updates` | list | Interfaces updated during the run |
| `interface_removals` | list | Interfaces reset to defaults |
| `interfaces_state` | list | LLDP operational state per interface |
| `api_responses` | dict | Raw API responses |

---

## [Examples](#table-of-contents)

### Enable LLDP on a port with advertisements

```yaml
- name: Enable LLDP on port 1:5
  extreme.fe.extreme_fe_lldp_interfaces:
    state: merged
    interfaces:
      - name: "1:5"
        transmit_enabled: true
        receive_enabled: true
```

### Configure MED policy

```yaml
- name: Set MED policy on port 1:10
  extreme.fe.extreme_fe_lldp_interfaces:
    state: replaced
    interfaces:
      - name: "1:10"
        transmit_enabled: true
        receive_enabled: true
        med_policy:
          - type: VOICE
            dscp: 46
            priority: 5
            tagged: true
            vlan_id: 100
```

### Gather LLDP interface settings

```yaml
- name: Collect LLDP interface settings with neighbor state
  extreme.fe.extreme_fe_lldp_interfaces:
    state: gathered
    gather_state: true
  register: lldp_ports
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage LLDP interfaces on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current LLDP interface settings
      extreme.fe.extreme_fe_lldp_interfaces:
        state: gathered
        gather_state: true
      register: lldp_before

    - name: Enable LLDP on access ports
      extreme.fe.extreme_fe_lldp_interfaces:
        state: merged
        interfaces:
          - name: "1:5"
            transmit_enabled: true
            receive_enabled: true
          - name: "1:6"
            transmit_enabled: true
            receive_enabled: true

    - name: Reset LLDP on unused ports
      extreme.fe.extreme_fe_lldp_interfaces:
        state: deleted
        interfaces:
          - name: "1:7"
          - name: "1:8"
```

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
