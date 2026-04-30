# -*- coding: utf-8 -*-
"""Ansible module to manage LLDP interface settings on Fabric Engine switches."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

DOCUMENTATION = r"""
---
module: extreme_fe_lldp_interfaces
short_description: Manage LLDP interface settings on ExtremeNetworks Fabric Engine switches
version_added: "1.1.0"
description:
  - Manage LLDP interface-level settings on ExtremeNetworks Fabric Engine (VOSS) switches using the custom C(extreme_fe) HTTPAPI plugin.
  - Uses C(/v0/configuration/lldp/ports/{port}) and C(/v0/configuration/lldp/ports/{port}/med-policy) from the NOS OpenAPI schema.
  - Supports the VOSS LLDP port attributes exposed by the schema, including basic transmit or receive control, advertised TLVs, location data, and MED network policy entries.
  - Switch Engine (EXOS)-only LLDP attributes are intentionally excluded.
  - When C(med_policy) is supplied, it is treated as the authoritative list for that interface because the device API replaces the full MED policy list.
author:
  - ExtremeNetworks Networking Automation Team
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
  - Port identifiers must use slot:port notation such as C(1:5).
  - On Fabric Engine, C(transmit_enabled) and C(receive_enabled) should be set to the same value. If only one is supplied, this module mirrors the same value to the other field.
  - If LLDP transmit or receive is disabled, the device ignores advertisement and location attributes in the same request. This module submits only the basic LLDP enable flags in that case.
requirements:
  - ansible.netcommon
options:
  state:
    description:
      - Desired module operation.
      - C(merged) applies the supplied interface settings incrementally without removing unspecified configuration.
      - C(replaced) treats the supplied values as authoritative for the targeted interfaces and resets omitted LLDP attributes to device defaults.
      - C(overridden) behaves like C(replaced) for the listed interfaces and resets LLDP settings on discovered interfaces that are not provided.
      - C(deleted) resets the listed interfaces to LLDP defaults.
      - C(gathered) returns current LLDP interface configuration without applying changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  interfaces:
    description:
      - Interface LLDP definitions to manage.
      - Required when C(state) is C(merged), C(replaced), C(overridden), or C(deleted).
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
              - Civic address location string in Fabric Engine civic address format.
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
    interfaces:
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
    interfaces:
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
          civic_address: "country-code US city Raleigh street Main building 100"
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
    interfaces:
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
interfaces_settings:
  description: Normalized LLDP settings for gathered or modified interfaces.
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
  description: Raw API responses captured during execution.
  returned: always
  type: dict
"""

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

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
    "interfaces": {
        "type": "list",
        "elements": "dict",
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

LOCATION_FIELD_MAP = {
    "civic_address": "civicAddress",
    "ecs_elin": "ecsElin",
    "coordinate": "coordinate",
}

MED_POLICY_FIELD_MAP = {
    "type": "type",
    "dscp": "dscp",
    "priority": "priority",
    "tagged": "tagged",
    "vlan_id": "vlanId",
}

REQUIRES_INTERFACES = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED}


class FeLldpInterfacesError(Exception):
    """Raised for LLDP interface validation and response issues."""

    def __init__(
        self, message: str, *, details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _extract_error(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    message = (
        payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    )
    if isinstance(code, int) and code >= 400:
        return {
            "code": code,
            "message": message or "Device reported an LLDP error",
            "payload": payload,
        }
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported LLDP errors",
            "errors": errors,
            "payload": payload,
        }
    return None


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: Dict[str, Any],
    response_key: str,
    payload: Optional[Any] = None,
    expect_content: bool = True,
) -> Any:
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=api_responses,
        )

    api_responses[response_key] = response

    if response in (None, ""):
        return None if not expect_content else {}

    if isinstance(response, bytes):
        response = to_text(response)
        api_responses[response_key] = response

    if isinstance(response, dict):
        error = _extract_error(response)
        if error:
            module.fail_json(
                msg=error.get("message"), details=error, api_responses=api_responses
            )

    return response


def _get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeLldpInterfacesError(
            "Connection type httpapi is required for this module"
        )
    return Connection(module._socket_path)


def _normalize_port_name(raw: Any) -> str:
    if not isinstance(raw, str):
        raise FeLldpInterfacesError(
            "Interface name must be a string in slot:port format"
        )
    value = raw.strip()
    if not value:
        raise FeLldpInterfacesError("Interface name must not be empty")
    return value


def _is_poe_capable(capability: Dict[str, Any]) -> bool:
    caps = capability.get("capabilities")
    if not isinstance(caps, dict):
        return False
    return bool(
        caps.get("poe")
        or caps.get("poeMaxPower") is not None
        or caps.get("poeMaxClassification") is not None
    )


def _default_interface_settings(is_poe_capable: bool) -> Dict[str, Any]:
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


def _normalize_med_policy_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for param, rest_key in MED_POLICY_FIELD_MAP.items():
        value = item.get(rest_key) if rest_key in item else item.get(param)
        if value is None:
            continue
        if param in {"dscp", "priority", "vlan_id"}:
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise FeLldpInterfacesError(
                    "MED policy field '{0}' must be an integer".format(param),
                    details={"policy": item},
                )
        if param == "dscp" and not (0 <= value <= 63):
            raise FeLldpInterfacesError(
                "MED policy dscp must be between 0 and 63", details={"policy": item}
            )
        if param == "priority" and not (0 <= value <= 7):
            raise FeLldpInterfacesError(
                "MED policy priority must be between 0 and 7", details={"policy": item}
            )
        if param == "vlan_id" and not (0 <= value <= 4059):
            raise FeLldpInterfacesError(
                "MED policy vlan_id must be between 0 and 4059",
                details={"policy": item},
            )
        normalized[param] = value
    required = {"type", "dscp", "priority", "tagged", "vlan_id"}
    missing = sorted(required.difference(normalized.keys()))
    if missing:
        raise FeLldpInterfacesError(
            "Each MED policy entry must provide type, dscp, priority, tagged, and vlan_id",
            details={"missing": missing, "policy": item},
        )
    return normalized


def _sort_med_policy(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


CIVIC_ADDRESS_FIELDS = {
    "country-code",
    "language",
    "province-state",
    "county",
    "city",
    "city-division",
    "neighborhood",
    "street-group",
    "leading-street-direction",
    "trailing-street-suffix",
    "street",
    "house-number",
    "house-number-suffix",
    "landmark",
    "additional-info",
    "name",
    "postal-zip",
    "building",
    "unit",
    "floor",
    "room",
    "type-of-place",
    "postal-community-name",
    "post-office-box",
    "additional-code",
    "seat",
    "primary-road-name",
    "road-section",
    "branch-road-name",
    "sub-branch-road-name",
    "street-name-pre-modifier",
    "street-name-post-modifier",
}


def _parse_civic_address(value: str) -> Dict[str, str]:
    """Parse a civic address string into a dict of field-value pairs (sorted by key).

    Handles both user-provided format and device-returned format:
      User:   country-code RO city Bucharest street Victoriei building 10
      Device: country-code RO building "10" city "Bucharest" street "Victoriei"
    """
    if not value or not isinstance(value, str):
        return {}
    tokens = value.strip().split()
    result: Dict[str, str] = {}
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


def _locations_equal(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
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


def _normalize_current_settings(payload: Any, is_poe_capable: bool) -> Dict[str, Any]:
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
        normalized_location: Dict[str, Any] = {}
        for param, rest_key in LOCATION_FIELD_MAP.items():
            value = location.get(rest_key)
            if value not in (None, ""):
                normalized_location[param] = value
        base["location"] = normalized_location

    med_policy = payload.get("medPolicy")
    if isinstance(med_policy, list):
        base["med_policy"] = _sort_med_policy(
            _normalize_med_policy_item(item)
            for item in med_policy
            if isinstance(item, dict)
        )

    return base


def _normalize_input_interfaces(
    module: AnsibleModule, state: str
) -> List[Dict[str, Any]]:
    raw_entries = list(module.params.get("interfaces") or [])
    if state in REQUIRES_INTERFACES and not raw_entries:
        raise FeLldpInterfacesError(
            "interfaces is required when state in merged, replaced, overridden, deleted"
        )

    normalized_entries: List[Dict[str, Any]] = []
    seen: set = set()
    for item in raw_entries:
        if not isinstance(item, dict):
            raise FeLldpInterfacesError("Each interface entry must be a dictionary")
        name = _normalize_port_name(item.get("name"))
        if name in seen:
            raise FeLldpInterfacesError(
                "Duplicate interface entry detected", details={"name": name}
            )
        seen.add(name)

        normalized: Dict[str, Any] = {"name": name}

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
                "transmit_enabled and receive_enabled must use the same value on Fabric Engine",
                details={"name": name},
            )
        if tx_present:
            normalized["transmit_enabled"] = bool(tx_value)
        if rx_present:
            normalized["receive_enabled"] = bool(rx_value)

        advertise = item.get("advertise")
        if advertise is not None:
            if not isinstance(advertise, dict):
                raise FeLldpInterfacesError(
                    "advertise must be a dictionary", details={"name": name}
                )
            normalized_advertise: Dict[str, Any] = {}
            for param in ADVERTISE_FIELD_MAP:
                if param in advertise and advertise.get(param) is not None:
                    normalized_advertise[param] = advertise.get(param)
            if normalized_advertise:
                normalized["advertise"] = normalized_advertise

        location = item.get("location")
        if location is not None:
            if not isinstance(location, dict):
                raise FeLldpInterfacesError(
                    "location must be a dictionary", details={"name": name}
                )
            normalized_location: Dict[str, Any] = {}
            for param in LOCATION_FIELD_MAP:
                value = location.get(param)
                if value in (None, ""):
                    continue
                if param == "ecs_elin" and len(str(value)) > 25:
                    raise FeLldpInterfacesError(
                        "location.ecs_elin must be 25 characters or less",
                        details={"name": name},
                    )
                normalized_location[param] = value
            normalized["location"] = normalized_location

        med_policy = item.get("med_policy")
        if med_policy is not None:
            if not isinstance(med_policy, list):
                raise FeLldpInterfacesError(
                    "med_policy must be a list", details={"name": name}
                )
            normalized["med_policy"] = _sort_med_policy(
                _normalize_med_policy_item(entry)
                for entry in med_policy
                if isinstance(entry, dict)
            )

        if state == STATE_MERGED and len(normalized) == 1:
            raise FeLldpInterfacesError(
                "At least one LLDP interface attribute must be provided when state='merged'",
                details={"name": name},
            )

        normalized_entries.append(normalized)

    return normalized_entries


def _overlay_settings(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
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
    entry: Dict[str, Any],
    current: Dict[str, Any],
    defaults: Dict[str, Any],
    state: str,
) -> Dict[str, Any]:
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


def _settings_equal(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    if left.get("transmit_enabled") != right.get("transmit_enabled"):
        return False
    if left.get("receive_enabled") != right.get("receive_enabled"):
        return False
    # When either LLDP flag is explicitly disabled, _build_config_payload() returns
    # early without advertise/location, so those fields can never converge.  Skip
    # their comparison to avoid perpetual changed=True.
    if right.get("transmit_enabled") is False or right.get("receive_enabled") is False:
        return True
    return (
        (left.get("advertise") or {}) == (right.get("advertise") or {})
        and _locations_equal(left.get("location"), right.get("location"))
        and _sort_med_policy(left.get("med_policy") or [])
        == _sort_med_policy(right.get("med_policy") or [])
    )


def _port_config_path(port_name: str) -> str:
    return LLDP_PORT_CONFIG_TEMPLATE.format(port=quote(port_name, safe=""))


def _port_med_policy_path(port_name: str) -> str:
    return LLDP_PORT_MED_POLICY_TEMPLATE.format(port=quote(port_name, safe=""))


def _port_state_path(port_name: str) -> str:
    return LLDP_PORT_STATE_TEMPLATE.format(port=quote(port_name, safe=""))


def _build_config_payload(target: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "transmitEnabled": target.get("transmit_enabled", True),
        "receiveEnabled": target.get("receive_enabled", True),
    }
    if not payload["transmitEnabled"] or not payload["receiveEnabled"]:
        return payload

    advertise_payload: Dict[str, Any] = {}
    for param, rest_key in ADVERTISE_FIELD_MAP.items():
        advertise_payload[rest_key] = target.get("advertise", {}).get(param)
    payload["advertise"] = advertise_payload

    location_payload: Dict[str, Any] = {}
    for param, rest_key in LOCATION_FIELD_MAP.items():
        value = target.get("location", {}).get(param)
        if value not in (None, ""):
            location_payload[rest_key] = value
    if location_payload:
        payload["location"] = location_payload
    return payload


def _build_med_policy_payload(target: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for entry in _sort_med_policy(target.get("med_policy") or []):
        item: Dict[str, Any] = {}
        for param, rest_key in MED_POLICY_FIELD_MAP.items():
            item[rest_key] = entry.get(param)
        payload.append(item)
    return payload


def _fetch_capabilities(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
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
        raise FeLldpInterfacesError(
            "Unexpected response when retrieving port capabilities",
            details={"payload": data},
        )
    capabilities: Dict[str, Dict[str, Any]] = {}
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
    capabilities: Dict[str, Dict[str, Any]],
    api_responses: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
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
        raise FeLldpInterfacesError(
            "Unexpected response when retrieving LLDP configuration",
            details={"payload": data},
        )

    interfaces: Dict[str, Dict[str, Any]] = {}
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
    api_responses: Dict[str, Any],
    response_key: str,
) -> Dict[str, Any]:
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


def _format_output_interfaces(
    port_map: Dict[str, Dict[str, Any]],
    names: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    selected_names = list(names) if names is not None else sorted(port_map.keys())
    output: List[Dict[str, Any]] = []
    for name in selected_names:
        settings = port_map.get(name)
        if settings is None:
            continue
        output.append({"name": name, "settings": settings})
    return output


def _gather_port_state(
    module: AnsibleModule,
    connection: Connection,
    port_names: Iterable[str],
    api_responses: Dict[str, Any],
) -> List[Dict[str, Any]]:
    state_responses = api_responses.setdefault("state", {})
    results: List[Dict[str, Any]] = []
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
    target: Dict[str, Any],
    current_map: Dict[str, Dict[str, Any]],
    is_poe_capable_flag: bool,
    api_responses: Dict[str, Any],
    operation: str,
) -> Dict[str, Any]:
    operations = api_responses.setdefault("operations", {}).setdefault(port_name, {})
    config_payload = _build_config_payload(target)
    med_policy_payload = _build_med_policy_payload(target)

    if module.check_mode:
        operations["config_put"] = None
        operations["med_policy_put"] = None
        current_map[port_name] = deepcopy(target)
        return deepcopy(target)

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

    updated = _fetch_single_interface(
        module,
        connection,
        port_name,
        is_poe_capable_flag,
        operations,
        "after_get",
    )
    current_map[port_name] = updated
    operations["operation"] = operation
    operations["submitted"] = {
        "config": config_payload,
        "med_policy": med_policy_payload,
    }
    return updated


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)
    try:
        connection = _get_connection(module)
    except FeLldpInterfacesError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    result: Dict[str, Any] = {"changed": False, "api_responses": {}}

    try:
        state = module.params.get("state")
        gather_filter = module.params.get("gather_filter") or None
        gather_state = bool(module.params.get("gather_state"))

        capabilities = _fetch_capabilities(module, connection, result["api_responses"])
        current_map = _fetch_all_interfaces(
            module, connection, capabilities, result["api_responses"]
        )
        normalized_entries = _normalize_input_interfaces(module, state)

        if state == STATE_GATHERED:
            selected_names = (
                [_normalize_port_name(item) for item in gather_filter]
                if gather_filter
                else sorted(current_map.keys())
            )
            result["interfaces_settings"] = _format_output_interfaces(
                current_map, selected_names
            )
            if gather_state:
                result["interfaces_state"] = _gather_port_state(
                    module,
                    connection,
                    selected_names,
                    result["api_responses"],
                )
            module.exit_json(**result)

        current_names = set(current_map.keys())
        desired_names = {
            _normalize_port_name(entry["name"]) for entry in normalized_entries
        }
        defaults_map: Dict[str, Dict[str, Any]] = {}
        for port_name in current_names.union(desired_names):
            defaults_map[port_name] = _default_interface_settings(
                _is_poe_capable(capabilities.get(port_name, {}))
            )

        updated_names: List[str] = []
        removed_names: List[str] = []

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
            if state == STATE_DELETED:
                removed_names.append(port_name)
            else:
                updated_names.append(port_name)
                current_map[port_name] = updated

        if state == STATE_OVERRIDDEN:
            ports_to_reset = sorted(current_names.difference(desired_names))
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
                removed_names.append(port_name)

        if updated_names:
            result["interface_updates"] = updated_names
            result["interfaces_settings"] = _format_output_interfaces(
                current_map, updated_names
            )
        if removed_names:
            result["interface_removals"] = removed_names
            if "interfaces_settings" not in result:
                result["interfaces_settings"] = _format_output_interfaces(
                    current_map, removed_names
                )

        if gather_state:
            selected_names = updated_names or removed_names or sorted(desired_names)
            result["interfaces_state"] = _gather_port_state(
                module,
                connection,
                selected_names,
                result["api_responses"],
            )

        module.exit_json(**result)
    except FeLldpInterfacesError as exc:
        module.fail_json(
            api_responses=result.get("api_responses", {}), **exc.to_fail_kwargs()
        )
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=result.get("api_responses", {}),
        )


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
