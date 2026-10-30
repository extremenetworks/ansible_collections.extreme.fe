# Local User Accounts

## Module: extreme.fe.extreme_fe_local_users

Manages local user accounts on Fabric Engine devices.

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
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

This module manages local user accounts on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports the Ansible states: merged, replaced, overridden, deleted and gathered.
- Manages the account name, privilege level, enabled state, removable flag and password.
- Each account is identified by its `username`, which is the resource identifier and the path segment of the PATCH and DELETE endpoints.
- Accounts are created with POST, updated with PATCH and removed with DELETE. An account that does not exist is created; an account that exists has only the differing fields patched.
- The password is never read back from the device and never returned by this module.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- **Usernames:** up to 20 characters, and each `username` only once in `config`.
- **`level` and `enabled` are required** for every entry with `merged`, `replaced` and `overridden`; `deleted` needs only `username`. For an existing account, `replaced` therefore behaves like `merged`.
- **Passwords and idempotency:** the switch stores passwords encrypted, so the module cannot compare them. With the default `update_password: always`, a task that sets `secret.value` reports `changed` on every run. Use `update_password: on_create` to write the password only when the account is created.
- **Changing a password:** supply `old_secret`. On the Fabric Engine 9.4 and 9.5 devices tested, a change confirmed with `super_user_name` and `super_user_password` was refused even with valid administrator credentials.
- **Passwords are never returned** in `gathered`, `before`, `after`, `--diff` or error messages, so `gathered` can be passed back as `config` without writing a password.
- **Levels:** a new account can only be created with `ADMIN`, `ADMIN_LIMITED` or `READ_ONLY`. `L3_LIMITED`, `L2_LIMITED` and `L1_LIMITED` belong to the built-in `l3`, `l2` and `l1` accounts and are accepted only for an account that already has that level. Changing the level of an existing account may not be supported by the switch; delete and re-create the account instead.
- **`removable`** can only be set when an account is created. A different value for an existing account fails.
- **Protected accounts:** the switch's built-in accounts (`removable: false`) and the account Ansible is connected with are never deleted. `deleted` without `config` and `overridden` skip them with a warning and list them in `skipped_users`; naming one in `deleted` fails before anything is deleted. If the module cannot tell which account the connection uses, `deleted` without `config` and `overridden` fail instead.
- **`deleted`:** an account that does not exist is not an error. Without `config` (or with `config: []`), every account except the protected ones is deleted.
- **Lost connections:** if the connection drops during a change, the task reports `changed: true`, because the change may have been applied. Run the task again to make sure.
- **`changed` on failure:** a failed task reports `changed: true` if an account was already created, changed or deleted in the same task, and the error message names it.
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
| GET | /v0/configuration/accounts | Get the account information for all user accounts |
| POST | /v0/configuration/accounts | Add a user account |
| PATCH | /v0/configuration/accounts/{username} | Update a user account |
| DELETE | /v0/configuration/accounts/{username} | Remove a user account |

---

## [Platform Constraints](#table-of-contents)

- `username` accepts 1 to 20 characters. The OpenAPI `UsernameString` schema states 1-32, but a real Fabric Engine device rejects anything over 20 (`Username must be provided and length should be between 1 and 20 characters`) - confirmed against a live device on 2026-09-22. The module enforces the firmware limit.
- `secret.value` accepts at most 512 characters, per the OpenAPI `AaaSecret` schema. That maximum accommodates the longest encrypted password a GET can return; a cleartext password is subject to the device's own shorter limit.
- On Fabric Engine the password must not contain, repeat, or reverse the associated username.
- The privilege levels map to Fabric Engine as follows: `ADMIN` is read-write-all, `ADMIN_LIMITED` is read-write, `L3_LIMITED` is layer3, `L2_LIMITED` is layer2, `L1_LIMITED` is layer1 and `READ_ONLY` is read-only.
- The POST body and the PATCH body are different schemas. POST accepts `username`, `level`, `enabled`, `removable` and `secret`. PATCH accepts `level`, `enabled`, `secret`, `oldSecret`, `superUserName` and `superUserPassword`. `removable` is therefore settable only at creation, and `username` cannot be changed by this API at all.
- Renaming an account is not supported by the REST API. Remove the old account and add a new one.
- The POST, PATCH and DELETE operations answer with HTTP 204 and no response body, so the module re-reads the account list to report the state after a change.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | no | `merged` | One of `merged`, `replaced`, `overridden`, `deleted`, `gathered`. |
| `config` | list | no | | List of local user accounts to manage. Required when `state` is `merged`, `replaced` or `overridden`. |
| `config[].username` | str | yes | | Account name, 1-20 characters. The resource identifier. |
| `config[].level` | str | no | | Privilege level. One of `ADMIN`, `ADMIN_LIMITED`, `L3_LIMITED`, `L2_LIMITED`, `L1_LIMITED`, `READ_ONLY`; a new account only `ADMIN`, `ADMIN_LIMITED` or `READ_ONLY`. Required for `merged`, `replaced` and `overridden`. |
| `config[].enabled` | bool | no | | Whether the account is enabled. Required for `merged`, `replaced` and `overridden`. |
| `config[].removable` | bool | no | | Whether the account may be deleted. Settable only when the account is created. |
| `config[].secret` | dict | no | | Password for the account. Without `value` nothing is written and the entry is ignored. |
| `config[].secret.value` | str | no | | The password. Never returned by the module. |
| `config[].secret.is_encrypted` | bool | no | | Whether `secret.value` is already encrypted (`true`) or cleartext (`false`). |
| `config[].old_secret` | dict | no | | The previous password, required by the device when overwriting an existing cleartext password. |
| `config[].old_secret.value` | str | no | | The previous password. Never returned by the module. |
| `config[].old_secret.is_encrypted` | bool | no | | Whether `old_secret.value` is already encrypted (`true`) or cleartext (`false`). |
| `config[].super_user_name` | str | no | | Super user name used to verify credentials when overwriting an existing password. Sent as `superUserName`; Fabric Engine 9.4 and 9.5 were seen to refuse valid credentials, so prefer `old_secret`. |
| `config[].super_user_password` | str | no | | Super user password used to verify credentials when overwriting an existing password. Never returned by the module. |
| `update_password` | str | no | `always` | One of `on_create`, `always`. Controls when the password is written to the device. |
| `gather_filter` | list | no | | Limit gathered account facts to these account names. |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|--------------|
| `merged` | Creates accounts that do not exist and patches the supplied fields on accounts that do. Unlisted accounts are left alone. | GET, POST, PATCH |
| `replaced` | Makes the supplied settings authoritative for each listed account. Identical to `merged` here, because `level` and `enabled` are mandatory and `secret` has no default to reset to. Unlisted accounts are left alone. | GET, POST, PATCH |
| `overridden` | Enforces the exact set of accounts. Removable accounts not listed in `config` are deleted, except the connecting account; listed accounts are created or updated. | GET, POST, PATCH, DELETE |
| `deleted` | Removes the listed accounts. With no `config`, or an empty one (`config: []`), removes every removable account except the connecting one. | GET, DELETE |
| `gathered` | Returns the current accounts without making changes. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any account was modified. |
| `before` | list | Full account configuration before changes. Returned for `merged`, `replaced`, `overridden` and `deleted`. |
| `after` | list | Full account configuration after changes. Returned for every action state; equals `before` when nothing changed, and is the predicted state in check mode. |
| `gathered` | list | Account configuration gathered from the device. Returned only for `state=gathered`. |
| `local_users` | list | Per-account operation results. Returned when `state` is not `gathered`. |
| `local_users[].username` | str | Account name. |
| `local_users[].before` | dict | Account configuration before the operation. |
| `local_users[].after` | dict | Account configuration after the operation. |
| `local_users[].changed` | bool | Whether this account was modified. |
| `local_users[].differences` | dict | Fields that changed, with their before and after values. |
| `skipped_users` | list | Protected accounts a bulk delete left in place, each as `{username, reason}`: accounts reporting `removable=false` and the account the connection is authenticated with. A warning is emitted for each. Returned for `overridden` and for `deleted` without `config`; empty when none was skipped. |

### Output Fields

Every account reported in `before`, `after` and `gathered` uses these fields, which are `config` options. `secret` is never reported.

| Field | Type | Description |
|-------|------|-------------|
| `username` | str | Account name. |
| `level` | str | Privilege level. |
| `enabled` | bool | Whether the account is enabled. |
| `removable` | bool | Whether the account may be deleted. |

---

## [Examples](#table-of-contents)

### Gather all local user accounts

```yaml
- name: Gather all local user accounts
  extreme.fe.extreme_fe_local_users:
    state: gathered
```

### Gather a single account

```yaml
- name: Gather a single account
  extreme.fe.extreme_fe_local_users:
    state: gathered
    gather_filter:
      - operator
```

### Create a read-only account

```yaml
- name: Create a read-only account
  extreme.fe.extreme_fe_local_users:
    state: merged
    config:
      - username: operator
        level: READ_ONLY
        enabled: true
        secret:
          value: "{{ operator_password }}"
          is_encrypted: false
```

### Create an account that cannot be deleted later

```yaml
- name: Create an account that cannot be deleted later
  extreme.fe.extreme_fe_local_users:
    state: merged
    config:
      - username: backup_admin
        level: ADMIN
        enabled: true
        removable: false
        secret:
          value: "{{ backup_admin_password }}"
          is_encrypted: false
```

### Keep the run idempotent

With the default `update_password: always` a task that supplies a password reports `changed` every run, because the stored password is encrypted and cannot be compared. Use `on_create` to write the password only when the account is created.

```yaml
- name: Ensure the account exists without rewriting its password every run
  extreme.fe.extreme_fe_local_users:
    state: merged
    update_password: on_create
    config:
      - username: operator
        level: READ_ONLY
        enabled: true
        secret:
          value: "{{ operator_password }}"
          is_encrypted: false
```

### Rotate a password, supplying the previous one

```yaml
- name: Rotate the operator password
  extreme.fe.extreme_fe_local_users:
    state: merged
    config:
      - username: operator
        level: READ_ONLY
        enabled: true
        secret:
          value: "{{ new_operator_password }}"
          is_encrypted: false
        old_secret:
          value: "{{ old_operator_password }}"
          is_encrypted: false
```

### Disable an account

```yaml
- name: Disable the operator account
  extreme.fe.extreme_fe_local_users:
    state: replaced
    config:
      - username: operator
        level: READ_ONLY
        enabled: false
```

### Enforce the exact set of accounts

Removable accounts that are not listed are deleted. Accounts reporting `removable: false` and the connecting account are skipped; each is reported in `skipped_users` with the reason, and a warning is emitted.

```yaml
- name: Make these the only removable accounts on the device
  extreme.fe.extreme_fe_local_users:
    state: overridden
    config:
      - username: operator
        level: READ_ONLY
        enabled: true
      - username: netadmin
        level: ADMIN
        enabled: true
```

### Remove a single account

```yaml
- name: Remove a single account
  extreme.fe.extreme_fe_local_users:
    state: deleted
    config:
      - username: operator
```

### Remove every removable account

The connecting account and any account reporting `removable: false` are kept; each is reported in `skipped_users` with the reason, and a warning is emitted.

```yaml
- name: Remove every removable account except the connecting one
  extreme.fe.extreme_fe_local_users:
    state: deleted
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage local user accounts on Fabric Engine devices
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  vars:
    operator_password: "{{ vault_operator_password }}"
    netadmin_password: "{{ vault_netadmin_password }}"
  tasks:
    - name: Gather all local user accounts
      extreme.fe.extreme_fe_local_users:
        state: gathered
      register: accounts_before

    - name: Show the accounts currently configured
      ansible.builtin.debug:
        var: accounts_before.gathered

    - name: Create a read-only account
      extreme.fe.extreme_fe_local_users:
        state: merged
        update_password: on_create
        config:
          - username: operator
            level: READ_ONLY
            enabled: true
            secret:
              value: "{{ operator_password }}"
              is_encrypted: false

    - name: Create an administrative account
      extreme.fe.extreme_fe_local_users:
        state: merged
        update_password: on_create
        config:
          - username: netadmin
            level: ADMIN
            enabled: true
            secret:
              value: "{{ netadmin_password }}"
              is_encrypted: false

    - name: Disable the operator account
      extreme.fe.extreme_fe_local_users:
        state: replaced
        config:
          - username: operator
            level: READ_ONLY
            enabled: false

    - name: Make these the only removable accounts on the device
      extreme.fe.extreme_fe_local_users:
        state: overridden
        config:
          - username: operator
            level: READ_ONLY
            enabled: false
          - username: netadmin
            level: ADMIN
            enabled: true

    - name: Remove the operator account
      extreme.fe.extreme_fe_local_users:
        state: deleted
        config:
          - username: operator

    - name: Gather the accounts again
      extreme.fe.extreme_fe_local_users:
        state: gathered
      register: accounts_after

    - name: Show the accounts after the changes
      ansible.builtin.debug:
        var: accounts_after.gathered
```

---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
