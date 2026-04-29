# extreme_fe_l2_interfaces

```yaml

---
module: extreme_fe_l2_interfaces
short_description: Manages L2 interface settings on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Configure L2 interface settings on ExtremeNetworks Fabric Engine
  (VOSS) switches using the ``extreme_fe`` HTTPAPI connection plugin.
- Supports VLAN membership (access/trunk mode, tagged/untagged VLANs)
  on one or more interfaces per task via the ``config`` list parameter.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe``
  HTTPAPI plugin shipped with this project.
- When ``state=overridden``, the module reads all interface VLAN
  settings and resets any interface not listed in ``config`` to the
  device defaults (TRUNK mode, untagged VLAN 1, no tagged VLANs).
  ``config`` must not be empty.  Interfaces that cannot be reset
  (e.g. LACP LAGs) are skipped with a warning.
requirements:
- ansible.netcommon
options:
  config:
    description:
    - List of L2 interface definitions to manage.
    - When omitted with ``state=gathered``, the module returns VLAN
      settings for all interfaces on the device.
    type: list
    elements: dict
    suboptions:
      name:
        description:
        - Interface identifier such as ``1:5``, ``PORT:1:5``, or ``LAG:10``.
          When the type prefix is omitted, ``PORT`` is assumed.
        type: str
        required: true
      port_type:
        description:
        - Interface VLAN mode.
        type: str
        choices:
        - ACCESS
        - TRUNK
      untagged_vlan:
        description:
        - VLAN ID for untagged traffic (port VLAN).
          Use ``0`` to clear the untagged VLAN.
        type: int
      tagged_vlans:
        description:
        - Authoritative list of tagged (allowed) VLANs for the
          interface. In ``merged`` state, replaces the current
          tagged list (use ``add_tagged_vlans``/``remove_tagged_vlans``
          for incremental changes). In ``replaced``/``overridden``
          states, sets the complete tagged list.
        type: list
        elements: int
      add_tagged_vlans:
        description:
        - VLANs to add to the tagged list without removing other
          entries. Only valid with ``state=merged``.
        type: list
        elements: int
      remove_tagged_vlans:
        description:
        - VLANs to remove from the tagged list without affecting
          other entries. Only valid with ``state=merged`` or
          ``state=deleted``.
        type: list
        elements: int
  state:
    description:
    - Desired module operation.
    - C(merged) applies the provided parameters incrementally
      without removing unspecified VLAN membership.
    - C(replaced) treats the supplied values as authoritative
      for each listed interface.
    - C(overridden) like C(replaced) but also resets every
      interface NOT in C(config) to device defaults.
    - C(deleted) removes tagged VLAN membership. When no VLAN
      parameters are given, all memberships are reset.
    - C(gathered) returns current VLAN membership without
      applying changes.
    type: str
    choices:
    - merged
    - replaced
    - overridden
    - deleted
    - gathered
    default: merged

```