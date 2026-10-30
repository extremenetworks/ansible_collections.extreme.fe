# Network Time Protocol (NTP)

## Module: extreme.fe.extreme_fe_ntp_global

Manages global Network Time Protocol settings on Fabric Engine devices.

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

This module manages the Network Time Protocol configuration on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports the Ansible states: merged, replaced, overridden, deleted and gathered.
- Manages the global NTP admin state, the poll interval and the list of NTP servers.
- NTP servers are identified by a host name, an IPv4 address or an IPv6 address.
- The REST API exposes only GET and PUT for NTP - there is no PATCH and there are no per-server POST or DELETE endpoints. Every state is therefore applied as a read-modify-write: the module reads the current settings, folds the supplied `config` into them according to the requested state, and replaces the virtual router configuration with a single PUT.
- The PUT is skipped when the desired configuration already matches the device, so every state is idempotent.
- IPv6 addresses are normalized to their compressed canonical form, so `2001:0db8:0000::1` and `2001:db8::1` are recognised as the same server.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- Each server may be listed once in `config.servers`. An address is compared in its canonical form (an IPv6 address in any notation, a host name in any case), so the same server written twice fails before any request.
- A PUT that fails without an answer (a lost connection) may have been applied, so the task reports `changed: true` with `details.outcome: unknown`.
- `host_type` is validated against `address`. Tagging an IP address as `hostname` is rejected, as is
  tagging an IPv4 address `IPv6` or the reverse — the discriminator is sent to the device as given, so a
  mismatch would be written under the wrong type and would also skip IP canonicalization, breaking
  idempotency. Omit `host_type` to have it detected from the address.
- When the device reports no NTP configuration at all, the module warns and treats the device as
  unconfigured, returning factory defaults rather than failing.
- The OpenAPI schema marks `vrName` as read-only and states that it is ignored on Fabric Engine, where the NTP properties are global. The PUT endpoint still requires the virtual router in the URL, so `vr_name` is a required parameter. It is never sent in the request body.
- `vr_name` is normalized the same way `extreme_fe_vrf` normalizes VRF names, using the collection's shared `normalize_vrf_name()` helper, because the REST path is case-sensitive. User virtual router names are lowercased and the system routers are mapped to their canonical casing, so `globalrouter` and `GlobalRouter` both reach `/v0/configuration/ntp/GlobalRouter`. Supplying a mixed-case name that has to be converted raises a warning.
- The normalized `vr_name` is then matched case-insensitively against the virtual routers the device reports. For the action states, a `vr_name` the device does not report fails the task and the error lists the names that are available - this prevents writing to the wrong resource. That check only applies when the device reports virtual routers at all; on a device with no NTP configuration anywhere the factory defaults are used as the baseline, so a first-time configuration works. For `gathered` a missing `vr_name` raises a warning and returns the factory-default values.
- Server addresses are canonicalized before they are compared, so the same server is recognised however it is spelled. IP addresses are put in their canonical form and host names are lowercased, DNS being case-insensitive; both are reported and sent to the device in that form.
- `poll_interval` is an exponent - the interval between NTP updates in seconds is 2 raised to the power of this value. The factory default of `8` is therefore 256 seconds.
- `gathered`, `before` and `after` contain only the `config` option fields (`enabled`, `poll_interval`, `servers`), so `gathered` can be passed back as `config`. The virtual router is reported in the separate top-level `vr_name` result.
- Supports check mode and diff mode. Under `--diff` the module reports the whole NTP configuration before and after the change; combined with `--check` the reported "after" is the state that would have been written.
- A rejected PUT fails the task with `changed=false`. When the PUT succeeds but the re-read that follows it fails, the task fails with `changed=true` and a message saying the configuration was applied.
- The broadcast client setting and the per-server NTP version, minimum poll and maximum poll attributes are Switch Engine (EXOS) only and are not supported by this module.
- `merged` never enables a server that is currently disabled unless `config[].servers[].enabled` is supplied explicitly.
- `deleted` with a `config` that contains an empty `servers` list removes nothing. Omit `config`, or give it with no option set (`{}`), to reset the whole NTP configuration.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/ntp | Get the NTP settings for every virtual router |
| PUT | /v0/configuration/ntp/{vr_name} | Replace the NTP configuration for the virtual router specified |

---

## [Platform Constraints](#table-of-contents)

- No PATCH method exists for NTP, so each change replaces the complete NTP configuration of the virtual router.
- `vrName` is read-only and is ignored on Fabric Engine, where the NTP properties are global.
- The `{vr_name}` path segment is case-sensitive - the system virtual routers must be addressed as `GlobalRouter` and `MgmtRouter`. The module normalizes the supplied name to that form.
- `poll_interval` accepts 4 to 17 only.
- `vr_name` accepts 1 to 16 characters. The OpenAPI spec allows 32, but the device firmware rejects longer virtual router names.
- The broadcast client setting, and the per-server `version`, `minPoll` and `maxPoll` attributes, are Switch Engine (EXOS) only and are not exposed by this module.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state: `merged`, `replaced`, `overridden`, `deleted` or `gathered` |
| `vr_name` | str | Yes | - | Virtual router whose NTP configuration is managed (1-16 characters, normally `GlobalRouter`). Normalized to canonical casing before the REST path is built |
| `config` | dict | Yes (merged/replaced/overridden) | - | NTP settings to manage. A `config` with no option set (for example `{}`) counts as omitted for these states and fails before any request |
| `config.enabled` | bool | No | - | Global NTP admin state. Left alone when omitted, except for `overridden` which resets it to `false` |
| `config.poll_interval` | int | No | - | Update interval exponent, 4 to 17. Left alone when omitted, except for `overridden` which resets it to `8` |
| `config.servers` | list of dict | No | - | NTP servers for the virtual router |
| `config.servers[].address` | str | Yes | - | Host name, IPv4 address or IPv6 address of the server |
| `config.servers[].host_type` | str | No | derived from `address` | `hostname`, `IPv4` or `IPv6`. A value that contradicts `address` fails the task — including tagging an IP address as `hostname` |
| `config.servers[].enabled` | bool | No | - | Server admin state. An existing server keeps its current state, a newly added server is enabled |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply the supplied fields and add the supplied servers. Nothing already on the device is removed, and fields that are not supplied keep their current value. | GET, PUT |
| `replaced` | The supplied `servers` list becomes the complete server list for the virtual router - unlisted servers are removed and missing ones are added. Scalar fields that are not supplied keep their current value. Omitting the `servers` key leaves the current list alone. | GET, PUT |
| `overridden` | Enforce the supplied configuration exactly. Every field and every server not supplied is reset to its factory default. | GET, PUT |
| `deleted` | Reset to factory defaults. With a `config`, only the servers listed in it are removed and only the scalar fields named in it are reset. | GET, PUT |
| `gathered` | Read-only output. | GET |

---

## [Factory Defaults](#table-of-contents)

| Field | Default Value | Source |
|-------|---------------|--------|
| `enabled` | `false` | OpenAPI spec, `NtpSettingsByVr.enabled` |
| `poll_interval` | `8` | OpenAPI spec, `NtpSettingsByVr.pollInterval` |
| `servers` | `[]` | No NTP servers are preconfigured at factory reset |
| `servers[].enabled` | `true` | OpenAPI spec, `NtpServer.enabled` |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether the NTP configuration changed |
| `before` | dict | NTP configuration before changes (action states) |
| `after` | dict | NTP configuration after changes (returned for every action state; equals `before` when nothing changed, and is the predicted state in check mode) |
| `gathered` | dict | Current NTP configuration in the `config` option shape (returned for `state=gathered`); it can be passed back as `config` |
| `vr_name` | str | Virtual router the reported configuration belongs to, as the device names it (always returned); pass it back as the `vr_name` option |
| `ntp_global.before` | dict | NTP configuration before the requested change |
| `ntp_global.after` | dict | NTP configuration after the requested change |
| `ntp_global.config` | dict | Gathered NTP configuration |
| `ntp_global.differences` | dict | Changed attributes with their before and after values |
| `submitted` | dict | The PUT path and body sent to the device when a change was required |

### Output Fields

`before`, `after`, `gathered` and `ntp_global.before`/`after`/`config` contain only the `config` option fields below; the virtual router is the separate top-level `vr_name` result.

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Global NTP admin state |
| `poll_interval` | int | Update interval exponent (interval in seconds is 2 to this power) |
| `servers[].address` | str | Host name or IP address of the server |
| `servers[].host_type` | str | `hostname`, `IPv4` or `IPv6` |
| `servers[].enabled` | bool | Server admin state |

---

## [Examples](#table-of-contents)

### Enable NTP and add servers

```yaml
- name: Enable NTP and add two servers
  extreme.fe.extreme_fe_ntp_global:
    state: merged
    vr_name: GlobalRouter
    config:
      enabled: true
      poll_interval: 10
      servers:
        - address: 10.10.10.1
          host_type: IPv4
        - address: time.example.com
          host_type: hostname
```

### Replace the server list

`host_type` may be omitted - it is derived from the address.

```yaml
- name: Make the listed servers the complete server list
  extreme.fe.extreme_fe_ntp_global:
    state: replaced
    vr_name: GlobalRouter
    config:
      servers:
        - address: 10.10.10.1
        - address: 2001:db8::1
```

### Disable a single server without removing it

```yaml
- name: Administratively disable one NTP server
  extreme.fe.extreme_fe_ntp_global:
    state: merged
    vr_name: GlobalRouter
    config:
      servers:
        - address: 10.10.10.1
          enabled: false
```

### Override the entire NTP configuration

Everything not listed is reset to its factory default, so `poll_interval` returns to `8`.

```yaml
- name: Enforce the exact NTP configuration
  extreme.fe.extreme_fe_ntp_global:
    state: overridden
    vr_name: GlobalRouter
    config:
      enabled: true
      servers:
        - address: 10.10.10.1
```

### Delete NTP configuration

```yaml
- name: Remove one NTP server
  extreme.fe.extreme_fe_ntp_global:
    state: deleted
    vr_name: GlobalRouter
    config:
      servers:
        - address: 10.10.10.1

- name: Reset the whole NTP configuration to factory defaults
  extreme.fe.extreme_fe_ntp_global:
    state: deleted
    vr_name: GlobalRouter
```

### Gather NTP configuration

```yaml
- name: Collect the current NTP configuration
  extreme.fe.extreme_fe_ntp_global:
    state: gathered
    vr_name: GlobalRouter
  register: ntp_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage NTP configuration
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current NTP configuration
      extreme.fe.extreme_fe_ntp_global:
        state: gathered
        vr_name: GlobalRouter
      register: ntp_before

    - name: Enable NTP and add two servers
      extreme.fe.extreme_fe_ntp_global:
        state: merged
        vr_name: GlobalRouter
        config:
          enabled: true
          poll_interval: 10
          servers:
            - address: 10.10.10.1
              host_type: IPv4
            - address: time.example.com
              host_type: hostname

    - name: Make the listed servers the complete server list
      extreme.fe.extreme_fe_ntp_global:
        state: replaced
        vr_name: GlobalRouter
        config:
          servers:
            - address: 10.10.10.1
            - address: 2001:db8::1

    - name: Enforce the exact NTP configuration
      extreme.fe.extreme_fe_ntp_global:
        state: overridden
        vr_name: GlobalRouter
        config:
          enabled: true
          servers:
            - address: 10.10.10.1

    - name: Reset the whole NTP configuration to factory defaults
      extreme.fe.extreme_fe_ntp_global:
        state: deleted
        vr_name: GlobalRouter

    - name: Gather NTP configuration after changes
      extreme.fe.extreme_fe_ntp_global:
        state: gathered
        vr_name: GlobalRouter
      register: ntp_after
```

---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
