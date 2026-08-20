# SPDX-License-Identifier: GPL-3.0-or-later
"""Ansible module to manage ExtremeNetworks Fabric Engine VLANs via HTTPAPI.

REST endpoints used:
  GET    /v0/configuration/vlan              - list all VLANs
  GET    /v0/configuration/vlan/{vlan_id}    - get single VLAN
  POST   /v0/configuration/vrf/{vr_name}/vlan - create VLAN
  PATCH  /v0/configuration/vlan/{vlan_id}    - update VLAN scalars
  DELETE /v0/configuration/vrf/{vr_name}/vlan/{vlan_id} - delete VLAN
  POST   /v0/operation/vlan/{vlan_id}/interfaces/:add    - add membership
  POST   /v0/operation/vlan/{vlan_id}/interfaces/:remove  - remove membership
"""

from __future__ import annotations

import copy

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

# -- Documentation -------------------------------------------------------------

DOCUMENTATION = r"""
module: extreme_fe_vlans
short_description: Manage VLANs on ExtremeNetworks Fabric Engine devices
version_added: "1.0.0"
description:
  - Create, update, remove, and query VLANs on ExtremeNetworks Fabric Engine
    devices using the REST API endpoints exposed through the OpenAPI Server.
  - Supports multiple VLANs per task via the C(config) list parameter.
  - Use C(extreme_fe_fabric_l2) to manage ISID to VLAN associations.
author:
  - ExtremeNetworks Networking Automation Team
notes:
  - VLANs are supplied through the C(config) list. The former top-level
    parameters (C(vlan_id), C(vlan_name), C(vlan_type), ...) still work as a
    single-entry config and emit a deprecation warning; the two forms cannot
    be mixed in one task.
  - Tested against Fabric Engine Version 9.3.2.
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI
    plugin shipped with this project.
  - For the VLANs a task lists, C(replaced) and C(overridden) enforce
    membership authoritatively per VLAN, but only for the interface types
    the entry mentions. Neither state reconciles membership on a per-port
    basis across VLANs, so under C(replaced) a port keeps its membership in
    VLANs the task does not list. Under C(overridden) those VLANs are
    deleted outright, which removes the port from them as a side effect.
  - Mentioning an interface type makes it authoritative for both tagged and
    untagged members. Supplying C(lag_interfaces) as an empty list therefore
    clears every LAG from that VLAN, and listing only tagged members removes
    the untagged ones. Omit the key entirely to leave a type alone under
    C(replaced); under C(overridden) an unmentioned type is cleared anyway.
  - C(overridden) deletes every VLAN not listed in C(config), so an
    incomplete C(config) removes working configuration. VLANs carrying L3
    interfaces, SPBM ISIDs or RSMLT instances may be refused by the
    device; those are reported in C(skipped_vlans) and raised as warnings
    rather than aborting the run.
requirements:
  - ansible.netcommon
options:
  state:
    description:
      - Desired VLAN operation.
      - C(merged) applies the supplied attributes and membership changes
        incrementally without removing unspecified values.
      - C(replaced) makes the provided data authoritative per VLAN. Omitted
        scalar attributes are reset to factory defaults. Membership is
        authoritative for interface types the user mentions.
      - C(overridden) like replaced, but authoritative across the whole
        device -- VLANs NOT listed in C(config) are deleted. Use caution
        with this state. VLANs 1 and 4048 are never deleted, and a VLAN the
        device refuses to remove is reported in C(skipped_vlans) rather
        than failing the task. Use C(replaced) to confine changes to the
        VLANs the task lists.
      - C(deleted) removes the specified VLANs from the device. If C(config)
        is empty or omitted, deletes all user-created VLANs.
      - C(gathered) returns current VLAN information without applying changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - List of VLAN configurations to manage.
    type: list
    elements: dict
    suboptions:
      vlan_id:
        description:
          - Numeric VLAN identifier (1-4094).
        type: int
        required: true
      vlan_name:
        description:
          - Friendly name assigned to the VLAN.
        type: str
      vlan_type:
        description:
          - VLAN type identifier required on Fabric Engine platforms.
          - Defaults to PORT_MSTP_RSTP when omitted during creation.
        type: str
        choices:
          - PORT_MSTP_RSTP
          - PROTOCOL_MSTP_RSTP
          - PVLAN_MSTP_RSTP
          - SPBM_BVLAN
      stp_name:
        description:
          - Auto-bind STP instance name associated with the VLAN.
          - An empty string assigns the VLAN to STP instance 0 (device default).
        type: str
      vr_name:
        description:
          - Virtual router or forwarding context the VLAN belongs to.
        type: str
        default: GlobalRouter
      lag_interfaces:
        description:
          - LAG memberships to ensure present on the VLAN.
        type: list
        elements: dict
        suboptions:
          name:
            description:
              - LAG identifier (numeric LAG ID as reported by the device).
            type: str
            required: true
          tag:
            description:
              - Apply the LAG as a tagged or untagged VLAN member.
            type: str
            choices: [tagged, untagged]
            default: tagged
      remove_lag_interfaces:
        description:
          - LAG memberships to remove from the VLAN.
          - Honoured in every write state, not only C(merged). It is most
            useful under C(replaced) alongside an omitted C(lag_interfaces)
            - that combination removes just the members listed here and
            leaves the rest of the VLAN's LAG membership alone, whereas
            supplying C(lag_interfaces) makes the whole type authoritative.
          - Removals are applied after additions, so naming the same LAG in
            both lists removes it.
        type: list
        elements: dict
        suboptions:
          name:
            description:
              - LAG identifier to remove.
            type: str
            required: true
          tag:
            description:
              - Membership type to remove (tagged or untagged).
            type: str
            choices: [tagged, untagged]
            default: tagged
      isis_logical_interfaces:
        description:
          - ISIS logical interfaces to ensure present on the VLAN.
        type: list
        elements: dict
        suboptions:
          name:
            description:
              - Logical interface identifier (for example C(1) or C(10)).
            type: str
            required: true
          tag:
            description:
              - Assign the logical interface as tagged or untagged within the VLAN.
            type: str
            choices: [tagged, untagged]
            default: tagged
      remove_isis_logical_interfaces:
        description:
          - ISIS logical interface memberships to remove from the VLAN.
          - Honoured in every write state, not only C(merged), with the same
            semantics as C(remove_lag_interfaces).
        type: list
        elements: dict
        suboptions:
          name:
            description:
              - Logical interface identifier to remove.
            type: str
            required: true
          tag:
            description:
              - Membership type to remove (tagged or untagged).
            type: str
            choices: [tagged, untagged]
            default: tagged
  # Deprecated pre-1.2.1 interface. These mirror the 'config' suboptions
  # and are folded into a single-entry config list at runtime.
  vlan_id:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: int
  vlan_name:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: str
  vlan_type:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: str
    choices: [PORT_MSTP_RSTP, PROTOCOL_MSTP_RSTP, PVLAN_MSTP_RSTP, SPBM_BVLAN]
  stp_name:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: str
  vr_name:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: str
    default: GlobalRouter
  lag_interfaces:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - See the matching field under C(config).
        type: str
      tag:
        description:
          - See the matching field under C(config).
        type: str
        choices: [tagged, untagged]
        default: tagged
  remove_lag_interfaces:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - See the matching field under C(config).
        type: str
      tag:
        description:
          - See the matching field under C(config).
        type: str
        choices: [tagged, untagged]
        default: tagged
  isis_logical_interfaces:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - See the matching field under C(config).
        type: str
      tag:
        description:
          - See the matching field under C(config).
        type: str
        choices: [tagged, untagged]
        default: tagged
  remove_isis_logical_interfaces:
    description:
      - Deprecated. Supply this through the C(config) list instead;
        the top-level form manages a single VLAN.
    type: list
    elements: dict
    suboptions:
      name:
        description:
          - See the matching field under C(config).
        type: str
      tag:
        description:
          - See the matching field under C(config).
        type: str
        choices: [tagged, untagged]
        default: tagged
  gather_filter:
    description:
      - Limit gathered VLAN facts to these VLAN identifiers.
    type: list
    elements: int
"""

EXAMPLES = r"""
- name: Manage VLANs on Fabric Engine devices
  hosts: switches
  gather_facts: false
  tasks:
    - name: Create or update multiple VLANs (merged)
      extreme.fe.extreme_fe_vlans:
        state: merged
        config:
          - vlan_id: 20
            vlan_name: Campus-20
            vr_name: GlobalRouter
            lag_interfaces:
              - name: "10"
                tag: tagged
          - vlan_id: 30
            vlan_name: Campus-30
            vr_name: GlobalRouter

    - name: Enforce VLAN 200 membership (replaced)
      extreme.fe.extreme_fe_vlans:
        state: replaced
        config:
          - vlan_id: 200
            vr_name: GlobalRouter
            lag_interfaces:
              - name: "10"
                tag: tagged

      # Deletes every other user VLAN on the device. VLANs 1 and 4048 are
      # left alone; anything the device refuses to delete is reported in
      # skipped_vlans.
    - name: Override all VLANs - only these should exist (overridden)
      extreme.fe.extreme_fe_vlans:
        state: overridden
        config:
          - vlan_id: 20
            vlan_name: Campus-20
            vr_name: GlobalRouter
          - vlan_id: 30
            vlan_name: Campus-30
            vr_name: GlobalRouter

    - name: Remove specific LAG from VLAN 200 (merged with remove)
      extreme.fe.extreme_fe_vlans:
        state: merged
        config:
          - vlan_id: 200
            vr_name: GlobalRouter
            remove_lag_interfaces:
              - name: "11"
                tag: tagged

    - name: Delete VLAN 200
      extreme.fe.extreme_fe_vlans:
        state: deleted
        config:
          - vlan_id: 200
            vr_name: GlobalRouter

    - name: Delete all user-created VLANs
      extreme.fe.extreme_fe_vlans:
        state: deleted

    - name: Gather specific VLANs
      extreme.fe.extreme_fe_vlans:
        state: gathered
        gather_filter: [20, 30]
        register: vlan_info

    - name: Display VLAN configuration
      ansible.builtin.debug:
        var: vlan_info.gathered
"""

RETURN = r"""
before:
  description:
    - Full VLAN configuration state before changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
after:
  description:
    - Full VLAN configuration state after changes.
    - Only returned when the module made changes.
  returned: when changed
  type: list
  elements: dict
deleted_vlans:
  description:
    - VLAN IDs removed because C(state=overridden) and the task did not
      list them. In check mode, the VLANs that would have been removed.
  returned: when state is overridden and unlisted VLANs were removed
  type: list
  elements: int
  sample: [200, 300]
skipped_vlans:
  description:
    - Unlisted VLANs that C(state=overridden) could not delete, typically
      because an L3 interface, SPBM ISID or RSMLT instance still
      references them. Each is also raised as a warning.
  returned: when state is overridden and a delete was refused
  type: list
  elements: dict
  contains:
    vlan_id:
      description: The VLAN that could not be deleted.
      type: int
    reason:
      description: The error the device returned.
      type: str
gathered:
  description:
    - VLAN configuration gathered from the device.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
vlans:
  description:
    - Under the action states, per-VLAN operation results with differences.
    - Under C(state=gathered) this instead repeats C(gathered), which is what
      the module returned for that state up to 1.2.0. That form is deprecated
      and will be removed in 2.0.0 - use C(gathered).
  returned: always except when the task fails
  type: list
  elements: dict
  contains:
    vlan_id:
      description: VLAN identifier.
      type: int
    before:
      description: VLAN configuration before the operation.
      type: dict
    after:
      description: VLAN configuration after the operation.
      type: dict
    changed:
      description: Whether this VLAN was modified.
      type: bool
    differences:
      description: Fields that changed with before and after values.
      type: dict
"""

# -- Constants -----------------------------------------------------------------

# State string constants
STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# There is deliberately no module-wide Ansible <-> REST field map here. The
# three places that translate names need different subsets, so a shared table
# would have to be filtered at each call site and would invite sending a
# non-patchable field by mistake:
#   _to_ansible_output()            all five scalars, plus the two membership
#                                   lists, which no scalar map covers
#   _build_scalar_update_merged()   name/vlanType/stpName only -- id and
#                                   vrName identify the VLAN and cannot be
#                                   PATCHed
#   _build_scalar_update_replaced() the same three, each with its own default
# Each site therefore spells out the pairs it uses.

# Factory defaults for scalar attributes -- used by replaced/overridden to
# reset omitted fields. Verified via OpenAPI spec:
#   - name: device auto-assigns "VLAN-{id}" when not specified
#   - vlanType: PORT_MSTP_RSTP is the standard Fabric Engine type for port-based VLANs
#   - stpName: empty string -> STP instance 0 (OpenAPI: "an empty or not present
#     string indicates the VLAN is assigned to STP instance 0")
FULL_DEFAULTS = {
    "vlan_name": None,       # Will be computed as "VLAN-{id}" per VLAN
    "vlan_type": "PORT_MSTP_RSTP",
    "stp_name": "",          # Empty string = STP instance 0 (from OpenAPI spec)
}

# System VLANs that should not be deleted or reset by overridden
SYSTEM_VLANS = {1, 4048}

# Interface type constants for membership payloads
INTERFACE_TYPE_LAG = "LAG"
INTERFACE_TYPE_ISIS = "ISIS_LOGICAL_INTERFACE"

# Tag value translation: Ansible choice -> REST API value
TAG_VALUE_MAP = {"tagged": "TAG", "untagged": "UNTAG"}

# HTTP status codes considered successful
_SUCCESS_STATUS_CODES = {200, 201, 202, 204}

# -- ARGUMENT_SPEC -------------------------------------------------------------

_INTERFACE_ENTRY_SPEC = {
    "name": {"type": "str", "required": True},
    "tag": {"type": "str", "choices": ["tagged", "untagged"], "default": "tagged"},
}

ARGUMENT_SPEC = {
    "state": {
        "type": "str",
        "choices": [STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN,
                    STATE_DELETED, STATE_GATHERED],
        "default": STATE_MERGED,
    },
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "vlan_id": {"type": "int", "required": True},
            "vlan_name": {"type": "str"},
            "vlan_type": {
                "type": "str",
                "choices": ["PORT_MSTP_RSTP", "PROTOCOL_MSTP_RSTP",
                            "PVLAN_MSTP_RSTP", "SPBM_BVLAN"],
            },
            "stp_name": {"type": "str"},
            "vr_name": {"type": "str", "default": "GlobalRouter"},
            "lag_interfaces": {
                "type": "list",
                "elements": "dict",
                "options": dict(_INTERFACE_ENTRY_SPEC),
            },
            "remove_lag_interfaces": {
                "type": "list",
                "elements": "dict",
                "options": dict(_INTERFACE_ENTRY_SPEC),
            },
            "isis_logical_interfaces": {
                "type": "list",
                "elements": "dict",
                "options": dict(_INTERFACE_ENTRY_SPEC),
            },
            "remove_isis_logical_interfaces": {
                "type": "list",
                "elements": "dict",
                "options": dict(_INTERFACE_ENTRY_SPEC),
            },
        },
    },
    "gather_filter": {"type": "list", "elements": "int"},
}

# ── Backwards compatibility with the pre-1.2.1 flat interface ────────────────
# VLANs used to be supplied as top-level parameters instead of a 'config'
# list. Those parameters are re-declared here from the same suboption spec, so
# existing playbooks keep working; _entries_from_params() folds them into a
# single-entry config and emits a deprecation warning.
_FLAT_PARAMS = tuple(ARGUMENT_SPEC["config"]["options"])
# Suboptions carrying a default are never None once Ansible has parsed the
# task, so they cannot signal "the user supplied this". They only count when
# they differ from that default.
_FLAT_DEFAULTS = {
    name: spec["default"]
    for name, spec in ARGUMENT_SPEC["config"]["options"].items()
    if "default" in spec
}
for _name, _spec in ARGUMENT_SPEC["config"]["options"].items():
    # 'required' belongs to the config entry, not the top level: a task using
    # the config list supplies none of these, so copying the flag would make
    # the new interface impossible to use.
    _flat = dict(_spec)
    _flat.pop("required", None)
    ARGUMENT_SPEC[_name] = _flat


def _flat_form_used(module):
    """True when the caller supplied any top-level VLAN parameter."""
    for name in _FLAT_PARAMS:
        value = module.params.get(name)
        if value is None:
            continue
        if name in _FLAT_DEFAULTS and value == _FLAT_DEFAULTS[name]:
            continue
        return True
    return False


def _entries_from_params(module):
    """Normalise both supported input forms into a list of VLAN entries.

    The flat form is the pre-1.2.1 interface. It is accepted as a single-entry
    config list so existing playbooks keep working, and warned about once.
    """
    config = module.params.get("config")
    flat_used = _flat_form_used(module)

    # 'is not None' rather than truthiness: Ansible leaves an omitted list as
    # None but keeps an explicit 'config: []' as an empty list, and supplying
    # that alongside the deprecated parameters is still mixing the two forms.
    if config is not None and flat_used:
        module.fail_json(
            msg="Use either the 'config' list or the top-level VLAN parameters, "
                "not both. The top-level form is deprecated; move its values "
                "into 'config'.")
    if config:
        return [dict(entry) for entry in config]
    if flat_used:
        module.deprecate(
            "Supplying VLAN attributes at the top level is deprecated; use the "
            "'config' list instead, for example "
            "config: [{vlan_id: 100, vlan_name: Data}]. The top-level form "
            "manages a single VLAN and cannot express 'overridden' across "
            "several VLANs.",
            version="2.0.0",
            collection_name="extreme.fe",
        )
        # vlan_id is required inside a config entry, but the flag is stripped
        # from the flat copies, so the top-level form can reach here without
        # one. Every REST path formats the ID with %d, so catch it now rather
        # than fail with a TypeError deep in the request layer.
        if module.params.get("vlan_id") is None:
            module.fail_json(
                msg="'vlan_id' is required. It is missing from the deprecated "
                    "top-level parameters; supply it, or move the VLAN into "
                    "the 'config' list where it is enforced.")
        return [{name: module.params.get(name) for name in _FLAT_PARAMS}]
    return []

# -- Custom Exception ----------------------------------------------------------


class FeVlansError(Exception):
    """Base exception for module-level errors."""

    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self):
        data = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# -- Helper Functions ----------------------------------------------------------


def _is_not_found_response(payload):
    """Return True if the REST response indicates a 404 / not-found condition."""
    if not isinstance(payload, dict):
        return False
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    if code == 404:
        return True
    message = (payload.get("errorMessage") or payload.get("message")
               or payload.get("detail"))
    if isinstance(message, str):
        lowered = message.lower()
        if "not found" in lowered or "does not exist" in lowered:
            return True
    return False


def _raise_for_error_payload(payload, method, path):
    """Fail when the device answers with a success status but an error body.

    The httpapi plugin raises for HTTP status codes, but Fabric Engine can also return
    a 2xx carrying an error document. The scalar writes ignored the response
    entirely, so a rejected create, update or delete was reported as applied.
    That matters most for the overridden delete pre-pass, which would list a
    VLAN in 'deleted_vlans' while it was still on the device and never record
    it in 'skipped_vlans'.

    Membership operations are checked separately by _validate_multi_status(),
    which understands the per-interface 207 response shape.
    """
    if not isinstance(payload, dict):
        return
    code = (payload.get("errorCode") or payload.get("statusCode")
            or payload.get("code"))
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    # Only an explicit error marker counts -- a normal VLAN document carries
    # none of these keys, so this cannot misfire on a successful read.
    if not (payload.get("errorCode") or (isinstance(code, int) and code >= 400)):
        return
    message = (payload.get("errorMessage") or payload.get("message")
               or payload.get("detail"))
    raise FeVlansError(
        "Device rejected %s %s%s" % (
            method, path, ": %s" % message if message else ""),
        details={"response": payload},
    )


def _call_api(connection, method, path, payload=None, allow_not_found=False):
    """Send a REST API request and return the response.

    The response is checked for an embedded error document. Pass
    allow_not_found=True from the read helpers, which map a not-found body to
    None or [] themselves rather than treating it as a failure.
    """
    response = connection.send_request(payload, path=path, method=method)
    if allow_not_found and _is_not_found_response(response):
        return response
    _raise_for_error_payload(response, method, path)
    return response


def _normalize_membership_entry(option, entry):
    """Validate and normalize a membership entry to (name, tag_value) tuple."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if name is None or str(name).strip() == "":
        raise FeVlansError("Interface name is required for '%s' entries" % option)
    tag_choice = str(entry.get("tag", "tagged")).lower()
    tag_value = TAG_VALUE_MAP.get(tag_choice)
    if tag_value is None:
        raise FeVlansError(
            "Unsupported tag value '%s' for interface '%s'" % (tag_choice, name))
    return str(name), tag_value


def _key_to_entry(key):
    """Convert a (interfaceType, interfaceName) key to a REST entry dict."""
    interface_type, interface_name = key
    return {"interfaceType": interface_type, "interfaceName": interface_name}


def _sanitize_membership(entries):
    """Clean and normalize a list of membership entries from REST response."""
    sanitized = []
    if not entries:
        return sanitized
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        interface_type = entry.get("interfaceType")
        interface_name = entry.get("interfaceName")
        if not interface_type or not interface_name:
            continue
        sanitized.append({
            "interfaceType": str(interface_type),
            "interfaceName": str(interface_name),
        })
    return sanitized


def _membership_key(entry):
    """Return a hashable key for a membership entry."""
    return (str(entry.get("interfaceType", "")).upper(),
            str(entry.get("interfaceName", "")))


def _remove_membership_entry(entries, key):
    """Remove the first entry matching key from the list."""
    removed = False
    filtered = []
    for entry in entries:
        if not removed and _membership_key(entry) == key:
            removed = True
            continue
        filtered.append(entry)
    if removed:
        entries[:] = filtered
    return removed


def _validate_multi_status(operation, vlan_id, response):
    """Check a multi-status membership response for failures."""
    if response in (None, ""):
        return
    entries = response
    if isinstance(entries, dict):
        for key in ("interfaces", "entries", "items", "results"):
            candidate = entries.get(key)
            if isinstance(candidate, list):
                entries = candidate
                break
    if not isinstance(entries, list):
        return
    failures = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        status = item.get("statusCode")
        try:
            status_int = int(status) if status is not None else None
        except (TypeError, ValueError):
            status_int = None
        if status_int is None or status_int not in _SUCCESS_STATUS_CODES:
            failures.append({
                "interfaceType": item.get("interfaceType"),
                "interfaceName": item.get("interfaceName"),
                "tagType": item.get("tagType"),
                "statusCode": status,
                "errorMessage": item.get("errorMessage"),
            })
    if failures:
        raise FeVlansError(
            "Failed to %s VLAN membership for VLAN %d" % (operation, vlan_id),
            details={"failures": failures},
        )


# -- Data-Fetching Functions ---------------------------------------------------


def _get_all_vlans(connection):
    """GET /v0/configuration/vlan -- retrieve all VLANs from device."""
    data = _call_api(connection, "GET", "/v0/configuration/vlan",
                     allow_not_found=True)
    if data is None or _is_not_found_response(data):
        return []
    if isinstance(data, list):
        return data
    raise FeVlansError(
        "Unexpected response when retrieving VLAN summary",
        details={"response": data},
    )


def _get_vlan(connection, vlan_id):
    """GET /v0/configuration/vlan/{vlan_id} -- retrieve a single VLAN."""
    try:
        data = _call_api(
            connection, "GET", "/v0/configuration/vlan/%d" % vlan_id,
            allow_not_found=True)
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        return data
    raise FeVlansError(
        "Unexpected response when retrieving VLAN configuration",
        details={"response": data},
    )


# -- REST Write Operations ----------------------------------------------------


def _create_vlan(connection, vr_name, vlan_id, vlan_name, vlan_type, stp_name):
    """POST /v0/configuration/vrf/{vr_name}/vlan -- create a new VLAN."""
    payload = {"id": vlan_id}
    if vlan_type:
        payload["vlanType"] = vlan_type
    if stp_name is not None:
        payload["stpName"] = stp_name
    else:
        payload["stpName"] = ""
    if vlan_name is not None:
        payload["name"] = vlan_name
    _call_api(connection, "POST",
              "/v0/configuration/vrf/%s/vlan" % vr_name, payload)


def _update_vlan(connection, vlan_id, payload):
    """PATCH /v0/configuration/vlan/{vlan_id} -- update VLAN scalars."""
    if payload:
        _call_api(connection, "PATCH",
                  "/v0/configuration/vlan/%d" % vlan_id, payload)


def _delete_vlan(connection, vr_name, vlan_id):
    """DELETE /v0/configuration/vrf/{vr_name}/vlan/{vlan_id}."""
    _call_api(connection, "DELETE",
              "/v0/configuration/vrf/%s/vlan/%d" % (vr_name, vlan_id))


# -- Output Formatter ----------------------------------------------------------


def _to_ansible_output(raw):
    """Convert a raw REST VLAN dict to Ansible-friendly output format."""
    out = {}
    out["vlan_id"] = raw.get("id")
    out["vlan_name"] = raw.get("name")
    out["vlan_type"] = raw.get("vlanType")
    out["stp_name"] = raw.get("stpName")
    out["vr_name"] = raw.get("vrName")
    out["tagged_interfaces"] = _sanitize_membership(raw.get("taggedInterfaces"))
    out["untagged_interfaces"] = _sanitize_membership(
        raw.get("untaggedInterfaces"))
    return out


def _to_ansible_list(raw_list):
    """Convert a list of raw REST VLAN dicts to Ansible output format."""
    return [_to_ansible_output(v) for v in raw_list]


# -- Diff / Comparison Logic ---------------------------------------------------


def _compute_diff(before, after):
    """Compare before/after Ansible output dicts, returning changed fields."""
    differences = {}
    if before is None and after is None:
        return differences
    if before is None:
        before = {}
    if after is None:
        after = {}
    all_keys = set(before.keys()) | set(after.keys())
    for key in sorted(all_keys):
        bval = before.get(key)
        aval = after.get(key)
        if bval != aval:
            differences[key] = {"before": bval, "after": aval}
    return differences


# -- Membership Operations ----------------------------------------------------


def _parse_interface_list(entries, option, interface_type):
    """Parse an interface list parameter into tagged/untagged REST payloads."""
    result = {"TAG": [], "UNTAG": []}
    if not entries or not isinstance(entries, list):
        return result
    for entry in entries:
        normalized = _normalize_membership_entry(option, entry)
        if normalized is None:
            continue
        name, tag_value = normalized
        result[tag_value].append({
            "interfaceType": interface_type,
            "interfaceName": name,
        })
    return result


def _membership_ops_for_merge(config_entry):
    """Compute membership additions/removals for merged state."""
    additions = {"TAG": [], "UNTAG": []}
    removals = {"TAG": [], "UNTAG": []}

    for option, itype in (
        ("lag_interfaces", INTERFACE_TYPE_LAG),
        ("isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    ):
        parsed = _parse_interface_list(
            config_entry.get(option), option, itype)
        for tv in ("TAG", "UNTAG"):
            additions[tv].extend(parsed[tv])

    for option, itype in (
        ("remove_lag_interfaces", INTERFACE_TYPE_LAG),
        ("remove_isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    ):
        parsed = _parse_interface_list(
            config_entry.get(option), option, itype)
        for tv in ("TAG", "UNTAG"):
            removals[tv].extend(parsed[tv])

    return additions, removals


def _membership_ops_authoritative(config_entry, existing, *, purge_missing):
    """Compute membership adds/removes for replaced/overridden state.

    When purge_missing=True (overridden), interface types not mentioned in
    config are also purged. When False (replaced), unmentioned types are
    left alone.
    """
    desired_sets = {}
    explicit_removals = {}
    for tv in ("TAG", "UNTAG"):
        for itype in (INTERFACE_TYPE_LAG, INTERFACE_TYPE_ISIS):
            desired_sets[(tv, itype)] = None
            explicit_removals[(tv, itype)] = set()

    # Build current sets from device state
    current_sets = {}
    for tv, source in (
        ("TAG", existing.get("taggedInterfaces")),
        ("UNTAG", existing.get("untaggedInterfaces")),
    ):
        for entry in _sanitize_membership(source):
            key = _membership_key(entry)
            combo = (tv, key[0])
            current_sets.setdefault(combo, set()).add(key)

    # Process user-specified additions
    for option, itype in (
        ("lag_interfaces", INTERFACE_TYPE_LAG),
        ("isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    ):
        entries = config_entry.get(option)
        if entries is None:
            if purge_missing:
                for tv in ("TAG", "UNTAG"):
                    if desired_sets[(tv, itype)] is None:
                        desired_sets[(tv, itype)] = set()
            continue
        if not isinstance(entries, list):
            continue
        # Mentioning an interface type makes it authoritative for both tag
        # values, which is what replaced and overridden promise. Seeding both
        # sets here rather than only where a member is supplied covers the two
        # cases that would otherwise leave membership untouched: an empty list
        # ("this VLAN has no members of this type") and a list naming only
        # tagged members, which should still clear the untagged ones. Without
        # it an empty list under overridden was less authoritative than
        # omitting the key altogether.
        for tv in ("TAG", "UNTAG"):
            if desired_sets[(tv, itype)] is None:
                desired_sets[(tv, itype)] = set()
        for raw_entry in entries:
            normalized = _normalize_membership_entry(option, raw_entry)
            if normalized is None:
                continue
            name, tv = normalized
            key = (itype, name)
            combo = (tv, itype)
            if desired_sets[combo] is None:
                desired_sets[combo] = set()
            desired_sets[combo].add(key)

    # Process explicit removals
    for option, itype in (
        ("remove_lag_interfaces", INTERFACE_TYPE_LAG),
        ("remove_isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    ):
        entries = config_entry.get(option) or []
        if not isinstance(entries, list):
            continue
        for raw_entry in entries:
            normalized = _normalize_membership_entry(option, raw_entry)
            if normalized is None:
                continue
            name, tv = normalized
            explicit_removals[(tv, itype)].add((itype, name))

    # Compute final additions and removals
    additions_sets = {"TAG": set(), "UNTAG": set()}
    removals_sets = {"TAG": set(), "UNTAG": set()}

    all_combos = (set(current_sets.keys()) | set(desired_sets.keys())
                  | set(explicit_removals.keys()))
    for combo in all_combos:
        tv, itype = combo
        cur = current_sets.get(combo, set())
        des = desired_sets.get(combo)
        rem = set(explicit_removals.get(combo, set()))
        if des is not None:
            additions_sets[tv].update(des - cur)
            rem.update(cur - des)
        additions_sets[tv] -= rem
        removals_sets[tv].update(rem)

    additions = {
        tv: [_key_to_entry(k) for k in sorted(additions_sets[tv])]
        for tv in ("TAG", "UNTAG")
    }
    removals = {
        tv: [_key_to_entry(k) for k in sorted(removals_sets[tv])]
        for tv in ("TAG", "UNTAG")
    }
    return additions, removals


def _resolve_membership_ops(config_entry, existing, state):
    """Dispatch to the correct membership operation builder."""
    if state == STATE_MERGED:
        return _membership_ops_for_merge(config_entry)
    if state == STATE_REPLACED:
        return _membership_ops_authoritative(
            config_entry, existing, purge_missing=False)
    if state == STATE_OVERRIDDEN:
        return _membership_ops_authoritative(
            config_entry, existing, purge_missing=True)
    return {"TAG": [], "UNTAG": []}, {"TAG": [], "UNTAG": []}


def _apply_membership_changes(
    module, connection, vlan_id, existing, additions, removals,
):
    """Apply membership additions/removals. Returns (changed, updated)."""
    current_tagged = _sanitize_membership(existing.get("taggedInterfaces"))
    current_untagged = _sanitize_membership(
        existing.get("untaggedInterfaces"))

    tagged_keys = {_membership_key(e) for e in current_tagged}
    untagged_keys = {_membership_key(e) for e in current_untagged}

    lag_add_payload = []
    lag_remove_payload = []
    patch_required = False
    membership_changed = False
    tagged_changed = False
    untagged_changed = False

    for tv in ("TAG", "UNTAG"):
        target_list = current_tagged if tv == "TAG" else current_untagged
        target_keys = tagged_keys if tv == "TAG" else untagged_keys

        for entry in additions[tv]:
            key = _membership_key(entry)
            if key in target_keys:
                continue
            target_keys.add(key)
            target_list.append(entry.copy())
            membership_changed = True
            if entry["interfaceType"] == INTERFACE_TYPE_LAG:
                lag_add_payload.append({"tagType": tv, **entry})
            else:
                patch_required = True
            if tv == "TAG":
                tagged_changed = True
            else:
                untagged_changed = True

        for entry in removals[tv]:
            key = _membership_key(entry)
            if key not in target_keys:
                continue
            target_keys.remove(key)
            removed = _remove_membership_entry(target_list, key)
            if not removed:
                continue
            membership_changed = True
            if entry["interfaceType"] == INTERFACE_TYPE_LAG:
                lag_remove_payload.append({"tagType": tv, **entry})
            else:
                patch_required = True
            if tv == "TAG":
                tagged_changed = True
            else:
                untagged_changed = True

    if not membership_changed:
        return False, existing

    working_copy = copy.deepcopy(existing) if existing else {}
    working_copy["taggedInterfaces"] = current_tagged
    working_copy["untaggedInterfaces"] = current_untagged

    if module.check_mode:
        return True, working_copy

    if lag_add_payload:
        response = _call_api(
            connection, "POST",
            "/v0/operation/vlan/%d/interfaces/:add" % vlan_id,
            lag_add_payload,
        )
        _validate_multi_status("add", vlan_id, response)

    if lag_remove_payload:
        response = _call_api(
            connection, "POST",
            "/v0/operation/vlan/%d/interfaces/:remove" % vlan_id,
            lag_remove_payload,
        )
        _validate_multi_status("remove", vlan_id, response)

    if patch_required:
        payload = {}
        if tagged_changed:
            payload["taggedInterfaces"] = current_tagged
        if untagged_changed:
            payload["untaggedInterfaces"] = current_untagged
        if payload:
            _update_vlan(connection, vlan_id, payload)

    return True, working_copy


# -- Payload Builders ----------------------------------------------------------


def _vlan_default_name(vlan_id):
    """Return the device default name for a VLAN."""
    return "VLAN-%d" % vlan_id


def _build_scalar_update_merged(config_entry, existing):
    """Build a PATCH payload for merged state -- only user-supplied fields."""
    payload = {}
    for ansible_key, rest_key in (
        ("vlan_name", "name"),
        ("vlan_type", "vlanType"),
        ("stp_name", "stpName"),
    ):
        value = config_entry.get(ansible_key)
        if value is not None and value != existing.get(rest_key):
            payload[rest_key] = value
    return payload


def _build_scalar_update_replaced(config_entry, existing, vlan_id):
    """Build a PATCH payload for replaced/overridden state.

    User-supplied fields are applied. Omitted scalar fields are reset to
    FULL_DEFAULTS values, ensuring declarative compliance.
    """
    payload = {}

    # vlan_name: user value or default "VLAN-{id}"
    user_name = config_entry.get("vlan_name")
    desired_name = (user_name if user_name is not None
                    else _vlan_default_name(vlan_id))
    if desired_name != existing.get("name"):
        payload["name"] = desired_name

    # vlan_type: user value or default PORT_MSTP_RSTP
    user_type = config_entry.get("vlan_type")
    desired_type = (user_type if user_type is not None
                    else FULL_DEFAULTS["vlan_type"])
    if desired_type != existing.get("vlanType"):
        payload["vlanType"] = desired_type

    # stp_name: user value or default "" (STP instance 0)
    user_stp = config_entry.get("stp_name")
    desired_stp = (user_stp if user_stp is not None
                   else FULL_DEFAULTS["stp_name"])
    if desired_stp != existing.get("stpName"):
        payload["stpName"] = desired_stp

    return payload


# -- State Handlers ------------------------------------------------------------


def _handle_gathered(module, connection):
    """Handle state=gathered: read-only, return current VLAN state."""
    gather_filter = module.params.get("gather_filter")
    if gather_filter:
        raw_list = []
        for vid in gather_filter:
            vlan = _get_vlan(connection, vid)
            if vlan is not None:
                raw_list.append(vlan)
    else:
        raw_list = _get_all_vlans(connection)
    facts = _to_ansible_list(raw_list)
    # 'gathered' is the standard key. 'vlans' is the key this module returned
    # for state=gathered up to 1.2.0, kept so existing playbooks keep working;
    # it is deprecated and goes away in 2.0.0. Note that under the action
    # states 'vlans' carries per-VLAN operation results instead, so consumers
    # should prefer 'gathered' here.
    return {"changed": False, "gathered": facts, "vlans": facts}


def _handle_single_vlan_merge(module, connection, config_entry, existing_map):
    """Process a single VLAN entry for merged state."""
    vlan_id = config_entry["vlan_id"]
    vr_name = config_entry.get("vr_name", "GlobalRouter")
    existing_raw = existing_map.get(vlan_id)
    changed = False

    before_output = _to_ansible_output(existing_raw) if existing_raw else None

    if existing_raw is None:
        changed = True
        vlan_name = config_entry.get("vlan_name")
        # Ansible pre-populates every declared suboption, so the key is always
        # present and get()'s default never applies -- an omitted vlan_type
        # arrives as None. Test the value instead.
        vlan_type = config_entry.get("vlan_type")
        if vlan_type is None:
            vlan_type = FULL_DEFAULTS["vlan_type"]
        stp_name = config_entry.get("stp_name")
        if not module.check_mode:
            _create_vlan(connection, vr_name, vlan_id,
                         vlan_name, vlan_type, stp_name)
            existing_raw = (_get_vlan(connection, vlan_id)
                            or {"id": vlan_id, "vrName": vr_name})
        else:
            existing_raw = {"id": vlan_id, "vrName": vr_name}
            # An omitted name is auto-assigned by the device as VLAN-<id>,
            # so predict that rather than leaving it unset -- otherwise the
            # check-mode diff shows a name change that never happens.
            existing_raw["name"] = (
                vlan_name if vlan_name is not None
                else _vlan_default_name(vlan_id)
            )
            if vlan_type is not None:
                existing_raw["vlanType"] = vlan_type
            # _create_vlan() always sends stpName, falling back to "" (STP
            # instance 0), so predict that rather than leaving it unset.
            existing_raw["stpName"] = (
                stp_name if stp_name is not None
                else FULL_DEFAULTS["stp_name"]
            )
    else:
        existing_raw = copy.deepcopy(existing_raw)

    update_payload = _build_scalar_update_merged(config_entry, existing_raw)
    if update_payload:
        changed = True
        if not module.check_mode:
            _update_vlan(connection, vlan_id, update_payload)
        for k, v in update_payload.items():
            existing_raw[k] = v

    additions, removals = _resolve_membership_ops(
        config_entry, existing_raw, STATE_MERGED)
    has_ops = any(additions.values()) or any(removals.values())
    if has_ops:
        mem_changed, existing_raw = _apply_membership_changes(
            module, connection, vlan_id, existing_raw, additions, removals,
        )
        if mem_changed:
            changed = True

    if changed and not module.check_mode:
        refreshed = _get_vlan(connection, vlan_id)
        if refreshed is not None:
            existing_raw = refreshed

    after_output = _to_ansible_output(existing_raw)
    differences = _compute_diff(before_output, after_output) if changed else {}

    return {
        "vlan_id": vlan_id,
        "before": before_output,
        "after": after_output,
        "changed": changed,
        "differences": differences,
    }


def _handle_single_vlan_replace(
    module, connection, config_entry, existing_map, state,
):
    """Process a single VLAN for replaced/overridden state.

    Omitted scalar attributes are reset to FULL_DEFAULTS.
    """
    vlan_id = config_entry["vlan_id"]
    vr_name = config_entry.get("vr_name", "GlobalRouter")
    existing_raw = existing_map.get(vlan_id)
    changed = False

    before_output = _to_ansible_output(existing_raw) if existing_raw else None

    if existing_raw is None:
        changed = True
        vlan_name = config_entry.get("vlan_name")
        # Same as the merged path: the key is always present, so an omitted
        # vlan_type is None rather than absent and get()'s default is dead.
        vlan_type = config_entry.get("vlan_type")
        if vlan_type is None:
            vlan_type = FULL_DEFAULTS["vlan_type"]
        stp_name = config_entry.get("stp_name")
        if stp_name is None:
            stp_name = FULL_DEFAULTS["stp_name"]
        if not module.check_mode:
            _create_vlan(connection, vr_name, vlan_id,
                         vlan_name, vlan_type, stp_name)
            existing_raw = (_get_vlan(connection, vlan_id)
                            or {"id": vlan_id, "vrName": vr_name})
        else:
            existing_raw = {"id": vlan_id, "vrName": vr_name}
            # Same as the merged path: the device auto-names an unnamed VLAN
            # VLAN-<id>, so predict that instead of leaving it unset.
            existing_raw["name"] = (
                vlan_name if vlan_name is not None
                else _vlan_default_name(vlan_id)
            )
            existing_raw["vlanType"] = vlan_type
            existing_raw["stpName"] = stp_name
    else:
        existing_raw = copy.deepcopy(existing_raw)

    # Sub-issue A fix: reset omitted scalars to FULL_DEFAULTS
    update_payload = _build_scalar_update_replaced(
        config_entry, existing_raw, vlan_id)
    if update_payload:
        changed = True
        if not module.check_mode:
            _update_vlan(connection, vlan_id, update_payload)
        for k, v in update_payload.items():
            existing_raw[k] = v

    # Authoritative membership
    purge = (state == STATE_OVERRIDDEN)
    additions, removals = _membership_ops_authoritative(
        config_entry, existing_raw, purge_missing=purge,
    )
    has_ops = any(additions.values()) or any(removals.values())
    if has_ops:
        mem_changed, existing_raw = _apply_membership_changes(
            module, connection, vlan_id, existing_raw, additions, removals,
        )
        if mem_changed:
            changed = True

    if changed and not module.check_mode:
        refreshed = _get_vlan(connection, vlan_id)
        if refreshed is not None:
            existing_raw = refreshed

    after_output = _to_ansible_output(existing_raw)
    differences = _compute_diff(before_output, after_output) if changed else {}

    return {
        "vlan_id": vlan_id,
        "before": before_output,
        "after": after_output,
        "changed": changed,
        "differences": differences,
    }


def _handle_overridden_prepass(module, connection, config, all_vlans):
    """Delete VLANs the task did not list (overridden pre-pass).

    overridden is authoritative across the whole device, so a VLAN absent
    from 'config' is removed rather than reset -- matching the resource
    module convention used by ios_vlans, nxos_vlans, eos_vlans and
    junos_vlans. Use state=replaced to confine changes to listed VLANs.

    System VLANs (1, 4048) are skipped. The reference implementations do
    delete their reserved VLANs, but on Fabric Engine these are the default and
    reserved management VLANs and removing them is not recoverable from a
    playbook.

    A VLAN the device refuses to delete -- typically because an L3
    interface, SPBM ISID or RSMLT instance still references it -- is
    reported instead of failing the run, so one stuck VLAN does not abort
    an otherwise valid sweep.

    Returns (results, deleted_vlans, skipped_vlans).
    """
    listed_ids = {entry["vlan_id"] for entry in config}
    results = []
    deleted = []
    skipped = []

    for raw_vlan in all_vlans:
        vid = raw_vlan.get("id")
        if vid is None or vid in listed_ids or vid in SYSTEM_VLANS:
            continue

        before_output = _to_ansible_output(raw_vlan)
        vr_name = raw_vlan.get("vrName", "GlobalRouter")

        if not module.check_mode:
            try:
                _delete_vlan(connection, vr_name, vid)
            except (ConnectionError, FeVlansError) as exc:
                # Report it -- a silently skipped delete looks like success
                # while the VLAN is still on the device.
                skipped.append({"vlan_id": vid, "reason": to_text(exc)})
                continue

        deleted.append(vid)
        results.append({
            "vlan_id": vid,
            "before": before_output,
            "after": None,
            "changed": True,
            "differences": _compute_diff(before_output, None),
        })

    return results, deleted, skipped


def _handle_merge_replace(module, connection, config, state):
    """Handle merged/replaced/overridden states."""
    # Bulk GET all VLANs once for efficiency
    all_vlans = _get_all_vlans(connection)
    existing_map = {v["id"]: v for v in all_vlans if "id" in v}

    # Capture before snapshot (Sub-issue E fix)
    before_snapshot = _to_ansible_list(all_vlans)

    per_vlan_results = []
    any_changed = False
    deleted_vlans = []
    skipped_vlans = []

    # Overridden pre-pass: delete unlisted VLANs
    if state == STATE_OVERRIDDEN:
        prepass_results, deleted_vlans, skipped_vlans = (
            _handle_overridden_prepass(module, connection, config, all_vlans))
        per_vlan_results.extend(prepass_results)
        if any(r["changed"] for r in prepass_results):
            any_changed = True
        for skip in skipped_vlans:
            module.warn(
                "Overridden: VLAN %s could not be deleted and was skipped: %s"
                % (skip["vlan_id"], skip["reason"]))
        # A deleted VLAN must not then be treated as existing config.
        for vid in deleted_vlans:
            existing_map.pop(vid, None)

    # Process each VLAN in config
    for entry in config:
        if state == STATE_MERGED:
            result = _handle_single_vlan_merge(
                module, connection, entry, existing_map,
            )
        else:
            result = _handle_single_vlan_replace(
                module, connection, entry, existing_map, state,
            )
        per_vlan_results.append(result)
        if result["changed"]:
            any_changed = True

    output = {
        "changed": any_changed,
        "before": before_snapshot,
        "vlans": per_vlan_results,
    }
    if deleted_vlans:
        output["deleted_vlans"] = deleted_vlans
    if skipped_vlans:
        output["skipped_vlans"] = skipped_vlans
    if any_changed and not module.check_mode:
        after_vlans = _get_all_vlans(connection)
        output["after"] = _to_ansible_list(after_vlans)

    return output


def _handle_deleted(module, connection, config):
    """Handle state=deleted: remove specified VLANs or all user VLANs."""
    all_vlans = _get_all_vlans(connection)
    existing_map = {v["id"]: v for v in all_vlans if "id" in v}
    before_snapshot = _to_ansible_list(all_vlans)

    per_vlan_results = []
    any_changed = False

    if config:
        targets = config
    else:
        # Delete all user-created VLANs (skip system VLANs)
        targets = [
            {"vlan_id": vid, "vr_name": v.get("vrName", "GlobalRouter")}
            for vid, v in existing_map.items()
            if vid not in SYSTEM_VLANS
        ]

    for entry in targets:
        vlan_id = entry["vlan_id"]
        existing = existing_map.get(vlan_id)
        # The DELETE path is scoped by VRF, so it has to name the VRF the VLAN
        # actually lives in. vr_name carries an argspec default of
        # 'GlobalRouter', so a task that simply omits it cannot be told apart
        # from one that asked for GlobalRouter -- trusting it would send the
        # DELETE to the wrong path for any VLAN in another VRF. The device
        # record is authoritative; fall back to the entry only when the VLAN
        # is not on the device.
        vr_name = (existing or {}).get("vrName") or entry.get(
            "vr_name", "GlobalRouter")

        if existing is None:
            per_vlan_results.append({
                "vlan_id": vlan_id,
                "before": None,
                "after": None,
                "changed": False,
                "differences": {},
            })
            continue

        before_output = _to_ansible_output(existing)
        any_changed = True

        if not module.check_mode:
            _delete_vlan(connection, vr_name, vlan_id)

        per_vlan_results.append({
            "vlan_id": vlan_id,
            "before": before_output,
            "after": None,
            "changed": True,
            "differences": _compute_diff(before_output, None),
        })

    output = {
        "changed": any_changed,
        "before": before_snapshot,
        "vlans": per_vlan_results,
    }
    if any_changed and not module.check_mode:
        after_vlans = _get_all_vlans(connection)
        output["after"] = _to_ansible_list(after_vlans)

    return output


# -- Entry Point ---------------------------------------------------------------


def main():
    """Module entry point with state dispatch."""
    # No required_if here on purpose. The module accepts either the 'config'
    # list or the deprecated top-level parameters, and required_if cannot
    # express "one of these two forms"; the guard below does it instead.
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
    )

    state = module.params["state"]
    # Accepts the 'config' list or the deprecated top-level parameters.
    # required_if cannot express that, so the guard below does it instead.
    config = _entries_from_params(module)

    # Config validation guard -- merged/replaced/overridden require config
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN) and not config:
        module.fail_json(
            msg="'config' is required when state is '%s' (or supply the "
                "deprecated top-level VLAN parameters)" % state)

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == STATE_GATHERED:
            result = _handle_gathered(module, connection)
            module.exit_json(**result)
        elif state == STATE_DELETED:
            result = _handle_deleted(
                module, connection, config if config else None)
            module.exit_json(**result)
        else:
            # merged, replaced, or overridden
            result = _handle_merge_replace(module, connection, config, state)
            module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc), code=getattr(exc, "code", None))
    except FeVlansError as err:
        module.fail_json(**err.to_fail_kwargs())


if __name__ == "__main__":
    main()
