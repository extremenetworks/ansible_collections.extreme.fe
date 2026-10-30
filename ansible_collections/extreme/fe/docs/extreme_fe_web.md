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

- Tested against Fabric Engine Version 9.3.2. The fix for the secure_only factory default is based on reports from Fabric Engine 9.4 and 9.5; it has not been tested on those versions.
- A PATCH that fails without an answer (for example because disabling the web server cut the session) may have been applied. When it cannot be re-read, or the re-read omits an attempted field, the task reports `changed: true` with `details.outcome: unknown`.
- The OpenAPI schema does not declare defaults for `webServer.enabled` or `webServer.secureOnly`; the reset values in this module are the Fabric Engine factory defaults (`enabled: false`, `secure_only: true`).
- `replaced` and `overridden` are equivalent because the web-server configuration is a singleton resource with no supported sub-resources.
- The `gathered` state returns only the supported web-server configuration.
- `gathered`, `before`, and `after` always contain both `enabled` and `secure_only`. A value the device does not report (or reports as null) is unknown: it is `null` in `before` and `after`, a requested value for it is always sent, and `gathered` fails rather than publishing it. A complete `gathered` can be passed back as `config`, and re-applying it changes nothing.
- Supports check mode and diff mode. In check mode, changed operations return the predicted configuration without sending a PATCH. An unchanged action-state operation returns the current configuration in `after` and `diff.after`.
- **Warning:** the REST API session used by this collection can depend on the device web server. Disabling the web server (`enabled: false`), which `deleted`, `replaced`, and `overridden` also do when `enabled` is omitted, can cut off that session and every later task on the device; enabling `secure_only`, which the same states also do when `secure_only` is omitted (its factory default is `true`), can do the same for an HTTP (non-HTTPS) connection. Keep the device reachable through another management path before running such a task.
- Both supported attributes are sent in one PATCH. If the device rejects it, the module re-reads the system-services configuration and the failure reports in `details.applied_fields` and `details.not_applied_fields` which REST fields (`webServer.enabled`, `webServer.secureOnly`) the device applied, with `details.attempted_payload`, `details.status_code` and `details.resource`; the task reports `changed: true` when any field was applied. If the re-read fails too, for example because the PATCH has just disabled the web server, `details.reread_error` says why and nothing is attributed, with `details.reread_error_code` when the device gave a numeric error code. An error document in a 2xx answer, to the GET or to the PATCH, is reported by its numeric code only, never by its message or payload, which could quote a stored credential. A re-read that does not report an attempted field (or reports it as null) lists it in `details.unknown_fields`, without assuming a default, and still attributes the fields it reports (one that reports none of them counts as a failed re-read).

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
