# Save Configuration

## Module: extreme.fe.extreme_fe_save_config

Saves the running configuration on Fabric Engine devices.

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

Through this module the current Fabric Engine running configuration is saved to the active or specified configuration file via the REST API endpoint exposed through the OpenAPI Server.

- Supports optionally providing a filename and using Fabric Engine's verbose save option.

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
| POST | /v0/operation/system/config/:save | Save running configuration |

---

## [Parameters](#table-of-contents)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | str | No | - | Destination configuration filename. When omitted, saves to the active config file |
| `verbose` | bool | No | - | When true, save both current and default configuration state |

---

## [Return Values](#table-of-contents)

| Key | Type | Description |
|-----|------|-------------|
| `changed` | bool | Whether the save request was triggered |
| `response` | dict | Raw response payload returned by the device |

---

## [Examples](#table-of-contents)

### Save running configuration

```yaml
- name: Save running configuration
  extreme.fe.extreme_fe_save_config:
    verbose: false
```

### Save to a named backup file

```yaml
- name: Save running configuration as backup
  extreme.fe.extreme_fe_save_config:
    name: config-backup.cfg
    verbose: false
```

---

## [Complete Playbook](#table-of-contents)

Copy this playbook and fill in the inventory.

```yaml
- name: Save Fabric Engine configuration
  hosts: switches
  gather_facts: false
  collections:
    - extreme.fe
  tasks:

    - name: Save running configuration
      extreme.fe.extreme_fe_save_config:
        verbose: false

    - name: Save configuration to backup file
      extreme.fe.extreme_fe_save_config:
        name: config-backup.cfg
        verbose: true
```


---

## [Status](#table-of-contents)

This module is maintained by the Extreme Networks `Infrastructure as Code` team.

### Authors

- Bjorn Haas ([@bhaas_extr](https://github.com/bhaas_extr))
