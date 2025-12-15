# extreme_fe_poe

```yaml

---
module: extreme_fe_poe
short_description: Manage PoE settings on ExtremeNetworks Fabric Engine switches
version_added: 1.4.0
description:
  - Retrieve and configure Power over Ethernet (PoE) settings for copper ports on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI plugin.
  - Supports the standard Ansible network resource states to merge, replace, override, delete, or gather PoE configuration across PoE-capable ports.
notes:
  - Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
  - Applicable only to Fabric Engine (VOSS) devices. Switch Engine (EXOS) attributes are intentionally excluded.
requirements:
  - ansible.netcommon
options:
  config:
    description:
      - Structured PoE definitions to manage.
      - Required when ``state`` is ``merged``, ``replaced``, or ``deleted``.
      - With ``state: overridden`` an empty list resets all PoE configuration for every discovered PoE-capable port.
    type: list
    elements: dict
    suboptions:
      port:
        description:
          - Identifier of the PoE-capable port (for example ``1:5``).
        type: str
        required: true
      enable:
        description:
          - Enable (true) or disable (false) PoE power on the port.
        type: bool
      power_limit:
        description:
          - Desired PoE power limit per port in milliwatts. Fabric Engine supports 3000-98000 inclusive.
        type: int
      priority:
        description:
          - Power management priority for the port.
        type: str
        choices: [LOW, HIGH, CRITICAL]
      perpetual_poe:
        description:
          - Enable or disable the Perpetual PoE feature.
        type: bool
      fast_poe:
        description:
          - Enable or disable Fast PoE startup.
        type: bool
  state:
    description:
      - Desired module operation.
      - ``merged`` applies the supplied attributes incrementally to the listed ports without removing unspecified values.
      - ``replaced`` enforces the supplied attributes on the listed ports while clearing unspecified values.
      - ``overridden`` treats the supplied configuration as authoritative for every PoE-capable port, deleting configuration from ports that are not listed.
      - ``deleted`` removes PoE configuration from the listed ports (use ``state: overridden`` with an empty ``config`` list to reset all ports).
      - ``gathered`` returns current configuration and live PoE state information without applying changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
author:
  - ExtremeNetworks Networking Automation Team

```