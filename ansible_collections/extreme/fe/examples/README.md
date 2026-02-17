# Example Ansible Playbooks for Extreme Networks Fabric Engine

This folder contains **example playbooks** demonstrating how to use the `extreme.fe` Ansible collection to automate Extreme Networks Fabric Engine switches.

**NOTE:** These examples are intended for learning and testing purposes. Review and adapt them to your environment before production use.

## Requirements

*   **Ansible:** Tested with:
                - ansible [core 2.20.2]
*   **Python:** Tested with:
                - python version = 3.12.3
*   **Ansible Collections:**
    *   `extreme.fe` (Extreme Networks Fabric Engine collection)
*   **Extreme Networks Fabric Engine Switches:** With REST API enabled.
    *   See [Enable REST API on Switch](#enable-rest-api-on-switch) section below.
*   **Network Connectivity:** Your Ansible control node must have network connectivity to the managed switches.

## Features (Demonstrated in this Example)

*   **PoE Management:**
    *   Check PoE status on ports
    *   Power cycling (bounce) for WAP recovery
    *   Monitor power consumption

*   **VLAN Service Provisioning:**
    *   Create VLANs with auto-generated names
    *   Add ports to VLANs (preserves existing configuration)
    *   Create/replace ISID for SPB fabric connectivity
    *   Smart ISID replacement (auto-deletes old ISID if changing)
    *   Save configuration to named files

*   **VLAN Delete (vlan_delete):**
    *   Delete VLANs and auto-find/delete bound ISID

*   **Config Delete (config_delete):**
    *   Delete configuration files from switch

*   **Firmware Upgrade:**
    *   Check current firmware version
    *   Skip upgrade if already on target version
    *   Add and activate new firmware
    *   Automatic reboot and wait for switch
    *   Verify upgrade succeeded

## Enable REST API on Switch

Before using this Ansible collection, you must enable the REST API (OpenAPI) on your Extreme Networks Fabric Engine switch.

**⚠️ License Requirement:** The REST API (OpenAPI) feature requires an **EP1 (Extreme Platform ONE)** or **Premier** license on your Fabric Engine switch. Without the appropriate license, the `openapi local-mgmt enable` command will not be available.

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

2.  **Install the Extreme Fabric Engine Collection:**

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

Modify the `inventory.ini` file to include your Extreme Fabric Engine switches:

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

# Add your credentials in YAML format (in the editor that opens):
# ---
# ansible_user: "admin"
# ansible_password: "your_secure_password"

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

### provision_vlan_service.yml - VLAN + Port + ISID Configuration

This playbook creates or updates a complete VLAN service with port assignment and
SPB fabric ISID binding.

**What it does:**
1. Creates VLAN (or keeps existing) with name "VLAN-\<ID\>"
2. Adds port to VLAN (keeps existing ports)
3. Creates/replaces the ISID bound to the VLAN (auto-deletes old ISID if different)
4. Saves configuration

**Parameters:**

| Parameter     | Description                    | Default          | Example                  |
|---------------|--------------------------------|------------------|--------------------------|
| `vlan_id`     | VLAN ID to create/configure    | `5`              | `-e vlan_id=10`          |
| `vlan_port`   | Port to add to the VLAN        | `1:5`            | `-e vlan_port=1:8`       |
| `vlan_isid`   | I-SID number for SPB fabric    | same as vlan_id  | `-e vlan_isid=10010`     |
| `config_name` | Config file name to save       | `config.cfg`     | `-e config_name=my.cfg`  |

**Examples:**

```bash
# Basic usage with defaults (VLAN 5, port 1:5, ISID 5, config.cfg)
ansible-playbook -i inventory.ini provision_vlan_service.yml

# Create VLAN 10 with port 1:8
ansible-playbook -i inventory.ini provision_vlan_service.yml -e vlan_id=10 -e vlan_port=1:8

# Create VLAN 10 with custom ISID
ansible-playbook -i inventory.ini provision_vlan_service.yml -e vlan_id=10 -e vlan_port=1:8 -e vlan_isid=10010

# Change the ISID of VLAN 10
ansible-playbook -i inventory.ini provision_vlan_service.yml -e vlan_id=10 -e vlan_isid=10011

# All parameters
ansible-playbook -i inventory.ini provision_vlan_service.yml -e vlan_id=20 -e vlan_port=1:10 -e vlan_isid=20000 -e config_name=custom.cfg
```

**Expected Output:**

```
TASK [Create VLAN 10] ********************************************************
changed: [fe_sw_1]

TASK [Show VLAN result] ******************************************************
ok: [fe_sw_1] => {
    "msg": "VLAN 10 - Created/Updated"
}

TASK [Add port 1:8 to VLAN 10] ***********************************************
changed: [fe_sw_1]

TASK [Show port result] ******************************************************
ok: [fe_sw_1] => {
    "msg": "Port 1:8 -> VLAN 10 - Added/Updated"
}

TASK [Gather existing ISID] *************************************************
ok: [fe_sw_1]

TASK [Find ISID currently bound to VLAN 10] **********************************
ok: [fe_sw_1]

TASK [Delete existing ISID 10 if different from 10010] ***********************
changed: [fe_sw_1]

TASK [Show delete ISID result] ***********************************************
ok: [fe_sw_1] => {
    "msg": "Old ISID 10 deleted from VLAN 10"
}

TASK [Create ISID 10010 bound to VLAN 10] ************************************
changed: [fe_sw_1]

TASK [Show ISID result] ******************************************************
ok: [fe_sw_1] => {
    "msg": "ISID 10010 -> VLAN 10 - Created/Updated"
}

TASK [Save configuration to config.cfg] **************************************
changed: [fe_sw_1]

TASK [Summary] ***************************************************************
ok: [fe_sw_1] => {
    "msg": [
        "✓ VLAN 10 (VLAN-10)",
        "✓ Port 1:8 assigned to VLAN 10",
        "✓ ISID 10010 bound to VLAN 10",
        "✓ Config saved to config.cfg"
    ]
}
```

**Note:** If the VLAN already has a different ISID bound, the playbook will automatically
delete the old ISID before creating the new one.

### vlan_delete.yml - VLAN + ISID Delete

This playbook removes a VLAN and its bound ISID. It automatically finds and deletes
the ISID bound to the specified VLAN - you don't need to know what ISID was used.

**What it does:**
1. Validates vlan_id parameter (required)
2. Gathers VLAN info to find its configuration (VR, etc.)
3. Finds the ISID bound to the VLAN (if any)
4. Deletes the ISID bound to the VLAN (must be deleted before VLAN)
5. Deletes the VLAN using its actual VR name

**Parameters:**

| Parameter  | Description       | Required | Example          |
|------------|-------------------|----------|------------------|
| `vlan_id`  | VLAN ID to delete | Yes      | `-e vlan_id=50`  |

**Examples:**

```bash
# Delete VLAN 50 and its bound ISID
ansible-playbook -i inventory.ini vlan_delete.yml -e vlan_id=50

# Dry run (check mode) - see what would be deleted without making changes
ansible-playbook -i inventory.ini vlan_delete.yml -e vlan_id=50 --check
```

**Expected Output:**

```
TASK [Step 2 - Show delete target] *******************************************
ok: [fe_sw_1] => {
    "msg": [
        "=== VLAN DELETE ===",
        "Target VLAN: 50",
        "Will also delete any ISID bound to this VLAN"
    ]
}

TASK [Step 3 - Show VLAN info found] *****************************************
ok: [fe_sw_1] => {
    "msg": [
        "VLAN 50 found: YES",
        "VLAN Name: VLAN-50",
        "VLAN VR: GlobalRouter"
    ]
}

TASK [Step 4 - Show ISID found] **********************************************
ok: [fe_sw_1] => {
    "msg": [
        "ISID bound to VLAN 50: 5000"
    ]
}

TASK [Step 5 - Delete ISID 5000 (bound to VLAN 50)] **************************
changed: [fe_sw_1]

TASK [Step 5 - Show ISID deletion result] ************************************
ok: [fe_sw_1] => {
    "msg": [
        "ISID 5000 deletion: SUCCESS"
    ]
}

TASK [Step 6 - Delete VLAN 50 from VR GlobalRouter] **************************
changed: [fe_sw_1]

TASK [Step 6 - Show VLAN deletion result] ************************************
ok: [fe_sw_1] => {
    "msg": [
        "VLAN 50 deletion: SUCCESS"
    ]
}

TASK [Step 7 - Summary] ******************************************************
ok: [fe_sw_1] => {
    "msg": [
        "=== VLAN DELETE COMPLETE ===",
        "VLAN 50 (VR: GlobalRouter) deleted: ✓ YES",
        "ISID deleted: 5000"
    ]
}
```

**Note:** The playbook automatically finds and deletes the ISID bound to the specified VLAN,
you don't need to know what ISID was used. It also auto-detects the VR the VLAN belongs to.

### config_delete.yml - Config File Delete

This playbook removes a saved configuration file from the switch.

**What it does:**
1. Validates config_name parameter (required)
2. Deletes the specified configuration file

**Parameters:**

| Parameter     | Description              | Required | Example                      |
|---------------|--------------------------|----------|------------------------------|
| `config_name` | Config file name to delete | Yes      | `-e config_name=myconfig.cfg` |

**Examples:**

```bash
# Delete a specific config file
ansible-playbook -i inventory.ini config_delete.yml -e config_name=iot-config.cfg

# Dry run (check mode) - see what would be deleted without making changes
ansible-playbook -i inventory.ini config_delete.yml -e config_name=test.cfg --check
```

**Expected Output:**

```
TASK [Step 2 - Show delete target] *******************************************
ok: [fe_sw_1] => {
    "msg": [
        "=== CONFIG DELETE ===",
        "Target config file: iot-config.cfg"
    ]
}

TASK [Step 3 - Show config file deletion result] *****************************
ok: [fe_sw_1] => {
    "msg": [
        "Config file iot-config.cfg deletion: SUCCESS"
    ]
}

TASK [Delete Summary] ********************************************************
ok: [fe_sw_1] => {
    "msg": [
        "=== CONFIG DELETE COMPLETE ===",
        "Config iot-config.cfg deleted: ✓ YES"
    ]
}
```

### firmware_upgrade.yml - Firmware Upgrade

This playbook performs a complete firmware upgrade on Fabric Engine switches with version
verification.

**What it does:**
1. Validates parameters
2. Checks current firmware version
3. Skips upgrade if already on target version
4. Saves configuration (optional)
5. Verifies firmware file exists on switch
6. Adds software from firmware file
7. Activates the new software version
8. Reboots the switch
9. Waits for switch to come back online
10. Commits the software upgrade
11. Verifies the upgrade succeeded

**Parameters:**

| Parameter          | Description                             | Default    | Example                                  |
|--------------------|-----------------------------------------|------------|------------------------------------------|
| `software_file`    | Name of the firmware file on /intflash/ | (required) | `-e software_file=5420.9.3.2.0int003.voss` |
| `software_version` | Target firmware version string          | (required) | `-e software_version=9.3.2.0_B003`       |
| `save_config`      | Save config before upgrade              | `true`     | `-e save_config=false`                   |

**Examples:**

```bash
# Basic upgrade
ansible-playbook -i inventory.ini firmware_upgrade.yml \
  -e software_file=5420.9.3.2.0int003.voss \
  -e software_version=9.3.2.0_B003

# Skip saving config before upgrade
ansible-playbook -i inventory.ini firmware_upgrade.yml \
  -e software_file=5420.9.3.2.0int003.voss \
  -e software_version=9.3.2.0_B003 \
  -e save_config=false

# Dry run (check mode) - see what would happen without making changes
ansible-playbook -i inventory.ini firmware_upgrade.yml \
  -e software_file=5420.9.3.2.0int003.voss \
  -e software_version=9.3.2.0_B003 \
  --check
```

**Expected Output (upgrade needed):**

```
TASK [Show upgrade parameters] ***********************************************
ok: [fe_sw_1] => {
    "msg": "File: 5420.9.3.2.0int003.voss → version 9.3.2.0_B003"
}

TASK [Show current version] **************************************************
ok: [fe_sw_1] => {
    "msg": "Current: 9.3.2.0_B002 | Target: 9.3.2.0_B003 | Upgrade needed: True"
}

TASK [Save configuration] ****************************************************
changed: [fe_sw_1]

TASK [Add software 5420.9.3.2.0int003.voss] **********************************
changed: [fe_sw_1]

TASK [Activate software 5420.9.3.2.0int003] **********************************
changed: [fe_sw_1]

TASK [Reboot switch] *********************************************************
changed: [fe_sw_1]

TASK [Wait for switch to reboot] *********************************************
ok: [fe_sw_1]

TASK [Wait for services to start] ********************************************
Pausing for 30 seconds
ok: [fe_sw_1]

TASK [Commit software upgrade] ***********************************************
changed: [fe_sw_1]

TASK [Verify upgrade succeeded] **********************************************
ok: [fe_sw_1] => {
    "msg": "Upgrade verified: 9.3.2.0_B003"
}

TASK [Summary] ***************************************************************
ok: [fe_sw_1] => {
    "msg": "Upgraded 9.3.2.0_B002 → 9.3.2.0_B003"
}
```

**Expected Output (already on target version):**

```
TASK [Show current version] **************************************************
ok: [fe_sw_1] => {
    "msg": "Current: 9.3.2.0_B003 | Target: 9.3.2.0_B003 | Upgrade needed: False"
}

TASK [Summary (no upgrade needed)] *******************************************
ok: [fe_sw_1] => {
    "msg": "Already on target version: 9.3.2.0_B003"
}
```

**Note:** The firmware file must be uploaded to /intflash/ on the switch before running
this playbook. Use SCP, SFTP, or the switch's file transfer commands to upload the file.

**Check Mode:** When run with `--check`, the playbook validates parameters, checks the
current firmware version, and reports whether an upgrade would be needed. All system-modifying
tasks (file check, add, activate, reboot, commit, verify) are skipped.

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

*   [Extreme Networks Fabric Engine Documentation](https://www.extremenetworks.com/support/documentation)
*   [Ansible Documentation](https://docs.ansible.com/)
*   [Ansible Galaxy - extreme.fe Collection](https://galaxy.ansible.com/extreme/fe)

## Contributing

Contributions are welcome! Please submit issues or pull requests.

## License

See the LICENSE file in the parent directory.
