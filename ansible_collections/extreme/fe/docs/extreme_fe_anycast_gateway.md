# Anycast Gateway

## Module: extreme.fe.extreme_fe_anycast_gateway

Manages Anycast Gateway interfaces on Fabric Engine devices.

---

Version added: 1.2.0

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

This module manages Anycast Gateway interfaces on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Resource identifier is `vlan_id`.
- Create-time fields are immutable after creation: `ip_address`, `mask_length`, `one_ip`, `vr_id`.
- The only updatable field on an existing interface is `enabled`.
- `mask_length` only exists for an interface in ONE-IP mode (`one_ip=true`). It is never sent for any other interface and is reported as `null` for it.
- Changing an immutable field with `replaced` or `overridden` deletes and re-creates the interface. The re-create request is validated before the delete, and the original interface is restored automatically if the re-create fails.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- **Settings fixed at creation:** `ip_address`, `mask_length`, `one_ip` and `vr_id` cannot be changed on an existing interface. `merged` fails if you try. Use `replaced` (or `overridden`) instead: the module deletes the interface and creates it again with the new values. Only `enabled` can be changed in place.
- **Omitted settings:** with `replaced` and `overridden`, a creation setting you leave out (`ip_address`, `one_ip`, `vr_id`, `mask_length`) keeps its current value, so the interface is not re-created by accident. An omitted `enabled` is reset to its default, `false`, which disables the interface: set `enabled: true` to keep it up.
- **ONE-IP and mask length:** `mask_length` is only used with `one_ip: true`, and it is required when you create a ONE-IP interface. For any other interface, leave it out; it is reported as `null`.
- **Safe re-creation:** the new settings are checked before the old interface is deleted. If the device still rejects them, the module puts the original interface back and the task fails with the device's error. In the rare case that the original cannot be restored, the error message says so and `details.original_payload` holds what you need to re-create it by hand.
- **Disable before delete:** Fabric Engine only deletes a disabled interface, so the module disables it for you first.
- **Lost connections:** if the connection drops during a change, the module checks the device to find out whether the change was applied, and warns you when it was.
- **`changed` on failure:** a failed task reports `changed: true` if the device was already modified (for example by an earlier entry in `config`), and `changed: false` if nothing was written.
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
| GET | /v0/configuration/anycast-gateway/interfaces | List all Anycast Gateway interfaces |
| POST | /v0/configuration/anycast-gateway/vlan/{vlan_id} | Create Anycast Gateway interface |
| PATCH | /v0/configuration/anycast-gateway/vlan/{vlan_id}/interface | Update interface (enabled only) |
| DELETE | /v0/configuration/anycast-gateway/vlan/{vlan_id} | Delete interface |
| GET | /v0/state/anycast-gateway/interfaces | Read operational interface state |

---

## [Platform Constraints](#table-of-contents)

- `vlan_id` range: 1-4094.
- `mask_length` can only be set when `one_ip=true`; it is never sent otherwise and is reported as `null` for an interface that is not ONE-IP.
- Once created, immutable fields require delete + re-create to change.
- Module auto-disables interface before delete, as required by Fabric Engine devices.
- IPv6 Anycast is not supported by current firmware.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | Yes (merged/replaced/overridden) | - | Anycast interface config list |
| `config[].vlan_id` | int | Yes | - | VLAN ID (resource key) |
| `config[].ip_address` | str | No | - | IPv4 Anycast address (immutable) |
| `config[].mask_length` | int | No | - | IPv4 mask length (immutable). Only with `one_ip=true`; never sent otherwise. Required to create an interface with `one_ip=true` |
| `config[].one_ip` | bool | No | - | ONE-IP mode (immutable) |
| `config[].vr_id` | int | No | - | Virtual Router ID (immutable). Reported as `null` for a gateway without a VRID (the device reports `vrId` 0) |
| `config[].enabled` | bool | No | - | Interface admin state (patchable) |
| `gather_filter` | list of int | No | - | Limit gathered output to selected VLAN IDs |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create missing interfaces, patch `enabled` on existing interfaces. | GET, POST, PATCH |
| `replaced` | Reconcile listed interfaces; recreate (DELETE + POST) when immutable fields differ. The re-create is validated first and the original interface is restored if it fails. | GET, DELETE, POST, PATCH |
| `overridden` | Delete unlisted interfaces, then apply `replaced` logic. | GET, DELETE, POST, PATCH |
| `deleted` | Delete listed interfaces; delete all if `config` omitted. | GET, DELETE, PATCH |
| `gathered` | Read-only output. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any interface was modified |
| `before` | list of dict | Interface config before changes. Returned when state is `merged`, `replaced`, `overridden` or `deleted` |
| `after` | list of dict | Interface config after the task ran. Returned when state is `merged`, `replaced`, `overridden` or `deleted`, whether or not anything changed. After a real change it is re-read from the device: an interface of the task that this read does not return (the device can omit recently created interfaces) is read on its own, or predicted if that does not return it either, and if the re-read fails `after` is the predicted state and a warning says so. In check mode it is the predicted state; when nothing changed it equals `before` |
| `gathered` | list of dict | Gathered Anycast interface configuration. Holds only the `config` options (`vlan_id`, `ip_address`, `mask_length`, `enabled`, `one_ip`, `vr_id`), so it can be passed back as `config` unchanged and re-applying it with `merged`, `replaced` or `overridden` changes nothing. `mask_length` is `null` for a gateway that is not in ONE-IP mode and `vr_id` is `null` for a gateway without a VRID |
| `anycast_gateways_state` | list of dict | Returned when state is `gathered`. Read-only data of the gathered interfaces, one entry per entry of `gathered`: `vlan_id`, `mac_address`, `l2vsn_isid` and `oper_state` (`null` when the state endpoint does not report it) |
| `anycast_gateways` | list of dict | Per-resource operation results. Each `after` is re-read from the device after a real change, the predicted state otherwise (check mode, or when the device does not return the interface) |
| `api_responses` | dict | Raw REST API responses, for debugging. **Deprecated**, will be removed in 2.0.0 - use `before` and `after` for the configuration before and after a change, `gathered` for `state: gathered`, and `anycast_gateways` for the per-interface results; when a re-create fails, the failure `details` report whether the original gateway was restored |

---

## [Examples](#table-of-contents)

### Gather interface state

```yaml
- name: Gather current Anycast Gateway configuration
  extreme.fe.extreme_fe_anycast_gateway:
    state: gathered
```

### Re-apply gathered configuration

`gathered` holds only the `config` options, so it can be fed back as is; re-applying it changes nothing.

```yaml
- name: Gather Anycast GW configuration
  extreme.fe.extreme_fe_anycast_gateway:
    state: gathered
  register: ag

- name: Re-apply the gathered configuration
  extreme.fe.extreme_fe_anycast_gateway:
    state: replaced
    config: "{{ ag.gathered }}"
```

### Create interface

```yaml
- name: Create Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: merged
    config:
      - vlan_id: 100
        ip_address: 10.10.10.1
        mask_length: 24
        one_ip: true
        enabled: true
```

### Replace interface config

```yaml
- name: Replace Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: replaced
    config:
      - vlan_id: 100
        ip_address: 10.10.10.254
        mask_length: 24
        one_ip: true
        enabled: true
```

### Change the address of a regular (not ONE-IP) interface

```yaml
- name: Change the address of a regular (not ONE-IP) Anycast GW on VLAN 300
  extreme.fe.extreme_fe_anycast_gateway:
    state: replaced
    config:
      - vlan_id: 300
        ip_address: 10.30.30.254
        vr_id: 30
        enabled: true
```

### Delete interfaces

```yaml
- name: Delete Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: deleted
    config:
      - vlan_id: 100

- name: Delete all Anycast GW interfaces
  extreme.fe.extreme_fe_anycast_gateway:
    state: deleted
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.


```yaml
- name: Manage Anycast Gateway interfaces
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current Anycast Gateway configuration
      extreme.fe.extreme_fe_anycast_gateway:
        state: gathered

    - name: Create Anycast GW on VLAN 100 (ONE-IP)
      extreme.fe.extreme_fe_anycast_gateway:
        state: merged
        config:
          - vlan_id: 100
            ip_address: 10.10.10.1
            mask_length: 24
            one_ip: true
            enabled: true

    - name: Replace Anycast GW on VLAN 100
      extreme.fe.extreme_fe_anycast_gateway:
        state: replaced
        config:
          - vlan_id: 100
            ip_address: 10.10.10.254
            mask_length: 24
            one_ip: true
            enabled: true

    - name: Change the address of a regular (not ONE-IP) Anycast GW on VLAN 300
      extreme.fe.extreme_fe_anycast_gateway:
        state: replaced
        config:
          - vlan_id: 300
            ip_address: 10.30.30.254
            vr_id: 30
            enabled: true

    - name: Override all Anycast GW interfaces
      extreme.fe.extreme_fe_anycast_gateway:
        state: overridden
        config:
          - vlan_id: 100
            ip_address: 10.10.10.1
            mask_length: 24
            one_ip: true
            enabled: true

    - name: Delete Anycast GW on VLAN 100
      extreme.fe.extreme_fe_anycast_gateway:
        state: deleted
        config:
          - vlan_id: 100

    - name: Delete all Anycast GW interfaces
      extreme.fe.extreme_fe_anycast_gateway:
        state: deleted
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
