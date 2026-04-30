# extreme_fe_stp

```yaml
---
module: extreme_fe_stp
short_description: Manage STP per-port settings on ExtremeNetworks Fabric Engine switches
version_added: 1.1.0
description:
- Configure STP per-port settings on ExtremeNetworks Fabric Engine
  (VOSS) switches using the C(extreme_fe) HTTPAPI connection plugin.
- Supports BPDU Guard, edge port, port priority, path cost, and
  per-port STP enable/disable.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the C(ansible.netcommon) collection and the C(extreme_fe)
  HTTPAPI plugin shipped with this project.
- BPDU Guard requires STP to be active on the device.
- C(stp_instance) is required and identifies the STP domain to
  operate on.  Use C(0) for CIST/RSTP, or C(0)-C(63) for MSTP
  instances.  This mirrors the VOSS CLI and REST API, which
  always require an explicit STP instance.
- On VOSS, C(bpduRestrictEnabled) is not separately configurable; it
  is always C(true) when C(bpduProtection) is C(GUARD).
requirements:
- ansible.netcommon
options:
  interface:
    description:
    - Interface identifier, for example C(PORT:1:5) or C(LAG:10). When the type prefix is omitted, C(PORT) is assumed.
    type: str
  interface_type:
    description:
    - Interface type. Use together with C(interface_name) when the combined C(interface) parameter is not supplied.
    type: str
    choices:
    - PORT
    - LAG
  interface_name:
    description:
    - Interface name (for C(PORT) use slot/port notation such as C(1:5)).
    type: str
  bpdu_guard_enabled:
    description:
    - Enable (C(true)) or disable (C(false)) BPDU Guard on the port.
    - When omitted, the BPDU Guard setting is left unchanged (merged)
      or not managed at all.
    type: bool
  recovery_timeout:
    description:
    - Seconds before a BPDU Guard disabled port is re-enabled.
    - A value of C(0) means the port stays disabled forever.
    - Valid range is C(0) or C(10-65535).  Default on VOSS is 120.
    type: int
  is_edge_port:
    description:
    - Mark the port as an edge port (directly connected to a user
      device rather than another switch).  CIST only.
    type: bool
  priority:
    description:
    - STP port priority (0-240 in steps of 16, default 128).
    type: int
  path_cost:
    description:
    - STP path cost contribution (1-200000000).
    type: int
  stp_enabled:
    description:
    - Enable (C(true)) or disable (C(false)) STP on this port.
    - Default is C(true) (STP enabled on port at factory reset).
    type: bool
  stp_instance:
    description:
    - STP instance (domain) to target for BPDU Guard and STP
      per-port settings.
    - In MSTP mode, valid values are C(0) (CIST) through C(63).
    - In RSTP mode, only C(0) is valid.
    - Both plain instance numbers (C(0), C(2)) and device-format
      names (C(s0), C(s2)) are accepted.
    required: true
    type: str
  state:
    description:
    - Desired module operation.
    - '`merged` applies the provided parameters incrementally without removing unspecified STP settings.'
    - '`replaced` treats the supplied values as authoritative for the target interface. Omitted STP fields are reset to factory defaults (except C(path_cost), which has no documented VOSS default and is left unchanged unless explicitly set).'
    - '`overridden` is like C(replaced) but also resets other ports within the same STP instance to factory defaults (C(path_cost) exception applies — see C(replaced)).'
    - '`deleted` resets STP per-port settings to factory defaults (C(path_cost) is left unchanged).'
    - '`gathered` returns the current STP per-port settings without applying changes.'
    type: str
    choices:
    - merged
    - replaced
    - overridden
    - deleted
    - gathered
    default: merged
```
