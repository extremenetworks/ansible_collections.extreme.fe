# extreme_fe_mlag

```yaml

module: extreme_fe_mlag
short_description: Manage MLAG on ExtremeNetworks Fabric Engine switches
version_added: 1.4.0
description:
- Manage Multi-switch Link Aggregation (MLAG) configuration on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI transport.
- Configure MLAG peers, ports, and RSMLT (Routed Split Multi-Link Trunking) instances.
- Supports both configuration and state retrieval operations for comprehensive MLAG management.
- Handles error propagation from device REST API endpoints back to Ansible.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
- Fabric Engine (VOSS) specific functionality; Switch Engine (EXOS) features are limited.
- RSMLT operations are Fabric Engine specific.
requirements:
- ansible.netcommon
options:
  state:
    description:
    - Desired MLAG operation.
    type: str
    choices: [present, absent, gathered, merged, replaced, deleted]
    default: present
  config:
    description:
    - MLAG configuration parameters.
    type: dict
    suboptions:
      peers:
        description:
        - List of MLAG peers to configure.
        type: list
        elements: dict
        suboptions:
          peer_id:
            description:
            - MLAG peer identifier.
            type: str
            required: true
          peer_ip_address:
            description:
            - IP address of the MLAG peer.
            type: str
          local_ip_address:
            description:
            - Local IP address for MLAG communication.
            type: str
          local_vlan_id:
            description:
            - Local VLAN ID for MLAG communication.
            type: int
          authentication_key:
            description:
            - Authentication key for MLAG peer.
            type: str
          hello_interval:
            description:
            - Hello interval for MLAG peer communication in seconds.
            type: int
          hello_timeout:
            description:
            - Hello timeout for MLAG peer communication in seconds.
            type: int
          ports:
            description:
            - List of MLAG ports for this peer.
            type: list
            elements: dict
            suboptions:
              port_id:
                description:
                - Port identifier (LAG ID).
                type: str
                required: true
              mlag_id:
                description:
                - MLAG ID for the port.
                type: int
      rsmlt:
        description:
        - RSMLT configuration.
        type: dict
        suboptions:
          instances:
            description:
            - List of RSMLT instances to configure.
            type: list
            elements: dict
            suboptions:
              vlan_id:
                description:
                - VLAN ID for RSMLT instance.
                type: int
                required: true
              enabled:
                description:
                - Enable/disable RSMLT instance.
                type: bool
                default: true
              hold_up_timer:
                description:
                - Hold up timer value in seconds (0-3600, or 9999 for infinity).
                type: int
                default: 0
              hold_down_timer:
                description:
                - Hold down timer value in seconds (0-3600).
                type: int
                default: 0
  gather_filter:
    description:
    - Filter for gathered information.
    type: dict
    suboptions:
      peer_ids:
        description:
        - List of peer IDs to gather information for.
        type: list
        elements: str
      include_ports:
        description:
        - Include port information in gathered data.
        type: bool
        default: true
      include_rsmlt:
        description:
        - Include RSMLT information in gathered data.
        type: bool
        default: true
      include_state:
        description:
        - Include state information in gathered data.
        type: bool
        default: false

```