# extreme_fe_vlans

```yaml

module: extreme_fe_vlans
short_description: Manage VLANs on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Create, update, remove, and query VLANs on ExtremeNetworks Fabric Engine switches using
  the custom ``extreme_fe`` HTTPAPI plugin.
- Supports creating VLANs, ensuring membership, deleting VLANs, and collecting VLAN facts.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped
  with this project.
requirements:
- ansible.netcommon
options:
    state:
        description:
        - Desired VLAN operation.
        - ``merged`` applies the supplied attributes and membership changes incrementally without removing unspecified values.
        - ``replaced`` makes the provided data authoritative for the listed memberships.
        - ``overridden`` clears memberships that are not provided while applying the supplied definitions.
        - ``deleted`` removes the VLAN from the device.
        - ``gathered`` returns current VLAN information without applying changes.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
  vlan_id:
    description:
    - Numeric VLAN identifier (1-4094).
    type: int
  vlan_name:
    description:
    - Friendly name assigned to the VLAN.
    type: str
  vlan_type:
    description:
    - VLAN type identifier required on Fabric Engine platforms.
    - Defaults to PORT_MSTP_RSTP when omitted.
    type: str
    default: PORT_MSTP_RSTP
  stp_name:
    description:
    - Auto-bind STP instance name associated with the VLAN.
    - Leave undefined to target the device default (instance 0).
    type: str
  vr_name:
    description:
    - Virtual router/forwarding context the VLAN belongs to.
    type: str
    default: GlobalRouter
  gather_filter:
    description:
    - Limit gathered VLAN facts to these VLAN identifiers.
    type: list
    elements: int
    lag_interfaces:
        description:
        - LAG memberships to ensure present on the VLAN. Use ``tag`` to choose tagged or untagged membership.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                - LAG identifier to manage. Use the numeric LAG ID as reported by the device.
                type: str
                required: true
            tag:
                description:
                - Apply the LAG as a tagged or untagged VLAN member.
                type: str
                choices: [tagged, untagged]
                default: tagged
    remove_lag_interfaces:
        description:
        - LAG memberships to remove from the VLAN when performing merge-style operations.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                - LAG identifier to remove. Use the numeric LAG ID as reported by the device.
                type: str
                required: true
            tag:
                description:
                - Membership type to remove (tagged or untagged).
                type: str
                choices: [tagged, untagged]
                default: tagged
    isis_logical_interfaces:
        description:
        - ISIS logical interfaces to ensure present on the VLAN.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                - Logical interface identifier (for example ``1`` or ``10``).
                type: str
                required: true
            tag:
                description:
                - Assign the logical interface as tagged or untagged within the VLAN.
                type: str
                choices: [tagged, untagged]
                default: tagged
    remove_isis_logical_interfaces:
        description:
        - ISIS logical interface memberships to remove from the VLAN.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                - Logical interface identifier to remove.
                type: str
                required: true
            tag:
                description:
                - Membership type to remove (tagged or untagged).
                type: str
                choices: [tagged, untagged]
                default: tagged

```