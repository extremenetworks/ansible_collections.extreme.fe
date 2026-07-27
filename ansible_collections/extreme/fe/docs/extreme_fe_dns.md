# Domain Name System (DNS)

## Module: extreme.fe.extreme_fe_dns

Manages Domain Name System settings on Fabric Engine devices.

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

This module manages the DNS servers and domain suffix configuration on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server.

- Supports the Ansible states: merged, replaced, overridden, deleted and gathered.
- Dynamic DNS entries learned from DHCP are read-only and excluded from management.
- Fabric Engine devices use `GlobalRouter` for DNS server entries.
- `replaced` reconciles server set via POST/DELETE.
- `overridden` enforces full DNS config via PUT.

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
| GET | /v0/configuration/dns | Retrieve DNS settings |
| PUT | /v0/configuration/dns | Replace entire DNS configuration |
| POST | /v0/configuration/dns/server | Add DNS server |
| DELETE | /v0/configuration/dns/server/{address_type}/{address}/{vr_name} | Delete DNS server |
| POST | /v0/configuration/dns/domain | Add DNS domain |
| DELETE | /v0/configuration/dns/domain/{domain_name} | Delete DNS domain |

---

## [Platform Constraints](#table-of-contents)

- Maximum 3 user-configurable DNS servers.
- Single DNS domain suffix supported.
- Dynamic DNS servers can exist but are read-only.
- `vrName` must be `GlobalRouter`.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `merged` | Operation state |
| `config` | dict | Yes (merged/replaced/overridden) | - | DNS config object |
| `config.domain` | str | No | - | Domain suffix |
| `config.servers` | list of dict | No | - | DNS servers |
| `config.servers[].address` | str | Yes | - | Server IP address |
| `config.servers[].address_type` | str | No | `IPv4` | `IPv4` or `IPv6` |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `merged` | Add missing servers/domain, keep unspecified values. | GET, POST |
| `replaced` | Desired server list becomes final state; remove unlisted servers. | GET, POST, DELETE |
| `overridden` | Replace complete DNS config using PUT. | GET, PUT |
| `deleted` | Remove listed servers/domain, or all if `config` omitted. | GET, DELETE |
| `gathered` | Read-only output. | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether DNS config changed |
| `dns.before` | dict | DNS config before changes |
| `dns.after` | dict | DNS config after changes |
| `dns.config` | dict | Gathered DNS configuration |
| `dns.differences` | dict | Diff between before and after |
| `submitted` | dict | Submitted payload when changes were needed |
| `api_responses` | dict | Raw REST API responses |

---

## [Examples](#table-of-contents)

### Add DNS servers

```yaml
- name: Add primary and secondary DNS servers
  extreme.fe.extreme_fe_dns:
    state: merged
    config:
      domain: example.com
      servers:
        - address: 8.8.8.8
          address_type: IPv4
        - address: 8.8.4.4
          address_type: IPv4
```

### Replace DNS configuration

```yaml
- name: Enforce desired DNS configuration
  extreme.fe.extreme_fe_dns:
    state: replaced
    config:
      domain: corp.example.com
      servers:
        - address: 10.0.0.1
          address_type: IPv4
        - address: 10.0.0.2
          address_type: IPv4
        - address: 2001:db8::1
          address_type: IPv6
```

### Delete DNS entries

```yaml
- name: Remove specific DNS server and domain
  extreme.fe.extreme_fe_dns:
    state: deleted
    config:
      domain: example.com
      servers:
        - address: 8.8.4.4
          address_type: IPv4

- name: Remove all DNS configuration
  extreme.fe.extreme_fe_dns:
    state: deleted
```

### Gather DNS configuration

```yaml
- name: Collect current DNS configuration
  extreme.fe.extreme_fe_dns:
    state: gathered
  register: dns_info
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.


```yaml
- name: Manage DNS configuration
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Gather current DNS configuration
      extreme.fe.extreme_fe_dns:
        state: gathered
      register: dns_before

    - name: Add primary and secondary DNS servers
      extreme.fe.extreme_fe_dns:
        state: merged
        config:
          domain: example.com
          servers:
            - address: 8.8.8.8
              address_type: IPv4
            - address: 8.8.4.4
              address_type: IPv4

    - name: Enforce desired DNS configuration
      extreme.fe.extreme_fe_dns:
        state: replaced
        config:
          domain: corp.example.com
          servers:
            - address: 10.0.0.1
              address_type: IPv4
            - address: 10.0.0.2
              address_type: IPv4

    - name: Override entire DNS configuration
      extreme.fe.extreme_fe_dns:
        state: overridden
        config:
          domain: lab.example.com
          servers:
            - address: 1.1.1.1
              address_type: IPv4

    - name: Remove all DNS configuration
      extreme.fe.extreme_fe_dns:
        state: deleted

    - name: Gather DNS configuration after changes
      extreme.fe.extreme_fe_dns:
        state: gathered
      register: dns_after
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
