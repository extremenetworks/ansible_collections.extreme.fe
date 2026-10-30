# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage ExtremeNetworks Fabric Engine Ethernet interfaces."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_interfaces
short_description: Manage Ethernet interfaces on ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
    - Configure administrative state, global interface settings, and per-port attributes on ExtremeNetworks
      Fabric Engine switches using the custom C(extreme_fe) HTTPAPI plugin.
    - Supports enabling or disabling multiple ports, adjusting Fabric Engine global port flags, and tuning
      per-port features such as speed, duplex, Energy Efficient Ethernet, and Fabric Engine specific options.
    - Provides standard Ansible network resource states including C(merged), C(replaced), C(overridden),
      C(deleted), and C(gathered). The C(gathered) state returns the per-port configuration read from
      C(/v0/configuration/ports) under C(gathered), and the operational interface status read from the
      high-version C(/v1/state/ports) REST endpoints under C(ports_state).
author:
    - Bjorn Haas (@bhaas_extr)
notes:
    - Each port may be listed once in C(config); a port listed twice fails before any request.
    - A write that fails without an answer (a lost connection) and cannot be re-read may have been applied, so
      the task reports C(changed=true) with C(details.outcome=unknown).
    - Ports are supplied through the C(config) list. The parameter was named
      C(ports) before 1.2.1; that name still works as a deprecated alias so
      existing playbooks keep running.
    - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
    - Port names must use slot and port notation such as C(1:5).
    - Setting C(auto_negotiation) to C(false) is rejected for a port whose capabilities report an empty
      C(autoNegOffSupportedSpeedDuplexList) (for example 7520-48XT-6C copper ports), because the device cannot
      disable auto-negotiation there. The task fails before any port is modified, also in check mode.
    - Supports check mode and diff mode. Under C(--diff) the module reports the per-port configuration of the whole
      device before and after the change, including ports that C(overridden) resets to defaults; combined with
      C(--check) the reported C(after) is the state that would have been written.
    - Each port update and the global settings update is sent as one PATCH carrying every changed field. The device
      can apply part of such a request and still reject it, so on a rejected update the module re-reads the port
      (or the global settings) and reports which fields were and were not applied. The failure message names them,
      C(details) carries C(attempted_payload), C(applied_fields), C(not_applied_fields), C(status_code) and
      C(resource), and C(changed) is C(true) when any field was applied. If the re-read fails too, C(details) carries
      C(reread_error) and which fields were applied is unknown.
    - The admin state of the C(admin) ports is written with one PUT to C(/v0/configuration/ports), and C(deleted) and
      C(overridden) reset a port with one PUT of its default values. A rejected PUT is attributed the same way, the
      admin flags as C(<port>.enabled). For a reset, the fields the port already held at their default are listed in
      C(unchanged_fields) and never count as applied. A reset that C(overridden) skips with a warning still reports
      C(changed=true) when the re-read shows part of it applied.
    - A task that fails after one of its writes succeeded (the global settings PATCH, the admin PUT, a port PATCH or
      reset PUT) reports C(changed=true), whichever later request or read-back failed, and the failure message lists
      the writes already applied.
    - C(state=deleted) with neither C(config) nor C(admin) resets every port the device lists to its defaults,
      except the admin state (C(enabled)), which is left alone so a port that was shut down stays down; the global
      settings are not touched either. Protected ports
      are skipped, each with a warning naming the port and the reason, and listed in C(skipped_interfaces). They
      are the out-of-band management port (C(mgmt) or C(<slot>:mgmt), or flagged C(managementPort) in the port
      capabilities), every port that is a tagged or untagged member of a management VLAN (C(isMgmtInterface) in
      C(/v0/configuration/vlan)), and the member ports of a LAG that is a member of one (C(/v0/configuration/lag)).
      A port the device refuses to reset is skipped with a warning and listed there too.
    - C(overridden) protects the same ports when it resets the ports absent from C(config), with the same warning
      and the same C(skipped_interfaces) list. A port named in C(config) is always applied as C(replaced), protected
      or not.
    - The VLAN list, and the LAG list when a management VLAN has a LAG member, are read before anything is written,
      and only when at least one swept port would be reset (it is not at its defaults, or C(admin) names it). If
      either read fails the task fails without changing the device, also in check mode, so the management
      connection is never put at risk; list the ports in C(config) to change them instead. A management-VLAN LAG
      missing from the LAG list, or without a C(memberPorts) list (absent, not a list, or with a blank or
      non-string member name), fails the task the same way; an empty list is a memberless LAG.
    - The port capabilities (C(/v0/state/capabilities/system/ports)), which flag C(managementPort), are read at
      the same point. On firmware without that endpoint (HTTP 404) the management port is identified by its name
      only, with a warning. Any other failure of that read fails the task the same way, without changing the
      device.
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired module operation.
            - C(merged) applies the supplied interface changes incrementally without removing unspecified configuration.
            - C(replaced) treats the supplied values as authoritative for the targeted interfaces.
            - C(merged) and C(replaced) fail before any request when C(config), C(global_settings) and C(admin) are
              all omitted or empty. A task that sets only C(global_settings) or only C(admin) is valid.
            - C(overridden) enforces the supplied definitions and clears interface overrides that are not provided.
              Protected ports absent from C(config) are not reset (see the notes). It fails before any request when
              C(config) is omitted or empty, because it would otherwise reset every unprotected port.
            - C(deleted) removes the supplied interface configuration, disabling the listed settings and port overrides.
              With neither C(config) nor C(admin) it resets every port to its defaults, except the admin state and
              the protected ports described in the notes.
            - C(gathered) returns the per-port configuration and the operational interface state without
              applying changes.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    global_settings:
        description:
            - Fabric Engine global port settings to apply.
        type: dict
        suboptions:
            flow_control_mode:
                description:
                    - Enable or disable the Fabric Engine global flow control flag.
                type: bool
            advanced_feature_bandwidth_reservation:
                description:
                    - Reserve loopback bandwidth for advanced features (Fabric Engine only).
                type: str
                choices: [DISABLE, LOW, HIGH, VIM]
    admin:
        description:
            - Administrative enable/disable operations to apply across ports using the bulk C(/configuration/ports)
              endpoint.
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as C(1:5)).
                type: str
                required: true
            enabled:
                description:
                    - Desired administrative status for the interface.
                type: bool
                required: true
    config:
        aliases:
            - ports
        description:
            - Per-port configuration settings applied through C(/configuration/ports/{port}).
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as C(1:5)).
                type: str
                required: true
            enabled:
                description:
                    - Administrative status for the port.
                type: bool
            description:
                description:
                    - Textual description for the interface (max 255 characters).
                type: str
            speed:
                description:
                    - Operational speed override when auto-negotiation is disabled.
                    - C(AUTO) is a VIM speed (VIM-4YE, VIM-6YE ports), not "negotiate the speed"; Fabric Engine refuses
                      it on any other port. To let a regular port negotiate its speed, use C(auto_negotiation=true)
                      (optionally with C(auto_advertisements)). C(speed=AUTO) fails before anything is written on a
                      port whose capabilities (C(/v0/state/capabilities/system/ports)) report C(vimPort=false); the
                      check is skipped when the capabilities cannot be read, and a refusal then names the likely
                      cause.
                type: str
                choices: [0M, 10M, 100M, 1G, 2.5G, 5G, 10G, 20G, 25G, 40G, 50G, 100G, 400G, AUTO]
            duplex:
                description:
                    - Duplex setting when auto-negotiation is disabled.
                type: str
                choices: [HALF_DUPLEX, FULL_DUPLEX, NONE]
            auto_negotiation:
                description:
                    - Toggle auto-negotiation for the interface.
                    - Disabling auto-negotiation (C(false)) fails, before anything is written, on ports whose
                      capabilities (C(/v0/state/capabilities/system/ports)) list no supported speed/duplex
                      combination for auto-negotiation off, for example the 10GBASE-T front-panel copper ports of
                      the 7520-48XT-6C. The device would accept the request with HTTP 204 and silently keep
                      auto-negotiation enabled. The check is skipped when the capabilities cannot be read.
                type: bool
            auto_advertisements:
                description:
                    - Authoritative list of auto-negotiation advertisements.
                type: list
                elements: str
                choices:
                    - NONE
                    - 10-HALF
                    - 10-FULL
                    - 100-HALF
                    - 100-FULL
                    - 1000-HALF
                    - 1000-FULL
                    - 2500-FULL
                    - 5000-FULL
                    - 10000-HALF
                    - 10000-FULL
                    - 25000-HALF
                    - 25000-FULL
                    - 40000-FULL
                    - 50000-FULL
                    - 100000-FULL
                    - 400000-FULL
            flow_control:
                description:
                    - Interface level flow control mode (when global flow control is enabled).
                    - When omitted, C(replaced) and C(overridden) reset it to DISABLE, except on a port whose current
                      mode is not one of the choices (for example RX_ENABLE or PFC_ENABLE), which keeps its mode.
                type: str
                choices: [ENABLE, DISABLE]
            debounce_timer:
                description:
                    - Debounce timer value in milliseconds (0-300000).
                type: int
            channelized:
                description:
                    - Enable or disable channelization on supported Fabric Engine fiber ports.
                type: bool
            fec:
                description:
                    - Forward error correction mode.
                type: str
                choices: [NONE, CLAUSE_74, CLAUSE_91_108, AUTO]
            eee:
                description:
                    - Enable or disable Energy Efficient Ethernet.
                type: bool
            port_mode:
                description:
                    - Enable Fabric Engine tagging mode on the port (true indicates trunk behaviour).
                type: bool
            flex_uni:
                description:
                    - Enable or disable Fabric Engine Flex UNI mode on the port.
                    - Device default is false; if omitted the existing setting is left unchanged, and C(state=deleted)
                      resets it to the device default (false).
                type: bool
                version_added: "1.1.0"
            native_vlan:
                description:
                    - Native VLAN identifier for trunk ports. Valid VLAN IDs are 1-4094.
                    - "C(0) is accepted for backwards compatibility but is currently a
                      no-op. The device rejects every value the module could use to clear
                      the assignment - C(0) with HTTP 422, JSON null with 'None is not of
                      type integer', and C(1) unless the port is already a member of
                      VLAN 1 - so the field is omitted from the request instead. Clearing
                      a native VLAN requires the port to be a member of VLAN 1 and has no
                      REST equivalent."
                    - "Not reset by C(replaced) or C(overridden) for the same reason: an
                      omitted C(native_vlan) leaves the current assignment in place."
                    - "C(deleted) cannot clear it either. The reset payload drops fields
                      whose factory default is null, because the device rejects a typed
                      null, so C(nativeVlan) is never sent and the port keeps its current
                      native VLAN. Removing a native VLAN has to be done from the CLI."
                    - Any other value outside 1-4094 is rejected before the request is sent.
                type: int
            ip_arp_inspection_trusted:
                description:
                    - Mark the interface as trusted for ARP inspection.
                type: bool
    gather_filter:
        description:
            - Limit the C(gathered) configuration and the C(ports_state) operational state to these port names.
        type: list
        elements: str
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc:

# =========================================================================
# Full playbook examples with prerequisites:
# To create a complete playbook, uncomment the lines starting with:
#   '# - name:', '# hosts:', '# gather_facts:', and '# tasks:'
# After uncommenting, realign indentation to conform to YAML format
# (playbook level at col 0, tasks indented under tasks:)
# =========================================================================
#
# Prerequisites:
#
# ## Disable link-debounce on target ports (required before disabling ports)
# # interface gigabitEthernet 1/5-1/10
# #   no link-debounce
# # exit
#
# ## Disable Autosense on target ports (required before manual configuration)
# # autosense
# #   no enable port 1/5,1/6,1/7,1/8,1/9,1/10
# # exit
#
# ## Enable flow-control-mode boot flag (if using flow_control option)
# # boot config flags flow-control-mode
#
# ## Verify Configuration
# # show autosense status
# # show interfaces gigabitEthernet config 1/5-1/10

# -------------------------------------------------------------------------
# Task 1: Disable multiple ports using merged state
# Description:
#   - Administratively disable a range of ports
#   - 'merged' state is non-destructive (only modifies specified attributes)
# Prerequisites:
#   - Link debounce must be disabled on target ports
# -------------------------------------------------------------------------
# - name: "Task 1: Disable ports 1:5 through 1:10 using merged state"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Disable selected ports
  extreme.fe.extreme_fe_interfaces:
    state: merged
    admin:
      - name: "1:5"
        enabled: false
      - name: "1:6"
        enabled: false
      - name: "1:7"
        enabled: false
      - name: "1:8"
        enabled: false
      - name: "1:9"
        enabled: false
      - name: "1:10"
        enabled: false

# -------------------------------------------------------------------------
# Task 2: Replace interface configuration
# Description:
#   - Enforce specific interface settings using 'replaced' state
#   - All attributes set exactly as defined
# Prerequisites:
#   - Port must be a member of native_vlan (if specified)
#   - flow-control-mode boot flag enabled (if using flow_control)
# -------------------------------------------------------------------------
# - name: "Task 2: Replace configuration for ports 1:5 and 1:6"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Tune interface attributes
  extreme.fe.extreme_fe_interfaces:
    state: replaced
    config:
      - name: "1:5"
        description: Server uplink
        auto_negotiation: false
        speed: 100M
        duplex: FULL_DUPLEX
        flow_control: DISABLE
        ip_arp_inspection_trusted: true
        port_mode: true
        native_vlan: 200
      - name: "1:6"
        description: Backup uplink
        auto_negotiation: true
        flow_control: ENABLE
        flex_uni: false

# -------------------------------------------------------------------------
# Task 3: Delete interface configuration overrides
# Description:
#   - Remove custom interface configurations using 'deleted' state
#   - Resets ports to default settings
# Prerequisites:
#   - Target ports must not be Autosense enabled
# -------------------------------------------------------------------------
# - name: "Task 3: Remove interface overrides for ports 1:5 and 1:6"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Clear configuration
  extreme.fe.extreme_fe_interfaces:
    state: deleted
    config:
      - name: "1:5"
      - name: "1:6"

# -------------------------------------------------------------------------
# Task 4: Reset all interfaces except protected
# Description:
#   - 'deleted' without 'config' (and without 'admin') resets every port
#   - The out-of-band management port and the ports carrying a management
#     VLAN are skipped with a warning and listed in 'skipped_interfaces'
# -------------------------------------------------------------------------
# - name: "Task 4: Reset all interfaces except protected"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Reset all interfaces except protected
  extreme.fe.extreme_fe_interfaces:
    state: deleted
  register: reset_all
"""

RETURN = r"""
---
changed:
    description: Indicates whether any changes were made.
    returned: always
    type: bool
before:
    description:
        - Per-port configuration on the device before the task ran.
        - Captured for every state except C(gathered).
        - Built from the bulk ports endpoint, which can leave out fields it
          considers unset - C(description) is the usual one. Ports named in
          C(config) are re-read individually first, so they carry the full
          field set; for the rest of the switch a missing field means the
          bulk listing did not report it, not that the port has no value for
          it.
    returned: when state is not gathered
    type: list
    elements: dict
after:
    description:
        - Per-port configuration on the device after the task ran.
        - After a real change it is re-read from the device, so it reflects what
          the device actually applied rather than what was requested.
        - In check mode it is the predicted state - the ports that would be
          written, and the ports C(overridden) or C(deleted) would reset, carry
          their new values. When nothing changed it equals C(before).
        - Built the same way as C(before), including the individual re-read of
          the ports named in C(config), so the two snapshots carry the same
          field set and diffing them is meaningful.
    returned: when state is not gathered
    type: list
    elements: dict
global_settings:
    description: Resulting global port configuration after applying changes.
    returned: when state in [merged, replaced, overridden] and global settings requested
    type: dict
admin_updates:
    description: Ports whose administrative status was changed during execution.
    returned: when state in [merged, replaced, overridden, deleted] and admin operations provided
    type: list
    elements: dict
port_updates:
    description: Ports whose per-port attributes were modified.
    returned: when state in [merged, replaced, overridden] and per-port operations provided
    type: list
    elements: dict
port_removals:
    description: Ports whose interface overrides were removed during execution.
    returned: when state in [overridden, deleted]
    type: list
    elements: dict
skipped_interfaces:
    description:
        - Ports that the reset sweep of C(state=overridden) (the ports absent from C(config)) or of
          C(state=deleted) without C(config) and C(admin) (every port) did not reset, sorted by name. Each one
          is also named in a warning with the reason.
        - The protected ports (the out-of-band management port, the members of a management VLAN and the
          member ports of a LAG in one) and any port the device refused to reset.
    returned: when state is overridden, or deleted and neither config nor admin is given
    type: list
    elements: str
    sample: ["1:1", "mgmt"]
gathered:
    description:
        - Per-port configuration read from C(/v0/configuration/ports), one entry per port in the form the
          C(config) option accepts, so it can be supplied back as C(config) unchanged. Re-applying an
          unfiltered result (no C(gather_filter)) with C(merged), C(replaced) or C(overridden) changes nothing.
        - With C(gather_filter) the result lists only the selected ports. It is still safe to re-apply with
          C(merged) or C(replaced), but C(overridden) takes it as the complete port list and resets every
          unlisted port that is not protected, so re-apply a filtered result with C(overridden) only to do that.
        - Uses the keys of C(before), sorted by port name, without the fields the device does not report
          and without values outside an option's choices (for example a FEC mode the module does not
          offer). An omitted field keeps the value the port holds.
        - Ports whose bulk record lacks a field are re-read individually, so C(description) is reported.
        - The global settings and the admin state of the C(admin) option are not included.
    returned: when state == gathered
    type: list
    elements: dict
    sample:
        - name: "1:5"
          enabled: true
          description: Server uplink
          speed: 1G
          duplex: FULL_DUPLEX
          auto_negotiation: true
          auto_advertisements: [1000-FULL]
          flow_control: DISABLE
          debounce_timer: 0
          channelized: false
          eee: false
          port_mode: false
          flex_uni: false
          native_vlan: 1
          ip_arp_inspection_trusted: false
ports_state:
    description:
        - Operational interface state returned from the C(/v1/state/ports) API, as the device reports it.
        - This is not configuration and cannot be supplied back as C(config); use C(gathered) for that.
        - With C(gather_filter) each entry is the port name with its state under C(settings), without it the
          raw REST list is returned. Kept unchanged for existing playbooks.
    returned: when state == gathered
    type: list
    elements: dict
"""

import copy
import re
from collections.abc import Callable, Iterable
from typing import Any

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import http_status, is_answer_unknown_code

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# Native VLAN bounds. The OpenAPI EthernetInterface schema declares
# nativeVlan as minimum 0 / maximum 4094, but none of the values the module
# could use to clear the assignment is accepted by the device:
#   nativeVlan = 0     -> HTTP 422 "Port with name <port> is not member of
#                         VLAN ID 0"
#   nativeVlan = null  -> rejected, "None is not of type integer"
#   nativeVlan = 1     -> fails unless the port is already a member of VLAN 1
# So 0 is accepted as input and the field is OMITTED from the payload rather
# than sent -- see _normalize_port_payload(). That makes native_vlan: 0 a
# no-op today; clearing a native VLAN requires the port to be a member of
# VLAN 1 and has no clean REST equivalent.
NATIVE_VLAN_CLEAR = 0
NATIVE_VLAN_MIN = 1
NATIVE_VLAN_MAX = 4094


ARGUMENT_SPEC = {
    "state": {
        "type": "str",
        "choices": [
            STATE_MERGED,
            STATE_REPLACED,
            STATE_OVERRIDDEN,
            STATE_DELETED,
            STATE_GATHERED,
        ],
        "default": STATE_MERGED,
    },
    "global_settings": {
        "type": "dict",
        "options": {
            "flow_control_mode": {"type": "bool"},
            "advanced_feature_bandwidth_reservation": {
                "type": "str",
                "choices": ["DISABLE", "LOW", "HIGH", "VIM"],
            },
        },
    },
    "admin": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "enabled": {"type": "bool", "required": True},
        },
    },
    # Renamed from 'ports' to 'config' so every resource module in the
    # collection uses the same parameter name. The old name stays as a
    # deprecated alias, so existing playbooks keep working and Ansible
    # resolves both to module.params["config"].
    "config": {
        "type": "list",
        "elements": "dict",
        "aliases": ["ports"],
        "deprecated_aliases": [
            {"name": "ports", "version": "2.0.0", "collection_name": "extreme.fe"},
        ],
        "options": {
            "name": {"type": "str", "required": True},
            "enabled": {"type": "bool"},
            "description": {"type": "str"},
            "speed": {
                "type": "str",
                "choices": [
                    "0M",
                    "10M",
                    "100M",
                    "1G",
                    "2.5G",
                    "5G",
                    "10G",
                    "20G",
                    "25G",
                    "40G",
                    "50G",
                    "100G",
                    "400G",
                    "AUTO",
                ],
            },
            "duplex": {
                "type": "str",
                "choices": ["HALF_DUPLEX", "FULL_DUPLEX", "NONE"],
            },
            "auto_negotiation": {"type": "bool"},
            "auto_advertisements": {
                "type": "list",
                "elements": "str",
                "choices": [
                    "NONE",
                    "10-HALF",
                    "10-FULL",
                    "100-HALF",
                    "100-FULL",
                    "1000-HALF",
                    "1000-FULL",
                    "2500-FULL",
                    "5000-FULL",
                    "10000-HALF",
                    "10000-FULL",
                    "25000-HALF",
                    "25000-FULL",
                    "40000-FULL",
                    "50000-FULL",
                    "100000-FULL",
                    "400000-FULL",
                ],
            },
            "flow_control": {
                "type": "str",
                "choices": ["ENABLE", "DISABLE"],
            },
            "debounce_timer": {"type": "int"},
            "channelized": {"type": "bool"},
            "fec": {
                "type": "str",
                "choices": ["NONE", "CLAUSE_74", "CLAUSE_91_108", "AUTO"],
            },
            "eee": {"type": "bool"},
            "port_mode": {"type": "bool"},
            "flex_uni": {"type": "bool"},
            "native_vlan": {"type": "int"},
            "ip_arp_inspection_trusted": {"type": "bool"},
        },
    },
    "gather_filter": {"type": "list", "elements": "str"},
}

GLOBAL_FIELD_MAP = {
    "flow_control_mode": "flowControlMode",
    "advanced_feature_bandwidth_reservation": "advancedFeatureBandwidthReservation",
}

PORT_FIELD_MAP = {
    "enabled": "enabled",
    "description": "description",
    "speed": "speed",
    "duplex": "duplex",
    "auto_negotiation": "autoNegotiationEnabled",
    "auto_advertisements": "autoAdvertisementsList",
    "flow_control": "flowControl",
    "debounce_timer": "debounceTimer",
    "channelized": "channelized",
    "fec": "fec",
    "eee": "eee",
    "port_mode": "portMode",
    "flex_uni": "flexUni",
    "native_vlan": "nativeVlan",
    "ip_arp_inspection_trusted": "ipArpInspectionTrusted",
}

# Per-port capabilities of the device (GET). Used only to refuse disabling
# auto-negotiation on ports that cannot turn it off.
PORT_CAPABILITIES_PATH = "/v0/state/capabilities/system/ports"

# Factory defaults for ALL port attributes -- used by replaced/overridden/deleted
# to reset omitted fields. Verified via OpenAPI spec (EthernetInterface schema).
# NOTE: physical-layer fields (speed, duplex, autoAdvertisementsList, fec) are
# hardware-specific and set to None so they are NOT force-reset. Forcing them
# breaks links or errors on some hardware (e.g. autoAdvertisementsList=["NONE"]
# disables auto-negotiation and drops live links; speed=100M is rejected on 10G
# ports; fec=NONE is rejected where FEC is unsupported). Auto-negotiation
# (reset to True below) governs the actual speed/duplex/advertisement.
PORT_FULL_DEFAULTS = {
    "enabled": True,  # default: true
    "description": "",  # no explicit default; empty string clears
    "autoNegotiationEnabled": True,  # default: true
    "autoAdvertisementsList": None,  # hardware-specific; not force-reset
    "flowControl": "DISABLE",  # default: DISABLE
    "debounceTimer": 0,  # default: 0
    "channelized": False,  # default: false
    "fec": None,  # hardware-specific; not force-reset
    "eee": False,  # default: false
    "portMode": False,  # default: false
    "flexUni": False,  # default: false
    # None here means "never sent", NOT "cleared". The device rejects a typed
    # null ("None is not of type integer"), rejects 0 with HTTP 422, and
    # rejects 1 unless the port already belongs to VLAN 1 -- so no state can
    # clear a native VLAN over REST. Reset drops the field and the port keeps
    # whatever it has; clearing one has to be done from the CLI.
    "nativeVlan": None,
    "ipArpInspectionTrusted": False,  # no explicit default; false is factory
    "speed": None,  # hardware-specific; not force-reset
    "duplex": None,  # hardware-specific; not force-reset
}

# What a reset actually puts on the wire. The device rejects a typed null, so
# fields whose factory default is None are dropped and simply left alone --
# see the nativeVlan note above. Shared by the reset itself and by the
# hydration that decides whether a port needs an individual read first, so the
# two can never disagree about which fields matter.
PORT_RESET_PAYLOAD: dict[str, Any] = {key: value for key, value in PORT_FULL_DEFAULTS.items() if value is not None}
# state=deleted without config or admin leaves the admin state alone, as
# documented: resetting 'enabled' to its default would bring up every port that
# was deliberately shut down (a loop or an exposed port on a whole switch).
DELETE_ALL_RESET_PAYLOAD: dict[str, Any] = {key: value for key, value in PORT_RESET_PAYLOAD.items() if key != "enabled"}
DELETE_ALL_LEAD = "Cannot reset all interfaces"


class FeInterfacesError(Exception):
    """Base exception for interface module errors."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        changed: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        # Extra top-level fail_json keys, e.g. the 'code' of a transport error, so a
        # wrapped ConnectionError still fails with the keys it produced unwrapped.
        self.extra = extra or {}
        # Whether the device was left modified; only set where the module knows it
        # (a rejected write whose re-read shows some fields applied, or any failure
        # after an earlier write of the same task succeeded - see _WriteTracker).
        # None keeps the default fail result, which carries no 'changed' key.
        self.changed = changed

    def to_fail_kwargs(self) -> dict[str, Any]:
        data: dict[str, Any] = {"msg": to_text(self)}
        data.update(self.extra)
        if self.details:
            data["details"] = self.details
        if self.changed is not None:
            data["changed"] = self.changed
        return data


class _WriteTracker:
    """Remember which writes of this task already modified the device.

    Used as a context manager around the write phases of a task. Once a write
    has succeeded (record()), a later failure - another PATCH or PUT, or the
    read-back of the after state - must not hide that change: the failure is
    re-raised as an FeInterfacesError with changed=true, its message extended
    by the writes already applied. A ConnectionError keeps its msg and code.
    Before the first write, failures pass through untouched.
    """

    def __init__(self) -> None:
        self.done: list[str] = []

    def record(self, what: str) -> None:
        self.done.append(what)

    def __enter__(self) -> _WriteTracker:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is None or not self.done or not isinstance(exc, (ConnectionError, FeInterfacesError)):
            return False
        sentence = "The task had already changed the device before this failure: %s." % ", ".join(self.done)
        if isinstance(exc, FeInterfacesError):
            # The failing write's own attribution may have left changed unset
            # (nothing of ITS payload applied); the earlier writes still count.
            raise FeInterfacesError(
                _append_sentence(to_text(exc), sentence), details=exc.details, extra=exc.extra, changed=True
            ) from exc
        # Same fail result keys run_module() builds for a ConnectionError (msg,
        # code), plus changed=true.
        code = getattr(exc, "code", None)
        raise FeInterfacesError(_append_sentence(to_text(exc), sentence), extra={"code": code}, changed=True) from exc


def _append_sentence(message: str, sentence: str) -> str:
    """Append a sentence to an error message, adding the full stop it may lack.

    A message that already ends a sentence ('.', '!' or '?') gets no extra one.
    """
    lead = message.rstrip()
    if lead and not lead.endswith((".", "!", "?")):
        lead += "."
    return ("%s %s" % (lead, sentence)).strip()


def _normalize_port_name(raw: str) -> str:
    if not isinstance(raw, str):
        raise FeInterfacesError("Port name must be a string in slot:port format")
    value = raw.strip()
    if not value:
        raise FeInterfacesError("Port name must not be empty")
    return value


def _list_equal(first: Iterable[Any] | None, second: Iterable[Any] | None) -> bool:
    if first is None and second is None:
        return True
    if first is None or second is None:
        return False
    first_list = list(first)
    second_list = list(second)
    if len(first_list) != len(second_list):
        return False
    return sorted(first_list) == sorted(second_list)


def _bulk_record_answers(payload: dict[str, Any], settings: dict[str, Any] | None) -> bool:
    """True when the bulk record carries every key this payload compares.

    The bulk ports listing omits fields it treats as unset -- description is
    the usual one -- so a diff against it can be wrong for those fields. It is
    only wrong for keys it does not carry, though, so a port whose payload
    touches nothing missing can be diffed straight from the bulk data and
    needs no individual read.
    """
    if not settings:
        return False
    return all(key in settings for key in payload)


def _hydrate_ports(
    connection: Connection,
    current_map: dict[str, dict[str, Any]],
    entries: list[dict[str, Any]],
    state: str,
) -> None:
    """Re-read the individual ports whose bulk record is not good enough.

    Run before the before-snapshot is taken so the snapshot shows the same
    fields the diff is computed from, rather than whatever the bulk listing
    happened to include. Ports the bulk record already answers are skipped, so
    a long config list does not turn into one GET per port for no gain.
    """
    for entry in entries or []:
        name = entry.get("name")
        if name is None:
            continue
        port_name = _normalize_port_name(name)
        if state == STATE_DELETED:
            # A deleted entry is just {'name': ...}, so it builds no payload.
            # The fields that matter are the ones the reset writes, and those
            # decide both the snapshot and whether the port is already clean.
            payload = PORT_RESET_PAYLOAD
        else:
            payload = _normalize_port_payload(entry, state)
        if not payload or _bulk_record_answers(payload, current_map.get(port_name)):
            continue
        full_settings = _fetch_single_port(connection, port_name)
        if full_settings:
            current_map[port_name] = full_settings


def _already_at_defaults(
    existing_settings: dict[str, Any] | None,
    default_payload: dict[str, Any],
) -> bool:
    """True when a reset would be a no-op for this port.

    Only the fields the reset payload actually sends are compared -- fields
    dropped from it (those whose factory default is null, such as nativeVlan)
    are not reset either way, so they cannot make a difference.

    An unknown port returns False so the reset is still attempted; the caller
    handles a 404 from the device.
    """
    if not existing_settings:
        return False
    for key, default_value in default_payload.items():
        current_value = existing_settings.get(key)
        if key == "autoAdvertisementsList":
            if not _list_equal(current_value, default_value):
                return False
        elif current_value != default_value:
            return False
    return True


def get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeInterfacesError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def fetch_port_config_map(connection: Connection) -> dict[str, dict[str, Any]]:
    """GET /v0/configuration/ports -- retrieve all port settings (bulk)."""
    data = connection.send_request(None, path="/v0/configuration/ports", method="GET")
    if data is None:
        return {}
    if not isinstance(data, list):
        raise FeInterfacesError(
            "Unexpected response when retrieving port configuration",
            details={"response": data},
        )
    result: dict[str, dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        settings = item.get("settings")
        if not isinstance(settings, dict):
            settings = {}
        result[name] = settings
    return result


def _fetch_single_port(connection: Connection, port_name: str) -> dict[str, Any]:
    """GET /v0/configuration/ports/{port} -- retrieve full settings for one port.

    The per-port endpoint returns all fields including description,
    which the bulk endpoint may omit. Used for accurate diff comparison.
    """
    try:
        data = connection.send_request(None, path="/v0/configuration/ports/%s" % port_name, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return {}
        raise
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def fetch_global_config(connection: Connection) -> dict[str, Any]:
    try:
        data = connection.send_request(None, path="/v0/configuration/ports/global", method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return {}
        raise
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise FeInterfacesError(
            "Unexpected response when retrieving global port settings",
            details={"response": data},
        )
    return data


# ── Rejected-write attribution ─────────────────────────────────────────────────
# Fabric Engine can apply part of a multi-field PATCH and then answer with an
# error (seen on LAG: two fields written, HTTP 500 returned). The request shape
# is unchanged here; a failure is followed by one re-read of the resource so the
# task reports which attempted fields the device now holds. The admin-state PUT
# and the port reset PUT carry several fields too and are attributed the same way.


def _patch_value_matches(attempted: Any, current: Any) -> bool:
    """True when a read-back value equals the attempted one.

    Lists (autoAdvertisementsList) compare order-insensitively, the same way
    the diff that built the payload compares them.
    """
    if isinstance(attempted, list) and isinstance(current, list):
        return _list_equal(attempted, current)
    return bool(attempted == current)


def _split_applied_fields(attempted: dict[str, Any], current: Any, prefix: str = "") -> tuple[list[str], list[str]]:
    """Split the attempted payload into applied / not applied dotted REST key paths.

    Nested dicts are walked recursively (e.g. fabricAttach.proxy.mgmtIsid), so a
    partly written sub-object is reported field by field. A key the read-back
    does not carry counts as not applied.
    """
    applied: list[str] = []
    not_applied: list[str] = []
    current_dict = current if isinstance(current, dict) else {}
    for key, want in attempted.items():
        path = prefix + key
        have = current_dict.get(key)
        if isinstance(want, dict) and want:
            sub_applied, sub_not_applied = _split_applied_fields(want, have, path + ".")
            applied.extend(sub_applied)
            not_applied.extend(sub_not_applied)
        elif _patch_value_matches(want, have):
            applied.append(path)
        else:
            not_applied.append(path)
    return applied, not_applied


def _count_fields(attempted: dict[str, Any]) -> int:
    """Number of leaf fields in a payload, counting nested dicts field by field."""
    return sum(_count_fields(value) if isinstance(value, dict) and value else 1 for value in attempted.values())


# speed AUTO is a VIM speed (OpenAPI TransmissionSpeed): Fabric Engine refuses it
# on any other port, with no reason in the answer.
SPEED_AUTO_HINT = (
    "speed AUTO can only be set on VIM ports; use auto_negotiation: true to let the port negotiate its speed"
)


def _attribution_sentence(path: str, applied: list[str], not_applied: list[str], method: str = "PATCH") -> str:
    """Describe how far a rejected write got, from the re-read of the resource."""
    total = len(applied) + len(not_applied)
    if not applied:
        return "The device rejected the %s of %s; a re-read shows none of the %d fields was applied: %s." % (
            method,
            path,
            total,
            ", ".join(not_applied),
        )
    if not not_applied:
        return "The device rejected the %s of %s, but a re-read shows all %d fields applied: %s." % (
            method,
            path,
            total,
            ", ".join(applied),
        )
    return "The device rejected the %s of %s after applying %d of %d fields: %s; not applied: %s." % (
        method,
        path,
        len(applied),
        total,
        ", ".join(applied),
        ", ".join(not_applied),
    )


def _rejected_patch_error(
    reread: Callable[[], dict[str, Any]],
    path: str,
    payload: dict[str, Any],
    message: str,
    *,
    status_code: Any = None,
    base_details: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    method: str = "PATCH",
    before: dict[str, Any] | None = None,
    request_body: Any = None,
) -> FeInterfacesError:
    """Build the error for a rejected write, attributed by re-reading the resource.

    *reread* is the GET the module already uses for this resource. The returned
    error keeps *message* (the original failure) and appends what the re-read
    shows; details carry the attempted payload, applied_fields /
    not_applied_fields as dotted REST key paths, the status code when known and
    the resource path. changed is True when the re-read shows any field
    applied, otherwise left unset so the fail result is as before.

    *method* only names the request in the message. A PATCH carries changed
    fields only; a reset PUT also carries fields that already held their value,
    so it passes *before* (the record the request was built from): those fields
    go to unchanged_fields and never count as applied. *request_body* is the
    body as sent when it differs in shape from *payload*, which is then only the
    per-field view the re-read is compared with (the admin PUT sends a list).
    """
    details: dict[str, Any] = dict(base_details or {})
    details["attempted_payload"] = payload if request_body is None else request_body
    details["resource"] = path
    # Only an HTTP status: a lost answer's JSON-RPC code or REQUEST_NOT_SENT is not one.
    status = http_status(status_code)
    if status is not None:
        details["status_code"] = status
    compared = payload
    if before is not None:
        unchanged = [key for key, value in payload.items() if _patch_value_matches(value, before.get(key))]
        details["unchanged_fields"] = unchanged
        compared = {key: value for key, value in payload.items() if key not in unchanged}
    try:
        current = reread()
    except (ConnectionError, FeInterfacesError) as exc:
        current = None
        reread_error = to_text(exc)
    else:
        # The per-port and global readers answer {} for 404 / no body, which
        # says nothing about the fields; treat it as a failed re-read.
        reread_error = "the device returned no configuration for %s" % path
        # The readers accept any dict, but this API can answer a GET with a 2xx
        # error document. Comparing fields against it would wrongly report every
        # field as not applied, so it counts as a failed re-read too.
        embedded = _error_document(current)
        if embedded:
            current = None
            reread_error = "the re-read of %s returned an error document (%s)" % (path, embedded)
    if not current:
        details["reread_error"] = reread_error
        sentence = (
            "The device may have applied part of the %s of %s before refusing it, but re-reading the "
            "resource failed (%s), so it is unknown which of the %d attempted fields were applied."
            % (method, path, reread_error, _count_fields(compared))
        )
        # A transport failure without an HTTP status (no answer): the write may
        # have been applied, so changed is reported. An error document passes no
        # 'code' in extra, an HTTP error a numeric one.
        no_answer = extra is not None and "code" in extra and is_answer_unknown_code(extra["code"])
        if no_answer:
            details["outcome"] = "unknown"
        return FeInterfacesError(
            _append_sentence(message, sentence), details=details, extra=extra, changed=True if no_answer else None
        )
    applied, not_applied = _split_applied_fields(compared, current)
    details["applied_fields"] = applied
    details["not_applied_fields"] = not_applied
    sentence = _attribution_sentence(path, applied, not_applied, method)
    # The device gives no reason for refusing speed AUTO on a non-VIM port; name
    # the likely one (the capability check before the write is skipped when the
    # capabilities cannot be read).
    if "speed" in not_applied and compared.get("speed") == "AUTO":
        sentence = _append_sentence(sentence, SPEED_AUTO_HINT[0].upper() + SPEED_AUTO_HINT[1:] + ".")
    # Any applied field means the failed task did modify the device. changed is
    # left unset otherwise: writes that succeeded earlier in the task are added
    # by _WriteTracker, which re-raises this error with changed=true.
    return FeInterfacesError(
        _append_sentence(message, sentence), details=details, extra=extra, changed=True if applied else None
    )


def _error_document_parts(document: Any) -> tuple[bool, Any, list[Any] | None]:
    """(is an error document, its status code or None, its errors list or None).

    The status code is the errorCode, else a statusCode/code of 400 or more
    (a numeric string counts as its number); an errors-list body has none.
    """
    if not isinstance(document, dict):
        return False, None, None
    status = document.get("statusCode", document.get("code"))
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    errors = document.get("errors")
    errors = errors if isinstance(errors, list) and errors else None
    # bool is an int subclass; True is not a status code.
    is_status = isinstance(status, int) and not isinstance(status, bool) and status >= 400
    code = document.get("errorCode") or (status if is_status else None)
    return bool(code) or errors is not None, code, errors


def _error_document_code(document: Any) -> Any:
    """The status code an error document carries (see _error_document_parts), else None.

    Passed as status_code to _rejected_patch_error() for a 2xx error body, so
    details.status_code is set as it is for an HTTP error.
    """
    return _error_document_parts(document)[1]


def _error_document(document: Any) -> str | None:
    """Return a short description when *document* is an embedded error, else None.

    Fabric Engine can answer a request with a 2xx status and an error body. The
    markers are those extreme_fe_vlans, extreme_fe_l2_interfaces and
    extreme_fe_autosense recognise: a non-empty errorCode, a statusCode/code of
    400 or more, or a non-empty errors list. Used for the write responses and
    for the re-read that attributes a rejected write.
    """
    is_error, code, errors = _error_document_parts(document)
    if not is_error:
        return None
    text = document.get("errorMessage") or document.get("message") or document.get("detail")
    if not text and errors:
        text = "%d error(s) reported: %s" % (len(errors), errors)
    return "%s%s" % ("%s: " % code if code else "", text or "no message")


def _send_patch_attributed(
    connection: Connection,
    path: str,
    payload: dict[str, Any],
    reread: Callable[[], dict[str, Any]],
) -> Any:
    """PATCH *payload* to *path*; on a transport/HTTP error, fail with an attributed error.

    The request itself is exactly the single PATCH the module always sent; only
    the failure is enriched. The top-level 'code' key of the unwrapped
    ConnectionError result is kept.
    """
    try:
        return connection.send_request(payload, path=path, method="PATCH")
    except ConnectionError as exc:
        code = getattr(exc, "code", None)
        raise _rejected_patch_error(
            reread, path, payload, to_text(exc), status_code=code, extra={"code": code}
        ) from exc


def apply_global_settings(
    module: AnsibleModule,
    connection: Connection,
    desired: dict[str, Any],
    current: dict[str, Any],
    state: str,
) -> tuple[bool, dict[str, Any]]:
    if state == STATE_DELETED:
        if desired:
            raise FeInterfacesError("'global_settings' is not valid for state deleted")
        return False, current
    if not desired:
        return False, current

    payload: dict[str, Any] = {}
    for param, rest_key in GLOBAL_FIELD_MAP.items():
        value = desired.get(param)
        # An omitted suboption arrives as None (the argument spec fills every
        # key). No state resets the global settings, so it is never written:
        # sending it would PATCH the device's value to null.
        if value is None:
            continue
        if current.get(rest_key) != value:
            payload[rest_key] = value

    if not payload:
        return False, current

    if module.check_mode:
        new_config = current.copy()
        new_config.update(payload)
        return True, new_config

    # PATCH /v0/configuration/ports/global with every changed global flag at once.
    # On an error, an HTTP status or an error body, the global GET is re-read to
    # report which flags were applied.
    global_path = "/v0/configuration/ports/global"

    def _reread_global() -> dict[str, Any]:
        return fetch_global_config(connection)

    response = _send_patch_attributed(connection, global_path, payload, _reread_global)
    if _error_document(response):
        # The device's error body stays at the top of details, as for the ports.
        raise _rejected_patch_error(
            _reread_global,
            global_path,
            payload,
            "Failed to update the global interface settings",
            status_code=_error_document_code(response),
            base_details=response,
        )
    merged = current.copy()
    merged.update(payload)
    return True, merged


def apply_port_admin(
    module: AnsibleModule,
    connection: Connection,
    operations: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    state: str,
) -> tuple[bool, list[str]]:
    if not operations:
        return False, []

    updates: list[dict[str, Any]] = []
    changed_ports: list[str] = []
    for op in operations:
        port_name = _normalize_port_name(op["name"])
        desired_enabled = op.get("enabled")
        if desired_enabled is None and state == STATE_DELETED:
            desired_enabled = False
        current_enabled = None
        if port_name in current_map:
            current_enabled = current_map[port_name].get("enabled")
        if desired_enabled is None:
            continue
        if current_enabled is None or bool(current_enabled) != bool(desired_enabled):
            updates.append({"port": port_name, "enabled": bool(desired_enabled)})
            changed_ports.append(port_name)
            # reflect locally to keep downstream comparisons consistent
            current_map.setdefault(port_name, {})["enabled"] = bool(desired_enabled)

    if not updates:
        return False, []

    if module.check_mode:
        return True, changed_ports

    _send_admin_put(connection, updates)
    return True, changed_ports


def _send_admin_put(connection: Connection, updates: list[dict[str, Any]]) -> None:
    """PUT the admin-state list to /v0/configuration/ports; attribute a rejection per port.

    One request carries the enabled flag of several ports, which the device
    may apply in part. On a failure the bulk listing is re-read and each port's
    flag is reported as a dotted '<port>.enabled' path in applied_fields /
    not_applied_fields; a port missing from the listing counts as not applied.
    """
    path = "/v0/configuration/ports"
    # Per-port view of the list body, the shape the re-read is compared in.
    attempted = {update["port"]: {"enabled": update["enabled"]} for update in updates}

    def _reread_admin() -> dict[str, Any]:
        listing = fetch_port_config_map(connection)
        if not listing:
            # No body at all says nothing about the flags: a failed re-read.
            return {}
        # Every attempted port stays in the map, an absent one with no
        # settings, so it is reported in not_applied_fields even when no
        # attempted port is listed.
        return {name: listing.get(name, {}) for name in attempted}

    try:
        response = connection.send_request(updates, path=path, method="PUT")
    except ConnectionError as exc:
        code = getattr(exc, "code", None)
        raise _rejected_patch_error(
            _reread_admin,
            path,
            attempted,
            to_text(exc),
            status_code=code,
            extra={"code": code},
            method="PUT",
            request_body=updates,
        ) from exc
    if _error_document(response):
        # The device's error body stays at the top of details, as before.
        raise _rejected_patch_error(
            _reread_admin,
            path,
            attempted,
            "Failed to update administrative state for interfaces",
            status_code=_error_document_code(response),
            base_details=response,
            method="PUT",
            request_body=updates,
        )


def _validate_native_vlan(module: AnsibleModule, ports: list[dict[str, Any]]) -> None:
    """Reject out-of-range native_vlan values before any REST call is made.

    Valid input is 0 (clear the assignment) or a real VLAN ID 1-4094.
    Catching this locally gives the user a clear message instead of an
    opaque HTTP 422 from the device.
    """
    for entry in ports or []:
        value = entry.get("native_vlan")
        # Not supplied, or the documented "clear" sentinel -- nothing to check.
        if value is None or value == NATIVE_VLAN_CLEAR:
            continue
        if value < NATIVE_VLAN_MIN or value > NATIVE_VLAN_MAX:
            module.fail_json(
                msg=(
                    "native_vlan must be {0} (clear the native VLAN assignment) "
                    "or a VLAN ID between {1} and {2}, got {3} on port '{4}'".format(
                        NATIVE_VLAN_CLEAR,
                        NATIVE_VLAN_MIN,
                        NATIVE_VLAN_MAX,
                        value,
                        entry.get("name"),
                    )
                )
            )


def _normalize_port_payload(entry: dict[str, Any], state: str) -> dict[str, Any]:
    """Build REST payload from user config entry.

    For merged: only user-supplied fields are included.
    For replaced/overridden: all PORT_FIELD_MAP fields are included,
    using PORT_FULL_DEFAULTS for omitted fields.

    Note: Ansible pre-populates all sub-options with None even when the
    user did not supply them. We detect "user supplied" via value != None.
    """
    payload: dict[str, Any] = {}
    for param, rest_key in PORT_FIELD_MAP.items():
        value = entry.get(param)
        if value is not None:
            # native_vlan=0 requests "clear". Fabric Engine has no clean clear that
            # works regardless of VLAN 1 membership (nativeVlan=0 is rejected,
            # and nativeVlan=1 fails when the port is not a member of VLAN 1),
            # so omit the field: no-op in merged, harmless on reset. Clearing
            # the native VLAN requires the port to be a member of VLAN 1.
            if param == "native_vlan" and value == 0:
                continue
            if rest_key == "autoAdvertisementsList":
                if isinstance(value, list):
                    payload[rest_key] = list(value)
            else:
                payload[rest_key] = value
        elif state in (STATE_REPLACED, STATE_OVERRIDDEN):
            # User omitted this field — reset to factory default
            default_value = PORT_FULL_DEFAULTS.get(rest_key)
            # Never send None to the API (device rejects typed null values)
            if default_value is not None:
                payload[rest_key] = default_value
    return payload


def _keep_unexpressible_values(
    payload: dict[str, Any], entry: dict[str, Any], current: dict[str, Any], state: str
) -> dict[str, Any]:
    """Drop a reset default when the port's current value is outside the option's choices.

    replaced/overridden reset an omitted field to PORT_FULL_DEFAULTS. A value the
    option cannot express (for example flowControl RX_ENABLE or PFC_ENABLE) is
    also left out of 'gathered', so resetting it would make a re-applied gathered
    result change the port. Such a value is kept unless the user names the field.
    """
    if state not in (STATE_REPLACED, STATE_OVERRIDDEN):
        return payload
    options = ARGUMENT_SPEC["config"]["options"]
    kept = dict(payload)
    for param, rest_key in PORT_FIELD_MAP.items():
        choices = options.get(param, {}).get("choices")
        current_value = current.get(rest_key)
        if (
            choices
            and entry.get(param) is None
            and rest_key in kept
            and current_value is not None
            and not _is_valid_choice(current_value, choices)
        ):
            del kept[rest_key]
    return kept


def _fetch_port_capabilities(connection: Connection) -> dict[str, dict[str, Any]]:
    """GET /v0/state/capabilities/system/ports -- map port name to its capabilities object.

    Best effort: firmware without the endpoint, a failed request or an
    unexpected payload yields an empty map so the caller simply skips its check.
    """
    try:
        data = connection.send_request(None, path=PORT_CAPABILITIES_PATH, method="GET")
    except ConnectionError:
        return {}
    if not isinstance(data, list):
        return {}
    return _capabilities_map(data)


def _capabilities_map(data: list[Any]) -> dict[str, dict[str, Any]]:
    """Map each port of a capabilities listing to its capabilities object."""
    result: dict[str, dict[str, Any]] = {}
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("port"), str):
            caps = item.get("capabilities")
            result[item["port"]] = caps if isinstance(caps, dict) else item
    return result


def _fetch_sweep_capabilities(
    module: AnsibleModule, connection: Connection, lead: str
) -> dict[str, dict[str, Any]] | None:
    """GET the port capabilities for a reset sweep's protection; any doubt fails the task.

    Unlike _fetch_port_capabilities() this read is strict, because a
    management port flagged only by managementPort would otherwise be reset.
    A 404 (HTTP, or a not-found error document) means the firmware has no
    such endpoint: the sweep continues with the management port name rule
    alone, with a warning. Any other failure - a transport or HTTP error, any
    other error document or an unexpected body - fails the task before the
    first write, also in check mode. *lead* opens the failure message.
    """
    reason = None
    extra: dict[str, Any] = {}
    try:
        data = connection.send_request(None, path=PORT_CAPABILITIES_PATH, method="GET")
    except ConnectionError as exc:
        data = None
        code = getattr(exc, "code", None)
        if code != 404:
            reason = to_text(exc)
            extra["code"] = code
    else:
        code = _error_document_code(data)
        embedded = _error_document(data)
        if embedded and str(code) != "404":
            reason = "the device returned an error document (%s)" % embedded
        elif not embedded and not isinstance(data, list):
            reason = "unexpected response %r" % (data,)
    if reason is None and str(code) == "404":
        module.warn(
            "The port capabilities (%s) are not available on this device, so the reset sweep identifies "
            "management ports by name only (mgmt or <slot>:mgmt)." % PORT_CAPABILITIES_PATH
        )
        return None
    if reason is None:
        # Strict: a record that is not {port, capabilities} cannot be trusted to
        # flag managementPort, so it fails the read instead of being dropped.
        bad = [
            item
            for item in data
            if not isinstance(item, dict)
            or not isinstance(item.get("port"), str)
            or not isinstance(item.get("capabilities", {}), dict)
        ]
        if not bad:
            return _capabilities_map(data)
        reason = "malformed capability record(s) %r" % (bad[:3],)
    raise FeInterfacesError(
        "%s: reading %s failed (%s). Nothing was changed, because without it the module cannot tell which "
        "ports are management ports." % (lead, PORT_CAPABILITIES_PATH, reason),
        details={"resource": PORT_CAPABILITIES_PATH},
        extra=extra,
    )


def _auto_neg_off_candidates(
    entries: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    state: str,
) -> list[str]:
    """Names of ports whose entry asks to disable auto-negotiation and would need a write.

    Entries requesting true (or nothing), and ports already at false, are not
    candidates. replaced/overridden only ever reset to the default (true), so
    they are candidates solely when the user explicitly supplied false.
    """
    names: list[str] = []
    for entry in entries or []:
        if entry.get("name") is None:
            continue
        payload = _normalize_port_payload(entry, state)
        if payload.get("autoNegotiationEnabled") is not False:
            continue
        port_name = _normalize_port_name(entry["name"])
        if current_map.get(port_name, {}).get("autoNegotiationEnabled") is not False:
            names.append(port_name)
    return names


def _speed_auto_candidates(
    entries: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    state: str,
) -> list[str]:
    """Names of ports whose entry sets speed AUTO and would need a write (current speed is not AUTO)."""
    names: list[str] = []
    for entry in entries or []:
        if entry.get("name") is None:
            continue
        if _normalize_port_payload(entry, state).get("speed") != "AUTO":
            continue
        port_name = _normalize_port_name(entry["name"])
        if current_map.get(port_name, {}).get("speed") != "AUTO":
            names.append(port_name)
    return names


def _validate_port_capabilities(
    connection: Connection,
    entries: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    state: str,
) -> None:
    """Refuse, before the first write, the port settings the port's capabilities rule out.

    Covers disabling auto-negotiation (_validate_auto_negotiation_off) and
    speed AUTO on a port that is not a VIM port (the device refuses it
    without a reason). The capabilities are read once, and only when a port
    needs one of the checks; a missing capabilities endpoint, port or key never
    fails the task.
    """
    auto_neg_off = _auto_neg_off_candidates(entries, current_map, state)
    speed_auto = _speed_auto_candidates(entries, current_map, state)
    if not auto_neg_off and not speed_auto:
        return
    capabilities = _fetch_port_capabilities(connection)
    _validate_auto_negotiation_off(auto_neg_off, capabilities)
    for port_name in speed_auto:
        if capabilities.get(port_name, {}).get("vimPort") is False:
            raise FeInterfacesError(
                "Port %s: %s (its capabilities report vimPort false)." % (port_name, SPEED_AUTO_HINT),
                details={"port": port_name, "speed": "AUTO"},
            )


def _validate_auto_negotiation_off(
    candidates: list[str],
    capabilities: dict[str, dict[str, Any]],
) -> None:
    """Fail up front when auto-negotiation cannot be disabled on a requested port.

    Some ports (e.g. 7520-48XT-6C copper) answer the PATCH with 204 but keep
    auto-negotiation enabled; their capabilities show an empty
    autoNegOffSupportedSpeedDuplexList. Running this before the first write
    means no port is modified by a task that cannot succeed. A missing
    capabilities endpoint, port or key never fails the task.
    """
    for port_name in candidates:
        off_list = capabilities.get(port_name, {}).get("autoNegOffSupportedSpeedDuplexList")
        if isinstance(off_list, list) and not off_list:
            raise FeInterfacesError(
                "Auto-negotiation cannot be disabled on port %s: its capabilities list no supported speed/duplex "
                "for auto-negotiation off (autoNegOffSupportedSpeedDuplexList is empty), so the device would "
                "accept the request but keep auto-negotiation enabled." % port_name,
                details={"port": port_name},
            )


def _verify_auto_negotiation_off(
    entries: list[dict[str, Any]],
    updated_ports: list[str],
    after_map: dict[str, dict[str, Any]],
    state: str,
) -> None:
    """Second line of defence: fail if a port written with auto-negotiation false still reads true.

    Uses the post-write read-back the module already performs; no extra request.
    """
    updated = set(updated_ports)
    for entry in entries or []:
        if entry.get("name") is None:
            continue
        port_name = _normalize_port_name(entry["name"])
        if port_name not in updated:
            continue
        if _normalize_port_payload(entry, state).get("autoNegotiationEnabled") is not False:
            continue
        if after_map.get(port_name, {}).get("autoNegotiationEnabled") is True:
            raise FeInterfacesError(
                "Auto-negotiation is still enabled on port %s after the update; the device accepted the request "
                "but did not disable it." % port_name,
                details={"port": port_name},
            )


def apply_port_settings(
    module: AnsibleModule,
    connection: Connection,
    ports: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    state: str,
    writes: _WriteTracker | None = None,
) -> tuple[bool, list[str]]:
    if not ports:
        return False, []

    changed_ports: list[str] = []
    for entry in ports:
        port_name = _normalize_port_name(entry["name"])
        payload = _normalize_port_payload(entry, state)
        if not payload:
            continue

        # Sub-issue D fix: use per-port GET for accurate current state.
        # The bulk endpoint may omit fields like description, causing
        # false diffs on subsequent runs. This runs in check mode too --
        # it is a read, and skipping it would leave check mode diffing
        # against the incomplete bulk data and predicting changes that a
        # real run would not make.
        #
        # _hydrate_ports() has normally already done this for the ports in
        # config, so the guard below usually short-circuits; it stays here
        # because this function is also reachable with a map that was never
        # hydrated. Ports whose bulk record carries every key the payload
        # compares are diffed from it directly, with no request at all.
        current_settings = current_map.get(port_name, {})
        if not _bulk_record_answers(payload, current_settings):
            full_settings = _fetch_single_port(connection, port_name)
            if full_settings:
                current_settings = full_settings
                current_map[port_name] = full_settings

        payload = _keep_unexpressible_values(payload, entry, current_settings, state)
        diff: dict[str, Any] = {}
        for key, desired_value in payload.items():
            if key == "autoAdvertisementsList":
                current_value = current_settings.get(key)
                if _list_equal(current_value, desired_value):
                    continue
                diff[key] = desired_value
            else:
                current_value = current_settings.get(key)
                if current_value == desired_value:
                    continue
                diff[key] = desired_value
        if not diff:
            continue
        if not module.check_mode:
            # PATCH /v0/configuration/ports/{port} with the whole field diff. On a
            # rejection (HTTP error or an error body) the per-port GET is
            # re-read so the failure names the fields the device did apply.
            port_path = "/v0/configuration/ports/%s" % port_name

            def _reread_port(name: str = port_name) -> dict[str, Any]:
                return _fetch_single_port(connection, name)

            response = _send_patch_attributed(connection, port_path, diff, _reread_port)
            if _error_document(response):
                # The device's error body stays at the top of details, as before.
                raise _rejected_patch_error(
                    _reread_port,
                    port_path,
                    diff,
                    "Failed to update interface %s" % port_name,
                    status_code=_error_document_code(response),
                    base_details=response,
                )
            if writes is not None:
                writes.record("updated port %s" % port_name)
        changed_ports.append(port_name)
        # Fold the change into the working map in check mode too, so the
        # predicted 'after' snapshot can be read from it.
        stored = current_map.setdefault(port_name, {}).copy()
        stored.update(diff)
        current_map[port_name] = stored
    if not changed_ports:
        return False, []
    return True, changed_ports


def delete_port_settings(
    module: AnsibleModule,
    connection: Connection,
    ports: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    graceful: bool = False,
    writes: _WriteTracker | None = None,
    skipped: list[str] | None = None,
    reset_payload: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Reset each listed port to PORT_RESET_PAYLOAD (or *reset_payload*); return (changed, reset ports).

    graceful skips, with a warning, a port the device refuses to reset or does
    not know; *skipped*, when given, collects those port names.
    """
    if not ports:
        return False, []

    default_payload = reset_payload if reset_payload is not None else PORT_RESET_PAYLOAD

    changed = False
    removed_ports: list[str] = []
    for entry in ports:
        if "name" not in entry:
            raise FeInterfacesError("'name' is required for state deleted (every 'config' entry)")
        port_name = _normalize_port_name(entry["name"])
        existing_settings = current_map.get(port_name)

        # A port already sitting at its defaults needs no reset. Without this
        # every run PUTs to every targeted port and reports changed, which
        # matters most for overridden -- it sweeps every port the task did
        # not list, so the cost is one PUT per port on the device.
        if _already_at_defaults(existing_settings, default_payload):
            continue

        # The bulk listing omits some fields, description among them, so a
        # port can look different purely because the data is incomplete --
        # a missing description reads as None against a default of "".
        # Confirm against the per-port endpoint before writing, unless the
        # record already carries every field the reset compares, which is the
        # case for ports _hydrate_ports() has been through. Ports that
        # already looked clean skipped out above, so this costs one GET only
        # where a PUT would otherwise have been issued.
        if existing_settings is not None and not _bulk_record_answers(default_payload, existing_settings):
            full_settings = _fetch_single_port(connection, port_name)
            if full_settings:
                if module.check_mode:
                    # Nothing was written in check mode, so the device still
                    # holds the old values. Keep what this task already changed
                    # locally (an admin change, say), or the reset would be
                    # judged against stale data and wrongly predicted as a no-op.
                    full_settings.update(existing_settings)
                existing_settings = full_settings
                current_map[port_name] = full_settings
                if _already_at_defaults(existing_settings, default_payload):
                    continue

        if module.check_mode:
            if existing_settings is not None:
                changed = True
                removed_ports.append(port_name)
                current_map.pop(port_name, None)
            continue

        try:
            response = _send_port_reset(connection, port_name, default_payload, existing_settings)
        except ConnectionError as exc:
            # _send_port_reset() lets only a 404 through unwrapped.
            if existing_settings is not None:
                # The port was in the listing when the task started, so
                # treat the reset as already done rather than failing a
                # task with nothing left to do.
                changed = True
                removed_ports.append(port_name)
                current_map.pop(port_name, None)
                continue
            # Not in the bulk listing either. That listing covers every
            # port on the device, so the name does not exist -- almost
            # always a typo. Swallowing it would let a misspelled port
            # report success while nothing was reset, and every other
            # state fails on the same bad name.
            if graceful:
                module.warn(f"Skipped reset of interface {port_name}: not found on the device")
                _drop_skipped(current_map, port_name, skipped)
                continue
            raise FeInterfacesError(
                f"Interface '{port_name}' does not exist on the device. Check the port name in 'config'."
            ) from exc
        except FeInterfacesError as exc:
            # graceful: reserved ports (e.g. Insight ports) cannot be reset;
            # skip them with a warning instead of failing the whole task. Only
            # a rejection whose re-read showed what was applied is skipped: when
            # the re-read failed (reread_error) the rejected PUT may have changed
            # the port, so the outcome is unknown and the task fails instead.
            if not graceful or exc.details.get("reread_error"):
                raise
            if _skip_rejected_reset(module, port_name, exc, writes):
                changed = True
            _drop_skipped(current_map, port_name, skipped)
            continue

        if writes is not None:
            writes.record("reset port %s" % port_name)
        if existing_settings is not None or response is not None:
            changed = True
            removed_ports.append(port_name)
        current_map.pop(port_name, None)

    return changed, removed_ports


def _drop_skipped(current_map: dict[str, dict[str, Any]], port_name: str, skipped: list[str] | None) -> None:
    """Forget a port whose reset was skipped, and note it in *skipped* when the caller collects them."""
    current_map.pop(port_name, None)
    if skipped is not None:
        skipped.append(port_name)


def _skip_rejected_reset(
    module: AnsibleModule,
    port_name: str,
    exc: FeInterfacesError,
    writes: _WriteTracker | None,
) -> bool:
    """Warn about a reset the overridden sweep skips; True when it was partly applied.

    The warning carries the attribution, and a reset the re-read shows as
    partly applied still counts as a change of the task.
    """
    module.warn(f"Skipped reset of interface {port_name}: {to_text(exc)}")
    if not exc.changed:
        return False
    if writes is not None:
        writes.record("partly reset port %s" % port_name)
    return True


def _send_port_reset(
    connection: Connection,
    port_name: str,
    payload: dict[str, Any],
    existing_settings: dict[str, Any] | None,
) -> Any:
    """PUT the reset payload to one port; attribute a rejection by re-reading the port.

    Uses PUT with default values to reset the port configuration -- DELETE is
    not supported by the API for ports. A 404 is re-raised unchanged for the
    caller to classify. Any other failure, an HTTP error or an error body,
    becomes an FeInterfacesError naming the reset fields the device now holds;
    fields the port already held before the PUT are reported as
    unchanged_fields, so they never make the failure count as a change.
    """
    path = f"/v0/configuration/ports/{port_name}"

    def _reread_port() -> dict[str, Any]:
        return _fetch_single_port(connection, port_name)

    try:
        response = connection.send_request(payload, path=path, method="PUT")
    except ConnectionError as exc:
        code = getattr(exc, "code", None)
        if code == 404:
            raise
        raise _rejected_patch_error(
            _reread_port,
            path,
            payload,
            to_text(exc),
            status_code=code,
            extra={"code": code},
            method="PUT",
            before=existing_settings or {},
        ) from exc
    embedded = _error_document(response)
    if embedded:
        # The device's own text when it gave one; an errors-list body has none.
        reason = response.get("errorMessage", response.get("errorCode")) or embedded
        # The device's error body stays at the top of details, as before.
        raise _rejected_patch_error(
            _reread_port,
            path,
            payload,
            f"Failed to reset configuration for interface {port_name}: {reason}",
            status_code=_error_document_code(response),
            base_details=response,
            method="PUT",
            before=existing_settings or {},
        )
    return response


def gather_interface_state(
    connection: Connection,
    gather_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    params: list[str] | None = gather_filter or None
    if params:
        results: list[dict[str, Any]] = []
        for raw in params:
            port_name = _normalize_port_name(raw)
            data = connection.send_request(None, path=f"/v1/state/ports/{port_name}", method="GET")
            if isinstance(data, dict):
                results.append({"name": port_name, "settings": data})
        return results

    data = connection.send_request(None, path="/v1/state/ports", method="GET")
    if data is None:
        return []
    if not isinstance(data, list):
        raise FeInterfacesError(
            "Unexpected response when retrieving interface state",
            details={"response": data},
        )
    return data


def _is_valid_choice(value: Any, choices: list[str]) -> bool:
    """True when value (or, for a list, every element) is one of the option's choices."""
    if isinstance(value, list):
        return all(item in choices for item in value)
    return value in choices


def _to_config_entry(name: str, settings: dict[str, Any]) -> dict[str, Any]:
    """One port in the shape of a config entry, for the gathered result.

    Same keys as the before/after snapshot, but only values the module accepts
    back: unreported fields (None) and values outside an option's choices (for
    example a FEC mode the module does not offer) are left out, so the entry
    passes argument validation and an omitted field keeps what the port holds.
    """
    options = ARGUMENT_SPEC["config"]["options"]
    entry: dict[str, Any] = {}
    for key, value in _to_ansible_port_output(name, settings).items():
        if value is None:
            continue
        choices = options[key].get("choices")
        if choices and not _is_valid_choice(value, choices):
            continue
        entry[key] = value
    return entry


def gather_interface_config(
    connection: Connection,
    gather_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Per-port configuration from /v0/configuration/ports, in the shape of a config entry.

    Ports whose bulk record lacks a field that replaced or overridden would
    reset are re-read individually, as the before snapshot does for the ports
    a task names, so re-applying the result compares against the full record
    and changes nothing. A filtered name the device does not list is skipped.
    """
    current_map = fetch_port_config_map(connection)
    if gather_filter:
        wanted = {_normalize_port_name(raw) for raw in gather_filter}
        current_map = {name: settings for name, settings in current_map.items() if name in wanted}
    for name, settings in current_map.items():
        if not _bulk_record_answers(PORT_RESET_PAYLOAD, settings):
            full_settings = _fetch_single_port(connection, name)
            if full_settings:
                current_map[name] = full_settings
    return [_to_config_entry(name, settings) for name, settings in sorted(current_map.items())]


def _handle_gathered(module: AnsibleModule, connection: Connection) -> dict[str, Any]:
    """Handle state=gathered: read-only, return port configuration and operational state."""
    gather_filter = module.params.get("gather_filter")
    # ports_state is the operational state this state returned before 1.3.0;
    # gathered is the configuration, in the form the config option accepts.
    ports_state = gather_interface_state(connection, gather_filter)
    gathered = gather_interface_config(connection, gather_filter)
    return {"changed": False, "gathered": gathered, "ports_state": ports_state}


def _handle_overridden_prepass(
    module: AnsibleModule,
    connection: Connection,
    desired_ports: list[dict[str, Any]],
    initial_port_names: Iterable[str],
    current_map: dict[str, dict[str, Any]],
    result: dict[str, Any],
    writes: _WriteTracker | None = None,
    protected: Iterable[str] = (),
    skipped: list[str] | None = None,
) -> list[str]:
    """Reset ports not listed in desired_ports (overridden pre-pass).

    The *protected* ports (see _sweep_protection) are left out; the ports the
    device refuses to reset are skipped with a warning and added to *skipped*.
    """
    desired_port_names = _listed_port_names(desired_ports)
    kept = set(protected)
    to_remove = [name for name in initial_port_names if name not in desired_port_names and name not in kept]
    if not to_remove:
        return []
    removal_entries = [{"name": name} for name in to_remove]
    removal_changed, removed_ports = delete_port_settings(
        module, connection, removal_entries, current_map, graceful=True, writes=writes, skipped=skipped
    )
    if removal_changed:
        result["changed"] = True
    return removed_ports


# ── Reset sweeps (overridden, deleted without config): protected ports ─────────
# The out-of-band management port and every port that carries a management VLAN
# are never reset by a sweep, so the task cannot cut the connection it runs over.
# overridden and deleted without config use the same helper, _sweep_protection().
VLAN_CONFIG_PATH = "/v0/configuration/vlan"
LAG_CONFIG_PATH = "/v0/configuration/lag"
# OpenAPI PortName: 'mgmt' or '<slot>:mgmt' is the out-of-band management port
# ('mgt0' in AP naming).
MGMT_PORT_RE = re.compile(r"^(?:\d{1,3}:)?(?:mgmt|mgt0)$", re.IGNORECASE)


def _is_delete_all(state: str, desired_ports: list[dict[str, Any]], desired_admin: list[dict[str, Any]]) -> bool:
    """True for state=deleted with neither config nor admin: reset every port."""
    return state == STATE_DELETED and not desired_ports and not desired_admin


def _listed_port_names(desired_ports: list[dict[str, Any]]) -> set[str]:
    """Normalised names of the ports named in config."""
    return {
        _normalize_port_name(entry["name"]) for entry in desired_ports if isinstance(entry, dict) and "name" in entry
    }


def _read_protection_list(connection: Connection, path: str, lead: str) -> list[dict[str, Any]]:
    """GET a list the sweep protection depends on; any doubt fails the task before a write.

    *lead* opens the failure message and says which reset could not be done.
    """
    reason = None
    extra: dict[str, Any] = {}
    try:
        data = connection.send_request(None, path=path, method="GET")
    except ConnectionError as exc:
        reason = to_text(exc)
        extra["code"] = getattr(exc, "code", None)
        data = None
    else:
        embedded = _error_document(data)
        if embedded:
            reason = "the device returned an error document (%s)" % embedded
        elif not isinstance(data, list):
            reason = "unexpected response %r" % (data,)
    if reason is None and not all(isinstance(item, dict) for item in data):
        reason = "malformed entries in the list"
    if reason is None:
        return list(data)
    raise FeInterfacesError(
        "%s: reading %s failed (%s). Nothing was changed, because without it the module cannot tell which "
        "ports carry the management VLAN." % (lead, path, reason),
        details={"resource": path},
        extra=extra,
    )


def _mgmt_vlan_members(connection: Connection, lead: str) -> dict[tuple[str, str], Any]:
    """Map (interfaceType, interfaceName) of each management VLAN member to that VLAN's id."""
    members: dict[tuple[str, str], Any] = {}
    for vlan in _read_protection_list(connection, VLAN_CONFIG_PATH, lead):
        if vlan.get("isMgmtInterface") is not True:
            continue
        for member_type, member_name in _strict_vlan_members(vlan, lead):
            members.setdefault((member_type, member_name), vlan.get("id"))
    return members


def _strict_vlan_members(vlan: dict[str, Any], lead: str) -> list[tuple[str, str]]:
    """(interfaceType, interfaceName) of every member of a management VLAN; malformed data fails the task.

    A membership list that is not a list, or a member without a type and name,
    could hide a port or LAG that carries the management path, so it fails
    before any write instead of being skipped.
    """
    result: list[tuple[str, str]] = []
    for key in ("untaggedInterfaces", "taggedInterfaces"):
        value = vlan.get(key)
        if value is None:
            continue
        ok = isinstance(value, list)
        for member in value if ok else []:
            member_type = str(member.get("interfaceType") or "").strip().upper() if isinstance(member, dict) else ""
            member_name = str(member.get("interfaceName") or "").strip() if isinstance(member, dict) else ""
            if not (member_type and member_name):
                ok = False
                break
            result.append((member_type, member_name))
        if not ok:
            raise FeInterfacesError(
                "%s: the %s of management VLAN %s are malformed (%r). Nothing was changed, because the module "
                "cannot tell which ports carry the management VLAN." % (lead, key, vlan.get("id"), value),
                details={"resource": VLAN_CONFIG_PATH},
            )
    return result


def _reset_protected(
    module: AnsibleModule, connection: Connection, port_names: Iterable[str], lead: str
) -> dict[str, str]:
    """Ports a reset sweep must not reset, each with the reason.

    The out-of-band management port (by name, or flagged managementPort in the
    capabilities, see _fetch_sweep_capabilities), the PORT members of a
    management VLAN (isMgmtInterface in /v0/configuration/vlan, tagged or
    untagged), and the member ports of a LAG that is in a management VLAN. A
    failed capabilities (other than a 404), VLAN or LAG read fails the task,
    since nothing has been written yet.
    """
    names = set(port_names)
    protected: dict[str, str] = {}
    capabilities = _fetch_sweep_capabilities(module, connection, lead)
    if capabilities is not None:
        # Every swept port needs its record, or a port flagged only by
        # managementPort could be missed (the name rule covers mgmt ports).
        unknown = sorted(name for name in names if not MGMT_PORT_RE.match(name) and name not in capabilities)
        if unknown:
            raise FeInterfacesError(
                "%s: %s has no capability record for port(s) %s. Nothing was changed, because the module cannot "
                "tell whether they are management ports." % (lead, PORT_CAPABILITIES_PATH, ", ".join(unknown)),
                details={"resource": PORT_CAPABILITIES_PATH},
            )
    for name in sorted(names):
        if MGMT_PORT_RE.match(name) or (capabilities or {}).get(name, {}).get("managementPort") is True:
            protected[name] = "out-of-band management port"
    lag_vlans: dict[str, Any] = {}
    for (member_type, member_name), vlan_id in _mgmt_vlan_members(connection, lead).items():
        if member_type == "PORT" and member_name in names:
            protected.setdefault(member_name, "member of management VLAN %s" % vlan_id)
        elif member_type == "LAG":
            lag_vlans[member_name] = vlan_id
    if not lag_vlans:
        return protected
    found: set[str] = set()
    for lag in _read_protection_list(connection, LAG_CONFIG_PATH, lead):
        lag_id = str(lag.get("lagId", "")).strip()
        if lag_id not in lag_vlans:
            continue
        members = lag.get("memberPorts")
        # A missing, non-list or blank-named member list is malformed (an empty
        # list is a memberless LAG): not counted as found, so the check below
        # fails closed instead of leaving the real member ports unprotected.
        if not isinstance(members, list) or not all(isinstance(p, str) and p.strip() for p in members):
            continue
        found.add(lag_id)
        for port in members:
            port_name = str(port).strip()
            if port_name in names:
                protected.setdefault(
                    port_name, "member port of LAG %s, which is in management VLAN %s" % (lag_id, lag_vlans[lag_id])
                )
    # Every LAG the management VLAN references must be in the LAG list, or its
    # member ports would be swept unprotected.
    missing = sorted(set(lag_vlans) - found)
    if missing:
        raise FeInterfacesError(
            "%s: the management VLAN references LAG(s) %s, which %s did not return (or returned malformed). "
            "Nothing was changed, because their member ports cannot be protected."
            % (lead, ", ".join(missing), LAG_CONFIG_PATH)
        )
    return protected


def _sweep_ports(
    state: str,
    desired_ports: list[dict[str, Any]],
    desired_admin: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
) -> tuple[list[str], str]:
    """Ports a reset sweep of this task may reset, and the lead of a protection-read failure.

    Every port for deleted without config, the ports absent from config for
    overridden, none otherwise.
    """
    if _is_delete_all(state, desired_ports, desired_admin):
        return sorted(current_map), DELETE_ALL_LEAD
    if state == STATE_OVERRIDDEN:
        listed = _listed_port_names(desired_ports)
        return sorted(name for name in current_map if name not in listed), (
            "Cannot reset the ports absent from 'config' (overridden)"
        )
    return [], ""


def _sweep_protection(
    module: AnsibleModule,
    connection: Connection,
    sweep: tuple[list[str], str],
    current_map: dict[str, dict[str, Any]],
    desired_admin: list[dict[str, Any]],
    skipped: list[str],
) -> set[str]:
    """Classify the protected ports of a reset sweep before any write; return their names.

    The protection data is read only when at least one swept port would be
    reset: it is not at its defaults in the bulk listing, or the admin list of
    the task names it. Each protected port is warned about and added to
    *skipped*. A failed protection read fails the task with nothing written.
    """
    names, lead = sweep
    admin_names = {_normalize_port_name(op["name"]) for op in desired_admin if op.get("name")}
    # The delete-all sweep (no config, no admin) does not reset 'enabled'.
    reset_payload = DELETE_ALL_RESET_PAYLOAD if lead == DELETE_ALL_LEAD else PORT_RESET_PAYLOAD
    if not any(name in admin_names or not _already_at_defaults(current_map.get(name), reset_payload) for name in names):
        return set()
    protected = _reset_protected(module, connection, names, lead)
    for name in sorted(protected):
        module.warn(f"Skipped reset of interface {name}: protected ({protected[name]})")
        skipped.append(name)
    return set(protected)


def _to_ansible_port_output(name: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Convert port settings to Ansible output format."""
    out: dict[str, Any] = {"name": name}
    for ansible_key, rest_key in PORT_FIELD_MAP.items():
        out[ansible_key] = settings.get(rest_key)
    return out


def _capture_before_snapshot(
    current_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Capture before-state snapshot from current port config map."""
    return [_to_ansible_port_output(name, settings) for name, settings in sorted(current_map.items())]


def _predict_admin(
    predicted: dict[str, dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    admin_ports: list[str],
) -> None:
    """Fold the admin changes into the predicted map.

    apply_port_admin() has already put the new enabled value into current_map.
    Ports the device does not list are skipped, so a typo cannot add a port to
    the predicted snapshot.
    """
    for port_name in admin_ports:
        if port_name in predicted and port_name in current_map:
            predicted[port_name]["enabled"] = current_map[port_name].get("enabled")


def _predict_port_updates(
    predicted: dict[str, dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    port_names: list[str],
) -> None:
    """Fold the per-port updates into the predicted map.

    apply_port_settings() leaves the merged settings of every updated port in
    current_map, in check mode as well as in a real run.
    """
    for port_name in port_names:
        if port_name in predicted and port_name in current_map:
            predicted[port_name] = copy.deepcopy(current_map[port_name])


def _predict_resets(
    predicted: dict[str, dict[str, Any]], port_names: list[str], reset_payload: dict[str, Any] | None = None
) -> None:
    """Fold the port resets (deleted state, overridden pre-pass) into the predicted map.

    A reset sends PORT_RESET_PAYLOAD (DELETE_ALL_RESET_PAYLOAD for delete-all),
    so those fields take their factory value and every field left out of it
    keeps what the port has.
    """
    for port_name in port_names:
        if port_name in predicted:
            predicted[port_name].update(reset_payload if reset_payload is not None else PORT_RESET_PAYLOAD)


def _capture_after_snapshot(
    module: AnsibleModule,
    connection: Connection,
    desired_ports: list[dict[str, Any]],
    state: str,
    changed: bool,
    port_updates: list[str],
    predicted: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the after snapshot of every port.

    After a real change the ports are re-read from the device. In check mode, or
    when nothing changed (so nothing was written), it is the predicted state,
    which equals the before snapshot when there is no change.
    """
    if not changed or module.check_mode:
        return _capture_before_snapshot(predicted)
    after_map = fetch_port_config_map(connection)
    # Hydrated the same way as 'before', so the two snapshots carry the
    # same field set and a diff between them is meaningful.
    _hydrate_ports(connection, after_map, desired_ports, state)
    # Read-back must agree with a requested auto-negotiation false.
    _verify_auto_negotiation_off(desired_ports, port_updates, after_map, state)
    return _capture_before_snapshot(after_map)


def _handle_action_states(
    module: AnsibleModule,
    connection: Connection,
    state: str,
) -> dict[str, Any]:
    """Handle merged/replaced/overridden/deleted states.

    Every device write of the task is recorded, so a failure after one of them
    succeeded reports changed=true and names the writes (see _WriteTracker).
    """
    with _WriteTracker() as writes:
        return _run_action_states(module, connection, state, writes)


def _run_action_states(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    writes: _WriteTracker,
) -> dict[str, Any]:
    """Apply the global, admin and per-port phases, recording each write in writes."""
    # Pre-flight range check -- fail before touching the device.
    _validate_native_vlan(module, module.params.get("config") or [])

    current_map = fetch_port_config_map(connection)
    current_global = fetch_global_config(connection)
    initial_port_names = set(current_map.keys())

    desired_global = module.params.get("global_settings") or {}
    desired_admin = module.params.get("admin") or []
    desired_ports = module.params.get("config") or []

    # The reset sweeps - state=deleted with neither config nor admin (every
    # port) and overridden (the ports absent from config) - skip the protected
    # ports, which are classified here, before any write. A failed
    # classification read fails the task with nothing written.
    delete_all = _is_delete_all(state, desired_ports, desired_admin)
    skipped: list[str] = []
    sweep = _sweep_ports(state, desired_ports, desired_admin, current_map)
    protected = _sweep_protection(module, connection, sweep, current_map, desired_admin, skipped)
    reset_entries = [{"name": name} for name in sweep[0] if name not in protected] if delete_all else []

    # Fill in the ports the task will write before snapshotting them, so
    # 'before' reports the same fields the diff is computed against instead of
    # showing None for anything the bulk listing left out.
    _hydrate_ports(connection, current_map, desired_ports, state)

    # Refuse disabling auto-negotiation, and speed AUTO, where the port cannot do
    # it, before any write (global, admin or port) and also in check mode.
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
        _validate_port_capabilities(connection, desired_ports, current_map, state)

    # Sub-issue F fix: capture before snapshot
    before_snapshot = _capture_before_snapshot(current_map)
    # Working copy that follows every change the task makes, so 'after' can be
    # predicted in check mode without touching the device.
    predicted = copy.deepcopy(current_map)

    result: dict[str, Any] = {"changed": False, "before": before_snapshot}

    # Global settings
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
        changed_global, merged_global = apply_global_settings(module, connection, desired_global, current_global, state)
        if changed_global:
            result["changed"] = True
            result["global_settings"] = merged_global
            # A real global PATCH succeeded (check mode wrote nothing).
            if not module.check_mode:
                writes.record("updated the global settings")
    else:
        if desired_global:
            raise FeInterfacesError("'global_settings' is not valid for state deleted")

    # Admin operations
    if desired_admin:
        admin_changed, admin_ports = apply_port_admin(module, connection, desired_admin, current_map, state)
        if admin_changed:
            result["changed"] = True
            result["admin_updates"] = admin_ports
            _predict_admin(predicted, current_map, admin_ports)
            if not module.check_mode:
                writes.record("updated the admin state of %s" % ", ".join(admin_ports))

    # Port operations
    port_removals: list[str] = []
    port_updates: list[str] = []

    if state == STATE_DELETED:
        if delete_all:
            port_changed, removed_ports = delete_port_settings(
                module,
                connection,
                reset_entries,
                current_map,
                graceful=True,
                writes=writes,
                skipped=skipped,
                reset_payload=DELETE_ALL_RESET_PAYLOAD,
            )
            result["skipped_interfaces"] = sorted(set(skipped))
        else:
            port_changed, removed_ports = delete_port_settings(
                module, connection, desired_ports, current_map, writes=writes
            )
        if port_changed:
            result["changed"] = True
        port_removals.extend(removed_ports)
        _predict_resets(predicted, removed_ports, DELETE_ALL_RESET_PAYLOAD if delete_all else None)
    else:
        port_changed, port_names = apply_port_settings(
            module, connection, desired_ports, current_map, state, writes=writes
        )
        if port_changed:
            result["changed"] = True
            port_updates.extend(port_names)
            _predict_port_updates(predicted, current_map, port_names)

        if state == STATE_OVERRIDDEN:
            removed = _handle_overridden_prepass(
                module, connection, desired_ports, initial_port_names, current_map, result, writes, protected, skipped
            )
            port_removals.extend(removed)
            _predict_resets(predicted, removed)
            result["skipped_interfaces"] = sorted(set(skipped))

    if port_updates:
        result["port_updates"] = port_updates
    if port_removals:
        result["port_removals"] = sorted(set(port_removals))

    # 'after' is always reported: re-read from the device after a real change,
    # predicted in check mode, and equal to 'before' when nothing changed.
    result["after"] = _capture_after_snapshot(
        module, connection, desired_ports, state, result["changed"], port_updates, predicted
    )

    # Diff mode (--diff): Ansible renders the before/after pair itself. It is
    # populated whether or not anything changed (identical lists render as no
    # diff) and in check mode 'after' is the predicted state. Ports that
    # overridden or deleted reset are in both snapshots, so --diff shows them.
    if module._diff:
        result["diff"] = {"before": result["before"], "after": result["after"]}

    return result


def _input_required_error(params: dict[str, Any]) -> str | None:
    """Message refusing a task with nothing to apply, or None when its input is enough.

    merged and replaced need at least one of config, global_settings and
    admin. overridden needs config, since without it the task would reset
    every unprotected port of the device.
    """
    state = params.get("state")
    if state == STATE_OVERRIDDEN and not params.get("config"):
        return "value of config parameter must not be empty for state overridden"
    global_settings = params.get("global_settings") or {}
    has_global = any(value is not None for value in global_settings.values())
    if state in (STATE_MERGED, STATE_REPLACED) and not (params.get("config") or has_global or params.get("admin")):
        return "value of config parameter must not be empty for state %s (or supply global_settings or admin)" % state
    return None


def run_module() -> None:
    """Module entry point with state dispatch."""
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    # Refuse a task with nothing to apply before any request is sent.
    input_error = _input_required_error(module.params)
    if input_error:
        module.fail_json(msg=input_error)
        return
    # A port listed twice would get two requests and keep the last one silently.
    seen: set[str] = set()
    for entry in module.params.get("config") or []:
        try:
            name = _normalize_port_name(entry["name"])
        except FeInterfacesError as exc:
            # An empty or non-string name: the module's structured failure, not a traceback.
            module.fail_json(**exc.to_fail_kwargs())
            return
        if name in seen:
            module.fail_json(msg="Port '%s' is listed more than once in 'config'; list each port once" % name)
            return
        seen.add(name)

    try:
        connection = get_connection(module)
    except FeInterfacesError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    try:
        state = module.params.get("state")
        if state == STATE_GATHERED:
            result = _handle_gathered(module, connection)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED):
            result = _handle_action_states(module, connection, state)
        else:
            raise FeInterfacesError("Unsupported state '%s'" % state)
        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeInterfacesError as exc:
        module.fail_json(**exc.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
