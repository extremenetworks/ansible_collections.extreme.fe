# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage L2 interface settings on Fabric Engine switches.

Manages VLAN membership (access/trunk mode, tagged/untagged VLANs)
on physical ports and LAG interfaces.

REST API endpoints used:
  VLAN membership:
    - GET  /v0/configuration/vlan/interfaces
    - GET  /v0/configuration/vlan/interfaces/type/{type}/name/{name}
    - PUT  /v0/configuration/vlan/interfaces/type/{type}/name/{name}
  Reset protection (state=deleted without config):
    - GET  /v0/configuration/vlan
    - GET  /v0/configuration/lag
"""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_l2_interfaces
short_description: Manages L2 interface settings on ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
- Configure L2 interface settings on ExtremeNetworks Fabric Engine switches using the C(extreme_fe) HTTPAPI connection
  plugin.
- Supports VLAN membership (access/trunk mode, tagged/untagged VLANs)
  on one or more interfaces per task via the C(config) list parameter.
author:
- Bjorn Haas (@bhaas_extr)
notes:
- Tested against Fabric Engine Version 9.3.2.
- Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI connection plugin.
- List each port or LAG only once in C(config).
- With C(replaced) and C(overridden), an omitted C(untagged_vlan) is reset to VLAN 1, and the port type follows
  C(tagged_vlans) (C(TRUNK) when you give tagged VLANs, C(ACCESS) otherwise). Set C(untagged_vlan) explicitly to
  keep a different one.
- C(overridden) resets every interface not listed in C(config) to C(ACCESS) with untagged VLAN 1 and no tagged
  VLANs. It fails when C(config) is empty, so it never resets every interface by accident.
- C(deleted) without C(config) removes the VLAN membership of every port and LAG (untagged VLAN 0, no tagged
  VLANs) and keeps each interface's port type.
- To keep your management connection up, C(overridden) and C(deleted) without C(config) never reset the
  management port, the ports and LAGs in a management VLAN, or the member ports of such a LAG. They also skip
  LACP/VLACP LAGs, which the switch cannot reset, and any interface the switch refuses to reset. Skipped
  interfaces get a warning and are listed in C(skipped_interfaces). An interface you name in C(config) is always
  configured, protected or not. If the module cannot read the information it needs to find the protected
  interfaces, the task fails before changing anything.
- A C(TRUNK) LAG with no member ports and not in LACP mode ignores C(untagged_vlan). The module warns and leaves it
  out; run the task again after adding member ports.
- The C(gathered) result can be passed back as C(config). If you gathered only some interfaces, re-apply it with
  C(merged) or C(replaced), not C(overridden), which would reset every interface that is not in the list.
- The per-interface result list under C(interfaces) is the form used up to 1.2.1 and will be removed in 2.0.0.
  Use C(gathered), C(before) and C(after) instead.
- If the connection drops during a change, the module cannot tell whether it was applied, so it reports
  C(changed=true) with C(details.outcome=unknown). Run the task again to bring the switch to the requested state.
- A failed task reports C(changed=true) if the switch was already modified by an earlier write in the same task,
  and the error message names the interfaces already written.
- Supports check mode and diff mode.
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
        - When omitted, C(replaced) and C(overridden) derive it from the rest of
          the entry (see C(state)), except on an interface whose current type is
          not one of the choices, which keeps its type.
        type: str
        choices:
        - ACCESS
        - TRUNK
      untagged_vlan:
        description:
        - VLAN ID for untagged traffic (port VLAN).
          Use C(0) to clear the untagged VLAN.
        - On a C(TRUNK) LAG that is not in LACP mode and has no member ports,
          the device ignores this value and reports C(0). The module neither
          compares nor sends it, including its automatic membership in the
          allowed VLAN list; only explicitly listed tagged VLANs are written.
          If it is the only difference, no request is sent and nothing is
          reported as changed, so the value is not stored or pending on the
          device. When other attributes of the LAG change, the request omits
          C(portVlan). The module warns once per interface; run the task again
          after the LAG has member ports to apply the value.
        type: int
      tagged_vlans:
        description:
        - Authoritative list of tagged (allowed) VLANs for the
          interface. In C(merged) state, replaces the current
          tagged list (use C(add_tagged_vlans)/C(remove_tagged_vlans)
          for incremental changes). In C(replaced)/C(overridden)
          states, sets the complete tagged list.
        - In C(deleted) state it is NOT an authoritative list. It names the VLANs to remove
          from the tagged list, together with C(remove_tagged_vlans); tagged VLANs not
          named are kept. When neither C(tagged_vlans) nor C(remove_tagged_vlans) is
          given, every tagged VLAN is removed.
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
      for each listed interface. A field left out is reset to the
      device default rather than kept, so omitting C(untagged_vlan)
      sets it back to VLAN 1. C(port_type) is the exception - an
      explicit value is always honoured, and only when it is left
      out is it derived from the rest of the config, C(TRUNK) when
      C(tagged_vlans) is given and C(ACCESS) otherwise, so a trunk
      port does not have to spell it out. An interface whose current
      type is not C(ACCESS) or C(TRUNK) keeps it when C(port_type) is
      left out.
    - C(overridden) like C(replaced) but also resets every
      interface NOT in C(config) to device defaults, except the
      protected ones described in the notes.
    - C(deleted) removes tagged VLAN membership. When no VLAN
      parameters are given, all memberships are reset. Without
      C(config) it does so for every interface, except the protected
      ones described in the notes.
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

# -------------------------------------------------------------------------
# Task 8: Reset all interfaces except protected
#   - 'deleted' without 'config' resets every port and LAG; the management
#     port, the management VLAN members and LACP LAGs are skipped with a
#     warning and listed in 'skipped_interfaces'
# -------------------------------------------------------------------------
- name: Reset all interfaces except protected
  extreme.fe.extreme_fe_l2_interfaces:
    state: deleted
  register: l2_reset
"""

RETURN = r"""
changed:
    description: Indicates whether any changes were made.
    returned: always
    type: bool
gathered:
    description:
    - L2 interface configuration gathered from the device, one entry per
      interface in the form the C(config) option accepts, so it can be
      supplied back as C(config) unchanged. Re-applying a result gathered
      without C(config) with C(merged), C(replaced) or C(overridden)
      changes nothing.
    - Gathered with C(config), the result lists only the named interfaces.
      It is still safe to re-apply with C(merged) or C(replaced), but
      C(overridden) takes it as the complete interface list and resets every
      unlisted interface that is not protected, so re-apply such a result
      with C(overridden) only to do that.
    - A C(port_type) other than C(ACCESS) or C(TRUNK) is left out. Such a
      type is kept when the result is re-applied.
    - C(tagged_vlans) does not repeat C(untagged_vlan), which the device also
      lists among the allowed VLANs of a C(TRUNK) interface.
    - A C(TRUNK) LAG that is not in LACP mode and has no member ports reports
      C(untagged_vlan) 0, which re-applies without a request or a warning.
    - Interfaces named in C(config) that the device does not have are left
      out, with a warning.
    - Returned only for C(state=gathered).
    returned: when state is gathered
    type: list
    elements: dict
    contains:
        name:
            description: Interface identifier, C(LAG:) prefixed for a LAG.
            type: str
        port_type:
            description: Interface VLAN mode, C(ACCESS) or C(TRUNK).
            type: str
        untagged_vlan:
            description: Untagged (port) VLAN, C(0) when there is none.
            type: int
        tagged_vlans:
            description: Tagged VLANs, empty for an C(ACCESS) interface.
            type: list
            elements: int
    sample:
        - name: "1:5"
          port_type: TRUNK
          untagged_vlan: 1
          tagged_vlans: [10, 20]
        - name: "LAG:10"
          port_type: ACCESS
          untagged_vlan: 5
          tagged_vlans: []
interfaces:
    description: >-
        Under the action states, per-interface operation results.
        Under C(state=overridden) the entries for the interfaces named in
        C(config) come first, followed by every interface absent from
        C(config) that the module was able to reset, each carrying its own
        C(changed) flag. Interfaces it could not reset are reported by name
        in C(skipped_interfaces) and appear here no further. Under
        C(state=deleted) without C(config) it lists every interface the
        module was able to reset in the same way.
        Under C(state=gathered) this instead lists the gathered interfaces
        in the per-interface result form below, which is what the module
        returned for that state up to 1.2.1. It cannot be supplied back as
        C(config). That form is deprecated and will be removed in 2.0.0 -
        use C(gathered).
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
before:
    description: >-
        Settings for each interface the task touched, as they were before
        it ran - those named in C(config), plus every interface
        C(state=overridden) or C(state=deleted) without C(config) was able
        to reset, changed or not. Interfaces
        listed in C(skipped_interfaces) are not covered.
    returned: when state is not gathered
    type: list
    elements: dict
after:
    description: >-
        Settings for each interface the task touched once it has run.
        In check mode this is the predicted state.
    returned: when state is not gathered
    type: list
    elements: dict
reset_interfaces:
    description: >-
        Interfaces that were modified and reset to defaults during
        overridden state because they were not listed in config, or by
        state=deleted without config.
    returned: when state is overridden, or deleted without config
    type: list
    elements: str
skipped_interfaces:
    description: >-
        Interfaces that could not be reset during overridden state
        (e.g. LACP LAGs or protected ports). Under state=deleted without
        config also the protected interfaces, the out-of-band management
        port, the members of a management VLAN and the member ports of a
        LAG in one, each named in a warning with the reason.
    returned: when state is overridden, or deleted without config
    type: list
    elements: str
"""

import re
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

ARGUMENT_SPEC: dict[str, Any] = {
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

KNOWN_INTERFACE_TYPES: set[str] = {"PORT", "LAG"}

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# Default L2 settings used when resetting ports (overridden state).
# Verified against Fabric Engine factory defaults: ACCESS mode, portVlan=1.
# allowedVlans is empty because an ACCESS port carries no tagged membership:
# the device reports [] and the ACCESS payload path clears the list, so a
# non-empty reset target would never compare equal to a port already at the
# default and `overridden` would PUT it on every run.
DEFAULTS: dict[str, Any] = {
    "portType": "ACCESS",
    "portVlan": 1,
    "allowedVlans": [],
}

# Aggregation modes whose LAG cannot be reset: the device rejects a port-type
# change on an MLT running LACP/VLACP.
UNRESETTABLE_LAG_MODES: set[str] = {"LACP", "VLACP"}


# --------------------------------------------------------------------------
# Exception
# --------------------------------------------------------------------------


class FeL2InterfacesError(Exception):
    """Base exception for the L2 interface module."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, object] | None = None,
        extra: dict[str, object] | None = None,
        changed: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        # Extra top-level fail_json keys, e.g. the 'code' of a transport error, so a
        # wrapped ConnectionError still fails with the keys it produced unwrapped.
        self.extra = extra or {}
        # True when a failure follows a write of the same task that succeeded (see
        # _WriteTracker); None keeps the default fail result, which has no 'changed'.
        self.changed = changed

    def to_fail_kwargs(self) -> dict[str, object]:
        data: dict[str, object] = {"msg": to_text(self)}
        data.update(self.extra)
        if self.details:
            data["details"] = self.details
        if self.changed is not None:
            data["changed"] = self.changed
        return data


class _WriteTracker:
    """Remember which writes of this task already modified the device.

    Used as a context manager around the write phase of a task. Once a PUT has
    succeeded (record()), a later failure - the PUT of another interface, the
    retry PUT, or a read-back - must not hide that change: the failure is
    re-raised as an FeL2InterfacesError with changed=true, its message extended
    by the interfaces already written. A ConnectionError keeps its msg and code.
    Before the first write, failures pass through untouched.
    """

    def __init__(self) -> None:
        self.done: list[str] = []

    def record(self, what: str) -> None:
        # The retry PUT of an interface is not a second change worth listing.
        if what not in self.done:
            self.done.append(what)

    def mark(self) -> int:
        """Position to roll back to with rollback()."""
        return len(self.done)

    def rollback(self, mark: int) -> None:
        """Forget the entries recorded after *mark* (an earlier write of the same interface stays)."""
        del self.done[mark:]

    def __enter__(self) -> _WriteTracker:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is None or not self.done or not isinstance(exc, (ConnectionError, FeL2InterfacesError)):
            return False
        message = _append_sentence(
            to_text(exc),
            "The task had already changed the device before this failure: wrote %s." % ", ".join(self.done),
        )
        if isinstance(exc, FeL2InterfacesError):
            raise FeL2InterfacesError(message, details=exc.details, extra=exc.extra, changed=True) from exc
        # Same fail result keys run_module() builds for a ConnectionError (msg,
        # code), plus changed=true.
        code = getattr(exc, "code", None)
        raise FeL2InterfacesError(message, extra={"code": code}, changed=True) from exc


def _append_sentence(message: str, sentence: str) -> str:
    """Append a sentence to an error message, adding the full stop it may lack.

    A message that already ends a sentence ('.', '!' or '?') gets no extra one.
    """
    lead = message.rstrip()
    if lead and not lead.endswith((".", "!", "?")):
        lead += "."
    return ("%s %s" % (lead, sentence)).strip()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _is_not_found_response(payload: object | None) -> bool:
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


def parse_interface_name(name: str) -> tuple[str, str]:
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
                raise FeL2InterfacesError(f"Interface name is empty after '{prefix_upper}:' prefix")
            return prefix_upper, iface_name
    return "PORT", raw


def _normalize_vlan_list(value: Iterable[object] | None) -> list[int]:
    if value is None:
        return []
    if isinstance(value, str):
        if not HAS_YAML:
            raise FeL2InterfacesError(
                "PyYAML is required to parse VLAN list from a string. Install it with: pip install PyYAML"
            )
        try:
            parsed = yaml.safe_load(value)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            value = parsed
        else:
            value = [value]
    result: list[int] = []
    for item in value:
        if item is None:
            continue
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            raise FeL2InterfacesError(f"Unable to convert VLAN value '{item}' to an integer")
    return result


def _normalize_port_type(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip().upper()
        return stripped if stripped else None
    raise FeL2InterfacesError(f"Unsupported port_type value '{value}' supplied")


def _normalize_vlan_value(value: object | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise FeL2InterfacesError(f"Unable to convert VLAN value '{value}' to an integer")


# --------------------------------------------------------------------------
# REST API wrappers
# --------------------------------------------------------------------------

COLLECTION_PATH = "/v0/configuration/vlan/interfaces"
LAG_PATH = "/v0/configuration/lag"
VLAN_PATH = "/v0/configuration/vlan"


def _interface_path(iface_type: str, iface_name: str) -> str:
    return f"/v0/configuration/vlan/interfaces/type/" f"{quote(iface_type)}/name/{quote(iface_name)}"


def get_interface_settings(connection: Connection, iface_type: str, iface_name: str) -> dict[str, object] | None:
    try:
        data = connection.send_request(None, path=_interface_path(iface_type, iface_name), method="GET")
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


def _is_error_document(data: object | None) -> bool:
    """True for a 2xx error document: errorCode, statusCode/code >= 400, or a non-empty errors/error."""
    if not isinstance(data, dict):
        return False
    # An or-chain, like the other classifiers: a null or empty statusCode must
    # not hide a code next to it.
    code = data.get("statusCode") or data.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    if data.get("errorCode") or (isinstance(code, int) and not isinstance(code, bool) and code >= 400):
        return True
    errors = data.get("errors")
    return bool(isinstance(errors, list) and errors) or bool(data.get("error"))


def _strict_collection(data: object | None) -> list[dict[str, Any]]:
    """The interface list of a collection answer, or FeL2InterfacesError (fail closed)."""
    items = data
    if isinstance(data, dict) and not _is_error_document(data):
        items = next((data[key] for key in ("interfaces", "items", "data") if isinstance(data.get(key), list)), None)
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise FeL2InterfacesError(
            "Unexpected response when retrieving the interface list (%s); nothing was changed" % COLLECTION_PATH,
            details={"response": data},
        )
    return list(items)


def get_all_interface_settings(
    connection: Connection,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """GET /v0/configuration/vlan/interfaces -- returns all interfaces.

    *strict* is for the reset sweeps (overridden, deleted without config): there
    an error document or a malformed answer must not read as "no interfaces", so
    only a list of interface documents (or a 404) is accepted.
    """
    try:
        data = connection.send_request(None, path=COLLECTION_PATH, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    if strict:
        return _strict_collection(data)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("interfaces", "items", "data"):
            if isinstance(data.get(key), list):
                return [item for item in data[key] if isinstance(item, dict)]
    return []


def get_lag_list(connection: Connection, strict: bool = False) -> list[dict[str, Any]]:
    """GET /v0/configuration/lag -- every LAG record (lagId, mode, memberPorts, ...).

    *strict* is for expanding a management-VLAN LAG into its member ports: a LAG
    is known to exist, so a 404, an empty or a not-found answer cannot mean "no
    LAGs" and fails the task instead of leaving its ports unprotected.
    """
    try:
        data = connection.send_request(None, path=LAG_PATH, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404 and not strict:
            return []
        if strict:
            raise FeL2InterfacesError(
                "Cannot expand the LAG(s) of the management VLAN into their ports: reading %s failed (%s); "
                "nothing was changed" % (LAG_PATH, to_text(exc)),
                extra={"code": getattr(exc, "code", None)},
            ) from exc
        raise
    if strict and (data is None or _is_not_found_response(data) or _is_error_document(data)):
        raise FeL2InterfacesError(
            "Cannot expand the LAG(s) of the management VLAN into their ports: %s returned no LAG list; "
            "nothing was changed" % LAG_PATH,
            details={"response": data},
        )
    if data is None or _is_not_found_response(data):
        # No LAGs on the device, so there is nothing to classify.
        return []
    if not isinstance(data, list):
        # Reading this as "no LAGs" would leave an LACP LAG unclassified, which
        # is exactly the case the caller consults it for.
        raise FeL2InterfacesError(
            "Unexpected response when retrieving LAG aggregation modes",
            details={"response": data},
        )
    return [item for item in data if isinstance(item, dict)]


def get_lag_modes(connection: Connection) -> dict[str, str]:
    """GET /v0/configuration/lag -- map LAG id to its aggregation mode."""
    return _lag_modes(get_lag_list(connection))


def _lag_modes(lags: list[dict[str, Any]]) -> dict[str, str]:
    """Map LAG id to its aggregation mode, from the LAG records."""
    modes: dict[str, str] = {}
    for item in lags:
        lag_id = item.get("lagId")
        mode = item.get("mode")
        if lag_id is None or not isinstance(mode, str):
            continue
        modes[str(lag_id).strip()] = mode.strip().upper()
    return modes


def _lag_is_memberless_non_lacp(connection: Connection, lag_id: str) -> bool:
    """True when the LAG is readable, not in LACP mode and has no member ports.

    GET /v0/configuration/lag/{lag_id}. Any doubt (read failure, unexpected
    body, missing mode or memberPorts) answers False, so the caller then
    behaves exactly as it did before this check existed.
    """
    path = f"{LAG_PATH}/{quote(lag_id.strip())}"
    try:
        data = connection.send_request(None, path=path, method="GET")
    except (ConnectionError, FeL2InterfacesError):
        return False
    if not isinstance(data, dict):
        return False
    mode = data.get("mode")
    members = data.get("memberPorts")
    if not isinstance(mode, str) or not isinstance(members, list):
        return False
    # An LACP LAG negotiates its members, so it is never treated as memberless.
    return mode.strip().upper() != "LACP" and not members


def _should_ignore_port_vlan(
    connection: Connection,
    iface_type: str,
    iface_name: str,
    comparison: dict[str, Any],
) -> bool:
    """Whether portVlan must stay out of the comparison for this interface.

    The device ignores portVlan on a non-LACP TRUNK LAG that has no member
    ports and always reports 0, so comparing it can never converge. ACCESS
    LAGs do store it and are left alone.
    """
    if iface_type != "LAG" or comparison.get("portType") != "TRUNK":
        return False
    return _lag_is_memberless_non_lacp(connection, iface_name)


def _unsupported_reset_reason(iface_type: str, iface_name: str, lag_modes: dict[str, str]) -> str | None:
    """Why this interface cannot be reset to defaults, or None if it can.

    Classifying before the PUT is what keeps check mode honest: a real run
    learns the interface is off limits from the rejected request, which check
    mode never sends, so it would otherwise predict a reset that cannot happen.
    """
    if iface_type != "LAG":
        return None
    mode = lag_modes.get(iface_name.strip())
    if mode in UNRESETTABLE_LAG_MODES:
        return f"the device rejects port-type changes on a {mode} LAG"
    return None


def _raise_if_error_body(response: object | None, iface_type: str, iface_name: str) -> None:
    """Fail when a 2xx response carries an error body.

    The device can answer a rejected write with a success status and an error
    payload. Left unchecked that write is reported as applied, so the task
    claims changed against a device that changed nothing.
    """
    if not isinstance(response, dict):
        return
    code = response.get("errorCode") or response.get("statusCode") or response.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    errors = response.get("errors")
    has_errors = isinstance(errors, list) and bool(errors)
    # Only an explicit error marker counts. A normal interface document carries
    # none of these keys, and a bare `message` is not on its own an error, so
    # this cannot misfire on a write the device actually accepted.
    if not (response.get("errorCode") or (isinstance(code, int) and code >= 400) or has_errors):
        return
    message = response.get("errorMessage") or response.get("message") or response.get("detail")
    if not message and has_errors:
        message = f"{len(errors)} error(s) reported: {errors}"
    display = f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
    raise FeL2InterfacesError(
        f"Device rejected the VLAN membership write for {display}" + (f": {message}" if message else ""),
        details={"interface": display, "code": code, "response": response},
    )


def _error_body_text(response: object | None) -> str | None:
    """Short description when a 2xx response is an error document, else None (markers of _raise_if_error_body)."""
    if not isinstance(response, dict):
        return None
    code = response.get("errorCode") or response.get("statusCode") or response.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    errors = response.get("errors")
    if not (
        response.get("errorCode") or (isinstance(code, int) and code >= 400) or (isinstance(errors, list) and errors)
    ):
        return None
    message = response.get("errorMessage") or response.get("message") or response.get("detail") or errors
    return f"{code}: {message}" if code else str(message)


def replace_interface_settings(
    connection: Connection,
    iface_type: str,
    iface_name: str,
    payload: dict[str, object],
) -> None:
    path = _interface_path(iface_type, iface_name)
    try:
        response = connection.send_request(payload, path=path, method="PUT")
    except ConnectionError as exc:
        if not answer_unknown(exc):
            raise
        # No answer (a lost connection; no code, or a negative JSON-RPC code of
        # the persistent connection): the PUT may have been applied, so the
        # task reports changed (and a reset sweep does not list it as skipped).
        raise FeL2InterfacesError(
            "%s. The PUT %s may have been applied before the answer was lost; check the interface on the device."
            % (to_text(exc).rstrip("."), path),
            details={"outcome": "unknown", "resource": path},
            extra={"code": None},
            changed=True,
        ) from exc
    _raise_if_error_body(response, iface_type, iface_name)


# --------------------------------------------------------------------------
# Ansible-facing state normalisation
# --------------------------------------------------------------------------


def _to_ansible_state(
    raw: dict[str, Any] | None,
) -> dict[str, Any]:
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
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
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
    entry: dict[str, Any],
    existing: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
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
        desired_port_type = current_port_type or ("TRUNK" if target_allowed else "ACCESS")

    # ACCESS ports do not support allowedVlans.
    if desired_port_type == "ACCESS":
        has_tagged_intent = (
            tagged_vlans not in (None, []) or add_tagged not in (None, []) or remove_tagged not in (None, [])
        )
        if has_tagged_intent:
            raise FeL2InterfacesError(
                "ACCESS ports do not support tagged VLANs. "
                "Either remove tagged VLAN parameters or set "
                "'port_type' to TRUNK."
            )
        target_allowed = set()

    # TRUNK: device includes portVlan in allowedVlans.
    if desired_port_type == "TRUNK" and target_untagged is not None and target_untagged > 0:
        target_allowed.add(target_untagged)

    payload: dict[str, Any] = {
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
    entry: dict[str, Any],
    existing: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build desired payload for replaced state (authoritative per-interface)."""
    add_tagged = entry.get("add_tagged_vlans")
    remove_tagged = entry.get("remove_tagged_vlans")
    if add_tagged not in (None, []) or remove_tagged not in (None, []):
        raise FeL2InterfacesError(
            "'add_tagged_vlans' and 'remove_tagged_vlans' are not valid for states replaced and overridden"
        )

    desired_port_type = _normalize_port_type(entry.get("port_type"))
    tagged_vlans = entry.get("tagged_vlans")
    target_untagged = _normalize_vlan_value(entry.get("untagged_vlan"))

    target_allowed: set[int] = set(_normalize_vlan_list(tagged_vlans))

    # `replaced` and `overridden` are authoritative: a field the user leaves
    # out is reset to the device default, not inherited from whatever the
    # interface happens to carry. DEFAULTS is the same reset target
    # `overridden` applies to the interfaces absent from `config`, so a listed
    # and an unlisted interface end up meaning the same thing by "default".
    if target_untagged is None:
        target_untagged = DEFAULTS["portVlan"]

    # port_type is *derived from the supplied config*, not read from the
    # device, so it stays authoritative: a tagged list requires TRUNK, and its
    # absence means ACCESS. Defaulting to DEFAULTS["portType"] instead would
    # make `tagged_vlans` without an explicit `port_type` fail the ACCESS
    # guard below, breaking the ordinary way of writing a trunk port.
    # A current type the option cannot express is kept instead: `gathered`
    # leaves it out, so deriving ACCESS/TRUNK would make a re-applied gathered
    # result change the interface.
    current_port_type = _normalize_port_type(existing.get("portType"))
    if desired_port_type is None and _is_unexpressible_port_type(current_port_type):
        desired_port_type = current_port_type
        # The builders mirror portVlan into allowedVlans only for TRUNK. For a
        # kept type the device's own list decides: mirror it when it does.
        current_allowed = {int(v) for v in existing.get("allowedVlans") or []}
        if target_untagged > 0 and target_untagged in current_allowed:
            target_allowed.add(target_untagged)
    if desired_port_type is None:
        desired_port_type = "TRUNK" if target_allowed else "ACCESS"

    if desired_port_type == "ACCESS" and target_allowed:
        raise FeL2InterfacesError(
            "ACCESS ports do not support tagged VLANs. Either remove 'tagged_vlans' or set 'port_type' to TRUNK."
        )

    # TRUNK: device includes portVlan in allowedVlans.
    if desired_port_type == "TRUNK" and target_untagged is not None and target_untagged > 0:
        target_allowed.add(target_untagged)

    payload: dict[str, Any] = {
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


def _is_unexpressible_port_type(port_type: str | None) -> bool:
    """True for a reported port type that is not one of the port_type choices (ACCESS, TRUNK)."""
    return port_type is not None and port_type not in ARGUMENT_SPEC["config"]["options"]["port_type"]["choices"]


def _build_deleted_payload(
    entry: dict[str, Any],
    existing: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build desired payload for deleted state."""
    add_tagged = entry.get("add_tagged_vlans")
    if add_tagged not in (None, []):
        raise FeL2InterfacesError(
            "'add_tagged_vlans' is not valid for state deleted. "
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
    if desired_port_type == "TRUNK" and target_untagged is not None and target_untagged > 0:
        target_allowed.add(target_untagged)

    payload: dict[str, Any] = {
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


def _build_defaults_payload() -> tuple[dict[str, Any], dict[str, Any]]:
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


def _current_state_key(raw: dict[str, Any]) -> dict[str, Any]:
    """Build a comparison dict from existing device data."""
    return {
        "portType": _normalize_port_type(raw.get("portType")),
        "portVlan": _normalize_vlan_value(raw.get("portVlan")),
        "allowedVlans": sorted({int(v) for v in raw.get("allowedVlans") or []}),
    }


def _without_port_vlan(key: dict[str, Any], ignore: bool) -> dict[str, Any]:
    """Return the comparison dict or payload, minus portVlan when it must be ignored."""
    if not ignore:
        return key
    return {k: v for k, v in key.items() if k != "portVlan"}


def _predicted_state(existing: dict[str, Any], comparison: dict[str, Any], ignore_port_vlan: bool) -> dict[str, Any]:
    """State expected after a write (or reported in check mode).

    portVlan is only ignored on a memberless non-LACP TRUNK LAG, which the
    device reads back with portVlan 0. A LAG that already is TRUNK keeps the
    value the device reports for it; one turned into TRUNK by this write (from
    ACCESS, say) loses the portVlan it stored before, so the prediction is 0,
    the value a real run reads back, not the stale ACCESS one.
    """
    predicted = dict(comparison)
    if ignore_port_vlan:
        if _normalize_port_type(existing.get("portType")) == "TRUNK":
            predicted["portVlan"] = existing.get("portVlan")
        else:
            predicted["portVlan"] = 0
    return predicted


def _write_and_read_back(
    connection: Connection,
    iface_type: str,
    iface_name: str,
    payload: dict[str, Any],
    fallback: dict[str, Any],
    ignore_port_vlan: bool,
    writes: _WriteTracker | None = None,
) -> dict[str, Any]:
    """PUT the payload and read the interface back, retrying once if needed.

    Each accepted PUT is recorded in writes, when given.
    """
    display = f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
    replace_interface_settings(connection, iface_type, iface_name, payload)
    if writes is not None:
        writes.record(display)
    final = get_interface_settings(connection, iface_type, iface_name) or fallback
    # Re-try if portVlan diverges (port-type transition edge case). The retry
    # is pointless when portVlan is excluded: the payload no longer carries it
    # and the device would never report it.
    expected_vlan = payload.get("portVlan")
    if (
        not ignore_port_vlan
        and expected_vlan is not None
        and _normalize_vlan_value(final.get("portVlan")) != expected_vlan
    ):
        replace_interface_settings(connection, iface_type, iface_name, payload)
        final = get_interface_settings(connection, iface_type, iface_name) or fallback
    return final


def _without_mirrored_untagged(
    payload: dict[str, Any],
    comparison: dict[str, Any],
    entry: dict[str, Any],
    existing: dict[str, Any],
    state: str,
    ignore_port_vlan: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Drop the VLAN the builders mirrored from untagged_vlan into allowedVlans.

    When portVlan is ignored the untagged VLAN has no role on the device, so
    its automatic membership in allowedVlans must be neither compared nor
    written. A VLAN the user listed explicitly (tagged_vlans or
    add_tagged_vlans) stays, and so does the membership `merged` keeps from the
    device when no tagged_vlans list was given.
    """
    vlan = comparison.get("portVlan")
    if not ignore_port_vlan or not isinstance(vlan, int) or vlan <= 0 or vlan not in comparison["allowedVlans"]:
        return payload, comparison
    explicit = set(_normalize_vlan_list(entry.get("tagged_vlans"))) | set(
        _normalize_vlan_list(entry.get("add_tagged_vlans"))
    )
    if state == STATE_MERGED and entry.get("tagged_vlans") is None:
        kept = {int(v) for v in existing.get("allowedVlans") or []}
        explicit |= kept - set(_normalize_vlan_list(entry.get("remove_tagged_vlans")))
    if vlan in explicit:
        return payload, comparison
    allowed = [v for v in comparison["allowedVlans"] if v != vlan]
    return {**payload, "allowedVlans": list(allowed)}, {**comparison, "allowedVlans": allowed}


def _apply_interface(
    connection: Connection,
    iface_type: str,
    iface_name: str,
    existing: dict[str, Any],
    payload: dict[str, Any],
    comparison: dict[str, Any],
    *,
    check_mode: bool,
    ignore_port_vlan: bool = False,
    writes: _WriteTracker | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Apply payload to one interface. Returns (changed, final_raw)."""
    # Both sides of the comparison drop portVlan together when it is ignored.
    current = _without_port_vlan(_current_state_key(existing), ignore_port_vlan)
    desired = _without_port_vlan(comparison, ignore_port_vlan)
    if current == desired:
        return False, existing

    predicted = _predicted_state(existing, comparison, ignore_port_vlan)
    if check_mode:
        return True, predicted

    mark = writes.mark() if writes is not None else 0
    final = _write_and_read_back(connection, iface_type, iface_name, payload, predicted, ignore_port_vlan, writes)
    # `changed` comes from the same compared keys that feed `differences`, so a
    # write that left the observable state untouched is never reported as a change.
    final_key = _without_port_vlan(_current_state_key(final), ignore_port_vlan)
    if final_key == current and writes is not None:
        # The module concluded this write changed nothing, so a later failure
        # must not name it. Only this call's entry is dropped.
        writes.rollback(mark)
    return final_key != current, final


def _warn_untagged_ignored(warn: Callable[[str], None] | None, name: str, entry: dict[str, Any]) -> None:
    """Tell the user an explicit untagged_vlan has no effect on this LAG yet."""
    requested = _normalize_vlan_value(entry.get("untagged_vlan"))
    # Only an explicit, non-zero request is worth a warning.
    if warn is None or not requested:
        return
    warn(
        f"{name}: untagged_vlan {requested} is not applied or stored on a TRUNK LAG "
        "without member ports (the device ignores it and reports 0). "
        "Re-run the task after adding member ports."
    )


def _process_config_entry(
    connection: Connection,
    entry: dict[str, Any],
    state: str,
    *,
    check_mode: bool,
    warn: Callable[[str], None] | None = None,
    writes: _WriteTracker | None = None,
) -> dict[str, Any]:
    """Process a single config entry. Returns per-interface result dict."""
    name = entry["name"]
    iface_type, iface_name = parse_interface_name(name)
    # Canonical name: omit PORT: prefix, keep LAG: prefix.
    canonical_name = f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name

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
    if raw_existing is None and state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
        raise FeL2InterfacesError(f"Interface '{canonical_name}' does not exist on the device")
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

    # A memberless non-LACP TRUNK LAG ignores portVlan, so leave it out of the
    # comparison and the request (deleted keeps its own semantics).
    ignore_port_vlan = state != STATE_DELETED and _should_ignore_port_vlan(
        connection, iface_type, iface_name, comparison
    )
    if ignore_port_vlan:
        _warn_untagged_ignored(warn, canonical_name, entry)
        payload, comparison = _without_mirrored_untagged(payload, comparison, entry, existing, state, True)
        # portVlan is optional in the PUT schema and the device ignores it on
        # such a LAG, so omitting it changes nothing on the device. Dropping it
        # here covers the first PUT and the retry, which reuse this payload.
        payload = _without_port_vlan(payload, True)

    changed, final_raw = _apply_interface(
        connection,
        iface_type,
        iface_name,
        existing,
        payload,
        comparison,
        check_mode=check_mode,
        ignore_port_vlan=ignore_port_vlan,
        writes=writes,
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


def _to_config_entry(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """One interface in the shape of a config entry, for the gathered result.

    The same fields as the before/after snapshot, minus values the module does
    not accept back (an unreported field or a port type other than ACCESS and
    TRUNK). untagged_vlan is kept as reported, also the 0 of a memberless TRUNK
    LAG: re-applied, 0 adds no tagged VLAN and the comparison already ignores
    portVlan there, so the task is a no-op instead of warning about VLAN 1.
    """
    entry: dict[str, Any] = {"name": name}
    for key, value in _to_ansible_state(raw).items():
        if value is None:
            continue
        if key == "port_type" and _is_unexpressible_port_type(value):
            continue
        entry[key] = value
    return entry


def _gathered_raw(module: AnsibleModule, connection: Connection) -> list[tuple[str, dict[str, Any] | None]]:
    """Read the interfaces for state=gathered as [(canonical name, raw settings or None), ...]."""
    config = module.params.get("config") or []
    found: list[tuple[str, dict[str, Any] | None]] = []
    if config:
        for entry in config:
            iface_type, iface_name = parse_interface_name(entry["name"])
            # Canonical name: omit PORT: prefix, keep LAG:.
            canonical_name = f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
            raw = get_interface_settings(connection, iface_type, iface_name)
            if raw is None:
                module.warn(f"Interface '{canonical_name}' does not exist on the device; left out of gathered")
            found.append((canonical_name, raw))
        return found
    for item in get_all_interface_settings(connection):
        iface_type = str(item.get("interfaceType") or "PORT").strip().upper()
        iface_name = str(item.get("interfaceName") or "").strip()
        if not iface_name:
            continue
        name = f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name
        found.append((name, item.get("interfaceSettings") or item))
    return found


def _handle_gathered(module: AnsibleModule, connection: Connection) -> dict[str, Any]:
    found = _gathered_raw(module, connection)
    # `gathered` is the standard key, in the form `config` accepts, so it can be
    # applied back as is; an interface the device does not have is left out.
    gathered = [_to_config_entry(name, raw) for name, raw in found if raw is not None]
    # `interfaces` keeps the per-interface result form this state returned up
    # to 1.2.1 and is deprecated.
    interfaces: list[dict[str, Any]] = []
    for name, raw in found:
        state = _to_ansible_state(raw)
        interfaces.append({"name": name, "before": state, "after": state, "differences": [], "changed": False})
    return {"changed": False, "gathered": gathered, "interfaces": interfaces}


def _listed_interfaces(
    all_ifaces: list[dict[str, Any]], exclude: set[tuple[str, str]]
) -> list[tuple[str, str, dict[str, Any]]]:
    """(type, name, settings) of each interface the device lists, minus the *exclude* keys."""
    listed: list[tuple[str, str, dict[str, Any]]] = []
    for item in all_ifaces:
        iface_type = str(item.get("interfaceType") or "PORT").strip().upper()
        iface_name = str(item.get("interfaceName") or "").strip()
        if not iface_name:
            continue
        if (iface_type, iface_name) in exclude:
            continue
        listed.append((iface_type, iface_name, item.get("interfaceSettings") or item))
    return listed


def _reset_interfaces(
    module: AnsibleModule,
    connection: Connection,
    targets: list[tuple[str, str, dict[str, Any]]],
    build: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]],
    lag_modes: dict[str, str],
    writes: _WriteTracker | None,
    *,
    label: str,
    protected: dict[str, str] | None = None,
) -> tuple[bool, list[str], list[dict[str, Any]], list[str]]:
    """Reset each target to the payload *build* returns for its settings.

    Shared by overridden (the interfaces absent from config, to DEFAULTS) and
    deleted without config (every interface, to the deleted payload), so both
    skip the same interfaces: a *protected* one, a LACP/VLACP LAG, and one the
    device rejects. Each skip is warned about. Returns (changed, reset
    interface names, per-interface results, skipped interface names).
    """
    overall_changed = False
    reset_interfaces: list[str] = []
    reset_states: list[dict[str, Any]] = []
    skipped_interfaces: list[str] = []
    for iface_type, iface_name, settings in targets:
        display_name = f"{iface_type}:{iface_name}" if iface_type != "PORT" else iface_name

        guard = (protected or {}).get(display_name)
        if guard:
            module.warn(f"{label}: skipped {display_name} (protected — {guard})")
            skipped_interfaces.append(display_name)
            continue
        reason = _unsupported_reset_reason(iface_type, iface_name, lag_modes)
        if reason:
            module.warn(f"{label}: skipped {display_name} (cannot reset — {reason})")
            skipped_interfaces.append(display_name)
            continue

        payload, comparison = build(settings)
        written = len(writes.done) if writes is not None else 0
        try:
            changed, final_raw = _apply_interface(
                connection,
                iface_type,
                iface_name,
                settings,
                payload,
                comparison,
                check_mode=module.check_mode,
                writes=writes,
            )
        except (ConnectionError, FeL2InterfacesError) as exc:
            # A failure after the device accepted this reset (the read-back or
            # the retry PUT) is not "cannot reset": the interface was modified,
            # so the task fails and reports the change instead of skipping it.
            if writes is not None and len(writes.done) > written:
                raise
            # A PUT without an answer may have reset it: not a skip either.
            if isinstance(exc, FeL2InterfacesError) and exc.changed:
                raise
            # Anything the pre-check could not foresee, such as a protected
            # port, still surfaces here when the device rejects the write.
            module.warn(f"{label}: skipped {display_name} " f"(cannot reset — {exc})")
            skipped_interfaces.append(display_name)
            continue
        if changed:
            overall_changed = True
            reset_interfaces.append(display_name)

        # Recorded whether or not it changed: the task targeted this interface,
        # and the before/after pair is contracted to cover every target.
        before = _to_ansible_state(settings)
        after = _to_ansible_state(final_raw)
        reset_states.append(
            {
                "name": display_name,
                "before": before,
                "after": after,
                "differences": _compute_differences(before, after),
                "changed": changed,
            }
        )
    return overall_changed, reset_interfaces, reset_states, skipped_interfaces


# OpenAPI PortName: 'mgmt' or '<slot>:mgmt' is the out-of-band management port
# ('mgt0' in AP naming).
MGMT_PORT_RE = re.compile(r"^(?:\d{1,3}:)?(?:mgmt|mgt0)$", re.IGNORECASE)


def _mgmt_vlan_members(connection: Connection, lead: str) -> dict[tuple[str, str], Any]:
    """Map (interfaceType, interfaceName) of each management VLAN member to that VLAN's id.

    GET /v0/configuration/vlan, VLANs with isMgmtInterface true, tagged and
    untagged members. Any doubt fails the task: a reset sweep reads this before
    its first write, and must not reset the management path. *lead* opens the
    failure message and says which reset could not be done.
    """
    reason = None
    try:
        data = connection.send_request(None, path=VLAN_PATH, method="GET")
    except ConnectionError as exc:
        reason = to_text(exc)
        data = None
    else:
        embedded = _error_body_text(data)
        if embedded is not None:
            reason = "the device returned an error document (%s)" % embedded
        elif not isinstance(data, list):
            reason = "unexpected response %r" % (data,)
    if reason is not None:
        raise FeL2InterfacesError(
            "%s: reading %s failed (%s). Nothing was changed, because without it the module cannot tell which "
            "interfaces carry the management VLAN." % (lead, VLAN_PATH, reason),
            details={"resource": VLAN_PATH},
        )
    members: dict[tuple[str, str], Any] = {}
    for vlan in data:
        if not isinstance(vlan, dict):
            raise FeL2InterfacesError(
                "%s: %s returned a malformed VLAN entry (%r). Nothing was changed." % (lead, VLAN_PATH, vlan),
                details={"resource": VLAN_PATH},
            )
        if vlan.get("isMgmtInterface") is not True:
            continue
        for key in ("untaggedInterfaces", "taggedInterfaces"):
            value = vlan.get(key)
            if value is None:
                continue
            # Fail closed: a malformed membership could hide a port or LAG that
            # carries the management path.
            valid = isinstance(value, list) and all(
                isinstance(m, dict)
                and str(m.get("interfaceType") or "").strip()
                and str(m.get("interfaceName") or "").strip()
                for m in value
            )
            if not valid:
                raise FeL2InterfacesError(
                    "%s: the %s of management VLAN %s are malformed (%r). Nothing was changed, because the module "
                    "cannot tell which interfaces carry the management VLAN." % (lead, key, vlan.get("id"), value),
                    details={"resource": VLAN_PATH},
                )
            for member in value:
                member_type = str(member["interfaceType"]).strip().upper()
                members.setdefault((member_type, str(member["interfaceName"]).strip()), vlan.get("id"))
    return members


def _protected_interfaces(
    targets: list[tuple[str, str, dict[str, Any]]],
    members: dict[tuple[str, str], Any],
    lags: list[dict[str, Any]],
) -> dict[str, str]:
    """Interfaces a reset sweep must not reset, display name -> reason.

    The out-of-band management port, each PORT or LAG in a management VLAN,
    and the member ports of such a LAG.
    """
    protected: dict[str, str] = {}
    for iface_type, iface_name, _settings in targets:
        if iface_type == "PORT" and MGMT_PORT_RE.match(iface_name):
            protected[iface_name] = "out-of-band management port"
    lag_vlans: dict[str, Any] = {}
    for (member_type, member_name), vlan_id in members.items():
        display = f"{member_type}:{member_name}" if member_type != "PORT" else member_name
        protected.setdefault(display, f"member of management VLAN {vlan_id}")
        if member_type == "LAG":
            lag_vlans[member_name] = vlan_id
    found: set[str] = set()
    for lag in lags:
        lag_id = str(lag.get("lagId", "")).strip()
        if lag_id not in lag_vlans:
            continue
        members_list = lag.get("memberPorts")
        # A missing, non-list or blank-named member list is malformed (an empty
        # list is a memberless LAG): not counted as found, so the check below
        # fails closed instead of leaving the real member ports unprotected.
        if not isinstance(members_list, list) or not all(isinstance(p, str) and p.strip() for p in members_list):
            continue
        found.add(lag_id)
        for port in members_list:
            protected.setdefault(
                str(port).strip(), f"member port of LAG {lag_id}, which is in management VLAN {lag_vlans[lag_id]}"
            )
    # Every LAG the management VLAN references must be in the LAG list, or its
    # member ports would be reset unprotected.
    missing = sorted(set(lag_vlans) - found)
    if missing:
        raise FeL2InterfacesError(
            "The management VLAN references LAG(s) %s, which %s did not return (or returned malformed). "
            "Nothing was changed, because their member ports cannot be protected." % (", ".join(missing), LAG_PATH)
        )
    return protected


def _sweep_protection(
    connection: Connection,
    targets: list[tuple[str, str, dict[str, Any]]],
    build: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]],
    lead: str,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Protected interfaces of a reset sweep, and the LAG records read on the way.

    Shared by overridden and deleted without config, so the two never disagree.
    The VLAN list is read only when at least one target differs from its reset
    target (*build*), and the LAG list only then too, when a target or a
    management VLAN member is a LAG. Both reads happen before the sweep's first
    write; a failed VLAN read fails the task. A sweep with nothing to reset
    sends neither read (an interface at its reset target is not written, so
    the LAG modes are not needed either).
    """
    needs_reset = any(_current_state_key(settings) != build(settings)[1] for _t, _n, settings in targets)
    members = _mgmt_vlan_members(connection, lead) if needs_reset else {}
    mgmt_lags = any(t == "LAG" for t, _n in members)
    need_lags = needs_reset and (any(t == "LAG" for t, _n, _s in targets) or mgmt_lags)
    # Strict when a management-VLAN LAG must be expanded into its member ports.
    lags = get_lag_list(connection, strict=mgmt_lags) if need_lags else []
    return (_protected_interfaces(targets, members, lags) if needs_reset else {}), lags


def _handle_deleted_all(
    module: AnsibleModule, connection: Connection, writes: _WriteTracker | None = None
) -> dict[str, Any]:
    """state=deleted without config: reset every interface, as deleted does for a listed one.

    The protected interfaces (see _sweep_protection) and those overridden
    also skips (LACP/VLACP LAGs, interfaces the device refuses to reset) are
    left alone, with a warning, and listed in skipped_interfaces. Every read
    the protection depends on happens before the first write.
    """
    targets = _listed_interfaces(get_all_interface_settings(connection, strict=True), set())

    def build(settings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return _build_deleted_payload({}, settings)

    protected, lags = _sweep_protection(connection, targets, build, "Cannot reset all interfaces")
    changed, reset_interfaces, reset_states, skipped_interfaces = _reset_interfaces(
        module,
        connection,
        targets,
        build,
        _lag_modes(lags),
        writes,
        label=STATE_DELETED,
        protected=protected,
    )
    return {
        "changed": changed,
        "interfaces": reset_states,
        "reset_interfaces": reset_interfaces,
        "skipped_interfaces": skipped_interfaces,
    }


def _handle_overridden(
    module: AnsibleModule, connection: Connection, writes: _WriteTracker | None = None
) -> dict[str, Any]:
    config = module.params.get("config") or []
    if not config:
        raise FeL2InterfacesError("value of config parameter must not be empty for state overridden")

    check_mode = module.check_mode
    interfaces: list[dict[str, Any]] = []

    # Build set of configured interface keys for comparison.
    config_keys: set[tuple[str, str]] = set()
    for entry in config:
        itype, iname = parse_interface_name(entry["name"])
        config_keys.add((itype, iname))

    # Phase 1: Reset unlisted interfaces to defaults.
    all_ifaces = get_all_interface_settings(connection, strict=True)
    # Build a lookup of existing (type, name) for pre-validation.
    existing_keys: set[tuple[str, str]] = set()
    for item in all_ifaces:
        etype = str(item.get("interfaceType") or "PORT").strip().upper()
        ename = str(item.get("interfaceName") or "").strip()
        if ename:
            existing_keys.add((etype, ename))

    # Pre-validate: all config entries must reference existing interfaces.
    missing = [entry["name"] for entry in config if parse_interface_name(entry["name"]) not in existing_keys]
    if missing:
        raise FeL2InterfacesError(
            f"Interface '{missing[0]}' does not exist on the device"
            if len(missing) == 1
            else "Interfaces %s do not exist on the device" % ", ".join("'%s'" % name for name in missing)
        )

    defaults_payload, defaults_comparison = _build_defaults_payload()

    unlisted = _listed_interfaces(all_ifaces, config_keys)

    def build(_settings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return defaults_payload, defaults_comparison

    # Same protection as deleted without config, classified before the first
    # write; the interfaces named in config are applied as replaced regardless.
    protected, lags = _sweep_protection(
        connection, unlisted, build, "Cannot reset the interfaces absent from 'config' (overridden)"
    )

    overall_changed, reset_interfaces, reset_states, skipped_interfaces = _reset_interfaces(
        module,
        connection,
        unlisted,
        build,
        _lag_modes(lags),
        writes,
        label=STATE_OVERRIDDEN,
        protected=protected,
    )

    # Phase 2: Apply config entries as replaced.
    for entry in config:
        result = _process_config_entry(
            connection,
            entry,
            STATE_OVERRIDDEN,
            check_mode=check_mode,
            warn=module.warn,
            writes=writes,
        )
        if result["changed"]:
            overall_changed = True
        interfaces.append(result)

    # The reset ports go last, so positional access to the config entries is
    # unchanged. They belong here because the task modified them, and it is what
    # puts them into the standard before/after pair and the --diff output.
    interfaces.extend(reset_states)

    return {
        "changed": overall_changed,
        "interfaces": interfaces,
        "reset_interfaces": reset_interfaces,
        "skipped_interfaces": skipped_interfaces,
    }


def _handle_config_states(
    module: AnsibleModule, connection: Connection, state: str, writes: _WriteTracker | None = None
) -> dict[str, Any]:
    """Handle merged, replaced, deleted states."""
    config = module.params.get("config") or []
    if not config:
        raise FeL2InterfacesError(f"value of config parameter must not be empty for state {state}")

    check_mode = module.check_mode
    overall_changed = False
    interfaces: list[dict[str, Any]] = []

    for entry in config:
        result = _process_config_entry(connection, entry, state, check_mode=check_mode, warn=module.warn, writes=writes)
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

    # An interface listed twice would get two PUTs and keep the last one silently.
    seen: set[tuple[str, str]] = set()
    for entry in module.params.get("config") or []:
        try:
            key = parse_interface_name(entry["name"])
        except FeL2InterfacesError as exc:
            module.fail_json(**exc.to_fail_kwargs())
        if key in seen:
            module.fail_json(
                msg="Interface '%s' is listed more than once in 'config'; list each interface once" % entry["name"]
            )
        seen.add(key)

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == STATE_GATHERED:
            result = _handle_gathered(module, connection)
        elif state == STATE_OVERRIDDEN:
            # Every PUT is recorded, so a failure after one of them reports
            # changed=true and names the interfaces written (see _WriteTracker).
            with _WriteTracker() as writes:
                result = _handle_overridden(module, connection, writes)
        elif state == STATE_DELETED and not module.params.get("config"):
            # Without config, deleted resets every interface but the protected ones.
            with _WriteTracker() as writes:
                result = _handle_deleted_all(module, connection, writes)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_DELETED):
            with _WriteTracker() as writes:
                result = _handle_config_states(module, connection, state, writes)
        else:
            raise FeL2InterfacesError(f"Unsupported state '{state}'")
        if state != STATE_GATHERED:
            # Standard top-level snapshots, alongside the per-interface ones.
            # Covers every entry of `interfaces`: those named in `config` and,
            # under `overridden`, each interface absent from `config` that the
            # module was able to reset, changed or not, with its own before and
            # after. Interfaces in `skipped_interfaces` are not covered.
            entries = result.get("interfaces", [])
            result["before"] = [{"name": i["name"], **i["before"]} for i in entries]
            result["after"] = [{"name": i["name"], **i["after"]} for i in entries]

            # Diff mode (--diff): Ansible renders the pair itself. Populated
            # even when nothing changed, so --check --diff can show a play is
            # already converged.
            if module._diff:
                result["diff"] = {
                    "before": result["before"],
                    "after": result["after"],
                }

        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeL2InterfacesError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
