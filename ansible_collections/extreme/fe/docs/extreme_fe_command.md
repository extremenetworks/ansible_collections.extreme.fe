# System Commands

## Module: extreme.fe.extreme_fe_command

Executes CLI commands on Fabric Engine devices.

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

Through this module one or more CLI commands can be executed on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Ensures the commands run in the order provided and submits them as a single REST operation to `/v0/operation/system/cli`.
- Returns the CLI output for every command and fails when any command reports an error.

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
| POST | /v0/operation/system/cli | Execute CLI commands |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `commands` | list of str | Yes | - | Ordered list of CLI commands to execute on the device |
| `continue_on_failure` | bool | No | `false` | Continue executing commands after a failure is reported |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Always true — CLI commands were executed |
| `responses` | list of dict | Results for each CLI command (command, output, status_code) |
| `cli_warnings` | list | Commands that returned status 400 with valid CLI output |

---

## [Examples](#table-of-contents)

### Execute CLI commands

```yaml
- name: Run CLI commands on the switch
  extreme.fe.extreme_fe_command:
    commands:
      - enable
      - configure terminal
      - show vlan basic
  register: cli_result
```

### Continue on failure

```yaml
- name: Execute CLI sequence with continue on failure
  extreme.fe.extreme_fe_command:
    commands:
      - enable
      - enable super-user-mode
      - show vlan basic
    continue_on_failure: true
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Execute CLI commands on Fabric Engine switch
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Run show commands
      extreme.fe.extreme_fe_command:
        commands:
          - show vlan basic
          - show interfaces gigabitEthernet name
      register: show_output

    - name: Display output
      ansible.builtin.debug:
        var: show_output.responses
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
