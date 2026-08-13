# -*- coding: utf-8 -*-
"""Ansible module to manage Extreme Fabric Engine autosense settings."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

from typing import Any, Dict, Iterable, List, Optional, Tuple

DOCUMENTATION = r"""
---
module: extreme_fe_autosense
short_description: Manage Fabric Engine autosense settings and port behaviour
version_added: "1.0.0"
description:
    - Manage global autosense settings and per-port overrides on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI plugin.
    - Supports Fabric Attach profiles, voice and DiffServ parameters, multihost limits, onboarding defaults, and per-port autosense toggles and wait timers.
    - Provides a gathered mode that reports the full configuration and live autosense port state from C(/v0/state/autosense/ports).
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - Ports are supplied through the C(config) list. The parameter was named
      C(ports) before 1.2.1; that name still works as a deprecated alias.
    - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
    - Port identifiers must use slot:port notation such as C(1:5).
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired module operation.
            - C(merged) applies the provided settings as an incremental merge.
            - C(replaced) makes the supplied values authoritative for the targeted resources.
            - C(overridden) replaces the running configuration with the supplied values and removes entries that are not provided.
            - C(deleted) removes the specified per-port overrides.
            - C(gathered) returns the current configuration (and optional state payloads) without making changes.
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
              an empty dict to reset every global setting.
        type: dict
        suboptions:
            access_diffserv_enabled:
                description:
                    - Enable the access DiffServ profile for autosense ports.
                type: bool
            data_isid:
                description:
                    - Data I-SID assigned to autosense data roles. C(0) clears the value.
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
                                    - Fabric Attach camera I-SID. C(0) clears the association.
                                type: int
                    ovs:
                        description:
                            - Open vSwitch Fabric Attach profile.
                        type: dict
                        suboptions:
                            isid:
                                description:
                                    - Fabric Attach OVS I-SID. C(0) clears the association.
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
                                    - Management I-SID used for proxy traffic. C(0) clears the value.
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
                                    - WAP I-SID. C(0) clears the association.
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
                            - ISIS Level-1 metric applied to autosense interfaces.
                        type: int
                    l1_metric_auto_enabled:
                        description:
                            - Enable automatic calculation of the ISIS Level-1 metric.
                        type: bool
            onboarding_isid:
                description:
                    - Onboarding I-SID used while autosense negotiations complete. C(0) clears the value.
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
                            - Voice I-SID used by autosense ports. C(0) clears the association.
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
                    - Network service identifier (I-SID). C(0) clears the association.
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
          value: "my-secret-key"
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
- name: Reset custom overrides and disable autosense
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
      description: Global autosense configuration (snake_case keys).
      returned: always
      type: dict
    ports:
      description: Per-port autosense overrides.
      returned: always
      type: list
      elements: dict
after:
  description:
    - Global settings and per-port overrides on the device after the task ran.
    - Re-read from the device, so it reflects what the device actually applied
      rather than what was requested. Not returned when nothing changed or in
      check mode, since it would repeat C(before).
  returned: when the task changed the device and not in check mode
  type: dict
  contains:
    global_settings:
      description: Global autosense configuration (snake_case keys).
      returned: always
      type: dict
    ports:
      description: Per-port autosense overrides.
      returned: always
      type: list
      elements: dict
global_settings:
  description: Resulting global autosense configuration after any updates (snake_case keys).
  returned: when state == gathered or when global settings changed/queried
  type: dict
ports_settings:
  description: List of per-port autosense settings with normalized field names.
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

ARGUMENT_SPEC: Dict[str, Any] = {
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
                        "options": {
                            "is_encrypted": {"type": "bool"},
                            "value": {"type": "str"},
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
                                "options": {
                                    "is_encrypted": {"type": "bool"},
                                    "value": {"type": "str"},
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
            {"name": "ports", "version": "1.2.1", "collection_name": "extreme.fe"},
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


GLOBAL_SPEC: Dict[str, Any] = {
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
                    "value": {"rest": "value"},
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
                            "value": {"rest": "value"},
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


PORT_FIELD_MAP: Dict[str, str] = {
    "enable": "enable",
    "nsi": "nsi",
    "wait_interval": "waitInterval",
}

# Factory defaults for per-port autosense overrides -- used by replaced/overridden
# to reset omitted fields rather than requiring all fields from the user.
# Verified via device behavior: autosense is enabled by default, nsi=0 means
# cleared, wait_interval=35 is the OpenAPI default.
PORT_FULL_DEFAULTS: Dict[str, Any] = {
    "enable": True,        # default: true (from OpenAPI PortAutoSenseSettings)
    "nsi": 0,              # 0 clears the I-SID assignment
    "waitInterval": 35,    # default: 35 (from OpenAPI PortAutoSenseSettings)
}

# Payload used to emulate a per-port DELETE on firmware that rejects the
# method (VOSS 9.4 answers 405). Deliberately NOT PORT_FULL_DEFAULTS: that
# dict holds the OpenAPI defaults for fields *inside* an override, where
# enable is true, while removing an override means the port should stop being
# autosense-managed. Resetting enable to true here would switch autosense ON
# for every port a playbook asked to clear, so the two must not be merged.
#
# waitInterval is absent on purpose -- it only has meaning while autosense is
# enabled, and _delete_port_override() carries the port's existing value over
# so the PATCH does not touch a field the delete does not own.
PORT_DELETE_RESET: Dict[str, Any] = {
    "enable": False,       # no override -- autosense off for this port
    "nsi": 0,              # 0 clears the I-SID assignment
}

# The only status that means "this firmware does not implement DELETE on the
# per-port endpoint" and so justifies the PATCH fallback.
HTTP_METHOD_NOT_ALLOWED = 405

# Factory defaults for global autosense settings -- used by replaced/overridden
# to reset omitted fields. Only includes fields with explicit OpenAPI defaults.
# Fields without defaults (dot1xMultihost counts, l1Metric, waitInterval) are
# left unchanged when omitted because device factory values are not documented.
GLOBAL_FULL_DEFAULTS: Dict[str, Any] = {
    "accessDiffservEnabled": True,       # default: true
    "dataIsid": 0,                       # 0 means not set
    "dhcpDetectionEnabled": True,        # default: true
    "dot1pOverrideEnabled": True,        # default: true
    "onboardingIsid": 0,                 # 0 means not set
    "fabricAttach": {
        "msgAuthEnabled": True,           # default: true
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
        "dot1xLldpAuthEnabled": False,     # default: false
        "isid": 0,                         # 0 means not set
    },
}


STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"


class FeAutosenseError(Exception):
    """Base exception for autosense module errors."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _normalize_port_name(raw: str) -> str:
    if not isinstance(raw, str):
        raise FeAutosenseError("Port name must be a string in slot:port format")
    value = raw.strip()
    if not value:
        raise FeAutosenseError("Port name must not be empty")
    return value


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_diff_from_module(
    desired: Dict[str, Any],
    current: Dict[str, Any],
    spec: Dict[str, Any],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
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
            # Special handling for authKey: API requires both isEncrypted and value
            # We must send the complete object even if only one field changed
            if rest_key == "authKey":
                complete_authkey: Dict[str, Any] = {}
                complete_authkey["isEncrypted"] = desired_value.get(
                    "is_encrypted", current_value.get("isEncrypted", False)
                )
                complete_authkey["value"] = desired_value.get(
                    "value", current_value.get("value", "")
                )
                # Check if anything actually changed
                if (complete_authkey["isEncrypted"] != current_value.get("isEncrypted") or
                        complete_authkey["value"] != current_value.get("value")):
                    payload[rest_key] = complete_authkey
            # Special handling for helloAuth: API requires key, keyId, and type together
            # The nested key object also requires both isEncrypted and value
            elif rest_key == "helloAuth":
                complete_helloauth: Dict[str, Any] = {}
                # Build the nested key object (requires isEncrypted and value together)
                key_desired = desired_value.get("key", {})
                key_current = current_value.get("key", {})
                if key_desired or key_current:
                    complete_key: Dict[str, Any] = {}
                    complete_key["isEncrypted"] = key_desired.get(
                        "is_encrypted", key_current.get("isEncrypted", False)
                    )
                    complete_key["value"] = key_desired.get(
                        "value", key_current.get("value", "")
                    )
                    complete_helloauth["key"] = complete_key
                # keyId field
                complete_helloauth["keyId"] = desired_value.get(
                    "key_id", current_value.get("keyId", 0)
                )
                # type field
                complete_helloauth["type"] = desired_value.get(
                    "type", current_value.get("type", "NONE")
                )
                # Check if anything actually changed
                current_key = current_value.get("key", {})
                if (complete_helloauth.get("key", {}).get("isEncrypted") != current_key.get("isEncrypted") or
                        complete_helloauth.get("key", {}).get("value") != current_key.get("value") or
                        complete_helloauth["keyId"] != current_value.get("keyId") or
                        complete_helloauth["type"] != current_value.get("type")):
                    payload[rest_key] = complete_helloauth
            else:
                diff_value = _build_diff_from_module(desired_value, current_value, child_spec)
                if diff_value:
                    payload[rest_key] = diff_value
        else:
            current_value = current.get(rest_key)
            if current_value != desired_value:
                payload[rest_key] = desired_value
    return payload


def _transform_for_output(payload: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for param, mapping in spec.items():
        rest_key = mapping["rest"]
        if rest_key not in payload:
            continue
        value = payload.get(rest_key)
        if value is None:
            continue
        child_spec = mapping.get("spec")
        if child_spec and isinstance(value, dict):
            child_value = _transform_for_output(value, child_spec)
            if child_value:
                result[param] = child_value
        else:
            result[param] = value
    return result


def _build_port_payload(entry: Dict[str, Any], state: str) -> Dict[str, Any]:
    """Build REST payload for a port entry.

    For merged: only user-supplied fields.
    For replaced/overridden: all fields, using PORT_FULL_DEFAULTS for omitted.
    """
    payload: Dict[str, Any] = {}
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
    port_map: Dict[str, Dict[str, Any]],
    gather_filter: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
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
    result: List[Dict[str, Any]] = []
    for name in names:
        settings = port_map.get(name)
        if not isinstance(settings, dict):
            continue
        transformed: Dict[str, Any] = {}
        for param, rest_key in PORT_FIELD_MAP.items():
            if rest_key in settings:
                transformed[param] = settings.get(rest_key)
        result.append({"name": name, "settings": transformed})
    return result


def get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeAutosenseError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def fetch_autosense_config(connection: Connection) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    data = connection.send_request(None, path="/v0/configuration/autosense", method="GET")
    if data is None:
        return {}, {}
    if not isinstance(data, dict):
        raise FeAutosenseError(
            "Unexpected response when retrieving autosense configuration",
            details={"response": data},
        )
    ports_payload = data.get("ports")
    port_map: Dict[str, Dict[str, Any]] = {}
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


def apply_global_settings(
    module: AnsibleModule,
    connection: Connection,
    desired: Dict[str, Any],
    current: Dict[str, Any],
    state: str = STATE_MERGED,
) -> Tuple[bool, Dict[str, Any]]:
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
            user_payload = _build_diff_from_module(desired, {}, GLOBAL_SPEC)
            target = _deep_merge(target, user_payload)
        # Now diff target against current
        diff: Dict[str, Any] = {}
        for key, desired_value in target.items():
            current_value = current.get(key)
            if isinstance(desired_value, dict) and isinstance(current_value, dict):
                sub_diff: Dict[str, Any] = {}
                for sk, sv in desired_value.items():
                    if current_value.get(sk) != sv:
                        sub_diff[sk] = sv
                if sub_diff:
                    diff[key] = sub_diff
            elif current_value != desired_value:
                diff[key] = desired_value
    else:
        # Merged: only user-supplied fields
        if not desired:
            return False, current
        diff = _build_diff_from_module(desired, current, GLOBAL_SPEC)

    if not diff:
        return False, current

    if module.check_mode:
        merged = _deep_merge(current, diff)
        return True, merged

    connection.send_request(diff, path="/v0/configuration/autosense", method="PATCH")
    merged = _deep_merge(current, diff)
    return True, merged


def apply_port_settings(
    module: AnsibleModule,
    connection: Connection,
    operations: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
    state_mode: str,
) -> Tuple[bool, Dict[str, Dict[str, Any]], List[str]]:
    if not operations:
        return False, current_map, []

    changed = False
    updated_ports: List[str] = []
    for entry in operations:
        port_name = _normalize_port_name(entry["name"])
        payload = _build_port_payload(entry, state_mode)
        if not payload:
            continue
        current_settings = current_map.get(port_name, {})
        diff: Dict[str, Any] = {}
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
        response = connection.send_request(
            diff,
            path="/v0/configuration/autosense/port/%s" % port_name,
            method="PATCH",
        )
        if isinstance(response, dict) and response.get("errorCode"):
            raise FeAutosenseError(
                "Failed to update autosense settings for port %s" % port_name,
                details=response,
            )
        changed = True
        updated_ports.append(port_name)
        current_map[port_name] = _deep_merge(current_settings, diff)
    return changed, current_map, updated_ports


def _delete_port_override(
    module: AnsibleModule,
    connection: Connection,
    port_name: str,
    current_map: Dict[str, Dict[str, Any]],
) -> bool:
    existing_settings = current_map.get(port_name)
    # No entry for this port means the device holds no override to remove, so
    # there is nothing to do. Returning before either write keeps deleted
    # idempotent -- in particular on the PATCH fallback below, which would
    # otherwise push defaults and report a change on an untouched port.
    if existing_settings is None:
        return False

    if module.check_mode:
        current_map.pop(port_name, None)
        return True

    try:
        connection.send_request(None, path="/v0/configuration/autosense/port/%s" % port_name, method="DELETE")
        current_map.pop(port_name, None)
        return True
    except ConnectionError as exc:
        # Only 405 means "this device does not implement DELETE here". Any
        # other failure -- a 5xx, an auth problem, or a timeout, which the
        # httpapi plugin raises as a codeless ConnectionError after exhausting
        # retries -- says nothing about method support, and falling back would
        # write the reset payload off the back of an error that never reached
        # the device.
        if getattr(exc, "code", None) != HTTP_METHOD_NOT_ALLOWED:
            raise
        # DELETE returns 405 on VOSS 9.4 — fall back to PATCH with the
        # removal payload. See PORT_DELETE_RESET for why this is not
        # PORT_FULL_DEFAULTS.
        payload: Dict[str, Any] = dict(PORT_DELETE_RESET)
        if isinstance(existing_settings, dict) and "waitInterval" in existing_settings:
            payload["waitInterval"] = existing_settings["waitInterval"]
        # Idempotency: if existing settings already match the reset payload,
        # the port is already in the desired state — skip the PATCH.
        if isinstance(existing_settings, dict):
            already_reset = all(
                existing_settings.get(k) == v for k, v in payload.items()
            )
            if already_reset:
                current_map.pop(port_name, None)
                return False
        response = connection.send_request(
            payload,
            path="/v0/configuration/autosense/port/%s" % port_name,
            method="PATCH",
        )
        if isinstance(response, dict) and response.get("errorCode"):
            raise FeAutosenseError(
                "Failed to remove autosense overrides for port %s" % port_name,
                details=response,
            )
        current_map.pop(port_name, None)
        return True


def delete_port_settings(
    module: AnsibleModule,
    connection: Connection,
    operations: List[Dict[str, Any]],
    current_map: Dict[str, Dict[str, Any]],
) -> Tuple[bool, Dict[str, Dict[str, Any]], List[str]]:
    if not operations:
        return False, current_map, []

    changed = False
    removed_ports: List[str] = []
    for entry in operations:
        port_name = _normalize_port_name(entry["name"])
        if _delete_port_override(module, connection, port_name, current_map):
            changed = True
            removed_ports.append(port_name)
    return changed, current_map, removed_ports


def gather_autosense_state(
    connection: Connection,
    gather_filter: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    data = connection.send_request(None, path="/v0/state/autosense/ports", method="GET")
    if data is None:
        return []
    if not isinstance(data, list):
        raise FeAutosenseError(
            "Unexpected response when retrieving autosense state",
            details={"response": data},
        )
    filter_set: Optional[set] = None
    if gather_filter:
        filter_set = {_normalize_port_name(item) for item in gather_filter}
    results: List[Dict[str, Any]] = []
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
    gather_filter: Optional[List[str]],
    gather_state: bool,
    current_global: Dict[str, Any],
    port_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Handle state=gathered: read-only."""
    result: Dict[str, Any] = {"changed": False}
    result["global_settings"] = _transform_for_output(current_global, GLOBAL_SPEC)
    result["ports_settings"] = _transform_ports_output(port_map, gather_filter)
    if gather_state:
        result["ports_state"] = gather_autosense_state(connection, gather_filter)
    return result


def _handle_action_states(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    current_global: Dict[str, Any],
    port_map: Dict[str, Dict[str, Any]],
    gather_state: bool,
    gather_filter: Optional[List[str]],
) -> Dict[str, Any]:
    """Handle merged/replaced/overridden/deleted states."""
    result: Dict[str, Any] = {"changed": False}

    # Before snapshot
    before_global = _transform_for_output(current_global, GLOBAL_SPEC)
    before_ports = _transform_ports_output(port_map)
    result["before"] = {"global_settings": before_global, "ports": before_ports}

    raw_global = module.params.get("global_settings")
    desired_global = raw_global or {}
    desired_ports = module.params.get("config") or []
    initial_port_names = set(port_map.keys())

    # Global settings.
    #
    # Only touched when the task actually mentions them. The global settings
    # are a separate resource from the per-port overrides in 'config', so a
    # task managing only ports must not reset them -- under replaced and
    # overridden that would rewrite device-wide configuration the playbook
    # never referred to.
    #
    # 'global_settings' is a dict with suboptions, so Ansible fills it in as
    # soon as the key appears and an explicit 'global_settings: {}' arrives
    # non-None. That makes the three cases distinguishable:
    #   key omitted            -> globals left alone
    #   global_settings: {}    -> under replaced/overridden, all globals reset
    #   global_settings: {...} -> supplied fields applied, and under
    #                             replaced/overridden the omitted ones reset
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN) \
            and raw_global is not None:
        changed_global, current_global = apply_global_settings(
            module, connection, desired_global, current_global, state)
        if changed_global:
            result["changed"] = True
        if changed_global or (desired_global and module.check_mode):
            result["global_settings"] = _transform_for_output(
                current_global, GLOBAL_SPEC)
    elif state == STATE_DELETED:
        if desired_global:
            raise FeAutosenseError(
                "Global settings cannot be supplied when state='deleted'.")

    # Port operations
    updated_ports: List[str] = []
    removed_ports: List[str] = []

    if state == STATE_DELETED:
        changed_ports, port_map, removed_ports = delete_port_settings(
            module, connection, desired_ports, port_map)
    else:
        changed_ports, port_map, updated_ports = apply_port_settings(
            module, connection, desired_ports, port_map, state)
        if state == STATE_OVERRIDDEN:
            desired_port_names = {
                _normalize_port_name(entry["name"])
                for entry in desired_ports if "name" in entry
            }
            to_remove = [name for name in initial_port_names
                         if name not in desired_port_names]
            if to_remove:
                removal_entries = [{"name": name} for name in to_remove]
                removal_changed, port_map, removal_list = delete_port_settings(
                    module, connection, removal_entries, port_map)
                if removal_changed:
                    changed_ports = True
                removed_ports.extend(removal_list)

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

    # After snapshot
    if result["changed"] and not module.check_mode:
        after_global, after_port_map = fetch_autosense_config(connection)
        result["after"] = {
            "global_settings": _transform_for_output(after_global, GLOBAL_SPEC),
            "ports": _transform_ports_output(after_port_map),
        }

    # Optional state collection
    if gather_state:
        if gather_filter:
            state_filter: Optional[List[str]] = gather_filter
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

        current_global, port_map = fetch_autosense_config(connection)

        if state == STATE_GATHERED:
            result = _handle_gathered(
                connection, gather_filter, gather_state,
                current_global, port_map)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN,
                       STATE_DELETED):
            result = _handle_action_states(
                module, connection, state, current_global, port_map,
                gather_state, gather_filter)
        else:
            raise FeAutosenseError(
                "Unsupported state '%s' supplied." % state)

        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeAutosenseError as exc:
        module.fail_json(**exc.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
