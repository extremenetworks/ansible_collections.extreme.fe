# Changelog

## 1.2.0
- Release date: June 2026

### New Modules
- **extreme_fe_anycast_gateway**: Manages Anycast Gateway interfaces
- **extreme_fe_dns**: Manages DNS settings (servers and domain)
- **extreme_fe_spbm_l3vsn**: Manages SPBM Layer3 VSN
- **extreme_fe_snmp**: Manages the SNMP system name
- **extreme_fe_vrf**: Manages VRFs (Virtual Routing and Forwarding)
- **extreme_fe_vrf_static_routes**: Manages static routes on VRFs

### Notable Bug Fixes
**extreme_fe_fabric_l2** module no longer requires the name parameter for replaced state
**extreme_fe_facts** fixed v1→v0 API fallback
**extreme_fe_l2_interfaces** module refactored to use the config-list pattern
**extreme_fe_stp** module refactored to use the config-list pattern


## 1.1.0
- Release date: April 2026

### New Modules
- **extreme_fe_lldp_global**: Configures global LLDP timer settings
- **extreme_fe_lldp_interfaces**: Configures LLDP per-interface settings
- **extreme_fe_slpp**: Configures Simple Loop Prevention Protocol (SLPP)
- **extreme_fe_stp**: Configures STP per-port settings and BPDU Guard

### New Features
- **extreme_fe_interfaces**: Added `flex_uni` field to enable or disable Fabric Engine Flex UNI mode on the port

### Notable Bug Fixes
- **extreme_fe_command** module failing with HTTP status 400 despite successful CLI output
- **extreme_fe_mlag** module failing to configure MLAG peer with error "None is not of type 'integer'"
-  **extreme_fe_poe** module failing with fatal error on devices without PoE-capable ports

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
