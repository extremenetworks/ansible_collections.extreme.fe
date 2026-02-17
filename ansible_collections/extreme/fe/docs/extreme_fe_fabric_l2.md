# extreme_fe_fabric_l2

```yaml

module: extreme_fe_fabric_l2
short_description: Manage Fabric Engine ISIDs on ExtremeNetworks switches
version_added: '1.0.0'
description:
    - "Manage Layer 2 ISIDs (service instance identifiers) on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI plugin."
    - Supports provisioning CVLAN-backed ISIDs, updating friendly names, gathering existing definitions, and removing bindings.
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - "Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project."
    - Currently supports managing CVLAN-backed ISIDs. Additional ISID types may be implemented in future revisions.
    - Supports Ansible check mode for configuration states.
requirements:
    - ansible.netcommon
options:
  state:
        description:
            - Desired module operation.
            - "``merged`` ensures the supplied attributes are merged with the running configuration and creates the ISID when missing."
            - "``replaced`` treats the supplied values as authoritative for the targeted ISID."
            - "``overridden`` enforces the supplied values and clears the friendly name when it is omitted."
            - "``deleted`` removes the ISID binding from the device."
            - "``gathered`` returns current ISID data without making changes."
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
  isid:
    description:
      - Numeric service identifier (1-15999999).
      - Required when ``state`` is not ``gathered``.
    type: int
  isid_type:
    description:
      - ISID service type. Only ``CVLAN`` is currently supported.
    type: str
    choices: [CVLAN]
    default: CVLAN
  name:
    description:
      - Friendly name to associate with the ISID.
      - When ``state`` is ``overridden`` and ``name`` is omitted, the module clears the existing friendly name.
    type: str
  cvlan:
    description:
      - CVLAN identifier to bind to the ISID when ``isid_type`` is ``CVLAN``.
      - Required when creating a new ISID or when deleting an existing ISID whose CVLAN cannot be discovered automatically.
    type: int
  gather_filter:
    description:
      - Limit gathered output to this list of ISID identifiers.
      - When omitted, the module returns all configured ISIDs.
    type: list
    elements: int

```