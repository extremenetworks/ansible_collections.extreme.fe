# Link Layer Discovery Protocol (LLDP) - Interface Settings

## Module: extreme.fe.extreme_fe_lldp_interfaces

Manages LLDP interface settings on Fabric Engine devices.

---

Version added: 1.0.0

## Table of Contents

- [Description](#description)
- [Notes](#notes)
- [Requirements](#requirements)
- [REST API Endpoints](#rest-api-endpoints)
- [Parameters](#parameters)
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

This module manages LLDP interface-level settings on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports LLDP transmit/receive control, advertised TLVs, location data, and MED network policy entries.

---

## [Notes](#table-of-contents)

- On Fabric Engine, `transmit_enabled` and `receive_enabled` must use the same value; if only one is supplied, the module mirrors it to the other.
- If LLDP transmit or receive is disabled, the device ignores advertisement/location attributes in the same request; the module submits only the basic LLDP enable flags in that case.
- The MED network policy is written through a separate endpoint, and only while LLDP is enabled. Disabling a port's LLDP therefore leaves the policy the device already holds in place, just as it leaves the advertisement and location attributes.
- When `med_policy` is supplied, it is treated as the authoritative list for that interface because the device API replaces the full MED policy list.
- The device returns `civic_address` with a `ldp location-identification civic-address` CLI prefix attached.
  That prefix is stripped from gathered output, so a value read back from the device can be re-applied unchanged.
- `civic_address` is validated before any request is sent. It must start with `country-code` followed by exactly two
  letters, must contain at least one more supported label, and every label needs a value. An unsupported or
  misspelled label (for example `postal-code`) makes the task fail naming the interface and label, because the device
  would silently drop it or append it to the previous value and advertise a wrong emergency location. Unquoted values
  run to the next supported label, so a value containing a label-like word must be quoted, for example
  `street "Main room"`.
- `state: gathered` returns the interface list under the standard `gathered` key, each entry in the shape of a
  `config` entry, so the list can be applied back as `config` without a change. It is also still returned under
  `interfaces_settings` in the `{name, settings}` form used up to 1.2.1, so existing playbooks keep working; that
  form is deprecated and will be removed in 2.0.0.
- `state: deleted` without `config` (or with an empty list) resets every discovered interface to its LLDP defaults.
- Returns `before` and `after` snapshots of every targeted interface, whether or not anything changed, in the same
  shape as `gathered`.
- Supports check mode (`--check`) to preview a change without sending it, and diff mode (`--diff`) to show the
  before and after interface settings.
- Each interface is written with up to two requests, the LLDP settings PUT and then the MED policy PUT, and is
  re-read afterwards. Both requests always send their whole section, so the settings PUT is resent unchanged for a
  MED-policy-only change. When a request fails after the settings PUT succeeded, the task fails and the message
  names the request that failed and the one(s) already applied; it reports `changed=true` only when one of the
  applied requests differed from the interface's settings. A failure on a later interface also reports
  `changed=true` and lists the interfaces this task already changed (`details.changed_interfaces`).
- Tested against Fabric Engine Version 9.3.2.
- A PUT that fails without an answer (a lost connection) may have been applied, so the task reports `changed: true` with `details.outcome: unknown`.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/lldp | Get all LLDP port configurations |
| PUT | /v0/configuration/lldp/ports/{port} | Configure LLDP on port |
| PUT | /v0/configuration/lldp/ports/{port}/med-policy | Configure MED policy |
| GET | /v0/state/lldp/ports/{port} | Get LLDP neighbor state |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | No | - | Per-port LLDP settings. Required for `merged`, `replaced` and `overridden`; `deleted` without it resets every interface. Named `interfaces` up to 1.2.1; that name still works as a deprecated alias and will be removed in 2.0.0 |
| `config[].name` | str | Yes | - | Port identifier (slot:port) |
| `config[].transmit_enabled` | bool | No | - | Enable LLDP transmit |
| `config[].receive_enabled` | bool | No | - | Enable LLDP receive |
| `config[].advertise` | dict | No | - | TLVs to advertise |
| `config[].advertise.system_capabilities` | bool | No | - | Advertise system capabilities |
| `config[].advertise.system_description` | bool | No | - | Advertise system description |
| `config[].advertise.system_name` | bool | No | - | Advertise system name |
| `config[].advertise.port_description` | bool | No | - | Advertise port description |
| `config[].advertise.management_address` | bool | No | - | Advertise management address |
| `config[].advertise.med_capabilities` | bool | No | - | Advertise MED capabilities |
| `config[].advertise.med_power` | bool | No | - | Advertise MED power |
| `config[].advertise.dot3_mac_phy` | bool | No | - | Advertise 802.3 MAC/PHY |
| `config[].advertise.location` | bool | No | - | Advertise MED location |
| `config[].advertise.network_policy` | bool | No | - | Advertise MED network policy |
| `config[].advertise.inventory` | bool | No | - | Advertise MED inventory |
| `config[].location` | dict | No | - | LLDP-MED location data |
| `config[].location.civic_address` | str | No | - | Civic address; must start with `country-code` plus exactly two letters and contain at least one more label. Supported labels: `country-code`, `additional-code`, `additional-information`, `apartment`, `block`, `building`, `city`, `city-district`, `county`, `floor`, `house-number`, `house-number-suffix`, `landmark`, `leading-street-direction`, `name`, `place-type`, `pobox`, `postal-community-name`, `postal-zip-code`, `room-number`, `state`, `street`, `street-suffix`, `trailing-street-suffix`. Any other label (for example `postal-code`, `province-state`, `postal-zip`, `room`, `unit`, `language`) is rejected before any request is sent. Unquoted values run to the next supported label; quote a value containing a label-like word (`street "Main room"`). Label order and quoting do not matter when compared with the device |
| `config[].location.ecs_elin` | str | No | - | ELIN identifier |
| `config[].location.coordinate` | str | No | - | Geographic coordinate |
| `config[].med_policy` | list of dict | No | - | MED network policies (authoritative list) |
| `config[].med_policy[].type` | str | Yes | - | Policy type: `VOICE`, `VOICE_SIGNALING`, `GUEST_VOICE`, `GUEST_VOICE_SIGNALING`, `SOFT_PHONE_VOICE`, `VIDEO_CONFERENCING`, `STREAMING_VIDEO`, `VIDEO_SIGNALING` |
| `config[].med_policy[].dscp` | int | Yes | - | DSCP value |
| `config[].med_policy[].priority` | int | Yes | - | 802.1p priority |
| `config[].med_policy[].tagged` | bool | Yes | - | Whether traffic is tagged |
| `config[].med_policy[].vlan_id` | int | Yes | - | VLAN ID |
| `gather_filter` | list of str | No | - | Limit gathered output to these ports |
| `gather_state` | bool | No | `false` | Include LLDP neighbor state |

The deprecated `interfaces` alias takes the same nested options, so `interfaces[].name` and `config[].name`
mean the same thing.

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `gathered` | list | LLDP interface configuration read from the device, as `config` entries (`state: gathered` only) |
| `interfaces_settings` | list | Normalized LLDP settings per interface, as `{name, settings}`. **Deprecated** for `state: gathered`, will be removed in 2.0.0 - use `gathered` |
| `interface_updates` | list | Interfaces updated during the run |
| `interface_removals` | list | Interfaces reset to defaults |
| `before` | list | LLDP settings for every targeted interface as they were before the task ran |
| `after` | list | LLDP settings for every targeted interface once the task has run; the predicted state in check mode |
| `interfaces_state` | list | LLDP operational state per interface |
| `api_responses` | dict | Raw API responses, for debugging. **Deprecated**, will be removed in 2.0.0 - use `before` and `after` for the configuration before and after a change, `gathered` for `state: gathered`, and `interfaces_state` for the operational state when `gather_state` is true. The normalized snapshots do not contain the raw responses |

---

## [Examples](#table-of-contents)

### Enable LLDP on a port with advertisements

```yaml
- name: Enable LLDP on port 1:5
  extreme.fe.extreme_fe_lldp_interfaces:
    state: merged
    config:
      - name: "1:5"
        transmit_enabled: true
        receive_enabled: true
```

### Configure MED policy

```yaml
- name: Set MED policy on port 1:10
  extreme.fe.extreme_fe_lldp_interfaces:
    state: replaced
    config:
      - name: "1:10"
        transmit_enabled: true
        receive_enabled: true
        med_policy:
          - type: VOICE
            dscp: 46
            priority: 5
            tagged: true
            vlan_id: 100
```

### Configure a civic address location

```yaml
- name: Set the LLDP-MED civic address on port 1:5
  extreme.fe.extreme_fe_lldp_interfaces:
    state: merged
    config:
      - name: "1:5"
        location:
          civic_address: "country-code US state CA city San Jose street Extreme Networks postal-zip-code 95134 room-number 101"
```

### Gather LLDP interface settings

```yaml
- name: Collect LLDP interface settings with neighbor state
  extreme.fe.extreme_fe_lldp_interfaces:
    state: gathered
    gather_state: true
  register: lldp_ports
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage LLDP interfaces on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current LLDP interface settings
      extreme.fe.extreme_fe_lldp_interfaces:
        state: gathered
        gather_state: true
      register: lldp_before

    - name: Enable LLDP on access ports
      extreme.fe.extreme_fe_lldp_interfaces:
        state: merged
        interfaces:
          - name: "1:5"
            transmit_enabled: true
            receive_enabled: true
          - name: "1:6"
            transmit_enabled: true
            receive_enabled: true

    - name: Reset LLDP on unused ports
      extreme.fe.extreme_fe_lldp_interfaces:
        state: deleted
        interfaces:
          - name: "1:7"
          - name: "1:8"
```

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
