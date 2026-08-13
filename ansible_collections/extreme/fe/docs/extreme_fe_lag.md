# Link Aggregation Group (LAG)

## Module: extreme.fe.extreme_fe_lag

Manages LAG configuration on Fabric Engine devices.

---

Version added: 1.0.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Parameters](#parameters)
- [State Behaviour Summary](#state-behaviour-summary)
- [Factory Defaults](#factory-defaults)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

Through this module, Link Aggregation Groups (LAGs) can be created and deleted on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- The module updates LAG attributes such as friendly names, load balancing algorithms, and LACP keys.
- Adds or removes member ports through the Fabric Engine LAG REST endpoints.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- Fabric Engine cannot patch an existing LAG's aggregation mode; delete and recreate the LAG to change `mode`.
- `replaced` and `overridden` reset omitted attributes to the factory defaults listed under [Factory Defaults](#factory-defaults). `mode` is never reset, because the API cannot patch it.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/lag | List all LAGs |
| GET | /v0/configuration/lag/{lag_id} | Get LAG config |
| POST | /v0/configuration/lag | Create LAG |
| PATCH | /v0/configuration/lag/{lag_id} | Update LAG attributes |
| DELETE | /v0/configuration/lag/{lag_id} | Delete LAG |
| POST | /v0/configuration/lag/{lag_id}/memberPorts | Add member ports |
| DELETE | /v0/configuration/lag/{lag_id}/memberPorts/{port} | Remove member port |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `lag_id` | raw | Yes | - | LAG identifier |
| `name` | str | No | - | Friendly name for the LAG |
| `mode` | str | No | - | Aggregation mode: `STATIC`, `LACP`, or `VLACP` |
| `lacp_key` | str | No | - | LACP key for the LAG. Valid values are `1`-`512`. Never reset by `replaced`/`overridden` - see [Factory Defaults](#factory-defaults) |
| `load_balance_algo` | str | No | - | Load balancing algorithm: `L2`, `L3`, `L3_L4`, `CUSTOM`, `PORT`. Fabric Engine always applies `CUSTOM`; other values are accepted by the API and ignored |
| `flex_uni` | bool | No | - | Enable or disable Flex-UNI (switched UNI) on the LAG. Must be `true` before the LAG can be used in a Switched UNI (SUNI) ISID endpoint, and `false` for Transparent UNI (TUNI) membership. Device factory default is `false`. With `merged` it is applied only when supplied; with `replaced`/`overridden` an omitted value is reset to `false` |
| `member_ports` | list of str | No | - | Authoritative list of member ports |
| `add_member_ports` | list of str | No | - | Ports to add to the LAG |
| `remove_member_ports` | list of str | No | - | Ports to remove from the LAG |
| `purge_member_ports` | bool | No | `false` | Remove ports not in `member_ports` |
| `gather_filter` | list of str | No | - | Limit gathered output to these LAG IDs |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create LAG if missing; add/update attributes and members incrementally. | GET, POST, PATCH, DELETE |
| `replaced` | Make supplied attributes and members authoritative for the LAG; omitted attributes are reset to factory defaults. | GET, POST, PATCH, DELETE |
| `overridden` | Like `replaced` for each listed LAG, and authoritative across the **whole device**: any LAG not listed in `config` is **deleted** (reported in `deleted_lags`; failures in `skipped_lags`). The deprecated top-level form manages a single LAG and never deletes unlisted ones. | GET, POST, PATCH, DELETE |
| `deleted` | Delete the LAG entirely or remove specified members. | GET, DELETE |
| `gathered` | Read-only — return current LAG configuration. | GET |

---

## [Factory Defaults](#table-of-contents)

Values used by `replaced` and `overridden` to reset attributes the task omits.

| Field | Default Value | Source |
|-------|---------------|--------|
| `flex_uni` | `false` | OpenAPI `LagConfigs.flexUni` (`default: false`); confirmed on device (`FLEX-UNI: disable`) |
| `load_balance_algo` | `CUSTOM` | OpenAPI `LagLoadBalanceAlgo` ("Fabric Engine will always return/set CUSTOM"); confirmed on device |
| `member_ports` | `[]` | Device verification - a new MLT has no member ports |
| `name` | `MLT-<lag_id>` | Device verification - a bare MLT is named after its own ID (computed per LAG, not a constant) |

Verified on a 7520-48XT-6C running Fabric Engine 9.3 by creating bare MLTs (`mlt 60`,
`mlt 70 enable`) and reading them back through `GET /v0/configuration/lag/<id>`.

`mode` and `lacp_key` are deliberately excluded.

Fabric Engine cannot patch the aggregation mode, so `replaced` and `overridden` cannot
reset it to `STATIC` - the module leaves it as-is instead of attempting a change the
API would reject.

`lacp_key` cannot be reset either. A bare MLT reports `"0"`, which is
`LACP_ANY_AGGRETABLE_KEY` in the device source - a value the device computes but will
not accept as input. Writing `"0"` back returns HTTP 500, the CLI range is
`lacp key <1-512|defVal>`, and clearing a key is a port-level two-step
(`no lacp aggregation enable`, then `default lacp key`) with no REST equivalent.
To clear an LACP key, delete and recreate the LAG.

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `lag` | dict | Resulting LAG configuration |
| `lag_removed` | dict | LAG configuration that was deleted |
| `member_additions` | list | Ports that were added |
| `member_removals` | list | Ports that were removed |
| `lags` | list | LAG configurations (gathered) |

---

## [Examples](#table-of-contents)

LAGs are supplied through the `config` list, which manages several LAGs in one
task. The former top-level parameters (`lag_id`, `name`, `member_ports`, ...)
still work as a single-entry config but are deprecated and emit a warning; the
two forms cannot be mixed in one task.

### Create LAGs with member ports

```yaml
- name: Create two LAGs in a single task
  extreme.fe.extreme_fe_lag:
    state: merged
    config:
      - lag_id: 10
        name: Core-Uplink
        mode: LACP
        member_ports:
          - "1:1"
          - "1:2"
      - lag_id: 11
        name: Edge-Uplink
        member_ports:
          - "1:3"
```

### Add ports to an existing LAG

`merged` is additive: existing members are kept.

```yaml
- name: Add a port to LAG 10
  extreme.fe.extreme_fe_lag:
    state: merged
    config:
      - lag_id: 10
        add_member_ports:
          - "1:4"
```

### Enforce an exact member list for one LAG

`replaced` makes the supplied members authoritative and resets omitted
attributes to their factory defaults, but touches only the LAGs it lists.

```yaml
- name: Make 1:1 and 1:2 the only members of LAG 10
  extreme.fe.extreme_fe_lag:
    state: replaced
    config:
      - lag_id: 10
        member_ports:
          - "1:1"
          - "1:2"
```

An empty list clears every member while keeping the LAG:

```yaml
- name: Remove all members from LAG 20
  extreme.fe.extreme_fe_lag:
    state: replaced
    config:
      - lag_id: 20
        member_ports: []
```

### Enforce the complete LAG inventory

`overridden` is authoritative across the **whole device**: each listed LAG is
handled as for `replaced`, and any LAG the task does not list is **deleted**.
LAGs it could not delete are reported in `skipped_lags`. Use it only when the
task describes every LAG the device should have - to reset a single LAG without
touching the others, use `replaced`.

```yaml
- name: Make LAGs 10 and 11 the only LAGs on the device
  extreme.fe.extreme_fe_lag:
    state: overridden
    config:
      - lag_id: 10
        member_ports:
          - "1:1"
          - "1:2"
      - lag_id: 11
        member_ports:
          - "1:3"
```

### Enable Flex-UNI on a LAG

Flex-UNI must be enabled on the LAG before `extreme.fe.extreme_fe_fabric_l2` can
reference it from a Switched UNI (SUNI) ISID endpoint. A LAG intended for
Transparent UNI (TUNI) membership must keep Flex-UNI disabled.

```yaml
- name: Enable Flex-UNI so LAG 50 can be used as a switched UNI
  extreme.fe.extreme_fe_lag:
    state: merged
    config:
      - lag_id: 50
        flex_uni: true
```

### Delete LAGs

Without `member_ports` the whole LAG is removed; with `member_ports` only those
members are pruned and the LAG itself is kept.

```yaml
- name: Delete LAG 11 entirely and prune one member from LAG 10
  extreme.fe.extreme_fe_lag:
    state: deleted
    config:
      - lag_id: 11
      - lag_id: 10
        member_ports:
          - "1:4"
```

### Gather LAG configuration

```yaml
- name: Collect information for every LAG
  extreme.fe.extreme_fe_lag:
    state: gathered
  register: lag_info

- name: Collect information for specific LAGs
  extreme.fe.extreme_fe_lag:
    state: gathered
    gather_filter:
      - "10"
      - "11"
  register: lag_subset
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage LAGs on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current LAGs
      extreme.fe.extreme_fe_lag:
        state: gathered
      register: lags_before

    - name: Create the uplink LAGs
      extreme.fe.extreme_fe_lag:
        state: merged
        config:
          - lag_id: 10
            name: Core-Uplink
            mode: LACP
            member_ports:
              - "1:1"
              - "1:2"
          - lag_id: 11
            name: Edge-Uplink
            member_ports:
              - "1:3"

    - name: Delete an unused LAG
      extreme.fe.extreme_fe_lag:
        state: deleted
        config:
          - lag_id: 20
      register: lags_after

    - name: Show what changed
      ansible.builtin.debug:
        msg:
          - "before: {{ lags_before.lags }}"
          - "after : {{ lags_after.after }}"
```

---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
