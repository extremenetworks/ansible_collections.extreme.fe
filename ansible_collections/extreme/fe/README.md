# Extreme Networks Fabric Engine Collection

The Ansible Extreme Networks Fabric Engine collection includes a variety of Ansible content to help automate the management of Extreme Networks Fabric Engine (VOSS) network switches.

This collection has been tested against Fabric Engine VOSS 9.3.2.0.

## Ansible version compatibility

This collection has been tested against the following Ansible version:

| Ansible Version        | Status |
|------------------------|--------|
| ansible [core 2.20.2]  | Tested |

### Python version compatibility

| Python Version | Status |
|----------------|--------|
| 3.12.3         | Tested |

Plugins and modules within a collection may be tested with only specific Ansible versions. A collection may contain metadata that identifies these versions.

### Supported connections

The Extreme Fabric Engine collection supports `httpapi` connections. The custom `extreme_fe` HTTPAPI plugin communicates with Fabric Engine switches via REST API.

| Connection Type | Description                      |
|-----------------|----------------------------------|
| httpapi         | REST API communication via HTTPS |

## Included content

### HTTPAPI plugins

| Name                  | Description |
|-----------------------|-------------|
| extreme.fe.extreme_fe | Use extreme_fe httpapi to run REST API commands on Extreme Fabric Engine switches |

### Modules

| Name                                | Description                  |
|-------------------------------------|------------------------------|
| extreme.fe.extreme_fe_anycast_gateway | Manages Anycast Gateway interfaces on Fabric Engine devices |
| extreme.fe.extreme_fe_autosense     | Manages Fabric Engine autosense settings and port behaviour |
| extreme.fe.extreme_fe_command       | Executes CLI commands on Fabric Engine devices |
| extreme.fe.extreme_fe_dns           | Manages DNS settings on Fabric Engine devices |
| extreme.fe.extreme_fe_fabric_l2     | Manages Layer 2 Fabric (ISID/C-VLAN) on Fabric Engine devices |
| extreme.fe.extreme_fe_facts         | Gathers hardware and system facts from Fabric Engine devices |
| extreme.fe.extreme_fe_interfaces    | Manages Ethernet interfaces on Fabric Engine devices |
| extreme.fe.extreme_fe_l2_interfaces | Manages Layer 2 interface on Fabric Engine devices |
| extreme.fe.extreme_fe_l3_interfaces | Manages Layer 3 interfaces on Fabric Engine devices |
| extreme.fe.extreme_fe_lag           | Manages Link Aggregation Groups (MLT/LACP) configuration |
| extreme.fe.extreme_fe_lldp_global   | Manages global LLDP settings on Fabric Engine devices |
| extreme.fe.extreme_fe_lldp_interfaces | Manages LLDP interface settings on Fabric Engine devices |
| extreme.fe.extreme_fe_mlag          | Manages Multi-chassis LAG (vIST/SMLT) configuration |
| extreme.fe.extreme_fe_ping          | Sends a ping from a Fabric Engine device to the given host |
| extreme.fe.extreme_fe_poe           | Manages Power over Ethernet settings |
| extreme.fe.extreme_fe_save_config   | Saves the running configuration on Fabric Engine devices |
| extreme.fe.extreme_fe_slpp          | Manages SLPP (Simple Loop Prevention Protocol) settings |
| extreme.fe.extreme_fe_snmp          | Manages the SNMP system name on Fabric Engine devices |
| extreme.fe.extreme_fe_spbm_l3vsn    | Manages SPBM L3VSN (IPVPN) instances on Fabric Engine devices |
| extreme.fe.extreme_fe_stp           | Manages STP per-port settings and BPDU Guard|
| extreme.fe.extreme_fe_vlans         | Manages VLANs on Fabric Engine devices |
| extreme.fe.extreme_fe_vrf           | Manages VRFs on Fabric Engine devices |
| extreme.fe.extreme_fe_vrf_static_routes | Manages static routes on Fabric Engine devices |

Click the `Content` button to see the list of content included in this collection.

## Installing this collection

You can install the Extreme Fabric Engine collection with the Ansible Galaxy CLI:

```bash
ansible-galaxy collection install extreme.fe
```

You can also include it in a `requirements.yml` file and install it with `ansible-galaxy collection install -r requirements.yml`, using the format:

```yaml
---
collections:
  - name: extreme.fe
```

## Using this collection

This collection includes [network resource modules](https://docs.ansible.com/ansible/latest/network/user_guide/network_resource_modules.html).

### Requirements

- **Extreme Networks Fabric Engine Switches:** With REST API enabled.
- **Network Connectivity:** Your Ansible control node must have network connectivity to the managed switches.

### Enable REST API on Switch

Before using this Ansible collection, you must enable the REST API (OpenAPI) on your Extreme Networks Fabric Engine switch.

**⚠️ License Requirement:** The REST API (OpenAPI) feature requires an **EP1 (Extreme Platform ONE)** or **Premier** license on your Fabric Engine switch. Without the appropriate license, the `openapi local-mgmt enable` command will not be available.

#### Enable via CLI

Connect to your switch via console or SSH and run the following commands:

```
enable
configure terminal
application
openapi local-mgmt enable
exit
```

#### Verify REST API is Enabled

```
show application openapi
```

Expected output should show the OpenAPI local management is enabled.

### Inventory Configuration

Configure your inventory file with the required connection parameters:

```ini
[switches]
fe_sw_1 ansible_host=SWITCH_IP_ADDRESS
```

**Change `SWITCH_IP_ADDRESS` to the IP address of YOUR switch.**

You can add multiple switches:

```ini
[switches]
fe_sw_1 ansible_host=192.168.1.100
fe_sw_2 ansible_host=192.168.1.101
fe_sw_3 ansible_host=192.168.1.102
```

### Connection Variables

The inventory file includes connection settings for the REST API:

```ini
[switches:vars]
ansible_connection=httpapi
ansible_network_os=extreme.fe.extreme_fe
ansible_httpapi_use_ssl=true
ansible_httpapi_validate_certs=false
ansible_httpapi_port=9443
ansible_httpapi_base_path=/rest/openapi
ansible_user=ADMIN_USER
ansible_password=PASSWORD
```

**Important settings to modify:**

| Variable               | Description                  | Example |
|------------------------|------------------------------|---------|
| `ansible_host`         | IP address of your switch    | `192.168.1.100` |
| `ansible_httpapi_port` | REST API port (default 9443) | `9443` |
| `ansible_user`         | Username for authentication  | `admin` |
| `ansible_password`     | Password for authentication  | `your_password` |

### Security Recommendations

For production use, **do not store passwords in plain text**. Use Ansible Vault:

```bash
# Create encrypted password file
ansible-vault create secrets.yml

# Add your credentials in YAML format (in the editor that opens):
# ---
# ansible_user: "admin"
# ansible_password: "your_secure_password"

# Run playbook with vault and load variables from secrets.yml
ansible-playbook -i inventory.ini playbook.yml -e @secrets.yml --ask-vault-pass
```

**Alternative:** Place `secrets.yml` in `group_vars/switches/` directory and it will be loaded automatically:

```bash
mkdir -p group_vars/switches
ansible-vault create group_vars/switches/vault.yml
# Then run normally - Ansible loads group_vars automatically
ansible-playbook -i inventory.ini playbook.yml --ask-vault-pass
```

### Using modules from the Extreme Fabric Engine collection in your playbooks

You can call modules by their Fully Qualified Collection Namespace (FQCN), such as `extreme.fe.extreme_fe_vlans`. The following example task creates a VLAN on a Fabric Engine switch:

```yaml
---
- name: Configure VLANs on Fabric Engine switch
  hosts: switches
  gather_facts: false
  tasks:
    - name: Create VLAN 100
      extreme.fe.extreme_fe_vlans:
        vlan_id: 100
        name: "Data-VLAN"
        state: merged
```

### Example: Collecting facts

```yaml
---
- name: Gather facts from Fabric Engine switches
  hosts: switches
  gather_facts: false
  tasks:
    - name: Collect system facts
      extreme.fe.extreme_fe_facts:
        gather_subset:
          - system
          - interfaces
      register: facts

    - name: Display hostname
      ansible.builtin.debug:
        var: facts.ansible_facts.ansible_net_hostname
```

### Example: Execute CLI commands

```yaml
---
- name: Run CLI commands on Fabric Engine switch
  hosts: switches
  gather_facts: false
  tasks:
    - name: Show VLAN configuration
      extreme.fe.extreme_fe_command:
        commands:
          - show vlan basic
      register: result

    - name: Display output
      ansible.builtin.debug:
        var: result.output
```

### See Also:

- [Ansible Using collections](https://docs.ansible.com/ansible/latest/user_guide/collections_using.html) for more details.
- [Ansible Network Resource Modules](https://docs.ansible.com/ansible/latest/network/user_guide/network_resource_modules.html)

## Support

For support, please contact [Extreme Networks Support](https://www.extremenetworks.com/support).

### Code of Conduct

This collection follows the Ansible project's [Code of Conduct](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html). Please read and familiarize yourself with this document.

## Release notes

Release notes are available in the CHANGELOG.rst.
## More information

- [Ansible network resources](https://docs.ansible.com/ansible/latest/network/getting_started/network_resources.html)
- [Ansible Collection overview](https://github.com/ansible-collections/overview)
- [Ansible User guide](https://docs.ansible.com/ansible/latest/user_guide/index.html)
- [Ansible Developer guide](https://docs.ansible.com/ansible/latest/dev_guide/index.html)
- [Extreme Networks](https://www.extremenetworks.com/)
