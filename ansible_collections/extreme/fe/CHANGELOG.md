# Changelog

## 1.3.0
- Release date: October 2026

### New Modules
- **extreme_fe_capabilities**: Reads device capabilities (platform, ports, supported URLs and OpenAPI limits).
- **extreme_fe_local_users**: Manages local user accounts.
- **extreme_fe_ntp_global**: Manages the global NTP settings.
- **extreme_fe_radius**: Manages global RADIUS settings, AAA servers, dynamic authorization clients, and secure profiles.
- **extreme_fe_ssh**: Manages the SSH service flags.
- **extreme_fe_syslog**: Manages the global syslog admin state and the syslog servers list.
- **extreme_fe_web**: Manages web-server settings.

### New Features
- **extreme_fe httpapi plugin**:
    - Inventories can identify switches by DNS hostname or FQDN, with no `ansible_host`. The plugin resolves the name and connects to the IP address, because connecting by name sends the TLS SNI extension, which affected Fabric Engine releases abort the handshake on.
    - Added the `ansible_httpapi_resolve_hostname` option (default `true`); set it to `false` to always connect by name. Hosts given as IP addresses and plain-HTTP connections are unaffected.
    - With `ansible_httpapi_validate_certs=true`, the switch certificate should list the switch IP address as an `iPAddress` subjectAltName, since it is verified against the address connected to.
    - A switch pinned to its own self-signed certificate (the only certificate in `ansible_httpapi_ca_path`) keeps being reached by name; a CA bundle at `ca_path` does not change the behaviour.
    - The address is resolved again when `validate_certs` or `ca_path` change, by `wait_for_connection`, and after a connection reset, so a DNS failover or readdressed switch takes effect.

### Bug Fixes
- **extreme_fe_anycast_gateway**:
    - **Breaking:** `gathered` holds only the `config` options, so it can be fed back as `config`. The read-only `mac_address`, `l2vsn_isid` and `oper_state` moved to the new `anycast_gateways_state` list.
    - A lost answer during a re-create, delete or enable is checked against the device. The failure says what is configured (`replacement_kept`, `details.original_payload`).
    - added `before`, `after` and `--diff` support.
    - Deprecated the `api_responses` return key (removal in 2.0.0).
- **extreme_fe_autosense**:
    - **Breaking:** `deleted`, and the ports `overridden` removes, return each port to its factory defaults (`enable: true`, `nsi: 0`, `wait_interval: 35`). Up to 1.2.x autosense was turned off on the port; use `merged` with `enable: false` for that.
    - **Breaking:** `deleted` without `config` removes the override of every port.
    - `gathered` returns the per-port overrides in the form `config` accepts. `ports_settings` and `ports` are deprecated (removal in 2.0.0).
- **extreme_fe_command**:
    - A failed batch returns `responses` for every command, so the output of the commands that succeeded is not lost. It reports `changed: true` when commands ran before the failure.
    - Fixed a batch failing when a command that answers 400 with output (such as `show sys-info`) was not the last one. The skipped commands are now re-sent.
- **extreme_fe_facts**:
    - An endpoint the device does not serve or refuses (for example PoE on a switch without PoE), or that answers with an error document, is left out with a warning instead of failing every fact.
    - Secret values (SNMP communities and passwords, web server and proxy passwords, OSPF keys) are no longer returned in the facts.
    - `gather_subset` accepts `min` and `!all`.
- **extreme_fe_interfaces**:
    - **Breaking:** `deleted` without `config` and `admin` resets every port to its defaults, except for the protected management port, the management VLAN members and their LAG member ports.
    - `gathered` returns the port configuration in the form `config` accepts; a port listed twice in `config` fails before any request.
    - added `before`, `after` and `--diff` support.
- **extreme_fe_l2_interfaces**:
    - **Breaking:** `gathered` returns entries in the form `config` accepts. The previous per-interface form is still returned under `interfaces` (deprecated, removal in 2.0.0).
    - **Breaking:** `replaced` and `overridden` reset an omitted `untagged_vlan` instead of keeping the current one; set it explicitly to keep it.
    - `deleted` without `config` resets every port and LAG; protected interfaces are skipped and listed in `skipped_interfaces`.
    - added `before`, `after` and `--diff` support.
- **extreme_fe_l3_interfaces**:
    - The vIST VLAN is protected: `overridden` and `deleted` without `config` skip it with a warning, and an explicit change fails.
    - `deleted` without `config` removes the addresses of every interface; `overridden` without `config` fails instead of clearing every interface.
    - `deleted` on a VLAN that does not exist is a no-op instead of failing.
    - Moving an address between interfaces in one task no longer fails as a duplicate.
    - `gathered` returns the interfaces in the form `config` accepts; a misspelt `config` key is rejected.
- **extreme_fe_lag**:
    - **Breaking:** `gathered` returns the form `config` accepts.
    - `overridden` and `deleted` without `config` keep the vIST LAG and the members of the vIST VLAN.
    - added `before`, `after` and `--diff` support.
- **extreme_fe_lldp_global**:
    - `gathered` returns the form `config` accepts.
    - Deprecated the `api_responses` return key (removal in 2.0.0).
- **extreme_fe_lldp_interfaces**:
    - **Breaking:** `deleted` without `config` resets every interface to its LLDP defaults.
    - `gathered` returns entries in the form `config` accepts; `interfaces_settings` is deprecated (removal in 2.0.0).
    - Renamed the `interfaces` list to `config`; `interfaces` remains as a deprecated alias.
    - Deprecated the `api_responses` return key (removal in 2.0.0).
- **extreme_fe_snmp**:
    - **Breaking:** an unset system name is returned as `""` instead of `null`, so `gathered` can be fed back as `config`. Playbooks that test the name with `is none` must test for `""`.
    - SNMP communities and SNMPv3 passwords are no longer returned, including in `api_responses` and error messages.
    - Deprecated the `api_responses` return key (removal in 2.0.0).
- **extreme_fe_vlans**:
    - **Breaking:** `gathered` returns the form `config` accepts, with LAG and ISIS members in `lag_interfaces` and `isis_logical_interfaces`. PORT members are left out (they are managed by `extreme_fe_l2_interfaces`). The previous form is still returned under `vlans`.
    - `overridden` and `deleted` without `config` no longer delete the protected management VLAN, dynamic VLANs or `BROUTER` VLANs; they are listed in `skipped_vlans`.
    - A VLAN the device keeps after a DELETE answered 204 is reported as not deleted.
    - A partly applied LAG membership change fails with `changed: true` and lists the applied interfaces.
- **All resource modules of this release** (named above):
    - `merged`, `replaced` and `overridden` with an omitted or empty `config` fail before any request with "value of config parameter must not be empty for state <state>".
    - A write that fails without an answer (a lost connection) reports `changed: true` with `details.outcome: unknown`, as it may have been applied. A failure after an earlier successful write reports `changed: true` and names what was applied.

## 1.2.1
- Release date: August 2026

### New Features
- **extreme_fe_fabric_l2**: Added `SUNI` and `TUNI` ISID types support.
- **extreme_fe_lag**: Added the `flex_uni` option, required before a LAG can be used by a `SUNI` ISID endpoint.

### Bug Fixes
- **extreme_fe_autosense**:
    - Fixed `overridden` not resetting omitted port attributes.
    - Fixed `replaced` and `overridden` silently resetting nothing.
    - Fixed `deleted` reporting `changed=True` for a port that had no overrides. On Fabric Engine 9.4 the `DELETE` endpoint returns 405 and the module falls back to a `PATCH` with default values, which was applied and reported unconditionally.
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
    - `deleted` with `config` omitted or empty now deletes every LAG on the device instead of failing. LAGs in the management VLAN or a vIST VLAN and MLAG ports are protected: they are kept with a warning and listed in `skipped_lags`. `overridden` now keeps the same protected LAGs instead of deleting them. If the VLAN or MLAG data needed to identify them cannot be read, the task fails before deleting anything.
- **extreme_fe_mlag**:
    - Added the `overridden` state. It is authoritative over RSMLT as well as peer ports, so instances absent from `config` are reset to their defaults; `replaced` remains authoritative over peer ports only.
    - Added before/after snapshot support.
- **extreme_fe_slpp**:
    - Now accepts partial config for replaced and overridden states
    - Grouped the `vlans` and `ports` lists under a single `config` dict, matching `extreme_fe_mlag`. SLPP manages two distinct resource types and a task may configure both in one run, so they are kept as separate lists rather than merged. The former top-level `vlans` and `ports` still work and emit a deprecation warning; the two forms cannot be mixed in one task.
- **extreme_fe_vlans**:
    - Fixed `overridden` not enforcing VLAN membership authoritatively, and refactored to the `config` list pattern so one task can manage several VLANs.
    - `overridden` now **deletes** VLANs absent from `config` instead of resetting them to factory defaults. VLANs 1 and 4048 are never deleted, and any VLAN the device refuses to remove — typically one still referenced by an L3 interface, SPBM ISID or RSMLT instance — is reported in `skipped_vlans` and raised as a warning rather than failing the task. Playbooks that relied on the previous reset behaviour should use `replaced`.
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
- **extreme_fe_fabric_l2**: No longer requires the `name` parameter for `state: replaced`.
- **extreme_fe_facts**: Fixed `v1→v0` API fallback.
- **extreme_fe_l2_interfaces**: Refactored to use the config-list pattern.
- **extreme_fe_stp**: Refactored to use the config-list pattern.

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
