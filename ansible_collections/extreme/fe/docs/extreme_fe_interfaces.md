# extreme_fe_interfaces

```yaml

---
module: extreme_fe_interfaces
short_description: Manage Ethernet interfaces on ExtremeNetworks Fabric Engine switches
version_added: "1.1.0"
description:
    - Configure administrative state, global interface settings, and per-port attributes on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI plugin.
    - Supports enabling or disabling multiple ports, adjusting Fabric Engine global port flags, and tuning per-port features such as speed, duplex, Energy Efficient Ethernet, and Fabric Engine specific options.
    - Provides standard Ansible network resource states including ``merged``, ``replaced``, ``overridden``, ``deleted``, and ``gathered``. The ``gathered`` state reads interface status from the high-version ``/v1/state/ports`` REST endpoints.
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
    - Port names must use slot and port notation such as ``1:5``.
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired module operation.
            - ``merged`` applies the supplied interface changes incrementally without removing unspecified configuration.
            - ``replaced`` treats the supplied values as authoritative for the targeted interfaces.
            - ``overridden`` enforces the supplied definitions and clears interface overrides that are not provided.
            - ``deleted`` removes the supplied interface configuration, disabling the listed settings and port overrides.
            - ``gathered`` returns interface state information without applying changes.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    global_settings:
        description:
            - Fabric Engine global port settings to apply.
        type: dict
        suboptions:
            flow_control_mode:
                description:
                    - Enable or disable the Fabric Engine global flow control flag.
                type: bool
            advanced_feature_bandwidth_reservation:
                description:
                    - Reserve loopback bandwidth for advanced features (Fabric Engine only).
                type: str
                choices: [DISABLE, LOW, HIGH, VIM]
    admin:
        description:
            - Administrative enable/disable operations to apply across ports using the bulk ``/configuration/ports`` endpoint.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as ``1:5``).
                type: str
                required: true
            enabled:
                description:
                    - Desired administrative status for the interface.
                type: bool
                required: true
    ports:
        description:
            - Per-port configuration settings applied through ``/configuration/ports/{port}``.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as ``1:5``).
                type: str
                required: true
            enabled:
                description:
                    - Administrative status for the port.
                type: bool
            description:
                description:
                    - Textual description for the interface (max 255 characters).
                type: str
            speed:
                description:
                    - Operational speed override when auto-negotiation is disabled.
                type: str
                choices: [0M, 10M, 100M, 1G, 2.5G, 5G, 10G, 20G, 25G, 40G, 50G, 100G, 400G, AUTO]
            duplex:
                description:
                    - Duplex setting when auto-negotiation is disabled.
                type: str
                choices: [HALF_DUPLEX, FULL_DUPLEX, NONE]
            auto_negotiation:
                description:
                    - Toggle auto-negotiation for the interface.
                type: bool
            auto_advertisements:
                description:
                    - Authoritative list of auto-negotiation advertisements.
                type: list
                elements: str
                choices: [NONE, 10-HALF, 10-FULL, 100-HALF, 100-FULL, 1000-HALF, 1000-FULL, 2500-FULL, 5000-FULL, 10000-HALF, 10000-FULL, 25000-HALF, 25000-FULL, 40000-FULL, 50000-FULL, 100000-FULL, 400000-FULL]
            flow_control:
                description:
                    - Interface level flow control mode (when global flow control is enabled).
                type: str
                choices: [ENABLE, DISABLE]
            debounce_timer:
                description:
                    - Debounce timer value in milliseconds (0-300000).
                type: int
            channelized:
                description:
                    - Enable or disable channelization on supported Fabric Engine fiber ports.
                type: bool
            fec:
                description:
                    - Forward error correction mode.
                type: str
                choices: [NONE, CLAUSE_74, CLAUSE_91_108, AUTO]
            eee:
                description:
                    - Enable or disable Energy Efficient Ethernet.
                type: bool
            port_mode:
                description:
                    - Enable Fabric Engine tagging mode on the port (true indicates trunk behaviour).
                type: bool
            native_vlan:
                description:
                    - Native VLAN identifier for trunk ports (0 to clear).
                type: int
            ip_arp_inspection_trusted:
                description:
                    - Mark the interface as trusted for ARP inspection.
                type: bool
    gather_filter:
        description:
            - Limit gathered interface state to these port names.
        type: list
        elements: str

```