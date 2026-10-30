# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage Extreme Fabric Engine autosense settings."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_autosense
short_description: Manage Fabric Engine autosense settings and port behaviour
version_added: "1.0.0"
description:
    - Manage global autosense settings and per-port overrides on ExtremeNetworks Fabric Engine switches using the
      custom C(extreme_fe) HTTPAPI plugin.
    - Supports Fabric Attach profiles, voice and DiffServ parameters, multihost limits, onboarding defaults, and
      per-port autosense toggles and wait timers.
    - Provides a gathered mode that reports the full configuration and live autosense port state from
      C(/v0/state/autosense/ports).
author:
    - Bjorn Haas (@bhaas_extr)
notes:
    - Ports are supplied through the C(config) list. The parameter was named
      C(ports) before 1.2.1; that name still works as a deprecated alias.
    - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
    - Each port may be listed once in C(config); a port listed twice fails before any request.
    - A PATCH or DELETE that fails without an answer (a lost connection) and cannot be confirmed (the
      re-read fails, or the PATCH carries a key the re-read cannot compare and no other field is
      confirmed applied) may have been applied, so the task reports C(changed=true) with
      C(details.outcome=unknown). A per-port DELETE
      answered with 404 counts as done; the override was just read as present, and a DELETE resent after
      a lost answer finds it gone.
    - When the device does not report whether it implements the per-port DELETE, check mode cannot tell
      and warns; its prediction assumes the DELETE and shows the ports removed.
    - Port identifiers must use slot:port notation such as C(1:5).
    - The Fabric Attach authentication key (C(global_settings.fabric_attach.auth_key.value)) and the ISIS Hello
      authentication key (C(global_settings.isis.hello_auth.key.value)) are secrets. A supplied value is masked in
      the task invocation, and the module never returns the stored key, so C(gathered), C(global_settings),
      C(before), C(after) and C(--diff) omit C(value); C(is_encrypted) is not a secret and stays visible. The
      C(extreme_fe) HTTPAPI plugin also keeps the C(/v0/configuration/autosense) request and response bodies out
      of the C(-vvv) log and the HTTP trace file. A device error message is reported with any key value removed; a
      connection or transport failure on that endpoint is reported with its detail redacted.
    - Supports check mode and diff mode. Under C(--diff) the module reports the global settings and the per-port
      overrides of the whole device before and after the change, including the ports that C(overridden) removes;
      combined with C(--check) the reported C(after) is the state that would have been written.
    - The global settings and each port override are updated with one PATCH carrying every changed field. The device
      may apply part of such a request and still reject it, so on a rejected update the module re-reads the resource
      and reports which fields were and were not applied. The failure message names them, and C(details) holds
      C(attempted_payload) (secret key values masked), C(applied_fields), C(not_applied_fields),
      C(unverifiable_fields) (secret keys whose read-back differs, as the device may return them obscured),
      C(unchanged_fields) (already at the requested value), C(resource) and C(status_code) when known, all as dotted
      REST paths such as C(fabricAttach.proxy.mgmtIsid). The task then reports C(changed=true) when any field was
      applied. If the re-read fails as well, C(details) holds C(reread_error) and part of the payload may be applied.
    - A PATCH answered with a success status but an error document (C(errorCode), a C(statusCode) of 400 or more,
      or an C(errors) list) fails the same way, for the global settings and for a port.
    - A per-port DELETE answered that way is not taken as a removal. An embedded 405 falls back to the PATCH like an
      HTTP 405; any other error fails the task with the device's message, leaving the override as it is. Its body is reported in
      C(details) with any key value masked, and key values are removed from the failure message.
    - A task that fails after one of its writes succeeded (the global settings PATCH, a port PATCH or DELETE)
      reports C(changed=true), whichever later request failed.
    - Before removing a port override, the module reads C(/v0/state/capabilities/urls) once to learn whether the
      device implements the per-port DELETE. Where it does not (Fabric Engine 9.4 lists only GET and PATCH), the
      device lists every port, and removing an override resets the port to its factory defaults with a PATCH
      (C(enable=true), C(nsi=0), C(wait_interval=35)); a port already at those values gets no request. When the
      capabilities do not say, the first DELETE answered 405 decides for the rest of the task, and check mode then
      predicts a change for a port that already holds those values.
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired module operation.
            - C(merged) applies the provided settings as an incremental merge.
            - C(replaced) makes the supplied values authoritative for the targeted resources.
            - C(overridden) replaces the running configuration with the supplied values and removes entries that are
              not provided.
            - C(deleted) removes the specified per-port overrides, which returns each port to its factory defaults
              (autosense enabled, C(nsi) 0, C(wait_interval) 35). Without C(config) (or with an empty list) it does so
              for every port the device lists. To turn autosense off on a port, use C(merged) with C(enable=false).
            - C(gathered) returns the current configuration (and optional state payloads) without making changes.
            - C(merged) and C(replaced) fail before any request when neither C(config) nor C(global_settings) is
              supplied. Under C(merged) a C(global_settings) with no suboption set counts as not supplied, while under
              C(replaced) an empty C(global_settings) is accepted and resets the global settings.
            - C(overridden) fails before any request when C(config) is omitted or empty, because it would delete every
              per-port override. Use C(deleted) without C(config) to remove them all.
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    global_settings:
        description:
            - Global autosense settings applied through C(/v0/configuration/autosense).
            - These are device-wide and separate from the per-port overrides in
              C(config). They are only touched when a task mentions them, so a
              task that manages ports alone never rewrites them, including
              under C(replaced) and C(overridden).
            - Omit the key to leave the global settings untouched. Supply it
              with values to apply them - under C(replaced) and C(overridden)
              any field left out is reset to its factory default. Supply it as
              an empty dict to reset every global setting that has one.
            - Fields with no documented factory default are never reset and keep their device value when omitted, in
              every state. They are C(fabric_attach.auth_key), the C(dot1x_multihost) counts, C(isis.l1_metric) and
              C(wait_interval). Change the Fabric Attach authentication key only by supplying C(fabric_attach.auth_key).
            - The API takes C(fabric_attach.auth_key) (C(is_encrypted), C(value)) and C(isis.hello_auth) (C(key),
              C(key_id), C(type)) as whole objects, and the device returns a stored key only in a hashed or obscured
              form, so the module never sends a key value it read from the device. When only part of one of these
              objects is supplied, an omitted C(is_encrypted), C(key_id) or C(type) keeps its device value, but a
              change that would have to re-send the stored key fails before any write, in every state and in check
              mode. So C(fabric_attach.auth_key.is_encrypted) is changed only together with
              C(fabric_attach.auth_key.value), and C(isis.hello_auth.key.is_encrypted), C(key_id) or C(type) only
              together with C(isis.hello_auth.key.value). A partial object equal to the device is a no-op and does not
              fail. When the resulting C(isis.hello_auth.type) is NONE and no key value is supplied, the factory empty
              key is sent instead of the stored one.
            - Under C(replaced) and C(overridden) an omitted C(isis.hello_auth) is reset to its factory default
              (C(type) NONE, C(key_id) 0, empty key), while an omitted C(fabric_attach.auth_key) is left unchanged.
        type: dict
        suboptions:
            access_diffserv_enabled:
                description:
                    - Enable the access DiffServ profile for autosense ports.
                type: bool
            data_isid:
                description:
                    - Data ISID assigned to autosense data roles. C(0) clears the value.
                type: int
            dhcp_detection_enabled:
                description:
                    - Enable DHCP detection on autosense ports.
                type: bool
            dot1p_override_enabled:
                description:
                    - Enable 802.1p override for autosense traffic classes.
                type: bool
            dot1x_multihost:
                description:
                    - Configure 802.1X multihost client limits applied to autosense ports.
                type: dict
                suboptions:
                    eap_mac_max:
                        description:
                            - Maximum simultaneous EAP clients allowed when autosense is enabled.
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
                    - Fabric Attach global defaults for autosense ports.
                type: dict
                suboptions:
                    auth_key:
                        description:
                            - Fabric Attach authentication key properties.
                            - Supply C(value) to change C(is_encrypted). The stored key is never re-sent, so a change of
                              C(is_encrypted) alone fails.
                        type: dict
                        suboptions:
                            is_encrypted:
                                description:
                                    - Set to true when the provided key value is already encrypted or obfuscated.
                                type: bool
                            value:
                                description:
                                    - Secret material for the Fabric Attach authentication key.
                                    - Masked in logs and task output; never returned by the module.
                                type: str
                    msg_auth_enabled:
                        description:
                            - Enable Fabric Attach message authentication on autosense ports.
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
                                    - Fabric Attach camera ISID. C(0) clears the association.
                                type: int
                    ovs:
                        description:
                            - Open vSwitch Fabric Attach profile.
                        type: dict
                        suboptions:
                            isid:
                                description:
                                    - Fabric Attach OVS ISID. C(0) clears the association.
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
                                    - Management ISID used for proxy traffic. C(0) clears the value.
                                type: int
                            no_auth_isid:
                                description:
                                    - Fabric Attach proxy ISID used when authentication is not required.
                                type: int
                    wap_type1:
                        description:
                            - Wireless access point (type 1) Fabric Attach settings.
                        type: dict
                        suboptions:
                            isid:
                                description:
                                    - WAP ISID. C(0) clears the association.
                                type: int
                            status:
                                description:
                                    - 802.1X status for the WAP role.
                                type: str
                                choices: [AUTO, FORCE_AUTHORIZED]
            isis:
                description:
                    - ISIS parameters applied to autosense ports.
                type: dict
                suboptions:
                    hello_auth:
                        description:
                            - ISIS Hello authentication profile.
                            - Changing C(key.is_encrypted), C(key_id) or C(type) requires C(key.value), as the stored
                              key is never re-sent. The exception is a resulting C(type) of NONE, which sends the
                              factory empty key when no C(key.value) is supplied.
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
                                            - Masked in logs and task output; never returned by the module.
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
                            - ISIS Level-1 metric applied to autosense interfaces.
                        type: int
                    l1_metric_auto_enabled:
                        description:
                            - Enable automatic calculation of the ISIS Level-1 metric.
                        type: bool
            onboarding_isid:
                description:
                    - Onboarding ISID used while autosense negotiations complete. C(0) clears the value.
                type: int
            voice:
                description:
                    - Voice autosense profile defaults.
                type: dict
                suboptions:
                    cvid:
                        description:
                            - Voice CVID applied to autosense ports handling tagged voice traffic.
                        type: int
                    dot1x_lldp_auth_enabled:
                        description:
                            - Enable LLDP-based 802.1X authentication for voice endpoints.
                        type: bool
                    isid:
                        description:
                            - Voice ISID used by autosense ports. C(0) clears the association.
                        type: int
            wait_interval:
                description:
                    - Global wait interval (seconds) used by the autosense state machine.
                type: int
    config:
        aliases:
            - ports
        description:
            - Per-port autosense overrides applied through C(/v0/configuration/autosense/port/{port}).
        type: list
        elements: dict
        suboptions:
            name:
                description:
                    - Port identifier (slot:port notation such as C(1:5)).
                type: str
                required: true
            enable:
                description:
                    - Enable or disable autosense on the specified port.
                type: bool
            nsi:
                description:
                    - Network service identifier (ISID). C(0) clears the association.
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
            - When true, include data from C(/v0/state/autosense/ports) in the result.
        type: bool
        default: false
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
# ## Autosense is enabled by default on Fabric Engine switches
# ## Verify autosense status
# # show autosense
# # show interfaces gigabitEthernet autosense
#
# -------------------------------------------------------------------------
# Task 1: Merge autosense port configuration
# Description:
#   - This example demonstrates how to enable and configure autosense on
#     a specific port using the 'merged' state. The 'merged' state allows
#     non-destructive updates, adding or modifying settings without removing
#     existing configurations on other ports.
# Prerequisites:
#   - Target port must exist
# -------------------------------------------------------------------------
# - name: "Task 1: Merge autosense overrides for a single port"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enable autosense on port 1:15 with a shorter wait interval
  extreme.fe.extreme_fe_autosense:
    state: merged
    config:
      - name: "1:15"
        enable: true
        wait_interval: 15

# -------------------------------------------------------------------------
# Task 2: Replace global Fabric Attach settings
# Description:
#   - This example shows how to enforce specific global Fabric Attach and
#     voice settings using the 'replaced' state. Unlike 'merged', the
#     'replaced' state ensures the configuration matches exactly what is
#     defined, potentially removing settings not specified in the task.
# -------------------------------------------------------------------------
# - name: "Task 2: Replace global Fabric Attach defaults"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce Fabric Attach credentials and LLDP preferences
  extreme.fe.extreme_fe_autosense:
    state: replaced
    global_settings:
      fabric_attach:
        auth_key:
          is_encrypted: false
          value: "{{ fabric_attach_auth_key }}"
        msg_auth_enabled: true
      voice:
        dot1x_lldp_auth_enabled: true

# -------------------------------------------------------------------------
# Task 3: Delete autosense port overrides
# Description:
#   - This example demonstrates how to remove autosense configurations from
#     specific ports using the 'deleted' state. This resets the ports back
#     to their default autosense behavior, clearing any custom overrides.
# Prerequisites:
#   - Target ports should have autosense configured
# -------------------------------------------------------------------------
# - name: "Task 3: Remove autosense overrides from a set of ports"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Reset ports 1:5 and 1:6 to their factory autosense defaults
  extreme.fe.extreme_fe_autosense:
    state: deleted
    config:
      - name: "1:5"
      - name: "1:6"

# -------------------------------------------------------------------------
# Task 4: Gather autosense configuration and state
# Description:
#   - This example demonstrates how to retrieve the current autosense
#     configuration and live state from the switch using the 'gathered'
#     state. This is a read-only operation useful for auditing port
#     configurations or comparing settings across switches.
# -------------------------------------------------------------------------
# - name: "Task 4: Gather configuration and live autosense state"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect autosense information for ports 1:1 and 1:2
  extreme.fe.extreme_fe_autosense:
    state: gathered
    gather_state: true
    gather_filter:
      - "1:1"
      - "1:2"
  register: autosense_info
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made.
  returned: always
  type: bool
before:
  description:
    - Global settings and per-port overrides on the device before the task ran.
    - Captured for every state except C(gathered).
  returned: when state is not gathered
  type: dict
  contains:
    global_settings:
      description: Global autosense configuration, in the form O(global_settings) accepts.
      returned: always
      type: dict
    config:
      description:
        - Per-port autosense overrides, as C(config) entries (C(name), C(enable), C(nsi), C(wait_interval)), like
          C(gathered).
      returned: always
      type: list
      elements: dict
    ports:
      description:
        - The same per-port overrides in the form returned up to 1.2.1, each as C(name) plus C(settings).
        - Deprecated and will be removed in 2.0.0 - use C(config). Not part of the C(--diff) output.
      returned: always
      type: list
      elements: dict
after:
  description:
    - Global settings and per-port overrides on the device after the task ran.
    - After a real change it is re-read from the device, so it reflects what the device actually applied
      rather than what was requested.
    - In check mode it is the predicted state, that is the global settings and ports that would be written. A port
      whose override C(overridden) or C(deleted) removes is absent only where the per-port DELETE is used; where the
      device does not implement it (Fabric Engine 9.4), the port stays listed with its factory defaults
      (C(enable=true), C(nsi=0), C(wait_interval=35)), and so does the prediction. When nothing changed it equals
      C(before).
  returned: when state is not gathered
  type: dict
  contains:
    global_settings:
      description: Global autosense configuration, in the form O(global_settings) accepts.
      returned: always
      type: dict
    config:
      description:
        - Per-port autosense overrides, as C(config) entries (C(name), C(enable), C(nsi), C(wait_interval)), like
          C(gathered).
      returned: always
      type: list
      elements: dict
    ports:
      description:
        - The same per-port overrides in the form returned up to 1.2.1, each as C(name) plus C(settings).
        - Deprecated and will be removed in 2.0.0 - use C(config). Not part of the C(--diff) output.
      returned: always
      type: list
      elements: dict
global_settings:
  description: Resulting global autosense configuration after any updates (Ansible parameter names).
  returned: when state == gathered or when global settings changed/queried
  type: dict
gathered:
  description:
    - Per-port autosense overrides read from the device, for C(state=gathered).
    - Each entry has the shape of a C(config) entry (C(name), C(enable), C(nsi), C(wait_interval)), so the list
      can be applied back as C(config) without a change. The global settings are returned in C(global_settings).
  returned: when state is gathered
  type: list
  elements: dict
ports_settings:
  description:
    - List of per-port autosense settings with normalized field names, each as C(name) plus C(settings).
    - Under C(state=gathered) this form is deprecated and will be removed in 2.0.0 - use C(gathered).
  returned: when state == gathered or port settings changed/queried
  type: list
port_updates:
  description: Ports that were modified during execution.
  returned: when port settings changed
  type: list
port_removals:
  description: Ports whose overrides were removed when using C(state=deleted) or C(state=overridden).
  returned: when port overrides were cleared
  type: list
ports_state:
  description: Autosense state payload returned from C(/v0/state/autosense/ports) when requested.
  returned: when gather_state is true
  type: list
"""

import copy
from collections.abc import Iterable
from typing import Any

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import http_status, is_answer_unknown_code

ARGUMENT_SPEC: dict[str, Any] = {
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
    "global_settings": {
        "type": "dict",
        "options": {
            "access_diffserv_enabled": {"type": "bool"},
            "data_isid": {"type": "int"},
            "dhcp_detection_enabled": {"type": "bool"},
            "dot1p_override_enabled": {"type": "bool"},
            "dot1x_multihost": {
                "type": "dict",
                "options": {
                    "eap_mac_max": {"type": "int"},
                    "mac_max": {"type": "int"},
                    "non_eap_mac_max": {"type": "int"},
                },
            },
            "fabric_attach": {
                "type": "dict",
                "options": {
                    "auth_key": {
                        "type": "dict",
                        # The container is not a secret: is_encrypted must stay visible.
                        "no_log": False,
                        "options": {
                            "is_encrypted": {"type": "bool"},
                            # The key itself is the secret, so only the leaf is masked.
                            "value": {"type": "str", "no_log": True},
                        },
                    },
                    "msg_auth_enabled": {"type": "bool"},
                    "camera": {
                        "type": "dict",
                        "options": {
                            "dot1x_status": {"type": "str", "choices": ["AUTO", "FORCE_AUTHORIZED"]},
                            "isid": {"type": "int"},
                        },
                    },
                    "ovs": {
                        "type": "dict",
                        "options": {
                            "isid": {"type": "int"},
                            "status": {"type": "str", "choices": ["AUTO", "FORCE_AUTHORIZED"]},
                        },
                    },
                    "proxy": {
                        "type": "dict",
                        "options": {
                            "mgmt_cvid": {"type": "int"},
                            "mgmt_isid": {"type": "int"},
                            "no_auth_isid": {"type": "int"},
                        },
                    },
                    "wap_type1": {
                        "type": "dict",
                        "options": {
                            "isid": {"type": "int"},
                            "status": {"type": "str", "choices": ["AUTO", "FORCE_AUTHORIZED"]},
                        },
                    },
                },
            },
            "isis": {
                "type": "dict",
                "options": {
                    "hello_auth": {
                        "type": "dict",
                        "options": {
                            "key": {
                                "type": "dict",
                                # The container is not a secret: is_encrypted must stay visible.
                                "no_log": False,
                                "options": {
                                    "is_encrypted": {"type": "bool"},
                                    # The key itself is the secret, so only the leaf is masked.
                                    "value": {"type": "str", "no_log": True},
                                },
                            },
                            "key_id": {"type": "int"},
                            "type": {
                                "type": "str",
                                "choices": ["HMAC_MD5", "HMAC_SHA_256", "SIMPLE", "NONE"],
                            },
                        },
                    },
                    "l1_metric": {"type": "int"},
                    "l1_metric_auto_enabled": {"type": "bool"},
                },
            },
            "onboarding_isid": {"type": "int"},
            "voice": {
                "type": "dict",
                "options": {
                    "cvid": {"type": "int"},
                    "dot1x_lldp_auth_enabled": {"type": "bool"},
                    "isid": {"type": "int"},
                },
            },
            "wait_interval": {"type": "int"},
        },
    },
    # Renamed from 'ports' to 'config' so every resource module in the
    # collection uses the same parameter name. The old name stays as a
    # deprecated alias; Ansible resolves both to module.params["config"].
    "config": {
        "type": "list",
        "elements": "dict",
        "aliases": ["ports"],
        "deprecated_aliases": [
            {"name": "ports", "version": "2.0.0", "collection_name": "extreme.fe"},
        ],
        "options": {
            "name": {"type": "str", "required": True},
            "enable": {"type": "bool"},
            "nsi": {"type": "int"},
            "wait_interval": {"type": "int"},
        },
    },
    "gather_filter": {"type": "list", "elements": "str"},
    "gather_state": {"type": "bool", "default": False},
}


GLOBAL_SPEC: dict[str, Any] = {
    "access_diffserv_enabled": {"rest": "accessDiffservEnabled"},
    "data_isid": {"rest": "dataIsid"},
    "dhcp_detection_enabled": {"rest": "dhcpDetectionEnabled"},
    "dot1p_override_enabled": {"rest": "dot1pOverrideEnabled"},
    "dot1x_multihost": {
        "rest": "dot1xMultihost",
        "spec": {
            "eap_mac_max": {"rest": "eapMacMax"},
            "mac_max": {"rest": "macMax"},
            "non_eap_mac_max": {"rest": "nonEapMacMax"},
        },
    },
    "fabric_attach": {
        "rest": "fabricAttach",
        "spec": {
            "auth_key": {
                "rest": "authKey",
                "spec": {
                    "is_encrypted": {"rest": "isEncrypted"},
                    "value": {"rest": "value", "secret": True},
                },
            },
            "msg_auth_enabled": {"rest": "msgAuthEnabled"},
            "camera": {
                "rest": "camera",
                "spec": {
                    "dot1x_status": {"rest": "dot1xStatus"},
                    "isid": {"rest": "isid"},
                },
            },
            "ovs": {
                "rest": "ovs",
                "spec": {
                    "isid": {"rest": "isid"},
                    "status": {"rest": "status"},
                },
            },
            "proxy": {
                "rest": "proxy",
                "spec": {
                    "mgmt_cvid": {"rest": "mgmtCvid"},
                    "mgmt_isid": {"rest": "mgmtIsid"},
                    "no_auth_isid": {"rest": "noAuthIsid"},
                },
            },
            "wap_type1": {
                "rest": "wapType1",
                "spec": {
                    "isid": {"rest": "isid"},
                    "status": {"rest": "status"},
                },
            },
        },
    },
    "isis": {
        "rest": "isis",
        "spec": {
            "hello_auth": {
                "rest": "helloAuth",
                "spec": {
                    "key": {
                        "rest": "key",
                        "spec": {
                            "is_encrypted": {"rest": "isEncrypted"},
                            "value": {"rest": "value", "secret": True},
                        },
                    },
                    "key_id": {"rest": "keyId"},
                    "type": {"rest": "type"},
                },
            },
            "l1_metric": {"rest": "l1Metric"},
            "l1_metric_auto_enabled": {"rest": "l1MetricAutoEnabled"},
        },
    },
    "onboarding_isid": {"rest": "onboardingIsid"},
    "voice": {
        "rest": "voice",
        "spec": {
            "cvid": {"rest": "cvid"},
            "dot1x_lldp_auth_enabled": {"rest": "dot1xLldpAuthEnabled"},
            "isid": {"rest": "isid"},
        },
    },
    "wait_interval": {"rest": "waitInterval"},
}


PORT_FIELD_MAP: dict[str, str] = {
    "enable": "enable",
    "nsi": "nsi",
    "wait_interval": "waitInterval",
}

# Factory defaults for per-port autosense overrides -- used by replaced/overridden
# to reset omitted fields rather than requiring all fields from the user.
# Verified via device behavior: autosense is enabled by default, nsi=0 means
# cleared, wait_interval=35 is the OpenAPI default.
PORT_FULL_DEFAULTS: dict[str, Any] = {
    "enable": True,  # default: true (from OpenAPI PortAutoSenseSettings)
    "nsi": 0,  # 0 clears the ISID assignment
    "waitInterval": 35,  # default: 35 (from OpenAPI PortAutoSenseSettings)
}

# Payload that resets a port on firmware without the per-port DELETE
# (Fabric Engine 9.4: the URL capabilities list only GET and PATCH). The
# device lists every port, and a factory-default port holds exactly
# PORT_FULL_DEFAULTS (autosense on, nsi 0, wait 35; confirmed on a 7520,
# 2026-10-09), so "remove the override" means "back to those values". Until
# 1.2.x this was enable false / nsi 0, which turned autosense off instead,
# and a delete-all would have disabled it on every port.
PORT_DELETE_RESET: dict[str, Any] = dict(PORT_FULL_DEFAULTS)

# The only status that means "this firmware does not implement DELETE on the
# per-port endpoint" and so justifies the PATCH fallback.
HTTP_METHOD_NOT_ALLOWED = 405

# REST endpoints of the two resources the module PATCHes with several fields at once.
GLOBAL_CONFIG_PATH = "/v0/configuration/autosense"
PORT_CONFIG_PATH = "/v0/configuration/autosense/port/%s"
# Lists every URL of the device with its supported operations (OpenAPI Urls);
# read once, before removing a port override, to learn whether DELETE exists.
URL_CAPABILITIES_PATH = "/v0/state/capabilities/urls"

# Dotted REST paths of the secret leaves of the global payload (no_log options).
# A failed PATCH reports its attempted payload, so these are masked there, and
# their read-back is not compared strictly: the device may return the key in an
# obscured form, so a mismatch does not prove that the write was dropped.
SECRET_FIELD_PATHS = frozenset({"fabricAttach.authKey.value", "isis.helloAuth.key.value"})
SECRET_MASK = "********"
# REST objects whose 'value' member is a secret key (fabricAttach.authKey and
# isis.helloAuth.key); used to mask a device error body that echoes them.
SECRET_CONTAINER_KEYS = frozenset({"authKey", "key"})

# Factory defaults for global autosense settings -- used by replaced/overridden
# to reset omitted fields. Only includes fields with explicit OpenAPI defaults.
# Fields without defaults (dot1xMultihost counts, l1Metric, waitInterval and the
# Fabric Attach authKey) are left unchanged when omitted because device factory
# values are not documented. For authKey that is deliberate: resetting the FA
# authentication key on every replaced run would be a silent security change, and
# whether the device accepts an empty key back is unverified.
GLOBAL_FULL_DEFAULTS: dict[str, Any] = {
    "accessDiffservEnabled": True,  # default: true
    "dataIsid": 0,  # 0 means not set
    "dhcpDetectionEnabled": True,  # default: true
    "dot1pOverrideEnabled": True,  # default: true
    "onboardingIsid": 0,  # 0 means not set
    "fabricAttach": {
        "msgAuthEnabled": True,  # default: true
        "camera": {"dot1xStatus": "AUTO", "isid": 0},
        "ovs": {"isid": 0, "status": "AUTO"},
        "proxy": {"mgmtCvid": 0, "mgmtIsid": 0, "noAuthIsid": 0},
        "wapType1": {"isid": 0, "status": "AUTO"},
    },
    "isis": {
        "helloAuth": {
            "key": {"isEncrypted": False, "value": ""},
            "keyId": 0,
            "type": "NONE",
        },
    },
    "voice": {
        "cvid": 0,
        "dot1xLldpAuthEnabled": False,  # default: false
        "isid": 0,  # 0 means not set
    },
}


STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"


class FeAutosenseError(Exception):
    """Base exception for autosense module errors."""

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
        # Extra top-level fail_json keys, e.g. the 'code' of a transport error
        # that was turned into this error class.
        self.extra = extra or {}
        # Whether the device was left modified. Only set where the module knows
        # it (a rejected PATCH that a re-read shows as partly applied, or any
        # failure after an earlier write of the same task succeeded - see
        # _WriteTracker); None keeps the default fail result, which does not
        # report a change.
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
    """Remember whether this task already modified the device.

    Used as a context manager around the write phases of a task. Once a write
    has succeeded (record()), a later failure - another PATCH or DELETE, the
    405 fallback PATCH, or the re-read of the after state - must not hide that
    change: an FeAutosenseError is marked changed=true and a ConnectionError
    is turned into one with the same msg and code plus changed=true. Before
    the first write, failures pass through untouched.
    """

    def __init__(self) -> None:
        self.wrote = False

    def record(self) -> None:
        self.wrote = True

    def __enter__(self) -> _WriteTracker:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is None or not self.wrote:
            return False
        if isinstance(exc, FeAutosenseError):
            # The failing write's own attribution may have left changed unset
            # (nothing of ITS payload applied); the earlier write still counts.
            exc.changed = True
            return False
        if isinstance(exc, ConnectionError):
            # Same fail result keys run_module() builds for a ConnectionError
            # (msg, code), plus changed=true.
            code = getattr(exc, "code", None)
            raise FeAutosenseError(to_text(exc), extra={"code": code}, changed=True) from exc
        return False


def _normalize_port_name(raw: str) -> str:
    if not isinstance(raw, str):
        raise FeAutosenseError("Port name must be a string in slot:port format")
    value = raw.strip()
    if not value:
        raise FeAutosenseError("Port name must not be empty")
    return value


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _supplied_or(desired: dict[str, Any], name: str, fallback: Any) -> Any:
    """Return desired[name] when the user supplied it, else fallback.

    Ansible fills every omitted suboption with None, so desired.get(name, fallback)
    would return None and send a JSON null (for example isEncrypted: null) instead
    of keeping the current device value.
    """
    value = desired.get(name)
    return fallback if value is None else value


def _has_supplied(value: Any) -> bool:
    """Return True when a module value holds at least one supplied (non-None) leaf.

    Ansible passes an omitted suboption as None and fills every suboption of a
    supplied dict, so 'auth_key: {}' arrives as {'is_encrypted': None, 'value': None}.
    """
    if isinstance(value, dict):
        return any(_has_supplied(item) for item in value.values())
    return value is not None


def _complete_auth_key(desired_value: dict[str, Any], current_value: dict[str, Any]) -> dict[str, Any]:
    """Return a complete {isEncrypted, value} object: supplied values, else current_value's.

    The API requires both fields together. Used for fabricAttach.authKey and for
    the nested isis.helloAuth.key object, which has the same shape. A value taken
    from current_value only serves the idempotency compare: _guard_secret_values()
    refuses to send it (the device returns the stored key obscured).
    """
    return {
        "isEncrypted": _supplied_or(desired_value, "is_encrypted", current_value.get("isEncrypted", False)),
        "value": _supplied_or(desired_value, "value", current_value.get("value", "")),
    }


def _complete_hello_auth(desired_value: dict[str, Any], current_value: dict[str, Any]) -> dict[str, Any]:
    """Return a complete {key, keyId, type} object: supplied values, else current_value's.

    The API requires key, keyId and type together, and the nested key object
    requires isEncrypted and value together.
    """
    complete: dict[str, Any] = {}
    # Ansible passes an omitted 'key' suboption as None, not as a missing key.
    key_desired = desired_value.get("key") or {}
    key_current = current_value.get("key") or {}
    if key_desired or key_current:
        complete["key"] = _complete_auth_key(key_desired, key_current)
    complete["keyId"] = _supplied_or(desired_value, "key_id", current_value.get("keyId", 0))
    complete["type"] = _supplied_or(desired_value, "type", current_value.get("type", "NONE"))
    return complete


def _auth_key_differs(complete: dict[str, Any], current_value: dict[str, Any]) -> bool:
    """Return True when a completed authKey object differs from the current one."""
    return complete["isEncrypted"] != current_value.get("isEncrypted") or complete["value"] != current_value.get(
        "value"
    )


def _hello_auth_differs(complete: dict[str, Any], current_value: dict[str, Any]) -> bool:
    """Return True when a completed helloAuth object differs from the current one."""
    complete_key = complete.get("key") or {}
    current_key = current_value.get("key") or {}
    return (
        complete_key.get("isEncrypted") != current_key.get("isEncrypted")
        or complete_key.get("value") != current_key.get("value")
        or complete["keyId"] != current_value.get("keyId")
        or complete["type"] != current_value.get("type")
    )


# REST objects whose fields the API requires in one request. The value is the
# builder that completes a partially supplied object and the test that tells
# whether the completed object differs from the device.
COMPOSITE_BUILDERS: dict[str, tuple[Any, Any]] = {
    "authKey": (_complete_auth_key, _auth_key_differs),
    "helloAuth": (_complete_hello_auth, _hello_auth_differs),
}

# Dotted REST paths of those composite objects in the global payload.
GLOBAL_COMPOSITE_PATHS = ("fabricAttach.authKey", "isis.helloAuth")


def _build_diff_from_module(
    desired: dict[str, Any],
    current: dict[str, Any],
    spec: dict[str, Any],
    keep_all: bool = False,
) -> dict[str, Any]:
    """Convert module values to a REST payload.

    By default (merged) only the supplied fields that differ from current are
    returned. keep_all=True (the replaced/overridden overlay) returns every
    supplied field, even one equal to current, so it wins over the factory
    default it is merged onto. In both modes a supplied authKey/helloAuth object
    is completed with current's values for its omitted fields, as the API
    requires those fields together; an omitted key value completed this way is
    never sent (see _guard_secret_values()).
    """
    payload: dict[str, Any] = {}
    for param, mapping in spec.items():
        if param not in desired:
            continue
        rest_key = mapping["rest"]
        desired_value = desired.get(param)
        if desired_value is None:
            continue
        child_spec = mapping.get("spec")
        if child_spec:
            if not isinstance(desired_value, dict):
                raise FeAutosenseError(f"Option '{param}' must be a dictionary")
            current_value = current.get(rest_key)
            if not isinstance(current_value, dict):
                current_value = {}
            if rest_key in COMPOSITE_BUILDERS:
                # An object with no supplied field counts as not mentioned: in the
                # overlay the factory default stays authoritative for it, and in
                # merged its completion would be nothing but the device read-back.
                if not _has_supplied(desired_value):
                    continue
                complete_object, object_differs = COMPOSITE_BUILDERS[rest_key]
                complete = complete_object(desired_value, current_value)
                # Overlay: always; merged: only if anything changed. A completed
                # key value is checked by _guard_secret_values() before sending.
                if keep_all or object_differs(complete, current_value):
                    payload[rest_key] = complete
            else:
                diff_value = _build_diff_from_module(desired_value, current_value, child_spec, keep_all)
                if diff_value:
                    payload[rest_key] = diff_value
        else:
            current_value = current.get(rest_key)
            # The overlay keeps a supplied value even when it equals current.
            if keep_all or current_value != desired_value:
                payload[rest_key] = desired_value
    return payload


def _complete_global_composites(diff: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Send every composite object of a replaced/overridden diff whole.

    _diff_against_current() keeps only the leaves that differ, so a new
    authKey.value would go out without isEncrypted. When any part of a
    composite object differs, the whole target object replaces that part.
    """
    for path in GLOBAL_COMPOSITE_PATHS:
        section, _sep, name = path.partition(".")
        section_diff = diff.get(section)
        if isinstance(section_diff, dict) and name in section_diff:
            section_diff[name] = copy.deepcopy(target[section][name])
    return diff


# ── Secret key values are never re-sent ───────────────────────────────────────
# The composite builders above complete an omitted authKey/helloAuth.key value
# from the device so that the idempotency compare sees the whole object. That
# read-back must never go out: the device returns the stored key hashed or
# obscured (OpenAPI AutoSenseFaAuthSecret / AutoSenseIsisHelloAuthSecret), and
# the API has no way to change isEncrypted, keyId or type while keeping the
# stored key (isEncrypted+value and key+keyId+type are required together), so
# re-sending it would overwrite the working key with its obscured form.

# Error suffix shared by both checks.
_SECRET_NOT_RESENT = "the stored key is not readable and is never re-sent"


def _changed_names(outgoing: dict[str, Any], current: dict[str, Any], names: dict[str, str]) -> str:
    """Return 'a/b' for the option names whose REST path differs between outgoing and current.

    names maps a dotted REST path inside the composite to its option name. When
    no listed field differs (the device omits some of them), every name is listed.
    """
    changed = [name for path, name in names.items() if _lookup_dotted(outgoing, path) != _lookup_dotted(current, path)]
    return "/".join(changed or names.values())


def _guard_auth_key(diff: dict[str, Any], desired: dict[str, Any], current: dict[str, Any]) -> None:
    """Fail when an outgoing fabricAttach.authKey would carry a value the user did not supply.

    authKey has no factory default, so such a value can only come from the device.
    """
    outgoing = (diff.get("fabricAttach") or {}).get("authKey")
    if not isinstance(outgoing, dict):
        return
    desired_key = (desired.get("fabric_attach") or {}).get("auth_key") or {}
    if desired_key.get("value") is not None:
        return
    current_key = (current.get("fabricAttach") or {}).get("authKey") or {}
    changed = _changed_names(outgoing, current_key, {"isEncrypted": "is_encrypted"})
    raise FeAutosenseError(
        "global_settings.fabric_attach.auth_key: %s cannot be changed without supplying auth_key.value; %s"
        % (changed, _SECRET_NOT_RESENT)
    )


def _guard_hello_auth(diff: dict[str, Any], desired: dict[str, Any], current: dict[str, Any]) -> None:
    """Make an outgoing isis.helloAuth carry only a supplied or factory-default key value.

    Allowed without a supplied key.value: the replaced/overridden reset of an
    omitted hello_auth (the whole object is GLOBAL_FULL_DEFAULTS, empty key),
    and a resulting type NONE, whose companion is the factory empty key - the
    key is then replaced by the default one. Anything else fails.
    """
    outgoing = (diff.get("isis") or {}).get("helloAuth")
    if not isinstance(outgoing, dict):
        return
    desired_ha = (desired.get("isis") or {}).get("hello_auth") or {}
    desired_key = desired_ha.get("key") or {}
    if desired_key.get("value") is not None:
        return
    default_ha = GLOBAL_FULL_DEFAULTS["isis"]["helloAuth"]
    if not _has_supplied(desired_ha) and outgoing.get("key") == default_ha["key"]:
        # Factory reset of an omitted hello_auth: nothing of it came from the device.
        return
    if outgoing.get("type") == "NONE":
        # No authentication: send the factory empty key, never the stored one.
        default_key = default_ha["key"]
        outgoing["key"] = {
            "isEncrypted": _supplied_or(desired_key, "is_encrypted", default_key["isEncrypted"]),
            "value": default_key["value"],
        }
        return
    current_ha = (current.get("isis") or {}).get("helloAuth") or {}
    names = {"key.isEncrypted": "key.is_encrypted", "keyId": "key_id", "type": "type"}
    raise FeAutosenseError(
        "global_settings.isis.hello_auth: %s cannot be changed without supplying hello_auth.key.value; %s"
        % (_changed_names(outgoing, current_ha, names), _SECRET_NOT_RESENT)
    )


def _guard_secret_values(diff: dict[str, Any], desired: dict[str, Any], current: dict[str, Any]) -> None:
    """Check the outgoing global diff before any write, in every state and in check mode."""
    _guard_auth_key(diff, desired, current)
    _guard_hello_auth(diff, desired, current)


def _transform_for_output(payload: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for param, mapping in spec.items():
        rest_key = mapping["rest"]
        if rest_key not in payload:
            continue
        value = payload.get(rest_key)
        if value is None:
            continue
        # Secret leaves (the FA auth key and the ISIS hello key) are never returned.
        # no_log only scrubs a value the playbook supplied; on gathered, or any task
        # that does not set the key, the device's stored key would otherwise reach
        # gathered, global_settings, before/after and --diff unmasked.
        if mapping.get("secret"):
            continue
        child_spec = mapping.get("spec")
        if child_spec and isinstance(value, dict):
            child_value = _transform_for_output(value, child_spec)
            if child_value:
                result[param] = child_value
        else:
            result[param] = value
    return result


def _build_port_payload(entry: dict[str, Any], state: str) -> dict[str, Any]:
    """Build REST payload for a port entry.

    For merged: only user-supplied fields.
    For replaced/overridden: all fields, using PORT_FULL_DEFAULTS for omitted.
    """
    payload: dict[str, Any] = {}
    for param, rest_key in PORT_FIELD_MAP.items():
        # Ansible pre-populates every declared suboption, so "param in entry"
        # is always true and cannot tell a supplied value from an omitted one.
        # Only a non-None value means the user actually supplied it.
        value = entry.get(param)
        if value is not None:
            payload[rest_key] = value
        elif state in (STATE_REPLACED, STATE_OVERRIDDEN):
            # Fill omitted fields with factory defaults
            payload[rest_key] = PORT_FULL_DEFAULTS[rest_key]
    return payload


def _transform_ports_output(
    port_map: dict[str, dict[str, Any]],
    gather_filter: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    names: Iterable[str]
    if gather_filter:
        normalized = []
        for item in gather_filter:
            try:
                normalized.append(_normalize_port_name(item))
            except FeAutosenseError:
                continue
        names = normalized
    else:
        names = sorted(port_map.keys())
    result: list[dict[str, Any]] = []
    for name in names:
        settings = port_map.get(name)
        if not isinstance(settings, dict):
            continue
        transformed: dict[str, Any] = {}
        for param, rest_key in PORT_FIELD_MAP.items():
            if rest_key in settings:
                transformed[param] = settings.get(rest_key)
        result.append({"name": name, "settings": transformed})
    return result


def _ports_config_entries(
    port_map: dict[str, dict[str, Any]],
    gather_filter: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the per-port overrides as `config` entries (name next to the port fields)."""
    entries: list[dict[str, Any]] = []
    for item in _transform_ports_output(port_map, gather_filter):
        entry: dict[str, Any] = {"name": item["name"]}
        entry.update(item["settings"])
        entries.append(entry)
    return entries


def get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeAutosenseError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def fetch_autosense_config(connection: Connection) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    data = connection.send_request(None, path="/v0/configuration/autosense", method="GET")
    if data is None:
        return {}, {}
    if not isinstance(data, dict):
        raise FeAutosenseError(
            "Unexpected response when retrieving autosense configuration",
            details={"response": data},
        )
    ports_payload = data.get("ports")
    port_map: dict[str, dict[str, Any]] = {}
    if isinstance(ports_payload, list):
        for entry in ports_payload:
            if not isinstance(entry, dict):
                continue
            name = entry.get("portName")
            if not isinstance(name, str):
                continue
            settings = entry.get("portSettings")
            if isinstance(settings, dict):
                port_map[_normalize_port_name(name)] = dict(settings)
    global_payload = dict(data)
    global_payload.pop("ports", None)
    return global_payload, port_map


def _diff_against_current(target: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return only the leaves of target that differ from current, at any nesting depth.

    The device reports more keys than the module manages (for example
    fabricAttach.proxy also carries authForceEnabled and the ring management
    keys), so comparing a whole nested section against the managed subset would
    always look different and replaced/overridden would report a change on every run.
    """
    diff: dict[str, Any] = {}
    for key, desired_value in target.items():
        current_value = current.get(key)
        if isinstance(desired_value, dict) and isinstance(current_value, dict):
            sub_diff = _diff_against_current(desired_value, current_value)
            if sub_diff:
                diff[key] = sub_diff
        elif current_value != desired_value:
            diff[key] = desired_value
    return diff


# ── Rejected PATCH attribution ────────────────────────────────────────────────
# Fabric Engine can apply part of a multi-field PATCH and still answer with an
# error. The helpers below re-read the resource after such
# a failure and report which fields of the attempted payload the device holds.


def _payload_leaves(payload: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Return (dotted REST path, value) for every leaf of a nested payload."""
    leaves: list[tuple[str, Any]] = []
    for key, value in payload.items():
        path = prefix + key
        # A non-empty dict is a section (fabricAttach.proxy...); recurse into it.
        if isinstance(value, dict) and value:
            leaves.extend(_payload_leaves(value, path + "."))
        else:
            leaves.append((path, value))
    return leaves


def _lookup_dotted(data: Any, path: str) -> Any:
    """Return the value at a dotted REST path, or None when any level is missing."""
    for key in path.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _mask_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the payload with the secret leaves replaced by SECRET_MASK."""
    masked = copy.deepcopy(payload)
    for path in SECRET_FIELD_PATHS:
        parent_path, _sep, leaf = path.rpartition(".")
        parent = _lookup_dotted(masked, parent_path)
        if isinstance(parent, dict) and leaf in parent:
            parent[leaf] = SECRET_MASK
    return masked


def _secret_strings(*payloads: dict[str, Any]) -> list[str]:
    """Return the non-empty secret key values held by the given REST payloads.

    A device error can echo the stored key (held by the before state), which
    the playbook did not supply and no_log does not know about, so these are
    scrubbed explicitly. Longest first, so a secret that contains another one
    is replaced whole.
    """
    secrets = set()
    for payload in payloads:
        for path in SECRET_FIELD_PATHS:
            value = _lookup_dotted(payload, path)
            if isinstance(value, str) and value:
                secrets.add(value)
    return sorted(secrets, key=len, reverse=True)


def _scrub_text(text: str, secrets: list[str]) -> str:
    """Replace every occurrence of a secret string in text with SECRET_MASK."""
    for secret in secrets:
        text = text.replace(secret, SECRET_MASK)
    return text


def _sanitize_body(data: Any, secrets: list[str], parent_key: str | None = None) -> Any:
    """Return a copy of a device response body that is safe to report.

    The 'value' member of an authKey or key object is masked whatever it holds,
    and every string has the known secret values scrubbed from it.
    """
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            if key == "value" and parent_key in SECRET_CONTAINER_KEYS:
                sanitized[key] = SECRET_MASK
            else:
                sanitized[key] = _sanitize_body(value, secrets, key)
        return sanitized
    if isinstance(data, list):
        return [_sanitize_body(item, secrets, parent_key) for item in data]
    if isinstance(data, str):
        return _scrub_text(data, secrets)
    return data


def _embedded_error(response: Any) -> bool:
    """Return True when a 2xx response body is a Fabric Engine error document.

    The httpapi plugin raises for HTTP error statuses, but the device can also
    answer a write with a success status and an error body (the same markers
    extreme_fe_vlans checks): a non-empty errorCode, a statusCode/code of 400 or
    more, or a non-empty errors list. A normal response carries none of them.
    """
    if not isinstance(response, dict):
        return False
    if response.get("errorCode"):
        return True
    code = response.get("statusCode") or response.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    # bool is an int subclass; True is not a status code.
    if isinstance(code, int) and not isinstance(code, bool) and code >= 400:
        return True
    errors = response.get("errors")
    return isinstance(errors, list) and bool(errors)


def _embedded_error_message(response: dict[str, Any], path: str, method: str = "PATCH") -> str:
    """Default failure message for an error body: the device's own text, when any."""
    message = response.get("errorMessage") or response.get("message") or response.get("detail")
    return "Device rejected %s %s%s" % (method, path, ": %s" % message if message else "")


def _embedded_status(response: dict[str, Any]) -> int | None:
    """Return the HTTP-like status of an error body (statusCode, code or a numeric errorCode)."""
    for key in ("statusCode", "code", "errorCode"):
        code = response.get(key)
        if isinstance(code, str) and code.strip().isdigit():
            code = int(code)
        if isinstance(code, int) and not isinstance(code, bool):
            return code
    return None


def _classify_fields(payload: dict[str, Any], before: dict[str, Any], readback: dict[str, Any]) -> dict[str, list[str]]:
    """Sort the leaves of an attempted payload by what a re-read shows.

    unchanged      - the resource already held the value before the PATCH (the
                     authKey/helloAuth objects and the 405 fallback carry such
                     fields), so the re-read cannot tell whether it was written
    applied        - the re-read now holds the attempted value
    unverifiable   - a secret whose re-read differs (it may be returned obscured)
    not_applied    - every other field
    """
    fields: dict[str, list[str]] = {"applied": [], "not_applied": [], "unverifiable": [], "unchanged": []}
    for path, value in _payload_leaves(payload):
        if _lookup_dotted(before, path) == value:
            fields["unchanged"].append(path)
        elif _lookup_dotted(readback, path) == value:
            fields["applied"].append(path)
        elif path in SECRET_FIELD_PATHS:
            fields["unverifiable"].append(path)
        else:
            fields["not_applied"].append(path)
    return fields


def _attribution_sentence(resource: str, fields: dict[str, list[str]]) -> str:
    """Describe in one sentence how far a rejected PATCH got."""
    applied = fields["applied"]
    not_applied = fields["not_applied"]
    unverifiable = fields["unverifiable"]
    total = len(applied) + len(not_applied) + len(unverifiable)
    if applied:
        sentence = "The device rejected the PATCH of %s after applying %d of %d changed fields: %s; not applied: %s" % (
            resource,
            len(applied),
            total,
            ", ".join(applied),
            ", ".join(not_applied) or "none",
        )
    elif unverifiable:
        # A secret field cannot be compared with its hashed read-back, so the re-read
        # can only say that nothing was CONFIRMED as applied, not that nothing was.
        sentence = (
            "The device rejected the PATCH of %s; a re-read confirms none of the %d changed fields as applied"
            % (
                resource,
                total,
            )
        )
        if not_applied:
            sentence += "; not applied: " + ", ".join(not_applied)
    else:
        sentence = "The device rejected the PATCH of %s; a re-read shows none of the %d changed fields applied" % (
            resource,
            total,
        )
        if not_applied:
            sentence += ": " + ", ".join(not_applied)
    if unverifiable:
        sentence += "; secret fields that cannot be verified by re-reading: %s" % ", ".join(unverifiable)
    return sentence + "."


def _join_message(original: str, sentence: str) -> str:
    """Append the attribution sentence to the original error message."""
    original = original.rstrip()
    if original and not original.endswith("."):
        original += "."
    return ("%s %s" % (original, sentence)).strip()


def _reread_resource(connection: Connection, port_name: str | None) -> dict[str, Any]:
    """Re-read the PATCHed resource with the GET the module already uses.

    The global settings and the per-port overrides both come from
    GET /v0/configuration/autosense; a port without an override reads as {}.
    """
    global_payload, port_map = fetch_autosense_config(connection)
    if port_name is None:
        return global_payload
    return port_map.get(port_name, {})


def _patch_failure(
    connection: Connection,
    payload: dict[str, Any],
    before: dict[str, Any],
    port_name: str | None,
    failure: dict[str, Any],
) -> FeAutosenseError:
    """Build the error for a rejected multi-field PATCH, attributed per field.

    failure carries the original 'message', the HTTP 'status_code' (None when
    unknown), the 'extra' fail_json keys and 'details' already reported for it.
    """
    resource = GLOBAL_CONFIG_PATH if port_name is None else PORT_CONFIG_PATH % port_name
    # The device text and body may echo a key: mask the key members of the body
    # and scrub the attempted and stored key values from every reported string.
    secrets = _secret_strings(payload, before)
    failure = dict(failure, message=_scrub_text(failure["message"], secrets))
    details: dict[str, Any] = _sanitize_body(dict(failure["details"]), secrets)
    details["attempted_payload"] = _mask_secrets(payload)
    details["resource"] = resource
    # Only an HTTP status: a lost answer's JSON-RPC code or REQUEST_NOT_SENT is not one.
    status = http_status(failure["status_code"])
    if status is not None:
        details["status_code"] = status
    # A transport failure without an HTTP status (no answer): the PATCH may have
    # been applied. An error document has no 'code' in extra, an HTTP error a
    # numeric one.
    no_answer = "code" in failure["extra"] and is_answer_unknown_code(failure["extra"]["code"])
    try:
        readback = _reread_resource(connection, port_name)
    except (ConnectionError, FeAutosenseError) as exc:
        # The re-read failed too: the device state is unknown, so the result
        # keeps the default changed value and says that part may be applied.
        reread_error = _scrub_text(to_text(exc), secrets)
        details["reread_error"] = reread_error
        sentence = (
            "The device rejected the PATCH of %s, and re-reading it to see which fields were applied also failed (%s);"
            " part of the payload may already be applied." % (resource, reread_error)
        )
        # Without an answer the PATCH may have been applied: changed is reported.
        if no_answer:
            details["outcome"] = "unknown"
        return FeAutosenseError(
            _join_message(failure["message"], sentence),
            details=details,
            extra=failure["extra"],
            changed=True if no_answer else None,
        )
    fields = _classify_fields(payload, before, readback)
    details["applied_fields"] = fields["applied"]
    details["not_applied_fields"] = fields["not_applied"]
    details["unverifiable_fields"] = fields["unverifiable"]
    details["unchanged_fields"] = fields["unchanged"]
    # Any applied field means the device was modified before it refused, so the
    # fail result reports changed=true. Otherwise no field was CONFIRMED as applied
    # (a secret field can never be confirmed): without an answer an unverifiable
    # field may have been written, so the outcome is unknown and changed is
    # reported; with an HTTP refusal the default is kept.
    sentence = _attribution_sentence(resource, fields)
    lost_unverified = no_answer and bool(fields["unverifiable"]) and not fields["applied"]
    if lost_unverified:
        details["outcome"] = "unknown"
        sentence = _join_message(
            sentence, "The PATCH got no answer, so the unverifiable field(s) may have been written."
        )
    changed = True if fields["applied"] or lost_unverified else None
    return FeAutosenseError(
        _join_message(failure["message"], sentence),
        details=details,
        extra=failure["extra"],
        changed=changed,
    )


def _send_attributed_patch(
    connection: Connection,
    payload: dict[str, Any],
    before: dict[str, Any],
    port_name: str | None = None,
    error_message: str | None = None,
) -> Any:
    """Send one multi-field PATCH; on failure re-read and attribute it per field.

    The request itself is unchanged (one PATCH carrying the whole payload).
    port_name None means the global settings, otherwise that port's override.
    A 2xx reply whose body is an error document (see _embedded_error) fails the
    same way, global or per port. error_message, when given, is its message;
    otherwise the message is built from the device's own error text.
    """
    path = GLOBAL_CONFIG_PATH if port_name is None else PORT_CONFIG_PATH % port_name
    try:
        # PATCH <path> with the whole payload, exactly as before this wrapper.
        response = connection.send_request(payload, path=path, method="PATCH")
    except ConnectionError as exc:
        # HTTP error or transport failure: keep the 'code' key of the former
        # fail result and add the per-field attribution.
        code = getattr(exc, "code", None)
        failure = {"message": to_text(exc), "status_code": code, "extra": {"code": code}, "details": {}}
        raise _patch_failure(connection, payload, before, port_name, failure)
    if _embedded_error(response):
        # The device answered with an error body: its keys (sanitized by
        # _patch_failure) go in details, and the attribution keys next to them.
        message = error_message or _embedded_error_message(response, path)
        failure = {"message": message, "status_code": None, "extra": {}, "details": response}
        raise _patch_failure(connection, payload, before, port_name, failure)
    return response


def apply_global_settings(
    module: AnsibleModule,
    connection: Connection,
    desired: dict[str, Any],
    current: dict[str, Any],
    state: str = STATE_MERGED,
) -> tuple[bool, dict[str, Any]]:
    """Apply global autosense settings.

    For merged: only patch user-supplied fields.
    For replaced/overridden: build target from GLOBAL_FULL_DEFAULTS + user
    values, then diff against current to reset omitted fields.
    """
    if not desired and state == STATE_MERGED:
        return False, current

    if state in (STATE_REPLACED, STATE_OVERRIDDEN):
        # Build complete desired state: defaults + user overlay
        # First, build the full defaults payload in REST format
        target = _deep_merge({}, GLOBAL_FULL_DEFAULTS)
        # Overlay user-supplied values (convert from Ansible keys to REST keys)
        if desired:
            # Every supplied field (keep_all), with the omitted fields of a supplied
            # authKey/helloAuth object taken from the device (current) rather than
            # from the defaults; other omitted fields keep their default. authKey has
            # no entry in GLOBAL_FULL_DEFAULTS, so an omitted auth key is left alone.
            # A key value taken from the device is never sent (_guard_secret_values).
            user_payload = _build_diff_from_module(desired, current, GLOBAL_SPEC, keep_all=True)
            target = _deep_merge(target, user_payload)
        # Now diff target against current, sending changed composite objects whole.
        diff = _complete_global_composites(_diff_against_current(target, current), target)
    else:
        # Merged: only user-supplied fields
        if not desired:
            return False, current
        diff = _build_diff_from_module(desired, current, GLOBAL_SPEC)

    if not diff:
        return False, current

    # A changed authKey/helloAuth goes out whole; refuse (or default, for
    # helloAuth type NONE) a key value that would be the device's read-back.
    # Runs before the check-mode return so --check fails the same way.
    _guard_secret_values(diff, desired, current)

    if module.check_mode:
        merged = _deep_merge(current, diff)
        return True, merged

    # One PATCH carries the whole global diff. If the device rejects it, the
    # wrapper re-reads the settings and reports which fields it applied anyway.
    _send_attributed_patch(connection, diff, current)
    merged = _deep_merge(current, diff)
    return True, merged


def apply_port_settings(
    module: AnsibleModule,
    connection: Connection,
    operations: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    state_mode: str,
    writes: _WriteTracker | None = None,
) -> tuple[bool, dict[str, dict[str, Any]], list[str]]:
    if not operations:
        return False, current_map, []

    changed = False
    updated_ports: list[str] = []
    for entry in operations:
        port_name = _normalize_port_name(entry["name"])
        payload = _build_port_payload(entry, state_mode)
        if not payload:
            continue
        current_settings = current_map.get(port_name, {})
        diff: dict[str, Any] = {}
        for key, value in payload.items():
            if current_settings.get(key) != value:
                diff[key] = value
        if not diff:
            continue
        if module.check_mode:
            changed = True
            updated_ports.append(port_name)
            current_map[port_name] = _deep_merge(current_settings, diff)
            continue
        # PATCH /v0/configuration/autosense/port/<port> with every changed
        # field; a rejection is re-read and attributed per field.
        _send_attributed_patch(
            connection,
            diff,
            current_settings,
            port_name,
            "Failed to update autosense settings for port %s" % port_name,
        )
        # The PATCH succeeded: a later failure of this task reports a change.
        if writes is not None:
            writes.record()
        changed = True
        updated_ports.append(port_name)
        current_map[port_name] = _deep_merge(current_settings, diff)
    return changed, current_map, updated_ports


def _delete_port_override(
    module: AnsibleModule,
    connection: Connection,
    port_name: str,
    current_map: dict[str, dict[str, Any]],
    delete_support: dict[str, bool] | None = None,
) -> bool:
    """Remove the override of one port; return True when the device changed (or would).

    *delete_support* is shared by the ports of one task: {"supported": bool}
    when the URL capabilities say whether the per-port DELETE exists, or once
    a DELETE has answered 405 ({"supported": False}); empty while unknown.
    """
    if delete_support is None:
        delete_support = {}
    existing_settings = current_map.get(port_name)
    # No entry for this port means the device holds no override to remove, so
    # there is nothing to do. Returning before either write keeps deleted
    # idempotent -- in particular on the PATCH fallback below, which would
    # otherwise push defaults and report a change on an untouched port.
    if existing_settings is None:
        return False

    # The removal payload: the factory defaults (see PORT_DELETE_RESET).
    payload: dict[str, Any] = dict(PORT_DELETE_RESET)
    already_reset = isinstance(existing_settings, dict) and all(
        existing_settings.get(k) == v for k, v in payload.items()
    )
    # A port at the removal payload is only known to be in the desired state
    # where DELETE is not implemented: there every port is listed, and a reset
    # one holds exactly these values. Where DELETE works, the same values can
    # be an override record the user configured, which must still be deleted.
    # So once DELETE is known to be missing (URL capabilities, or a 405 earlier
    # in this task), such a port is skipped without a request and check mode
    # predicts no change for it. It stays in current_map, as the device keeps
    # listing it.
    if already_reset and delete_support.get("supported") is False:
        return False

    if module.check_mode:
        # Predict what the device will list afterwards: without DELETE the
        # fallback PATCH leaves the port with the removal payload; a DELETE
        # (supported, or still unknown) makes it absent.
        if "supported" not in delete_support and not delete_support.get("warned"):
            # Only a DELETE would tell, and check mode sends none.
            delete_support["warned"] = True
            module.warn(
                "The device does not report whether it implements the per-port autosense DELETE (%s), so the "
                "check-mode prediction assumes it does and shows the ports removed. On a device without it the "
                "real run resets them to their factory defaults and they stay listed." % URL_CAPABILITIES_PATH
            )
        if delete_support.get("supported") is False:
            current_map[port_name] = dict(existing_settings, **payload)
        else:
            current_map.pop(port_name, None)
        return True

    if delete_support.get("supported") is not False:
        path = PORT_CONFIG_PATH % port_name
        try:
            response = connection.send_request(None, path=path, method="DELETE")
        except ConnectionError as exc:
            # Only 405 means "this device does not implement DELETE here". Any
            # other failure -- a 5xx, an auth problem, or a timeout, which the
            # httpapi plugin raises as a codeless ConnectionError after exhausting
            # retries -- says nothing about method support, and falling back would
            # write the reset payload off the back of an error that never reached
            # the device.
            code = getattr(exc, "code", None)
            if code == 404:
                # The port override is gone: it was just read as present, and
                # HTTPAPI resends a DELETE after some transport failures, so a
                # first attempt that deleted it and lost its answer makes the
                # resend answer 404.
                current_map.pop(port_name, None)
                return True
            if is_answer_unknown_code(code):
                # No answer (no code, or a negative JSON-RPC code of the
                # persistent connection): the DELETE may have been applied.
                raise FeAutosenseError(
                    "%s. The DELETE of %s may have been applied before the answer was lost; check the port on the "
                    "device." % (to_text(exc).rstrip("."), path),
                    details={"outcome": "unknown", "resource": path},
                    extra={"code": None},
                    changed=True,
                ) from exc
            if code != HTTP_METHOD_NOT_ALLOWED:
                raise
            response = None
            delete_support["supported"] = False
        if delete_support.get("supported") is not False:
            if not _embedded_error(response):
                current_map.pop(port_name, None)
                return True
            # A 2xx answer with an error document did not delete anything. An
            # embedded 405 means the same as an HTTP 405 (fall back to the
            # PATCH); any other error fails the task, the port left as it is.
            if _embedded_status(response) != HTTP_METHOD_NOT_ALLOWED:
                raise FeAutosenseError(
                    _embedded_error_message(response, path, "DELETE"),
                    details=_sanitize_body(response, _secret_strings(existing_settings)),
                )
            delete_support["supported"] = False
        # The fallback PATCH would change nothing on a port already reset;
        # the device keeps listing it with these values.
        if already_reset:
            return False

    # DELETE returns 405 on Fabric Engine 9.4 — fall back to one PATCH with
    # the removal payload (later ports of the task skip the DELETE); a
    # rejection is re-read and attributed per field.
    _send_attributed_patch(
        connection,
        payload,
        existing_settings,
        port_name,
        "Failed to remove autosense overrides for port %s" % port_name,
    )
    # The port stays listed with the removal payload (only a DELETE removes it).
    current_map[port_name] = dict(existing_settings, **payload)
    return True


def _normalize_capability_url(url: str) -> str:
    """Reduce a capability URL to compare it with the per-port path.

    The leading version (/v0), placeholders ({port}, {portName}, ...) and
    slashes at either end are not significant: "/v0/configuration/autosense/port/{port}"
    becomes "configuration/autosense/port/{}".
    """
    parts = [part for part in url.strip().strip("/").split("/") if part]
    if parts and len(parts[0]) > 1 and parts[0][0] in "vV" and parts[0][1:].isdigit():
        parts = parts[1:]
    return "/".join("{}" if part.startswith("{") and part.endswith("}") else part.lower() for part in parts)


def _port_delete_support(connection: Connection) -> dict[str, bool]:
    """Return {"supported": bool} when the device says whether the per-port DELETE exists.

    Read-only: the URL capabilities list the operations of every URL. An empty
    dict means unknown (read failed, unexpected shape or the path not listed);
    _delete_port_override() then learns it from the first DELETE.
    """
    try:
        data = connection.send_request(None, path=URL_CAPABILITIES_PATH, method="GET")
    except ConnectionError:
        return {}
    if not isinstance(data, list):
        return {}
    wanted = _normalize_capability_url(PORT_CONFIG_PATH % "{port}")
    for entry in data:
        if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
            continue
        if _normalize_capability_url(entry["url"]) != wanted:
            continue
        ops = entry.get("supportedOps")
        if not isinstance(ops, list):
            return {}
        return {"supported": any(isinstance(op, str) and op.upper() == "DELETE" for op in ops)}
    return {}


def delete_port_settings(
    module: AnsibleModule,
    connection: Connection,
    operations: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    writes: _WriteTracker | None = None,
) -> tuple[bool, dict[str, dict[str, Any]], list[str]]:
    if not operations:
        return False, current_map, []

    changed = False
    removed_ports: list[str] = []
    # Whether this device implements the per-port DELETE: read from the URL
    # capabilities when a listed port has an override to remove, else (or
    # when they do not say) learned from the first DELETE answered 405 (see
    # _delete_port_override).
    delete_support: dict[str, bool] = {}
    if any(_normalize_port_name(entry["name"]) in current_map for entry in operations):
        delete_support = _port_delete_support(connection)
    for entry in operations:
        port_name = _normalize_port_name(entry["name"])
        if _delete_port_override(module, connection, port_name, current_map, delete_support):
            # A real DELETE (or its 405 fallback PATCH) succeeded; check mode
            # wrote nothing.
            if writes is not None and not module.check_mode:
                writes.record()
            changed = True
            removed_ports.append(port_name)
    return changed, current_map, removed_ports


def gather_autosense_state(
    connection: Connection,
    gather_filter: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    data = connection.send_request(None, path="/v0/state/autosense/ports", method="GET")
    if data is None:
        return []
    if not isinstance(data, list):
        raise FeAutosenseError(
            "Unexpected response when retrieving autosense state",
            details={"response": data},
        )
    filter_set: set | None = None
    if gather_filter:
        filter_set = {_normalize_port_name(item) for item in gather_filter}
    results: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("portName")
        if not isinstance(name, str):
            continue
        normalized_name = _normalize_port_name(name)
        if filter_set is not None and normalized_name not in filter_set:
            continue
        state_entry = {"name": normalized_name}
        state_value = entry.get("state")
        if state_value is not None:
            state_entry["state"] = state_value
        other_keys = {k: v for k, v in entry.items() if k not in ("portName", "state")}
        if other_keys:
            state_entry["details"] = other_keys
        results.append(state_entry)
    return results


def _handle_gathered(
    connection: Connection,
    gather_filter: list[str] | None,
    gather_state: bool,
    current_global: dict[str, Any],
    port_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Handle state=gathered: read-only."""
    result: dict[str, Any] = {"changed": False}
    result["global_settings"] = _transform_for_output(current_global, GLOBAL_SPEC)
    # `gathered` holds `config` entries, so it can be applied back as is;
    # `ports_settings` keeps the `{name, settings}` form and is deprecated here.
    result["gathered"] = _ports_config_entries(port_map, gather_filter)
    result["ports_settings"] = _transform_ports_output(port_map, gather_filter)
    if gather_state:
        result["ports_state"] = gather_autosense_state(connection, gather_filter)
    return result


def _build_snapshot(global_state: dict[str, Any], port_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return the before/after shape: the two inputs of the module, global settings
    plus every per-port override as `config` entries (like `gathered`).

    `ports` repeats the overrides in the `{name, settings}` form returned up
    to 1.2.1; it is deprecated (removal in 2.0.0) and left out of --diff.
    """
    return {
        "global_settings": _transform_for_output(global_state, GLOBAL_SPEC),
        "config": _ports_config_entries(port_map),
        "ports": _transform_ports_output(port_map),
    }


def _diff_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a before/after snapshot for --diff, without the deprecated `ports` copy."""
    return {key: value for key, value in snapshot.items() if key != "ports"}


def _apply_global_phase(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    current_global: dict[str, Any],
) -> tuple[bool, dict[str, Any], dict[str, Any] | None]:
    """Apply the global settings of the task.

    Returns (changed, current_global after the change, global_settings output or None).

    Only touched when the task actually mentions them. The global settings
    are a separate resource from the per-port overrides in 'config', so a
    task managing only ports must not reset them -- under replaced and
    overridden that would rewrite device-wide configuration the playbook
    never referred to.

    'global_settings' is a dict with suboptions, so Ansible fills it in as
    soon as the key appears and an explicit 'global_settings: {}' arrives
    non-None. That makes the three cases distinguishable:
      key omitted            -> globals left alone
      global_settings: {}    -> under replaced/overridden, all globals reset
      global_settings: {...} -> supplied fields applied, and under
                                replaced/overridden the omitted ones reset
    """
    raw_global = module.params.get("global_settings")
    desired_global = raw_global or {}
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN) and raw_global is not None:
        changed_global, current_global = apply_global_settings(
            module, connection, desired_global, current_global, state
        )
        output = None
        if changed_global or (desired_global and module.check_mode):
            output = _transform_for_output(current_global, GLOBAL_SPEC)
        return changed_global, current_global, output
    if state == STATE_DELETED and desired_global:
        raise FeAutosenseError("'global_settings' is not valid for state deleted")
    return False, current_global, None


def _apply_port_phase(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    port_map: dict[str, dict[str, Any]],
    writes: _WriteTracker | None = None,
) -> tuple[bool, dict[str, dict[str, Any]], list[str], list[str]]:
    """Apply the per-port overrides of the task.

    Returns (changed, port_map after the change, updated ports, removed ports).
    writes, when given, records every successful device write.
    """
    desired_ports = module.params.get("config") or []
    initial_port_names = set(port_map.keys())
    updated_ports: list[str] = []
    removed_ports: list[str] = []

    if state == STATE_DELETED:
        if not desired_ports:
            # No config: remove the override of every port the device lists.
            desired_ports = [{"name": name} for name in sorted(port_map)]
        changed_ports, port_map, removed_ports = delete_port_settings(
            module, connection, desired_ports, port_map, writes
        )
        return changed_ports, port_map, updated_ports, removed_ports

    changed_ports, port_map, updated_ports = apply_port_settings(
        module, connection, desired_ports, port_map, state, writes
    )
    if state == STATE_OVERRIDDEN:
        desired_port_names = {_normalize_port_name(entry["name"]) for entry in desired_ports if "name" in entry}
        to_remove = [name for name in initial_port_names if name not in desired_port_names]
        if to_remove:
            removal_entries = [{"name": name} for name in to_remove]
            removal_changed, port_map, removal_list = delete_port_settings(
                module, connection, removal_entries, port_map, writes
            )
            if removal_changed:
                changed_ports = True
            removed_ports.extend(removal_list)
    return changed_ports, port_map, updated_ports, removed_ports


def _capture_after_state(
    module: AnsibleModule,
    connection: Connection,
    changed: bool,
    before: dict[str, Any],
    current_global: dict[str, Any],
    port_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return the after snapshot.

    After a real change it is re-read from the device. In check mode it is the
    predicted state, built from the working copies the apply helpers have
    updated in place. When nothing changed it equals the before snapshot.
    """
    if not changed:
        return copy.deepcopy(before)
    if module.check_mode:
        return _build_snapshot(current_global, port_map)
    after_global, after_port_map = fetch_autosense_config(connection)
    return _build_snapshot(after_global, after_port_map)


def _has_supplied_value(value: Any) -> bool:
    """Return True when value holds at least one supplied (non-None) leaf."""
    if isinstance(value, dict):
        return any(_has_supplied_value(item) for item in value.values())
    return value is not None


def _validate_config_guard(module: AnsibleModule, state: str) -> None:
    """Fail before any request when a write state has nothing to apply.

    overridden removes every per-port override not listed in 'config', so an
    empty or omitted 'config' would delete them all; it always needs at least
    one port (use deleted without 'config' to remove every override).
    merged and replaced need 'config' or 'global_settings'. Under merged a
    'global_settings' whose suboptions are all unset applies nothing, while
    under replaced an explicit 'global_settings: {}' is the documented reset
    of the global settings and is accepted.
    """
    # A port listed twice would get two requests and keep the last one silently.
    seen: set[str] = set()
    for entry in module.params.get("config") or []:
        name = _normalize_port_name(entry["name"])
        if name in seen:
            raise FeAutosenseError("Port '%s' is listed more than once in 'config'; list each port once" % name)
        seen.add(name)
    if state not in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
        return
    if module.params.get("config"):
        return
    if state == STATE_OVERRIDDEN:
        raise FeAutosenseError(
            "value of config parameter must not be empty for state overridden: without a port every per-port "
            "override would be deleted. Use state 'deleted' without 'config' to remove all port overrides."
        )
    raw_global = module.params.get("global_settings")
    if state == STATE_REPLACED and raw_global is not None:
        return
    if _has_supplied_value(raw_global):
        return
    raise FeAutosenseError(
        "value of config parameter must not be empty for state %s (or supply global_settings)" % state
    )


def _handle_action_states(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    current_global: dict[str, Any],
    port_map: dict[str, dict[str, Any]],
    gather_state: bool,
    gather_filter: list[str] | None,
) -> dict[str, Any]:
    """Handle merged/replaced/overridden/deleted states.

    Every device write of the task is recorded, so a failure after one of them
    succeeded reports changed=true (see _WriteTracker).
    """
    with _WriteTracker() as writes:
        return _run_action_states(
            module, connection, state, current_global, port_map, gather_state, gather_filter, writes
        )


def _run_action_states(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    current_global: dict[str, Any],
    port_map: dict[str, dict[str, Any]],
    gather_state: bool,
    gather_filter: list[str] | None,
    writes: _WriteTracker,
) -> dict[str, Any]:
    """Apply the global and per-port phases, recording each write in writes."""
    result: dict[str, Any] = {"changed": False}

    # Before snapshot
    before = _build_snapshot(current_global, port_map)
    result["before"] = before

    # Global settings
    changed_global, current_global, global_output = _apply_global_phase(module, connection, state, current_global)
    if changed_global:
        result["changed"] = True
        # A real global PATCH succeeded (check mode wrote nothing).
        if not module.check_mode:
            writes.record()
    if global_output is not None:
        result["global_settings"] = global_output

    # Port operations
    desired_ports = module.params.get("config") or []
    changed_ports, port_map, updated_ports, removed_ports = _apply_port_phase(
        module, connection, state, port_map, writes
    )

    if changed_ports:
        result["changed"] = True
    if updated_ports:
        result["port_updates"] = updated_ports
    if removed_ports:
        result["port_removals"] = removed_ports

    if (changed_ports or (desired_ports and module.check_mode)) and updated_ports:
        result["ports_settings"] = _transform_ports_output(
            {name: port_map.get(name, {}) for name in updated_ports},
            updated_ports,
        )

    # After snapshot: re-read after a real change, predicted in check mode,
    # equal to the before snapshot when nothing changed.
    result["after"] = _capture_after_state(module, connection, result["changed"], before, current_global, port_map)

    # Diff mode (--diff): Ansible renders the before/after pair itself. It is populated
    # whether or not anything changed (identical dicts render as no diff) and in check
    # mode 'after' is the predicted state. It is never set for gathered. The
    # deprecated 'ports' copy is left out, so each port is shown once.
    if module._diff:
        result["diff"] = {"before": _diff_snapshot(result["before"]), "after": _diff_snapshot(result["after"])}

    # Optional state collection
    if gather_state:
        if gather_filter:
            state_filter: list[str] | None = gather_filter
        elif updated_ports:
            state_filter = updated_ports
        elif removed_ports:
            state_filter = removed_ports
        else:
            state_filter = None
        result["ports_state"] = gather_autosense_state(connection, state_filter)

    return result


def run_module() -> None:
    """Module entry point with state dispatch."""
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    try:
        connection = get_connection(module)
    except FeAutosenseError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    try:
        state = module.params.get("state")
        gather_filter = module.params.get("gather_filter") or None
        gather_state = bool(module.params.get("gather_state"))

        _validate_config_guard(module, state)
        current_global, port_map = fetch_autosense_config(connection)

        if state == STATE_GATHERED:
            result = _handle_gathered(connection, gather_filter, gather_state, current_global, port_map)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED):
            result = _handle_action_states(
                module, connection, state, current_global, port_map, gather_state, gather_filter
            )
        else:
            raise FeAutosenseError("Unsupported state '%s'" % state)

        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeAutosenseError as exc:
        module.fail_json(**exc.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
