# extreme_fe_lag

```yaml

---
module: extreme_fe_lag
short_description: Manage LAGs on ExtremeNetworks Fabric Engine switches
version_added: "1.3.0"
description:
    - "Create and delete Link Aggregation Groups (LAGs) on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI transport."
    - "Update Fabric Engine specific LAG attributes such as friendly names, load balancing algorithms, and Fabric Engine LACP keys."
    - "Add or remove member ports through the Fabric Engine LAG REST endpoints while propagating device errors back to Ansible."
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - "Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project."
    - "Only Fabric Engine (VOSS) LAG attributes and endpoints are used; Switch Engine (EXOS) parameters are intentionally unsupported."
    - "Fabric Engine does not support patching an existing LAG's aggregation mode; delete and recreate the LAG to modify ``mode``."
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired LAG operation.
            - "``merged`` creates the target LAG when missing and merges the supplied attributes and member ports."
            - "``replaced`` enforces the supplied member list and attributes for the target LAG, removing unstated members."
            - "``overridden`` clears member overrides that are not provided and applies the supplied attribute values (an empty ``member_ports`` list removes all members)."
            - "``deleted`` removes the specified LAG entirely or prunes the provided members when ``member_ports`` or ``remove_member_ports`` is supplied."
            - "``gathered`` returns the current LAG configuration without applying changes."
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    lag_id:
        description:
            - "LAG identifier (Fabric Engine MLT identifier)."
            - "Accepts string or integer values in the Fabric Engine supported range (1-512)."
        type: raw
    name:
        description:
            - "Friendly Fabric Engine name assigned to the LAG."
        type: str
    mode:
        description:
            - "Fabric Engine aggregation mode to use when creating the LAG."
        type: str
        choices: [STATIC, LACP, VLACP]
    lacp_key:
        description:
            - "Fabric Engine aggregation key used when the LAG operates in LACP or VLACP mode."
        type: str
    load_balance_algo:
        description:
            - "Load balancing algorithm applied to the Fabric Engine LAG."
        type: str
        choices: [L2, L3, L3_L4, CUSTOM, PORT]
    member_ports:
        description:
            - "List of member ports that participate in the LAG."
            - "With ``state: merged`` missing members are added while existing members remain unless ``purge_member_ports`` is true."
            - "With ``state: replaced`` or ``state: overridden`` the provided ports become authoritative; unspecified members are removed and an empty list clears all members."
            - "With ``state: deleted`` the provided ports are removed from the LAG without deleting the LAG itself."
        type: list
        elements: str
    add_member_ports:
        description:
            - "Incremental list of member ports to add to the LAG when ``state: merged``."
        type: list
        elements: str
    remove_member_ports:
        description:
            - "Incremental list of member ports to remove from the LAG when ``state: merged`` or ``state: deleted``."
        type: list
        elements: str
    purge_member_ports:
        description:
            - "Remove member ports that are not present in ``member_ports`` (only evaluated when ``state: merged``)."
            - "Requires ``member_ports`` when set to true."
        type: bool
        default: false
    gather_filter:
        description:
            - "Restrict gathered LAG results to these identifiers."
        type: list
        elements: str

```