# Example Ansible Playbooks for Extreme Networks FabricEngine

This folder contains **example playbooks** demonstrating how to use the `extreme.fe` Ansible collection to automate Extreme Networks FabricEngine switches.

**NOTE:** These examples are intended for learning and testing purposes. Review and adapt them to your environment before production use.

## Features (Demonstrated in this Example)

*   **PoE Management:**
    *   Check PoE status on ports
    *   Power cycling (bounce) for WAP recovery
    *   Monitor power consumption

## Requirements

*   **Ansible:** Tested with:
                - ansible [core 2.17.14]
                - ansible [core 2.20.2]
*   **Python:** Tested with:
                - python version = 3.12.3
*   **Ansible Collections:**
    *   `extreme.fe` (Extreme Networks FabricEngine collection)
*   **Extreme Networks FabricEngine Switches:** With REST API enabled.
    *   See [Enable REST API on Switch](#enable-rest-api-on-switch) section below.
*   **Network Connectivity:** Your Ansible control node must have network connectivity to the managed switches.

## Enable REST API on Switch

Before using this Ansible collection, you must enable the REST API (OpenAPI) on your Extreme Networks FabricEngine switch.

**⚠️ License Requirement:** The REST API (OpenAPI) feature requires an **EP1 (Endpoint Protection 1)** or **Premier** license on your FabricEngine switch. Without the appropriate license, the `openapi local-mgmt enable` command will not be available.

### Enable via CLI

Connect to your switch via console or SSH and run the following commands:

```
enable
configure terminal
application
openapi local-mgmt enable
exit
```

### Verify REST API is Enabled

```
show application openapi
```

Expected output should show the OpenAPI local management is enabled.

### Test REST API Access

From your Ansible control node, test connectivity to the REST API:

```bash
# Replace YOUR_SWITCH_IP with your switch's IP address
curl -k https://YOUR_SWITCH_IP:9443/rest/openapi
```

If the REST API is working, you should receive a JSON response.

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

| Variable               | Description                  | Example |
|------------------------|------------------------------|---------|
| `ansible_host`         | IP address of your switch    | `192.168.1.100` |
| `ansible_httpapi_port` | REST API port (default 9443) | `9443` |
| `ansible_user`         | Username for authentication  | `admin` |
| `ansible_password`     | Password for authentication  | `your_password` |

### 3. Security Recommendations

For production use, **do not store passwords in plain text**. Use Ansible Vault:

```bash
# Create encrypted password file
ansible-vault create secrets.yml

# Add your credentials (in the editor that opens)
ansible_user: admin
ansible_password: your_secure_password

# Run playbook with vault and load variables from secrets.yml
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e @secrets.yml --ask-vault-pass
```

**Alternative:** Place `secrets.yml` in `group_vars/switches/` directory and it will be loaded automatically:

```bash
mkdir -p group_vars/switches
ansible-vault create group_vars/switches/vault.yml
# Then run normally - Ansible loads group_vars automatically
ansible-playbook -i inventory.ini wap_poe_bounce.yml --ask-vault-pass
```

### 4. SSL Certificate Verification (Optional but Recommended)

By default, SSL certificate verification is disabled (`ansible_httpapi_validate_certs=false`) for ease of use with self-signed certificates. For better security, you can enable certificate verification.

#### Why enable certificate verification?

- Ensures you're connecting to the real switch (not a man-in-the-middle)
- Required in production environments for security compliance

#### Step-by-step setup:

**Step 1: Create a folder for certificates**

```bash
cd examples
mkdir -p certs
```

**Step 2: Download the certificate from your switch**

Replace `YOUR_SWITCH_IP` with your switch's IP address:

```bash
openssl s_client -connect YOUR_SWITCH_IP:9443 -showcerts </dev/null 2>/dev/null | openssl x509 -outform PEM > certs/fe_switch_cert.pem
```

Example with IP 192.168.1.100:
```bash
openssl s_client -connect 192.168.1.100:9443 -showcerts </dev/null 2>/dev/null | openssl x509 -outform PEM > certs/fe_switch_cert.pem
```

**Step 3: Check what hostname is in the certificate**

```bash
openssl x509 -in certs/fe_switch_cert.pem -noout -subject
```

This will show something like:
```
subject=C = XX, ST = StateName, L = CityName, O = CompanyName, CN = CommonNameOrHostname
```

The important part is `CN = CommonNameOrHostname` - this is the hostname the certificate was created for.

**Step 4: Add the hostname to your computer's hosts file**

Since the certificate uses a hostname (not IP), we need to map that hostname to the switch's IP:

```bash
# Add entry to /etc/hosts (requires sudo/admin)
echo "YOUR_SWITCH_IP CERTIFICATE_HOSTNAME" | sudo tee -a /etc/hosts
```

Example:
```bash
echo "192.168.1.100 CommonNameOrHostname" | sudo tee -a /etc/hosts
```

**Step 5: Update the inventory file**

Edit `inventory.ini` to:
1. Use the hostname instead of IP address
2. Enable certificate verification
3. Point to the certificate file

```ini
[switches]
fe_sw_1 ansible_host=CommonNameOrHostname

[switches:vars]
ansible_connection=httpapi
ansible_network_os=extreme.fe.extreme_fe
ansible_httpapi_use_ssl=true
ansible_httpapi_validate_certs=true
ansible_httpapi_ca_path=certs/fe_switch_cert.pem
ansible_httpapi_port=9443
ansible_httpapi_base_path=/rest/openapi
ansible_user=ADMIN_USER
ansible_password=PASSWORD
```

**Step 6: Test the connection**

```bash
ansible-playbook -i inventory.ini wap_poe_bounce.yml -e wap_port=1:5
```

#### Troubleshooting SSL issues

Case 1:
    Error: `certificate verify failed: self-signed certificate`
    Solution: Make sure `ansible_httpapi_ca_path` points to the correct certificate file
Case 2:
    Error: `certificate verify failed: IP address mismatch`
    Solution: Use the hostname from the certificate's CN field instead of IP address
Case 3:
    Error: `unable to get local issuer certificate`
    Solution: The certificate chain is incomplete - use `validate_certs=false` or get the full chain

#### Quick option: Disable verification (for testing only)

If you're just testing and don't need certificate verification:

```ini
ansible_httpapi_validate_certs=false
# ansible_httpapi_ca_path=certs/fe_switch_cert.pem  # Not needed when validation is disabled
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

# Run without specifying wap_port (uses default port 1:10)
ansible-playbook -i inventory.ini wap_poe_bounce.yml
```

### Parameters

| Parameter        | Description                     | Default | Example                |
|------------------|---------------------------------|---------|------------------------|
| `wap_port`       | Port to power cycle             | `1:10`  | `-e wap_port=1:5`      |
| `power_off_wait` | Seconds to wait after power OFF | `5`     | `-e power_off_wait=10` |
| `power_on_wait`  | Seconds for device to boot      | `30`    | `-e power_on_wait=60`  |

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

| Problem                   | Solution |
|---------------------------|----------|
| **Connection refused**    | Verify switch IP address and REST API is enabled |
| **Authentication failed** | Check username/password in inventory |
| **Module not found**      | Run `ansible-galaxy collection install extreme.fe` |
| **Port not found**        | Verify port format (e.g., `1:5` not `5`) |
| **SSL certificate error** | Set `ansible_httpapi_validate_certs=false` or configure proper certificates |

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
