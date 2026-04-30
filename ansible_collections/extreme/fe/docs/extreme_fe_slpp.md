# extreme_fe_slpp

```yaml
---
module: extreme_fe_slpp
short_description: Manage Fabric Engine SLPP (Simple Loop Prevention Protocol) settings
version_added: 1.1.0
description:
    - Manage global, per-VLAN, and per-port SLPP settings on ExtremeNetworks Fabric Engine
      switches using the custom C(extreme_fe) HTTPAPI plugin.
    - SLPP detects and contains Layer-2 loops by sending special loop-detection frames and
      blocking or shutting down the offending port and/or VLAN context upon loop detection.
    - Supports SLPP guard (blocks the port on loop detection) and SLPP packet reception
      detection modes.  On VOSS, enabling both packet-rx and guard on the same port
      simultaneously is not allowed.
    - Provides a gathered mode that reports the full configuration and live SLPP port state
      from C(/v0/state/slpp).
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin
      shipped with this project.
    - Port identifiers must use slot:port notation such as C(1:5).
    - On Fabric Engine B(VOSS), enabling both C(enable_packet_rx) and C(enable_guard) on the
      same port at the same time is not allowed.  The module will raise an error if both are
      set to C(true) in the same port entry.
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired module operation.
            - C(merged) applies the provided settings as an incremental merge.
            - C(replaced) makes the supplied values authoritative for the targeted resources.
            - C(overridden) replaces the running configuration with the supplied values and
              removes entries that are not provided.
            - C(deleted) removes the specified per-port and per-VLAN overrides.
            - C(gathered) returns the current configuration (and optional state payloads)
              without making changes.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    global_settings:
        description:
            - Global SLPP settings applied through C(/v0/configuration/slpp).
        type: dict
        suboptions:
            enabled:
                description:
                    - Enable or disable SLPP globally on the switch.
                type: bool
    vlans:
        description:
            - Per-VLAN SLPP settings applied through C(/v0/configuration/slpp/vlan/{vlan_id}).
        type: list
        elements: dict
        suboptions:
            vlan_id:
                description:
                    - VLAN identifier (1-4094).
                type: int
                required: true
            enabled:
                description:
                    - Enable or disable SLPP on this VLAN.
                type: bool
    ports:
        description:
            - Per-port SLPP settings applied through C(/v0/configuration/slpp/ports/{port}).
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as C(1:5)).
                type: str
                required: true
            enable_guard:
                description:
                    - Enable SLPP guard on the specified port.  When a loop is detected the
                      port is disabled.  Cannot be enabled at the same time as C(enable_packet_rx).
                type: bool
            guard_timeout:
                description:
                    - Time in seconds a port remains disabled after SLPP guard triggers.
                      A value of C(0) means the port will never be automatically re-enabled.
                      Valid range is C(0) or C(10-65535).
                type: int
            enable_packet_rx:
                description:
                    - Enable SLPP packet reception detection on the specified port.
                      This setting is applicable to Fabric Engine (VOSS) only.
                      Cannot be enabled at the same time as C(enable_guard).
                type: bool
            packet_rx_threshold:
                description:
                    - Number of SLPP packets received before action is taken.
                      Valid range is C(1-500).  Default is C(1).
                      This setting is applicable to Fabric Engine (VOSS) only.
                type: int
    gather_filter:
        description:
            - Optional list of port identifiers used to limit gathered configuration
              and state output.
        type: list
        elements: str
    gather_vlan_filter:
        description:
            - Optional list of VLAN IDs used to limit gathered VLAN configuration output.
        type: list
        elements: int
    gather_state:
        description:
            - When true, include data from C(/v0/state/slpp) in the result.
        type: bool
        default: false
```
