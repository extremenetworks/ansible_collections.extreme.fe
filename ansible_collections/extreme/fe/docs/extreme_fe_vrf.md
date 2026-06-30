# Virtual Routing and Forwarding (VRF)

## Module: extreme.fe.extreme_fe_vrf

Manage Virtual Routing and Forwarding configuration and retrieval on Fabric Engine devices.

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

This module manages VRF instances on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Each VRF is identified by its `name` (1-16 characters).
- The only writable configuration field (via PATCH) is `ip_routing_enabled`.

---

## [Notes](#table-of-contents)

- System VRFs (`GlobalRouter`, `MgmtRouter`) always exist and cannot be deleted.
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
| GET | `/v0/configuration/vrf` | List all VRFs on the device |
| POST | `/v0/configuration/vrf` | Create a new VRF |
| GET | `/v0/configuration/vrf/{vr_name}` | Get a single VRF by name |
| PATCH | `/v0/configuration/vrf/{vr_name}` | Update VRF settings (VOSS only) |
| DELETE | `/v0/configuration/vrf/{vr_name}` | Delete a VRF by name |

---

## [Platform Constraints](#table-of-contents)

- VRF name: string, 1–16 characters (OpenAPI spec says 32, but firmware enforces 16)
- Only `VRF` type is supported on VOSS (`VR` type is EXOS-only)
- `GlobalRouter` and `MgmtRouter` are system VRFs that cannot be deleted
- The only writable field via PATCH is `ipRoutingEnabled`
- Port associations are managed through brouter interfaces, not directly via VRF API
- Dynamic VRFs (created by protocols) are excluded from `overridden`/`deleted` delete-all operations

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state: `merged`, `replaced`, `overridden`, `deleted`, `gathered` |
| `config` | list of dict | Yes (for merged/replaced/overridden) | — | List of VRF configurations to manage |
| `config[].name` | str | Yes | — | VRF name (1-16 characters, resource identifier) |
| `config[].ip_routing_enabled` | bool | No | - | Enable/disable IP routing on this VRF |
| `gather_filter` | list of str | No | — | Limit gathered results to these VRF names |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Create VRFs that don't exist; update `ip_routing_enabled` on existing VRFs if specified. Unlisted VRFs untouched. | POST, PATCH |
| `replaced` | Create or update listed VRFs with complete payload (omitted fields reset to defaults). Unlisted VRFs untouched. | POST, PATCH |
| `overridden` | Delete unlisted user VRFs, then apply `replaced` logic to listed VRFs. | DELETE, POST, PATCH |
| `deleted` | Delete specified VRFs. If `config` omitted, delete all user-created VRFs. | DELETE |
| `gathered` | Read-only — return current VRF state. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any VRF was modified |
| `vrfs` | list of dict | Per-VRF operation results |
| `vrfs[].name` | str | VRF name |
| `vrfs[].config` | dict | VRF configuration (gathered state only) |
| `vrfs[].before` | dict | VRF configuration before changes (non-gathered states) |
| `vrfs[].after` | dict | VRF configuration after changes (non-gathered states) |
| `vrfs[].changed` | bool | Whether this specific VRF was modified (non-gathered states) |
| `vrfs[].differences` | dict | Fields that differ between before and after (non-gathered states) |
| `api_responses` | dict | Raw REST API responses for debugging |

### Output Fields (in before/after/config dicts)

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | VRF name |
| `ip_routing_enabled` | bool | Whether IP routing is enabled |
| `id` | int | VRF numeric identifier (read-only) |
| `is_mgmt` | bool | Whether this is the management VRF (read-only) |
| `dynamic` | bool | Whether dynamically created (read-only) |
| `vr_type` | str | Virtual router type: VR or VRF (read-only) |
| `port_list` | list | Ports associated with the VRF (read-only) |
| `dynamic_port_list` | list | Dynamically associated ports (read-only) |
| `vlan_id_list` | list of int | VLAN IDs on the VRF (read-only) |

---

## [Examples](#table-of-contents)

### Gathered — read all VRFs

```yaml
- name: Gather current VRF configuration
  extreme.fe.extreme_fe_vrf:
    state: gathered
```

### Gathered — filter by name

```yaml
- name: Gather specific VRFs
  extreme.fe.extreme_fe_vrf:
    state: gathered
    gather_filter:
      - customer-a
      - customer-b
```

### Merged — create VRF with routing enabled

```yaml
- name: Create VRF with IP routing
  extreme.fe.extreme_fe_vrf:
    state: merged
    config:
      - name: customer-a
        ip_routing_enabled: true
```

### Merged — create multiple VRFs

```yaml
- name: Create multiple VRFs
  extreme.fe.extreme_fe_vrf:
    state: merged
    config:
      - name: customer-a
        ip_routing_enabled: true
      - name: customer-b
        ip_routing_enabled: false
```

### Replaced — reset omitted fields to defaults

```yaml
- name: Replace VRF settings
  extreme.fe.extreme_fe_vrf:
    state: replaced
    config:
      - name: customer-a
        # ip_routing_enabled omitted → reset to true (factory default)
```

### Overridden — enforce exact VRF set

```yaml
- name: Override all VRFs
  extreme.fe.extreme_fe_vrf:
    state: overridden
    config:
      - name: customer-a
        ip_routing_enabled: true
      - name: customer-b
        ip_routing_enabled: false
    # Any other user-created VRFs will be deleted
```

### Deleted — remove specific VRFs

```yaml
- name: Delete specific VRFs
  extreme.fe.extreme_fe_vrf:
    state: deleted
    config:
      - name: customer-a
      - name: customer-b
```

### Deleted — remove all user-created VRFs

```yaml
- name: Delete all user VRFs
  extreme.fe.extreme_fe_vrf:
    state: deleted
    # No config → deletes all user-created VRFs
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.


```yaml
- name: Manage VRF instances
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather all VRFs
      extreme.fe.extreme_fe_vrf:
        state: gathered

    - name: Gather specific VRFs
      extreme.fe.extreme_fe_vrf:
        state: gathered
        gather_filter:
          - customer-a
          - customer-b

    - name: Create VRF with IP routing
      extreme.fe.extreme_fe_vrf:
        state: merged
        config:
          - name: customer-a
            ip_routing_enabled: true

    - name: Create multiple VRFs
      extreme.fe.extreme_fe_vrf:
        state: merged
        config:
          - name: customer-a
            ip_routing_enabled: true
          - name: customer-b
            ip_routing_enabled: false

    - name: Replace VRF settings
      extreme.fe.extreme_fe_vrf:
        state: replaced
        config:
          - name: customer-a

    - name: Override all VRFs
      extreme.fe.extreme_fe_vrf:
        state: overridden
        config:
          - name: customer-a
            ip_routing_enabled: true
          - name: customer-b
            ip_routing_enabled: false

    - name: Delete specific VRFs
      extreme.fe.extreme_fe_vrf:
        state: deleted
        config:
          - name: customer-a
          - name: customer-b

    - name: Delete all user-created VRFs
      extreme.fe.extreme_fe_vrf:
        state: deleted
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
