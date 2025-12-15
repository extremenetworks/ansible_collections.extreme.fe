# extreme_fe_autosense

```yaml

---
module: extreme_fe_autosense
short_description: Manage Fabric Engine auto-sense settings and port behaviour
version_added: 1.6.0
description:
    - Manage global auto-sense settings and per-port overrides on ExtremeNetworks Fabric Engine switches using the custom ``extreme_fe`` HTTPAPI plugin.
    - Supports Fabric Attach profiles, voice and DiffServ parameters, multihost limits, onboarding defaults, and per-port auto-sense toggles and wait timers.
    - Provides a gathered mode that reports the full configuration and live auto-sense port state from ``/v0/state/autosense/ports``.
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped with this project.
    - Port identifiers must use slot:port notation such as ``1:5``.
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired module operation.
            - ``merged`` applies the provided settings as an incremental merge.
            - ``replaced`` makes the supplied values authoritative for the targeted resources.
            - ``overridden`` replaces the running configuration with the supplied values and removes entries that are not provided.
            - ``deleted`` removes the specified per-port overrides.
            - ``gathered`` returns the current configuration (and optional state payloads) without making changes.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    global_settings:
        description:
            - Global auto-sense settings applied through ``/v0/configuration/autosense``.
        type: dict
        suboptions:
            access_diffserv_enabled:
                description:
                    - Enable the access DiffServ profile for auto-sense ports.
                type: bool
            data_isid:
                description:
                    - Data I-SID assigned to auto-sense data roles. ``0`` clears the value.
                type: int
            dhcp_detection_enabled:
                description:
                    - Enable DHCP detection on auto-sense ports.
                type: bool
            dot1p_override_enabled:
                description:
                    - Enable 802.1p override for auto-sense traffic classes.
                type: bool
            dot1x_multihost:
                description:
                    - Configure 802.1X multihost client limits applied to auto-sense ports.
                type: dict
                suboptions:
                    eap_mac_max:
                        description:
                            - Maximum simultaneous EAP clients allowed when auto-sense is enabled.
                        type: int
                    mac_max:
                        description:
                            - Maximum MAC clients supported on 802.1X enabled ports.
                        type: int
                    non_eap_mac_max:
                        description:
                            - Maximum non-802.1X clients allowed on the port at one time.
                        type: int
            fabric_attach:
                description:
                    - Fabric Attach global defaults for auto-sense ports.
                type: dict
                suboptions:
                    auth_key:
                        description:
                            - Fabric Attach authentication key properties.
                        type: dict
                        suboptions:
                            is_encrypted:
                                description:
                                    - Set to true when the provided key value is already encrypted or obfuscated.
                                type: bool
                            value:
                                description:
                                    - Secret material for the Fabric Attach authentication key.
                                type: str
                    msg_auth_enabled:
                        description:
                            - Enable Fabric Attach message authentication on auto-sense ports.
                        type: bool
                    camera:
                        description:
                            - Camera role Fabric Attach settings.
                        type: dict
                        suboptions:
                            dot1x_status:
                                description:
                                    - 802.1X status for camera ports.
                                type: str
                                choices: [AUTO, FORCE_AUTHORIZED]
                            isid:
                                description:
                                    - Fabric Attach camera I-SID. ``0`` clears the association.
                                type: int
                    ovs:
                        description:
                            - Open vSwitch Fabric Attach profile.
                        type: dict
                        suboptions:
                            isid:
                                description:
                                    - Fabric Attach OVS I-SID. ``0`` clears the association.
                                type: int
                            status:
                                description:
                                    - 802.1X status for the OVS role.
                                type: str
                                choices: [AUTO, FORCE_AUTHORIZED]
                    proxy:
                        description:
                            - Fabric Attach proxy defaults.
                        type: dict
                        suboptions:
                            mgmt_cvid:
                                description:
                                    - Management CVID used for Fabric Attach proxy traffic.
                                type: int
                            mgmt_isid:
                                description:
                                    - Management I-SID used for proxy traffic. ``0`` clears the value.
                                type: int
                            no_auth_isid:
                                description:
                                    - Fabric Attach proxy I-SID used when authentication is not required.
                                type: int
                    wap_type1:
                        description:
                            - Wireless access point (type 1) Fabric Attach settings.
                        type: dict
                        suboptions:
                            isid:
                                description:
                                    - WAP I-SID. ``0`` clears the association.
                                type: int
                            status:
                                description:
                                    - 802.1X status for the WAP role.
                                type: str
                                choices: [AUTO, FORCE_AUTHORIZED]
            isis:
                description:
                    - ISIS parameters applied to auto-sense ports.
                type: dict
                suboptions:
                    hello_auth:
                        description:
                            - ISIS Hello authentication profile.
                        type: dict
                        suboptions:
                            key:
                                description:
                                    - Authentication key configuration. Value must be provided when updating the secret.
                                type: dict
                                suboptions:
                                    is_encrypted:
                                        description:
                                            - Set to true when supplying an encrypted or obfuscated secret.
                                        type: bool
                                    value:
                                        description:
                                            - Secret value for ISIS Hello authentication.
                                        type: str
                            key_id:
                                description:
                                    - ISIS Hello authentication key identifier.
                                type: int
                            type:
                                description:
                                    - Authentication type for ISIS Hello messages.
                                type: str
                                choices: [HMAC_MD5, HMAC_SHA_256, SIMPLE, NONE]
                    l1_metric:
                        description:
                            - ISIS Level-1 metric applied to auto-sense interfaces.
                        type: int
                    l1_metric_auto_enabled:
                        description:
                            - Enable automatic calculation of the ISIS Level-1 metric.
                        type: bool
            onboarding_isid:
                description:
                    - Onboarding I-SID used while auto-sense negotiations complete. ``0`` clears the value.
                type: int
            voice:
                description:
                    - Voice auto-sense profile defaults.
                type: dict
                suboptions:
                    cvid:
                        description:
                            - Voice CVID applied to auto-sense ports handling tagged voice traffic.
                        type: int
                    dot1x_lldp_auth_enabled:
                        description:
                            - Enable LLDP-based 802.1X authentication for voice endpoints.
                        type: bool
                    isid:
                        description:
                            - Voice I-SID used by auto-sense ports. ``0`` clears the association.
                        type: int
            wait_interval:
                description:
                    - Global wait interval (seconds) used by the auto-sense state machine.
                type: int
    ports:
        description:
            - Per-port auto-sense overrides applied through ``/v0/configuration/autosense/port/{port}``.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as ``1:5``).
                type: str
                required: true
            enable:
                description:
                    - Enable or disable auto-sense on the specified port.
                type: bool
            nsi:
                description:
                    - Network service identifier (I-SID). ``0`` clears the association.
                type: int
            wait_interval:
                description:
                    - Port-specific wait interval in seconds (overrides the global timer).
                type: int
    gather_filter:
        description:
            - Optional list of port identifiers used to limit gathered configuration and state output.
        type: list
        elements: str
    gather_state:
        description:
            - When true, include data from ``/v0/state/autosense/ports`` in the result.
        type: bool
        default: false

```