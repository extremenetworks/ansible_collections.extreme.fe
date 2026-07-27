# Virtual Routing and Forwarding (VRF) - Static Routes

## Module: extreme.fe.extreme_fe_vrf_static_routes

Manages static routes on Fabric Engine devices.

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

This module manages VRF-scoped static routes on Fabric Engine devices via the REST API endpoints exposed through the OpenAPI Server.

- Uses nested data grouped by VRF, address family, prefix, and next-hop.
- A static route is identified by VRF + address family + prefix + prefix length + next-hop/interface key.
- The only post-creation updatable field is `enabled`.
- Other route fields are create-time fields and require delete plus re-create when changed.

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
| POST | /v0/configuration/vrf/{vr_name}/route | Create static route |
| GET | /v0/configuration/vrf/{vr_name}/route | List routes for one VRF |
| PATCH | /v0/configuration/vrf/{vr_name}/route/... | Update route (enabled only) |
| DELETE | /v0/configuration/vrf/{vr_name}/route/... | Delete route |
| GET | /v0/configuration/route | List routes across all VRFs |
| GET | /v0/state/route | Dynamic route table (optional gather output) |
| GET | /v0/state/route/summary | Route-count summary (optional gather output) |

---

## [Platform Constraints](#table-of-contents)

- VRF names: 1-16 characters on Fabric Engine devices.
- For IPv4 routes, interface_type and interface are read-only.
- For IPv6 routes, interface_type and interface are supported for link-local next-hops.
- admin_distance range on Fabric Engine devices: 1-255.
- weight range on Fabric Engine devices: 1-65535.
- blackhole and forward_router_address are mutually exclusive.
- default_route is read-only and inferred by prefix (0.0.0.0/0 or ::/0).
- Examples use lowercase VRF names (globalrouter, mgmtrouter) to match normalization behavior.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | merged | Operation state: merged, replaced, overridden, deleted, gathered |
| `config` | list of dict | Yes (except gathered, delete-all) | - | VRF-scoped static route config |
| `config[].vrf` | str | Yes | - | VRF name (1-16 chars) |
| `config[].address_families` | list of dict | No | - | Address family blocks |
| `config[].address_families[].afi` | str | Yes | - | ipv4 or ipv6 |
| `config[].address_families[].routes` | list of dict | No | - | Destination route list |
| `routes[].prefix` | str | Yes | - | Destination prefix address |
| `routes[].prefix_len` | int | Yes | - | Prefix length |
| `routes[].next_hops` | list of dict | No | - | Next-hop list |
| `next_hops[].forward_router_address` | str | No | - | Next-hop IP |
| `next_hops[].interface_type` | str | No | - | port, vlan, ip_tunnel, oob |
| `next_hops[].interface` | str | No | - | Local interface name or id |
| `next_hops[].admin_distance` | int | No | - | Admin distance (create-time) |
| `next_hops[].weight` | int | No | - | Route metric (create-time) |
| `next_hops[].name` | str | No | - | Route name (create-time) |
| `next_hops[].enabled` | bool | No | - | Route enabled flag (patchable) |
| `next_hops[].blackhole` | bool | No | - | Blackhole route flag |
| `gather_filter` | list of str | No | - | Gather output only for listed VRFs |
| `gather_dynamic` | bool | No | `false` | Include dynamic routes in gathered output |
| `gather_summary` | bool | No | `false` | Include per-VRF summary in gathered output |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| merged | Additive create/update. Existing unlisted routes are untouched. | GET, POST, PATCH |
| replaced | Authoritative for listed routes. Omitted create-time fields use defaults when applicable. | GET, DELETE, POST, PATCH |
| overridden | Reconcile globally: remove unlisted routes (except protected VRFs), then apply replaced semantics to listed routes. | GET, DELETE, POST, PATCH |
| deleted | Delete specific routes. If config is omitted, delete all routes across non-system VRFs. | GET, DELETE |
| gathered | Read-only route collection output. Optional dynamic and summary payloads. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether any route was modified |
| `before` | list of dict | Full route config before changes (action states) |
| `after` | list of dict | Full route config after changes (when changed) |
| `gathered` | list of dict | Gathered static route view (gathered state) |
| `dynamic_routes` | list | Optional dynamic route table output |
| `route_summary` | list | Optional route summary output |
| `api_responses` | dict | Raw REST API responses for troubleshooting |

### Route Output Fields

| Field | Type | Description |
|-------|------|-------------|
| vrf | str | VRF name |
| address_families | list of dict | Per-AFI route data |
| address_families[].afi | str | ipv4 or ipv6 |
| routes[].prefix | str | Destination prefix |
| routes[].prefix_len | int | Prefix length |
| routes[].next_hops | list of dict | Next-hop entries |
| next_hops[].forward_router_address | str | Next-hop IP |
| next_hops[].interface_type | str | Local interface type |
| next_hops[].interface | str | Local interface name/id |
| next_hops[].admin_distance | int | Administrative distance |
| next_hops[].weight | int | Route metric |
| next_hops[].name | str | Optional route name |
| next_hops[].enabled | bool | Route enabled state |
| next_hops[].blackhole | bool | Blackhole flag |
| next_hops[].default_route | bool | Read-only default-route indicator |
---

## [Examples](#table-of-contents)

### Gathered - read all static routes

```yaml
- name: Gather all static routes
  extreme.fe.extreme_fe_vrf_static_routes:
    state: gathered
```

### Gathered - filter VRFs and include dynamic/summary

```yaml
- name: Gather selected VRFs with dynamic and summary data
  extreme.fe.extreme_fe_vrf_static_routes:
    state: gathered
    gather_filter:
      - globalrouter
    gather_dynamic: true
    gather_summary: true
```

### Merged - create an IPv4 static route

```yaml
- name: Create IPv4 static route
  extreme.fe.extreme_fe_vrf_static_routes:
    state: merged
    config:
      - vrf: globalrouter
        address_families:
          - afi: ipv4
            routes:
              - prefix: 10.0.0.0
                prefix_len: 24
                next_hops:
                  - forward_router_address: 192.168.1.1
                    admin_distance: 10
                    weight: 1
                    enabled: true
```

### Replaced - reset route set for a prefix

```yaml
- name: Replace next-hop set for prefix
  extreme.fe.extreme_fe_vrf_static_routes:
    state: replaced
    config:
      - vrf: vrf101
        address_families:
          - afi: ipv4
            routes:
              - prefix: 10.0.0.0
                prefix_len: 24
                next_hops:
                  - forward_router_address: 192.168.2.1
                    admin_distance: 5
```

### Overridden - enforce exact route configuration

```yaml
- name: Override static route inventory
  extreme.fe.extreme_fe_vrf_static_routes:
    state: overridden
    config:
      - vrf: globalrouter
        address_families:
          - afi: ipv4
            routes:
              - prefix: 10.0.0.0
                prefix_len: 24
                next_hops:
                  - forward_router_address: 192.168.1.1
```

### Deleted - remove specific route

```yaml
- name: Delete route from VRF
  extreme.fe.extreme_fe_vrf_static_routes:
    state: deleted
    config:
      - vrf: vrf101
        address_families:
          - afi: ipv4
            routes:
              - prefix: 10.0.0.0
                prefix_len: 24
                next_hops:
                  - forward_router_address: 192.168.1.1
```

### Deleted - remove all routes on one VRF

```yaml
- name: Delete all routes on a VRF
  extreme.fe.extreme_fe_vrf_static_routes:
    state: deleted
    config:
      - vrf: vrf101
```

### Merged - IPv6 route with local interface

```yaml
- name: Create IPv6 route with local interface
  extreme.fe.extreme_fe_vrf_static_routes:
    state: merged
    config:
      - vrf: globalrouter
        address_families:
          - afi: ipv6
            routes:
              - prefix: 2001:db8::
                prefix_len: 32
                next_hops:
                  - forward_router_address: fe80::1
                    interface_type: vlan
                    interface: "100"
```

### Merged - blackhole route

```yaml
- name: Create blackhole route
  extreme.fe.extreme_fe_vrf_static_routes:
    state: merged
    config:
      - vrf: globalrouter
        address_families:
          - afi: ipv4
            routes:
              - prefix: 192.168.99.0
                prefix_len: 24
                next_hops:
                  - blackhole: true
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.


```yaml
- name: Manage VRF static routes
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather all static routes
      extreme.fe.extreme_fe_vrf_static_routes:
        state: gathered

    - name: Gather selected VRFs with dynamic and summary data
      extreme.fe.extreme_fe_vrf_static_routes:
        state: gathered
        gather_filter:
          - globalrouter
        gather_dynamic: true
        gather_summary: true

    - name: Create IPv4 static route
      extreme.fe.extreme_fe_vrf_static_routes:
        state: merged
        config:
          - vrf: globalrouter
            address_families:
              - afi: ipv4
                routes:
                  - prefix: 10.0.0.0
                    prefix_len: 24
                    next_hops:
                      - forward_router_address: 192.168.1.1
                        admin_distance: 10
                        weight: 1
                        enabled: true

    - name: Replace next-hop set for prefix
      extreme.fe.extreme_fe_vrf_static_routes:
        state: replaced
        config:
          - vrf: vrf101
            address_families:
              - afi: ipv4
                routes:
                  - prefix: 10.0.0.0
                    prefix_len: 24
                    next_hops:
                      - forward_router_address: 192.168.2.1
                        admin_distance: 5

    - name: Override static route inventory
      extreme.fe.extreme_fe_vrf_static_routes:
        state: overridden
        config:
          - vrf: globalrouter
            address_families:
              - afi: ipv4
                routes:
                  - prefix: 10.0.0.0
                    prefix_len: 24
                    next_hops:
                      - forward_router_address: 192.168.1.1

    - name: Create IPv6 route with local interface
      extreme.fe.extreme_fe_vrf_static_routes:
        state: merged
        config:
          - vrf: globalrouter
            address_families:
              - afi: ipv6
                routes:
                  - prefix: 2001:db8::
                    prefix_len: 32
                    next_hops:
                      - forward_router_address: fe80::1
                        interface_type: vlan
                        interface: "100"

    - name: Create blackhole route
      extreme.fe.extreme_fe_vrf_static_routes:
        state: merged
        config:
          - vrf: globalrouter
            address_families:
              - afi: ipv4
                routes:
                  - prefix: 192.168.99.0
                    prefix_len: 24
                    next_hops:
                      - blackhole: true

    - name: Delete all routes on a VRF
      extreme.fe.extreme_fe_vrf_static_routes:
        state: deleted
        config:
          - vrf: vrf101

    - name: Delete all routes on non-system VRFs
      extreme.fe.extreme_fe_vrf_static_routes:
        state: deleted
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
