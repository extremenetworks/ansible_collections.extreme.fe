# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage LLDP interface settings on Fabric Engine switches."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_lldp_interfaces
short_description: Manage LLDP interface settings on ExtremeNetworks Fabric Engine switches
version_added: "1.1.0"
description:
  - Manage LLDP interface-level settings on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe)
    HTTPAPI plugin.
  - Uses C(/v0/configuration/lldp/ports/{port}) and C(/v0/configuration/lldp/ports/{port}/med-policy) from the NOS
    OpenAPI schema.
  - Supports the Fabric Engine LLDP port attributes exposed by the schema,
    including basic transmit or receive control, advertised TLVs, location
    data, and MED network policy entries.
  - When C(med_policy) is supplied, it is treated as the authoritative list for that interface because the device API
    replaces the full MED policy list.
author:
  - Bjorn Haas (@bhaas_extr)
notes:
  - Tested against Fabric Engine Version 9.3.2.
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI connection plugin.
  - Name ports using slot:port notation, such as C(1:5). The list was named C(interfaces) up to 1.2.1; that name
    still works but is deprecated.
  - Fabric Engine needs C(transmit_enabled) and C(receive_enabled) to have the same value. If you set only one,
    the module sets the other to match; setting them to different values fails.
  - When LLDP is off on a port, the switch ignores the advertisement, location and MED policy settings, so the
    module sends only the enable flags and the port keeps its other settings.
  - When you supply C(med_policy) for a port, it replaces that port's whole MED policy list.
  - C(civic_address) must start with C(country-code) and a two-letter code, followed by at least one more label,
    each with a value. A misspelled label (for example C(postal-code)) fails the task, because the switch would
    otherwise advertise a wrong emergency location. Quote a value that contains a label word, for example
    C(street "Main room").
  - C(deleted) without C(config) resets LLDP on every port to its defaults.
  - The C(gathered) result can be passed back as C(config). The old C(interfaces_settings) result is still
    returned but is deprecated and will be removed in 2.0.0.
  - Each port's LLDP settings and MED policy are written separately. If a write fails, the error message says
    which parts and ports were already changed, and the task reports C(changed=true) when the switch was modified.
  - If the connection drops during a change, the task reports C(changed=true) with C(details.outcome=unknown),
    because the change may have been applied. Run the task again to bring the switch to the requested state.
  - Supports check mode and diff mode.
requirements:
  - ansible.netcommon
options:
  state:
    description:
      - Desired module operation.
      - C(merged) applies the supplied interface settings incrementally without removing unspecified configuration.
      - C(replaced) treats the supplied values as authoritative for the targeted interfaces and resets omitted LLDP
        attributes to device defaults.
      - C(overridden) behaves like C(replaced) for the listed interfaces and resets LLDP settings on discovered
        interfaces that are not provided.
      - C(deleted) resets the listed interfaces to LLDP defaults. Without C(config) (or with an empty list) it
        resets every discovered interface.
      - C(gathered) returns current LLDP interface configuration without applying changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    aliases:
      - interfaces
    description:
      - Interface LLDP definitions to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional for C(deleted), which resets every discovered interface when it is omitted.
      - Named C(interfaces) up to version 1.2.1. That name still works as a deprecated alias and will be removed in
        2.0.0.
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - Port identifier in slot:port notation such as C(1:5).
        type: str
        required: true
      transmit_enabled:
        description:
          - Enable or disable LLDP transmit on the port.
        type: bool
      receive_enabled:
        description:
          - Enable or disable LLDP receive on the port.
        type: bool
      advertise:
        description:
          - LLDP TLVs advertised on the port.
        type: dict
        suboptions:
          system_capabilities:
            description:
              - Advertise the system capabilities TLV.
            type: bool
          system_description:
            description:
              - Advertise the system description TLV.
            type: bool
          system_name:
            description:
              - Advertise the system name TLV.
            type: bool
          port_description:
            description:
              - Advertise the port description TLV.
            type: bool
          management_address:
            description:
              - Advertise the management address TLV.
            type: bool
          med_capabilities:
            description:
              - Advertise the MED capabilities TLV.
            type: bool
          med_power:
            description:
              - Advertise the MED power TLV.
            type: bool
          dot3_mac_phy:
            description:
              - Advertise the 802.3 MAC or PHY TLV.
            type: bool
          location:
            description:
              - Advertise the MED location TLV.
            type: bool
          network_policy:
            description:
              - Advertise the MED network policy TLV.
            type: bool
          inventory:
            description:
              - Advertise the MED inventory TLV.
            type: bool
      location:
        description:
          - MED location information for the port.
        type: dict
        suboptions:
          civic_address:
            description:
              - Civic address location string in Fabric Engine civic address format, starting with C(country-code)
                followed by two characters, then at least one more label and its value.
              - Supported labels are C(country-code), C(additional-code), C(additional-information), C(apartment),
                C(block), C(building), C(city), C(city-district), C(county), C(floor), C(house-number),
                C(house-number-suffix), C(landmark), C(leading-street-direction), C(name), C(place-type), C(pobox),
                C(postal-community-name), C(postal-zip-code), C(room-number), C(state), C(street), C(street-suffix)
                and C(trailing-street-suffix).
              - The value must start with C(country-code) followed by exactly two letters, and at least one other
                supported label must follow; C(country-code) alone is rejected.
              - Any other label (for example C(postal-code), C(province-state), C(postal-zip), C(room), C(unit) or
                C(language)) is rejected before any request is sent, because the device would silently drop it or
                append it to the previous value and advertise a wrong emergency location.
              - An unquoted value runs up to the next supported label, so C(city San Jose) is valid. Quote a value that
                contains a label-like word, for example C(street "Main room"); the word directly after a label is
                always taken as part of its value.
              - Labels and quoted values may appear in any order; the comparison with the device is order and
                quoting independent.
            type: str
          ecs_elin:
            description:
              - Emergency line identification number.
            type: str
          coordinate:
            description:
              - Coordinate-based location string.
            type: str
      med_policy:
        description:
          - Authoritative MED network policy entries for the interface.
          - When provided, the module replaces the full MED policy list for the port.
        type: list
        elements: dict
        suboptions:
          type:
            description:
              - MED application type.
            type: str
            required: true
            choices:
              - GUEST_VOICE
              - GUEST_VOICE_SIGNALING
              - SOFT_PHONE_VOICE
              - STREAMING_VIDEO
              - VIDEO_CONFERENCING
              - VIDEO_SIGNALING
              - VOICE
              - VOICE_SIGNALING
          dscp:
            description:
              - DSCP value advertised for the policy.
            type: int
            required: true
          priority:
            description:
              - 802.1p priority advertised for the policy.
            type: int
            required: true
          tagged:
            description:
              - Whether the policy VLAN is tagged.
            type: bool
            required: true
          vlan_id:
            description:
              - VLAN identifier associated with the policy.
            type: int
            required: true
  gather_filter:
    description:
      - Optional list of interface names to limit gathered configuration or state output.
    type: list
    elements: str
  gather_state:
    description:
      - When true, include operational LLDP neighbor state from C(/v0/state/lldp/ports/{port}).
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
# ## Verify current LLDP configuration:
# # show lldp port config
# # show lldp med network-policy
#
# ## For MED power advertisement, use a PoE-capable copper port.

# -------------------------------------------------------------------------
# Task 1: Merge basic LLDP advertisement settings
# Description:
#   - Enable LLDP on a port and adjust selected advertisement TLVs without
#     replacing unspecified settings.
# -------------------------------------------------------------------------
# - name: "Task 1: Merge LLDP settings on port 1:10"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Ensure LLDP advertises system identity information
  extreme.fe.extreme_fe_lldp_interfaces:
    state: merged
    config:
      - name: "1:10"
        transmit_enabled: true
        receive_enabled: true
        advertise:
          system_name: true
          system_description: true
          inventory: true

# -------------------------------------------------------------------------
# Task 2: Replace full LLDP interface configuration
# Description:
#   - Enforce a complete LLDP profile for the interface, including MED policy
#     and location settings.
# -------------------------------------------------------------------------
# - name: "Task 2: Replace LLDP settings on port 1:10"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Set authoritative LLDP interface configuration
  extreme.fe.extreme_fe_lldp_interfaces:
    state: replaced
    config:
      - name: "1:10"
        transmit_enabled: true
        receive_enabled: true
        advertise:
          system_capabilities: true
          system_description: true
          system_name: true
          port_description: true
          management_address: true
          med_capabilities: true
          med_power: true
          dot3_mac_phy: true
          location: true
          network_policy: true
          inventory: true
        location:
          civic_address: "country-code US state NC city Raleigh street Main postal-zip-code 27601 building 100"
          ecs_elin: "5551234567"
        med_policy:
          - type: VOICE
            dscp: 46
            priority: 5
            tagged: true
            vlan_id: 20

# -------------------------------------------------------------------------
# Task 3: Reset LLDP interface configuration
# Description:
#   - Restore LLDP settings to defaults for the listed interface.
# -------------------------------------------------------------------------
# - name: "Task 3: Reset LLDP settings on port 1:10"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Reset LLDP port settings to defaults
  extreme.fe.extreme_fe_lldp_interfaces:
    state: deleted
    config:
      - name: "1:10"

# -------------------------------------------------------------------------
# Task 4: Gather LLDP interface configuration and state
# Description:
#   - Read the current LLDP port configuration and neighbor state.
# -------------------------------------------------------------------------
# - name: "Task 4: Gather LLDP settings for ports 1:10 and 1:11"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect LLDP interface configuration and state
  extreme.fe.extreme_fe_lldp_interfaces:
    state: gathered
    gather_state: true
    gather_filter:
      - "1:10"
      - "1:11"
  register: lldp_interfaces_info
"""

RETURN = r"""
---
changed:
  description: Indicates whether any configuration changes were made.
  returned: always
  type: bool
gathered:
  description:
    - LLDP interface configuration gathered from the device.
    - Each entry has the shape of a C(config) entry (C(name), C(transmit_enabled), C(receive_enabled), C(advertise),
      C(location), C(med_policy)), so the list can be applied back as C(config) without a change.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
interfaces_settings:
  description:
    - Normalized LLDP settings for gathered or modified interfaces.
    - Each entry holds C(name) and the interface settings under C(settings).
    - Under C(state=gathered) this lists the C(gathered) interfaces in that form, which is what the
      module returned for that state up to 1.2.1. That form is deprecated and
      will be removed in 2.0.0 - use C(gathered).
  returned: when interfaces are gathered or changed
  type: list
  elements: dict
interface_updates:
  description: Interface names updated during the run.
  returned: when configuration changes occur
  type: list
  elements: str
interface_removals:
  description: Interface names reset to defaults when using C(state=deleted) or C(state=overridden).
  returned: when interfaces are reset
  type: list
  elements: str
interfaces_state:
  description: LLDP operational state per interface when C(gather_state=true).
  returned: when gather_state is true
  type: list
  elements: dict
api_responses:
  description:
    - Raw API responses captured during execution, for debugging.
    - Deprecated and will be removed in 2.0.0.
    - Use C(before) and C(after) for the configuration before and after a change, C(gathered) for C(state=gathered), and
      C(interfaces_state) for the operational state returned when C(gather_state=true). The normalized snapshots do not
      contain the raw responses.
  returned: always
  type: dict
before:
  description:
    - LLDP settings for every targeted interface as they were before the task ran.
    - Each entry has the shape of a C(config) entry, like C(gathered).
    - Covers the interfaces named in C(config) plus any that C(state=overridden) reset, or every discovered
      interface for C(state=deleted) without C(config).
    - Returned whether or not anything changed.
  returned: when state is not gathered
  type: list
  elements: dict
after:
  description:
    - LLDP settings for every targeted interface once the task has run.
    - Each entry has the shape of a C(config) entry, like C(gathered).
    - In check mode this is the predicted state rather than a device read.
  returned: when state is not gathered
  type: list
  elements: dict
"""

import re
from collections.abc import Iterable
from copy import deepcopy
from typing import Any
from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import is_answer_unknown_code

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

ARGUMENT_SPEC = {
    "state": {
        "type": "str",
        "choices": [STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED, STATE_GATHERED],
        "default": STATE_MERGED,
    },
    # Renamed from 'interfaces' to 'config' so every resource module in the
    # collection uses the same parameter name. The old name stays as a
    # deprecated alias, so existing playbooks keep working and Ansible
    # resolves both to module.params["config"].
    "config": {
        "type": "list",
        "elements": "dict",
        "aliases": ["interfaces"],
        "deprecated_aliases": [{"name": "interfaces", "version": "2.0.0", "collection_name": "extreme.fe"}],
        "options": {
            "name": {"type": "str", "required": True},
            "transmit_enabled": {"type": "bool"},
            "receive_enabled": {"type": "bool"},
            "advertise": {
                "type": "dict",
                "options": {
                    "system_capabilities": {"type": "bool"},
                    "system_description": {"type": "bool"},
                    "system_name": {"type": "bool"},
                    "port_description": {"type": "bool"},
                    "management_address": {"type": "bool"},
                    "med_capabilities": {"type": "bool"},
                    "med_power": {"type": "bool"},
                    "dot3_mac_phy": {"type": "bool"},
                    "location": {"type": "bool"},
                    "network_policy": {"type": "bool"},
                    "inventory": {"type": "bool"},
                },
            },
            "location": {
                "type": "dict",
                "options": {
                    "civic_address": {"type": "str"},
                    "ecs_elin": {"type": "str"},
                    "coordinate": {"type": "str"},
                },
            },
            "med_policy": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "type": {
                        "type": "str",
                        "required": True,
                        "choices": [
                            "GUEST_VOICE",
                            "GUEST_VOICE_SIGNALING",
                            "SOFT_PHONE_VOICE",
                            "STREAMING_VIDEO",
                            "VIDEO_CONFERENCING",
                            "VIDEO_SIGNALING",
                            "VOICE",
                            "VOICE_SIGNALING",
                        ],
                    },
                    "dscp": {"type": "int", "required": True},
                    "priority": {"type": "int", "required": True},
                    "tagged": {"type": "bool", "required": True},
                    "vlan_id": {"type": "int", "required": True},
                },
            },
        },
    },
    "gather_filter": {"type": "list", "elements": "str"},
    "gather_state": {"type": "bool", "default": False},
}

LLDP_CONFIG_PATH = "/v0/configuration/lldp"
LLDP_PORT_CONFIG_TEMPLATE = "/v0/configuration/lldp/ports/{port}"
LLDP_PORT_MED_POLICY_TEMPLATE = "/v0/configuration/lldp/ports/{port}/med-policy"
LLDP_PORT_STATE_TEMPLATE = "/v0/state/lldp/ports/{port}"
PORT_CAPABILITIES_PATH = "/v0/state/capabilities/system/ports"

ADVERTISE_FIELD_MAP = {
    "system_capabilities": "systemCapabilities",
    "system_description": "systemDescription",
    "system_name": "systemName",
    "port_description": "portDescription",
    "management_address": "managementAddress",
    "med_capabilities": "medCapabilities",
    "med_power": "medPower",
    "dot3_mac_phy": "dot3MacPhy",
    "location": "location",
    "network_policy": "networkPolicy",
    "inventory": "inventory",
}

LOCATION_FIELD_MAP = {"civic_address": "civicAddress", "ecs_elin": "ecsElin", "coordinate": "coordinate"}

MED_POLICY_FIELD_MAP = {"type": "type", "dscp": "dscp", "priority": "priority", "tagged": "tagged", "vlan_id": "vlanId"}

# `deleted` without config resets every discovered interface instead.
REQUIRES_INTERFACES = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}


class FeLldpInterfacesError(Exception):
    """Raised for LLDP interface validation and response issues."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        changed: bool = False,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        # Top-level fail_json keys (code, err) of a transport failure.
        self.extra = extra or {}
        # True when the device was already changed before this error.
        self.changed = changed

    def to_fail_kwargs(self) -> dict[str, Any]:
        data: dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        data.update(self.extra)
        return data


def _extract_error(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if isinstance(code, int) and code >= 400:
        return {"code": code, "message": message or "Device reported an LLDP error", "payload": payload}
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return {"message": message or "Device reported LLDP errors", "errors": errors, "payload": payload}
    return None


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: dict[str, Any],
    response_key: str,
    payload: Any | None = None,
    expect_content: bool = True,
) -> Any:
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        # Raised rather than failed here so a failure after an earlier write
        # can say what was applied; run_module() fails with the same msg, code
        # and err, plus api_responses.
        code = getattr(exc, "code", None)
        if method != "GET" and is_answer_unknown_code(code):
            # No answer (a lost connection): the write may have been applied.
            raise FeLldpInterfacesError(
                "%s. The %s %s may have been applied before the answer was lost; check the port on the device."
                % (to_text(exc).rstrip("."), method, path),
                details={"outcome": "unknown", "resource": path},
                extra={"code": None, "err": getattr(exc, "err", None)},
                changed=True,
            )
        raise FeLldpInterfacesError(to_text(exc), extra={"code": code, "err": getattr(exc, "err", None)})

    api_responses[response_key] = response

    if response in (None, ""):
        return None if not expect_content else {}

    if isinstance(response, bytes):
        response = to_text(response)
        api_responses[response_key] = response

    if isinstance(response, dict):
        error = _extract_error(response)
        if error:
            raise FeLldpInterfacesError(to_text(error.get("message")), details=error)

    return response


def _get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeLldpInterfacesError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def _normalize_port_name(raw: Any) -> str:
    if not isinstance(raw, str):
        raise FeLldpInterfacesError("Interface name must be a string in slot:port format")
    value = raw.strip()
    if not value:
        raise FeLldpInterfacesError("Interface name must not be empty")
    return value


def _is_poe_capable(capability: dict[str, Any]) -> bool:
    caps = capability.get("capabilities")
    if not isinstance(caps, dict):
        return False
    return bool(caps.get("poe") or caps.get("poeMaxPower") is not None or caps.get("poeMaxClassification") is not None)


def _default_interface_settings(is_poe_capable: bool) -> dict[str, Any]:
    return {
        "transmit_enabled": True,
        "receive_enabled": True,
        "advertise": {
            "system_capabilities": True,
            "system_description": True,
            "system_name": True,
            "port_description": True,
            "management_address": True,
            "med_capabilities": True,
            "med_power": bool(is_poe_capable),
            "dot3_mac_phy": False,
            "location": True,
            "network_policy": True,
            "inventory": True,
        },
        "location": {},
        "med_policy": [],
    }


def _normalize_med_policy_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for param, rest_key in MED_POLICY_FIELD_MAP.items():
        value = item.get(rest_key) if rest_key in item else item.get(param)
        if value is None:
            continue
        if param in {"dscp", "priority", "vlan_id"}:
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise FeLldpInterfacesError(f"MED policy field '{param}' must be an integer", details={"policy": item})
        if param == "dscp" and not (0 <= value <= 63):
            raise FeLldpInterfacesError("MED policy dscp must be between 0 and 63", details={"policy": item})
        if param == "priority" and not (0 <= value <= 7):
            raise FeLldpInterfacesError("MED policy priority must be between 0 and 7", details={"policy": item})
        if param == "vlan_id" and not (0 <= value <= 4059):
            raise FeLldpInterfacesError("MED policy vlan_id must be between 0 and 4059", details={"policy": item})
        normalized[param] = value
    required = {"type", "dscp", "priority", "tagged", "vlan_id"}
    missing = sorted(required.difference(normalized.keys()))
    if missing:
        raise FeLldpInterfacesError(
            "Each MED policy entry must provide type, dscp, priority, tagged, and vlan_id",
            details={"missing": missing, "policy": item},
        )
    return normalized


def _sort_med_policy(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in entries],
        key=lambda item: (
            str(item.get("type", "")),
            int(item.get("vlan_id", 0)),
            int(item.get("dscp", 0)),
            int(item.get("priority", 0)),
            bool(item.get("tagged", False)),
        ),
    )


# Civic address labels Fabric Engine accepts (OpenAPI schema LldpLocation,
# field civicAddress). country-code is required by the device and accepted
# although the schema list omits it.
CIVIC_ADDRESS_FIELDS = {
    "country-code",
    "additional-code",
    "additional-information",
    "apartment",
    "block",
    "building",
    "city",
    "city-district",
    "county",
    "floor",
    "house-number",
    "house-number-suffix",
    "landmark",
    "leading-street-direction",
    "name",
    "place-type",
    "pobox",
    "postal-community-name",
    "postal-zip-code",
    "room-number",
    "state",
    "street",
    "street-suffix",
    "trailing-street-suffix",
}

# Labels earlier module versions accepted but the device does not. The device
# answers 204 and then drops the label or glues it onto the preceding value,
# which silently corrupts the advertised emergency location. The value is the
# obvious replacement (None where there is no clear one).
CIVIC_ADDRESS_REJECTED_LABELS = {
    "additional-info": "additional-information",
    "branch-road-name": None,
    "city-division": "city-district",
    "language": None,
    "neighborhood": None,
    "post-office-box": "pobox",
    "postal-zip": "postal-zip-code",
    "primary-road-name": None,
    "province-state": "state",
    "road-section": None,
    "room": "room-number",
    "seat": None,
    "street-group": None,
    "street-name-post-modifier": None,
    "street-name-pre-modifier": None,
    "sub-branch-road-name": None,
    "type-of-place": "place-type",
    "unit": None,
}

# Splits a civic address into quoted values (a quote runs to its closing quote,
# or to the end when unterminated) and bare whitespace-separated tokens.
_CIVIC_TOKEN_RE = re.compile(r'"[^"]*(?:"|$)|\S+')
# Shape of an attempted label: hyphenated words written all in lowercase
# (postal-code) or all in uppercase (POSTAL-COD). Title-case words such as
# Saint-Denis or Winston-Salem are deliberately not matched: they are real
# place names and cannot be told apart from a mistyped label.
_CIVIC_LABEL_SHAPE_RE = re.compile(r"^(?:[a-z]+(?:-[a-z]+)+|[A-Z]+(?:-[A-Z]+)+)$")

_CIVIC_RULE = (
    "a Fabric Engine civic address must always start with the 'country-code' label followed by 2 characters, "
    "and at least one other supported label must also be set (for example: "
    "country-code RO city Bucharest street Avenue building 10)"
)
_CIVIC_QUOTE_HINT = 'Quote the value if it is genuinely a value word, for example street "Main room".'


def _unsupported_label_error(label: str) -> str:
    """Build the message for an unsupported label (with a replacement hint where one is clear)."""
    hint = CIVIC_ADDRESS_REJECTED_LABELS.get(label)
    did_you_mean = " Did you mean '%s'?" % hint if hint else ""
    return (
        "it uses the unsupported label '%s'; Fabric Engine would silently drop it or attach it to the "
        "previous value.%s %s Supported labels: %s"
        % (label, did_you_mean, _CIVIC_QUOTE_HINT, ", ".join(sorted(CIVIC_ADDRESS_FIELDS)))
    )


def _civic_token_kind(token: str) -> str:
    """Classify an unquoted token that follows a complete value: 'label', 'unsupported' or 'value'."""
    lowered = token.lower()
    if lowered in CIVIC_ADDRESS_FIELDS:
        return "label"
    if lowered in CIVIC_ADDRESS_REJECTED_LABELS or _CIVIC_LABEL_SHAPE_RE.match(token):
        return "unsupported"
    return "value"


def _is_unsupported_label_first_value(token: str) -> bool:
    """Tell whether an unquoted token right after a label is a mistyped hyphenated label.

    Single words such as Room or unit stay valid first values; only hyphenated tokens
    (postal-code, POSTAL-COD, postal-zip, province-state) are treated as labels.
    """
    lowered = token.lower()
    if "-" not in token or lowered in CIVIC_ADDRESS_FIELDS:
        return False
    return lowered in CIVIC_ADDRESS_REJECTED_LABELS or bool(_CIVIC_LABEL_SHAPE_RE.match(token))


def _civic_field_text(tokens: list[str]) -> str:
    """Return the text of a field value with quotes removed, so an empty "" or " " counts as no value."""
    return " ".join(token.strip('"').strip() for token in tokens).strip()


def _split_civic_fields(tokens: list[str]) -> tuple[list[list[Any]], str | None]:
    """Group tokens into [label, [value tokens]] pairs; return (fields, error).

    A token directly after a label is part of its value (so street Room is fine),
    unless it is itself a supported label in any letter case (the value is missing) or a
    hyphenated unsupported label such as postal-code (an error).
    Later unquoted tokens are labels when supported, errors when they look like an
    unsupported label, and value text otherwise (device values run to the next label).
    """
    fields: list[list[Any]] = []
    for token in tokens:
        quoted = token.startswith('"')
        if fields and not fields[-1][1]:
            # Labels are case-insensitive everywhere else (_civic_token_kind, _parse_civic_address), so
            # CITY STATE CA must be caught here too. A label word that really is the value must be quoted.
            if not quoted and token.lower() in CIVIC_ADDRESS_FIELDS:
                return fields, "the label '%s' has no value" % fields[-1][0]
            if not quoted and _is_unsupported_label_first_value(token):
                return fields, _unsupported_label_error(token.lower())
            fields[-1][1].append(token)
            continue
        kind = "value" if quoted or not fields else _civic_token_kind(token)
        if kind == "unsupported":
            return fields, _unsupported_label_error(token.lower())
        if kind == "label" or not fields:
            fields.append([token.lower(), []])
        else:
            fields[-1][1].append(token)
    return fields, None


def _validate_civic_address(value: str) -> str | None:
    """Validate a raw civic address against the documented Fabric Engine grammar.

    Returns an error message (without the interface prefix) or None when valid.
    Quoted values are always values; see _split_civic_fields for the label rules.
    """
    tokens = _CIVIC_TOKEN_RE.findall(value)
    for token in tokens:
        if token.startswith('"') and not (len(token) > 1 and token.endswith('"')):
            return "it contains an unterminated double quote"
    if not tokens or tokens[0].lower() != "country-code":
        return "it does not start with 'country-code'; %s" % _CIVIC_RULE
    fields, error = _split_civic_fields(tokens)
    if error:
        return error
    # Every label needs real text: a bare "" (or whitespace in quotes) is not a value.
    for label, value_tokens in fields:
        if not _civic_field_text(value_tokens):
            return "the label '%s' has no value" % label
    country = _civic_field_text(fields[0][1])
    if len(country) != 2 or not (country.isascii() and country.isalpha()):
        return "the country-code value '%s' is not exactly 2 letters; %s" % (country, _CIVIC_RULE)
    if len(fields) < 2:
        return "country-code alone is not enough; %s" % _CIVIC_RULE
    return None


def _validate_civic_addresses(entries: Any, state: str) -> None:
    """Reject malformed civic addresses before any request is made.

    Only the states that write a location are checked (merged, replaced,
    overridden). Raises FeLldpInterfacesError naming the interface and the problem.
    """
    if state not in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
        return
    for item in entries or []:
        location = item.get("location") if isinstance(item, dict) else None
        civic = location.get("civic_address") if isinstance(location, dict) else None
        if not civic or not isinstance(civic, str):
            continue
        problem = _validate_civic_address(civic)
        if problem is None:
            continue
        raise FeLldpInterfacesError(
            "Interface %s: invalid location.civic_address: %s" % (item.get("name"), problem),
            details={"name": item.get("name"), "problem": problem},
        )


def _parse_civic_address(value: str) -> dict[str, str]:
    """Parse a civic address string into a dict of field-value pairs (sorted by key).

    Handles both user-provided format and device-returned format:
      User:   country-code RO city Bucharest street Victoriei building 10
      Device: country-code RO building "10" city "Bucharest" street "Victoriei"
    """
    if not value or not isinstance(value, str):
        return {}
    tokens = value.strip().split()
    result: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        # Check for multi-word field names (e.g. "country-code", "house-number-suffix")
        key = None
        for length in (3, 2, 1):
            candidate = "-".join(tokens[i : i + length])
            if candidate.lower() in CIVIC_ADDRESS_FIELDS:
                key = candidate.lower()
                i += length
                break
        if key is None:
            i += 1
            continue
        # Collect the value — may be quoted or unquoted
        if i >= len(tokens):
            break
        if tokens[i].startswith('"'):
            # Quoted value: collect tokens until closing quote
            parts = [tokens[i].lstrip('"')]
            if tokens[i].endswith('"') and len(tokens[i]) > 1:
                result[key] = tokens[i].strip('"')
                i += 1
                continue
            i += 1
            while i < len(tokens):
                if tokens[i].endswith('"'):
                    parts.append(tokens[i].rstrip('"'))
                    i += 1
                    break
                parts.append(tokens[i])
                i += 1
            result[key] = " ".join(parts)
        else:
            # Unquoted: collect tokens until next known field name
            parts = []
            while i < len(tokens):
                # Look ahead: is this token the start of a new field?
                is_field = False
                for length in (3, 2, 1):
                    candidate = "-".join(tokens[i : i + length])
                    if candidate.lower() in CIVIC_ADDRESS_FIELDS:
                        is_field = True
                        break
                if is_field:
                    break
                parts.append(tokens[i])
                i += 1
            result[key] = " ".join(parts)
    return dict(sorted(result.items()))


def _locations_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Compare two location dicts with semantic civic_address comparison."""
    left = left or {}
    right = right or {}
    # Compare non-civic fields directly
    for key in ("ecs_elin", "coordinate"):
        if left.get(key) != right.get(key):
            return False
    # Semantic comparison for civic_address
    left_civic = left.get("civic_address", "")
    right_civic = right.get("civic_address", "")
    if (not left_civic) and (not right_civic):
        return True
    if (not left_civic) or (not right_civic):
        return False
    return _parse_civic_address(left_civic) == _parse_civic_address(right_civic)


def _normalize_current_settings(payload: Any, is_poe_capable: bool) -> dict[str, Any]:
    base = _default_interface_settings(is_poe_capable)
    if not isinstance(payload, dict):
        return base

    if "transmitEnabled" in payload:
        base["transmit_enabled"] = bool(payload.get("transmitEnabled"))
    if "receiveEnabled" in payload:
        base["receive_enabled"] = bool(payload.get("receiveEnabled"))

    advertise = payload.get("advertise")
    if isinstance(advertise, dict):
        for param, rest_key in ADVERTISE_FIELD_MAP.items():
            if rest_key in advertise and advertise.get(rest_key) is not None:
                base["advertise"][param] = advertise.get(rest_key)

    location = payload.get("location")
    if isinstance(location, dict):
        normalized_location: dict[str, Any] = {}
        for param, rest_key in LOCATION_FIELD_MAP.items():
            value = location.get(rest_key)
            if value not in (None, ""):
                # Strip the device-prepended CLI prefix from civic_address
                # Device returns: "ldp location-identification civic-address <fields>"
                # We store only the fields part: "<fields>"
                if param == "civic_address" and isinstance(value, str):
                    CLI_PREFIX = "ldp location-identification civic-address "
                    if value.startswith(CLI_PREFIX):
                        value = value[len(CLI_PREFIX) :]
                normalized_location[param] = value
        base["location"] = normalized_location

    med_policy = payload.get("medPolicy")
    if isinstance(med_policy, list):
        base["med_policy"] = _sort_med_policy(
            _normalize_med_policy_item(item) for item in med_policy if isinstance(item, dict)
        )

    return base


def _normalize_tx_rx(item: dict[str, Any], name: str, normalized: dict[str, Any]) -> None:
    """Mirror transmit/receive onto each other and reject a mismatched pair.

    Fabric Engine requires the two flags to agree, so supplying one is taken as
    supplying both.
    """
    tx_value = item.get("transmit_enabled")
    rx_value = item.get("receive_enabled")
    tx_present = tx_value is not None
    rx_present = rx_value is not None
    if tx_present and not rx_present:
        rx_value = tx_value
        rx_present = True
    elif rx_present and not tx_present:
        tx_value = rx_value
        tx_present = True
    if tx_present and rx_present and tx_value != rx_value:
        raise FeLldpInterfacesError(
            "transmit_enabled and receive_enabled must use the same value on Fabric Engine", details={"name": name}
        )
    if tx_present:
        normalized["transmit_enabled"] = bool(tx_value)
    if rx_present:
        normalized["receive_enabled"] = bool(rx_value)


def _normalize_input_advertise(item: dict[str, Any], name: str, normalized: dict[str, Any]) -> None:
    """Copy across the advertise flags the caller actually supplied."""
    advertise = item.get("advertise")
    if advertise is None:
        return
    if not isinstance(advertise, dict):
        raise FeLldpInterfacesError("advertise must be a dictionary", details={"name": name})
    normalized_advertise: dict[str, Any] = {}
    for param in ADVERTISE_FIELD_MAP:
        if param in advertise and advertise.get(param) is not None:
            normalized_advertise[param] = advertise.get(param)
    if normalized_advertise:
        normalized["advertise"] = normalized_advertise


def _normalize_input_location(item: dict[str, Any], name: str, normalized: dict[str, Any]) -> None:
    """Copy across the location fields, enforcing the ecs_elin length limit."""
    location = item.get("location")
    if location is None:
        return
    if not isinstance(location, dict):
        raise FeLldpInterfacesError("location must be a dictionary", details={"name": name})
    normalized_location: dict[str, Any] = {}
    for param in LOCATION_FIELD_MAP:
        value = location.get(param)
        if value in (None, ""):
            continue
        if param == "ecs_elin" and len(str(value)) > 25:
            raise FeLldpInterfacesError("location.ecs_elin must be 25 characters or less", details={"name": name})
        normalized_location[param] = value
    normalized["location"] = normalized_location


def _normalize_input_med_policy(item: dict[str, Any], name: str, normalized: dict[str, Any]) -> None:
    """Normalise and sort the MED policy list."""
    med_policy = item.get("med_policy")
    if med_policy is None:
        return
    if not isinstance(med_policy, list):
        raise FeLldpInterfacesError("med_policy must be a list", details={"name": name})
    normalized["med_policy"] = _sort_med_policy(
        _normalize_med_policy_item(entry) for entry in med_policy if isinstance(entry, dict)
    )


def _normalize_input_entry(item: dict[str, Any], name: str, state: str) -> dict[str, Any]:
    """Normalise a single config entry whose name has already been resolved."""
    normalized: dict[str, Any] = {"name": name}
    _normalize_tx_rx(item, name, normalized)
    _normalize_input_advertise(item, name, normalized)
    _normalize_input_location(item, name, normalized)
    _normalize_input_med_policy(item, name, normalized)

    # Only the name survived, so the caller supplied nothing to merge.
    if state == STATE_MERGED and len(normalized) == 1:
        raise FeLldpInterfacesError(
            "At least one LLDP attribute besides 'name' is required for state merged (interface '%s')" % name,
            details={"name": name},
        )
    return normalized


def _normalize_input_interfaces(
    module: AnsibleModule, state: str, discovered: Iterable[str] = ()
) -> list[dict[str, Any]]:
    raw_entries = list(module.params.get("config") or [])
    if state == STATE_DELETED and not raw_entries:
        # No config: reset every discovered interface to its defaults.
        raw_entries = [{"name": name} for name in sorted(discovered)]
    if state in REQUIRES_INTERFACES and not raw_entries:
        raise FeLldpInterfacesError("value of config parameter must not be empty for state %s" % state)

    normalized_entries: list[dict[str, Any]] = []
    seen: set = set()
    for item in raw_entries:
        # Shape and duplicate checks stay ahead of per-field normalisation, so a
        # duplicate entry is still reported as such rather than as whatever
        # field error it happens to also contain.
        if not isinstance(item, dict):
            raise FeLldpInterfacesError("Each interface entry must be a dictionary")
        name = _normalize_port_name(item.get("name"))
        if name in seen:
            raise FeLldpInterfacesError(
                "Interface '%s' is listed more than once in 'config'; list each interface once" % name,
                details={"name": name},
            )
        seen.add(name)
        normalized_entries.append(_normalize_input_entry(item, name, state))

    return normalized_entries


def _overlay_settings(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key in ("transmit_enabled", "receive_enabled"):
        if key in updates:
            result[key] = updates[key]
    if "advertise" in updates:
        result.setdefault("advertise", {})
        result["advertise"].update(updates.get("advertise") or {})
    if "location" in updates:
        result.setdefault("location", {})
        result["location"].update(updates.get("location") or {})
    if "med_policy" in updates:
        result["med_policy"] = _sort_med_policy(updates.get("med_policy") or [])
    return result


def _build_target_settings(
    entry: dict[str, Any], current: dict[str, Any], defaults: dict[str, Any], state: str
) -> dict[str, Any]:
    if state == STATE_MERGED:
        target = _overlay_settings(current, entry)
    elif state in (STATE_REPLACED, STATE_OVERRIDDEN):
        target = _overlay_settings(defaults, entry)
    elif state == STATE_DELETED:
        target = deepcopy(defaults)
    else:
        target = deepcopy(current)
    target["med_policy"] = _sort_med_policy(target.get("med_policy") or [])
    return target


def _settings_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("transmit_enabled") != right.get("transmit_enabled"):
        return False
    if left.get("receive_enabled") != right.get("receive_enabled"):
        return False
    # When either LLDP flag is explicitly disabled, _build_config_payload() returns
    # early without advertise/location, so those fields can never converge.  Skip
    # their comparison to avoid perpetual changed=True.  The MED policy goes with
    # them: _normalize_tx_rx() keeps the two flags equal - mirroring a lone value
    # and rejecting a mismatched pair - so one being off means LLDP is off, and
    # _apply_interface() skips the policy write too.
    if right.get("transmit_enabled") is False or right.get("receive_enabled") is False:
        return True
    return (
        (left.get("advertise") or {}) == (right.get("advertise") or {})
        and _locations_equal(left.get("location"), right.get("location"))
        and _sort_med_policy(left.get("med_policy") or []) == _sort_med_policy(right.get("med_policy") or [])
    )


def _port_config_path(port_name: str) -> str:
    return LLDP_PORT_CONFIG_TEMPLATE.format(port=quote(port_name, safe=""))


def _port_med_policy_path(port_name: str) -> str:
    return LLDP_PORT_MED_POLICY_TEMPLATE.format(port=quote(port_name, safe=""))


def _port_state_path(port_name: str) -> str:
    return LLDP_PORT_STATE_TEMPLATE.format(port=quote(port_name, safe=""))


def _build_config_payload(target: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "transmitEnabled": target.get("transmit_enabled", True),
        "receiveEnabled": target.get("receive_enabled", True),
    }
    if not payload["transmitEnabled"] or not payload["receiveEnabled"]:
        return payload

    advertise_payload: dict[str, Any] = {}
    for param, rest_key in ADVERTISE_FIELD_MAP.items():
        advertise_payload[rest_key] = target.get("advertise", {}).get(param)
    payload["advertise"] = advertise_payload

    location_payload: dict[str, Any] = {}
    for param, rest_key in LOCATION_FIELD_MAP.items():
        value = target.get("location", {}).get(param)
        if value not in (None, ""):
            location_payload[rest_key] = value
    if location_payload:
        payload["location"] = location_payload
    return payload


def _build_med_policy_payload(target: dict[str, Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for entry in _sort_med_policy(target.get("med_policy") or []):
        item: dict[str, Any] = {}
        for param, rest_key in MED_POLICY_FIELD_MAP.items():
            item[rest_key] = entry.get(param)
        payload.append(item)
    return payload


def _project_applied_settings(current: dict[str, Any] | None, target: dict[str, Any]) -> dict[str, Any]:
    """Predict what a real run would leave on one port.

    _build_config_payload() drops advertise and location once either LLDP flag
    is off, and the MED policy PUT is skipped when transmit is off, so the
    device keeps whatever it already had for those fields. Check mode has to
    carry them over or it reports a target the request never submits.
    """
    projected = deepcopy(target)
    if current is None:
        return projected
    transmit = target.get("transmit_enabled", True)
    receive = target.get("receive_enabled", True)
    if not transmit or not receive:
        for field in ("advertise", "location"):
            if field in current:
                projected[field] = deepcopy(current[field])
    if not transmit and "med_policy" in current:
        projected["med_policy"] = deepcopy(current["med_policy"])
    return projected


def _fetch_capabilities(
    module: AnsibleModule, connection: Connection, api_responses: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    data = (
        _call_api(
            module,
            connection,
            method="GET",
            path=PORT_CAPABILITIES_PATH,
            api_responses=api_responses,
            response_key="capabilities",
        )
        or []
    )
    if not isinstance(data, list):
        raise FeLldpInterfacesError("Unexpected response when retrieving port capabilities", details={"payload": data})
    capabilities: dict[str, dict[str, Any]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        port = entry.get("port")
        if isinstance(port, str):
            capabilities[port] = entry
    return capabilities


def _fetch_all_interfaces(
    module: AnsibleModule,
    connection: Connection,
    capabilities: dict[str, dict[str, Any]],
    api_responses: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    data = (
        _call_api(
            module,
            connection,
            method="GET",
            path=LLDP_CONFIG_PATH,
            api_responses=api_responses,
            response_key="configuration",
        )
        or {}
    )
    if not isinstance(data, dict):
        raise FeLldpInterfacesError("Unexpected response when retrieving LLDP configuration", details={"payload": data})

    interfaces: dict[str, dict[str, Any]] = {}
    for entry in data.get("ports") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("portName")
        if not isinstance(name, str):
            continue
        settings = entry.get("settings")
        is_poe_capable_flag = _is_poe_capable(capabilities.get(name, {}))
        norm_name = _normalize_port_name(name)
        normalized = _normalize_current_settings(settings, is_poe_capable_flag)
        interfaces[norm_name] = normalized
    return interfaces


def _fetch_single_interface(
    module: AnsibleModule,
    connection: Connection,
    port_name: str,
    is_poe_capable_flag: bool,
    api_responses: dict[str, Any],
    response_key: str,
) -> dict[str, Any]:
    data = (
        _call_api(
            module,
            connection,
            method="GET",
            path=_port_config_path(port_name),
            api_responses=api_responses,
            response_key=response_key,
        )
        or {}
    )
    return _normalize_current_settings(data, is_poe_capable_flag)


def _config_entry(name: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Return one interface in the shape of a `config` entry (name plus its settings)."""
    entry: dict[str, Any] = {"name": name}
    entry.update(deepcopy(settings))
    return entry


def _format_output_interfaces(
    port_map: dict[str, dict[str, Any]], names: Iterable[str] | None = None, flat: bool = False
) -> list[dict[str, Any]]:
    """List the selected ports, as `config` entries when *flat*, else in the
    deprecated `{name, settings}` form of `interfaces_settings`."""
    selected_names = list(names) if names is not None else sorted(port_map.keys())
    output: list[dict[str, Any]] = []
    for name in selected_names:
        settings = port_map.get(name)
        if settings is None:
            continue
        output.append(_config_entry(name, settings) if flat else {"name": name, "settings": settings})
    return output


def _snapshot_interfaces(
    port_map: dict[str, dict[str, Any]], defaults_map: dict[str, dict[str, Any]], names: Iterable[str]
) -> list[dict[str, Any]]:
    """Build a before/after snapshot for the given ports.

    Falls back to the port's device defaults when it is absent from port_map,
    so both halves of the pair list the same ports and a newly configured
    interface shows what it looked like beforehand rather than dropping out.
    Each port is a `config` entry, like `gathered`.
    """
    snapshot: list[dict[str, Any]] = []
    for name in names:
        settings = port_map.get(name)
        if settings is None:
            settings = defaults_map.get(name)
        if settings is None:
            continue
        snapshot.append(_config_entry(name, settings))
    return snapshot


def _gather_port_state(
    module: AnsibleModule, connection: Connection, port_names: Iterable[str], api_responses: dict[str, Any]
) -> list[dict[str, Any]]:
    state_responses = api_responses.setdefault("state", {})
    results: list[dict[str, Any]] = []
    for port_name in port_names:
        payload = (
            _call_api(
                module,
                connection,
                method="GET",
                path=_port_state_path(port_name),
                api_responses=state_responses,
                response_key=port_name,
            )
            or {}
        )
        results.append({"name": port_name, "state": payload})
    return results


def _apply_interface(
    module: AnsibleModule,
    connection: Connection,
    port_name: str,
    target: dict[str, Any],
    current_map: dict[str, dict[str, Any]],
    is_poe_capable_flag: bool,
    api_responses: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    operations = api_responses.setdefault("operations", {}).setdefault(port_name, {})
    config_payload = _build_config_payload(target)
    med_policy_payload = _build_med_policy_payload(target)

    if module.check_mode:
        operations["config_put"] = None
        operations["med_policy_put"] = None
        # A port absent from current_map is at its defaults, which is the same
        # baseline the caller compared the target against.
        baseline = current_map.get(port_name)
        if baseline is None:
            baseline = _default_interface_settings(is_poe_capable_flag)
        projected = _project_applied_settings(baseline, target)
        current_map[port_name] = projected
        return deepcopy(projected)

    # Both PUTs always send their full section, so a request that succeeded
    # changed the port only when its section differs from the current settings
    # (a MED-policy-only change still resends the unchanged LLDP settings).
    baseline = current_map.get(port_name)
    if baseline is None:
        baseline = _default_interface_settings(is_poe_capable_flag)
    settings_differ = not _settings_equal(baseline, dict(target, med_policy=baseline.get("med_policy") or []))
    med_policy_differs = _sort_med_policy(baseline.get("med_policy") or []) != _sort_med_policy(
        target.get("med_policy") or []
    )

    _call_api(
        module,
        connection,
        method="PUT",
        path=_port_config_path(port_name),
        payload=config_payload,
        expect_content=False,
        api_responses=operations,
        response_key="config_put",
    )
    applied = ["PUT %s (LLDP settings)" % _port_config_path(port_name)]
    changed = settings_differ
    step = "PUT %s (MED policy)" % _port_med_policy_path(port_name)
    try:
        if config_payload.get("transmitEnabled", True):
            _call_api(
                module,
                connection,
                method="PUT",
                path=_port_med_policy_path(port_name),
                payload=med_policy_payload,
                expect_content=False,
                api_responses=operations,
                response_key="med_policy_put",
            )
            applied.append(step)
            changed = changed or med_policy_differs
        step = "re-read GET %s" % _port_config_path(port_name)
        updated = _fetch_single_interface(module, connection, port_name, is_poe_capable_flag, operations, "after_get")
    except FeLldpInterfacesError as exc:
        # A MED policy PUT without an answer may have been applied (exc.changed).
        raise _after_write_error(port_name, applied, step, exc, changed or exc.changed)
    current_map[port_name] = updated
    operations["operation"] = operation
    operations["submitted"] = {"config": config_payload, "med_policy": med_policy_payload}
    return updated


def _after_write_error(
    port_name: str, applied: list[str], failed: str, exc: FeLldpInterfacesError, changed: bool
) -> FeLldpInterfacesError:
    """Re-raise a failure that follows the port's successful config PUT.

    *applied* lists the requests that succeeded (always the LLDP settings PUT,
    plus the MED policy PUT when the failure is the re-read) and *failed* names
    the request that failed. Both are named in the message. *changed* says
    whether any of the succeeded requests differed from the port's settings;
    when none did, the message says the port was left unchanged.
    """
    outcome = "" if changed else " (the port's configuration was left unchanged)"
    return FeLldpInterfacesError(
        "Interface %s: %s %s applied%s, but the %s failed: %s"
        % (
            port_name,
            " and ".join(applied),
            "were" if len(applied) > 1 else "was",
            outcome,
            failed,
            to_text(exc),
        ),
        details=dict(exc.details, interface=port_name, applied_requests=list(applied), failed_request=failed),
        extra=exc.extra,
        changed=changed,
    )


def _fail_after_writes(module: AnsibleModule, exc: FeLldpInterfacesError, result: dict[str, Any], done: list[str]):
    """Fail the task, reporting changed=true and naming earlier ports when the task already wrote."""
    kwargs = exc.to_fail_kwargs()
    changed = bool(result.get("changed")) or exc.changed
    if done and not module.check_mode:
        kwargs["msg"] = "%s. Interfaces already changed by this task: %s." % (
            to_text(kwargs["msg"]).rstrip().rstrip("."),
            ", ".join(done),
        )
        kwargs["details"] = dict(kwargs.get("details") or {}, changed_interfaces=list(done))
    module.fail_json(changed=changed, api_responses=result.get("api_responses", {}), **kwargs)


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)
    try:
        connection = _get_connection(module)
    except FeLldpInterfacesError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    result: dict[str, Any] = {"changed": False, "api_responses": {}}
    # Ports whose writes all succeeded, in order, for the failure message.
    done: list[str] = []

    try:
        state = module.params.get("state")
        gather_filter = module.params.get("gather_filter") or None
        gather_state = bool(module.params.get("gather_state"))

        # Validate civic_address labels first so an unsupported label never
        # reaches the device (also holds in check mode).
        _validate_civic_addresses(module.params.get("config"), state)

        capabilities = _fetch_capabilities(module, connection, result["api_responses"])
        current_map = _fetch_all_interfaces(module, connection, capabilities, result["api_responses"])
        # Snapshot the device state before anything is applied. _apply_interface
        # mutates current_map in place (in check mode too), so without this copy
        # there would be nothing left to compare the result against.
        before_map = deepcopy(current_map)
        normalized_entries = _normalize_input_interfaces(module, state, current_map.keys())

        if state == STATE_GATHERED:
            selected_names = (
                [_normalize_port_name(item) for item in gather_filter] if gather_filter else sorted(current_map.keys())
            )
            # `gathered` holds `config` entries, so it can be applied back as is;
            # `interfaces_settings` keeps the `{name, settings}` form returned
            # up to 1.2.1 and is deprecated.
            result["gathered"] = _format_output_interfaces(current_map, selected_names, flat=True)
            result["interfaces_settings"] = _format_output_interfaces(current_map, selected_names)
            if gather_state:
                result["interfaces_state"] = _gather_port_state(
                    module, connection, selected_names, result["api_responses"]
                )
            module.exit_json(**result)

        current_names = set(current_map.keys())
        desired_names = {_normalize_port_name(entry["name"]) for entry in normalized_entries}
        defaults_map: dict[str, dict[str, Any]] = {}
        for port_name in current_names.union(desired_names):
            defaults_map[port_name] = _default_interface_settings(_is_poe_capable(capabilities.get(port_name, {})))

        updated_names: list[str] = []
        removed_names: list[str] = []
        # Every port `overridden` is authoritative over, not just the ones it
        # had to write: an unlisted port already at its defaults is still a
        # target of the task and belongs in the before/after pair.
        reset_targets: list[str] = []

        for entry in normalized_entries:
            port_name = entry["name"]
            current = deepcopy(current_map.get(port_name, defaults_map[port_name]))
            defaults = deepcopy(defaults_map[port_name])
            target = _build_target_settings(entry, current, defaults, state)
            if _settings_equal(current, target):
                continue
            updated = _apply_interface(
                module,
                connection,
                port_name,
                target,
                current_map,
                defaults["advertise"]["med_power"],
                result["api_responses"],
                state,
            )
            result["changed"] = True
            done.append(port_name)
            if state == STATE_DELETED:
                removed_names.append(port_name)
            else:
                updated_names.append(port_name)
                current_map[port_name] = updated

        if state == STATE_OVERRIDDEN:
            ports_to_reset = sorted(current_names.difference(desired_names))
            reset_targets = list(ports_to_reset)
            for port_name in ports_to_reset:
                current = deepcopy(current_map.get(port_name, defaults_map[port_name]))
                defaults = deepcopy(defaults_map[port_name])
                if _settings_equal(current, defaults):
                    continue
                _apply_interface(
                    module,
                    connection,
                    port_name,
                    defaults,
                    current_map,
                    defaults["advertise"]["med_power"],
                    result["api_responses"],
                    STATE_DELETED,
                )
                result["changed"] = True
                done.append(port_name)
                removed_names.append(port_name)

        if updated_names:
            result["interface_updates"] = updated_names
            result["interfaces_settings"] = _format_output_interfaces(current_map, updated_names)
        if removed_names:
            result["interface_removals"] = removed_names
            if "interfaces_settings" not in result:
                result["interfaces_settings"] = _format_output_interfaces(current_map, removed_names)

        if gather_state:
            selected_names = updated_names or removed_names or sorted(desired_names)
            result["interfaces_state"] = _gather_port_state(module, connection, selected_names, result["api_responses"])

        # Every interface this task targeted, whether or not it changed: the
        # ports named in config, plus the ones `overridden` is authoritative
        # over on its own.
        affected_names = sorted(desired_names.union(removed_names).union(reset_targets))
        result["before"] = _snapshot_interfaces(before_map, defaults_map, affected_names)
        result["after"] = _snapshot_interfaces(current_map, defaults_map, affected_names)

        # Diff mode (--diff): Ansible renders the before/after pair itself.
        # Populated even when nothing changed, so `--check --diff` can show
        # that a play is already converged.
        if module._diff:
            result["diff"] = {"before": result["before"], "after": result["after"]}

        module.exit_json(**result)
    except FeLldpInterfacesError as exc:
        _fail_after_writes(module, exc, result, done)
    except ConnectionError as exc:
        _fail_after_writes(
            module,
            FeLldpInterfacesError(
                to_text(exc), extra={"code": getattr(exc, "code", None), "err": getattr(exc, "err", None)}
            ),
            result,
            done,
        )


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
