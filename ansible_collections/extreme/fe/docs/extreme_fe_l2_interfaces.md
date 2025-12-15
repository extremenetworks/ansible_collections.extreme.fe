# extreme_fe_l2_interfaces

```yaml

---
module: extreme_fe_l2_interfaces
short_description: Manage L2 interface VLAN membership on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Configure interface VLAN membership on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI plugin.
- Supports setting access/trunk mode, untagged VLANs, and tagged VLAN lists on physical or LAG interfaces.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
requirements:
- ansible.netcommon
options:
  interface:
    description:
    - Interface identifier, for example ``PORT:1:5`` or ``LAG:10``. When the type prefix is omitted, ``PORT`` is assumed.
    type: str
  interface_type:
    description:
    - Interface type. Use together with ``interface_name`` when the combined ``interface`` parameter is not supplied.
    type: str
    choices:
    - PORT
    - LAG
  interface_name:
    description:
    - Interface name (for ``PORT`` use slot/port notation such as ``1:5``).
    type: str
  port_type:
    description:
    - Interface VLAN mode.
    type: str
    choices:
    - ACCESS
    - TRUNK
  untagged_vlan:
    description:
    - VLAN ID for untagged traffic (port VLAN). Use ``0`` to clear the untagged VLAN.
    type: int
  tagged_vlans:
    description:
    - Authoritative list of tagged (allowed) VLANs for the interface. Replaces any existing list.
    type: list
    elements: int
  add_tagged_vlans:
    description:
    - VLANs to add to the tagged list without removing other entries.
    type: list
    elements: int
  remove_tagged_vlans:
    description:
    - VLANs to remove from the tagged list without affecting other entries.
    type: list
    elements: int
  state:
    description:
    - Desired module operation.
    - '`merged` applies the provided parameters incrementally without removing unspecified VLAN membership.'
    - '`replaced` treats the supplied values as authoritative for the target interface.'
    - '`overridden` enforces the supplied values and clears the untagged VLAN and tagged membership when not provided.'
    - '`deleted` removes tagged VLAN membership (optionally limited to the supplied VLAN list) and clears the untagged VLAN when applicable.'
    - '`gathered` returns the current VLAN membership without applying changes.'
    type: str
    choices:
    - merged
    - replaced
    - overridden
    - deleted
    - gathered
    default: merged

```