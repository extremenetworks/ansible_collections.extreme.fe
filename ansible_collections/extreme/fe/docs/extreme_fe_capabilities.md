# Capabilities Management

## Module: extreme.fe.extreme_fe_capabilities

Reads device capabilities on Fabric Engine devices.

---

Version added: 1.3.0

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

This module reads device-capability information on Fabric Engine devices using the REST API endpoints exposed through the OpenAPI Server, under the `Capabilities Management` tag.

- Supports only the Ansible state `gathered`. Every endpoint under this tag is GET-only - there is no PATCH, PUT, POST or DELETE - so the module never writes to the device.
- `gather_filter` selects which capability dataset(s) to retrieve: `all`, `system`, `urls`, `ports` or `openapi`. Multiple values can be combined in one task.
- `all` calls the combined endpoint, which returns `system`, `urls` and `openapi` together in a single response.
- `port` narrows the `ports` dataset down to one named port instead of every port on the device.

---

## [Notes](#table-of-contents)

- Tested against Fabric Engine Version 9.3.2.
- **Read-only:** the module never changes the switch, so `changed` is always `false`.
- **Single port:** `port` works only together with `ports` in `gather_filter`; without it the task fails. With `port`, `gathered.ports` holds that one port's data as a single object instead of a list.
- Supports check mode (`--check`); it makes no difference, since nothing is ever written.

---

## [Requirements](#table-of-contents)

- `extreme.fe` collection installed on the Ansible control node (includes `ansible.netcommon` dependency and the `extreme_fe` HTTPAPI connection plugin).
- Inventory configured with `ansible_connection: httpapi` and `ansible_network_os: extreme.fe.extreme_fe`.
- `OpenAPI Server` service enabled on the devices being managed.

---

## [REST API Endpoints](#table-of-contents)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v0/state/capabilities | Get all capabilities of the device |
| GET | /v0/state/capabilities/system | Get platform capabilities of the device |
| GET | /v0/state/capabilities/urls | Get all supported urls of the device |
| GET | /v0/state/capabilities/system/ports | Get all ports and their capability |
| GET | /v0/state/capabilities/system/ports/{port} | Get all capabilities on a specific port |
| GET | /v0/state/capabilities/openapi | Get OpenAPI capabilities of the device |

---

## [Platform Constraints](#table-of-contents)

- Every endpoint under `Capabilities Management` is read-only. No write method exists, so no Ansible state other than `gathered` is supported.
- Some fields in the returned capability data are platform- or NOS-specific (for example RADIUS vendor IDs and L2 MTU values are Fabric Engine (VOSS) specific; `stacking`, `ethernet`, `defaultSpeed`, `defaultDuplex` and `defaultAutoNegotiationEnabled` on port capabilities are Switch Engine (EXOS) specific). The module returns the device's response as-is and does not filter these out.

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `state` | str | No | `gathered` | Only `gathered` is supported - every underlying REST endpoint is read-only |
| `gather_filter` | list of str | No | `[all]` | Capability dataset(s) to retrieve: `all`, `system`, `urls`, `ports`, `openapi` |
| `port` | str | No | - | Name of a single port (for example `1:1:1`) to retrieve capabilities for. Requires `ports` in `gather_filter` |

---

## [State Behaviour Summary](#table-of-contents)

| State | Behaviour | HTTP Methods |
|-------|-----------|-------------|
| `gathered` | Read-only output of the selected capability dataset(s). | GET |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Always `false` - this module never writes to the device |
| `gathered` | dict | Capability data keyed by the `gather_filter` entry that produced it |
| `gathered.all` | dict | Combined capabilities (`urls`, `system`, `openapi`) - present when `all` is requested |
| `gathered.system` | dict | Platform capabilities - present when `system` is requested |
| `gathered.urls` | list | Every supported URL with its allowed operations and attributes - present when `urls` is requested |
| `gathered.ports` | list or dict | Every port's capabilities (list), or one port's capabilities (dict) when `port` is supplied - present when `ports` is requested |
| `gathered.openapi` | dict | OpenAPI server request-concurrency limits - present when `openapi` is requested |
| `capabilities.config` | dict | Same content as the top-level `gathered` key |

---

## [Examples](#table-of-contents)

### Gather all device capabilities

```yaml
- name: Collect all device capabilities
  extreme.fe.extreme_fe_capabilities:
  register: all_capabilities
```

### Gather only platform capabilities

```yaml
- name: Collect platform capabilities
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - system
  register: system_capabilities
```

### Gather the list of supported URLs

```yaml
- name: Collect all supported URLs
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - urls
  register: url_capabilities
```

### Gather capabilities for every port

```yaml
- name: Collect capabilities for every port
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - ports
  register: all_port_capabilities
```

### Gather capabilities for a single port

```yaml
- name: Collect capabilities for port 1:1:1
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - ports
    port: "1:1:1"
  register: single_port_capabilities
```

### Gather multiple datasets in one task

```yaml
- name: Collect system and OpenAPI capabilities together
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - system
      - openapi
  register: combined_capabilities
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Read device capabilities
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Collect all device capabilities
      extreme.fe.extreme_fe_capabilities:
      register: all_capabilities

    - name: Collect platform capabilities
      extreme.fe.extreme_fe_capabilities:
        gather_filter:
          - system
      register: system_capabilities

    - name: Collect all supported URLs
      extreme.fe.extreme_fe_capabilities:
        gather_filter:
          - urls
      register: url_capabilities

    - name: Collect capabilities for every port
      extreme.fe.extreme_fe_capabilities:
        gather_filter:
          - ports
      register: all_port_capabilities

    - name: Collect capabilities for port 1:1:1
      extreme.fe.extreme_fe_capabilities:
        gather_filter:
          - ports
        port: "1:1:1"
      register: single_port_capabilities

    - name: Collect system and OpenAPI capabilities together
      extreme.fe.extreme_fe_capabilities:
        gather_filter:
          - system
          - openapi
      register: combined_capabilities
```

---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Andreea-Lavinia Vraja ([@avraja_extr](https://github.com/avraja_extr))
