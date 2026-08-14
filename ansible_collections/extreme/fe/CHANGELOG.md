# Changelog

## 1.2.1
- Release date: August 2026

### New Features
- **extreme_fe_fabric_l2**: Added `SUNI` and `TUNI` I-SID types support.
- **extreme_fe_lag**: Added the `flex_uni` option, required before a LAG can be used by a `SUNI` I-SID endpoint.

### Bug Fixes
- **extreme_fe_autosense**:
    - Fixed `overridden` not resetting omitted port attributes.
    - Fixed `replaced` and `overridden` silently resetting nothing.
    - Fixed `deleted` reporting `changed=True` for a port that had no overrides. On VOSS 9.4 the `DELETE` endpoint returns 405 and the module falls back to a `PATCH` with default values, which was applied and reported unconditionally.
    - Documented the before/after snapshots, which the module already returned.
    - Renamed the `ports` list to `config`, with `ports` kept as a deprecated alias.
- **extreme_fe_interfaces**:
    - Fixed `overridden` not resetting omitted port attributes. Physical-layer fields, that are hardware-specific, are deliberately excluded.
    - `overridden` skips ports that cannot be reset (for example Insight ports) with a warning instead of failing the whole task.
    - Added before/after snapshot support.
    - Renamed the `ports` list to `config` so every resource module in the collection uses the same parameter name. `ports` remains as a deprecated alias, so existing playbooks keep working.
    - Corrected the `native_vlan` documentation. Clearing a native VLAN has no REST equivalent.
- **extreme_fe_lag**:
    - Fixed the replaced and overridden states, and added before/after snapshot support.
    - LAGs are now supplied through a `config` list, so one task can manage several LAGs. The former top-level parameters still work as a single-entry config and emit a deprecation warning.
    - `overridden` is now authoritative across the whole device — LAGs absent from `config` are deleted and reported in `deleted_lags`.
- **extreme_fe_mlag**:
    - Added the `overridden` state. It is authoritative over RSMLT as well as peer ports, so instances absent from `config` are reset to their defaults; `replaced` remains authoritative over peer ports only.
    - Added before/after snapshot support.
- **extreme_fe_slpp**:
    - Now accepts partial config for replaced and overridden states
    - Grouped the `vlans` and `ports` lists under a single `config` dict, matching `extreme_fe_mlag`. SLPP manages two distinct resource types and a task may configure both in one run, so they are kept as separate lists rather than merged. The former top-level `vlans` and `ports` still work and emit a deprecation warning; the two forms cannot be mixed in one task.
- **extreme_fe_vlans**:
    - Fixed `overridden` not enforcing VLAN membership authoritatively, and refactored to the `config` list pattern so one task can manage several VLANs.
    - `overridden` now **deletes** VLANs absent from `config` instead of resetting them to factory defaults. VLANs 1 and 4048 are never deleted, and any VLAN the device refuses to remove — typically one still referenced by an L3 interface, SPBM I-SID or RSMLT instance — is reported in `skipped_vlans` and raised as a warning rather than failing the task. Playbooks that relied on the previous reset behaviour should use `replaced`.
    - The former top-level parameters (`vlan_id`, `vlan_name`, `vlan_type`, ...) still work as a single-entry `config` and emit a deprecation warning, so existing playbooks keep running. The two forms cannot be mixed in one task.
    - Added the before/after snapshot support.
    - `state: gathered` returns the VLAN list under the standard `gathered` key. It is also still returned under `vlans`, the key used up to 1.2.0, so existing playbooks keep working; that form is deprecated and will be removed.
    - Fixed check mode predicting an empty name for a VLAN it would create without one. The device auto-assigns `VLAN-<id>`, which the predicted state now reflects.
    - Fixed `replaced` and `overridden` not enforcing membership for an interface type that was mentioned but supplied no matching members. An empty `lag_interfaces` list now clears every LAG from the VLAN, and a list naming only tagged members now removes the untagged ones. Previously an empty list was less authoritative than omitting the key.
    - Create, update and delete now fail when the device answers with a success status but an error body. Those responses were ignored, so a rejected write was reported as applied — under `overridden` a VLAN the device refused to delete was listed in `deleted_vlans` instead of `skipped_vlans`.

## 1.2.0
- Release date: June 2026

### New Modules
- **extreme_fe_anycast_gateway**: Manages Anycast Gateway interfaces
- **extreme_fe_dns**: Manages DNS settings (servers and domain)
- **extreme_fe_spbm_l3vsn**: Manages SPBM Layer3 VSN
- **extreme_fe_snmp**: Manages the SNMP system name
- **extreme_fe_vrf**: Manages VRFs (Virtual Routing and Forwarding)
- **extreme_fe_vrf_static_routes**: Manages static routes on VRFs

### Bug Fixes
- **extreme_fe_fabric_l2** module no longer requires the name parameter for replaced state
- **extreme_fe_facts** fixed v1→v0 API fallback
- **extreme_fe_l2_interfaces** module refactored to use the config-list pattern
- **extreme_fe_stp** module refactored to use the config-list pattern

## 1.1.0
- Release date: April 2026

### New Modules
- **extreme_fe_lldp_global**: Configures global LLDP timer settings
- **extreme_fe_lldp_interfaces**: Configures LLDP per-interface settings
- **extreme_fe_slpp**: Configures Simple Loop Prevention Protocol (SLPP)
- **extreme_fe_stp**: Configures STP per-port settings and BPDU Guard

### New Features
- **extreme_fe_interfaces**: Added `flex_uni` field to enable or disable Fabric Engine Flex UNI mode on the port

### Bug Fixes
- **extreme_fe_command**: Fixed module failing with HTTP status 400 despite successful CLI output
- **extreme_fe_mlag**: Fixed module failing to configure MLAG peer with error "None is not of type 'integer'"
- **extreme_fe_poe**: Fixed module failing with fatal error on devices without PoE-capable ports

### Key Improvements
- **extreme_fe_facts**: Added v1→v0 API fallback for empty responses
- **extreme_fe_fabric_l2**: Added requirement for `name` parameter when using `replaced` state
- **extreme_fe_l2_interfaces**: Refactored to use config-list pattern for better consistency
- **extreme_fe_l3_interfaces**: Added support for empty loopback interfaces, protected VLANs, and IPv6 link-local configuration

### Maintenance
- Fixed linting compliance issues (yamllint and ansible-lint)
- Updated GitHub Actions workflows for CI and publishing
- Improved module documentation

## 1.0.0
- Initial release of the Extreme Networks Fabric Engine Ansible Collection (extreme.fe)
- Includes HTTPAPI plugin, modules, playbooks, and integration harness

### Maintenance
- Reworked internal integration test harness (templates, start/stop scripts, Docker helpers)
- Added GitHub Actions workflow to build/publish the collection to Galaxy
- Ensured packaging excludes internal tests/CI assets via build_ignore in galaxy.yml
- Removed obsolete scripts (e.g., software_install.sh) and updated documentation references
