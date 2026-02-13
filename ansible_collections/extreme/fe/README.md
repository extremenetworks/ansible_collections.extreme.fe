# Extreme Networks Fabric Engine Collection

The Ansible Extreme Networks Fabric Engine collection includes a variety of Ansible content to help automate the management of Extreme Networks Fabric Engine (VOSS) network switches.

This collection has been tested against Fabric Engine VOSS 9.3.2.0.

## Communication

- Join the [Ansible Forum Network Working Group](https://forum.ansible.com/g/network-wg)
- For issues, open a ticket on [GitHub Issues](https://github.com/extremenetworks/ansible_collections.extreme.fe/issues)

## Ansible version compatibility

This collection has been tested against the following Ansible versions:

| Ansible Version        | Status |
|------------------------|--------|
| ansible [core 2.17.14] | Tested |
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
| extreme.fe.extreme_fe_autosense     | Configure Auto-Sense settings on Fabric Engine switches |
| extreme.fe.extreme_fe_command       | Execute CLI commands on Fabric Engine switches |
| extreme.fe.extreme_fe_fabric_l2     | Manage Layer 2 Fabric (ISID/C-VLAN) configuration |
| extreme.fe.extreme_fe_facts         | Collect facts from Fabric Engine switches |
| extreme.fe.extreme_fe_interfaces    | Configure physical interfaces on Fabric Engine switches |
| extreme.fe.extreme_fe_l2_interfaces | Configure Layer 2 interface settings |
| extreme.fe.extreme_fe_l3_interfaces | Configure Layer 3 interface addressing |
| extreme.fe.extreme_fe_lag           | Configure Link Aggregation Groups (MLT/LACP) |
| extreme.fe.extreme_fe_mlag          | Configure Multi-chassis LAG (vIST/SMLT) |
| extreme.fe.extreme_fe_ping          | Execute ICMP ping tests from the switch |
| extreme.fe.extreme_fe_poe           | Configure Power over Ethernet settings |
| extreme.fe.extreme_fe_save_config   | Save running configuration to file |
| extreme.fe.extreme_fe_vlans         | Configure VLANs on Fabric Engine switches |

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

## Contributing to this collection

We welcome community contributions to this collection. If you find problems, please open an issue or create a PR against the [Extreme Fabric Engine collection repository](https://github.com/extremenetworks/ansible_collections.extreme.fe).

See [Contributing to Ansible-maintained collections](https://docs.ansible.com/ansible/devel/community/contributing_maintained_collections.html#contributing-maintained-collections) for complete details.

## Support

For support, please contact [Extreme Networks Support](https://www.extremenetworks.com/support) or open an issue on the [GitHub repository](https://github.com/extremenetworks/ansible_collections.extreme.fe/issues).

### Code of Conduct

This collection follows the Ansible project's [Code of Conduct](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html). Please read and familiarize yourself with this document.

## Release notes

Release notes are available in the [CHANGELOG.rst](https://github.com/extremenetworks/ansible_collections.extreme.fe/blob/main/CHANGELOG.rst).

## Roadmap

<!-- Add information about planned features and improvements here -->

## More information

- [Ansible network resources](https://docs.ansible.com/ansible/latest/network/getting_started/network_resources.html)
- [Ansible Collection overview](https://github.com/ansible-collections/overview)
- [Ansible User guide](https://docs.ansible.com/ansible/latest/user_guide/index.html)
- [Ansible Developer guide](https://docs.ansible.com/ansible/latest/dev_guide/index.html)
- [Extreme Networks](https://www.extremenetworks.com/)

## Licensing

GNU General Public License v3.0 or later.

See [LICENSE](https://www.gnu.org/licenses/gpl-3.0.txt) to see the full text.
