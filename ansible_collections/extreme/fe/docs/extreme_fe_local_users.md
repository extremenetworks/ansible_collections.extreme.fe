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
- A write (`POST`, `PATCH`, `DELETE`) that fails without an answer (a lost connection) may have been applied, so the task reports `changed: true`. A `DELETE` answered with 404 counts as done: the account was just read as present, and a DELETE resent after a lost answer finds it gone. An account `POST` answered with 409 (a resend) is checked against a re-read: it counts as done when the account is there with the submitted level and the POST carried no password. Otherwise the outcome is unknown and the task fails with `changed: true`; the stored password is encrypted and cannot be compared, so another writer may have created the account with a different one. Running the task again with `update_password: always` and `old_secret`, or `super_user_name` and `super_user_password`, re-applies it.
- Every error is scrubbed of the stored passwords the module read from the device as well, so an error that quotes another account's stored (encrypted) password does not return it.
- Supports check mode and diff mode. Under `--diff` the module reports the whole account list before and after the change; combined with `--check` the reported "after" is the state that would have been written.
- The device stores passwords encrypted, so a cleartext password supplied in `config` can never be compared against the stored value. Idempotency for the password is therefore controlled by `update_password` rather than by comparison. This mirrors the convention used by the `ios_user`, `eos_user`, `nxos_user` and `vyos_user` modules, which all expose the same parameter with the same default for the same reason.
- With the default `update_password: always`, a task that supplies `secret.value` reports `changed` on every run. Set `update_password: on_create` to keep a playbook idempotent - the password is then written only when the account is created.
- The account password is never returned. `gathered`, `before` and `after` omit `secret` entirely (neither `secret.value` nor `secret.is_encrypted`), so they use the `config` option shape and `gathered` can be re-applied as `config` without writing a password. The same applies to `old_secret.value` and `super_user_password`: every credential a task submits is masked out of failure `details`, `msg` and `err`, including when the device answers with plain text or quotes the request back in an error. This redaction does not depend on the task having submitted a value to compare the response against - the module finds a credential structurally wherever a response carries one (`secret.value`, `oldSecret.value`, `superUserPassword`) and scrubs that value from every string field of the same response, not only from the field it was found under, so a free-text message that quotes it is caught too. A response the device answers as plain text rather than JSON has no such structure to search, so it is redacted in full instead. The `extreme_fe` HTTPAPI plugin applies the same protection one layer earlier, before a 207 or HTTP-error message ever reaches this module. It never logs the request or response bodies of this endpoint, and it keeps the device's error message for a `POST` or `PATCH` (for example `Invalid user type. Supported values are ADMIN, ADMIN_LIMITED, READ_ONLY.`) with every submitted or returned credential masked; the error of a GET, of a `DELETE` and a plain-text answer keep only the status code. No vendor network module surfaces a stored credential, and neither does this one.
- `level` and `enabled` are required for every entry when `state` is `merged`, `replaced` or `overridden`. The OpenAPI spec defines no factory default for either, so they cannot be defaulted. They are not required for `deleted`, which needs only `username`.
- Because `level` and `enabled` are mandatory and `secret` cannot be reset to a default, `replaced` and `merged` behave identically for an existing account. `replaced` is retained for interface consistency with the other resource modules in this collection.
- `removable` appears only in the REST POST body. The PATCH body cannot carry it, so it can be set when an account is created but never changed afterwards. Supplying a value that differs from an existing account's current value fails with an explicit error rather than being silently dropped.
- Accounts that report `removable: false` are part of the device default configuration and cannot be deleted. `deleted` without `config` and `overridden` both skip them (and the connecting account), report each in `skipped_users` with the reason and emit a warning; naming such an account explicitly in a `deleted` task fails with an explicit error.
- The account used by the current Ansible connection is never deleted. `deleted` without `config` and `overridden` both skip it, and naming it explicitly fails. The account name is read from the connection plugin's `remote_user` option.
- `deleted` with an empty `config` (`config: []`) is the same as `deleted` without `config`, as in Ansible resource modules: every removable account except the connecting one is deleted, with the same protections.
- If the connecting account name cannot be determined, `deleted` without `config` fails rather than risk removing the account the connection depends on. List the accounts to remove in `config` instead.
- `deleted` naming an account that does not exist is not an error - the account is already absent, so the task reports no change for it.
- A device that reports no account collection at all - a 404, either at the transport level or embedded in an error document - is treated as an empty inventory rather than as a failure, so `gathered`, `deleted` and `overridden` still run against it.
- The same `username` may not appear more than once in a single `config` list.
- `username` is limited to 20 characters. The OpenAPI spec's `UsernameString` schema states 1-32, but a real Fabric Engine device rejects anything over 20 with `Username must be provided and length should be between 1 and 20 characters` - confirmed against a live device on 2026-09-22. The firmware limit is enforced here rather than the wider spec value.
- Whenever a password is written to an existing account, the module always includes `level` in the PATCH body alongside `secret`, even when `level` is unchanged. A real device rejects a PATCH carrying `secret` without `level`, regardless of `old_secret` or the super-user fields also being present - confirmed against a live device on 2026-09-22, which demanded `secret`, `level`, `value` and `oldSecret` together, or `secret`, `level`, `value`, `superUsername` and `superUserpassword` together. This is handled automatically; no playbook change is needed. The device reads the super-user fields as `superUserName` and `superUserPassword`, the names of the OpenAPI `UserAccountAttributes` schema, which the module sends.
- On the Fabric Engine 9.4 and 9.5 devices tested, a password change verified with `super_user_name` and `super_user_password` was refused with `Invalid username or password.` even for valid administrator credentials. Use `old_secret` to change a password.
- A PATCH that changes both `enabled` and the password is refused by the device (`Cannot update user password and user state at the same time.`), so the module sends the two changes as two PATCH requests, disabling before and enabling after the password change. When the second request fails, the task fails with `changed=true` and `details.applied_earlier` naming what the first one applied.
- Changing `level` on an existing account without also writing a password was rejected by the same device with the same error, and the User Guide states a custom account's access level "cannot be changed later" once created. Changing an account's level after creation may not be supported at all; if you need a different level, delete the account and recreate it.
- A new account can be created only with `level` `ADMIN`, `ADMIN_LIMITED` or `READ_ONLY` (the device answers any other level with `Invalid user type. Supported values are ADMIN, ADMIN_LIMITED, READ_ONLY.`). `L3_LIMITED`, `L2_LIMITED` and `L1_LIMITED` are the levels of the built-in `l3`, `l2` and `l1` accounts: they are accepted for an account that already has that level, so `gathered` output can be re-applied, and creating an account with one fails before any write request is sent (the module reads the account list first, to tell a new account from an existing one).
- A `secret` or `old_secret` without `value` writes nothing and is ignored, with a warning when it carries `is_encrypted`. Gathered output of earlier releases, which carried `secret.is_encrypted`, can therefore be re-applied unchanged.
- A new account is always created enabled. A real device silently ignores `enabled=false` on the `POST` that creates the account - confirmed 2026-09-22, and consistent with the User Guide's account creation CLI syntax, which has no disabled-creation form. The module issues a follow-up `PATCH` automatically when `enabled` is `false` at creation, so `config[].enabled: false` still takes effect; no playbook change is needed. If that follow-up `PATCH` fails, the task fails with `changed=true` and a message saying the account was created (and is still enabled unless the re-read shows otherwise).
- When a `PATCH` of an account fails, the module re-reads the account and reports in the failure `details` which of the attempted fields the device applied (`applied_fields`, `not_applied_fields`, `unchanged_fields` for a value the account already held, such as the `level` sent with a password), or `reread_error` when the re-read itself failed. `secret` is listed in `unknown_fields`, since the stored password is encrypted and cannot be compared; no field value is ever reported. `changed` is true when the re-read shows a field applied. A failed re-read is described generically, with its numeric error code; the device text is never copied, and neither is that of an error document answering any GET of the accounts, since it could quote a stored credential.
- A task that fails after one of its requests already changed the device (an account created, updated or deleted earlier in the same task) reports `changed=true`, and the message and `details.changed_users` name the accounts already changed. The failing account is named too when it was created before its follow-up PATCH failed, or when the re-read of a rejected PATCH shows a field applied.

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
