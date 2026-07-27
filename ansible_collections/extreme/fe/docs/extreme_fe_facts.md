# Device Facts

## Module: extreme.fe.extreme_fe_facts

Gathers hardware and system facts from Fabric Engine devices.

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

This module collects state, hardware, interface, configuration, and neighbor facts from Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Optionally gathers structured network resource data for interfaces, VLANs, routing, and other subsystems to support idempotent automation plays.

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
| GET | /v0/state/system | System state (default subset) |
| GET | /v0/state/system/fans | Fan status (hardware subset) |
| GET | /v0/state/system/power-supplies | PSU status (hardware subset) |
| GET | /v1/state/ports | Interface state (interfaces subset) |
| GET | /v0/configuration/system-services | System services (config subset) |
| GET | /v0/state/lldp | LLDP neighbors (neighbors subset) |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `gather_subset` | list of str | No | `[default]` | Fact subsets to collect: `default`, `hardware`, `interfaces`, `config`, `neighbors`, `all` |
| `gather_network_resources` | list of str | No | - | Network resources to collect: `interfaces`, `l2_interfaces`, `l3_interfaces`, `vlans`, `lag_interfaces`, `vrfs`, `static_routes`, `ospfv2`, `vrrp`, `lldp`, `cdp`, `ntp`, `dns`, `snmp_server`, `syslog`, `anycast_gateway`, `isid`, `all` |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Always false — facts gathering does not modify device state |
| `ansible_facts.extreme_fe_facts` | dict | Fact data grouped by subset name |
| `ansible_facts.extreme_fe_facts_network_resources` | dict | Network resource data keyed by resource name |
| `ansible_facts.extreme_fe_facts_gathered_subsets` | list | Subsets that were gathered |
| `ansible_facts.extreme_fe_facts_gathered_network_resources` | list | Network resources that were gathered |

---

## [Examples](#table-of-contents)

### Gather default facts

```yaml
- name: Collect basic device information
  extreme.fe.extreme_fe_facts:
  register: facts
```

### Gather hardware facts

```yaml
- name: Collect hardware inventory
  extreme.fe.extreme_fe_facts:
    gather_subset:
      - hardware
  register: fe_hw
```

### Gather configuration and network resources

```yaml
- name: Collect config and resource data
  extreme.fe.extreme_fe_facts:
    gather_subset:
      - config
      - neighbors
    gather_network_resources:
      - vlans
      - l3_interfaces
  register: device_data
```

### Gather all facts

```yaml
- name: Collect full set of facts
  extreme.fe.extreme_fe_facts:
    gather_subset: [all]
    gather_network_resources: [all]
  register: full_facts
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Gather Fabric Engine facts
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Collect default facts
      extreme.fe.extreme_fe_facts:
      register: device_facts

    - name: Collect hardware and interface facts
      extreme.fe.extreme_fe_facts:
        gather_subset:
          - hardware
          - interfaces
      register: hw_facts

    - name: Collect VLAN and L3 interface resources
      extreme.fe.extreme_fe_facts:
        gather_network_resources:
          - vlans
          - l3_interfaces
      register: resource_facts

    - name: Display device model
      ansible.builtin.debug:
        var: device_facts.ansible_facts.extreme_fe_facts
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
