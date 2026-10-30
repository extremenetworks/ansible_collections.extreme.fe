# Auto-Sense

## Module: extreme.fe.extreme_fe_autosense

Manages Fabric Engine autosense settings and port behaviour.

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

This module manages global autosense settings and per-port overrides on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports Fabric Attach profiles, voice and DiffServ parameters, multihost limits, onboarding defaults, and per-port autosense toggles and wait timers.
- Provides a gathered mode that reports the full configuration and live autosense port state from `/v0/state/autosense/ports`.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- Each port may be listed once in `config`; a port listed twice fails before any request.
- A PATCH or DELETE that fails without an answer (a lost connection) and cannot be confirmed (the re-read fails, or the PATCH carries a key the re-read cannot compare and no other field is confirmed applied) may have been applied, so the task reports `changed: true` with `details.outcome: unknown`. A per-port DELETE answered with 404 counts as done: the override was just read as present, and a DELETE resent after a lost answer finds it gone.
- When the device does not report whether it implements the per-port DELETE, check mode cannot tell and warns; its prediction assumes the DELETE and shows the ports removed.
- Ports are supplied through the `config` list. The parameter was named `ports` before 1.2.1; that name still works as a deprecated alias.
- Port identifiers must use slot:port notation such as `1:5`.
- The Fabric Attach authentication key (`global_settings.fabric_attach.auth_key.value`) and the ISIS Hello authentication key (`global_settings.isis.hello_auth.key.value`) are secrets. A supplied value is masked in the task invocation, and the module never returns the stored key, so `gathered`, `global_settings`, `before`, `after` and `--diff` omit `value`; `is_encrypted` is not a secret and stays visible. The `extreme_fe` HTTPAPI plugin also keeps the `/v0/configuration/autosense` request and response bodies out of the `-vvv` log and the HTTP trace file. A device error message is reported with any key value removed; a connection or transport failure on that endpoint is reported with its detail redacted.
- Supports check mode and diff mode. Under `--diff` the module reports the global settings and the per-port overrides of the whole device before and after the change, including the ports that `overridden` removes; combined with `--check` the reported `after` is the state that would have been written.
- The global settings and each port override are updated with one PATCH carrying every changed field. The device may apply part of such a request and still reject it, so on a rejected update the module re-reads the resource and reports which fields were and were not applied. The failure message names them, and `details` holds `attempted_payload` (secret key values masked), `applied_fields`, `not_applied_fields`, `unverifiable_fields` (secret keys whose read-back differs, as the device may return them obscured), `unchanged_fields` (already at the requested value), `resource` and `status_code` when known, all as dotted REST paths such as `fabricAttach.proxy.mgmtIsid`. The task then reports `changed=true` when any field was applied. If the re-read fails as well, `details` holds `reread_error` and part of the payload may be applied.
- A PATCH answered with a success status but an error document (`errorCode`, a `statusCode` of 400 or more, or an `errors` list) fails the same way, for the global settings and for a port. Its body is reported in `details` with any key value masked, and key values are removed from the failure message.
- A per-port DELETE answered with a success status but an error document is not taken as a removal: an embedded 405 falls back to the PATCH like an HTTP 405, and any other error fails the task with the device's message (body in `details`, key values masked), leaving the override as it is.
- The API takes `fabric_attach.auth_key` (`is_encrypted`, `value`) and `isis.hello_auth` (`key`, `key_id`, `type`) as whole objects, and the device returns a stored key only in a hashed or obscured form, so the module never sends a key value it read from the device. When only part of one of these objects is supplied, an omitted `is_encrypted`, `key_id` or `type` keeps its device value, but a change that would have to re-send the stored key fails before any write, in every state and in check mode. So `fabric_attach.auth_key.is_encrypted` is changed only together with `fabric_attach.auth_key.value`, and `isis.hello_auth.key.is_encrypted`, `key_id` or `type` only together with `isis.hello_auth.key.value`. A partial object equal to the device is a no-op and does not fail. When the resulting `isis.hello_auth.type` is NONE and no key value is supplied, the factory empty key is sent instead of the stored one.
- Under `replaced` and `overridden` an omitted `isis.hello_auth` is reset to its factory default (`type` NONE, `key_id` 0, empty key), while an omitted `fabric_attach.auth_key` is left unchanged.
- Fields with no documented factory default are never reset and keep their device value when omitted, in every state: `fabric_attach.auth_key`, the `dot1x_multihost` counts, `isis.l1_metric` and `wait_interval`. Change the Fabric Attach authentication key only by supplying `fabric_attach.auth_key`.
- A task that fails after one of its writes succeeded (the global settings PATCH, a port PATCH or DELETE) reports `changed=true`, whichever later request failed.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/autosense | Retrieve global autosense settings |
| PATCH | /v0/configuration/autosense | Update global autosense settings |
| GET | /v0/configuration/autosense/port | List all per-port overrides |
| GET | /v0/configuration/autosense/port/{port} | Get a specific port override |
| PATCH | /v0/configuration/autosense/port/{port} | Update a port override |
| DELETE | /v0/configuration/autosense/port/{port} | Remove a port override |
| GET | /v0/state/autosense/ports | Get live autosense port state |
| GET | /v0/state/capabilities/urls | Whether the device implements the per-port DELETE (read once, before removing a port override) |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Desired module operation. See State Behaviour Summary below. |
| `global_settings` | dict | No | - | Global autosense settings applied through `/v0/configuration/autosense` |
| `global_settings.access_diffserv_enabled` | bool | No | - | Enable the access DiffServ profile for autosense ports |
| `global_settings.data_isid` | int | No | - | Data ISID assigned to autosense data roles. `0` clears the value |
| `global_settings.dhcp_detection_enabled` | bool | No | - | Enable DHCP detection on autosense ports |
| `global_settings.dot1p_override_enabled` | bool | No | - | Enable 802.1p override for autosense traffic classes |
| `global_settings.dot1x_multihost` | dict | No | - | 802.1X multihost client limits for autosense ports |
| `global_settings.dot1x_multihost.eap_mac_max` | int | No | - | Maximum simultaneous EAP clients allowed |
| `global_settings.dot1x_multihost.mac_max` | int | No | - | Maximum MAC clients supported on 802.1X enabled ports |
| `global_settings.dot1x_multihost.non_eap_mac_max` | int | No | - | Maximum non-802.1X clients allowed on the port |
| `global_settings.fabric_attach` | dict | No | - | Fabric Attach global defaults for autosense ports |
| `global_settings.fabric_attach.auth_key` | dict | No | - | Fabric Attach authentication key properties. Supply `value` to change `is_encrypted`. The stored key is never re-sent, so a change of `is_encrypted` alone fails |
| `global_settings.fabric_attach.auth_key.is_encrypted` | bool | No | - | True when the provided key value is already encrypted |
| `global_settings.fabric_attach.auth_key.value` | str | No | - | Secret material for the Fabric Attach authentication key. Masked in logs and task output; never returned by the module |
| `global_settings.fabric_attach.msg_auth_enabled` | bool | No | - | Enable Fabric Attach message authentication |
| `global_settings.fabric_attach.camera` | dict | No | - | Camera role Fabric Attach settings |
| `global_settings.fabric_attach.camera.dot1x_status` | str | No | - | 802.1X status for camera ports (`AUTO` or `FORCE_AUTHORIZED`) |
| `global_settings.fabric_attach.camera.isid` | int | No | - | Fabric Attach camera ISID. `0` clears the association |
| `global_settings.fabric_attach.ovs` | dict | No | - | Open vSwitch Fabric Attach profile |
| `global_settings.fabric_attach.ovs.isid` | int | No | - | Fabric Attach OVS ISID. `0` clears the association |
| `global_settings.fabric_attach.ovs.status` | str | No | - | 802.1X status for the OVS role (`AUTO` or `FORCE_AUTHORIZED`) |
| `global_settings.fabric_attach.proxy` | dict | No | - | Fabric Attach proxy defaults |
| `global_settings.fabric_attach.proxy.mgmt_cvid` | int | No | - | Management CVID used for Fabric Attach proxy traffic |
| `global_settings.fabric_attach.proxy.mgmt_isid` | int | No | - | Management ISID used for proxy traffic. `0` clears the value |
| `global_settings.fabric_attach.proxy.no_auth_isid` | int | No | - | Proxy ISID used when authentication is not required |
| `global_settings.fabric_attach.wap_type1` | dict | No | - | Wireless access point (type 1) Fabric Attach settings |
| `global_settings.fabric_attach.wap_type1.isid` | int | No | - | WAP ISID. `0` clears the association |
| `global_settings.fabric_attach.wap_type1.status` | str | No | - | 802.1X status for the WAP role (`AUTO` or `FORCE_AUTHORIZED`) |
| `global_settings.isis` | dict | No | - | ISIS parameters applied to autosense ports |
| `global_settings.isis.hello_auth` | dict | No | - | ISIS Hello authentication profile. Changing `key.is_encrypted`, `key_id` or `type` requires `key.value`, as the stored key is never re-sent. The exception is a resulting `type` of NONE, which sends the factory empty key when no `key.value` is supplied |
| `global_settings.isis.hello_auth.key` | dict | No | - | Authentication key configuration |
| `global_settings.isis.hello_auth.key.is_encrypted` | bool | No | - | True when supplying an encrypted or obfuscated secret |
| `global_settings.isis.hello_auth.key.value` | str | No | - | Secret value for ISIS Hello authentication. Masked in logs and task output; never returned by the module |
| `global_settings.isis.hello_auth.key_id` | int | No | - | ISIS Hello authentication key identifier |
| `global_settings.isis.hello_auth.type` | str | No | - | Authentication type (`HMAC_MD5`, `HMAC_SHA_256`, `SIMPLE`, `NONE`) |
| `global_settings.isis.l1_metric` | int | No | - | ISIS Level-1 metric applied to autosense interfaces |
| `global_settings.isis.l1_metric_auto_enabled` | bool | No | - | Enable automatic calculation of the ISIS Level-1 metric |
| `global_settings.onboarding_isid` | int | No | - | Onboarding ISID used while autosense negotiations complete. `0` clears the value |
| `global_settings.voice` | dict | No | - | Voice autosense profile defaults |
| `global_settings.voice.cvid` | int | No | - | Voice CVID applied to autosense ports handling tagged voice traffic |
| `global_settings.voice.dot1x_lldp_auth_enabled` | bool | No | - | Enable LLDP-based 802.1X authentication for voice endpoints |
| `global_settings.voice.isid` | int | No | - | Voice ISID used by autosense ports. `0` clears the association |
| `global_settings.wait_interval` | int | No | - | Global wait interval (seconds) used by the autosense state machine |
| `config` | list of dict | No | - | Per-port autosense overrides. Aliased as `ports`, the pre-1.2.1 name, which is deprecated but still accepted |
| `config[].name` | str | Yes | - | Port identifier (slot:port notation such as `1:5`) |
| `config[].enable` | bool | No | - | Enable or disable autosense on the specified port |
| `config[].nsi` | int | No | - | Network service identifier (ISID). `0` clears the association |
| `config[].wait_interval` | int | No | - | Port-specific wait interval in seconds (overrides global timer) |
| `gather_filter` | list of str | No | - | Port identifiers to limit gathered output |
| `gather_state` | bool | No | `false` | Include data from `/v0/state/autosense/ports` in the result |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply provided settings as an incremental merge. | GET, PATCH |
| `replaced` | Make supplied values authoritative for targeted resources. | GET, PATCH, DELETE |
| `overridden` | Replace running configuration; remove entries not provided. | GET, PATCH, DELETE |
| `deleted` | Remove specified per-port overrides, returning each port to its factory defaults (autosense enabled, `nsi` 0, `wait_interval` 35); without `config` (or with an empty list), every port the device lists. Use `merged` with `enable: false` to turn autosense off. | GET, DELETE, PATCH |
| `gathered` | Read-only — return current configuration and optional state. The per-port overrides are returned under `gathered` as `config` entries, so they can be applied back without a change. | GET |

`merged` and `replaced` fail before any request when neither `config` nor `global_settings` is supplied. Under `merged` a `global_settings` with no suboption set counts as not supplied, while under `replaced` an empty `global_settings: {}` is accepted and resets the global settings. `overridden` fails before any request when `config` is omitted or empty, because it would delete every per-port override; use `deleted` without `config` to remove them all.

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `before` | dict | Global settings and per-port overrides before the task ran: `global_settings` and `config`, the per-port overrides as `config` entries like `gathered`. `ports` repeats them in the `{name, settings}` form returned up to 1.2.1; it is **deprecated**, will be removed in 2.0.0, and is not part of the `--diff` output - use `config`. Returned for every state except `gathered` |
| `after` | dict | The same after the task ran (`global_settings`, `config`, deprecated `ports`). Returned for every state except `gathered`. After a real change it is re-read from the device; in check mode it is the predicted state, that is the global settings and ports that would be written. A port whose override `overridden` or `deleted` removes is absent only after a successful per-port DELETE; where the device does not implement it (Fabric Engine 9.4), the port stays listed with its factory defaults (`enable: true`, `nsi: 0`, `wait_interval: 35`), in the re-read and in the check-mode prediction alike; when nothing changed it equals `before` |
| `global_settings` | dict | Resulting global autosense configuration (Ansible parameter names) |
| `gathered` | list | Per-port overrides as `config` entries (`name`, `enable`, `nsi`, `wait_interval`), `state: gathered` only. The global settings are in `global_settings` |
| `ports_settings` | list | List of per-port autosense settings with normalized field names, as `{name, settings}`. **Deprecated** for `state: gathered`, will be removed in 2.0.0 - use `gathered` |
| `port_updates` | list | Ports that were modified during execution |
| `port_removals` | list | Ports whose overrides were removed (deleted/overridden) |
| `ports_state` | list | Live autosense port state from `/v0/state/autosense/ports` |

---

## [Examples](#table-of-contents)

### Merge auto-sense port configuration

```yaml
- name: Enable auto-sense on access port 1:15 with a shorter wait interval
  extreme.fe.extreme_fe_autosense:
    state: merged
    config:
      - name: "1:15"
        enable: true
        wait_interval: 15
```

### Replace global Fabric Attach settings

```yaml
- name: Enforce Fabric Attach credentials and LLDP preferences
  extreme.fe.extreme_fe_autosense:
    state: replaced
    global_settings:
      fabric_attach:
        auth_key:
          is_encrypted: false
          value: "{{ fabric_attach_auth_key }}"
        msg_auth_enabled: true
      voice:
        dot1x_lldp_auth_enabled: true
```

### Delete auto-sense port overrides

```yaml
- name: Reset custom overrides on ports 1:5 and 1:6
  extreme.fe.extreme_fe_autosense:
    state: deleted
    config:
      - name: "1:5"
      - name: "1:6"
```

### Gather auto-sense configuration and state

```yaml
- name: Collect auto-sense information for ports 1:1 and 1:2
  extreme.fe.extreme_fe_autosense:
    state: gathered
    gather_filter:
      - "1:1"
      - "1:2"
    gather_state: true
  register: autosense_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.


```yaml
- name: Manage autosense configuration
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current auto-sense configuration and state
      extreme.fe.extreme_fe_autosense:
        state: gathered
        gather_state: true
      register: autosense_before

    - name: Enable auto-sense on access port with custom wait interval
      extreme.fe.extreme_fe_autosense:
        state: merged
        ports:
          - name: "1:15"
            enable: true
            wait_interval: 15

    - name: Enforce Fabric Attach credentials and voice LLDP auth
      extreme.fe.extreme_fe_autosense:
        state: replaced
        global_settings:
          fabric_attach:
            auth_key:
              is_encrypted: false
              value: "{{ fabric_attach_auth_key }}"
            msg_auth_enabled: true
          voice:
            dot1x_lldp_auth_enabled: true

    - name: Override global settings and ports (removes unlisted ports)
      extreme.fe.extreme_fe_autosense:
        state: overridden
        global_settings:
          data_isid: 10001
          onboarding_isid: 10002
          wait_interval: 30
        ports:
          - name: "1:1"
            enable: true
          - name: "1:2"
            enable: true
            wait_interval: 20

    - name: Remove auto-sense overrides from specific ports
      extreme.fe.extreme_fe_autosense:
        state: deleted
        ports:
          - name: "1:5"
          - name: "1:6"

    - name: Gather auto-sense configuration after changes
      extreme.fe.extreme_fe_autosense:
        state: gathered
        gather_state: true
      register: autosense_after
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
