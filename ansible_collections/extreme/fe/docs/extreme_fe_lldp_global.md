# extreme_fe_lldp_global

```yaml
---
module: extreme_fe_lldp_global
short_description: Manage global LLDP settings on ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
  - Manage device-wide LLDP timer settings on ExtremeNetworks Fabric Engine (VOSS) switches using the custom C(extreme_fe) HTTPAPI plugin.
  - Uses C(/v0/configuration/lldp) from the NOS OpenAPI schema.
  - Only Fabric Engine global attributes are exposed for configuration. Switch Engine (EXOS)-only fields are intentionally excluded.
  - C(init_delay_seconds) is returned in gathered output when present on the device, but it is not configurable on Fabric Engine.
author:
  - ExtremeNetworks Networking Automation Team
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
  - This module manages the singleton global LLDP resource only. It does not manage per-port LLDP settings.
  - C(overridden) is functionally equivalent to C(replaced) because the LLDP global configuration is a singleton object.
  - C(deleted) resets supplied attributes to device defaults. If C(config) is omitted with C(state=deleted), all configurable global LLDP attributes are reset.
requirements:
  - ansible.netcommon
options:
  config:
    description:
      - Structured LLDP global settings to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional when C(state=deleted); if omitted, all configurable LLDP global settings are reset to defaults.
    type: dict
    suboptions:
      advertisement_interval:
        description:
          - The interval in seconds at which LLDP frames are transmitted.
          - Maps to C(advertisementInterval).
        type: int
      hold_multiplier:
        description:
          - Multiplier applied to C(advertisement_interval) to determine neighbor time-to-live.
          - Maps to C(holdMultiplier).
        type: int
  gather_state:
    description:
      - When true, include LLDP operational state from C(/v0/state/lldp) in the module result.
    type: bool
    default: false
  state:
    description:
      - Desired module operation.
      - C(merged) incrementally applies only the supplied LLDP global attributes.
      - C(replaced) treats configurable LLDP global attributes as authoritative and resets omitted configurable attributes to defaults.
      - C(overridden) behaves like C(replaced) for this singleton resource.
      - C(deleted) resets the supplied attributes, or all configurable attributes when C(config) is omitted.
      - C(gathered) returns the current LLDP global configuration without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
```
