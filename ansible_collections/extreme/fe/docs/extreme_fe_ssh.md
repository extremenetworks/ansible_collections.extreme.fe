# Secure Shell (SSH) Service

## Module: extreme.fe.extreme_fe_ssh

Manages the SSH service flags on Fabric Engine devices.

---

Version added: 1.3.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Platform Constraints](#platform-constraints)
- [Parameters](#parameters)
- [State Behaviour Summary](#state-behaviour-summary)
- [Factory Defaults](#factory-defaults)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

This module manages the SSH service flags on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports the Ansible states: merged, replaced, overridden, deleted and gathered.
- Manages only `enabled` and `global_enabled` under the `ssh` object of the System Services configuration.
- Every other System Services field (`telnet`, `ftp`, `iqagent`, `webServer`, `cloudConnector`, `vxlanGwFullInterworkingMode`) is out of scope for this module and is never read or written by it.
- The REST API exposes `PATCH` for System Services, so only the `ssh` object, and only the field(s) that changed, are ever sent in the request body.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- **Both flags are needed to connect:** SSH access works only when both `enabled` and `global_enabled` are `true`.
- **Careful, resets turn SSH off:** the factory default of both flags is `false`. `deleted` without `config`, and `replaced` or `overridden` with a flag left out, set it to `false` and stop SSH access to the switch. `replaced` and `overridden` behave the same for this module.
- **Only SSH is changed:** other system services, such as Telnet, FTP or the web server, are never touched.
- **Unreported flags:** if the switch does not report a flag, it shows as `null` in `before` and `after`, and `gathered` fails instead of returning an incomplete configuration.
- **Partly applied changes:** if the switch rejects a change after applying part of it, the task reports which flags were applied, with `changed: true` when any was.
- **Lost connections:** if the connection drops during a change and the module cannot confirm the result, it reports `changed: true`, because the change may have been applied. Run the task again to bring the switch to the requested state.
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
| GET | /v0/configuration/system-services | Get the system services settings |
| PATCH | /v0/configuration/system-services | Update the system services configuration |

---

## [Platform Constraints](#table-of-contents)

- Only the `ssh` object of the System Services configuration is managed. `telnet`, `ftp`, `iqagent`, `webServer`, `cloudConnector` and `vxlanGwFullInterworkingMode` are discarded from every GET response and are never included in a PATCH body.
- `global_enabled` is a Fabric Engine (VOSS) only attribute per the OpenAPI spec (`x-nos=fabric-engine`).
- On Fabric Engine, both `enabled` and `global_enabled` must be `true` for SSH connectivity to work, though they can be set independently.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state: `merged`, `replaced`, `overridden`, `deleted` or `gathered` |
| `config` | dict | Yes (merged/replaced/overridden) | - | SSH service flags to manage. A `config` with no option set (for example `{}`) counts as omitted for these states and fails before any request. Optional for `deleted`; omitted or with no option set, both flags are reset |
| `config.enabled` | bool | No | - | SSH service status. Left alone when omitted, except for `overridden`/`replaced` which reset it to `false` |
| `config.global_enabled` | bool | No | - | Global SSH service status (Fabric Engine only). Left alone when omitted, except for `overridden`/`replaced` which reset it to `false` |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply the supplied field(s). The field not supplied keeps its current value. | GET, PATCH |
| `replaced` | The supplied fields are authoritative. Any field not supplied is reset to its factory default. | GET, PATCH |
| `overridden` | Behaves exactly like `replaced` - `ssh` is a singleton object with no listed/unlisted sub-resources to reconcile. | GET, PATCH |
| `deleted` | Reset to factory defaults. With a `config` naming a field, only the fields named in it are reset; a `config` with no option set (for example `{}`) resets both, as when it is omitted. | GET, PATCH |
| `gathered` | Read-only output. | GET |

---

## [Factory Defaults](#table-of-contents)

| Field | Default Value | Source |
|-------|---------------|--------|
| `enabled` | `false` | Not in OpenAPI spec. User Guide's Variable Definitions table for the CLI `sshd` boot-config flag states a default of "disabled"; confirmed with the requester |
| `global_enabled` | `false` | Not in OpenAPI spec. No conclusive non-Zero-Touch-Deployment default found in the User Guide; confirmed with the requester |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether the SSH configuration changed |
| `before` | dict | SSH configuration before changes (action states) |
| `after` | dict | SSH configuration after changes (returned for every action state; equals `before` when nothing changed, and is the predicted state in check mode) |
| `gathered` | dict | Current SSH configuration (returned for `state=gathered`). Always holds both flags; the gather fails when the device does not report one of them |
| `ssh.before` | dict | SSH configuration before the requested change |
| `ssh.after` | dict | SSH configuration after the requested change |
| `ssh.config` | dict | Gathered SSH configuration |
| `ssh.differences` | dict | Changed fields with their before and after values |
| `submitted` | dict | The PATCH path and body sent to the device when a change was required |

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | SSH service status |
| `global_enabled` | bool | Global SSH service status (Fabric Engine only) |

---

## [Examples](#table-of-contents)

### Enable the SSH service

```yaml
- name: Enable the SSH service
  extreme.fe.extreme_fe_ssh:
    state: merged
    config:
      enabled: true
      global_enabled: true
```

### Change only one flag

```yaml
- name: Enable only the global SSH flag, leave the service flag untouched
  extreme.fe.extreme_fe_ssh:
    state: merged
    config:
      global_enabled: true
```

### Make the supplied flags authoritative

```yaml
- name: Make the supplied flags authoritative
  extreme.fe.extreme_fe_ssh:
    state: replaced
    config:
      enabled: true
      global_enabled: true
```

### Override the SSH configuration

```yaml
- name: Enforce the exact SSH configuration
  extreme.fe.extreme_fe_ssh:
    state: overridden
    config:
      enabled: true
      global_enabled: true
```

### Delete SSH configuration

```yaml
- name: Reset the global SSH flag to its factory default
  extreme.fe.extreme_fe_ssh:
    state: deleted
    config:
      global_enabled: true

- name: Reset both SSH flags to their factory defaults
  extreme.fe.extreme_fe_ssh:
    state: deleted
```

### Gather SSH configuration

```yaml
- name: Collect the current SSH configuration
  extreme.fe.extreme_fe_ssh:
    state: gathered
  register: ssh_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage the SSH service flags
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current SSH configuration
      extreme.fe.extreme_fe_ssh:
        state: gathered
      register: ssh_before

    - name: Enable the SSH service
      extreme.fe.extreme_fe_ssh:
        state: merged
        config:
          enabled: true
          global_enabled: true

    - name: Make the supplied flags authoritative
      extreme.fe.extreme_fe_ssh:
        state: replaced
        config:
          enabled: true
          global_enabled: true

    - name: Enforce the exact SSH configuration
      extreme.fe.extreme_fe_ssh:
        state: overridden
        config:
          enabled: true
          global_enabled: true

    - name: Reset both SSH flags to their factory defaults
      extreme.fe.extreme_fe_ssh:
        state: deleted

    - name: Gather SSH configuration after changes
      extreme.fe.extreme_fe_ssh:
        state: gathered
      register: ssh_after
```

---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
