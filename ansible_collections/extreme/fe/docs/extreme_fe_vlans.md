# Virtual LANs (VLANs)

## Module: extreme.fe.extreme_fe_vlans

Manages VLANs on Fabric Engine devices.

---

Version added: 1.0.0

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

This module creates, updates, removes and queries VLANs on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- VLANs are supplied through the `config` list, so one task can manage several VLANs.
- Manages the VLAN name, type, STP instance and virtual router, and the LAG and ISIS logical interface memberships of each VLAN, tagged or untagged.
- Supports the Ansible states: merged, replaced, overridden, deleted and gathered.
- Use `extreme_fe_fabric_l2` to manage ISID to VLAN associations.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- **VLANs go in `config`:** the former top-level parameters (`vlan_id`, `vlan_name`, `vlan_type`, ...) still work as a single VLAN but are deprecated (removal in 2.0.0) and cannot be mixed with `config`. Even in that form, `overridden` deletes every other VLAN on the switch.
- **Port members are not managed here:** this module manages LAG and ISIS logical interface members. Add or remove ports with `extreme_fe_l2_interfaces`.
- **Members are replaced per type:** with `replaced` and `overridden`, naming `lag_interfaces` or `isis_logical_interfaces` makes that list the complete set of members of that type, tagged and untagged; an empty list removes them all. Leave the key out to keep the current members under `replaced`; under `overridden` an unnamed type is cleared. `remove_lag_interfaces` and `remove_isis_logical_interfaces` work in every state and are applied after additions.
- **ISIS logical interfaces must exist first:** the task fails before any change if one you name does not exist. On some switches the VLAN accepts an ISIS membership without storing it; the task then fails instead of reporting a change.
- **`overridden` deletes unlisted VLANs:** every VLAN not in `config` is deleted, so an incomplete list removes working configuration. Use `replaced` to change only the VLANs you list.
- **Protected VLANs:** `overridden` and `deleted` without `config` never delete VLAN 1, VLAN 4048, the management VLAN, dynamic VLANs, BROUTER VLANs or a VLAN whose type the switch does not report. A VLAN the switch refuses to delete (for example one still used by an L3 interface or an I-SID) is skipped too. Both are listed in `skipped_vlans` with a warning. A VLAN you name in `config` is always acted on, protected or not.
- **Deletes are checked:** a VLAN the switch still lists after a successful delete is not reported as deleted; remove it with the CLI (`vlan delete <id>`). You do not need `vr_name` to delete a VLAN.
- **Re-applying `gathered`:** the `gathered` result can be passed back as `config`. If you gathered only some VLANs with `gather_filter`, re-apply it with `merged` or `replaced`, not `overridden`, which would delete every VLAN not in the list. `before`, `after` and the deprecated `vlans` key keep the 1.2.1 form, which includes port members.
- **Partly applied changes:** if the switch rejects a change after applying part of it, the failure reports what was applied (the error message for VLAN settings, `details.applied_interfaces` for LAG members).
- **Lost connections:** if the connection drops during a change and the module cannot confirm the result, it reports `changed: true` with `details.outcome: unknown`, because the change may have been applied. Run the task again to bring the switch to the requested state.
- **`changed` on failure:** a failed task reports `changed: true` if the switch was already modified by an earlier write in the same task, and the error message lists those writes.
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
| GET | /v0/configuration/vlan | Retrieve all VLANs |
| GET | /v0/configuration/vlan/{vlan_id} | Retrieve a specific VLAN (also used for the read-back after a write and for `gather_filter`) |
| POST | /v0/configuration/vrf/{vr_name}/vlan | Create VLAN |
| PATCH | /v0/configuration/vlan/{vlan_id} | Update VLAN name, type, STP instance and ISIS logical interface membership |
| DELETE | /v0/configuration/vrf/{vr_name}/vlan/{vlan_id} | Delete VLAN |
| POST | /v0/operation/vlan/{vlan_id}/interfaces/:add | Add LAG membership |
| POST | /v0/operation/vlan/{vlan_id}/interfaces/:remove | Remove LAG membership |
| GET | /v0/configuration/spbm/isis/logical-ifs | List existing ISIS logical interfaces (existence check) |

---

## [Platform Constraints](#table-of-contents)

- `vlan_id` accepts 1 to 4094.
- VLANs 1 and 4048 are system VLANs, and the management, dynamic and BROUTER VLANs are protected too: `overridden` and the delete-all form of `deleted` never remove them (see the Notes).
- `vlan_type` is one of `PORT_MSTP_RSTP`, `PROTOCOL_MSTP_RSTP`, `PVLAN_MSTP_RSTP` or `SPBM_BVLAN`. When omitted at creation it is `PORT_MSTP_RSTP`.
- The VLAN ID and the virtual router identify the VLAN and cannot be changed with PATCH; `vr_name` only selects the context in which a VLAN is created or deleted.
- LAG membership is changed through the `:add` and `:remove` operations; ISIS logical interface membership is changed by PATCHing the VLAN's tagged and untagged interface lists.
- The VLAN endpoints accept an ISIS logical interface that does not exist (HTTP 204) and drop it silently, hence the existence check and the read-back described in the Notes.
- The REST API can only create layer-3 ISIS logical interfaces, which do not carry VLANs, so ISIS logical interface VLAN membership may not be manageable through the VLAN endpoints on a given device.
- A device can refuse to delete a VLAN that is still referenced by an L3 interface, an SPBM ISID or an RSMLT instance.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Desired VLAN operation: `merged`, `replaced`, `overridden`, `deleted` or `gathered` |
| `config` | list of dict | Yes (merged/replaced/overridden) | - | List of VLAN configurations to manage. Each `vlan_id` may appear only once; a duplicated `vlan_id` fails the task before any request is sent, also in check mode. For `deleted`, omit it (or leave it empty) to delete all user-created VLANs except the protected ones. Not used by `gathered` |
| `config[].vlan_id` | int | Yes | - | Numeric VLAN identifier (1-4094) |
| `config[].vlan_name` | str | No | - | Friendly name assigned to the VLAN. With `replaced`/`overridden` an omitted name is reset to `VLAN-<vlan_id>` |
| `config[].vlan_type` | str | No | - | VLAN type identifier required on Fabric Engine platforms. Choices: `PORT_MSTP_RSTP`, `PROTOCOL_MSTP_RSTP`, `PVLAN_MSTP_RSTP`, `SPBM_BVLAN`. Defaults to `PORT_MSTP_RSTP` when omitted during creation; reset to it by `replaced`/`overridden`, except on a VLAN whose current type is not one of the choices (for example `BROUTER`), which keeps its type |
| `config[].stp_name` | str | No | - | Auto-bind STP instance name associated with the VLAN. An empty string assigns the VLAN to STP instance 0 (device default) |
| `config[].vr_name` | str | No | `GlobalRouter` | Virtual router or forwarding context the VLAN belongs to |
| `config[].lag_interfaces` | list of dict | No | - | LAG memberships to ensure present on the VLAN. Under `replaced`/`overridden` mentioning this key (even as an empty list) makes LAG membership authoritative for both tagged and untagged |
| `config[].lag_interfaces[].name` | str | Yes | - | LAG identifier (numeric LAG ID as reported by the device) |
| `config[].lag_interfaces[].tag` | str | No | `tagged` | Apply the LAG as a `tagged` or `untagged` VLAN member |
| `config[].remove_lag_interfaces` | list of dict | No | - | LAG memberships to remove from the VLAN. Honoured in every write state, applied after additions, so naming the same LAG in both lists removes it |
| `config[].remove_lag_interfaces[].name` | str | Yes | - | LAG identifier to remove |
| `config[].remove_lag_interfaces[].tag` | str | No | `tagged` | Membership type to remove: `tagged` or `untagged` |
| `config[].isis_logical_interfaces` | list of dict | No | - | ISIS logical interfaces to ensure present on the VLAN. Each must already exist; the module reads `/v0/configuration/spbm/isis/logical-ifs` before any write (also in check mode) and fails naming the VLAN and interface if one is missing (check skipped if the list cannot be read). After the write the VLAN is read back and the task fails if the device accepted the request (HTTP 204) but did not store the membership |
| `config[].isis_logical_interfaces[].name` | str | Yes | - | Logical interface identifier (for example `1` or `10`) |
| `config[].isis_logical_interfaces[].tag` | str | No | `tagged` | Assign the logical interface as `tagged` or `untagged` within the VLAN |
| `config[].remove_isis_logical_interfaces` | list of dict | No | - | ISIS logical interface memberships to remove from the VLAN. Honoured in every write state, same semantics as `remove_lag_interfaces`. No existence check; a non-member is a no-op and reports no change |
| `config[].remove_isis_logical_interfaces[].name` | str | Yes | - | Logical interface identifier to remove |
| `config[].remove_isis_logical_interfaces[].tag` | str | No | `tagged` | Membership type to remove: `tagged` or `untagged` |
| `gather_filter` | list of int | No | - | Limit gathered VLAN facts to these VLAN identifiers |
| `vlan_id` | int | No | - | Deprecated. Use `config[].vlan_id`; the top-level form manages a single VLAN |
| `vlan_name` | str | No | - | Deprecated. Use `config[].vlan_name` |
| `vlan_type` | str | No | - | Deprecated. Use `config[].vlan_type`. Choices: `PORT_MSTP_RSTP`, `PROTOCOL_MSTP_RSTP`, `PVLAN_MSTP_RSTP`, `SPBM_BVLAN` |
| `stp_name` | str | No | - | Deprecated. Use `config[].stp_name` |
| `vr_name` | str | No | `GlobalRouter` | Deprecated. Use `config[].vr_name` |
| `lag_interfaces` | list of dict | No | - | Deprecated. Use `config[].lag_interfaces` |
| `lag_interfaces[].name` | str | Yes | - | Deprecated. Interface identifier, as for `config[].lag_interfaces[].name` |
| `lag_interfaces[].tag` | str | No | `tagged` | Deprecated. `tagged` or `untagged`, as for `config[].lag_interfaces[].tag` |
| `remove_lag_interfaces` | list of dict | No | - | Deprecated. Use `config[].remove_lag_interfaces` |
| `remove_lag_interfaces[].name` | str | Yes | - | Deprecated. Interface identifier, as for `config[].remove_lag_interfaces[].name` |
| `remove_lag_interfaces[].tag` | str | No | `tagged` | Deprecated. `tagged` or `untagged`, as for `config[].remove_lag_interfaces[].tag` |
| `isis_logical_interfaces` | list of dict | No | - | Deprecated. Use `config[].isis_logical_interfaces` |
| `isis_logical_interfaces[].name` | str | Yes | - | Deprecated. Interface identifier, as for `config[].isis_logical_interfaces[].name` |
| `isis_logical_interfaces[].tag` | str | No | `tagged` | Deprecated. `tagged` or `untagged`, as for `config[].isis_logical_interfaces[].tag` |
| `remove_isis_logical_interfaces` | list of dict | No | - | Deprecated. Use `config[].remove_isis_logical_interfaces` |
| `remove_isis_logical_interfaces[].name` | str | Yes | - | Deprecated. Interface identifier, as for `config[].remove_isis_logical_interfaces[].name` |
| `remove_isis_logical_interfaces[].tag` | str | No | `tagged` | Deprecated. `tagged` or `untagged`, as for `config[].remove_isis_logical_interfaces[].tag` |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create each listed VLAN if missing; apply only the supplied name, type and STP instance, and add (or, via `remove_*`, remove) memberships incrementally. Nothing else is touched. | GET, POST, PATCH |
| `replaced` | Make each listed VLAN authoritative: omitted name, type and STP instance are reset to the factory defaults, and membership is authoritative for the interface types the entry mentions. VLANs not listed are not touched. | GET, POST, PATCH |
| `overridden` | Like `replaced` for each listed VLAN, and authoritative across the **whole device**: any VLAN not listed in `config` is **deleted** (protected VLANs excepted: 1, 4048, management, dynamic, BROUTER), reported in `deleted_vlans`; protected management, dynamic and BROUTER VLANs and refused deletes land in `skipped_vlans`. An interface type left unmentioned in a listed entry is cleared. | GET, POST, PATCH, DELETE |
| `deleted` | Delete the VLANs listed in `config`, a VLAN that does not exist is a no-op. With no `config`, delete every user-created VLAN except the protected ones (1, 4048, management, dynamic, BROUTER); the management, dynamic and BROUTER ones are listed in `skipped_vlans`. | GET, DELETE |
| `gathered` | Read-only: return the current VLAN configuration, optionally limited by `gather_filter`. | GET |

---

## [Factory Defaults](#table-of-contents)

Values used by `replaced` and `overridden` to reset scalar attributes the task omits.

| Field | Default Value | Source |
|-------|---------------|--------|
| `vlan_name` | `VLAN-<vlan_id>` | OpenAPI spec - the device auto-assigns the name when none is given (computed per VLAN, not a constant) |
| `vlan_type` | `PORT_MSTP_RSTP` | Standard Fabric Engine type for port-based VLANs |
| `stp_name` | `""` (STP instance 0) | OpenAPI spec - an empty or missing string assigns the VLAN to STP instance 0 |

`vr_name` is never reset: it identifies the VLAN and cannot be patched.

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `before` | list | Full VLAN configuration state before changes. Each VLAN has the form of `vlans` under `state=gathered`, with `vr_name` and the members of every interface type, PORT included, in `tagged_interfaces` and `untagged_interfaces` lists of `interfaceType` and `interfaceName`; it is not the `config` form of `gathered`. Returned when state is `merged`, `replaced`, `overridden` or `deleted` |
| `after` | list | Full VLAN configuration state after changes. Returned when state is `merged`, `replaced`, `overridden` or `deleted`, whether or not the module made changes. In check mode this is the predicted state |
| `deleted_vlans` | list of int | VLAN IDs removed because `state=overridden` and the task did not list them. In check mode, the VLANs that would have been removed. Returned when state is `overridden` and unlisted VLANs were removed |
| `skipped_vlans` | list of dict | VLANs that `state=overridden` (the VLANs absent from `config`) or `state=deleted` without `config` did not delete, each also raised as a warning: the protected management, dynamic and BROUTER VLANs with `protected: true` (VLANs 1 and 4048 are kept but not listed), and, for `overridden`, the VLANs the device refused to delete (typically still referenced by an L3 interface, SPBM ISID or RSMLT instance) with `protected: false`. Returned when state is `overridden`, or `deleted` without `config`, and a VLAN was skipped |
| `skipped_vlans[].vlan_id` | int | The VLAN that was not deleted |
| `skipped_vlans[].reason` | str | Why it was not deleted: for a protected VLAN one of `management VLAN`, `dynamic VLAN` or `BROUTER VLAN` (VLANs 1 and 4048 are kept but not listed); otherwise the error the device returned |
| `skipped_vlans[].protected` | bool | `true` for a protected VLAN, `false` for a delete the device refused |
| `gathered` | list | VLAN configuration gathered from the device, one entry per VLAN in the form `config` accepts, so it can be supplied back as `config` unchanged; re-applying an unfiltered result (no `gather_filter`) with `merged`, `replaced` or `overridden` changes nothing. With `gather_filter` it lists only the selected VLANs: still safe to re-apply with `merged` or `replaced`, but `overridden` deletes every unlisted VLAN that is not protected. LAG and ISIS logical interface members are listed in `lag_interfaces` and `isis_logical_interfaces` with their `tag`; both lists are always present, empty when the VLAN has no such members. PORT members are not included, because `config` cannot express them; they are managed by `extreme_fe_l2_interfaces`, are left in place when the result is re-applied, and are still listed in `vlans`. A scalar the device does not report, or a `vlan_type` outside the choices of the option, is left out; such a type is kept when the result is re-applied. An unreported `stp_name` is STP instance 0 and is returned as `""`. Returned when state is `gathered` |
| `gathered[].vlan_id` | int | VLAN identifier |
| `gathered[].vlan_name` | str | VLAN name |
| `gathered[].vlan_type` | str | VLAN type |
| `gathered[].stp_name` | str | STP instance name, empty for STP instance 0 |
| `gathered[].vr_name` | str | Virtual router the VLAN belongs to |
| `gathered[].lag_interfaces` | list of dict | LAG members, each with `name` and `tag` (`tagged` or `untagged`) |
| `gathered[].isis_logical_interfaces` | list of dict | ISIS logical interface members, each with `name` and `tag` |
| `vlans` | list of dict | Under the action states, per-VLAN operation results with differences. Under `state=gathered` this instead lists the gathered VLANs in the form of `before`, which is what the module returned for that state up to 1.2.1. It includes the PORT members but cannot be supplied back as `config`. That form is deprecated and will be removed in 2.0.0 - use `gathered`. Returned always except when the task fails |
| `vlans[].vlan_id` | int | VLAN identifier |
| `vlans[].before` | dict | VLAN configuration before the operation |
| `vlans[].after` | dict | VLAN configuration after the operation |
| `vlans[].changed` | bool | Whether this VLAN was modified |
| `vlans[].differences` | dict | Fields that changed with before and after values |

---

## [Examples](#table-of-contents)

VLANs are supplied through the `config` list, which manages several VLANs in one
task. The former top-level parameters (`vlan_id`, `vlan_name`, `lag_interfaces`, ...)
still work as a single-entry config but are deprecated and emit a warning; the
two forms cannot be mixed in one task.

### Create or update multiple VLANs

```yaml
- name: Create or update multiple VLANs (merged)
  extreme.fe.extreme_fe_vlans:
    state: merged
    config:
      - vlan_id: 20
        vlan_name: Campus-20
        vr_name: GlobalRouter
        lag_interfaces:
          - name: "10"
            tag: tagged
      - vlan_id: 30
        vlan_name: Campus-30
        vr_name: GlobalRouter
```

### Enforce the membership of one VLAN

`replaced` makes the supplied data authoritative for the VLANs it lists and resets
omitted name, type and STP instance to their factory defaults. VLANs it does not
list are left alone.

```yaml
- name: Enforce VLAN 200 membership (replaced)
  extreme.fe.extreme_fe_vlans:
    state: replaced
    config:
      - vlan_id: 200
        vr_name: GlobalRouter
        lag_interfaces:
          - name: "10"
            tag: tagged
```

### Enforce the complete VLAN inventory

`overridden` is authoritative across the **whole device**: each listed VLAN is
handled as for `replaced`, and any VLAN the task does not list is **deleted**.
VLANs 1 and 4048 are kept silently. The management, dynamic and BROUTER VLANs are
kept with a warning; they and anything the device refuses to delete are reported
in `skipped_vlans`. Use it only when the task describes every VLAN the device should
have - to reset a single VLAN without touching the others, use `replaced`.

```yaml
- name: Override all VLANs - only these should exist (overridden)
  extreme.fe.extreme_fe_vlans:
    state: overridden
    config:
      - vlan_id: 20
        vlan_name: Campus-20
        vr_name: GlobalRouter
      - vlan_id: 30
        vlan_name: Campus-30
        vr_name: GlobalRouter
```

### Remove a LAG from a VLAN

```yaml
- name: Remove specific LAG from VLAN 200 (merged with remove)
  extreme.fe.extreme_fe_vlans:
    state: merged
    config:
      - vlan_id: 200
        vr_name: GlobalRouter
        remove_lag_interfaces:
          - name: "11"
            tag: tagged
```

### Add an ISIS logical interface to a VLAN

The ISIS logical interface must already exist on the device. The module fails before
any write if it does not, and fails after the write if the device accepts the
membership but does not store it.

```yaml
- name: Add ISIS logical interface 10 to VLAN 20
  extreme.fe.extreme_fe_vlans:
    state: merged
    config:
      - vlan_id: 20
        isis_logical_interfaces:
          - name: "10"
            tag: tagged
```

### Delete VLANs

```yaml
- name: Delete VLAN 200
  extreme.fe.extreme_fe_vlans:
    state: deleted
    config:
      - vlan_id: 200
        vr_name: GlobalRouter

- name: Delete all user-created VLANs
  extreme.fe.extreme_fe_vlans:
    state: deleted
```

### Gather VLAN configuration

```yaml
- name: Gather specific VLANs
  extreme.fe.extreme_fe_vlans:
    state: gathered
    gather_filter: [20, 30]
  register: vlan_info

- name: Display VLAN configuration
  ansible.builtin.debug:
    var: vlan_info.gathered
```

### Deprecated top-level form

Still accepted for a single VLAN, with a deprecation warning. Do not use it in new
playbooks.

```yaml
- name: Ensure VLAN 20 exists (deprecated top-level form)
  extreme.fe.extreme_fe_vlans:
    state: merged
    vlan_id: 20
    vlan_name: Campus-20
    vr_name: GlobalRouter
    lag_interfaces:
      - name: "10"
        tag: tagged
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage VLANs on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current VLAN configuration
      extreme.fe.extreme_fe_vlans:
        state: gathered
      register: vlans_before

    - name: Create or update the Campus VLANs
      extreme.fe.extreme_fe_vlans:
        state: merged
        config:
          - vlan_id: 20
            vlan_name: Campus-20
            vr_name: GlobalRouter
            lag_interfaces:
              - name: "10"
                tag: tagged
          - vlan_id: 30
            vlan_name: Campus-30
            vr_name: GlobalRouter

    - name: Enforce VLAN 200 membership
      extreme.fe.extreme_fe_vlans:
        state: replaced
        config:
          - vlan_id: 200
            vr_name: GlobalRouter
            lag_interfaces:
              - name: "10"
                tag: tagged

    - name: Remove a LAG from VLAN 200
      extreme.fe.extreme_fe_vlans:
        state: merged
        config:
          - vlan_id: 200
            vr_name: GlobalRouter
            remove_lag_interfaces:
              - name: "11"
                tag: tagged

    - name: Delete VLAN 200
      extreme.fe.extreme_fe_vlans:
        state: deleted
        config:
          - vlan_id: 200
            vr_name: GlobalRouter
      register: vlans_after

    - name: Show what changed
      ansible.builtin.debug:
        msg:
          - "before: {{ vlans_before.gathered }}"
          - "after : {{ vlans_after.after }}"
```

---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
