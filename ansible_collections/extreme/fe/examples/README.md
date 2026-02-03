# Example Ansible Playbooks for Extreme Networks FabricEngine

This folder contains **example playbooks** demonstrating how to use the `extreme.fe` Ansible collection to automate Extreme Networks FabricEngine switches.

**NOTE:** These examples are intended for learning and testing purposes. Review and adapt them to your environment before production use.

## Features (Demonstrated in this Example)

*   **PoE Management:**
    *   Check PoE status on ports
    *   Power cycling (bounce) for WAP recovery
    *   Monitor power consumption

## Requirements

*   **Ansible:** Version 2.9 or later (tested with 2.14+). Newer versions are recommended.
*   **Python:** Version 3.8 or later.
*   **Ansible Collections:**
    *   `extreme.fe` (Extreme Networks FabricEngine collection)
*   **Extreme Networks FabricEngine Switches:** With REST API enabled.
*   **Network Connectivity:** Your Ansible control node must have network connectivity to the managed switches.

## Installation

1.  **Install Ansible:**

    ```bash
    pip install ansible
    ```

2.  **Install the Extreme FabricEngine Collection:**

    ```bash
    ansible-galaxy collection install extreme.fe
    ```

    Or install from a local tarball:

    ```bash
    ansible-galaxy collection install extreme-fe-1.0.0.tar.gz
    ```

3.  **Verify Installation:**

    ```bash
    ansible-galaxy collection list | grep extreme.fe
    ```

## Configuration

### 1. Inventory File (`inventory.ini`)

Modify the `inventory.ini` file to include your Extreme FabricEngine switches:

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

### 2. Connection Variables

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

| Variable | Description | Example |
|----------|-------------|---------|
| `ansible_host` | IP address of your switch | `192.168.1.100` |
| `ansible_httpapi_port` | REST API port (default 9443) | `9443` |
| `ansible_user` | Username for authentication | `admin` |
| `ansible_password` | Password for authentication | `your_password` |

### 3. Security Recommendations

For production use, **do not store passwords in plain text**. Use Ansible Vault:

```bash
# Create encrypted password file
ansible-vault create secrets.yml

# Add your credentials
ansible_user: admin
ansible_password: your_secure_password

# Run playbook with vault
ansible-playbook -i inventory.ini wap_poe_bounce.yml --ask-vault-pass
```

## Available Playbooks

### wap_poe_bounce.yml - PoE Power Cycling for WAP Recovery

This playbook power-cycles a PoE port to recover a Wireless Access Point (WAP).

**What it does:**
1. Shows initial PoE status
2. Turns OFF power to the port
3. Waits (configurable)
4. Shows OFF status confirmation
5. Turns ON power to the port
6. Waits for device to boot
7. Shows final status
8. Displays summary

## Usage

### Basic Usage

```bash
# Run with port parameter (recommended)
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:5

# Run interactively (will prompt for port)
ansible-playbook -i inventory.ini wap_poe_bounce.yml
```

### Parameters

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `wap_port` | Port to power cycle | `1:10` | `-e wap_port=1:5` |
| `power_off_wait` | Seconds to wait after power OFF | `5` | `-e power_off_wait=10` |
| `power_on_wait` | Seconds for device to boot | `30` | `-e power_on_wait=60` |

### Examples

```bash
# Bounce port 1:5 with default timing
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:5

# Bounce port 1:10 with custom timing
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:10 -e power_off_wait=10 -e power_on_wait=60

# Dry run (check mode) - see what would happen without making changes
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:7 --check

# Verbose output for troubleshooting
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:7 -vvv
```

### Expected Output

```
TASK [Step 1 - Show INITIAL status] ******************************************
ok: [fe_sw_1] => {
    "msg": [
        "Port 1:5 - PoE Enabled: True",
        "Status: delivering",
        "Power: 5000 mW"
    ]
}

TASK [Step 2 - Turn OFF PoE power on port 1:5] *******************************
changed: [fe_sw_1]

TASK [Step 3 - Show OFF status] **********************************************
ok: [fe_sw_1] => {
    "msg": [
        "Port 1:5 - PoE Enabled: False",
        "Status: disabled",
        "Power: 0 mW"
    ]
}

...

TASK [Step 6 - PoE bounce complete!] *****************************************
ok: [fe_sw_1] => {
    "msg": [
        "✓ PoE bounce completed on port 1:5",
        "✓ Power was OFF for 5 seconds",
        "✓ WAP had 30 seconds to restart",
        "✓ Current PoE status: ENABLED"
    ]
}
```

## Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| **Connection refused** | Verify switch IP address and REST API is enabled |
| **Authentication failed** | Check username/password in inventory |
| **SSL certificate error** | Set `ansible_httpapi_validate_certs=false` or configure proper certificates |
| **Module not found** | Run `ansible-galaxy collection install extreme.fe` |
| **Port not found** | Verify port format (e.g., `1:5` not `5`) |

### Enable Verbose Output

```bash
# More detail
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:5 -v

# Even more detail
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:5 -vvv
```

### Verify Collection Installation

```bash
ansible-galaxy collection list | grep extreme
```

### Test Connectivity

```bash
# Test if switch is reachable
ping 192.168.1.100

# Test REST API port
curl -k https://192.168.1.100:9443/rest/openapi
```

## Quick Start Summary

1. **Edit inventory.ini** - Change `ansible_host=SWITCH_IP_ADDRESS` to your switch IP
2. **Update credentials** - Change `ansible_user` and `ansible_password` if needed
3. **Run playbook** - `ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:5`

## Additional Resources

*   [Extreme Networks FabricEngine Documentation](https://www.extremenetworks.com/support/documentation)
*   [Ansible Documentation](https://docs.ansible.com/)
*   [Ansible Galaxy - extreme.fe Collection](https://galaxy.ansible.com/extreme/fe)

## Contributing

Contributions are welcome! Please submit issues or pull requests.

## License

See the LICENSE file in the parent directory.
