# extreme_fe_lldp_interfaces

```yaml
---
module: extreme_fe_lldp_interfaces
short_description: Manage LLDP interface settings on ExtremeNetworks Fabric Engine switches
version_added: "1.1.0"
description:
  - Manage LLDP interface-level settings on ExtremeNetworks Fabric Engine (VOSS) switches using the custom C(extreme_fe) HTTPAPI plugin.
  - Uses C(/v0/configuration/lldp/ports/{port}) and C(/v0/configuration/lldp/ports/{port}/med-policy) from the NOS OpenAPI schema.
  - Supports the VOSS LLDP port attributes exposed by the schema, including basic transmit or receive control, advertised TLVs, location data, and MED network policy entries.
  - Switch Engine (EXOS)-only LLDP attributes are intentionally excluded.
  - When C(med_policy) is supplied, it is treated as the authoritative list for that interface because the device API replaces the full MED policy list.
author:
  - ExtremeNetworks Networking Automation Team
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
  - Port identifiers must use slot:port notation such as C(1:5).
  - On Fabric Engine, C(transmit_enabled) and C(receive_enabled) should be set to the same value. If only one is supplied, this module mirrors the same value to the other field.
  - If LLDP transmit or receive is disabled, the device ignores advertisement and location attributes in the same request. This module submits only the basic LLDP enable flags in that case.
requirements:
  - ansible.netcommon
options:
  state:
    description:
      - Desired module operation.
      - C(merged) applies the supplied interface settings incrementally without removing unspecified configuration.
      - C(replaced) treats the supplied values as authoritative for the targeted interfaces and resets omitted LLDP attributes to device defaults.
      - C(overridden) behaves like C(replaced) for the listed interfaces and resets LLDP settings on discovered interfaces that are not provided.
      - C(deleted) resets the listed interfaces to LLDP defaults.
      - C(gathered) returns current LLDP interface configuration without applying changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  interfaces:
    description:
      - Interface LLDP definitions to manage.
      - Required when C(state) is C(merged), C(replaced), C(overridden), or C(deleted).
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - Port identifier in slot:port notation such as C(1:5).
        type: str
        required: true
      transmit_enabled:
        description:
          - Enable or disable LLDP transmit on the port.
        type: bool
      receive_enabled:
        description:
          - Enable or disable LLDP receive on the port.
        type: bool
      advertise:
        description:
          - LLDP TLVs advertised on the port.
        type: dict
        suboptions:
          system_capabilities:
            description:
              - Advertise the system capabilities TLV.
            type: bool
          system_description:
            description:
              - Advertise the system description TLV.
            type: bool
          system_name:
            description:
              - Advertise the system name TLV.
            type: bool
          port_description:
            description:
              - Advertise the port description TLV.
            type: bool
          management_address:
            description:
              - Advertise the management address TLV.
            type: bool
          med_capabilities:
            description:
              - Advertise the MED capabilities TLV.
            type: bool
          med_power:
            description:
              - Advertise the MED power TLV.
            type: bool
          dot3_mac_phy:
            description:
              - Advertise the 802.3 MAC or PHY TLV.
            type: bool
          location:
            description:
              - Advertise the MED location TLV.
            type: bool
          network_policy:
            description:
              - Advertise the MED network policy TLV.
            type: bool
          inventory:
            description:
              - Advertise the MED inventory TLV.
            type: bool
      location:
        description:
          - MED location information for the port.
        type: dict
        suboptions:
          civic_address:
            description:
              - Civic address location string in Fabric Engine civic address format.
            type: str
          ecs_elin:
            description:
              - Emergency line identification number.
            type: str
          coordinate:
            description:
              - Coordinate-based location string.
            type: str
      med_policy:
        description:
          - Authoritative MED network policy entries for the interface.
          - When provided, the module replaces the full MED policy list for the port.
        type: list
        elements: dict
        suboptions:
          type:
            description:
              - MED application type.
            type: str
            required: true
            choices:
              - GUEST_VOICE
              - GUEST_VOICE_SIGNALING
              - SOFT_PHONE_VOICE
              - STREAMING_VIDEO
              - VIDEO_CONFERENCING
              - VIDEO_SIGNALING
              - VOICE
              - VOICE_SIGNALING
          dscp:
            description:
              - DSCP value advertised for the policy.
            type: int
            required: true
          priority:
            description:
              - 802.1p priority advertised for the policy.
            type: int
            required: true
          tagged:
            description:
              - Whether the policy VLAN is tagged.
            type: bool
            required: true
          vlan_id:
            description:
              - VLAN identifier associated with the policy.
            type: int
            required: true
  gather_filter:
    description:
      - Optional list of interface names to limit gathered configuration or state output.
    type: list
    elements: str
  gather_state:
    description:
      - When true, include operational LLDP neighbor state from C(/v0/state/lldp/ports/{port}).
    type: bool
    default: false
```
