# Layer 2 Interfaces

## Module: extreme.fe.extreme_fe_l2_interfaces

Manages L2 interface settings on Fabric Engine devices.

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

- This module manages L2 interface settings on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.
- Supports VLAN membership (access/trunk mode, tagged/untagged VLANs) on one or more interfaces per task.

---

## [Notes](#table-of-contents)

- When `state=overridden`, the module resets interfaces not listed in `config` to device defaults; `config` must not be empty. The protected interfaces absent from `config` (the same ones `deleted` without `config` protects, see below) are not reset; an interface named in `config` is always applied as `replaced`, protected or not.
- On a `TRUNK` LAG that is not in LACP mode and has no member ports, the device ignores `untagged_vlan` and reports 0, so the module neither compares nor sends it, including its automatic membership in the allowed VLAN list. Only explicitly listed tagged VLANs are written. If the untagged VLAN is the only difference, no request is sent and nothing is reported as changed; the value is not stored or pending on the device. When other attributes of the LAG change, the request omits `portVlan`. The module warns once per such interface; run the task again after adding member ports to apply the value. `ACCESS` LAGs are not affected. In check mode a LAG that the task turns into `TRUNK` is predicted with `untagged_vlan` 0, the value a real run reads back.
- Interfaces that cannot be reset during overridden (e.g., LACP LAGs), and the protected ones, are skipped with a warning and returned in `skipped_interfaces`.
- A task that fails after one of its writes succeeded reports `changed: true`, whichever later request or read-back failed, and the failure message names the interfaces already written. Under `overridden`, an interface whose reset the device accepted but whose read-back or retry then fails fails the task instead of being listed in `skipped_interfaces`.
- `state: gathered` returns the interface list under the standard `gathered` key, one entry per interface
  with `name`, `port_type`, `untagged_vlan` and `tagged_vlans`, the form `config` accepts. It can be supplied
  back as `config` unchanged, and re-applying a result gathered without `config` with `merged`, `replaced`
  or `overridden` changes nothing. Gathered with `config`, the result lists only the named interfaces: it is
  still safe to re-apply with `merged` or `replaced`, but `overridden` takes it as the complete interface list
  and resets every unlisted interface that is not protected, so re-apply such a result with `overridden` only
  to do that.
  `tagged_vlans` does not repeat `untagged_vlan`, and a memberless non-LACP `TRUNK` LAG is reported with
  `untagged_vlan` 0, which re-applies without a request or a warning. A `port_type` other than `ACCESS` or
  `TRUNK` is left out, and such a type is kept when the result is re-applied. Interfaces named in `config`
  that the device does not have are left out, with a warning.
- The interfaces are also still returned under `interfaces` in the per-interface result form used up to 1.2.1
  (`name`, `before`, `after`, `differences`, `changed`), so existing playbooks keep working; that form cannot
  be supplied back as `config`, is deprecated and will be removed in 2.0.0.
- Returns `before` and `after` snapshots for every interface the task touched — those named in `config`,
  plus every interface `overridden` or `deleted` without `config` was able to reset — populated whether or not anything changed.
  Interfaces reported in `skipped_interfaces` are not covered.
- `state: deleted` without `config` resets every interface the device lists, ports and LAGs, exactly as `deleted` resets a listed interface without VLAN parameters (port type kept, untagged VLAN 0, no tagged VLANs). Protected interfaces are skipped, each with a warning naming the interface and the reason, and listed in `skipped_interfaces`. They are the out-of-band management port (`mgmt` or `<slot>:mgmt`), every port and LAG that is a tagged or untagged member of a management VLAN (`isMgmtInterface` in `/v0/configuration/vlan`), and the member ports of such a LAG. LACP/VLACP LAGs and interfaces the device refuses to reset are skipped as `overridden` skips them.
- `overridden` and `deleted` without `config` read the VLAN list, and the LAG list when a swept interface is a LAG, before anything is written, and only when at least one interface they sweep would be reset. If it cannot be read the task fails without changing the device, also in check mode, so the management connection is never put at risk. A management-VLAN LAG whose record is missing from the LAG list, or has no `memberPorts` list (absent, not a list, or with a blank or non-string member name), fails the task the same way, since its member ports could not be protected; an empty list is a memberless LAG.
- Supports check mode (`--check`) and diff mode (`--diff`).
- Tested against Fabric Engine Version 9.3.2.
- Each interface may be listed once in `config`; one listed twice fails before any request.
- A PUT that fails without an answer (a lost connection) may have been applied, so the task reports `changed=true` with `details.outcome=unknown`; a reset sweep (`deleted` without `config`, `overridden`) fails then instead of listing the interface in `skipped_interfaces`.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/vlan/interfaces | Retrieve all interface VLAN settings |
| GET | /v0/configuration/vlan/interfaces/type/{type}/name/{name} | Get specific interface |
| GET | /v0/configuration/lag | Read LAG aggregation modes, to skip LAGs that cannot be reset, and the member ports of a LAG in a management VLAN (`overridden`, and `deleted` without `config`) |
| GET | /v0/configuration/vlan | Management VLAN members, protected from the reset of `overridden` and `deleted` without `config` |
| GET | /v0/configuration/lag/{lag_id} | Read a LAG's mode and member ports (TRUNK LAG entries only), to decide whether `untagged_vlan` can be compared |
| PUT | /v0/configuration/vlan/interfaces/type/{type}/name/{name} | Update interface VLAN settings |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | No | - | L2 interface definitions |
| `config[].name` | str | Yes | - | Interface identifier (`1:5`, `PORT:1:5`, or `LAG:10`) |
| `config[].port_type` | str | No | - | VLAN mode: `ACCESS` or `TRUNK`. When omitted, `replaced` and `overridden` derive it from the rest of the entry, except on an interface whose current type is not one of these, which keeps its type |
| `config[].untagged_vlan` | int | No | - | VLAN ID for untagged traffic (0 to clear). On a `TRUNK` LAG that is not in LACP mode and has no member ports, the device ignores it and reports 0. The module neither compares nor sends it, including its automatic membership in the allowed VLAN list; only explicitly listed tagged VLANs are written. If it is the only difference, no request is sent and nothing is reported as changed (the value is not stored or pending on the device); when other attributes of the LAG change, the request omits `portVlan`. The module warns once per interface; run the task again after the LAG has member ports to apply it |
| `config[].tagged_vlans` | list of int | No | - | Authoritative list of tagged VLANs. In `merged` it replaces the current tagged list; in `replaced`/`overridden` it sets the complete tagged list. In `deleted` it is **not** authoritative: it names the VLANs to remove from the tagged list, together with `remove_tagged_vlans`, and tagged VLANs not named are kept. When neither `tagged_vlans` nor `remove_tagged_vlans` is given, every tagged VLAN is removed |
| `config[].add_tagged_vlans` | list of int | No | - | VLANs to add (merged only) |
| `config[].remove_tagged_vlans` | list of int | No | - | VLANs to remove (merged/deleted only) |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply provided parameters incrementally without removing unspecified membership. | GET, PUT |
| `replaced` | Make supplied values authoritative for each listed interface. A field left out is reset to its device default - omitting `untagged_vlan` sets it back to VLAN 1. `port_type` is the exception: an explicit value is always honoured, and it is derived from the rest of the config (`TRUNK` when `tagged_vlans` is given, else `ACCESS`) only when left out; an interface whose current type is not `ACCESS` or `TRUNK` keeps it. | GET, PUT |
| `overridden` | Like `replaced` but also resets unlisted interfaces to defaults, except the protected ones (management port, management VLAN members, LACP/VLACP LAGs). | GET, PUT |
| `deleted` | Remove tagged VLAN membership; reset all if no parameters given. Without `config`, reset every interface except the protected ones (management port, management VLAN members, LACP/VLACP LAGs). | GET, PUT |
| `gathered` | Read-only — return current VLAN membership. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `gathered` | list | Interface VLAN membership read from the device (`state: gathered` only), one `{name, port_type, untagged_vlan, tagged_vlans}` entry per interface in the form `config` accepts; re-applying a result gathered without `config` with `merged`, `replaced` or `overridden` changes nothing. Gathered with `config` it lists only the named interfaces: still safe with `merged` or `replaced`, but `overridden` resets every unlisted interface that is not protected. A `port_type` other than `ACCESS` or `TRUNK` is left out and kept on re-apply |
| `interfaces` | list | Per-interface results (name, before, after, differences, changed). Under `state: gathered` the gathered interfaces in that form, as up to 1.2.1 (deprecated, use `gathered`) |
| `before` | list | Settings for every interface the task touched, as they were before it ran |
| `after` | list | Settings for every interface the task touched once it has run; the predicted state in check mode |
| `reset_interfaces` | list | Interfaces reset to defaults during overridden, or by `deleted` without `config` |
| `skipped_interfaces` | list | Interfaces that could not be reset (e.g. LACP LAGs). Under `overridden` and `deleted` without `config` also the protected ones - the out-of-band management port, the members of a management VLAN and the member ports of a LAG in one - each named in a warning with the reason |

---

## [Examples](#table-of-contents)

### Configure access port

```yaml
- name: Set access port on interface 1:5
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:5"
        port_type: ACCESS
        untagged_vlan: 5
    state: replaced
```

### Configure trunk ports

```yaml
- name: Ensure trunk membership on two ports
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:10"
        port_type: TRUNK
        untagged_vlan: 1
        tagged_vlans: [5, 6]
      - name: "1:11"
        port_type: TRUNK
        untagged_vlan: 1
        tagged_vlans: [7, 8]
    state: replaced
```

### Add tagged VLANs incrementally

```yaml
- name: Add VLAN 20 to port 1:7
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:7"
        add_tagged_vlans: [20]
    state: merged
```

### Reset all interfaces except protected

```yaml
- name: Reset all interfaces except protected
  extreme.fe.extreme_fe_l2_interfaces:
    state: deleted
  register: l2_reset
```

### Gather L2 interface settings

```yaml
- name: Collect all L2 interface settings
  extreme.fe.extreme_fe_l2_interfaces:
    state: gathered
  register: l2_config
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage L2 interfaces on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current L2 interface settings
      extreme.fe.extreme_fe_l2_interfaces:
        state: gathered
      register: l2_before

    - name: Configure access port
      extreme.fe.extreme_fe_l2_interfaces:
        config:
          - name: "1:5"
            port_type: ACCESS
            untagged_vlan: 5
        state: replaced

    - name: Configure trunk ports
      extreme.fe.extreme_fe_l2_interfaces:
        config:
          - name: "1:10"
            port_type: TRUNK
            untagged_vlan: 1
            tagged_vlans: [100, 200]
        state: replaced

    - name: Add tagged VLANs to a port
      extreme.fe.extreme_fe_l2_interfaces:
        config:
          - name: "1:7"
            add_tagged_vlans: [20, 30]
        state: merged
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
