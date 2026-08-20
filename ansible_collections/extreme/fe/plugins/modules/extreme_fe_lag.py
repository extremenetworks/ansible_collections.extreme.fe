"""Ansible module to manage ExtremeNetworks Fabric Engine LAGs via HTTPAPI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

DOCUMENTATION = r"""
---
module: extreme_fe_lag
short_description: Manage LAGs on ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
    - "Create and delete Link Aggregation Groups (LAGs) on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI transport."
    - "Update Fabric Engine specific LAG attributes such as friendly names, load balancing algorithms, and Fabric Engine LACP keys."
    - "Add or remove member ports through the Fabric Engine LAG REST endpoints while propagating device errors back to Ansible."
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - "Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project."
    - "Fabric Engine does not support patching an existing LAG's aggregation mode; delete and recreate the LAG to modify C(mode)."
    - "LAGs are supplied through the C(config) list. The former top-level parameters (C(lag_id), C(name), C(member_ports), ...) still work as a single-entry config and emit a deprecation warning; the two forms cannot be mixed in one task."
    - "With C(config), C(overridden) is authoritative across the whole device: LAGs that the task does not list are deleted. LAGs it could not delete are reported in C(skipped_lags) and raised as warnings. The deprecated top-level form manages a single LAG and never deletes unlisted ones."
    - "C(replaced) and C(overridden) reset omitted attributes to the factory defaults of a bare MLT: C(name) back to C(MLT-<lag_id>), C(load_balance_algo) to C(CUSTOM), and C(flex_uni) to C(false)."
    - "C(mode) and C(lacp_key) are never reset. Fabric Engine cannot patch the aggregation mode, and C('0') — the key an MLT created without one carries — is a value the device computes but will not accept as input. To clear either, delete and recreate the LAG."
    - "The LACP key space is partitioned by the device: C(0) means no key configured, C(1)-C(512) are the configurable keys (matching the CLI C(lacp key <1-512|defVal>)), and values of C(1024) and above are assigned internally per port (C(1024) bitwise-OR the port ifIndex) so that unaggregated ports can never match one another. The module rejects values outside C(1)-C(512) before contacting the device. C('0') is the one exception: it is accepted as a no-op when the LAG has no key configured yet, so C(gathered) output can be fed straight back into a task, and rejected with an explanation when the LAG has a real key."
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired LAG operation.
            - "C(merged) creates the target LAG when missing and merges the supplied attributes and member ports."
            - "C(replaced) enforces the supplied member list and attributes for the target LAG, removing unstated members and resetting omitted attributes to their factory defaults."
            - "C(overridden) is like C(replaced) for each listed LAG, and additionally deletes any LAG on the device that C(config) does not list."
            - "C(deleted) removes the specified LAG entirely or prunes the provided members when C(member_ports) or C(remove_member_ports) is supplied."
            - "C(gathered) returns the current LAG configuration without applying changes."
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    config:
        description:
            - "List of LAGs to manage. Each entry describes one LAG and its desired attributes."
            - "Required for every state except C(gathered), unless the deprecated top-level parameters are used instead."
        type: list
        elements: dict
        suboptions:
            lag_id:
                description:
                    - "LAG identifier (Fabric Engine MLT identifier)."
                    - "Accepts string or integer values in the Fabric Engine supported range (1-512)."
                type: raw
            name:
                description:
                    - "Friendly Fabric Engine name assigned to the LAG."
                type: str
            mode:
                description:
                    - "Fabric Engine aggregation mode to use when creating the LAG."
                type: str
                choices: [STATIC, LACP, VLACP]
            lacp_key:
                description:
                    - "Fabric Engine aggregation key used when the LAG operates in LACP or VLACP mode."
                    - "Valid values are C(1)-C(512). C(0) is the key the device reports for a LAG with none configured and cannot be written back."
                    - "Not reset by C(replaced) or C(overridden)."
                type: str
            load_balance_algo:
                description:
                    - "Load balancing algorithm applied to the LAG."
                    - "Fabric Engine always reports and applies C(CUSTOM). Supplying another value does not change the device mode, so the task continues to report a change."
                type: str
                choices: [L2, L3, L3_L4, CUSTOM, PORT]
            flex_uni:
                description:
                    - "Enable or disable Flex-UNI (switched UNI) on the Fabric Engine LAG."
                    - "Must be true before the LAG can be used in a Switched UNI (SUNI) ISID endpoint."
                    - "Must be false for the LAG to be usable as a Transparent UNI (TUNI) member."
                type: bool
            member_ports:
                description:
                    - "List of member ports that participate in the LAG."
                type: list
                elements: str
            add_member_ports:
                description:
                    - "Incremental list of member ports to add to the LAG when C(state=merged)."
                type: list
                elements: str
            remove_member_ports:
                description:
                    - "Incremental list of member ports to remove from the LAG when C(state=merged) or C(state=deleted)."
                type: list
                elements: str
            purge_member_ports:
                description:
                    - "Remove member ports that are not present in C(member_ports) (only evaluated when C(state=merged))."
                type: bool
                default: false
    lag_id:
        description:
            - "LAG identifier (Fabric Engine MLT identifier)."
            - "Accepts string or integer values in the Fabric Engine supported range (1-512)."
            - "Deprecated: supply LAGs through C(config) instead. The top-level form manages a single LAG."
        type: raw
    name:
        description:
            - "Friendly Fabric Engine name assigned to the LAG."
        type: str
    mode:
        description:
            - "Fabric Engine aggregation mode to use when creating the LAG."
        type: str
        choices: [STATIC, LACP, VLACP]
    lacp_key:
        description:
            - "Fabric Engine aggregation key used when the LAG operates in LACP or VLACP mode."
            - "Valid values are C(1)-C(512). C(0) is what the device reports for a LAG with no key configured; supplying it is accepted only when the LAG already has no key, and is rejected with a clear message otherwise because the device provides no way to write it back."
            - "Not reset by C(replaced) or C(overridden), so an omitted C(lacp_key) leaves the current value in place."
        type: str
    load_balance_algo:
        description:
            - "Load balancing algorithm applied to the LAG."
            - "Fabric Engine always reports and applies C(CUSTOM); other values are accepted by the API and ignored by the device."
        type: str
        choices: [L2, L3, L3_L4, CUSTOM, PORT]
    flex_uni:
        description:
            - "Enable or disable Flex-UNI (switched UNI) on the Fabric Engine LAG."
            - "Must be true before the LAG can be used in a Switched UNI (SUNI) ISID endpoint; the device otherwise rejects the endpoint with C(flex-uni must be enabled before creating endpoint)."
            - "Must be false for the LAG to be usable as a Transparent UNI (TUNI) member."
            - "With C(state=merged) omitting this leaves the current device value untouched; with C(state=replaced) or C(state=overridden) an omitted value is reset to the factory default (false)."
        type: bool
    member_ports:
        description:
            - "List of member ports that participate in the LAG."
            - "With C(state=merged) missing members are added while existing members remain unless C(purge_member_ports) is true."
            - "With C(state=replaced) or C(state=overridden) the provided ports become authoritative; unspecified members are removed and an empty list clears all members."
            - "With C(state=deleted) the provided ports are removed from the LAG without deleting the LAG itself."
        type: list
        elements: str
    add_member_ports:
        description:
            - "Incremental list of member ports to add to the LAG when C(state=merged)."
        type: list
        elements: str
    remove_member_ports:
        description:
            - "Incremental list of member ports to remove from the LAG when C(state=merged) or C(state=deleted)."
        type: list
        elements: str
    purge_member_ports:
        description:
            - "Remove member ports that are not present in C(member_ports) (only evaluated when C(state=merged))."
            - "Requires C(member_ports) when set to true."
        type: bool
        default: false
    gather_filter:
        description:
            - "Restrict gathered LAG results to these identifiers."
        type: list
        elements: str
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc.
#
# LAGs are supplied through the 'config' list, which manages several LAGs in
# one task. The former top-level parameters (lag_id, name, member_ports, ...)
# still work as a single-entry config but are deprecated and emit a warning;
# the two forms cannot be mixed in one task.

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
## Create LAGs (if not already existing)
# mlt 10 name "Uplink-LAG-10" enable
# mlt 11 name "MLT-11" enable
# mlt 20 name "MLT-20" enable
#
## Ensure ARP Inspection is consistently configured on LAG member ports
## (All ports in a LAG must have the same ARP Inspection setting)
# interface gigabitEthernet 1/5-1/9
#   no ip arp-inspection trust
# exit
#
## Verify Configuration
# show mlt
# show ip arp-inspection interfaces

# -------------------------------------------------------------------------
# Task 1: Create or update several LAGs in one task
# Description:
#   - 'merged' creates each LAG when missing and merges the supplied
#     attributes. Member ports are additive: existing members are kept and
#     add_member_ports contributes extra ports.
# -------------------------------------------------------------------------
# - name: "Task 1: Merge configuration for Fabric Engine LAGs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Create or update two LAGs in a single task
  extreme.fe.extreme_fe_lag:
    state: merged
    config:
      - lag_id: 10
        name: Uplink-LAG-10
        mode: LACP
        lacp_key: '10'
        member_ports:
          - '1:5'
          - '1:6'
        add_member_ports:
          - '1:7'
      - lag_id: 11
        name: Uplink-LAG-11
        member_ports:
          - '1:8'

# -------------------------------------------------------------------------
# Task 2: Merge with purge to enforce membership
# Description:
#   - purge_member_ports makes member_ports authoritative for that LAG even
#     in 'merged' state, removing ports the entry does not list.
# -------------------------------------------------------------------------
# - name: "Task 2: Merge LAG 11 and purge unspecified members"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce membership for LAG 11 while removing strays
  extreme.fe.extreme_fe_lag:
    state: merged
    config:
      - lag_id: 11
        member_ports:
          - '1:8'
          - '1:9'
        purge_member_ports: true

# -------------------------------------------------------------------------
# Task 3: Replace a LAG
# Description:
#   - 'replaced' makes the supplied members authoritative and resets omitted
#     attributes to their factory defaults: name back to MLT-<lag_id>,
#     load_balance_algo to CUSTOM and flex_uni to false. mode and lacp_key
#     are never reset - see the module notes.
#   - Only the LAGs listed are touched; LAGs absent from config are left
#     alone.
# -------------------------------------------------------------------------
# - name: "Task 3: Replace membership for Fabric Engine LAG 10"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce the desired member set and reset omitted attributes
  extreme.fe.extreme_fe_lag:
    state: replaced
    config:
      - lag_id: 10
        member_ports:
          - '1:5'
          - '1:6'

# -------------------------------------------------------------------------
# Task 4: Clear every member of a LAG
# Description:
#   - An empty member_ports list under 'replaced' removes all members while
#     keeping the LAG itself, and leaves other LAGs untouched.
# -------------------------------------------------------------------------
# - name: "Task 4: Clear the members of Fabric Engine LAG 20"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Remove all members while keeping the LAG definition
  extreme.fe.extreme_fe_lag:
    state: replaced
    config:
      - lag_id: 20
        member_ports: []

# -------------------------------------------------------------------------
# Task 5: Make the device match an exact set of LAGs
# Description:
#   - 'overridden' is authoritative across the WHOLE device: each listed LAG
#     is treated as for 'replaced', and any LAG that config does not list is
#     DELETED. LAGs it could not delete are reported in skipped_lags.
#   - Use it only when the task describes every LAG the device should have.
#     To reset a single LAG without touching the others, use 'replaced'.
# -------------------------------------------------------------------------
# - name: "Task 5: Make LAGs 10 and 11 the only LAGs on the device"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce the complete LAG inventory
  extreme.fe.extreme_fe_lag:
    state: overridden
    config:
      - lag_id: 10
        member_ports:
          - '1:5'
          - '1:6'
      - lag_id: 11
        member_ports:
          - '1:8'

# -------------------------------------------------------------------------
# Task 6: Enable Flex-UNI on a LAG
# Description:
#   - Flex-UNI must be enabled on the LAG before it can be referenced by a
#     Switched UNI (SUNI) ISID endpoint in extreme_fe_fabric_l2. Leave it
#     disabled on any LAG intended for Transparent UNI (TUNI) membership.
# -------------------------------------------------------------------------
# - name: "Task 6: Enable Flex-UNI on Fabric Engine LAG 50"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enable Flex-UNI so LAG 50 can be used as a switched UNI
  extreme.fe.extreme_fe_lag:
    state: merged
    config:
      - lag_id: 50
        flex_uni: true

# -------------------------------------------------------------------------
# Task 7: Delete LAGs
# Description:
#   - Without member_ports the whole LAG is removed. With member_ports only
#     those members are pruned and the LAG itself is kept.
# -------------------------------------------------------------------------
# - name: "Task 7: Delete Fabric Engine LAGs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Delete LAG 11 entirely and prune one member from LAG 10
  extreme.fe.extreme_fe_lag:
    state: deleted
    config:
      - lag_id: 11
      - lag_id: 10
        member_ports:
          - '1:7'

# -------------------------------------------------------------------------
# Task 8: Gather the current LAG configuration
# -------------------------------------------------------------------------
# - name: "Task 8: Gather Fabric Engine LAG configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather every LAG on the device
  extreme.fe.extreme_fe_lag:
    state: gathered

- name: Gather only the LAGs of interest
  extreme.fe.extreme_fe_lag:
    state: gathered
    gather_filter:
      - '10'
      - '11'
"""

RETURN = r"""
---
changed:
    description: "Indicates whether any changes were made."
    returned: always
    type: bool
lag:
    description: "Resulting LAG configuration returned by the Fabric Engine REST API."
    returned: when state in [merged, replaced, overridden, deleted] and the LAG exists after execution
    type: dict
lag_removed:
    description: "LAG configuration that was removed when the entire LAG was deleted."
    returned: when state == deleted and the target LAG was removed
    type: dict
member_additions:
    description: "Member ports that were added during execution."
    returned: when state in [merged, replaced, overridden] and member ports were added
    type: list
    elements: str
member_removals:
    description: "Member ports that were removed during execution."
    returned: when state in [merged, replaced, overridden, deleted] and member ports were removed
    type: list
    elements: str
lags:
    description:
        - "When C(state=gathered), the list of LAG configuration dictionaries retrieved from the device."
        - "Otherwise one entry per LAG in C(config), each carrying C(lag_id), C(changed), C(before) and C(after)."
    returned: always
    type: list
    elements: dict

before:
  description: LAG configuration on the device before the task ran.
  returned: when state is not gathered
  type: list
  elements: dict
after:
  description: LAG configuration on the device after the task ran.
  returned: when state is not gathered
  type: list
  elements: dict
gathered:
  description: Current LAG configuration entries returned by the device.
  returned: when state == gathered
  type: list
  elements: dict
deleted_lags:
  description: LAG identifiers deleted by overridden because config did not list them.
  returned: when state == overridden and unlisted LAGs were removed
  type: list
  elements: str
skipped_lags:
  description: LAGs overridden could not delete, with the device reason.
  returned: when state == overridden and a delete failed
  type: list
  elements: dict
"""

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"


# ── Factory defaults ──────────────────────────────────────────────────────────
#
# Used by replaced/overridden to reset attributes the user omitted.
#
# Verified on a 7520-48XT-6C running Fabric Engine 9.3 by creating two bare
# MLTs ("mlt 60", "mlt 70 enable") and reading them back with
# GET /v0/configuration/lag/<id>, which returned for both:
#     {"flexUni": false, "lacpKey": "0", "loadBalanceAlgo": "CUSTOM",
#      "memberPorts": [], "mode": "STATIC", "name": "MLT-<id>"}
#
# Two writable fields are deliberately NOT in this dict — see the notes below.
LAG_FULL_DEFAULTS: dict[str, Any] = {
    "flexUni": False,             # OpenAPI default: false; device: FLEX-UNI disable
    # lacpKey is NOT force-reset. A bare MLT *reports* key "0" (LACP admin
    # disabled), but the device rejects a PATCH that *writes* "0" with
    # HTTP 500 -- confirmed on hardware, while writing "10" to the same LAG
    # succeeds. It is a read-only sentinel, like nativeVlan 0 in
    # extreme_fe_interfaces. None means "leave it alone".
    "lacpKey": None,
    # OpenAPI LagLoadBalanceAlgo: "Fabric Engine will always
    # return/set CUSTOM" -- confirmed on hardware, where a request for L3 is
    # accepted and ignored. CUSTOM is therefore both the factory default and
    # the only value that ever takes effect on this platform.
    "loadBalanceAlgo": "CUSTOM",
    "memberPorts": [],            # Device: a new MLT has no member ports
}

# 'name' is NOT a constant — a bare MLT is named after its own ID ("MLT-60"),
# so the default has to be computed per LAG instead of read from the dict.
#
# 'mode' is intentionally absent. Fabric Engine cannot PATCH the aggregation
# mode (see _build_update_payload), so replaced/overridden have no way to reset
# it to STATIC. Listing it here would promise a reset the API cannot perform.


# Aggregation key semantics, taken from the Fabric Engine source:
#   nd_protocols/lacp/include/lacp_extern.h
#       LACP_ANY_AGGRETABLE_KEY      0                 -- an MLT created
#                                                         without an explicit key
#       LACP_DEFAULT_INDI_KEY(port)  (0x0400 | port)   -- a port that is not
#                                                         aggregated, i.e.
#                                                         1024 | ifIndex
#   nd_protocols/lacp/include/lacp.h
#       LACP_NOT_USABLE_KEY          1024              -- parked on an MLT while
#                                                         LACP is disabled so
#                                                         freed ports cannot
#                                                         re-aggregate
# The key space is partitioned: 0 means "unset / free to aggregate",
# 1-512 are the keys the CLI accepts ("lacp key <1-512|defVal>"), and
# anything >= 1024 is assigned internally per port. So 0 is the factory
# default an MLT REPORTS but is not a value the API will accept back --
# writing it returns HTTP 500.
LACP_KEY_FACTORY_DEFAULT = "0"
LACP_KEY_MIN = 1
LACP_KEY_MAX = 512


def _is_factory_lacp_key(value: str | None) -> bool:
    """True when the value is the key an MLT carries with none configured."""
    return value is not None and str(value).strip() == LACP_KEY_FACTORY_DEFAULT


def _validate_lacp_key(
    lag_id: str, lacp_key: str | None, existing: dict[str, Any] | None,
) -> None:
    """Reject key values the device cannot be asked to store.

    Catches two cases that would otherwise surface as an opaque HTTP 500:
    a key outside the configurable 1-512 range, and a request to set the
    factory default 0 on a LAG that currently has a real key -- the device
    computes 0 itself but provides no way to write it back.
    """
    if lacp_key is None:
        return
    text = str(lacp_key).strip()

    if text == LACP_KEY_FACTORY_DEFAULT:
        current = (existing or {}).get("lacpKey")
        if existing is not None and not _is_factory_lacp_key(current):
            raise FeLagError(
                "LAG %s already has LACP key %s. '0' is the value the device "
                "reports for a LAG with no key configured and cannot be "
                "written back; delete and recreate the LAG to clear the key."
                % (lag_id, current),
                details={"lag_id": lag_id, "current_lacp_key": current},
            )
        return

    try:
        value = int(text)
    except (TypeError, ValueError):
        raise FeLagError(
            "'lacp_key' must be a numeric string; got %r" % (lacp_key,),
            details={"lag_id": lag_id},
        )
    if not LACP_KEY_MIN <= value <= LACP_KEY_MAX:
        raise FeLagError(
            "'lacp_key' %s is outside the configurable range %d-%d. Values of "
            "0 and >= 1024 are assigned by the device and cannot be set."
            % (text, LACP_KEY_MIN, LACP_KEY_MAX),
            details={"lag_id": lag_id, "requested_lacp_key": text},
        )


def _default_lag_name(lag_id: str) -> str:
    """Factory default name for a LAG: the device names a bare MLT 'MLT-<id>'."""
    return f"MLT-{lag_id}"


# Per-LAG attributes. Shared between the 'config' list entries and the
# deprecated flat form, so the two can never drift apart.
_LAG_ENTRY_SPEC: dict[str, Any] = {
    "lag_id": {"type": "raw"},
    "name": {"type": "str"},
    "mode": {"type": "str", "choices": ["STATIC", "LACP", "VLACP"]},
    "lacp_key": {"type": "str"},
    "load_balance_algo": {
        "type": "str",
        "choices": ["L2", "L3", "L3_L4", "CUSTOM", "PORT"],
    },
    "flex_uni": {"type": "bool"},
    "member_ports": {"type": "list", "elements": "str"},
    "add_member_ports": {"type": "list", "elements": "str"},
    "remove_member_ports": {"type": "list", "elements": "str"},
    "purge_member_ports": {"type": "bool", "default": False},
}

# The flat parameters kept for backward compatibility. Supplying any of them
# builds a single-entry config list; see _entries_from_params().
_FLAT_PARAMS = tuple(_LAG_ENTRY_SPEC)

ARGUMENT_SPEC: dict[str, Any] = {
    "state": {
        "type": "str",
        "choices": [STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED, STATE_GATHERED],
        "default": STATE_MERGED,
    },
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {k: dict(v) for k, v in _LAG_ENTRY_SPEC.items()},
    },
    "gather_filter": {"type": "list", "elements": "str"},
}
# Flat form: same options at the top level. 'purge_member_ports' keeps its
# default here so existing playbooks behave exactly as before.
for _name, _spec in _LAG_ENTRY_SPEC.items():
    ARGUMENT_SPEC[_name] = dict(_spec)


class FeLagError(Exception):
    """Base exception for Fabric Engine LAG module errors."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> dict[str, Any]:
        data: dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _is_not_found_response(payload: Any | None) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    if code == 404:
        return True
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if isinstance(message, str) and "not found" in message.lower():
        return True
    return False


def _normalize_lag_id(value: Any) -> str:
    if value is None:
        raise FeLagError("Parameter 'lag_id' must be provided when state requires a LAG identifier")
    if isinstance(value, bool):
        raise FeLagError("Boolean values are not valid for 'lag_id'")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            raise FeLagError("Parameter 'lag_id' must not be empty")
        return trimmed
    return str(value)


def _flat_form_used(module: AnsibleModule) -> bool:
    """True when the caller supplied any top-level per-LAG parameter.

    'purge_member_ports' carries a default so it is never None; it only counts
    when actually switched on.
    """
    for name in _FLAT_PARAMS:
        if name == "purge_member_ports":
            if module.params.get(name):
                return True
        elif module.params.get(name) is not None:
            return True
    return False


def _entries_from_params(module: AnsibleModule) -> list[dict[str, Any]]:
    """Normalise both supported input forms into a list of LAG entries.

    The flat form is the pre-1.2.1 interface; it is accepted as a single-entry
    config list so existing playbooks keep working, and warned about once.
    """
    config = module.params.get("config")
    flat_used = _flat_form_used(module)

    if config and flat_used:
        raise FeLagError(
            "Use either the 'config' list or the top-level LAG parameters, not both. "
            "The top-level form is deprecated; move its values into 'config'."
        )
    if config:
        return [dict(entry) for entry in config]
    if flat_used:
        module.deprecate(
            "Supplying LAG attributes at the top level is deprecated; use the "
            "'config' list instead, for example "
            "config: [{lag_id: 10, name: Uplink}]. The top-level form manages "
            "a single LAG and cannot express 'overridden' across several LAGs.",
            version="2.0.0",
            collection_name="extreme.fe",
        )
        return [{name: module.params.get(name) for name in _FLAT_PARAMS}]
    return []


def _unique_port_list(values: list[str] | None, *, param_name: str) -> list[str]:
    if not values:
        return []
    unique: list[str] = []
    seen = set()
    for raw in values:
        if not isinstance(raw, str):
            raise FeLagError(
                f"All entries in '{param_name}' must be strings",
                details={"invalid_value": raw},
            )
        port = raw.strip()
        if not port:
            raise FeLagError(f"Port names in '{param_name}' cannot be empty")
        if port not in seen:
            seen.add(port)
            unique.append(port)
    return unique


def _extract_member_ports(lag: dict[str, Any] | None) -> list[str]:
    if not isinstance(lag, dict):
        return []
    raw = lag.get("memberPorts")
    if not isinstance(raw, list):
        return []
    members: list[str] = []
    for item in raw:
        if isinstance(item, str):
            members.append(item)
        elif item is not None:
            members.append(str(item))
    return members


def gather_lags(module: AnsibleModule, connection: Connection) -> list[dict[str, Any]]:
    gather_filter = module.params.get("gather_filter")
    if gather_filter:
        results: list[dict[str, Any]] = []
        for entry in gather_filter:
            lag_id = _normalize_lag_id(entry)
            config = get_lag_config(connection, lag_id)
            if config is not None:
                results.append(config)
        return results
    data = connection.send_request(None, path="/v0/configuration/lag", method="GET")
    if data is None or _is_not_found_response(data):
        return []
    if isinstance(data, list):
        result: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                result.append(item)
        return result
    raise FeLagError(
        "Unexpected response when retrieving LAG configuration summary",
        details={"response": data},
    )


def get_lag_config(connection: Connection, lag_id: str) -> dict[str, Any] | None:
    try:
        data = connection.send_request(
            None,
            path=f"/v0/configuration/lag/{lag_id}",
            method="GET",
        )
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        return data
    raise FeLagError(
        "Unexpected response when retrieving LAG configuration",
        details={"response": data},
    )


def create_lag(connection: Connection, payload: dict[str, Any]) -> None:
    connection.send_request(payload, path="/v0/configuration/lag", method="POST")


def update_lag(connection: Connection, lag_id: str, payload: dict[str, Any]) -> None:
    if payload:
        connection.send_request(payload, path=f"/v0/configuration/lag/{lag_id}", method="PATCH")


def apply_lag_attributes(
    connection: Connection, lag_id: str, payload: dict[str, Any],
) -> list[str]:
    """Apply attribute changes one field per PATCH.

    Fabric Engine rejects some individual values (writing lacpKey "0" returns
    HTTP 500 while "10" succeeds). A combined PATCH surfaced only a generic
    500 with no indication of which field the device refused, and could leave
    part of the payload applied. One request per field makes a rejection
    attributable and lets the caller report how far the change got.
    """
    applied: list[str] = []
    for field in sorted(payload):
        try:
            update_lag(connection, lag_id, {field: payload[field]})
        except ConnectionError as exc:
            raise FeLagError(
                "Failed to set '%s' on LAG %s: %s" % (field, lag_id, to_text(exc)),
                details={
                    "lag_id": lag_id,
                    "failed_field": field,
                    "applied_fields": applied,
                    "attempted": payload,
                },
            )
        applied.append(field)
    return applied


def delete_lag(connection: Connection, lag_id: str) -> None:
    connection.send_request(None, path=f"/v0/configuration/lag/{lag_id}", method="DELETE")


def add_member_ports(connection: Connection, lag_id: str, ports: list[str]) -> None:
    if ports:
        connection.send_request(ports, path=f"/v0/configuration/lag/{lag_id}/memberPorts", method="POST")


def remove_member_ports(connection: Connection, lag_id: str, ports: list[str]) -> None:
    for port in ports:
        connection.send_request(
            None,
            path=f"/v0/configuration/lag/{lag_id}/memberPorts/{port}",
            method="DELETE",
        )


# ── Payload builders ──────────────────────────────────────────────────────────


def _build_create_payload(
    *,
    lag_id: str,
    name: str | None,
    mode: str | None,
    lacp_key: str | None,
    load_balance_algo: str | None,
    flex_uni: bool | None,
) -> dict[str, Any]:
    """Build the POST body used to create a LAG.

    Only attributes the user actually supplied are included, so the device
    applies its own factory defaults to everything else.
    """
    payload: dict[str, Any] = {"lagId": lag_id}
    if name is not None:
        payload["name"] = name
    if mode is not None:
        payload["mode"] = mode
    # 0 is the value the device assigns itself; sending it is rejected.
    if lacp_key is not None and not _is_factory_lacp_key(lacp_key):
        payload["lacpKey"] = lacp_key
    if load_balance_algo is not None:
        payload["loadBalanceAlgo"] = load_balance_algo
    # Flex-UNI (switched UNI) — REST field flexUni, device default false
    if flex_uni is not None:
        payload["flexUni"] = flex_uni
    return payload


def _build_update_payload(
    *,
    existing: dict[str, Any],
    lag_id: str,
    name: str | None,
    mode: str | None,
    lacp_key: str | None,
    load_balance_algo: str | None,
    flex_uni: bool | None,
    reset_omitted: bool = False,
) -> dict[str, Any]:
    """Build the PATCH body for an existing LAG.

    Each attribute is included only when supplied AND different from the
    current device value, which keeps re-runs idempotent (changed=false).

    When *reset_omitted* is true (replaced/overridden), attributes the user
    left out are first filled from LAG_FULL_DEFAULTS so the supplied config
    becomes authoritative for the whole LAG. In merged state omitted
    attributes stay untouched.
    """
    if reset_omitted:
        if name is None:
            name = _default_lag_name(lag_id)
        if lacp_key is None:
            lacp_key = LAG_FULL_DEFAULTS["lacpKey"]
        if load_balance_algo is None:
            load_balance_algo = LAG_FULL_DEFAULTS["loadBalanceAlgo"]
        if flex_uni is None:
            flex_uni = LAG_FULL_DEFAULTS["flexUni"]

    update_payload: dict[str, Any] = {}
    if name is not None and name != existing.get("name"):
        update_payload["name"] = name
    if (lacp_key is not None and not _is_factory_lacp_key(lacp_key)
            and lacp_key != existing.get("lacpKey")):
        update_payload["lacpKey"] = lacp_key
    if load_balance_algo is not None and load_balance_algo != existing.get("loadBalanceAlgo"):
        update_payload["loadBalanceAlgo"] = load_balance_algo
    # Flex-UNI (switched UNI) — compare against the device default (false)
    # so an absent flexUni field is treated as disabled rather than "unknown".
    if flex_uni is not None and flex_uni != bool(existing.get("flexUni", False)):
        update_payload["flexUni"] = flex_uni
    # Fabric Engine cannot PATCH the aggregation mode — surface a clear error
    # instead of silently ignoring the request.
    if mode is not None and mode != existing.get("mode"):
        raise FeLagError(
            "Changing LAG mode on Fabric Engine is not supported via PATCH; delete and recreate the LAG to modify the mode.",
            details={"current_mode": existing.get("mode"), "requested_mode": mode},
        )
    return update_payload


def _process_entry(
    module: AnsibleModule, connection: Connection, entry: dict[str, Any], state: str,
) -> dict[str, Any]:
    """Apply one LAG entry. Returns a per-LAG result including before/after."""
    lag_id = _normalize_lag_id(entry.get("lag_id"))
    name = entry.get("name")
    mode = entry.get("mode")
    lacp_key = entry.get("lacp_key")
    load_balance_algo = entry.get("load_balance_algo")
    # Flex-UNI (switched UNI) toggle — required before the LAG can be bound
    # to a SUNI ISID endpoint, and must stay off for TUNI membership.
    flex_uni = entry.get("flex_uni")
    desired_members_param = entry.get("member_ports")
    add_members_param = entry.get("add_member_ports")
    remove_members_param = entry.get("remove_member_ports")
    purge_members_param = entry.get("purge_member_ports")

    desired_members: list[str] | None
    add_members: list[str] = []
    remove_members: list[str] = []
    purge_members = False

    if state == STATE_MERGED:
        desired_members = _unique_port_list(desired_members_param, param_name="member_ports") if desired_members_param is not None else None
        add_members = _unique_port_list(add_members_param, param_name="add_member_ports")
        remove_members = _unique_port_list(remove_members_param, param_name="remove_member_ports")
        purge_members = bool(purge_members_param)
        if purge_members and desired_members is None:
            raise FeLagError("'purge_member_ports' requires 'member_ports' when state is 'merged'")
    elif state == STATE_REPLACED:
        if add_members_param:
            raise FeLagError("'add_member_ports' is not supported when state is 'replaced'")
        if remove_members_param:
            raise FeLagError("'remove_member_ports' is not supported when state is 'replaced'")
        if desired_members_param is None:
            raise FeLagError("'member_ports' is required when state is 'replaced'")
        desired_members = _unique_port_list(desired_members_param, param_name="member_ports")
        purge_members = True
    elif state == STATE_OVERRIDDEN:
        if add_members_param:
            raise FeLagError("'add_member_ports' is not supported when state is 'overridden'")
        if remove_members_param:
            raise FeLagError("'remove_member_ports' is not supported when state is 'overridden'")
        if desired_members_param is None:
            desired_members = []
        else:
            desired_members = _unique_port_list(desired_members_param, param_name="member_ports")
        purge_members = True
    else:
        raise FeLagError(f"Unsupported state '{state}' for configuration workflow")

    existing = get_lag_config(connection, lag_id)
    _validate_lacp_key(lag_id, lacp_key, existing)
    before = deepcopy(existing)
    changed = False
    refreshed_required = False
    member_additions: list[str] = []
    member_removals: list[str] = []

    current: dict[str, Any]
    if existing is None:
        changed = True
        initial_members: list[str] = []
        if desired_members is not None:
            initial_members.extend(desired_members)
        elif add_members:
            initial_members.extend(add_members)
        payload: dict[str, Any] = _build_create_payload(
            lag_id=lag_id,
            name=name,
            mode=mode,
            lacp_key=lacp_key,
            load_balance_algo=load_balance_algo,
            flex_uni=flex_uni,
        )
        if initial_members:
            payload["memberPorts"] = initial_members
            member_additions.extend(initial_members)
        if module.check_mode:
            current = payload.copy()
            current.setdefault("memberPorts", list(initial_members))
        else:
            create_lag(connection, payload)
            refreshed_required = True
            current = get_lag_config(connection, lag_id) or payload
            # The device silently drops some attributes on POST (observed:
            # loadBalanceAlgo and flexUni) while accepting them on PATCH, so
            # a create would otherwise need a second run to converge.
            # Re-apply whatever did not land. 'mode' is passed as None: it is
            # create-only and cannot be patched, so a mismatch must not raise.
            followup = _build_update_payload(
                existing=current,
                lag_id=lag_id,
                name=name,
                mode=None,
                lacp_key=lacp_key,
                load_balance_algo=load_balance_algo,
                flex_uni=flex_uni,
                reset_omitted=False,
            )
            if followup:
                apply_lag_attributes(connection, lag_id, followup)
                current = get_lag_config(connection, lag_id) or current
    else:
        current = existing.copy()
        # replaced/overridden are authoritative: attributes the user omitted
        # are reset to their factory defaults. merged leaves them alone.
        update_payload: dict[str, Any] = _build_update_payload(
            existing=existing,
            lag_id=lag_id,
            name=name,
            mode=mode,
            lacp_key=lacp_key,
            load_balance_algo=load_balance_algo,
            flex_uni=flex_uni,
            reset_omitted=state in (STATE_REPLACED, STATE_OVERRIDDEN),
        )
        if update_payload:
            changed = True
            if module.check_mode:
                current.update(update_payload)
            else:
                apply_lag_attributes(connection, lag_id, update_payload)
                refreshed_required = True
                refreshed = get_lag_config(connection, lag_id)
                if refreshed is not None:
                    current = refreshed
                else:
                    current.update(update_payload)

    current_members = _extract_member_ports(current)
    current_member_set = set(current_members)

    ports_to_add: list[str] = []
    if desired_members is not None:
        for port in desired_members:
            if port not in current_member_set:
                ports_to_add.append(port)
                current_member_set.add(port)
    for port in add_members:
        if port not in current_member_set:
            ports_to_add.append(port)
            current_member_set.add(port)

    ports_to_remove: list[str] = []
    if purge_members and desired_members is not None:
        desired_set = set(desired_members)
        for port in current_members:
            if port not in desired_set and port not in ports_to_remove:
                ports_to_remove.append(port)
    for port in remove_members:
        if port in current_members and port not in ports_to_remove:
            ports_to_remove.append(port)

    if ports_to_add or ports_to_remove:
        changed = True

    if ports_to_add:
        member_additions.extend(ports_to_add)
    if ports_to_remove:
        member_removals.extend(ports_to_remove)

    if module.check_mode:
        simulated_members = current_members.copy()
        for port in ports_to_add:
            if port not in simulated_members:
                simulated_members.append(port)
        for port in ports_to_remove:
            if port in simulated_members:
                simulated_members.remove(port)
        current["memberPorts"] = simulated_members
        result: dict[str, Any] = {
            "lag_id": lag_id, "changed": changed, "lag": current,
            "before": before, "after": current if changed else before,
        }
        if member_additions:
            result["member_additions"] = _unique_port_list(member_additions, param_name="member_additions")
        if member_removals:
            result["member_removals"] = _unique_port_list(member_removals, param_name="member_removals")
        return result

    if ports_to_add:
        add_member_ports(connection, lag_id, ports_to_add)
        refreshed_required = True
    if ports_to_remove:
        remove_member_ports(connection, lag_id, ports_to_remove)
        refreshed_required = True

    if refreshed_required:
        final_lag = get_lag_config(connection, lag_id)
    else:
        final_lag = get_lag_config(connection, lag_id) if changed else current

    result: dict[str, Any] = {
        "lag_id": lag_id, "changed": changed, "lag": final_lag or current,
        "before": before, "after": final_lag or current,
    }
    if member_additions:
        result["member_additions"] = _unique_port_list(member_additions, param_name="member_additions")
    if member_removals:
        result["member_removals"] = _unique_port_list(member_removals, param_name="member_removals")
    return result


def _process_entry_deleted(
    module: AnsibleModule, connection: Connection, entry: dict[str, Any],
) -> dict[str, Any]:
    """Delete one LAG, or prune the listed members from it."""
    lag_id = _normalize_lag_id(entry.get("lag_id"))
    add_members_param = entry.get("add_member_ports")
    if add_members_param:
        raise FeLagError("'add_member_ports' is not supported when state is 'deleted'")

    members_to_remove: list[str] = []
    member_ports_param = entry.get("member_ports")
    remove_members_param = entry.get("remove_member_ports")
    if member_ports_param is not None:
        members_to_remove.extend(_unique_port_list(member_ports_param, param_name="member_ports"))
    if remove_members_param:
        members_to_remove.extend(_unique_port_list(remove_members_param, param_name="remove_member_ports"))
    if members_to_remove:
        members_to_remove = _unique_port_list(members_to_remove, param_name="member_removals")

    existing = get_lag_config(connection, lag_id)
    before = deepcopy(existing)
    if existing is None:
        return {"lag_id": lag_id, "changed": False, "lag": None,
                "before": None, "after": None}

    if not members_to_remove:
        if module.check_mode:
            result: dict[str, Any] = {
                "lag_id": lag_id,
                "changed": True,
                "lag": None,
                "lag_removed": existing,
                "member_removals": _extract_member_ports(existing),
                "before": before,
                "after": None,
            }
            return result
        delete_lag(connection, lag_id)
        return {
            "lag_id": lag_id,
            "changed": True,
            "lag": None,
            "lag_removed": existing,
            "member_removals": _extract_member_ports(existing),
            "before": before,
            "after": None,
        }

    current_members = _extract_member_ports(existing)
    current_member_set = set(current_members)
    ports_to_remove = [port for port in members_to_remove if port in current_member_set]
    if not ports_to_remove:
        return {"lag_id": lag_id, "changed": False, "lag": existing,
                "before": before, "after": before}

    if module.check_mode:
        simulated_members = [port for port in current_members if port not in ports_to_remove]
        simulated = existing.copy()
        simulated["memberPorts"] = simulated_members
        return {
            "lag_id": lag_id,
            "changed": True,
            "lag": simulated,
            "member_removals": ports_to_remove,
            "before": before,
            "after": simulated,
        }

    remove_member_ports(connection, lag_id, ports_to_remove)
    final_lag = get_lag_config(connection, lag_id)
    return {
        "lag_id": lag_id,
        "changed": True,
        "lag": final_lag,
        "member_removals": ports_to_remove,
        "before": before,
        "after": final_lag,
    }


def _override_delete_unlisted(
    module: AnsibleModule, connection: Connection, wanted: set,
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Delete LAGs the task did not mention.

    Only reached for state=overridden with a 'config' list. The deprecated
    flat form manages a single LAG and cannot express "everything else", so
    it never enumerates.
    """
    deleted: list[str] = []
    skipped: list[dict[str, Any]] = []
    changed = False
    for record in gather_lags(module, connection):
        device_id = record.get("lagId")
        if device_id is None or _normalize_lag_id(device_id) in wanted:
            continue
        lag_id = _normalize_lag_id(device_id)
        if not module.check_mode:
            try:
                delete_lag(connection, lag_id)
            except ConnectionError as exc:
                # Report it — a silently skipped delete looks like success
                # while the LAG is still on the device.
                skipped.append({"lag_id": lag_id, "reason": to_text(exc)})
                continue
        deleted.append(lag_id)
        changed = True
    return changed, deleted, skipped


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    if not module._socket_path:
        module.fail_json(msg="HTTPAPI connection is required for this module")

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))
        return

    state = module.params.get("state")

    try:
        if state == STATE_GATHERED:
            lags = gather_lags(module, connection)
            # 'gathered' mirrors the collection-wide convention; 'lags' is kept
            # for backward compatibility with existing playbooks.
            module.exit_json(changed=False, lags=lags, gathered=lags)

        entries = _entries_from_params(module)
        if not entries:
            module.fail_json(
                msg="The 'config' parameter is required when state=%s "
                    "(or supply the deprecated top-level LAG parameters)" % state
            )

        before_snapshot = gather_lags(module, connection)
        results: list[dict[str, Any]] = []
        changed = False
        deleted_lags: list[str] = []
        skipped_lags: list[dict[str, Any]] = []

        # Phase 1 (overridden only): remove LAGs absent from config.
        if state == STATE_OVERRIDDEN and module.params.get("config"):
            wanted = {_normalize_lag_id(e.get("lag_id")) for e in entries}
            changed, deleted_lags, skipped_lags = _override_delete_unlisted(
                module, connection, wanted)
            for skip in skipped_lags:
                module.warn(
                    "Overridden: LAG %s could not be deleted and was skipped: %s"
                    % (skip.get("lag_id"), skip.get("reason", "unknown"))
                )

        # Phase 2: apply each entry.
        for entry in entries:
            if state == STATE_DELETED:
                result = _process_entry_deleted(module, connection, entry)
            else:
                result = _process_entry(module, connection, entry, state)
            results.append(result)
            if result.get("changed"):
                changed = True

        output: dict[str, Any] = {
            "changed": changed,
            "before": before_snapshot,
            "lags": results,
        }
        if changed and not module.check_mode:
            output["after"] = gather_lags(module, connection)
        else:
            output["after"] = before_snapshot
        if deleted_lags:
            output["deleted_lags"] = deleted_lags
        if skipped_lags:
            output["skipped_lags"] = skipped_lags

        # Single-LAG shortcuts, kept so pre-config-list playbooks and their
        # assertions continue to work unchanged.
        if len(results) == 1:
            single = results[0]
            for key in ("lag", "lag_removed", "member_additions", "member_removals"):
                if key in single:
                    output[key] = single[key]

        module.exit_json(**output)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeLagError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
