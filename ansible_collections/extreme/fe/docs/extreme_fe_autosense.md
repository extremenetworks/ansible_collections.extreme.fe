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

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Desired module operation. See State Behaviour Summary below. |
| `global_settings` | dict | No | - | Global autosense settings applied through `/v0/configuration/autosense` |
| `global_settings.access_diffserv_enabled` | bool | No | - | Enable the access DiffServ profile for autosense ports |
| `global_settings.data_isid` | int | No | - | Data I-SID assigned to autosense data roles. `0` clears the value |
| `global_settings.dhcp_detection_enabled` | bool | No | - | Enable DHCP detection on autosense ports |
| `global_settings.dot1p_override_enabled` | bool | No | - | Enable 802.1p override for autosense traffic classes |
| `global_settings.dot1x_multihost` | dict | No | - | 802.1X multihost client limits for autosense ports |
| `global_settings.dot1x_multihost.eap_mac_max` | int | No | - | Maximum simultaneous EAP clients allowed |
| `global_settings.dot1x_multihost.mac_max` | int | No | - | Maximum MAC clients supported on 802.1X enabled ports |
| `global_settings.dot1x_multihost.non_eap_mac_max` | int | No | - | Maximum non-802.1X clients allowed on the port |
| `global_settings.fabric_attach` | dict | No | - | Fabric Attach global defaults for autosense ports |
| `global_settings.fabric_attach.auth_key` | dict | No | - | Fabric Attach authentication key properties |
| `global_settings.fabric_attach.auth_key.is_encrypted` | bool | No | - | True when the provided key value is already encrypted |
| `global_settings.fabric_attach.auth_key.value` | str | No | - | Secret material for the Fabric Attach authentication key |
| `global_settings.fabric_attach.msg_auth_enabled` | bool | No | - | Enable Fabric Attach message authentication |
| `global_settings.fabric_attach.camera` | dict | No | - | Camera role Fabric Attach settings |
| `global_settings.fabric_attach.camera.dot1x_status` | str | No | - | 802.1X status for camera ports (`AUTO` or `FORCE_AUTHORIZED`) |
| `global_settings.fabric_attach.camera.isid` | int | No | - | Fabric Attach camera I-SID. `0` clears the association |
| `global_settings.fabric_attach.ovs` | dict | No | - | Open vSwitch Fabric Attach profile |
| `global_settings.fabric_attach.ovs.isid` | int | No | - | Fabric Attach OVS I-SID. `0` clears the association |
| `global_settings.fabric_attach.ovs.status` | str | No | - | 802.1X status for the OVS role (`AUTO` or `FORCE_AUTHORIZED`) |
| `global_settings.fabric_attach.proxy` | dict | No | - | Fabric Attach proxy defaults |
| `global_settings.fabric_attach.proxy.mgmt_cvid` | int | No | - | Management CVID used for Fabric Attach proxy traffic |
| `global_settings.fabric_attach.proxy.mgmt_isid` | int | No | - | Management I-SID used for proxy traffic. `0` clears the value |
| `global_settings.fabric_attach.proxy.no_auth_isid` | int | No | - | Proxy I-SID used when authentication is not required |
| `global_settings.fabric_attach.wap_type1` | dict | No | - | Wireless access point (type 1) Fabric Attach settings |
| `global_settings.fabric_attach.wap_type1.isid` | int | No | - | WAP I-SID. `0` clears the association |
| `global_settings.fabric_attach.wap_type1.status` | str | No | - | 802.1X status for the WAP role (`AUTO` or `FORCE_AUTHORIZED`) |
| `global_settings.isis` | dict | No | - | ISIS parameters applied to autosense ports |
| `global_settings.isis.hello_auth` | dict | No | - | ISIS Hello authentication profile |
| `global_settings.isis.hello_auth.key` | dict | No | - | Authentication key configuration |
| `global_settings.isis.hello_auth.key.is_encrypted` | bool | No | - | True when supplying an encrypted or obfuscated secret |
| `global_settings.isis.hello_auth.key.value` | str | No | - | Secret value for ISIS Hello authentication |
| `global_settings.isis.hello_auth.key_id` | int | No | - | ISIS Hello authentication key identifier |
| `global_settings.isis.hello_auth.type` | str | No | - | Authentication type (`HMAC_MD5`, `HMAC_SHA_256`, `SIMPLE`, `NONE`) |
| `global_settings.isis.l1_metric` | int | No | - | ISIS Level-1 metric applied to autosense interfaces |
| `global_settings.isis.l1_metric_auto_enabled` | bool | No | - | Enable automatic calculation of the ISIS Level-1 metric |
| `global_settings.onboarding_isid` | int | No | - | Onboarding I-SID used while autosense negotiations complete. `0` clears the value |
| `global_settings.voice` | dict | No | - | Voice autosense profile defaults |
| `global_settings.voice.cvid` | int | No | - | Voice CVID applied to autosense ports handling tagged voice traffic |
| `global_settings.voice.dot1x_lldp_auth_enabled` | bool | No | - | Enable LLDP-based 802.1X authentication for voice endpoints |
| `global_settings.voice.isid` | int | No | - | Voice I-SID used by autosense ports. `0` clears the association |
| `global_settings.wait_interval` | int | No | - | Global wait interval (seconds) used by the autosense state machine |
| `ports` | list of dict | No | - | Per-port autosense overrides |
| `ports[].name` | str | Yes | - | Port identifier (slot:port notation such as `1:5`) |
| `ports[].enable` | bool | No | - | Enable or disable autosense on the specified port |
| `ports[].nsi` | int | No | - | Network service identifier (I-SID). `0` clears the association |
| `ports[].wait_interval` | int | No | - | Port-specific wait interval in seconds (overrides global timer) |
| `gather_filter` | list of str | No | - | Port identifiers to limit gathered output |
| `gather_state` | bool | No | `false` | Include data from `/v0/state/autosense/ports` in the result |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Apply provided settings as an incremental merge. | GET, PATCH |
| `replaced` | Make supplied values authoritative for targeted resources. | GET, PATCH, DELETE |
| `overridden` | Replace running configuration; remove entries not provided. | GET, PATCH, DELETE |
| `deleted` | Remove specified per-port overrides. | GET, DELETE |
| `gathered` | Read-only — return current configuration and optional state. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `global_settings` | dict | Resulting global autosense configuration (snake_case keys) |
| `ports_settings` | list | List of per-port autosense settings with normalized field names |
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
    ports:
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
    ports:
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
