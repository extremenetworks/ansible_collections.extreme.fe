# Extreme Networks Fabric Engine Collection - Documentation

This directory contains documentation for the `extreme.fe` Ansible collection.

## Modules

| Module | Description |
|--------|-------------|
| `extreme_fe_autosense` | Manage auto-sense settings and port behavior |
| `extreme_fe_command` | Execute CLI commands on Fabric Engine switches |
| `extreme_fe_fabric_l2` | Manage Layer 2 fabric settings |
| `extreme_fe_facts` | Gather facts from Fabric Engine switches |
| `extreme_fe_interfaces` | Manage physical interfaces |
| `extreme_fe_l2_interfaces` | Manage Layer 2 interface settings |
| `extreme_fe_l3_interfaces` | Manage Layer 3 interface settings |
| `extreme_fe_lag` | Manage Link Aggregation Groups |
| `extreme_fe_mlag` | Manage Multi-chassis LAG settings |
| `extreme_fe_ping` | Execute ping commands |
| `extreme_fe_poe` | Manage Power over Ethernet settings |
| `extreme_fe_save_config` | Save running configuration |
| `extreme_fe_vlans` | Manage VLAN configuration |

## Connection Requirements

All modules require the `ansible.netcommon.httpapi` connection type with the `extreme.fe.extreme_fe` network OS.

```yaml
ansible_connection: ansible.netcommon.httpapi
ansible_network_os: extreme.fe.extreme_fe
ansible_httpapi_use_ssl: true
ansible_httpapi_validate_certs: false
```

## Example Inventory

```ini
[extreme_switches]
switch1 ansible_host=10.0.0.1

[extreme_switches:vars]
ansible_user=admin
ansible_password=password
ansible_connection=ansible.netcommon.httpapi
ansible_network_os=extreme.fe.extreme_fe
ansible_httpapi_use_ssl=true
ansible_httpapi_validate_certs=false
ansible_httpapi_port=8080
```
