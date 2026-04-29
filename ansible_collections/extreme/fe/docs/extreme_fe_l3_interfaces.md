# extreme_fe_l3_interfaces

```yaml

module: extreme_fe_l3_interfaces
short_description: Manage Layer 3 interfaces on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Configure IPv4 and IPv6 addressing on VLAN and loopback interfaces of ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI transport.
- Supports declarative merge, replace, override, delete, and gather operations modeled after the Ansible ``ios_l3_interfaces`` and ``junos_l3_interfaces`` modules.
- Updates rely on the Fabric Engine REST resources ``/v0/configuration/vlan/{vlan_id}/address`` and ``/v0/configuration/loopback/{id}`` as defined in ``nos-openapi-09-15-2025.yaml``.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
- VLANs and loopbacks must exist prior to invoking this module; creation is out of scope.
- ``state=gathered`` returns all VLANs including system-protected ones (dynamic, management, BROUTER). When ``state=overridden``, those VLANs are skipped with a warning instead of being cleared. Other states pass requests to the device as-is and let the REST API reject invalid operations.
requirements:
- ansible.netcommon
options:
  config:
    description:
    - List of Layer 3 interface definitions to manage.
    - When omitted with ``state: gathered``, the module returns all VLANs (including system-protected) and all loopbacks that have at least one IP address. The REST API does not list empty loopbacks; use an explicit ``config`` entry to gather a specific empty loopback.
    type: list
    elements: dict
    suboptions:
      name:
        description:
        - Interface identifier for readability, such as ``VLAN 20`` or ``Loopback 10``.
        - When ``type`` is not supplied, the module attempts to infer the interface type and identifier from ``name``.
        type: str
      type:
        description:
        - Interface type to operate on.
        type: str
        choices: [vlan, loopback]
      vlan_id:
        description:
        - VLAN identifier for routed VLAN interfaces (SVIs).
        type: int
      loopback_id:
        description:
        - Loopback identifier for Fabric Engine loopback interfaces.
        type: int
      vrf:
        description:
        - Optional VRF name for documentation purposes only; changes are not pushed through this module.
        type: str
      ipv4:
        description:
        - IPv4 addresses to manage on the interface.
        - Accepts CIDR strings (for example ``10.0.1.1/24``) or dictionaries with ``address`` and ``prefix``/``mask``/``mask_length`` keys.
        type: list
        elements: raw
      ipv6:
        description:
        - IPv6 addresses to manage on the interface.
        - Accepts CIDR strings or dictionaries with ``address`` and ``prefix``/``mask_length`` keys.
        type: list
        elements: raw
  state:
    description:
    - Desired module operation.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged

```