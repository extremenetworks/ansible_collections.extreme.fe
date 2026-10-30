# Syslog

## Module: extreme.fe.extreme_fe_syslog

Manages syslog configuration on Fabric Engine devices.

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

This module manages the global syslog admin state and the syslog servers list on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports the Ansible states: merged, replaced, overridden, deleted and gathered.
- Manages the global `enabled` flag and the complete list of syslog servers.
- `/v0/configuration/syslog` exposes `PATCH` for the global `enabled` flag only. `/v0/configuration/syslog/servers` exposes `PUT` only, and always replaces the complete servers list - there is no per-server `PATCH`, `POST` or `DELETE`.
- A single task may change both `enabled` and `servers`; each is sent as its own request and each is skipped independently when that part of the configuration already matches the device.
- Each syslog server is identified by `host_id`, matching the VOSS CLI's `syslog host <1-10>`.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- A PATCH or PUT that fails without an answer (a lost connection) may have been applied, so the task reports `changed: true` with `details.outcome: unknown`.
- `enabled` (the global syslog admin state) is marked with the OpenAPI attribute `x-nos=fabric-engine`, meaning it applies only to Fabric Engine (VOSS), which matches this collection's target platform.
- `config.servers[].vr_name` does not exist in this module - the REST `vrName` field is marked `x-nos=switch-engine` (Switch Engine/EXOS only) and is never read or written.
- Secure forwarding (mode, TCP port, server certificate name) and `syslog max-hosts` are documented in the Fabric Engine CLI but are not present anywhere in the OpenAPI schema for these two endpoints, so this module never reads or writes them.
- `config.servers[].host_id` is the resource identifier for a syslog server, matching the VOSS CLI's `syslog host <1-10>`. The OpenAPI spec types it as a 1-10 character string; the VOSS CLI further restricts it to the decimal range 1-10, confirmed against a live device, and that firmware-confirmed range is what this module enforces.
- `config.servers[].address` is required on every server entry for `merged`, `replaced` and `overridden`, including one that already exists on the device. There is no per-server `PATCH`, so every write is a full read-modify-write of the whole servers list, and requiring the address on every entry avoids inventing a "required only when creating" rule.
- `config.servers[].port` accepts the OpenAPI-documented Fabric Engine (VOSS) range of 514-530, confirmed by the User Guide's `udp-port <514-530>` parameter and by a live device. This is narrower than the OpenAPI schema's raw `0-65535` bounds, which describe the field's general type rather than the Fabric Engine-specific range stated in the same field's description.
- Neither `config.servers[].port`, `config.servers[].enabled`, `config.servers[].facility` nor `config.servers[].log_level` has a documented OpenAPI default. All four factory defaults, and the global `config.enabled` default, were confirmed against a live device rather than assumed.
- For `replaced` and `overridden`, the servers list is treated as a set - the supplied `servers` list (when that key is present in config at all) becomes the complete list, and any server on the device but not in it is removed. `replaced` leaves the current list untouched only when `servers` is omitted from config entirely; `overridden` always treats an omitted `servers` key as "no servers desired" (a full wipe). The two states therefore behave identically for the servers list whenever `servers` is supplied, and differ only in how they treat the scalar `enabled` field when it is omitted.
- Supports check mode and diff mode. Under `--diff` the module reports the syslog configuration before and after the change; combined with `--check` the reported "after" is the state that would have been written.
- The admin state (`enabled`, a PATCH) and the servers list (a PUT) are two requests. When the PUT fails after the PATCH succeeded, the task fails with `changed=true` and a message saying the admin state was already applied. A failure of the first request reports `changed=false`; a failure of the re-read after the writes reports `changed=true`.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/syslog | Get the syslog settings for the device |
| PATCH | /v0/configuration/syslog | Update the global syslog configuration |
| PUT | /v0/configuration/syslog/servers | Replace the syslog servers configuration |

---

## [Platform Constraints](#table-of-contents)

- `/v0/configuration/syslog` PATCH accepts only `enabled`; the servers list is managed exclusively through the separate `/v0/configuration/syslog/servers` PUT endpoint.
- `/v0/configuration/syslog/servers` PUT always replaces the complete servers list - there is no per-server PATCH, POST or DELETE.
- `host_id` accepts the decimal range 1-10 (VOSS CLI `syslog host <1-10>`), narrower than the OpenAPI schema's raw 1-10 character string bound.
- `port` accepts 514-530 (Fabric Engine (VOSS) range), narrower than the OpenAPI schema's raw 0-65535 bounds.
- `vr_name` (REST `vrName`) is Switch Engine (EXOS) only and is not exposed by this module.
- `log_level` accepts any combination of the 8 severity values, but Fabric Engine stores only four (OpenAPI `SeverityLevels`, confirmed on 9.4 and 9.5): `EMERGENCY` and `ALERT` are stored and read back as `CRITICAL`, `NOTICE` and `DEBUG` as `INFORMATIONAL`. The module maps the requested levels the same way before it compares and sends them, and warns when it mapped one, so a repeated task reports no change. `before`, `after` and `gathered` show the stored levels.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state: `merged`, `replaced`, `overridden`, `deleted` or `gathered` |
| `config` | dict | Yes (merged/replaced/overridden) | - | Syslog configuration to manage. A `config` with no option set (for example `{}`) counts as omitted for these states and fails before any request |
| `config.enabled` | bool | No | - | Global syslog admin state. Left alone when omitted, except for `overridden` which resets it to `true` |
| `config.servers` | list of dict | No | - | List of syslog servers |
| `config.servers[].host_id` | str | Yes | - | Identifier of the syslog host slot (1-10), matching the VOSS CLI `syslog host <1-10>`. Compared as a number, so `"01"` and `"1"` name the same server |
| `config.servers[].address` | str | Yes (merged/replaced/overridden) | - | IPv4 or IPv6 address of the syslog server |
| `config.servers[].address_type` | str | No | derived from `address` | `IPv4` or `IPv6`. A value that contradicts `address` fails the task |
| `config.servers[].port` | int | No | - | UDP port, 514-530. Left alone when omitted for an existing server, defaulted to `514` for a new one, or for `overridden` |
| `config.servers[].enabled` | bool | No | - | Per-server admin state. Follows the same omitted-value rule as `port` |
| `config.servers[].facility` | str | No | - | UNIX syslog facility: `LOCAL0`-`LOCAL7`. Follows the same omitted-value rule as `port` |
| `config.servers[].log_level` | list of str | No | - | Severity levels: `EMERGENCY`, `ALERT`, `CRITICAL`, `ERROR`, `WARNING`, `NOTICE`, `INFORMATIONAL`, `DEBUG`. Follows the same omitted-value rule as `port`. Treated as a set - order and duplicates are ignored, and levels are reported in severity order. Fabric Engine stores `EMERGENCY` and `ALERT` as `CRITICAL`, `NOTICE` and `DEBUG` as `INFORMATIONAL`; the module applies the same mapping and warns when it does |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply the supplied `enabled`. Add or update the supplied servers; servers already on the device that are not mentioned are kept as-is. | GET, PATCH, PUT |
| `replaced` | Apply the supplied `enabled` (left alone if omitted). If `servers` is supplied, it becomes the complete servers list - unlisted servers are removed. If `servers` is omitted, the current list is left untouched. | GET, PATCH, PUT |
| `overridden` | Apply `enabled` or reset it to its factory default if omitted. The supplied `servers` (empty if omitted) becomes the complete servers list. | GET, PATCH, PUT |
| `deleted` | With `config`, only the fields/servers named are reset or removed. Without `config` (or with no option set, `{}`), the whole syslog configuration is reset to factory defaults. | GET, PATCH, PUT |
| `gathered` | Read-only output. | GET |

---

## [Factory Defaults](#table-of-contents)

| Field | Default Value | Source |
|-------|---------------|--------|
| `enabled` (global) | `true` | Not in OpenAPI spec. Confirmed via the User Guide's `syslog enable` default and a live device GET response |
| `servers` | `[]` | No syslog servers are preconfigured at factory reset |
| `servers[].port` | `514` | OpenAPI field description states the Fabric Engine (VOSS) default is `514`; confirmed by the User Guide and a live device |
| `servers[].enabled` | `false` | Not in OpenAPI spec. Confirmed via the User Guide and a live device GET response |
| `servers[].facility` | `LOCAL7` | Not in OpenAPI spec. Confirmed via the User Guide and a live device GET response |
| `servers[].log_level` | `[CRITICAL, ERROR, WARNING, INFORMATIONAL]` | Not in OpenAPI spec. Confirmed directly against a live device GET response for a server created with no `log_level` supplied |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether the syslog configuration changed |
| `before` | dict | Syslog configuration before changes (action states) |
| `after` | dict | Syslog configuration after changes (returned for every action state; equals `before` when nothing changed, and is the predicted state in check mode) |
| `gathered` | dict | Current syslog configuration (returned for `state=gathered`) |
| `syslog.before` | dict | Syslog configuration before the requested change |
| `syslog.after` | dict | Syslog configuration after the requested change |
| `syslog.config` | dict | Gathered syslog configuration |
| `syslog.differences` | dict | Changed fields with their before and after values |
| `submitted` | dict | The PATCH and/or PUT paths and bodies sent to the device when a change was required |

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Global syslog admin state |
| `servers[].host_id` | str | Identifier of the syslog host slot |
| `servers[].address` | str | IPv4 or IPv6 address of the server |
| `servers[].address_type` | str | `IPv4` or `IPv6` |
| `servers[].port` | int | UDP port |
| `servers[].enabled` | bool | Per-server admin state |
| `servers[].facility` | str | UNIX syslog facility |
| `servers[].log_level` | list of str | Severity levels sent to this server |

---

## [Examples](#table-of-contents)

### Enable syslog globally and add a server

```yaml
- name: Enable syslog globally and add a server
  extreme.fe.extreme_fe_syslog:
    state: merged
    config:
      enabled: true
      servers:
        - host_id: "1"
          address: 10.10.10.1
          port: 514
          enabled: true
          facility: LOCAL7
          log_level: [ERROR, CRITICAL]
```

### Update one server without touching the others

```yaml
- name: Update one server without touching the others
  extreme.fe.extreme_fe_syslog:
    state: merged
    config:
      servers:
        - host_id: "1"
          address: 10.10.10.1
          enabled: false
```

### Replace the server list

```yaml
- name: Make the listed servers the complete server list
  extreme.fe.extreme_fe_syslog:
    state: replaced
    config:
      servers:
        - host_id: "1"
          address: 10.10.10.1
        - host_id: "2"
          address: "2001:db8::1"
```

### Override the entire syslog configuration

```yaml
- name: Enforce the exact syslog configuration
  extreme.fe.extreme_fe_syslog:
    state: overridden
    config:
      enabled: true
      servers:
        - host_id: "1"
          address: 10.10.10.1
```

### Delete syslog configuration

```yaml
- name: Remove one syslog server
  extreme.fe.extreme_fe_syslog:
    state: deleted
    config:
      servers:
        - host_id: "1"

- name: Reset the whole syslog configuration to factory defaults
  extreme.fe.extreme_fe_syslog:
    state: deleted
```

### Gather syslog configuration

```yaml
- name: Collect the current syslog configuration
  extreme.fe.extreme_fe_syslog:
    state: gathered
  register: syslog_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage syslog configuration
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current syslog configuration
      extreme.fe.extreme_fe_syslog:
        state: gathered
      register: syslog_before

    - name: Enable syslog globally and add a server
      extreme.fe.extreme_fe_syslog:
        state: merged
        config:
          enabled: true
          servers:
            - host_id: "1"
              address: 10.10.10.1
              port: 514
              enabled: true
              facility: LOCAL7
              log_level: [ERROR, CRITICAL]

    - name: Make the listed servers the complete server list
      extreme.fe.extreme_fe_syslog:
        state: replaced
        config:
          servers:
            - host_id: "1"
              address: 10.10.10.1
            - host_id: "2"
              address: "2001:db8::1"

    - name: Enforce the exact syslog configuration
      extreme.fe.extreme_fe_syslog:
        state: overridden
        config:
          enabled: true
          servers:
            - host_id: "1"
              address: 10.10.10.1

    - name: Reset the whole syslog configuration to factory defaults
      extreme.fe.extreme_fe_syslog:
        state: deleted

    - name: Gather syslog configuration after changes
      extreme.fe.extreme_fe_syslog:
        state: gathered
      register: syslog_after
```

---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
