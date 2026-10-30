# Web Server

## Module: extreme.fe.extreme_fe_web

Manages the web-server service on Fabric Engine devices.

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

This module manages the web-server service on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports the Ansible states `merged`, `replaced`, `overridden`, `deleted`, and `gathered`.
- Manages only `enabled` and `secure_only` in the initial implementation.
- Preserves all other web-server and system-services attributes exposed by the API.
- Sends an idempotent nested `webServer` PATCH only when a supported value differs.

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2. The `secure_only` factory default is based on reports from Fabric Engine 9.4 and 9.5 and has not been tested there.
- **You can lock yourself out:** this collection talks to the switch through its web server. Disabling the web server, or turning on `secure_only` while you connect over plain HTTP, can cut off the current task and every later one. `deleted`, `replaced` and `overridden` do this too when you leave out `enabled` (default `false`) or `secure_only` (default `true`). Keep another way to reach the switch before running such a task.
- **`replaced` and `overridden` are the same:** the web server settings are a single resource, so both reset every setting you leave out to its factory default (`enabled: false`, `secure_only: true`).
- **Re-applying `gathered`:** `gathered` can be passed back as `config` and changes nothing. If the switch does not report one of the two settings, `gathered` fails instead of returning an incomplete result.
- **Lost connections:** if the connection drops during a change (for example because the change disabled the web server) and the module cannot confirm the result, it reports `changed: true` with `details.outcome: unknown`, because the change may have been applied.
- **Partly applied changes:** if the switch rejects a change after applying part of it, the error message lists which settings were applied and which were not.
- Supports check mode (`--check`) and diff mode (`--diff`).

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/system-services | Get system-services settings and extract `webServer` |
| PATCH | /v0/configuration/system-services | Update changed supported `webServer` attributes |

## [Platform Constraints](#table-of-contents)

- This module targets Fabric Engine (VOSS).
- Only the `enabled` and `secureOnly` REST attributes are supported in this release.
- Web-server ports, timeouts, TLS version, SSL renegotiation, certificates, and user credentials are outside the scope of this module and are preserved.
- The API represents web-server settings as a nested object inside the singleton System Services resource.

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state: `merged`, `replaced`, `overridden`, `deleted`, or `gathered` |
| `config` | dict | Yes for merged/replaced/overridden | - | Supported web-server configuration to manage |
| `config.enabled` | bool | No | - | Whether the web-server service is enabled |
| `config.secure_only` | bool | No | - | Whether only secure HTTPS connections are accepted. The factory default is `true`: `deleted`, and `replaced` / `overridden` without it, set it to `true` |

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Update only supplied supported attributes and preserve omitted values. | GET, PATCH |
| `replaced` | Treat the supplied supported configuration as complete; reset omitted supported attributes to defaults. | GET, PATCH |
| `overridden` | Enforce the complete supported singleton configuration; equivalent to `replaced`. | GET, PATCH |
| `deleted` | Reset selected attributes to defaults, or reset all supported attributes when `config` is omitted. | GET, PATCH |
| `gathered` | Return only the supported current web-server configuration without modifying the device. | GET |

## [Factory Defaults](#table-of-contents)

| Field | Default Value | Source |
|-------|---------------|--------|
| `enabled` | `false` | Confirmed VOSS device default; not declared by OpenAPI 9.4.2 |
| `secure_only` | `true` | Fabric Engine factory default (HTTPS only): `show web-server` reports `Secure-only : enabled` at factory settings, and only `secureOnly: false` adds a line (`no web-server secure-only`) to the running configuration (9.4 and 9.5); not declared by OpenAPI 9.4.2 |

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Always returned. Indicates whether configuration changed or would change in check mode. It is `false` for `gathered` and idempotent action-state runs. |
| `before` | dict | Returned for every state except `gathered`. Contains the supported configuration read before action-state processing. |
| `after` | dict | Returned for every state except `gathered`. Contains the post-change GET snapshot, the predicted snapshot in check mode, or the current configuration when unchanged. |
| `gathered` | dict | Returned only for `gathered`. Contains the current supported configuration in the `config` option shape, always with both `enabled` and `secure_only` (the gather fails when the device does not report one of them). |
| `web` | dict | Always returned. Contains `config` for `gathered`, or `before`, `after`, and `differences` for action states. |
| `web.before` | dict | Returned for action states. Same configuration as top-level `before`. |
| `web.after` | dict | Returned for action states. Same value as top-level `after`, including the current configuration when unchanged. |
| `web.config` | dict | Returned only for `gathered`. Same configuration as top-level `gathered`. |
| `web.differences` | dict | Returned for action states. Contains changed supported attributes with before/after values, or `{}` when unchanged. |

## [Examples](#table-of-contents)

### Merge Selected Settings

```yaml
- name: Enable the web server without changing secure-only mode
  extreme.fe.extreme_fe_web:
    state: merged
    config:
      enabled: true
```

### Replace Supported Settings

```yaml
- name: Replace the supported web-server configuration
  extreme.fe.extreme_fe_web:
    state: replaced
    config:
      enabled: true
      secure_only: true
```

### Override Supported Settings

```yaml
- name: Enforce HTTPS-only web access and reset enabled to default
  extreme.fe.extreme_fe_web:
    state: overridden
    config:
      secure_only: true
```

### Delete Selected Settings

```yaml
- name: Reset secure-only mode to its default (HTTPS only)
  extreme.fe.extreme_fe_web:
    state: deleted
    config:
      secure_only: true
```

### Delete All Supported Settings

```yaml
- name: Reset all supported web-server settings
  extreme.fe.extreme_fe_web:
    state: deleted
```

### Gather Settings

```yaml
- name: Gather web-server configuration
  extreme.fe.extreme_fe_web:
    state: gathered
  register: web_server_info
```

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
---
- name: Manage the Fabric Engine web-server service
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:
    - name: Enforce secure web-server access
      extreme.fe.extreme_fe_web:
        state: overridden
        config:
          enabled: true
          secure_only: true

    - name: Gather web-server configuration
      extreme.fe.extreme_fe_web:
        state: gathered
      register: web_server_info
```

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Vlad-Leonard Mocanu ([@vmocanu_extr](https://github.com/vmocanu_extr))
