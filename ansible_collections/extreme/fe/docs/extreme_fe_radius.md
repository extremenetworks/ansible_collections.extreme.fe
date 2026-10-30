# Remote Authentication Dial-In User Service (RADIUS)

## Module: extreme.fe.extreme_fe_radius

Manages RADIUS settings and retrieves RADIUS runtime state on Fabric Engine devices.

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

This module manages RADIUS configuration on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Manages global RADIUS settings.
- Manages AAA servers and dynamic authorization clients.
- Manages Secure RADIUS certificate profiles.
- Retrieves global and per-server runtime state with `state: gathered`.
- Supports `merged`, `replaced`, `overridden`, `deleted`, and `gathered`.

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2. Some fixes are based on reports from Fabric Engine 9.4 and 9.5 and have not been tested there.
- **Keep a way to log in:** `deleted` and `overridden` can remove the AAA servers the switch uses to authenticate management logins. If the switch logs users in through RADIUS, keep a local account (or another server) that works before running such a task.
- **Changing an AAA server re-creates it:** an existing AAA server cannot be updated in place, so a changed server is deleted and created again, which can briefly interrupt service.
- **The `default` secure profile is built in:** it cannot be created or deleted, and `replaced`, `overridden` and `deleted` always keep it.
- **Secrets are never returned:** shared secrets, the global reachability password, private keys and passphrases are left out of `gathered`, `before`, `after` and the diff, and are masked in error messages.
- **Secrets always count as a change:** the switch does not return secrets, so a supplied secret, key, passphrase or `global.password` is always sent and the task reports `changed` on every run. Leave them out of tasks you run repeatedly; an omitted secret is never sent and the stored one is kept.
- **The global password:** `deleted` without `config` and `overridden` never reset it. To change it, set `global.password`; to reset it to its factory default, name it under `global` with `deleted`.
- **Re-applying `gathered`:** `gathered` can be passed back as `config` and changes nothing; the stored secrets are kept. A secret that is only the device mask (`******`) is ignored with a warning, so a placeholder never replaces a real secret.
- **IPv6 server addresses:** compared as addresses, so `2001:db8::10` matches the `2001:db8:0:0:0:0:0:10` the switch reports.
- **Accounting:** `global.account_enabled: true` needs at least one `AAA` server (a `DYN_AUTH` client does not count). The module disables accounting before RADIUS itself when you turn both off. The switch can reject accounting changes made a few seconds apart.
- **Lost connections:** if the connection drops during a change, the task reports `changed: true` unless it can confirm nothing was applied, because the change may have gone through. Run the task again to bring the switch to the requested state.
- **Partly applied changes:** if the switch rejects a change to the global settings after applying part of it, the error message lists which settings were applied and which were not. A failed task reports `changed: true` if the switch was already modified.
- Supports check mode (`--check`) and diff mode (`--diff`).

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v0/configuration/radius` | Retrieve global settings, servers, and secure-profile summaries |
| PATCH | `/v0/configuration/radius` | Update global settings |
| GET | `/v0/state/radius` | Retrieve global and per-server runtime state |
| GET | `/v0/configuration/radius/secure-profile` | Retrieve secure profiles |
| POST | `/v0/configuration/radius/secure-profile` | Create a secure profile |
| GET | `/v0/configuration/radius/secure-profile/{secure_profile_name}` | Retrieve one secure profile |
| PATCH | `/v0/configuration/radius/secure-profile/{secure_profile_name}` | Update one secure profile |
| DELETE | `/v0/configuration/radius/secure-profile/{secure_profile_name}` | Delete one secure profile |
| PATCH | `/v0/configuration/radius/dynamic-server/host-type/{host_type}/host/{host}` | Update a dynamic authorization client |
| DELETE | `/v0/configuration/radius/dynamic-server/host-type/{host_type}/host/{host}` | Delete a dynamic authorization client |
| POST | `/v0/configuration/radius/server` | Create an AAA server or dynamic authorization client |
| DELETE | `/v0/configuration/radius/server/server-mode/{server_mode}/host-type/{host_type}/host/{host}/used-by/{used_by}` | Delete an AAA server |

## [Platform Constraints](#table-of-contents)

- Only `AAA` and `DYN_AUTH` server modes are supported on Fabric Engine.
- AAA `used_by` values are `DOT1X`, `LOGIN`, `ENDPOINT_TRACKING`, `SNMP`, and `WEB`.
- A changed AAA server is replaced with DELETE followed by POST because no update endpoint exists.
- Dynamic authorization clients are updated in place with PATCH.
- Secure profile names are 1-16 characters.
- AAA shared secrets are at most 32 characters.

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Desired resource state |
| `config` | dict | For merged, replaced, overridden | - | Complete RADIUS configuration input |
| `config.global` | dict | No | - | Global RADIUS settings |
| `config.global.enabled` | bool | No | - | Enable RADIUS |
| `config.global.account_attr` | int | No | - | Accounting attribute, 192-240 |
| `config.global.account_enabled` | bool | No | - | Enable RADIUS accounting |
| `config.global.account_cli_commands` | bool | No | - | Include CLI commands in accounting updates |
| `config.global.access_priority_attr` | int | No | - | Access-Priority attribute, 192-240 |
| `config.global.auth_info_attr` | int | No | - | Auth-Info vendor attribute, 0-255 |
| `config.global.command_access_attr` | int | No | - | Command-Access attribute, 192-240 |
| `config.global.clear_stat` | bool | No | - | Clear statistics for configured servers |
| `config.global.cli_commands_attr` | int | No | - | CLI-Commands attribute, 192-240 |
| `config.global.cli_commands_count` | int | No | - | CLI command interim-packet count, 1-40 |
| `config.global.cli_profile_enabled` | bool | No | - | Enable RADIUS CLI profiling |
| `config.global.max_server` | int | No | - | Maximum configured servers, 1-10 |
| `config.global.mcast_addr_attr` | int | No | - | Multicast address vendor attribute, 0-255 |
| `config.global.secure_enabled` | bool | No | - | Enable Secure RADIUS |
| `config.global.keep_alive_timer` | int | No | - | Reachable-server check interval, 30-600 seconds |
| `config.global.unreachable_timer` | int | No | - | Unreachable-server check interval, 30-600 seconds |
| `config.global.username` | str | No | - | Dummy-request reachability username, 1-16 characters |
| `config.global.password` | str | No | - | Dummy-request reachability password, 1-16 characters; hidden from output |
| `config.global.reachability_mode` | str | No | - | `USE_STATUS_SERVER_PACKETS` or `USE_DUMMY_RADIUS_REQUESTS` |
| `config.servers` | list of dict | No | - | AAA servers and dynamic authorization clients |
| `config.servers[].server_mode` | str | Yes | - | `AAA` or `DYN_AUTH` |
| `config.servers[].host_type` | str | Yes | - | `hostname`, `IPv4`, or `IPv6` |
| `config.servers[].address` | str | Yes | - | Host name or IP address |
| `config.servers[].used_by` | str | For AAA | - | Feature using the AAA server |
| `config.servers[].secret` | str | For create or AAA replacement | - | Shared secret; hidden from output |
| `config.servers[].auth_port` | int | No | - | AAA authentication port, 1-65535 |
| `config.servers[].account_port` | int | No | - | AAA accounting port, 1-65535 |
| `config.servers[].retries` | int | No | - | AAA retry count, 0-6 |
| `config.servers[].timeout` | int | No | - | AAA timeout, 1-180 seconds |
| `config.servers[].enabled` | bool | No | - | Enable the server or client |
| `config.servers[].account_enabled` | bool | No | - | Enable accounting on an AAA server |
| `config.servers[].priority` | int | No | - | AAA selection priority, 1-10 |
| `config.servers[].secure_enabled` | bool | No | - | Enable Secure RADIUS on an AAA server |
| `config.servers[].secure_mode` | str | No | - | `TLS` or `DTLS`. A server the device reports with secure mode `NONE` (plain UDP) has no `secure_mode` in the returned configuration |
| `config.servers[].secure_profile` | str | No | - | Secure profile name, 1-16 characters |
| `config.servers[].secure_log_level` | str | No | - | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG` |
| `config.servers[].secure_ocsp_enabled` | bool | No | - | Enable OCSP checks |
| `config.servers[].port` | int | No | - | Dynamic authorization listen port, 1024-65535 |
| `config.secure_profiles` | list of dict | No | - | Secure RADIUS certificate profiles |
| `config.secure_profiles[].name` | str | Yes | - | Profile name, 1-16 characters |
| `config.secure_profiles[].root_cert` | str | No | - | Root certificate or chain in PEM format, at most 30720 characters |
| `config.secure_profiles[].cert` | str | No | - | Client certificate in PEM format, at most 3072 characters |
| `config.secure_profiles[].key` | str | No | - | RSA private key in PEM format, at most 3072 characters; hidden from output |
| `config.secure_profiles[].password` | str | No | - | Private-key passphrase, at most 255 characters; hidden from output |

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Patch supplied globals, add missing resources, and update matching resources. Existing AAA changes use delete and recreate. | GET, PATCH, POST, DELETE |
| `replaced` | Supplied server/profile lists become final for those lists. Omitted global fields and omitted list types remain unchanged. | GET, PATCH, POST, DELETE |
| `overridden` | Reset omitted non-secret globals to defaults, reconcile listed resources, remove unlisted resources, and leave an omitted global password unchanged. | GET, PATCH, POST, DELETE |
| `deleted` | Reset named global fields and delete named resources. With no config, reset all non-secret globals (the global password is left unchanged) and delete all servers/profiles. | GET, PATCH, DELETE |
| `gathered` | Return configuration (in the `config` option shape, without secrets), read-only device values (`read_only_config`), and runtime state without changes. | GET |

## [Factory Defaults](#table-of-contents)

All values come from the `RadiusGlobalSettings` OpenAPI schema. The Fabric Engine `keepAliveTimer` default is stated in that field's description.

| Field | Default Value | Source |
|-------|---------------|--------|
| `enabled` | `false` | OpenAPI |
| `account_attr` | `193` | OpenAPI |
| `account_enabled` | `false` | OpenAPI |
| `account_cli_commands` | `false` | OpenAPI |
| `access_priority_attr` | `192` | OpenAPI |
| `auth_info_attr` | `91` | OpenAPI |
| `command_access_attr` | `194` | OpenAPI |
| `clear_stat` | `false` | OpenAPI |
| `cli_commands_attr` | `195` | OpenAPI |
| `cli_commands_count` | `40` | OpenAPI |
| `cli_profile_enabled` | `false` | OpenAPI |
| `max_server` | `10` | OpenAPI |
| `mcast_addr_attr` | `90` | OpenAPI |
| `secure_enabled` | `false` | OpenAPI |
| `keep_alive_timer` | `180` | OpenAPI description |
| `unreachable_timer` | `60` | OpenAPI |
| `username` | `reachme` | OpenAPI |
| `password` | `reachme` | OpenAPI, and the Fabric Engine factory value (`show radius reachability`) |
| `reachability_mode` | `USE_DUMMY_RADIUS_REQUESTS` | OpenAPI |

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Always returned. Indicates whether configuration changed. It is `false` for `gathered` and idempotent action-state runs. |
| `before` | dict | Returned for every state except `gathered`. Contains the full configuration read before action-state processing. |
| `after` | dict | Returned for every state except `gathered`. Contains the post-change GET snapshot, or the predicted snapshot in check mode. When nothing changes, it contains all the values already represented in `before`; extra GET-only fields do not count as changes. |
| `gathered` | dict | Returned only for `gathered`. Contains the current configuration in the `config` option shape, without secret material; it can be passed back as `config`. |
| `read_only_config` | dict | Returned only for `gathered`. Contains device-reported values that are not options: `global.igap_timeout_log_fsize`, per-server rows (identity keys plus `client_address`, `client_address_type`, `server_status`, `nas_ip`, `client_vlan_name`, `index`, `vr_name`), and per-profile rows (`name`, `root_cert_hash`, `cert_hash`, `status`). Not accepted as input. |
| `runtime_state` | dict | Returned only for `gathered`. Contains read-only global and per-server runtime state. |
| `radius` | dict | Always returned. Contains `config` for `gathered`, or `before`, `after`, and `differences` for action states. |
| `radius.before` | dict | Returned for action states. Same configuration as top-level `before`. |
| `radius.after` | dict | Returned for action states. Same value as top-level `after`. |
| `radius.config` | dict | Returned only for `gathered`. Same configuration as top-level `gathered`. |
| `radius.differences` | dict | Returned for action states. Contains changed top-level sections with before/after values, or `{}` when unchanged. |

### Output Fields

| Key | Type | Description |
|-----|------|-------------|
| `before.global` / `after.global` / `gathered.global` | dict | Non-secret global settings using the `config.global` option names; the password is never included. |
| `before.servers[]` / `after.servers[]` / `gathered.servers[]` | list of dict | Fabric Engine AAA and dynamic authorization server settings using the `config.servers[]` option names valid for each `server_mode`. The shared secret is never included. |
| `before.secure_profiles[]` / `after.secure_profiles[]` / `gathered.secure_profiles[]` | list of dict | Secure profile `name`, `root_cert`, and `cert` when reported; never private keys or passphrases. Hashes and status are in `read_only_config`. |
| `runtime_state.num_of_invalid_server_access` | int | Responses received from unknown or invalid RADIUS servers |
| `runtime_state.servers[]` | list of dict | Per-server runtime status and counters using snake_case field names |

## [Examples](#table-of-contents)

### Merge global settings and an AAA server

```yaml
- name: Enable RADIUS and add an AAA server
  extreme.fe.extreme_fe_radius:
    state: merged
    config:
      global:
        enabled: true
        account_enabled: true
      servers:
        - server_mode: AAA
          host_type: IPv4
          address: 192.0.2.10
          used_by: LOGIN
          secret: "{{ radius_shared_secret }}"
```

### Replace the server set

```yaml
- name: Make this the complete RADIUS server set
  extreme.fe.extreme_fe_radius:
    state: replaced
    config:
      servers:
        - server_mode: AAA
          host_type: IPv4
          address: 192.0.2.10
          used_by: LOGIN
        - server_mode: DYN_AUTH
          host_type: IPv4
          address: 192.0.2.20
          secret: "{{ radius_dynamic_secret }}"
          enabled: true
          port: 3799
```

### Override the complete configuration

```yaml
- name: Enforce the complete RADIUS configuration
  extreme.fe.extreme_fe_radius:
    state: overridden
    config:
      global:
        enabled: true
        secure_enabled: true
      servers:
        - server_mode: AAA
          host_type: IPv4
          address: 192.0.2.10
          used_by: LOGIN
          secret: "{{ radius_shared_secret }}"
          secure_enabled: true
          secure_profile: radsec-profile
      secure_profiles:
        - name: radsec-profile
          root_cert: "{{ radius_root_certificate }}"
          cert: "{{ radius_client_certificate }}"
          key: "{{ radius_private_key }}"
          password: "{{ radius_private_key_password }}"
```

### Delete selected resources

```yaml
- name: Remove one AAA server and secure profile
  extreme.fe.extreme_fe_radius:
    state: deleted
    config:
      servers:
        - server_mode: AAA
          host_type: IPv4
          address: 192.0.2.10
          used_by: LOGIN
      secure_profiles:
        - name: radsec-profile
```

### Delete all configuration

```yaml
- name: Reset globals and remove all RADIUS resources
  extreme.fe.extreme_fe_radius:
    state: deleted
```

### Gather configuration and runtime state

```yaml
- name: Gather RADIUS configuration and runtime state
  extreme.fe.extreme_fe_radius:
    state: gathered
  register: radius_state
```

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
---
- name: Manage RADIUS configuration
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  vars:
    radius_shared_secret: "secret1"
    radius_dynamic_secret: "secret2"
  tasks:
    - name: Gather RADIUS configuration and runtime state
      extreme.fe.extreme_fe_radius:
        state: gathered
      register: radius_state

    - name: Merge global settings and an AAA server
      extreme.fe.extreme_fe_radius:
        state: merged
        config:
          global:
            enabled: true
            account_attr: 193
            account_enabled: false
            account_cli_commands: false
            access_priority_attr: 192
            auth_info_attr: 91
            command_access_attr: 194
            clear_stat: false
            cli_commands_attr: 195
            cli_commands_count: 40
            cli_profile_enabled: false
            max_server: 10
            mcast_addr_attr: 90
            secure_enabled: false
            keep_alive_timer: 600
            unreachable_timer: 60
            username: reachme
            password: reachme
            reachability_mode: "USE_DUMMY_RADIUS_REQUESTS"
          servers:
            - server_mode: AAA
              host_type: IPv4
              address: 192.0.2.10
              used_by: LOGIN
              secret: "{{ radius_shared_secret }}"

    - name: Create a Secure RADIUS profile
      extreme.fe.extreme_fe_radius:
        state: merged
        config:
          secure_profiles:
            - name: radsecprofile
              root_cert: |
                -----BEGIN CERTIFICATE-----
                ZHVtbXktcm9vdC1jZXJ0aWZpY2F0ZQ==
                -----END CERTIFICATE-----
              cert: |
                -----BEGIN CERTIFICATE-----
                ZHVtbXktY2xpZW50LWNlcnRpZmljYXRl
                -----END CERTIFICATE-----
              key: |
                -----BEGIN RSA PRIVATE KEY-----
                ZHVtbXktY2xpZW50LXByaXZhdGUta2V5
                -----END RSA PRIVATE KEY-----
              password: dummy-radius-pass

    - name: Override the complete configuration
      extreme.fe.extreme_fe_radius:
        state: overridden
        config:
          global:
            enabled: true
          servers:
            - server_mode: AAA
              host_type: IPv4
              address: 192.0.2.9
              used_by: LOGIN
              secret: "{{ radius_shared_secret }}"
          secure_profiles: []

    - name: Replace the dynamic authorization client set
      extreme.fe.extreme_fe_radius:
        state: replaced
        config:
          servers:
            - server_mode: AAA
              host_type: IPv4
              address: 192.0.2.10
              used_by: LOGIN
              secret: "{{ radius_shared_secret }}"
            - server_mode: DYN_AUTH
              host_type: IPv4
              address: 192.0.2.20
              secret: "{{ radius_dynamic_secret }}"
              enabled: true
              port: 3799

    - name: Remove the dynamic authorization client
      extreme.fe.extreme_fe_radius:
        state: deleted
        config:
          servers:
            - server_mode: DYN_AUTH
              host_type: IPv4
              address: 192.0.2.20


    - name: Override the complete configuration
      extreme.fe.extreme_fe_radius:
        state: overridden
        config:
          global:
            enabled: true
          servers:
            - server_mode: AAA
              host_type: IPv4
              address: 192.0.2.9
              used_by: LOGIN
              secret: "{{ radius_shared_secret }}"
          secure_profiles: []
```

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Vlad-Leonard Mocanu ([@vmocanu_extr](https://github.com/vmocanu_extr))
