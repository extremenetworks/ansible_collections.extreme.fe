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
- An unset system name is reported as an empty string in `gathered`, `before` and `after`.
- Supports check mode and diff mode (`--diff`).

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- **System name only:** the module manages the switch's SNMP system name. An unset name is shown as `""`; clear it with `deleted` or with `name: ""`.
- **Secrets are never returned:** SNMP community strings and SNMPv3 passwords are removed from every result and error message.
- **Lost connections:** if the connection drops while the name is being written, the task reports `changed: true` with `details.outcome: unknown`, because the change may have been applied. Run the task again to make sure.
- **`changed` on failure:** a task that fails after the name was written reports `changed: true`.
- Supports check mode (`--check`) and diff mode (`--diff`).

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
| `before` | dict | SNMP config before the task (action states) |
| `after` | dict | SNMP config after the task, equal to `before` when nothing changed; the predicted state in check mode (action states) |
| `diff` | dict | `before` and `after`, in diff mode (`--diff`) |
| `gathered` | dict | Current SNMP config (`state: gathered`). An unset system name is `""`, so the result can be applied back as `config` |
| `snmp.config` | dict | Current SNMP config (gathered state) |
| `snmp.differences` | dict | Fields that differ between before and after |
| `api_responses` | dict | REST API responses, for debugging, with every secret value removed (SNMP community strings, SNMPv3 authentication and encryption passwords; non-secret siblings such as `isEncrypted` are kept). The secret values read from the device are also removed from every message text of a response, and the error text of a failed read is replaced by a generic text wherever it appears in the response (top level, list entries and nested wrappers), and so is a bare text answer or a bare text entry of an array answer or wrapper (an array of strings inside the configuration, such as `view[].oids`, is kept), with the status codes kept. **Deprecated**, will be removed in 2.0.0 - use `snmp.before` and `snmp.after` for the configuration before and after a change, and `gathered` or `snmp.config` for `state: gathered` |


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
