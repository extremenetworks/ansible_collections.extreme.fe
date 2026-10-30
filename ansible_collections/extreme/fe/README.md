# Extreme Networks Fabric Engine Collection

The Ansible Extreme Networks Fabric Engine collection includes a variety of Ansible content to help automate the management of Extreme Networks Fabric Engine network switches.

This collection has been tested against Fabric Engine 9.3.2.0.

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
| extreme.fe.extreme_fe_anycast_gateway | Manage Anycast Gateway interfaces on Fabric Engine switches |
| extreme.fe.extreme_fe_autosense     | Configure Auto-Sense settings on Fabric Engine switches |
| extreme.fe.extreme_fe_capabilities  | Read device capabilities on Fabric Engine switches |
| extreme.fe.extreme_fe_command       | Execute CLI commands on Fabric Engine switches |
| extreme.fe.extreme_fe_dns           | Manage DNS servers and domain on Fabric Engine switches |
| extreme.fe.extreme_fe_fabric_l2     | Manage Layer 2 Fabric ISIDs configuration |
| extreme.fe.extreme_fe_facts         | Collect facts from Fabric Engine switches |
| extreme.fe.extreme_fe_interfaces    | Configure physical interfaces on Fabric Engine switches |
| extreme.fe.extreme_fe_l2_interfaces | Configure Layer 2 interface settings |
| extreme.fe.extreme_fe_l3_interfaces | Configure Layer 3 interface addressing |
| extreme.fe.extreme_fe_lag           | Configure Link Aggregation Groups (MLT/LACP) |
| extreme.fe.extreme_fe_lldp_global   | Configure global LLDP timer settings |
| extreme.fe.extreme_fe_lldp_interfaces | Configure LLDP interface settings |
| extreme.fe.extreme_fe_local_users   | Manages local user accounts on Fabric Engine devices |
| extreme.fe.extreme_fe_mlag          | Configure Multi-chassis LAG (vIST/SMLT) |
| extreme.fe.extreme_fe_ntp_global    | Manages global NTP settings and servers on Fabric Engine switches |
| extreme.fe.extreme_fe_ping          | Execute ICMP ping tests from the switch |
| extreme.fe.extreme_fe_poe           | Configure Power over Ethernet settings |
| extreme.fe.extreme_fe_radius        | Manages global RADIUS settings, servers and secure-profiles on Fabric Engine switches |
| extreme.fe.extreme_fe_save_config   | Save running configuration to file |
| extreme.fe.extreme_fe_slpp          | Configure SLPP (Simple Loop Prevention Protocol) settings |
| extreme.fe.extreme_fe_snmp          | Manage SNMP system name on Fabric Engine switches |
| extreme.fe.extreme_fe_spbm_l3vsn    | Manage SPBM L3VSN (IPVPN) instances on Fabric Engine switches |
| extreme.fe.extreme_fe_ssh           | Manage the SSH service flags on Fabric Engine switches |
| extreme.fe.extreme_fe_stp           | Configure STP per-port settings and BPDU Guard |
| extreme.fe.extreme_fe_syslog        | Manage syslog configuration on Fabric Engine devices |
| extreme.fe.extreme_fe_vlans         | Configure VLANs on Fabric Engine switches |
| extreme.fe.extreme_fe_vrf           | Manage VRFs on Fabric Engine switches |
| extreme.fe.extreme_fe_vrf_static_routes | Manage static routes on Fabric Engine switches |
| extreme.fe.extreme_fe_web           | Manages global web-server settings on Fabric engine switches |

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

### Connecting by DNS hostname or FQDN

Inventories may list switches by DNS hostname or FQDN directly, with nothing else
per host:

```ini
[switches]
switch_1
switch_2
switch_3

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

Fabric Engine 9.3.2.0 and 9.4.0.0 abort the TLS handshake when the ClientHello
carries the SNI (Server Name Indication) extension, and a client sends SNI only
when it connects by name — RFC 6066 forbids sending it for an IP literal. The
collection therefore resolves each hostname to an IP address and connects to
that address, so the handshake carries no SNI extension. The standard
`ansible.netcommon.httpapi` connection plugin performs the requests unmodified.
The lookup runs before the first request and its result is then reused for the
host as long as the connection options behind it stay the same; changing
`ansible_httpapi_resolve_hostname`, `ansible_httpapi_validate_certs`,
`ansible_httpapi_ca_path`, the port or the proxy settings makes the next task
look the host up again, and closing or resetting the connection discards the
result altogether.

Hosts that are already IP addresses are not resolved, so IP-based inventories
reach the same device as before. The one change they can see is an unbracketed
IPv6 literal, which is rewritten to its bracketed form (`2001:db8::1` →
`[2001:db8::1]`) because a bare IPv6 address cannot sit in a URL authority; that
happens whatever `ansible_httpapi_resolve_hostname` is set to. Plain-HTTP
connections (`ansible_httpapi_use_ssl=false`) are left alone too: there is no
TLS handshake to keep SNI out of, and the name is what the `Host` header is
built from.

**With certificate validation enabled** (`ansible_httpapi_validate_certs=true`),
the connection is verified against the address it was made to, so each switch
certificate should carry the switch IP address as an `iPAddress` subjectAltName
entry. Certificate verification itself is unchanged and still performed by
Python's `ssl` module: both the chain of trust and the address are verified as
usual.

A switch pinned to its **own self-signed certificate** is detected and handled
automatically. When `ansible_httpapi_validate_certs=true` and
`ansible_httpapi_ca_path` points at a file holding **exactly one** self-signed
endpoint certificate — the setup `examples/README.md` documents, where the
switch's own certificate is its trust anchor — that certificate is inspected
before connecting:

| Self-signed endpoint certificate at `ca_path` | Connection |
|-----------------------------------------------|------------|
| Names the host, and its `iPAddress` SAN covers the address it resolves to | Made to the resolved address |
| Names the host, with no `iPAddress` SAN | Made by name, unchanged |
| Names the host, but its `iPAddress` SAN covers some other address | Made by name, unchanged |
| Names some other host, or cannot be read | Made to the resolved address |
| Does not identify itself as a server certificate | Made to the resolved address |

Nothing is inferred from anything else at `ca_path`. A file holding more than one
certificate is a trust store by construction — a name matching one entry says
nothing about which certificate the peer serves — so those hosts resolve to an
address like any other, **including a CA-signed switch certificate that carries
only `dNSName` entries**. A self-signed
certificate counts as the endpoint's own only when it says so: its
`extendedKeyUsage` names `serverAuth`, or, where that extension is absent,
`basicConstraints` marks it as not a CA. A root CA may legally omit both, so a
certificate carrying neither is read as a trust anchor rather than guessed at.
Point `ca_path` at the single switch certificate, or set
`ansible_httpapi_resolve_hostname=false`, to keep such a host reached by name.

So the certificate-based setup documented in `examples/README.md` — a
self-signed switch certificate whose CN is the hostname, with that name in the
inventory — keeps working exactly as before, with no inventory change. That path
connects by name, which means it still requires the switch to accept SNI.

`ansible_httpapi_resolve_hostname=false` forces connecting by name in every
case. Note that a switch running an affected release then aborts the handshake,
since connecting by name is what sends the SNI extension.

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

### Example: Flex-UNI services (SUNI and TUNI)

Flex-UNI must be enabled on a port or LAG **before** it can be bound to a Switched UNI
endpoint — the device rejects the endpoint otherwise. Transparent UNI members must
have it left disabled; a port cannot serve both roles.

```yaml
---
- name: Provision Flex-UNI services
  hosts: switches
  gather_facts: false
  tasks:
    - name: Enable Flex-UNI on the SUNI ports
      extreme.fe.extreme_fe_interfaces:
        state: merged
        ports:
          - name: "1:10"
            flex_uni: true
          - name: "1:11"
            flex_uni: true

    - name: Enable Flex-UNI on the SUNI LAG
      extreme.fe.extreme_fe_lag:
        state: merged
        lag_id: 50
        flex_uni: true

    - name: Create a Switched UNI with a tagged and an untagged endpoint
      extreme.fe.extreme_fe_fabric_l2:
        state: merged
        config:
          - isid: 8001
            isid_type: SUNI
            name: "Campus-FlexUNI"
            endpoints:
              - cvid: 1010
                ports:
                  - "1:10"
                lags:
                  - "50"
              # c-vid 4096 is the untagged endpoint — the only one on which
              # the device accepts BPDU forwarding.
              - cvid: 4096
                ports:
                  - "1:11"
                bpdu_enabled: true

    - name: Create a Transparent UNI (members must NOT have Flex-UNI)
      extreme.fe.extreme_fe_fabric_l2:
        state: merged
        config:
          - isid: 8003
            isid_type: TUNI
            name: "Transparent-Uplink"
            ports:
              - "1:13"
              - "1:14"
            lags:
              - "51"
```

In `merged` state an omitted attribute is left untouched, so the task below adds a LAG
without disturbing the existing port membership. Supply an explicit empty list to clear
a membership, or use `replaced` to enforce an exact state:

```yaml
    - name: Add a LAG to an existing endpoint, leaving its ports alone
      extreme.fe.extreme_fe_fabric_l2:
        state: merged
        config:
          - isid: 8001
            isid_type: SUNI
            endpoints:
              - cvid: 1010
                lags:
                  - "50"
                  - "51"
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

Release notes are available in the [CHANGELOG.md](CHANGELOG.md).

## More information

- [Ansible network resources](https://docs.ansible.com/ansible/latest/network/getting_started/network_resources.html)
- [Ansible Collection overview](https://github.com/ansible-collections/overview)
- [Ansible User guide](https://docs.ansible.com/ansible/latest/user_guide/index.html)
- [Ansible Developer guide](https://docs.ansible.com/ansible/latest/dev_guide/index.html)
- [Extreme Networks](https://www.extremenetworks.com/)