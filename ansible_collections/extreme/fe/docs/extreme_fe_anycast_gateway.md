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
- Once created, `ip_address`, `mask_length`, `one_ip` and `vr_id` cannot be changed. `state=merged` fails if you try to change them on an existing interface; use `state=replaced` (DELETE + re-POST) instead.
- For `state=replaced` and `state=overridden`, omitted immutable fields are treated as "don't care": only provided immutable fields are compared. Omitted immutable fields are taken from the existing interface when it is re-created (`mask_length` only when the resulting interface is in ONE-IP mode).
- `mask_length` can only be specified when `one_ip=true` (Fabric Engine constraint: `IP Address mask allowed only with Anycast Gateway ONE-IP.`). The module never sends a mask length for an interface that is not in ONE-IP mode. The device reports a mask length of 0 for such an interface, which means "not set", and the module returns `mask_length: null` for it.
- Before an interface is deleted for a re-create, the module builds the POST body and validates it locally. A request that cannot succeed (a `mask_length` without ONE-IP, or ONE-IP without a `mask_length`) fails without touching the device, also in check mode.
- Creating a new interface with `one_ip=true` requires `mask_length`. Without it the task fails before anything is
  sent to the device, also in check mode.
- If the re-create fails after the DELETE (the POST or the follow-up `enabled` PATCH is rejected), the module restores the original interface from the state it captured before the change, re-enables it if it was enabled, and then fails the task with the original error plus a statement that the original was restored. `changed` is `false` in that failure unless other interfaces of the same task were already modified. The failure `details` report the outcome (`rollback`, `original_payload`, `original_enabled`, `rollback_error`); the raw responses are also recorded in the deprecated `api_responses` as `replace_rollback_delete_<vlan_id>`, `replace_rollback_post_<vlan_id>` and `replace_rollback_enable_<vlan_id>`.
- If the restore itself fails, the message says so, `changed` is `true`, and `details.original_payload` (with `details.original_enabled`) holds what is needed to re-create the interface by hand.
- A DELETE or POST of a re-create that fails without an answer from the device (a transport error, for example a lost
  response) does not prove the device did not carry it out, so the module reads that VLAN back. If the DELETE was in
  fact carried out (the gateway is gone), or the POST was (the gateway exists with the requested `ip_address`,
  `one_ip`, `vr_id` and, for ONE-IP, `mask_length`), the re-create continues and a warning says the response was lost.
  Otherwise the failure is handled as described above. An error that the device returns in the response body, or an
  HTTP error status, is definitive and is handled as described above without reading the VLAN back. The exceptions are
  HTTP 409 on the POST and HTTP 404 on the DELETE, which a resend of a request that was already carried out gets back;
  the VLAN is read back for them as for a transport error.
- If the follow-up `enabled` PATCH fails without an answer, the new interface is read back. If it already has the
  requested `enabled`, the re-create succeeds and a warning says the response was lost; if it does not, the original is
  restored as described above. If it cannot be read back, the new interface may be enabled, so before it is deleted to
  restore the original it is disabled (checked the same way as any disable before a delete). If it cannot be disabled,
  it is not deleted; the task fails with a message that the new interface still exists and the original was not
  restored, `changed` is `true`, and `details` hold `rollback: not restored`, `replacement_kept: true` and
  `original_payload`. The raw responses are recorded in the deprecated `api_responses` as
  `replace_rollback_disable_<vlan_id>` (read-back: `replace_rollback_verify_patch_filtered_<vlan_id>`).
- The DELETE of the new interface and the POST of the original during that restore are checked the same way. If one of
  them fails without an answer (or with the HTTP 404 or 409 of a resend) and the read-back shows it was carried out (the
  new interface is gone, or the original exists again with its `ip_address`, `one_ip`, `vr_id` and, for ONE-IP,
  `mask_length`), the restore continues, the original is re-enabled if it was enabled, and a warning says the response
  was lost; the task then fails exactly as after any successful restore. If the device rejects the DELETE of the new
  interface (an error in the response body or an HTTP error status), or the read-back shows that it was not deleted, or
  that the VLAN holds a gateway with other values than the original, the message says so, `changed` is `true`, and
  `details` hold `rollback: not restored` (with `replacement_kept: true` when the new interface is still there). If
  the VLAN cannot be read back, the task fails with a message that the state of the gateway is unknown, `changed` is
  `true`, and `details` also hold `rollback: unknown` and `rollback_error`. The read-backs are recorded in the
  deprecated `api_responses` as `replace_rollback_verify_delete_filtered_<vlan_id>` (and
  `replace_rollback_verify_delete_state_<vlan_id>`) and `replace_rollback_verify_post_filtered_<vlan_id>`.
- The PATCH that disables an interface before it is deleted (re-create, `deleted`, `overridden`) is checked the same
  way. If it fails without an answer and the read-back shows the interface disabled, the module re-enables it and fails
  the task with the original error plus a statement that the gateway was re-enabled; `changed` is then `false` unless
  other interfaces of the same task were already modified, and `true` if it could not be re-enabled. The same `changed`
  rule applies when the disable of `deleted` or `overridden` fails without changing that interface.
- The DELETE of `deleted` and of the `overridden` pre-pass is checked the same way. If it fails without an answer (or
  with the HTTP 404 of a resend), the module reads that VLAN back. If the gateway is gone, the DELETE was carried out;
  the interface is reported as deleted, a warning says the response was lost and the task continues. If the gateway is
  still there, the task fails with the DELETE error plus a statement that the gateway is still configured (and
  disabled, if the module disabled it for the delete; it is not re-enabled). Any other DELETE failure is definitive and
  the VLAN is not read back. When the task fails because the gateway is still configured, `changed` is `true` if the
  module left it disabled, and otherwise `false` unless other interfaces of the same task were already modified. The
  read-backs are recorded in the deprecated `api_responses` as `delete_verify_delete_filtered_<vlan_id>` (and
  `delete_verify_delete_state_<vlan_id>`) for `deleted`, and `override_delete_verify_delete_filtered_<vlan_id>` (and
  `override_delete_verify_delete_state_<vlan_id>`) for `overridden`.
- If the VLAN cannot be read back after such a failure, the task fails with a message that the state of the gateway is
  unknown, `changed` is `true`, and `details` hold `vlan_id`, `original_payload`, `original_enabled`, the request error
  (`patch_error`, `delete_error` or `post_error`) and `read_error`. After the DELETE of `deleted` or the `overridden`
  pre-pass the message advises running the task again if the gateway is still there; after a re-create it advises
  re-creating the original from `original_payload` if the VLAN has no gateway.
- A read of a single VLAN treats HTTP 404 and 422 as "no Anycast Gateway", whether the device raises the status or
  returns it in the response body (for example a body with `statusCode` 404). The same applies to the read of the state
  endpoint that checks whether a gateway is still there after a failed request.
- An `enabled` PATCH (of `merged`, of `replaced` or `overridden` when only `enabled` differs, after a create or
  re-create, and when the original is re-enabled during a restore) and the POST that creates a missing interface are
  checked the same way when they fail without an answer (for the POST also the HTTP 409 of a resend). The VLAN is read
  back. If the request was carried out (the gateway has the requested `enabled`, or exists with the requested
  `ip_address`, `one_ip`, `vr_id` and, for ONE-IP, `mask_length`), the task continues and a warning says the response
  was lost. If it was not, the task fails with the request error. If the VLAN cannot be read back, the task fails with a
  message that the state of the gateway is unknown, `changed` is `true`, and `details` hold `vlan_id`,
  `state: unknown`, the request error and `read_error` (a restore that cannot tell whether the original was re-enabled
  also holds `rollback: unknown`). The read-backs are recorded in the deprecated `api_responses` as
  `<request key>_verify_filtered_<vlan_id>` (for example `patch_<vlan_id>_verify_filtered_<vlan_id>`) and
  `create_verify_post_filtered_<vlan_id>`.
- A failed task reports `changed: true` whenever the device was already modified, for example by an earlier entry of
  `config`, by the `overridden` pre-pass, or by the POST of a new interface whose `enabled` PATCH then failed (the
  message then says the interface was created). It reports `changed: false` when nothing was written, and always in
  check mode.
- The module automatically disables an interface before deleting it, as required by Fabric Engine.
- Supports check mode and diff mode. Under `--diff` the module reports the Anycast Gateway configuration of the whole device before and after the change; combined with `--check` the reported `after` is the state that would have been written.

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
