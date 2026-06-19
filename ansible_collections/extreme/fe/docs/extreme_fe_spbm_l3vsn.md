# SPBM Layer 3 VSN

## Module: extreme.fe.extreme_fe_spbm_l3vsn

Manages SPBM Layer 3 VSN (L3VSN / IPVPN) on Fabric Engine devices.

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

This module manages SPBM Layer 3 Virtual Services Network (L3VSN / IPVPN) VPN instances on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- The configuration is grouped by VRF name with nested `ipv4` and `ipv6` sub-dictionaries, each representing one VPN instance.
- A VRF can have zero, one, or both address families configured.
- MVPN (Multicast VPN) settings can only be set at creation time.
- To change MVPN settings, delete the VPN instance and recreate it.
- For GlobalRouter (GRT), the I-SID is always 0 and cannot be changed.
- The `vpn_enabled` field controls IP Shortcuts admin status on GRT.

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
| GET | `/v0/configuration/spbm/l3vsn/vrf` | List all L3VSN VPN instances across all VRFs |
| POST | `/v0/configuration/spbm/l3vsn/vrf/{vr_name}` | Create an IPv4 or IPv6 VPN instance for a VRF |
| GET | `/v0/configuration/spbm/l3vsn/vrf/{vr_name}` | Get L3VSN config for a specific VRF |
| PATCH | `/v0/configuration/spbm/l3vsn/vrf/{vr_name}/ipvpn-type/{ipvpn_type}` | Update VPN instance settings (isid, vpnEnabled, isidName) |
| DELETE | `/v0/configuration/spbm/l3vsn/vrf/{vr_name}/ipvpn-type/{ipvpn_type}` | Delete a VPN instance for a VRF |

---

## [Platform Constraints](#table-of-contents)

- VRF name: string, 1–16 characters (OpenAPI spec says 32, firmware enforces 16)
- I-SID range: 0–15999999 for set operations (values above 16000000 reserved for dynamic L2 instances)
- I-SID 0 means "unset" — required for GlobalRouter (GRT)
- `vpn_enabled=true` requires an EP1 or Premier license on the device
- MVPN settings are immutable after creation (not in the PATCH schema)
- `ipvpn_type` is determined by the config key (`ipv4` / `ipv6`) and set at creation
- I-SID name: 0–64 characters
- MVPN forward cache timeout: 10–86400 seconds (default: 210)
- Filter I-SID lists are NOT managed by this module (future ISIS module)

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state: `merged`, `replaced`, `overridden`, `deleted`, `gathered` |
| `config` | list of dict | Yes (for merged/replaced/overridden) | — | List of L3VSN configurations grouped by VRF |
| `config[].vrf_name` | str | Yes | — | VRF name (1-16 chars, resource identifier). Use `GlobalRouter` for GRT. |
| `config[].ipv4` | dict | No | — | IPv4 VPN instance settings |
| `config[].ipv4.isid` | int | No | - | I-SID number (0-15999999). 0 = unset. Always 0 for GRT. |
| `config[].ipv4.vpn_enabled` | bool | No | - | Enable IP VPN node (requires EP1/Premier license) |
| `config[].ipv4.isid_name` | str | No | - | I-SID descriptive name (0-64 chars) |
| `config[].ipv4.mvpn` | dict | No | - | MVPN settings (create-time only, immutable after creation) |
| `config[].ipv4.mvpn.enabled` | bool | No | - | Enable MVPN on this VRF |
| `config[].ipv4.mvpn.forward_cache_timeout` | int | No | - | MVPN forward cache timeout in seconds (10-86400) |
| `config[].ipv6` | dict | No | — | IPv6 VPN instance settings (same sub-options as `ipv4`) |
| `gather_filter` | list of str | No | — | Limit gathered output to these VRF names |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create instances that don't exist (POST). Update patchable fields on existing instances if specified (PATCH). Unlisted instances untouched. | POST, PATCH |
| `replaced` | Create or update listed instances with complete patchable payload (omitted patchable fields reset to defaults). Unlisted instances untouched. | POST, PATCH |
| `overridden` | Delete unlisted instances, then apply `replaced` logic to listed ones. | DELETE, POST, PATCH |
| `deleted` | Delete specified instances. Three levels: empty config → delete all; vrf_name only → delete both IPv4+IPv6; vrf_name + ipv4/ipv6 → delete only specified. | DELETE |
| `gathered` | Read-only — return current L3VSN state. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any L3VSN configuration was modified |
| `l3vsn` | list of dict | Per-VRF operation results |
| `l3vsn[].vrf_name` | str | VRF name |
| `l3vsn[].config` | dict | L3VSN configuration (gathered state only) |
| `l3vsn[].before` | dict | L3VSN configuration before changes (non-gathered states) |
| `l3vsn[].after` | dict | L3VSN configuration after changes (non-gathered states) |
| `l3vsn[].changed` | bool | Whether this VRF's L3VSN was modified (non-gathered states) |
| `l3vsn[].differences` | dict | Fields that differ between before and after (non-gathered states) |
| `api_responses` | dict | Raw REST API responses for debugging |

### Output Fields (in before/after/config dicts)

| Field | Type | Description |
|-------|------|-------------|
| `vrf_name` | str | VRF name |
| `ipv4` | dict | IPv4 VPN instance settings (if exists) |
| `ipv4.isid` | int | I-SID number |
| `ipv4.vpn_enabled` | bool | Whether IP VPN is enabled |
| `ipv4.isid_name` | str | I-SID descriptive name |
| `ipv4.mvpn.enabled` | bool | Whether MVPN is enabled |
| `ipv4.mvpn.forward_cache_timeout` | int | MVPN forward cache timeout in seconds |
| `ipv6` | dict | IPv6 VPN instance settings (same fields as `ipv4`) |

---

## [Examples](#table-of-contents)

### Gathered — read all L3VSN configuration

```yaml
- name: Gather current L3VSN configuration
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: gathered
```

### Gathered — filter by VRF name

```yaml
- name: Gather L3VSN for specific VRFs
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: gathered
    gather_filter:
      - customer-a
      - GlobalRouter
```

### Merged — create IPv4 VPN instance

```yaml
- name: Create L3VSN for customer VRF
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: merged
    config:
      - vrf_name: customer-a
        ipv4:
          isid: 100
          vpn_enabled: true
          isid_name: cust-a-v4
```

### Merged — create dual-stack with MVPN

```yaml
- name: Create dual-stack L3VSN with MVPN
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: merged
    config:
      - vrf_name: customer-a
        ipv4:
          isid: 100
          vpn_enabled: true
          mvpn:
            enabled: true
            forward_cache_timeout: 300
        ipv6:
          isid: 200
          vpn_enabled: true
```

### Replaced — reset omitted patchable fields to defaults

```yaml
- name: Replace L3VSN settings
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: replaced
    config:
      - vrf_name: customer-a
        ipv4:
          isid: 100
          vpn_enabled: true
          # isid_name omitted → reset to "" (factory default)
```

### Overridden — enforce exact L3VSN set

```yaml
- name: Override all L3VSN instances
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: overridden
    config:
      - vrf_name: customer-a
        ipv4:
          isid: 100
          vpn_enabled: true
    # Any VPN instances not listed here will be deleted
```

### Deleted — remove specific VPN instance types

```yaml
- name: Delete IPv6 VPN instance for a VRF
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: deleted
    config:
      - vrf_name: customer-a
        ipv6: {}
```

### Deleted — remove all instances for a VRF

```yaml
- name: Delete all L3VSN for a VRF
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: deleted
    config:
      - vrf_name: customer-a
```

### Deleted — remove all L3VSN across all VRFs

```yaml
- name: Delete all L3VSN
  extreme.fe.extreme_fe_spbm_l3vsn:
    state: deleted
    # No config → deletes all VPN instances across all VRFs
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.


```yaml
- name: Manage SPBM L3VSN instances
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current L3VSN configuration
      extreme.fe.extreme_fe_spbm_l3vsn:
        state: gathered

    - name: Create L3VSN for customer VRF
      extreme.fe.extreme_fe_spbm_l3vsn:
        state: merged
        config:
          - vrf_name: customer-a
            ipv4:
              isid: 100
              vpn_enabled: true
              isid_name: cust-a-v4

    - name: Create dual-stack L3VSN with MVPN
      extreme.fe.extreme_fe_spbm_l3vsn:
        state: merged
        config:
          - vrf_name: customer-a
            ipv4:
              isid: 100
              vpn_enabled: true
              mvpn:
                enabled: true
                forward_cache_timeout: 300
            ipv6:
              isid: 200
              vpn_enabled: true

    - name: Replace L3VSN config for VRF
      extreme.fe.extreme_fe_spbm_l3vsn:
        state: replaced
        config:
          - vrf_name: customer-a
            ipv4:
              isid: 100
              vpn_enabled: true

    - name: Override all L3VSN instances
      extreme.fe.extreme_fe_spbm_l3vsn:
        state: overridden
        config:
          - vrf_name: customer-a
            ipv4:
              isid: 100
              vpn_enabled: true

    - name: Delete IPv6 VPN for a VRF
      extreme.fe.extreme_fe_spbm_l3vsn:
        state: deleted
        config:
          - vrf_name: customer-a
            ipv6: {}

    - name: Delete all L3VSN instances
      extreme.fe.extreme_fe_spbm_l3vsn:
        state: deleted
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
