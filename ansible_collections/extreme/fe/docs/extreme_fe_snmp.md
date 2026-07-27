# Simple Network Management Protocol (SNMP)

## Module: extreme.fe.extreme_fe_snmp

Manage the SNMP system name on Fabric Engine devices.

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

This module manages the SNMP system name (`sysName`) on Fabric Engine devices via the REST API endpoints exposed through the OpenAPI Server.

- The system name is a singleton resource — exactly one per device.
- An empty string clears the system name.

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
| GET | /v1/configuration/snmp | Read current SNMP settings (falls back to /v0 if v1 returns no data) |
| PATCH | /v0/configuration/snmp | Update SNMP system name |

---

## [Platform Constraints](#table-of-contents)

- System name: 0–255 characters.
- Only `sysName` is managed by this module; other SNMP fields are not modified.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | dict | Yes (merged/replaced/overridden) | — | SNMP config |
| `config.name` | str | Yes (non-deleted states) | — | SNMP system name (0–255 chars) |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Set system name if it differs from current value. | GET, PATCH |
| `replaced` | Same as merged for this singleton. | GET, PATCH |
| `overridden` | Same as merged for this singleton. | GET, PATCH |
| `deleted` | Clear system name (reset to empty string). | GET, PATCH |
| `gathered` | Read-only — return current system name. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether the system name was modified |
| `snmp.before` | dict | SNMP config before changes |
| `snmp.after` | dict | SNMP config after changes |
| `snmp.config` | dict | Current SNMP config (gathered state) |
| `snmp.differences` | dict | Fields that differ between before and after |
| `api_responses` | dict | Raw REST API responses |


---

## [Examples](#table-of-contents)

### Set system name

```yaml
- name: Set system name
  extreme.fe.extreme_fe_snmp:
    state: merged
    config:
      name: "my-switch-01"
```

### Replace system name

```yaml
- name: Replace system name
  extreme.fe.extreme_fe_snmp:
    state: replaced
    config:
      name: "new-switch-name"
```

### Clear system name

```yaml
- name: Clear system name
  extreme.fe.extreme_fe_snmp:
    state: deleted
```

### Gather current system name

```yaml
- name: Gather current system name
  extreme.fe.extreme_fe_snmp:
    state: gathered
  register: snmp_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage SNMP system name
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current SNMP system name
      extreme.fe.extreme_fe_snmp:
        state: gathered
      register: snmp_before

    - name: Set SNMP system name
      extreme.fe.extreme_fe_snmp:
        state: merged
        config:
          name: "my-switch-01"

    - name: Replace SNMP system name
      extreme.fe.extreme_fe_snmp:
        state: replaced
        config:
          name: "new-switch-name"

    - name: Clear SNMP system name
      extreme.fe.extreme_fe_snmp:
        state: deleted

    - name: Gather SNMP system name after changes
      extreme.fe.extreme_fe_snmp:
        state: gathered
      register: snmp_after
```

---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
