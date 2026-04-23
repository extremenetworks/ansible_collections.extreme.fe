# -*- coding: utf-8 -*-
"""Ansible module to manage L2 interface settings on Fabric Engine switches.

Manages VLAN membership (access/trunk mode, tagged/untagged VLANs)
on physical ports and LAG interfaces.

REST API endpoints used:
  VLAN membership:
    - GET  /v0/configuration/vlan/interfaces
    - GET  /v0/configuration/vlan/interfaces/type/{type}/name/{name}
    - PUT  /v0/configuration/vlan/interfaces/type/{type}/name/{name}
"""

from __future__ import annotations

# -- Standard library imports --------------------------------------------------
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote

# -- Ansible SDK imports -------------------------------------------------------
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

import yaml

DOCUMENTATION = r"""
---
module: extreme_fe_l2_interfaces
short_description: Manages L2 interface settings on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Configure L2 interface settings on ExtremeNetworks Fabric Engine
  (VOSS) switches using the C(extreme_fe) HTTPAPI connection plugin.
- Supports VLAN membership (access/trunk mode, tagged/untagged VLANs)
  on one or more interfaces per task via the C(config) list parameter.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the C(ansible.netcommon) collection and the C(extreme_fe)
  HTTPAPI plugin shipped with this project.
- When C(state=overridden), the module reads all interface VLAN
  settings and resets any interface not listed in C(config) to the
  device defaults (TRUNK mode, untagged VLAN 1, no tagged VLANs).
  C(config) must not be empty.  Interfaces that cannot be reset
  (e.g. LACP LAGs) are skipped with a warning and listed in the
  C(skipped_interfaces) return value.
requirements:
- ansible.netcommon
options:
  config:
    description:
    - List of L2 interface definitions to manage.
    - When omitted with C(state=gathered), the module returns VLAN
      settings for all interfaces on the device.
    type: list
    elements: dict
    suboptions:
      name:
        description:
        - Interface identifier such as C(1:5), C(PORT:1:5), or C(LAG:10).
          When the type prefix is omitted, C(PORT) is assumed.
        type: str
        required: true
      port_type:
        description:
        - Interface VLAN mode.
        type: str
        choices:
        - ACCESS
        - TRUNK
      untagged_vlan:
        description:
        - VLAN ID for untagged traffic (port VLAN).
          Use C(0) to clear the untagged VLAN.
        type: int
      tagged_vlans:
        description:
        - Authoritative list of tagged (allowed) VLANs for the
          interface. In C(merged) state, replaces the current
          tagged list (use C(add_tagged_vlans)/C(remove_tagged_vlans)
          for incremental changes). In C(replaced)/C(overridden)
          states, sets the complete tagged list.
        type: list
        elements: int
      add_tagged_vlans:
        description:
        - VLANs to add to the tagged list without removing other
          entries. Only valid with C(state=merged).
        type: list
        elements: int
      remove_tagged_vlans:
        description:
        - VLANs to remove from the tagged list without affecting
          other entries. Only valid with C(state=merged) or
          C(state=deleted).
        type: list
        elements: int
  state:
    description:
    - Desired module operation.
    - C(merged) applies the provided parameters incrementally
      without removing unspecified VLAN membership.
    - C(replaced) treats the supplied values as authoritative
      for each listed interface.
    - C(overridden) like C(replaced) but also resets every
      interface NOT in C(config) to device defaults.
    - C(deleted) removes tagged VLAN membership. When no VLAN
      parameters are given, all memberships are reset.
    - C(gathered) returns current VLAN membership without
      applying changes.
    type: str
    choices:
    - merged
    - replaced
    - overridden
    - deleted
    - gathered
    default: merged
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc:

# -------------------------------------------------------------------------
# Task 1: Configure access port
# -------------------------------------------------------------------------
- name: Set access port on interface 1:5
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:5"
        port_type: ACCESS
        untagged_vlan: 5
    state: replaced

# -------------------------------------------------------------------------
# Task 2: Configure multiple trunk ports
# -------------------------------------------------------------------------
- name: Ensure trunk membership on two ports
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:10"
        port_type: TRUNK
        untagged_vlan: 1
        tagged_vlans: [5, 6]
      - name: "1:11"
        port_type: TRUNK
        untagged_vlan: 1
        tagged_vlans: [7, 8]
    state: replaced

# -------------------------------------------------------------------------
# Task 3: Add tagged VLANs incrementally
# -------------------------------------------------------------------------
- name: Add VLAN 20 to port 1:7
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:7"
        add_tagged_vlans: [20]
    state: merged

# -------------------------------------------------------------------------
# Task 4: Remove tagged VLAN
# -------------------------------------------------------------------------
- name: Drop VLAN 20 from port 1:7
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:7"
        remove_tagged_vlans: [20]
    state: merged

# -------------------------------------------------------------------------
# Task 5: Override all interfaces
# -------------------------------------------------------------------------
- name: Only ports 1:5 and 1:6 should have non-default config
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:5"
        port_type: TRUNK
        untagged_vlan: 1
        tagged_vlans: [100, 200]
      - name: "1:6"
        port_type: ACCESS
        untagged_vlan: 5
    state: overridden

# -------------------------------------------------------------------------
# Task 6: Gather all interface VLAN settings
# -------------------------------------------------------------------------
- name: Collect all L2 interface settings
  extreme.fe.extreme_fe_l2_interfaces:
    state: gathered
  register: l2_config

# -------------------------------------------------------------------------
# Task 7: Gather specific interface
# -------------------------------------------------------------------------
- name: Gather VLAN settings for port 1:8
  extreme.fe.extreme_fe_l2_interfaces:
    config:
      - name: "1:8"
    state: gathered
  register: l2_config
"""

RETURN = r"""
changed:
    description: Indicates whether any changes were made.
    returned: always
    type: bool
interfaces:
    description: >-
        List of per-interface results.  Each entry contains the
        interface name, before/after state, differences, and whether
        that interface changed.  For gathered state, before and after
        are both set to the current device state and differences is
        empty.
    returned: always
    type: list
    elements: dict
    contains:
        name:
            description: Interface identifier.
            type: str
        before:
            description: Configuration before the change.
            type: dict
        after:
            description: Configuration after the change.
            type: dict
        differences:
            description: Per-field breakdown of what changed.
            type: list
        changed:
            description: Whether this specific interface was modified.
            type: bool
reset_interfaces:
    description: >-
        Interfaces that were modified and reset to defaults during
        overridden state because they were not listed in config.
    returned: when state is overridden
    type: list
    elements: str
skipped_interfaces:
    description: >-
        Interfaces that could not be reset during overridden state
        (e.g. LACP LAGs or protected ports).
    returned: when state is overridden
    type: list
    elements: str
"""

ARGUMENT_SPEC: Dict[str, Any] = {
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "port_type": {"type": "str", "choices": ["ACCESS", "TRUNK"]},
            "untagged_vlan": {"type": "int"},
            "tagged_vlans": {"type": "list", "elements": "int"},
            "add_tagged_vlans": {"type": "list", "elements": "int"},
            "remove_tagged_vlans": {"type": "list", "elements": "int"},
        },
    },
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}

KNOWN_INTERFACE_TYPES: Set[str] = {"PORT", "LAG"}

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# Default L2 settings used when resetting ports (overridden state).
# Verified against VOSS factory defaults: TRUNK mode, portVlan=1.
DEFAULTS: Dict[str, Any] = {
    "portType": "TRUNK",
    "portVlan": 1,
    "allowedVlans": [1],
}


# --------------------------------------------------------------------------
# Exception
# --------------------------------------------------------------------------


class FeL2InterfacesError(Exception):
    """Base exception for the L2 interface module."""

    def __init__(
        self, message: str, *, details: Optional[Dict[str, object]] = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, object]:
        data: Dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _is_not_found_response(payload: Optional[object]) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    if code == 404:
        return True
    message = (
        payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    )
    if isinstance(message, str) and "not found" in message.lower():
        return True
    return False


def parse_interface_name(name: str) -> Tuple[str, str]:
    """Parse 'PORT:1:5', '1:5', or 'LAG:10' into (type, name)."""
    raw = name.strip()
    if not raw:
        raise FeL2InterfacesError("Interface name must not be empty")
    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        prefix_upper = prefix.strip().upper()
        if prefix_upper in KNOWN_INTERFACE_TYPES:
            iface_name = rest.strip()
            if not iface_name:
                raise FeL2InterfacesError(
                    f"Interface name is empty after '{prefix_upper}:' prefix"
                )
            return prefix_upper, iface_name
    return "PORT", raw


def _normalize_vlan_list(value: Optional[Iterable[object]]) -> List[int]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = yaml.safe_load(value)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            value = parsed
        else:
            value = [value]
    result: List[int] = []
    for item in value:
        if item is None:
            continue
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            raise FeL2InterfacesError(
                f"Unable to convert VLAN value '{item}' to an integer"
            )
    return result


def _normalize_port_type(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip().upper()
        return stripped if stripped else None
    raise FeL2InterfacesError(f"Unsupported port_type value '{value}' supplied")


def _normalize_vlan_value(value: Optional[object]) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise FeL2InterfacesError(
            f"Unable to convert VLAN value '{value}' to an integer"
        )


# --------------------------------------------------------------------------
# REST API wrappers
# --------------------------------------------------------------------------

COLLECTION_PATH = "/v0/configuration/vlan/interfaces"


def _interface_path(iface_type: str, iface_name: str) -> str:
    return (
        f"/v0/configuration/vlan/interfaces/type/"
        f"{quote(iface_type)}/name/{quote(iface_name)}"
    )


def get_interface_settings(
    connection: Connection, iface_type: str, iface_name: str
) -> Optional[Dict[str, object]]:
    try:
        data = connection.send_request(
            None, path=_interface_path(iface_type, iface_name), method="GET"
        )
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        if "interfaceSettings" in data and isinstance(data["interfaceSettings"], dict):
            return data["interfaceSettings"]
        return data
    raise FeL2InterfacesError(
        "Unexpected response when retrieving interface VLAN configuration",
        details={"response": data},
    )


def get_all_interface_settings(
    connection: Connection,
) -> List[Dict[str, Any]]:
    """GET /v0/configuration/vlan/interfaces -- returns all interfaces."""
    try:
        data = connection.send_request(None, path=COLLECTION_PATH, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("interfaces", "items", "data"):
            if isinstance(data.get(key), list):
                return [item for item in data[key] if isinstance(item, dict)]
    return []


def replace_interface_settings(
    connection: Connection,
    iface_type: str,
    iface_name: str,
    payload: Dict[str, object],
) -> None:
    connection.send_request(
        payload, path=_interface_path(iface_type, iface_name), method="PUT"
    )


# --------------------------------------------------------------------------
# Ansible-facing state normalisation
# --------------------------------------------------------------------------


def _to_ansible_state(
    raw: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Normalise a raw API response into a stable dict for before/after."""
    if raw is None:
        return {"port_type": None, "untagged_vlan": None, "tagged_vlans": []}
    port_vlan = _normalize_vlan_value(raw.get("portVlan"))
    all_vlans = sorted(_normalize_vlan_list(raw.get("allowedVlans")))
    tagged = [v for v in all_vlans if v != port_vlan and v != 0]
    return {
        "port_type": _normalize_port_type(raw.get("portType")),
        "untagged_vlan": port_vlan,
        "tagged_vlans": tagged,
    }


def _compute_differences(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> List[Dict[str, Any]]:
    diffs: List[Dict[str, Any]] = []
    for key in ("port_type", "untagged_vlan", "tagged_vlans"):
        bval = before.get(key)
        aval = after.get(key)
        if bval != aval:
            diffs.append({"field": key, "before": bval, "after": aval})
    return diffs


# --------------------------------------------------------------------------
# Payload builders per state
# --------------------------------------------------------------------------


def _build_merged_payload(
    entry: Dict[str, Any],
    existing: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build desired payload for merged state (additive)."""
    current_port_type = _normalize_port_type(existing.get("portType"))
    current_untagged = _normalize_vlan_value(existing.get("portVlan"))
    current_allowed = {int(v) for v in existing.get("allowedVlans") or []}

    desired_port_type = _normalize_port_type(entry.get("port_type"))
    tagged_vlans = entry.get("tagged_vlans")
    add_tagged = entry.get("add_tagged_vlans")
    remove_tagged = entry.get("remove_tagged_vlans")
    target_untagged = _normalize_vlan_value(entry.get("untagged_vlan"))

    target_allowed = set(current_allowed)
    if tagged_vlans is not None:
        target_allowed = set(_normalize_vlan_list(tagged_vlans))
    target_allowed |= set(_normalize_vlan_list(add_tagged))
    target_allowed -= set(_normalize_vlan_list(remove_tagged))

    if target_untagged is None:
        target_untagged = current_untagged
    if desired_port_type is None:
        desired_port_type = current_port_type or (
            "TRUNK" if target_allowed else "ACCESS"
        )

    # ACCESS ports do not support allowedVlans.
    if desired_port_type == "ACCESS":
        has_tagged_intent = (
            tagged_vlans not in (None, [])
            or add_tagged not in (None, [])
            or remove_tagged not in (None, [])
        )
        if has_tagged_intent:
            raise FeL2InterfacesError(
                "ACCESS ports do not support tagged VLANs. "
                "Either remove tagged VLAN parameters or set "
                "'port_type' to TRUNK."
            )
        target_allowed = set()

    # TRUNK: device includes portVlan in allowedVlans.
    if (
        desired_port_type == "TRUNK"
        and target_untagged is not None
        and target_untagged > 0
    ):
        target_allowed.add(target_untagged)

    payload: Dict[str, Any] = {
        "portType": desired_port_type,
        "allowedVlans": sorted(target_allowed),
    }
    if target_untagged is not None:
        payload["portVlan"] = target_untagged

    comparison = {
        "portType": desired_port_type,
        "portVlan": target_untagged,
        "allowedVlans": sorted(target_allowed),
    }
    return payload, comparison


def _build_replaced_payload(
    entry: Dict[str, Any],
    existing: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build desired payload for replaced state (authoritative per-interface)."""
    add_tagged = entry.get("add_tagged_vlans")
    remove_tagged = entry.get("remove_tagged_vlans")
    if add_tagged not in (None, []) or remove_tagged not in (None, []):
        raise FeL2InterfacesError(
            "'add_tagged_vlans' and 'remove_tagged_vlans' are not valid "
            "when state is 'replaced' or 'overridden'."
        )

    desired_port_type = _normalize_port_type(entry.get("port_type"))
    tagged_vlans = entry.get("tagged_vlans")
    target_untagged = _normalize_vlan_value(entry.get("untagged_vlan"))

    target_allowed: Set[int] = set(_normalize_vlan_list(tagged_vlans))

    # When untagged_vlan is omitted, default from existing to avoid a
    # perpetual diff (the device always reports a real portVlan).
    if target_untagged is None:
        target_untagged = _normalize_vlan_value(existing.get("portVlan"))

    if desired_port_type is None:
        desired_port_type = "TRUNK" if target_allowed else "ACCESS"

    if desired_port_type == "ACCESS" and target_allowed:
        raise FeL2InterfacesError(
            "ACCESS ports do not support tagged VLANs. "
            "Either remove 'tagged_vlans' or set 'port_type' to TRUNK."
        )

    # TRUNK: device includes portVlan in allowedVlans.
    if (
        desired_port_type == "TRUNK"
        and target_untagged is not None
        and target_untagged > 0
    ):
        target_allowed.add(target_untagged)

    payload: Dict[str, Any] = {
        "portType": desired_port_type,
        "allowedVlans": sorted(target_allowed),
    }
    if target_untagged is not None:
        payload["portVlan"] = target_untagged

    comparison = {
        "portType": desired_port_type,
        "portVlan": target_untagged,
        "allowedVlans": sorted(target_allowed),
    }
    return payload, comparison


def _build_deleted_payload(
    entry: Dict[str, Any],
    existing: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build desired payload for deleted state."""
    add_tagged = entry.get("add_tagged_vlans")
    if add_tagged not in (None, []):
        raise FeL2InterfacesError(
            "'add_tagged_vlans' is not valid when state is 'deleted'. "
            "Use 'tagged_vlans' or 'remove_tagged_vlans' to specify "
            "VLANs to remove."
        )

    current_port_type = _normalize_port_type(existing.get("portType"))
    current_untagged = _normalize_vlan_value(existing.get("portVlan"))
    current_allowed = {int(v) for v in existing.get("allowedVlans") or []}

    remove_list = set(_normalize_vlan_list(entry.get("tagged_vlans")))
    remove_list |= set(_normalize_vlan_list(entry.get("remove_tagged_vlans")))

    if remove_list:
        target_allowed = current_allowed - remove_list
    else:
        target_allowed = set()

    target_untagged = current_untagged
    requested_untagged = entry.get("untagged_vlan")
    if requested_untagged is not None:
        normalized = _normalize_vlan_value(requested_untagged)
        if normalized == 0 or current_untagged == normalized:
            # Explicit 0 means "clear untagged VLAN"; matching
            # current value also means "remove this untagged".
            target_untagged = 0
    elif not remove_list:
        target_untagged = 0

    desired_port_type = _normalize_port_type(entry.get("port_type"))
    if desired_port_type is None:
        desired_port_type = current_port_type or (
            "ACCESS" if not target_allowed and target_untagged in (0, None) else "TRUNK"
        )

    # TRUNK: mirror portVlan in allowedVlans.
    if (
        desired_port_type == "TRUNK"
        and target_untagged is not None
        and target_untagged > 0
    ):
        target_allowed.add(target_untagged)

    payload: Dict[str, Any] = {
        "portType": desired_port_type,
        "allowedVlans": sorted(target_allowed),
        "portVlan": target_untagged if target_untagged is not None else 0,
    }

    comparison = {
        "portType": desired_port_type,
        "portVlan": target_untagged if target_untagged is not None else 0,
        "allowedVlans": sorted(target_allowed),
    }
    return payload, comparison


def _build_defaults_payload() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build default-reset payload for overridden unlisted interfaces."""
    payload = dict(DEFAULTS)
    comparison = {
        "portType": DEFAULTS["portType"],
        "portVlan": DEFAULTS["portVlan"],
        "allowedVlans": list(DEFAULTS["allowedVlans"]),
    }
    return payload, comparison


# --------------------------------------------------------------------------
# Core processing
# --------------------------------------------------------------------------


def _current_state_key(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Build a comparison dict from existing device data."""
    return {
        "portType": _normalize_port_type(raw.get("portType")),
        "portVlan": _normalize_vlan_value(raw.get("portVlan")),
        "allowedVlans": sorted({int(v) for v in raw.get("allowedVlans") or []}),
    }


def _apply_interface(
    connection: Connection,
    iface_type: str,
    iface_name: str,
    existing: Dict[str, Any],
    payload: Dict[str, Any],
    comparison: Dict[str, Any],
    *,
    check_mode: bool,
) -> Tuple[bool, Dict[str, Any]]:
    """Apply payload to one interface. Returns (changed, final_raw)."""
    current = _current_state_key(existing)
    if current == comparison:
        return False, existing

    if not check_mode:
        replace_interface_settings(connection, iface_type, iface_name, payload)
        final = get_interface_settings(connection, iface_type, iface_name) or comparison
        # Re-try if portVlan diverges (port-type transition edge case).
        expected_vlan = payload.get("portVlan")
        if (
            expected_vlan is not None
            and _normalize_vlan_value(final.get("portVlan")) != expected_vlan
        ):
            replace_interface_settings(connection, iface_type, iface_name, payload)
            final = (
                get_interface_settings(connection, iface_type, iface_name) or comparison
            )
        return True, final

    return True, comparison


def _process_config_entry(
    connection: Connection,
    entry: Dict[str, Any],
    state: str,
    *,
    check_mode: bool,
) -> Dict[str, Any]:
    """Process a single config entry. Returns per-interface result dict."""
    name = entry["name"]
    iface_type, iface_name = parse_interface_name(name)
    # Canonical name: omit PORT: prefix, keep LAG: prefix.
    canonical_name = (
        f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
    )

    raw_existing = get_interface_settings(connection, iface_type, iface_name)
    if raw_existing is None and state == STATE_DELETED:
        # Nothing to delete — interface does not exist.
        return {
            "name": canonical_name,
            "before": _to_ansible_state(None),
            "after": _to_ansible_state(None),
            "differences": [],
            "changed": False,
        }
    if raw_existing is None and state in (
        STATE_MERGED,
        STATE_REPLACED,
        STATE_OVERRIDDEN,
    ):
        raise FeL2InterfacesError(
            f"Interface {canonical_name} does not exist on the device"
        )
    existing = raw_existing or {}
    before = _to_ansible_state(existing)

    if state == STATE_MERGED:
        payload, comparison = _build_merged_payload(entry, existing)
    elif state in (STATE_REPLACED, STATE_OVERRIDDEN):
        payload, comparison = _build_replaced_payload(entry, existing)
    elif state == STATE_DELETED:
        payload, comparison = _build_deleted_payload(entry, existing)
    else:
        raise FeL2InterfacesError(f"Unsupported state '{state}'")

    changed, final_raw = _apply_interface(
        connection,
        iface_type,
        iface_name,
        existing,
        payload,
        comparison,
        check_mode=check_mode,
    )

    after = _to_ansible_state(final_raw)
    differences = _compute_differences(before, after) if changed else []

    return {
        "name": canonical_name,
        "before": before,
        "after": after,
        "differences": differences,
        "changed": changed,
    }


# --------------------------------------------------------------------------
# State entry points
# --------------------------------------------------------------------------


def _handle_gathered(module: AnsibleModule, connection: Connection) -> Dict[str, Any]:
    config = module.params.get("config") or []
    interfaces: List[Dict[str, Any]] = []

    if config:
        for entry in config:
            name = entry["name"]
            iface_type, iface_name = parse_interface_name(name)
            # Canonical name: omit PORT: prefix, keep LAG:.
            canonical_name = (
                f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
            )
            raw = get_interface_settings(connection, iface_type, iface_name)
            if raw is None:
                module.warn(f"gathered: interface {canonical_name} not found on device")
            state = _to_ansible_state(raw)
            interfaces.append(
                {
                    "name": canonical_name,
                    "before": state,
                    "after": state,
                    "differences": [],
                    "changed": False,
                }
            )
    else:
        all_ifaces = get_all_interface_settings(connection)
        for item in all_ifaces:
            iface_type = str(item.get("interfaceType") or "PORT").strip().upper()
            iface_name = str(item.get("interfaceName") or "").strip()
            if not iface_name:
                continue
            settings = item.get("interfaceSettings") or item
            state = _to_ansible_state(settings)
            name = f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
            interfaces.append(
                {
                    "name": name,
                    "before": state,
                    "after": state,
                    "differences": [],
                    "changed": False,
                }
            )

    return {"changed": False, "interfaces": interfaces}


def _handle_overridden(module: AnsibleModule, connection: Connection) -> Dict[str, Any]:
    config = module.params.get("config") or []
    if not config:
        raise FeL2InterfacesError("'config' is required when state is 'overridden'")

    check_mode = module.check_mode
    overall_changed = False
    interfaces: List[Dict[str, Any]] = []
    reset_interfaces: List[str] = []
    skipped_interfaces: List[str] = []

    # Build set of configured interface keys for comparison.
    config_keys: Set[Tuple[str, str]] = set()
    for entry in config:
        itype, iname = parse_interface_name(entry["name"])
        config_keys.add((itype, iname))

    # Phase 1: Reset unlisted interfaces to defaults.
    all_ifaces = get_all_interface_settings(connection)
    # Build a lookup of existing (type, name) for pre-validation.
    existing_keys: Set[Tuple[str, str]] = set()
    for item in all_ifaces:
        etype = str(item.get("interfaceType") or "PORT").strip().upper()
        ename = str(item.get("interfaceName") or "").strip()
        if ename:
            existing_keys.add((etype, ename))

    # Pre-validate: all config entries must reference existing interfaces.
    missing = [
        entry["name"]
        for entry in config
        if parse_interface_name(entry["name"]) not in existing_keys
    ]
    if missing:
        raise FeL2InterfacesError(
            f"Interface(s) not found on device: {', '.join(missing)}"
        )

    defaults_payload, defaults_comparison = _build_defaults_payload()

    for item in all_ifaces:
        iface_type = str(item.get("interfaceType") or "PORT").strip().upper()
        iface_name = str(item.get("interfaceName") or "").strip()
        if not iface_name:
            continue
        if (iface_type, iface_name) in config_keys:
            continue
        settings = item.get("interfaceSettings") or item

        try:
            changed, _final_raw = _apply_interface(
                connection,
                iface_type,
                iface_name,
                settings,
                defaults_payload,
                defaults_comparison,
                check_mode=check_mode,
            )
        except (ConnectionError, FeL2InterfacesError) as exc:
            # Skip interfaces that cannot be reset (e.g. LAG in
            # LACP mode where port-type changes are rejected).
            display_name = (
                f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
            )
            module.warn(
                f"overridden: skipped {display_name} " f"(cannot reset — {exc})"
            )
            skipped_interfaces.append(display_name)
            continue
        if changed:
            overall_changed = True
            display_name = (
                f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
            )
            reset_interfaces.append(display_name)

    # Phase 2: Apply config entries as replaced.
    for entry in config:
        result = _process_config_entry(
            connection, entry, STATE_OVERRIDDEN, check_mode=check_mode
        )
        if result["changed"]:
            overall_changed = True
        interfaces.append(result)

    return {
        "changed": overall_changed,
        "interfaces": interfaces,
        "reset_interfaces": reset_interfaces,
        "skipped_interfaces": skipped_interfaces,
    }


def _handle_config_states(
    module: AnsibleModule, connection: Connection, state: str
) -> Dict[str, Any]:
    """Handle merged, replaced, deleted states."""
    config = module.params.get("config") or []
    if not config:
        raise FeL2InterfacesError(f"'config' is required when state is '{state}'")

    check_mode = module.check_mode
    overall_changed = False
    interfaces: List[Dict[str, Any]] = []

    for entry in config:
        result = _process_config_entry(connection, entry, state, check_mode=check_mode)
        if result["changed"]:
            overall_changed = True
        interfaces.append(result)

    return {"changed": overall_changed, "interfaces": interfaces}


# --------------------------------------------------------------------------
# Module entry point
# --------------------------------------------------------------------------


def run_module() -> None:
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
    )

    state = module.params["state"]

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == STATE_GATHERED:
            result = _handle_gathered(module, connection)
        elif state == STATE_OVERRIDDEN:
            result = _handle_overridden(module, connection)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_DELETED):
            result = _handle_config_states(module, connection, state)
        else:
            raise FeL2InterfacesError(f"Unsupported state '{state}'")
        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeL2InterfacesError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
