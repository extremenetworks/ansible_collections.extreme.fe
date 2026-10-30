# Ethernet Interfaces

## Module: extreme.fe.extreme_fe_interfaces

Manages Ethernet interfaces on Fabric Engine devices.

---

Version added: 1.0.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Parameters](#parameters)
- [State Behaviour Summary](#state-behaviour-summary)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

Through this module administrative state, global interface settings, and per-port attributes can be configured on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- The module supports enabling or disabling multiple ports, adjusting global port flags, and tuning per-port features such as speed, duplex, EEE, and Fabric Engine specific options.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- Each port may be listed once in `config`; a port listed twice fails before any request.
- A write that fails without an answer (a lost connection) and cannot be re-read may have been applied, so the task reports `changed=true` with `details.outcome=unknown`.
- Port names must use slot and port notation such as `1:5`.
- Setting `auto_negotiation` to `false` is rejected for a port whose capabilities report an empty `autoNegOffSupportedSpeedDuplexList` (for example 7520-48XT-6C copper ports), because the device cannot disable auto-negotiation there. The task fails before any port is modified, also in check mode.
- Supports check mode and diff mode. Under `--diff` the module reports the per-port configuration of the whole device before and after the change, including ports that `overridden` resets to defaults; combined with `--check` the reported `after` is the state that would have been written.
- Each port update and the global settings update is sent as one PATCH carrying every changed field. The device can apply part of such a request and still reject it, so on a rejected update the module re-reads the port (or the global settings) and reports which fields were and were not applied. The failure message names them, `details` carries `attempted_payload`, `applied_fields`, `not_applied_fields`, `status_code` and `resource`, and `changed` is `true` when any field was applied. If the re-read fails too, `details` carries `reread_error` and which fields were applied is unknown.
- The admin state of the `admin` ports is written with one PUT to `/v0/configuration/ports`, and `deleted` and `overridden` reset a port with one PUT of its default values. A rejected PUT is attributed the same way, the admin flags as `<port>.enabled`. For a reset, the fields the port already held at their default are listed in `unchanged_fields` and never count as applied. A reset that `overridden` skips with a warning still reports `changed: true` when the re-read shows part of it applied.
- A task that fails after one of its writes succeeded (the global settings PATCH, the admin PUT, a port PATCH or reset PUT) reports `changed: true`, whichever later request or read-back failed, and the failure message lists the writes already applied.
- `state: deleted` with neither `config` nor `admin` resets every port the device lists to its defaults, except the admin state (`enabled`), which is left alone so a port that was shut down stays down; the global settings are not touched either. Protected ports are skipped, each with a warning naming the port and the reason, and listed in `skipped_interfaces`. They are the out-of-band management port (`mgmt` or `<slot>:mgmt`, or flagged `managementPort` in the port capabilities), every port that is a tagged or untagged member of a management VLAN (`isMgmtInterface` in `/v0/configuration/vlan`), and the member ports of a LAG that is a member of one (`/v0/configuration/lag`). A port the device refuses to reset is skipped with a warning and listed there too.
- `overridden` protects the same ports when it resets the ports absent from `config`, with the same warning and the same `skipped_interfaces` list. A port named in `config` is always applied as `replaced`, protected or not.
- The VLAN list, and the LAG list when a management VLAN has a LAG member, are read before anything is written, and only when at least one swept port would be reset (it is not at its defaults, or `admin` names it). If either read fails the task fails without changing the device, also in check mode, so the management connection is never put at risk; list the ports in `config` to change them instead. A management-VLAN LAG whose record is missing from the LAG list, or has no `memberPorts` list (absent, not a list, or with a blank or non-string member name), fails the task the same way, since its member ports could not be protected; an empty list is a memberless LAG.
- The port capabilities (`/v0/state/capabilities/system/ports`), which flag `managementPort`, are read at the same point. On firmware without that endpoint (HTTP 404) the management port is identified by its name only, with a warning. Any other failure of that read fails the task the same way, without changing the device.
- `merged` and `replaced` fail before any request when `config`, `global_settings` and `admin` are all omitted or empty; a task that sets only `global_settings` or only `admin` is valid. `overridden` fails before any request when `config` is omitted or empty, because it would otherwise reset every unprotected port. `deleted` without `config` keeps resetting every unprotected port, as described above.
- `state: gathered` returns the per-port configuration under `gathered`, in the form `config` accepts, so `config: "{{ result.gathered }}"` can be applied back unchanged; re-applying an unfiltered result (no `gather_filter`) with `merged`, `replaced` or `overridden` changes nothing. With `gather_filter` the result lists only the selected ports: it is still safe to re-apply with `merged` or `replaced`, but `overridden` takes it as the complete port list and resets every unlisted port that is not protected, so re-apply a filtered result with `overridden` only to do that. The operational interface state is still returned under `ports_state`, as before; it is not configuration and cannot be supplied back as `config`.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/ports | Retrieve all port configurations |
| PUT | /v0/configuration/ports | Update multiple port admin statuses |
| PATCH | /v0/configuration/ports/{port} | Update specific port settings |
| PUT | /v0/configuration/ports/{port} | Reset a port to its default settings (`deleted`, `overridden`) |
| GET | /v0/configuration/ports/global | Get global port settings |
| PATCH | /v0/configuration/ports/global | Update global port settings |
| GET | /v0/configuration/ports/{port} | Re-read one port's full configuration (also for `gathered`, when the bulk listing omits a field) |
| GET | /v1/state/ports | Get port state (`ports_state`, `gathered` only) |
| GET | /v1/state/ports/{port} | Get one port's state (`ports_state` with `gather_filter`) |
| GET | /v0/state/capabilities/system/ports | Port capabilities (read only when auto-negotiation is to be disabled, and by the reset of `overridden` and `deleted` without `config` to find the management port; for that reset a failed read other than a 404 fails the task before any write) |
| GET | /v0/configuration/vlan | Management VLAN members, protected from the reset of `overridden` and `deleted` without `config` |
| GET | /v0/configuration/lag | Member ports of a LAG in a management VLAN (same two cases) |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `global_settings` | dict | No | - | Fabric Engine global port settings |
| `global_settings.flow_control_mode` | bool | No | - | Enable/disable global flow control |
| `global_settings.advanced_feature_bandwidth_reservation` | str | No | - | Loopback bandwidth reservation (`DISABLE`, `LOW`, `HIGH`, `VIM`) |
| `admin` | list of dict | No | - | Bulk admin enable/disable operations |
| `admin[].name` | str | Yes | - | Port identifier (slot:port) |
| `admin[].enabled` | bool | Yes | - | Administrative status |
| `config` | list of dict | No | - | Per-port configuration settings. Aliased as `ports`, the pre-1.2.1 name, which is deprecated but still accepted |
| `config[].name` | str | Yes | - | Port identifier (slot:port) |
| `config[].enabled` | bool | No | - | Administrative status |
| `config[].description` | str | No | - | Interface description (max 255 chars) |
| `config[].speed` | str | No | - | Speed override when auto-negotiation is disabled (`0M`, `10M`, `100M`, `1G`, `2.5G`, `5G`, `10G`, `20G`, `25G`, `40G`, `50G`, `100G`, `400G`, `AUTO`). `AUTO` is a VIM speed (VIM-4YE, VIM-6YE ports), not "negotiate the speed"; Fabric Engine refuses it on any other port. To let a regular port negotiate its speed, use `auto_negotiation: true` (optionally with `auto_advertisements`). `speed: AUTO` fails before anything is written on a port whose capabilities (`/v0/state/capabilities/system/ports`) report `vimPort: false`; the check is skipped when the capabilities cannot be read, and a refusal then names the likely cause |
| `config[].duplex` | str | No | - | Duplex setting (`HALF_DUPLEX`, `FULL_DUPLEX`, `NONE`) |
| `config[].auto_negotiation` | bool | No | - | Toggle auto-negotiation. Disabling it (`false`) fails, before anything is written, on ports whose capabilities (`/v0/state/capabilities/system/ports`) list no supported speed/duplex combination for auto-negotiation off, for example the 10GBASE-T front-panel copper ports of the 7520-48XT-6C. The device would accept the request with HTTP 204 and silently keep auto-negotiation enabled. The check is skipped when the capabilities cannot be read. |
| `config[].auto_advertisements` | list of str | No | - | Authoritative list of auto-negotiation advertisements |
| `config[].flow_control` | str | No | - | Flow control mode (`ENABLE`, `DISABLE`). When omitted, `replaced` and `overridden` reset it to `DISABLE`, except on a port whose current mode is not one of the choices (for example `RX_ENABLE` or `PFC_ENABLE`), which keeps its mode |
| `config[].debounce_timer` | int | No | - | Debounce timer in ms (0-300000) |
| `config[].channelized` | bool | No | - | Enable/disable channelization on supported fiber ports |
| `config[].fec` | str | No | - | Forward error correction mode (`NONE`, `CLAUSE_74`, `CLAUSE_91_108`, `AUTO`) |
| `config[].eee` | bool | No | - | Energy Efficient Ethernet |
| `config[].port_mode` | bool | No | - | Tagging mode (true = trunk) |
| `config[].flex_uni` | bool | No | - | Flex UNI mode |
| `config[].native_vlan` | int | No | - | Native VLAN for trunk ports (1-4094). `0` is accepted but is currently a no-op: the device rejects every value the module could use to clear the assignment (`0` with HTTP 422, JSON null with "None is not of type integer", and `1` unless the port is already a VLAN 1 member), so the field is omitted instead. **No state can clear an existing assignment** — `replaced` and `overridden` leave it in place when omitted, and `deleted` drops it from the reset payload for the same reason, so removing a native VLAN has to be done from the CLI. Other values are rejected before the request is sent |
| `config[].ip_arp_inspection_trusted` | bool | No | - | Mark interface as trusted for ARP inspection |
| `gather_filter` | list of str | No | - | Limit the `gathered` configuration and the `ports_state` operational state to these ports |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply supplied interface changes incrementally. Needs at least one of `config`, `global_settings`, `admin`. | GET, PUT, PATCH |
| `replaced` | Make supplied values authoritative for targeted interfaces. Needs at least one of `config`, `global_settings`, `admin`. | GET, PUT, PATCH |
| `overridden` | Enforce supplied definitions; clear unlisted overrides, except on protected ports (management port, management VLAN members). Requires `config`. | GET, PUT, PATCH |
| `deleted` | Remove supplied interface configuration and overrides. With neither `config` nor `admin`, reset every port except the protected ones (management port, management VLAN members). | GET, PUT, PATCH |
| `gathered` | Read-only — return the per-port configuration (`gathered`) and the operational state (`ports_state`). | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `before` | list | Per-port configuration before the task ran. Returned for every state except `gathered`. Ports named in `config` are re-read individually so they carry the full field set; elsewhere the bulk listing may omit fields it treats as unset (typically `description`) - missing means not reported, not cleared |
| `after` | list | Per-port configuration after the task ran. Returned for every state except `gathered`. After a real change it is re-read from the device; in check mode it is the predicted state, including the ports `overridden` or `deleted` would reset; when nothing changed it equals `before`. Built the same way as `before`, so the two are directly comparable |
| `global_settings` | dict | Resulting global port configuration |
| `admin_updates` | list | Ports whose admin status was changed |
| `port_updates` | list | Ports whose attributes were modified |
| `port_removals` | list | Ports whose overrides were removed |
| `skipped_interfaces` | list | Ports the reset sweep of `overridden` (ports absent from `config`) or of `deleted` without `config` and `admin` (every port) did not reset, sorted by name, each also named in a warning with the reason - the protected ports (out-of-band management port, management VLAN members, member ports of a LAG in one) and any port the device refused to reset. Returned for `overridden` and for that form of `deleted` |
| `gathered` | list | Per-port configuration read from `/v0/configuration/ports`, one entry per port in the form `config` accepts, so it can be supplied back as `config` unchanged; re-applying an unfiltered result (no `gather_filter`) with `merged`, `replaced` or `overridden` changes nothing. With `gather_filter` it lists only the selected ports: still safe to re-apply with `merged` or `replaced`, but `overridden` takes it as the complete port list and resets every unlisted port that is not protected. Uses the keys of `before`, sorted by port name, without the fields the device does not report and without values outside an option's choices (for example a FEC mode the module does not offer); an omitted field keeps the value the port holds. Ports whose bulk record lacks a field are re-read individually, so `description` is reported. The global settings and the `admin` state are not included. Returned when state is `gathered` |
| `ports_state` | list | Operational interface state from the `/v1/state/ports` API, as the device reports it. Not configuration, and cannot be supplied back as `config` (use `gathered`). With `gather_filter` each entry is the port name with its state under `settings`, without it the raw REST list is returned. Kept unchanged for existing playbooks. Returned when state is `gathered` |

---

## [Examples](#table-of-contents)

### Disable multiple ports

```yaml
- name: Disable selected ports
  extreme.fe.extreme_fe_interfaces:
    state: merged
    admin:
      - name: "1:5"
        enabled: false
      - name: "1:6"
        enabled: false
```

### Configure port attributes

```yaml
- name: Tune interface attributes
  extreme.fe.extreme_fe_interfaces:
    state: replaced
    config:
      - name: "1:5"
        description: Server uplink
        auto_negotiation: false
        speed: 100M
        duplex: FULL_DUPLEX
        port_mode: true
        native_vlan: 200
```

### Reset all interfaces except protected

```yaml
- name: Reset all interfaces except protected
  extreme.fe.extreme_fe_interfaces:
    state: deleted
  register: reset_all
```

### Gather interface state

```yaml
- name: Collect interface information
  extreme.fe.extreme_fe_interfaces:
    state: gathered
    gather_filter:
      - "1:1"
      - "1:2"
  register: iface_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage interfaces on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current interface state
      extreme.fe.extreme_fe_interfaces:
        state: gathered
      register: ifaces_before

    - name: Disable unused ports
      extreme.fe.extreme_fe_interfaces:
        state: merged
        admin:
          - name: "1:5"
            enabled: false
          - name: "1:6"
            enabled: false

    - name: Configure server uplink
      extreme.fe.extreme_fe_interfaces:
        state: replaced
        config:
          - name: "1:10"
            description: Server uplink
            speed: 1G
            duplex: FULL_DUPLEX
            port_mode: true
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
