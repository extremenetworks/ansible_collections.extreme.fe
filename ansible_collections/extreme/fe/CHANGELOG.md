# Changelog

## 1.1.0
- Release date: April 2026

### New Modules
- **extreme_fe_lldp_global**: Configure global LLDP timer settings
- **extreme_fe_lldp_interfaces**: Configure LLDP per-interface settings
- **extreme_fe_slpp**: Configure Simple Loop Prevention Protocol (SLPP)
- **extreme_fe_stp**: Configure STP per-port settings and BPDU Guard

### New Features
- **extreme_fe_interfaces**: Added `flex_uni` field to enable or disable Fabric Engine Flex UNI mode on the port

### Bug Fixes
- **IAC-82**: Fixed extreme_fe_command module failing with HTTP status 400 despite successful CLI output
- **IAC-90**: Fixed extreme_fe_mlag module failing to configure MLAG peer with error "None is not of type 'integer'"
- **IAC-92**: Fixed extreme_fe_poe module failing with fatal error on devices without PoE-capable ports

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
