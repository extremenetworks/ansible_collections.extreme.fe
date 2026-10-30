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
- When the device stops that operation early after a command it reports with status 400 but that still produced output that is not a CLI error (for example `show sys-info`), the module sends the commands the device skipped in follow-up operations, in order, so the batch completes.
- Returns the CLI output for every command and fails when any command reports an error.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- **Always reports a change:** the module cannot tell whether a command changed anything, so a successful task always reports `changed: true`. In check mode no command is sent and `responses` holds no output.
- **Commands that answer with a warning:** some commands, for example `show sys-info`, return their full output with an error status. The module accepts them and lists them in `cli_warnings`. Output that is a CLI error (a line starting with `%` or `Error:`) fails the task.
- **Stopping at the first failure:** by default the batch stops at the first command that fails, and the task fails. With `continue_on_failure: true` the switch runs the remaining commands anyway; the task still fails, but `responses` holds the output of every command.
- **CLI modes:** when the module has to re-send the rest of a batch after a command that answered with a warning, the new request starts outside any CLI mode an earlier command entered (for example `configure terminal`). If later commands depend on such a mode, set `continue_on_failure: true`, which keeps the whole batch in one request.
- **`changed` on failure:** a failed task reports `changed: true` if any command ran before the failure; the error lists the commands that ran and any whose result is unknown, so check the switch before running them again.

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
| `continue_on_failure` | bool | No | `false` | Continue executing commands after a failure is reported. When `false`, the device stops the batch at the first command that does not return 200; a command that returns 400 with output that is not a CLI error is accepted and the commands the device skipped are re-sent, while any other non-200 status (or a 400 whose output is a CLI error) stops the batch and fails the task The failed result still returns `responses` for every command. |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Indicates the module executed CLI commands on the device. Always true when the task succeeds. When the task fails, true if at least one command was executed before the failure (it returned 200, or 400 with output that is not a CLI error), so a failed batch that already ran configuration commands is not reported as unchanged. A failed task lists the commands that ran in `details.executed`. When a follow-up request re-sending skipped commands fails, the commands of the failed request are listed in `details.unknown`, because they may or may not have run, so check the device before retrying. Only when the device answered 409 (not executed) for that request are they listed in `details.not_executed` instead. A response with a malformed entry, to the first request or to a follow-up one, still counts the commands its well-formed entries confirm (200, or 400 with output that is not a CLI error) as executed, with `changed: true`; only the other commands of that request are listed in `details.unknown`. When the response to the first request cannot be read (empty, malformed or with the wrong number of entries) and confirms no execution, or the first request fails without an HTTP status (a lost connection, for example), `changed` stays false and every position is listed in `details.unknown`, with an empty `details.executed`; an explicit HTTP error of the first request is reported as before. A response with fewer or more entries than commands submitted counts a command as executed only when a confirming result names it in `cliInput` and that command text occurs once in the request; the others are unknown. The details of a malformed response never carry the response itself, which holds command text and output. These three lists hold the 0-based positions of the commands in `commands`, not the command text, so a password-bearing command is never copied into them |
| `responses` | list of dict | Results for each CLI command (`command`, `output`, `status_code`, and `warning` when the device returned status 400 with output that is not a CLI error). `output` is the CLI output as a list of lines, without line terminators, and an empty list when the command produced no output. Also returned when the task fails because a command failed: an entry for every command, the failed one included, so the output of the commands that succeeded can still be read (for example with `ignore_errors`). Not returned when the device response cannot be read or a request fails without results |
| `cli_warnings` | list | Commands that returned status 400 with output that is not a CLI error |
| `metadata` | dict | Success, failure and skip counters reported by the device. When skipped commands were re-sent, the counters of all requests are combined and `skipped` counts only the commands that were never executed |

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
