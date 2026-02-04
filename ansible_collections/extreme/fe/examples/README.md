# Extreme Fabric Engine (FE) Ansible Collection Examples

This directory contains example playbooks organized by use case, as well as comprehensive coverage tests for individual modules.

## Directory Structure

### Use Cases (`use_cases/`)
These playbooks demonstrate real-world workflows and best practices for managing Extreme Fabric Engine switches.

- **Initial Provisioning** (`initial_provisioning/`):
  - Setup MLAG, LAGs, and physical port configurations.
  - Manage autosense settings.

- **Fabric Service Provisioning** (`fabric_service_provisioning/`):
  - End-to-end service creation (VLANs + ISIDs + Ports).
  - L3 Interface IP addressing.

- **PoE Management** (`poe_management/`):
  - Manage Power over Ethernet settings.
  - "PoE Bounce" workflows for restarting attached devices (e.g., WAPs, Cameras).

- **Network Monitoring & Troubleshooting** (`network_monitoring_and_troubleshooting/`):
  - Fact gathering (hardware, interfaces, neighbors).
  - Connectivity tests (Ping).
  - Configuration management (Backup/Save).

### Module Coverage (`module_coverage/`)
These playbooks provide exhaustive test coverage for individual Ansible modules included in this collection. They are useful for understanding all available parameters for a specific module.
