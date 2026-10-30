# Layer 3 Interfaces

## Module: extreme.fe.extreme_fe_l3_interfaces

Manages Layer 3 interfaces on Fabric Engine devices.

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
- [Return Values](#return-values)
- [Examples](#examples)
- [Complete Playbook](#complete-playbook)
- [Status](#status)

---

## [Description](#table-of-contents)

This module manages IPv4 and IPv6 addresses on VLAN and loopback interfaces of Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports declarative merge, replace, override, delete, and gather operations.
- Every action state (`merged`, `replaced`, `overridden`, `deleted`) is a read-modify-write: the module reads the current addresses, computes the final address list and sends a `PUT` only for interfaces whose list differs, so these states are idempotent. `gathered` is read-only and never sends a `PUT`.
- `state: gathered` returns the interfaces under `gathered` in the form `config` accepts, so the result can be supplied back as `config` unchanged. With `overridden` only an unfiltered result is safe: `overridden` clears every interface the list leaves out.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- Each interface may be listed once in `config`; one listed twice fails before any request.
- An address PUT that fails without an answer (a lost connection) may have been applied, so the task reports `changed=true` with `details.outcome=unknown`.
- Requires the `ansible.netcommon` collection and the `extreme_fe` HTTPAPI plugin shipped with this project.
- VLANs and loopbacks must exist prior to invoking this module; creation is out of scope.
- A VLAN named in `config` that does not exist fails the task with `merged`, `replaced`, `overridden` and `gathered`. With `state=deleted` there is nothing to delete, so such a VLAN is skipped without a request, does not count as a change and is left out of `before`, `after` and `interfaces`.
- The REST API does not list a loopback that has no IP address, so a loopback named in `config` that the device does not list is treated as having none. Deleting its addresses is then a no-op.
- `state=gathered` returns all VLANs including system-protected ones (dynamic, management, BROUTER). When `state=overridden`, those VLANs are skipped with a warning instead of being cleared. Other states pass requests to the device as-is and let the REST API reject invalid operations.
- `config` is required for `merged`, `replaced` and `overridden`.
- `state=deleted` without `config` removes the addresses of every interface the device lists, as `overridden` with an empty list would. System-protected VLANs (dynamic, management, BROUTER) are skipped with a warning.
- An address moved from one interface to another in one task is removed from its old interface first, so the device does not reject it as a duplicate.
- A task that fails after one of its writes succeeded reports `changed=true`, and the failure message names the interfaces already written.
- Supports check mode (`--check`) to simulate changes without making them; `after` is then the predicted state.
- Supports diff mode (`--diff`) to display the `before` and `after` interface states.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/configuration/vlan | Retrieve all VLANs with their addresses |
| GET | /v0/configuration/vlan/{vlan_id} | Retrieve one VLAN with its addresses (404 when it does not exist) |
| PUT | /v0/configuration/vlan/{vlan_id}/address | Replace the VLAN address list |
| GET | /v0/configuration/loopback | Retrieve the loopbacks that have at least one IP address |
| PUT | /v0/configuration/loopback/{id} | Replace the loopback address list (an empty body `{}` deletes it) |

---

## [Platform Constraints](#table-of-contents)

- A loopback interface holds a single IPv4 address on Fabric Engine; a second one is rejected with `Multinetting is not supported`, and IPv6 on a loopback with `IPv6 is not currently supported`.
- A loopback only exists in the REST model while it has an IP address, so an empty loopback is not listed by `GET /v0/configuration/loopback`.
- Auto-assigned IPv6 link-local addresses (`fe80::/10`) cannot be configured; they are left out of every comparison and result. IPv6 addresses are returned in compressed form.
- Dynamic, management and BROUTER VLANs cannot be modified through the REST API.
- Fabric Engine does not allow the IP address of the virtual IST (vIST) VLAN to change while the vIST exists, but answers the address PUT with 204 and keeps the address. The module reads the vIST VLANs (`vistVlanId`) from `GET /v0/configuration/mlag/peers` before the first write, when a VLAN address is about to change. `overridden` and `deleted` without `config` skip an unlisted vIST VLAN with a warning, like the other protected VLANs. A task that asks for a change on the vIST VLAN explicitly (`merged`, `replaced`, `deleted`, or the VLAN listed in `overridden`) fails before any write, also in check mode. An MLAG peers read that fails (other than HTTP 404 or an empty answer) fails the task before any write.
- After a write, the re-read is compared with the previous addresses. An interface that still holds exactly its previous addresses was not changed by the device: the task fails naming it, and that write does not count as a change.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | list of dict | No | - | Layer 3 interface definitions. Required for `merged`, `replaced` and `overridden`; `deleted` without it removes the addresses of every interface. The `gathered` result can be supplied back unchanged |
| `config[].name` | str | No | - | Interface identifier (e.g. `VLAN 20`, `Loopback 10`); used to infer the type and id when `type` is omitted |
| `config[].type` | str | No | - | Interface type, `vlan` or `loopback` (not case-sensitive); inferred from `vlan_id`, `loopback_id` or `name` when omitted |
| `config[].vlan_id` | int | No | - | VLAN identifier for routed VLAN interfaces |
| `config[].loopback_id` | int | No | - | Loopback identifier |
| `config[].vrf` | str | No | - | VRF name (documentation only) |
| `config[].ipv4` | list of raw | No | - | IPv4 addresses (CIDR strings or dicts) |
| `config[].ipv6` | list of raw | No | - | IPv6 addresses (CIDR strings or dicts) |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Add/update addresses incrementally. | GET, PUT |
| `replaced` | Make supplied addresses authoritative for listed interfaces. | GET, PUT |
| `overridden` | Enforce supplied addresses globally; clear unlisted interfaces. | GET, PUT |
| `deleted` | Remove the listed addresses (all addresses when none are listed) from listed interfaces. A VLAN that does not exist is skipped. Without `config`, remove the addresses of every interface (protected VLANs are skipped). | GET, PUT |
| `gathered` | Read-only - return current L3 interface configuration. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any changes were made |
| `gathered` | list | `state: gathered` only. One entry per interface in the form `config` accepts, so it can be supplied back as `config` unchanged; re-applying it with `merged` or `replaced` changes nothing. With `overridden` it is safe only for an unfiltered result (gathered without `config`): a filtered result lists only the selected interfaces, and `overridden` clears the addresses of every other unprotected interface. IPv6 link-local addresses are left out, and without `config` so are loopbacks that have no IP address |
| `interfaces` | list | Final L3 interface configuration, the same entries as `after` (for `state: gathered` the same entries as `gathered`, the key to use for that state) |
| `before` | list | Configuration of every targeted interface before the module ran, in the same form as `gathered`. Returned for every action state, whether or not anything changed. Under `deleted`, VLANs that do not exist are left out |
| `after` | list | Configuration of the same interfaces after the module ran, read back after a change and predicted in check mode. Returned for every action state, whether or not anything changed |
| `differences` | list | Per-interface change details |

### Output Fields

Entries of `gathered`, `interfaces`, `before` and `after`:

| Field | Type | Description |
|-------|------|-------------|
| `type` | str | `vlan` or `loopback` |
| `vlan_id` | int | VLAN identifier, for a VLAN interface |
| `loopback_id` | int | Loopback identifier, for a loopback interface |
| `name` | str | Name given in `config`, otherwise the name the device reports, when there is one |
| `vrf` | str | VRF the device reports for the interface, when there is one |
| `ipv4` | list of str | IPv4 addresses in CIDR notation |
| `ipv6` | list of str | IPv6 addresses in CIDR notation |

---

## [Examples](#table-of-contents)

### Add IPv4 address to a VLAN

```yaml
- name: Ensure VLAN 20 has 10.0.1.101/24
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - vlan_id: 20
        ipv4:
          - 10.0.1.101/24
    state: merged
```

### Replace addresses on a VLAN

```yaml
- name: Replace address list on VLAN 200
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - vlan_id: 200
        ipv4:
          - 10.10.200.1/24
        ipv6:
          - 2001:db8:200::1/64
    state: replaced
```

### Delete addresses from a loopback

```yaml
- name: Clear loopback IPs
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - loopback_id: 5
    state: deleted
```

### Gather L3 interfaces

```yaml
- name: Collect routed interface addressing
  extreme.fe.extreme_fe_l3_interfaces:
    state: gathered
    config:
      - vlan_id: 20
      - vlan_id: 200
  register: routed_interfaces
```

### Restore gathered L3 interfaces

The `gathered` result has the form `config` accepts, so it can be applied back unchanged. Use `merged` or `replaced`; use `overridden` only with an unfiltered gather (no `config`), as `overridden` clears every interface the list leaves out.

```yaml
- name: Re-apply the gathered addressing
  extreme.fe.extreme_fe_l3_interfaces:
    config: "{{ routed_interfaces.gathered }}"
    state: replaced
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Manage L3 interfaces on Fabric Engine
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current L3 interface configuration
      extreme.fe.extreme_fe_l3_interfaces:
        state: gathered
      register: l3_before

    - name: Add IPv4 address to VLAN 20
      extreme.fe.extreme_fe_l3_interfaces:
        config:
          - vlan_id: 20
            ipv4:
              - 10.0.1.101/24
        state: merged

    - name: Replace addresses on VLAN 200
      extreme.fe.extreme_fe_l3_interfaces:
        config:
          - vlan_id: 200
            ipv4:
              - 10.10.200.1/24
            ipv6:
              - 2001:db8:200::1/64
        state: replaced

    - name: Clear loopback addresses
      extreme.fe.extreme_fe_l3_interfaces:
        config:
          - loopback_id: 5
        state: deleted

    - name: Restore the addressing gathered at the start
      extreme.fe.extreme_fe_l3_interfaces:
        config: "{{ l3_before.gathered }}"
        state: replaced
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
