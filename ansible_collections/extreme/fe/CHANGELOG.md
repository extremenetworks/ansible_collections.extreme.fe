# Changelog

## 1.0.0
- Initial release of the Extreme Networks Fabric Engine Ansible Collection (extreme.fe)
- Includes HTTPAPI plugin, modules, playbooks, and integration harness

### Maintenance
- Reworked internal integration test harness (templates, start/stop scripts, Docker helpers)
- Added GitHub Actions workflow to build/publish the collection to Galaxy
- Ensured packaging excludes internal tests/CI assets via build_ignore in galaxy.yml
- Removed obsolete scripts (e.g., software_install.sh) and updated documentation references
