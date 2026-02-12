# extreme_fe_facts

```yaml

module: extreme_fe_facts
short_description: Gather facts from ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Collect state, hardware, interface, configuration, and neighbor facts from
  ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI plugin.
- Optionally gather structured network resource data for interfaces, VLANs, routing,
  and other subsystems to support idempotent automation plays.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped
  with this project.
- Targets Fabric Engine (VOSS) platforms. Resources not available on Fabric Engine are
  skipped automatically.
options:
  gather_subset:
    description:
    - List of fact subsets to collect. Use ``all`` to gather every supported subset.
      Prefix a subset with ``!`` to exclude it when ``all`` is specified.
    - Supported subsets: ``default``, ``hardware``, ``interfaces``, ``config``, ``neighbors``.
    type: list
    elements: str
    default: [default]
  gather_network_resources:
    description:
    - List of network resource names to collect. Use ``all`` to gather every supported
      resource. Resources that are unavailable on the device are ignored.
    - Supported resources: ``interfaces``, ``l2_interfaces``, ``l3_interfaces``, ``vlans``,
      ``lag_interfaces``, ``vrfs``, ``static_routes``, ``ospfv2``, ``vrrp``, ``lldp``, ``cdp``,
      ``ntp``, ``dns``, ``snmp_server``, ``syslog``, ``anycast_gateway``, ``isid``.
    type: list
    elements: str
requirements:
- ansible.netcommon

```