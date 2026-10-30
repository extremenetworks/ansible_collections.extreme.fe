# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage ExtremeNetworks Fabric Engine Layer 3 interfaces.

Module Architecture Overview
============================
This module manages the IPv4 and IPv6 addresses of routed VLAN interfaces
and loopback interfaces on Extreme Fabric Engine switches via the REST
OpenAPI.

REST Endpoints used:
  GET  /v0/configuration/vlan
       -> Every VLAN with its addressList (full discovery, overridden and
          gathered without config)
  GET  /v0/configuration/vlan/{vlan_id}
       -> One VLAN with its addressList (a 404 means the VLAN does not exist)
  PUT  /v0/configuration/vlan/{vlan_id}/address
       -> Replace the complete IP address list of a VLAN
  GET  /v0/configuration/loopback
       -> Every loopback interface that has at least one IP address
  PUT  /v0/configuration/loopback/{id}
       -> Replace the IP address list of a loopback; an empty body ({})
          deletes the loopback IP configuration

Fabric Engine constraints:
  - The address endpoints only support PUT, so every action state is a
    read-modify-write (gathered only reads): read the current address set, fold the user's
    addresses into it according to the state, and PUT the complete list
    back only when it differs.
  - A loopback only exists in the REST model while it has an IP address,
    so a loopback the device does not list is treated as having none.
  - Auto-assigned IPv6 link-local addresses (fe80::/10) are not
    configurable and are left out of every comparison and result.
  - Dynamic, management and BROUTER VLANs cannot be modified; overridden
    skips them with a warning. So is the virtual IST VLAN (vistVlanId of an
    MLAG peer), read from /v0/configuration/mlag/peers.

Code Flow (run_module):
  1. Connect to the switch via httpapi
  2. gathered: read and return the interfaces (no writes)
  3. Otherwise normalise config, read the current addresses, compute the
     final address set per interface, PUT the ones that differ, re-read
     after a real change and return before/after/differences
"""

from __future__ import annotations

DOCUMENTATION = r"""
module: extreme_fe_l3_interfaces
short_description: Manage Layer 3 interfaces on ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
- Configure IPv4 and IPv6 addressing on VLAN and loopback interfaces of ExtremeNetworks Fabric Engine switches
  using the custom C(extreme_fe) HTTPAPI transport.
- Supports declarative merge, replace, override, delete, and gather operations modeled after the Ansible
  C(ios_l3_interfaces) and C(junos_l3_interfaces) modules.
- Updates rely on the Fabric Engine REST resources C(/v0/configuration/vlan/{vlan_id}/address) and
  C(/v0/configuration/loopback/{id}) as defined in C(nos-openapi-09-15-2025.yaml).
author:
- Bjorn Haas (@bhaas_extr)
notes:
- Tested against Fabric Engine Version 9.3.2.
- Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI connection plugin.
- Create VLANs and loopbacks first; this module only manages their IP addresses. A VLAN named in C(config) that
  does not exist fails the task, except with C(deleted), where it is skipped.
- List each interface only once in C(config).
- The switch does not list a loopback that has no IP address, so such a loopback is treated as having none.
- You can move an address from one interface to another in the same task; the module removes it from the old
  interface first.
- To keep your management connection up, C(overridden) and C(deleted) without C(config) skip dynamic, management
  and BROUTER VLANs, and the virtual IST (vIST) VLAN of an MLAG, each with a warning. The switch does not allow the
  vIST VLAN's address to change while the vIST exists, so a task that changes it explicitly fails before changing
  anything.
- C(deleted) without C(config) removes the addresses of every interface except the protected VLANs above.
- If the switch accepts an address change but does not apply it, the task fails and names the interface.
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
    - List of Layer 3 interface definitions to manage.
    - When omitted with C(state=gathered), the module returns all VLANs (including system-protected) and all
      loopbacks that have at least one IP address. The REST API does not list empty loopbacks; use an explicit
      C(config) entry to gather a specific empty loopback.
    - The C(gathered) result of this module can be supplied back as C(config) unchanged. With C(overridden) only an
      unfiltered result (gathered without C(config)) is safe, because C(overridden) clears every interface the list
      leaves out.
    type: list
    elements: dict
    suboptions:
      name:
        description:
        - Interface identifier for readability, such as C(VLAN 20) or C(Loopback 10).
        - When C(type) is not supplied, the module attempts to infer the interface type and identifier from C(name).
        type: str
      type:
        description:
        - Interface type to operate on, C(vlan) or C(loopback). The value is not case-sensitive.
        - When omitted, the type is inferred from C(vlan_id), C(loopback_id) or C(name).
        type: str
      vlan_id:
        description:
        - VLAN identifier for routed VLAN interfaces (SVIs).
        type: int
      loopback_id:
        description:
        - Loopback identifier for Fabric Engine loopback interfaces.
        type: int
      vrf:
        description:
        - Optional VRF name for documentation purposes only; changes are not pushed through this module.
        type: str
      ipv4:
        description:
        - IPv4 addresses to manage on the interface.
        - Accepts CIDR strings (for example C(10.0.1.1/24)) or dictionaries with C(address) and
          C(prefix)/C(mask)/C(mask_length) keys.
        type: list
        elements: raw
      ipv6:
        description:
        - IPv6 addresses to manage on the interface.
        - Accepts CIDR strings or dictionaries with C(address) and C(prefix)/C(mask_length) keys.
        type: list
        elements: raw
  state:
    description:
    - Desired module operation.
    - C(deleted) removes the listed addresses (all addresses when none are listed) from the listed interfaces;
      without C(config) it removes the addresses of every interface.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc:

# =========================================================================
# Full playbook examples with prerequisites:
# To create a complete playbook, uncomment the lines starting with:
#   '# - name:', '# hosts:', '# gather_facts:', '# collections:',
#   '#   - extreme.fe' and '# tasks:'
# After uncommenting, realign indentation to conform to YAML format
# (playbook level at col 0, tasks indented under tasks:)
# =========================================================================
#
# Prerequisites:
#
## Create VLANs (if not already existing)
# vlan create 20 type port-mstprstp 0
# vlan create 200 type port-mstprstp 0
#
## Give VLANs descriptive names
# vlan name 20 "VLAN-20"
# vlan name 200 "VLAN-200"
#
## Create loopback interface 5
# interface loopback 5
#   ip address 1.1.1.5 255.255.255.255
# exit
#
## Enable IP routing (if not already enabled)
# ip routing
#
## Make VLANs IP interfaces (add dummy IPs to enable L3)
# interface vlan 20
#   ip address 10.0.20.1 255.255.255.0
# exit
# interface vlan 200
#   ip address 10.0.200.1 255.255.255.0
# exit
#
## Verify Configuration
# show ip interface
# show ipv6 interface
# show interfaces loopback

# -------------------------------------------------------------------------
# Task 1: Merge IPv4 address on VLAN interface
# Description:
#   - This example demonstrates how to add an IPv4 address to a VLAN
#     interface using the 'merged' state. Existing addresses are preserved.
# -------------------------------------------------------------------------
# - name: "Task 1: Merge IPv4 address on VLAN 20"
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Ensure VLAN 20 has 10.0.1.101/24 configured
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - vlan_id: 20
        name: VLAN 20
        ipv4:
          - address: 10.0.1.101
            prefix: 24
    state: merged

# -------------------------------------------------------------------------
# Task 2: Replace interface addresses with IPv4 and IPv6
# Description:
#   - This example shows how to replace all addresses on a VLAN interface
#     with a new set of IPv4 and IPv6 addresses using 'replaced' state.
# -------------------------------------------------------------------------
# - name: "Task 2: Replace IPv4 and IPv6 addresses on VLAN 200"
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Replace address list
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - vlan_id: 200
        name: VLAN 200
        ipv4:
          - 10.10.200.1/24
        ipv6:
          - 2001:db8:200::1/64
    state: replaced

# -------------------------------------------------------------------------
# Task 3: Delete all addresses from loopback interface
# Description:
#   - This example demonstrates how to remove all IP addresses from a
#     loopback interface using the 'deleted' state.
# -------------------------------------------------------------------------
# - name: "Task 3: Remove all addressing from loopback 5"
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Clear loopback IPs
  extreme.fe.extreme_fe_l3_interfaces:
    config:
      - loopback_id: 5
        name: Loopback 5
    state: deleted

# -------------------------------------------------------------------------
# Task 4: Gather Layer 3 interface configuration
# Description:
#   - This example shows how to collect current Layer 3 interface
#     configuration using 'gathered' state without making changes.
# -------------------------------------------------------------------------
# - name: "Task 4: Gather configured Layer 3 interfaces"
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Collect routed interface addressing
  extreme.fe.extreme_fe_l3_interfaces:
    state: gathered
    config:
      - vlan_id: 20
      - vlan_id: 200
  register: routed_interfaces

# -------------------------------------------------------------------------
# Task 5: Restore gathered Layer 3 interface configuration
# Description:
#   - The 'gathered' result has the form 'config' accepts, so it can be
#     applied back unchanged, for example to restore a saved baseline.
#     Re-applying it to an unchanged device reports no change. Use merged or
#     replaced; use overridden only with an unfiltered gather (no config), as
#     overridden clears every interface the list leaves out.
# -------------------------------------------------------------------------
# - name: "Task 5: Restore the gathered addressing"
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Re-apply the gathered addressing
  extreme.fe.extreme_fe_l3_interfaces:
    config: "{{ routed_interfaces.gathered }}"
    state: replaced
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made.
  returned: always
  type: bool
gathered:
  description:
  - Layer 3 interface configuration gathered from the device, one entry per interface in the form the C(config)
    option accepts, so it can be supplied back as C(config) unchanged. Re-applying it with C(merged) or
    C(replaced) changes nothing. Re-applying it with C(overridden) is safe only for an unfiltered result
    (gathered without C(config)); a filtered result lists only the selected interfaces, and C(overridden)
    clears the addresses of every other unprotected interface.
  - IPv6 addresses are in compressed form, and auto-assigned IPv6 link-local addresses (C(fe80::/10)) are left
    out because they cannot be configured.
  - Without C(config), loopbacks that have no IP address are left out because the REST API does not list them.
  - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
  contains:
    type:
      description: Interface type, C(vlan) or C(loopback).
      type: str
    vlan_id:
      description: VLAN identifier, for a VLAN interface.
      type: int
    loopback_id:
      description: Loopback identifier, for a loopback interface.
      type: int
    name:
      description: Name given in C(config), otherwise the name the device reports, when there is one.
      type: str
    vrf:
      description: VRF the device reports for the interface, when there is one.
      type: str
    ipv4:
      description: IPv4 addresses in CIDR notation.
      type: list
      elements: str
    ipv6:
      description: IPv6 addresses in CIDR notation.
      type: list
      elements: str
  sample:
  - type: vlan
    vlan_id: 20
    name: VLAN 20
    vrf: GlobalRouter
    ipv4:
      - 10.0.1.101/24
    ipv6: []
interfaces:
  description:
  - Final Layer 3 interface configuration after the module ran, the same entries as C(after).
  - For C(state=gathered) the same entries as C(gathered), which is the key to use for that state.
  returned: always
  type: list
  elements: dict
  sample:
  - type: vlan
    vlan_id: 20
    name: VLAN 20
    ipv4:
      - 10.0.1.101/24
    ipv6: []
before:
  description:
  - Configuration of every interface the task targeted before the module ran, in the same form as C(gathered).
    These are the interfaces named in C(config), plus every interface the device lists for C(state=overridden)
    and for C(state=deleted) without C(config).
  - With C(state=deleted), VLANs named in C(config) that do not exist are left out.
  - Returned whether or not anything changed.
  returned: when C(state) is not C(gathered)
  type: list
  elements: dict
after:
  description:
  - Configuration of the same interfaces once the module has run, in the same form as C(before). It is read back
    from the device after a change, and is the predicted state in check mode.
  - Returned whether or not anything changed.
  returned: when C(state) is not C(gathered)
  type: list
  elements: dict
differences:
  description: Per-interface change details with before/after address lists for each modified address family.
  returned: when C(state) is not C(gathered)
  type: list
  elements: dict
"""

from collections.abc import Iterable, Sequence
from ipaddress import IPv4Interface, IPv6Interface, ip_address, ip_network
from typing import Dict, Set, Tuple

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown

# ── Constants ─────────────────────────────────────────────────────────────────

# Suboptions mirror DOCUMENTATION. `type` has no choices so the
# case-insensitive values the module has always accepted (for example
# `VLAN`) keep working; infer_interface() rejects anything else.
ARGUMENT_SPEC = {
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str"},
            "type": {"type": "str"},
            "vlan_id": {"type": "int"},
            "loopback_id": {"type": "int"},
            "vrf": {"type": "str"},
            "ipv4": {"type": "list", "elements": "raw"},
            "ipv6": {"type": "list", "elements": "raw"},
        },
    },
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}

SUPPORTED_TYPES = {"vlan", "loopback"}

# States that change the device; all of them need a non-empty config.
ACTION_STATES = {"merged", "replaced", "overridden", "deleted"}


# ── Response helpers ──────────────────────────────────────────────────────────


def _extract_error_code(payload: object | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        return int(code)
    if isinstance(code, int):
        return code
    return None


def _response_message(payload: dict[str, object]) -> object | None:
    return payload.get("errorMessage") or payload.get("message") or payload.get("detail")


def _is_single_not_found(entry: object) -> bool:
    """True for one error entry that says "not found": code 404, or no code and a not-found message."""
    if not isinstance(entry, dict):
        return False
    code = _extract_error_code(entry)
    if code is not None:
        # An explicit code takes precedence: a 500 whose message says "not
        # found" is an error, not a missing VLAN. The text is only a fallback.
        return code == 404
    message = _response_message(entry)
    return isinstance(message, str) and ("not exist" in message.lower() or "not found" in message.lower())


def _is_not_found_response(payload: object | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if _extract_error_code(payload) is not None:
        return _is_single_not_found(payload)
    # The status can be nested under errors (a list) or error (an object or a
    # list): the response means "missing" only when EVERY nested entry is a
    # confirmed not-found; a mixed list is an error.
    nested = payload.get("errors") if isinstance(payload.get("errors"), list) else payload.get("error")
    if isinstance(nested, dict):
        nested = [nested]
    if isinstance(nested, list) and nested:
        return all(_is_single_not_found(entry) for entry in nested)
    return _is_single_not_found(payload)


def _is_error_response(payload: object | None) -> bool:
    """Return True when a (2xx) response carries an error document.

    Only an explicit error marker counts: an HTTP-style code of 400 or
    more, a non-numeric ``errorCode``, a non-empty ``errors`` list, or a
    non-empty singular ``error`` value (both forms occur on Fabric Engine).
    A normal VLAN or loopback document carries none of these keys.
    """
    if not isinstance(payload, dict):
        return False
    code = _extract_error_code(payload)
    if code is not None and code >= 400:
        return True
    error_code = payload.get("errorCode")
    if isinstance(error_code, str) and error_code.strip() and not error_code.isdigit():
        return True
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return True
    return bool(payload.get("error"))


def _error_text(payload: object | None) -> str:
    """Return ': <device message>' for an error document, or ''."""
    if not isinstance(payload, dict):
        return ""
    message = _response_message(payload)
    if not message and isinstance(payload.get("errors"), list) and payload["errors"]:
        message = f"{len(payload['errors'])} error(s) reported: {payload['errors']}"
    if not message and payload.get("error"):
        message = to_text(payload["error"])
    return f": {message}" if message else ""


def _inventory_id(item: object, keys: tuple[str, ...], label: str) -> int:
    """The numeric id of an inventory entry, or ExtremeFeL3InterfacesError naming the entry."""
    raw = None
    if isinstance(item, dict):
        raw = next((item[key] for key in keys if item.get(key) is not None), None)
    try:
        if isinstance(raw, bool):
            raise ValueError(raw)
        return int(raw)
    except (TypeError, ValueError):
        raise ExtremeFeL3InterfacesError(
            f"Unexpected entry in the {label} inventory (missing or non-numeric id)",
            details={"entry": item},
        ) from None


def _vlan_protected_reason(vlan_data: dict[str, object]) -> str | None:
    """Return a human-readable reason if the VLAN is system-protected, else None."""
    if vlan_data.get("dynamic") is True:
        return "dynamic VLAN"
    if vlan_data.get("isMgmtInterface") is True:
        return "management VLAN"
    vlan_type = (vlan_data.get("vlanType") or "").upper()
    if vlan_type == "BROUTER":
        return "BROUTER VLAN"
    return None


MLAG_PEERS_PATH = "/v0/configuration/mlag/peers"
VIST_REASON = "virtual IST VLAN"


def _fetch_vist_vlans(connection: Connection) -> dict[int, object]:
    """Map each virtual IST VLAN (vistVlanId of an MLAG peer) to its peer id.

    Fabric Engine does not allow the address of the vIST VLAN to change while
    the vIST exists, yet answers the address PUT with 204 and keeps the address.
    Only an answer that means "no MLAG peer" counts as no vIST: HTTP
    404, an empty body, a not-found document or an empty list. Any other error
    or shape fails the task; the read runs before the first write, so nothing
    is changed then.
    """
    try:
        data = connection.send_request(None, path=MLAG_PEERS_PATH, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return {}
        raise ExtremeFeL3InterfacesError(
            "Reading the MLAG peers (%s) to identify the virtual IST VLAN failed: %s" % (MLAG_PEERS_PATH, to_text(exc)),
            extra={"code": getattr(exc, "code", None)},
        ) from exc
    if data in (None, "") or _is_not_found_response(data):
        return {}
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            "Reading the MLAG peers (%s) to identify the virtual IST VLAN failed%s"
            % (MLAG_PEERS_PATH, _error_text(data)),
            details={"response": data},
        )
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ExtremeFeL3InterfacesError(
            "Unexpected response when reading the MLAG peers (%s) to identify the virtual IST VLAN" % MLAG_PEERS_PATH,
            details={"response": data},
        )
    vist: dict[int, object] = {}
    for peer in data:
        # A 2xx list can carry an error document as one of its rows, with or
        # without a code ({"errorMessage": "Permission denied"}); it must not
        # read as "a peer without a vIST" and let the writes go ahead. Every
        # row has to be a peer (peerId), as in the lag module's protection read.
        peer_id = peer.get("peerId")
        is_peer = peer_id is not None and not isinstance(peer_id, (dict, list)) and str(peer_id).strip() != ""
        if _is_error_response(peer) or not is_peer:
            reason = _error_text(peer) or ": an entry without peerId"
            raise ExtremeFeL3InterfacesError(
                "Reading the MLAG peers (%s) to identify the virtual IST VLAN failed%s" % (MLAG_PEERS_PATH, reason),
                details={"response": data},
            )
        raw = peer.get("vistVlanId")
        if raw in (None, "", 0, "0"):
            continue
        try:
            vist[int(str(raw).strip())] = peer.get("peerId")
        except ValueError:
            raise ExtremeFeL3InterfacesError(
                "Unexpected vistVlanId %r in the MLAG peers (%s)" % (raw, MLAG_PEERS_PATH),
                details={"response": data},
            ) from None
    return vist


class ExtremeFeL3InterfacesError(Exception):
    """Base exception for the L3 interface module."""

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
        # Extra top-level fail_json keys, e.g. the 'code' of a wrapped ConnectionError.
        self.extra = extra or {}
        # True when the failure follows a successful write of the same task
        # (see _WriteTracker); None keeps the default fail result.
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
    """Remember which interfaces this task already wrote.

    Used as a context manager around the write phase. Once a PUT has
    succeeded, a later failure (another PUT or the read-back) must not hide
    that change: it is re-raised with changed=true and its message names the
    interfaces already written. Before the first write, failures pass
    through untouched.
    """

    def __init__(self) -> None:
        self.done: list[str] = []

    def record(self, what: str) -> None:
        if what not in self.done:
            self.done.append(what)

    def __enter__(self) -> _WriteTracker:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        # Any ordinary exception after a successful write - a ConnectionError, a
        # module error, or an unexpected one such as a ValueError while parsing a
        # read-back - must report the change (BaseException-only exits such as
        # SystemExit pass through).
        if exc is None or not self.done or not isinstance(exc, Exception):
            return False
        message = to_text(exc).rstrip()
        if message and not message.endswith("."):
            message += "."
        written = ", ".join(self.done)
        message = f"{message} The task had already changed the device before this failure: wrote {written}."
        if isinstance(exc, ExtremeFeL3InterfacesError):
            raise ExtremeFeL3InterfacesError(
                message.strip(), details=exc.details, extra=exc.extra, changed=True
            ) from exc
        raise ExtremeFeL3InterfacesError(
            message.strip(), extra={"code": getattr(exc, "code", None)}, changed=True
        ) from exc


class InterfaceId:
    """Represents a normalized interface identifier."""

    def __init__(
        self,
        if_type: str,
        identifier: int,
        name: str | None = None,
        vrf: str | None = None,
    ) -> None:
        self.type = if_type
        self.identifier = identifier
        self.name = name
        self.vrf = vrf

    def key(self) -> tuple[str, int]:
        return self.type, self.identifier

    def label(self) -> str:
        return f"{'VLAN' if self.type == 'vlan' else 'loopback'} {self.identifier}"

    def to_result_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"type": self.type}
        if self.type == "vlan":
            data["vlan_id"] = self.identifier
        elif self.type == "loopback":
            data["loopback_id"] = self.identifier
        if self.name:
            data["name"] = self.name
        if self.vrf:
            data["vrf"] = self.vrf
        return data


# ── Address normalisation ─────────────────────────────────────────────────────


def dotted_netmask_to_prefix(mask: str) -> int:
    try:
        network = ip_network(f"0.0.0.0/{mask}")
    except ValueError as exc:
        raise ExtremeFeL3InterfacesError(f"Invalid IPv4 netmask '{mask}'") from exc
    return int(network.prefixlen)


def _prefix_from_dict(value: dict[str, object]) -> object | None:
    """Return the prefix length given by the prefix/mask_length/maskLength keys."""
    for key in ("prefix", "mask_length", "maskLength"):
        if key in value and value[key] is not None:
            return value[key]
    return None


def _to_prefixlen(prefix: object, addr: object, family: str) -> int:
    try:
        return int(prefix)
    except (TypeError, ValueError) as exc:
        raise ExtremeFeL3InterfacesError(f"Invalid {family} interface '{addr}/{prefix}'") from exc


def normalize_ipv4_entry(value: object) -> tuple[str, str, int]:
    if isinstance(value, str):
        data = value.strip()
        if "/" not in data:
            raise ExtremeFeL3InterfacesError(f"IPv4 address '{value}' must include prefix length")
        addr, prefix = data.split("/", 1)
        prefixlen = _to_prefixlen(prefix, addr, "IPv4")
    elif isinstance(value, dict):
        addr = value.get("address") or value.get("addr")
        if not addr:
            raise ExtremeFeL3InterfacesError("IPv4 address dictionary must include 'address'")
        prefix = _prefix_from_dict(value)
        if prefix is not None:
            prefixlen = _to_prefixlen(prefix, addr, "IPv4")
        elif value.get("mask"):
            prefixlen = dotted_netmask_to_prefix(str(value["mask"]))
        else:
            raise ExtremeFeL3InterfacesError("IPv4 address dictionary must include prefix or mask")
    else:
        raise ExtremeFeL3InterfacesError(f"Unsupported IPv4 address type: {type(value).__name__}")

    try:
        iface = IPv4Interface(f"{addr}/{prefixlen}")
    except ValueError as exc:
        raise ExtremeFeL3InterfacesError(f"Invalid IPv4 interface '{addr}/{prefixlen}'") from exc
    return "ipv4", str(iface.ip), int(iface.network.prefixlen)


def normalize_ipv6_entry(value: object) -> tuple[str, str, int]:
    if isinstance(value, str):
        data = value.strip()
        if "/" not in data:
            raise ExtremeFeL3InterfacesError(f"IPv6 address '{value}' must include prefix length")
        addr, prefix = data.split("/", 1)
        prefixlen = _to_prefixlen(prefix, addr, "IPv6")
    elif isinstance(value, dict):
        addr = value.get("address") or value.get("addr")
        if not addr:
            raise ExtremeFeL3InterfacesError("IPv6 address dictionary must include 'address'")
        prefix = _prefix_from_dict(value)
        if prefix is None:
            raise ExtremeFeL3InterfacesError("IPv6 address dictionary must include prefix")
        prefixlen = _to_prefixlen(prefix, addr, "IPv6")
    else:
        raise ExtremeFeL3InterfacesError(f"Unsupported IPv6 address type: {type(value).__name__}")

    try:
        iface = IPv6Interface(f"{addr}/{prefixlen}")
    except ValueError as exc:
        raise ExtremeFeL3InterfacesError(f"Invalid IPv6 interface '{addr}/{prefixlen}'") from exc
    return "ipv6", str(iface.ip), int(iface.network.prefixlen)


def normalize_interface_addresses(entry: dict[str, object]) -> set[str]:
    addresses: set[str] = set()
    for item in entry.get("ipv4") or []:
        family, addr, prefix = normalize_ipv4_entry(item)
        addresses.add(f"{family}:{addr}/{prefix}")
    for item in entry.get("ipv6") or []:
        family, addr, prefix = normalize_ipv6_entry(item)
        addresses.add(f"{family}:{addr}/{prefix}")
    return addresses


def set_from_payload(address_list: Iterable[object], *, is_vlan: bool) -> set[str]:
    results: set[str] = set()
    for item in address_list or []:
        payload = item
        if is_vlan:
            if not isinstance(item, dict):
                continue
            payload = item.get("address")
        if not isinstance(payload, dict):
            continue
        ip_type = payload.get("ipAddressType") or payload.get("ip_type")
        address = payload.get("address")
        mask = payload.get("maskLength") or payload.get("mask_length")
        if not ip_type or not address or mask is None:
            continue
        if ip_type == "IPv4":
            family = "ipv4"
        elif ip_type == "IPv6":
            family = "ipv6"
            # Filter out auto-assigned IPv6 link-local addresses
            # (fe80::/10).  These are system-managed and cannot be
            # configured via the REST API.
            try:
                if ip_address(address).is_link_local:
                    continue
            except ValueError:
                pass
        else:
            continue
        # Normalize IPv6 addresses to compressed canonical form
        # so they match what normalize_ipv6_entry() produces.
        # The device returns expanded form (e.g. 2001:db8:862:0:0:0:0:1)
        # while user input normalizes to compressed (2001:db8:862::1).
        prefix = int(mask)
        if family == "ipv6":
            try:
                address = str(IPv6Interface(f"{address}/{prefix}").ip)
            except ValueError:
                pass
        results.add(f"{family}:{address}/{prefix}")
    return results


def addresses_to_payload(addresses: set[str], *, is_vlan: bool) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for entry in sorted(addresses):
        family, value = entry.split(":", 1)
        addr, prefix = value.split("/", 1)
        base = {
            "ipAddressType": "IPv4" if family == "ipv4" else "IPv6",
            "address": addr,
            "maskLength": int(prefix),
        }
        if is_vlan:
            payload.append({"address": base})
        else:
            payload.append(base)
    return payload


# ── Interface identification ──────────────────────────────────────────────────


def _id_from_name(name: str, message: str) -> int:
    """Return the number after the interface word in ``name`` (``VLAN 20`` -> 20)."""
    try:
        return int(name.split()[1])
    except Exception as exc:
        raise ExtremeFeL3InterfacesError(message) from exc


def _typed_interface(if_type: str, entry: dict[str, object]) -> InterfaceId:
    """Build the interface of a known type, taking the id from config or name."""
    name = entry.get("name")
    id_key = "vlan_id" if if_type == "vlan" else "loopback_id"
    label = "VLAN" if if_type == "vlan" else "loopback"
    identifier = entry.get(id_key)
    if identifier is None:
        if name and name.lower().startswith(if_type):
            identifier = _id_from_name(name, f"Unable to infer {label} identifier from name; specify '{id_key}'")
        else:
            raise ExtremeFeL3InterfacesError(f"'{id_key}' is required for {label} interfaces")
    return InterfaceId(if_type, int(identifier), name=name, vrf=entry.get("vrf"))


def _interface_from_name(entry: dict[str, object]) -> InterfaceId:
    """Infer type and id from a name such as ``VLAN 20`` or ``Loopback 10``."""
    name = entry.get("name")
    if name:
        lower = name.lower()
        for if_type, id_key, label in (("vlan", "vlan_id", "VLAN"), ("loopback", "loopback_id", "loopback")):
            if lower.startswith(if_type) and len(lower.split()) >= 2:
                identifier = _id_from_name(
                    lower, f"Unable to infer {label} identifier from name; specify 'type' and '{id_key}'"
                )
                return InterfaceId(if_type, identifier, name=name, vrf=entry.get("vrf"))
    raise ExtremeFeL3InterfacesError("Unable to determine interface type; specify 'type'")


def infer_interface(entry: dict[str, object]) -> InterfaceId:
    if_type = entry.get("type")
    if if_type:
        if_type = str(if_type).strip().lower()
        if if_type not in SUPPORTED_TYPES:
            raise ExtremeFeL3InterfacesError(f"Unsupported interface type '{if_type}'")
    if if_type == "vlan" or (if_type is None and entry.get("vlan_id") is not None):
        return _typed_interface("vlan", entry)
    if if_type == "loopback" or (if_type is None and entry.get("loopback_id") is not None):
        return _typed_interface("loopback", entry)
    return _interface_from_name(entry)


# ── REST access ───────────────────────────────────────────────────────────────


def vlan_path(vlan_id: int) -> str:
    return f"/v0/configuration/vlan/{vlan_id}"


def vlan_address_path(vlan_id: int) -> str:
    return f"/v0/configuration/vlan/{vlan_id}/address"


def loopback_path(loopback_id: int) -> str:
    return f"/v0/configuration/loopback/{loopback_id}"


def get_vlan_info(connection: Connection, vlan_id: int) -> dict[str, object] | None:
    # GET /v0/configuration/vlan/{vlan_id}; None when the VLAN does not exist.
    try:
        data = connection.send_request(None, path=vlan_path(vlan_id), method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if _is_not_found_response(data):
        return None
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            f"Failed to retrieve VLAN {vlan_id} details{_error_text(data)}",
            details={"response": data},
        )
    if isinstance(data, dict) and data:
        return data
    # Only a 404 or a not-found document means the VLAN does not exist; an
    # empty or unexpected answer is a failed read, so state=deleted never
    # mistakes it for a missing VLAN and skips it.
    raise ExtremeFeL3InterfacesError(
        f"Unexpected response when retrieving VLAN {vlan_id} details",
        details={"response": data},
    )


def put_vlan_addresses(connection: Connection, vlan_id: int, addresses: set[str]) -> None:
    # PUT /v0/configuration/vlan/{vlan_id}/address replaces the whole list.
    payload = {"addressList": addresses_to_payload(addresses, is_vlan=True)}
    data = connection.send_request(payload, path=vlan_address_path(vlan_id), method="PUT")
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            f"Failed to update VLAN {vlan_id} addressing{_error_text(data)}",
            details={"response": data},
        )


def get_loopbacks(connection: Connection) -> list[dict[str, object]]:
    # GET /v0/configuration/loopback lists only loopbacks with an IP address.
    try:
        data = connection.send_request(None, path="/v0/configuration/loopback", method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            f"Failed to retrieve loopback interfaces{_error_text(data)}",
            details={"response": data},
        )
    # Fail closed: delete-all and overridden act on this inventory, so only a
    # list (or a 404 above) is accepted - an empty or malformed answer must not
    # read as "no loopbacks" and leave their addresses untouched.
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ExtremeFeL3InterfacesError(
            "Unexpected response when retrieving loopback interfaces",
            details={"response": data},
        )
    # Every entry needs a numeric id: an {} entry must not become loopback -1.
    for item in data:
        _inventory_id(item, ("id",), "loopback")
    return list(data)


def get_loopback_info(
    loopbacks: Sequence[dict[str, object]],
    loopback_id: int,
) -> dict[str, object] | None:
    for item in loopbacks:
        if _inventory_id(item, ("id",), "loopback") == loopback_id:
            return item
    return None


def put_loopback_addresses(connection: Connection, loopback_id: int, addresses: set[str]) -> None:
    # Per the OpenAPI spec: "An empty request means that IP address configuration
    # will be deleted for that loopback interface."
    # When the address set is empty, send {} instead of {"ipAddressList": []}
    # to properly delete the loopback interface.
    if not addresses:
        payload: dict[str, object] = {}
    else:
        payload = {"ipAddressList": addresses_to_payload(addresses, is_vlan=False)}
    data = connection.send_request(payload, path=loopback_path(loopback_id), method="PUT")
    if _is_error_response(data):
        raise ExtremeFeL3InterfacesError(
            f"Failed to update loopback {loopback_id} addressing{_error_text(data)}",
            details={"response": data},
        )


def build_result_entry(interface: InterfaceId, addresses: set[str]) -> dict[str, object]:
    """Return one interface in the form the config option accepts."""
    data = interface.to_result_dict()
    ipv4_list: list[str] = []
    ipv6_list: list[str] = []
    for entry in sorted(addresses):
        family, value = entry.split(":", 1)
        if family == "ipv4":
            ipv4_list.append(value)
        else:
            ipv6_list.append(value)
    data["ipv4"] = ipv4_list
    data["ipv6"] = ipv6_list
    return data


# ── Gathering ─────────────────────────────────────────────────────────────────

# (type, id) -> (interface, normalised address set). typing aliases keep the
# runtime expression valid on every Python version modules run on.
InterfaceMap = Dict[Tuple[str, int], Tuple[InterfaceId, Set[str]]]


def _gather_vlan_targets(
    connection: Connection,
    targets: list[InterfaceId],
    results: InterfaceMap,
    skip_missing: bool,
) -> None:
    """Read each requested VLAN with GET /v0/configuration/vlan/{vlan_id}."""
    for target in targets:
        info = get_vlan_info(connection, target.identifier)
        if info is None:
            # state=deleted: nothing to delete on a VLAN that does not exist.
            if skip_missing:
                continue
            raise ExtremeFeL3InterfacesError(f"VLAN {target.identifier} does not exist")
        address_set = set_from_payload(info.get("addressList", []), is_vlan=True)
        iface = InterfaceId(
            "vlan",
            target.identifier,
            name=target.name or info.get("name"),
            vrf=info.get("vrName"),
        )
        results[iface.key()] = (iface, address_set)


def _gather_vlan_inventory(
    connection: Connection,
    results: InterfaceMap,
    protected_vlans: dict[tuple[str, int], str] | None,
) -> None:
    """Discover every VLAN with GET /v0/configuration/vlan."""
    try:
        vlan_list = connection.send_request(None, path="/v0/configuration/vlan", method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            vlan_list = []
        else:
            raise
    if _is_error_response(vlan_list):
        raise ExtremeFeL3InterfacesError(
            f"Failed to retrieve VLAN inventory{_error_text(vlan_list)}",
            details={"response": vlan_list},
        )
    # Fail closed, as for the loopbacks: only a list of VLAN documents (or a
    # 404 above) is a trustworthy inventory for delete-all and overridden.
    if not isinstance(vlan_list, list):
        raise ExtremeFeL3InterfacesError(
            "Unexpected response when retrieving the VLAN inventory",
            details={"response": vlan_list},
        )
    for item in vlan_list:
        vlan_id = _inventory_id(item, ("vlanId", "vlan_id", "id"), "VLAN")
        iface = InterfaceId(
            "vlan",
            vlan_id,
            name=item.get("name"),
            vrf=item.get("vrName"),
        )
        # Track system-protected VLANs (dynamic, management,
        # BROUTER) so the overridden state can skip them.
        if protected_vlans is not None:
            reason = _vlan_protected_reason(item)
            if reason:
                protected_vlans[iface.key()] = reason
        address_set = set_from_payload(item.get("addressList", []), is_vlan=True)
        results[iface.key()] = (iface, address_set)


def gather_all(
    connection: Connection,
    *,
    filter_map: dict[tuple[str, int], InterfaceId] | None = None,
    protected_vlans: dict[tuple[str, int], str] | None = None,
    skip_missing: bool = False,
) -> InterfaceMap:
    """Gather L3 addressing for all (or filtered) interfaces.

    When *protected_vlans* is a dict, it is populated with
    ``{(type, id): reason}`` entries for each system-protected
    VLAN encountered during full discovery (filter_map=None).
    With *skip_missing*, a VLAN of *filter_map* that does not exist is
    left out instead of failing (state=deleted).
    """
    results: InterfaceMap = {}

    # Gather VLAN addressing: one GET per requested VLAN, or full discovery.
    if filter_map is None:
        _gather_vlan_inventory(connection, results, protected_vlans)
    else:
        targets = [value for value in filter_map.values() if value.type == "vlan"]
        _gather_vlan_targets(connection, targets, results, skip_missing)

    # Gather loopback addressing
    if filter_map is None or any(key[0] == "loopback" for key in filter_map):
        loopbacks = get_loopbacks(connection)
        for item in loopbacks:
            loopback_id = _inventory_id(item, ("id",), "loopback")
            iface = InterfaceId("loopback", loopback_id, name=item.get("name"), vrf=item.get("vrName"))
            address_set = set_from_payload(item.get("ipAddressList", []), is_vlan=False)
            if filter_map is not None and iface.key() not in filter_map:
                continue
            results[iface.key()] = (iface, address_set)

    return results


def gather_selected(
    connection: Connection,
    interfaces: list[InterfaceId],
    *,
    skip_missing: bool = False,
) -> InterfaceMap:
    """Gather the named interfaces; see gather_all() for *skip_missing*."""
    mapping: dict[tuple[str, int], InterfaceId] = {item.key(): item for item in interfaces}
    gathered = gather_all(connection, filter_map=mapping, skip_missing=skip_missing)
    # Ensure every requested interface has an entry.  Loopbacks
    # with no IP addresses are omitted by the REST API, so they
    # may be missing from the gather results.
    _loopback_cache: list[dict[str, object]] | None = None
    for iface in interfaces:
        key = iface.key()
        if key in gathered:
            continue
        if iface.type == "vlan":
            # gather_all() already found this VLAN missing and skipped it.
            if skip_missing:
                continue
            info = get_vlan_info(connection, iface.identifier)
            if info is None:
                raise ExtremeFeL3InterfacesError(f"VLAN {iface.identifier} does not exist")
            derived = InterfaceId(
                "vlan",
                iface.identifier,
                name=iface.name or info.get("name"),
                vrf=info.get("vrName"),
            )
            addresses = set_from_payload(info.get("addressList", []), is_vlan=True)
            gathered[key] = (derived, addresses)
        elif iface.type == "loopback":
            if _loopback_cache is None:
                _loopback_cache = get_loopbacks(connection)
            item = get_loopback_info(_loopback_cache, iface.identifier)
            if item is None:
                # The REST API omits loopbacks that have no IP
                # addresses (in Fabric Engine, a loopback only exists as a
                # row in rcIpAddrTbl).  Treat as existing with an
                # empty address set - the subsequent PUT will
                # create the entry if needed.
                derived = InterfaceId(
                    "loopback",
                    iface.identifier,
                    name=iface.name,
                    vrf=iface.vrf,
                )
                addresses: set[str] = set()
            else:
                derived = InterfaceId(
                    "loopback",
                    iface.identifier,
                    name=iface.name or item.get("name"),
                    vrf=item.get("vrName"),
                )
                addresses = set_from_payload(item.get("ipAddressList", []), is_vlan=False)
            gathered[key] = (derived, addresses)
    return gathered


# ── Desired state ─────────────────────────────────────────────────────────────


def compute_final_sets(
    state: str,
    config_map: InterfaceMap,
    existing_map: InterfaceMap,
) -> InterfaceMap:
    """Return the final address set per interface for *state*.

    The identity (name, VRF) of an interface the device already reported
    is kept from *existing_map*, so a check-mode or no-op ``after`` matches
    what a re-read returns.
    """
    final: InterfaceMap = {}

    def identity(key: tuple[str, int], fallback: InterfaceId) -> InterfaceId:
        current = existing_map.get(key)
        return current[0] if current else fallback

    if state == "overridden":
        # All existing interfaces not in config are cleared
        for key, (iface, current) in existing_map.items():
            desired = config_map.get(key)
            final[key] = (iface, set(desired[1]) if desired else set())
        # Ensure config entries not in existing are included
        for key, value in config_map.items():
            if key not in final:
                final[key] = (value[0], set(value[1]))
        return final

    for key, value in config_map.items():
        current = existing_map.get(key)
        current_set = set(current[1]) if current else set()
        if state == "replaced":
            desired_set = set(value[1])
        elif state == "merged":
            desired_set = current_set | set(value[1])
        elif state == "deleted":
            # Listed addresses are removed; no addresses means remove all.
            desired_set = current_set - set(value[1]) if value[1] else set()
        else:
            return {}
        final[key] = (identity(key, value[0]), desired_set)
    return final


# ── State handlers ────────────────────────────────────────────────────────────


def _handle_gathered(connection: Connection, config: list[dict[str, object]]) -> dict[str, object]:
    """Read-only: return the interfaces in the form config accepts."""
    if config:
        gathered = gather_selected(connection, [infer_interface(item) for item in config])
    else:
        gathered = gather_all(connection)
    result_list = [build_result_entry(iface, addresses) for iface, addresses in gathered.values()]
    # `interfaces` is the key used up to 1.2.1 and is kept for compatibility.
    return {"changed": False, "gathered": result_list, "interfaces": list(result_list)}


def _build_config_map(config: list[dict[str, object]]) -> InterfaceMap:
    config_map: InterfaceMap = {}
    for item in config:
        iface = infer_interface(item)
        if iface.key() in config_map:
            # Listed twice: one entry would be kept silently.
            raise ExtremeFeL3InterfacesError(
                "Interface %s is listed more than once in config; list each interface once" % iface.label()
            )
        config_map[iface.key()] = (iface, normalize_interface_addresses(item))
    return config_map


def _gather_existing(
    connection: Connection,
    state: str,
    config_map: InterfaceMap,
    protected: dict[tuple[str, int], str],
) -> InterfaceMap:
    """Read the current addresses of the interfaces *state* touches."""
    if state != "overridden":
        return gather_selected(
            connection,
            [value[0] for value in config_map.values()],
            skip_missing=state == "deleted",
        )
    existing = gather_all(connection, protected_vlans=protected)
    for key, (iface, _addresses) in config_map.items():
        if key not in existing:
            if iface.type == "vlan":
                raise ExtremeFeL3InterfacesError(f"VLAN {iface.identifier} does not exist")
            if iface.type == "loopback":
                # The REST API omits loopbacks with no IP
                # addresses - treat as existing with empty
                # set so the PUT can assign addresses.
                existing[key] = (iface, set())
    return existing


def _apply_changes(
    module: AnsibleModule,
    connection: Connection,
    final_sets: InterfaceMap,
    existing: InterfaceMap,
    protected: dict[tuple[str, int], str],
    writes: _WriteTracker,
    listed: set[tuple[str, int]],
    sweep: bool,
) -> tuple[InterfaceMap, list[tuple[str, int]], list[str]]:
    """PUT every interface whose address set differs (not in check mode).

    An address moved from one interface to another in the same task must
    leave its old interface first, or the device rejects the addition as a
    duplicate. See _write_in_order().

    The virtual IST VLAN is skipped like the other protected VLANs
    when a sweep (*sweep*: overridden, deleted without config) would change it
    without the task listing it (*listed*); a change the task asks for
    explicitly fails before any write, also in check mode.

    Returns the projected interface map, the changed keys and warnings.
    """
    results: InterfaceMap = {}
    changed_keys: list[tuple[str, int]] = []
    warnings: list[str] = []
    pending: list[tuple[InterfaceId, set[str], set[str]]] = []
    vist: dict[int, object] | None = None
    for key, (iface, desired_set) in final_sets.items():
        current_set = existing.get(key, (iface, set()))[1]
        if desired_set != current_set:
            # Skip system-protected VLANs during overridden / delete-all
            # - these cannot be modified via REST.
            if key in protected:
                warnings.append(f"Skipping VLAN {iface.identifier}: {protected[key]} — cannot be modified")
                results[key] = (iface, current_set)
                continue
            if iface.type == "vlan":
                if vist is None:
                    # Read once, and only when a VLAN is about to be written.
                    vist = _fetch_vist_vlans(connection)
                if iface.identifier in vist:
                    if sweep and key not in listed:
                        warnings.append(f"Skipping VLAN {iface.identifier}: {VIST_REASON} — cannot be modified")
                        results[key] = (iface, current_set)
                        continue
                    raise ExtremeFeL3InterfacesError(
                        f"VLAN {iface.identifier} is the virtual IST VLAN (MLAG peer {vist[iface.identifier]}): "
                        "Fabric Engine does not allow its IP address to change while the virtual IST exists",
                        details={"interface": iface.label(), "mlag_peer": vist[iface.identifier]},
                    )
            changed_keys.append(key)
            pending.append((iface, current_set, desired_set))
        results[key] = (iface, desired_set)
    if not module.check_mode:
        _write_in_order(connection, pending, writes)
    return results, changed_keys, warnings


def _ip_of(entry: str) -> str:
    """The family and address of an ``ipv4:10.0.0.1/24`` entry, without its prefix length."""
    return entry.split("/", 1)[0]


def _write_in_order(
    connection: Connection, pending: list[tuple[InterfaceId, set[str], set[str]]], writes: _WriteTracker
) -> None:
    """Write the pending (iface, current, desired) changes so moved addresses never collide.

    A moved address is one an interface adds while a DIFFERENT pending
    interface currently holds and drops it. A prefix-only change on one
    interface (10.0.0.1/24 -> /25) is not a move. Every interface that releases a moved
    address is written first: with its final set when it gains nothing, or
    with what it keeps (current & desired) when it also gains an address,
    in which case its final set follows with the others. Every other
    interface gets a single PUT of its final set, in the original order, so a
    change confined to one interface never passes through a reduced set.
    """
    adders: dict[str, set[int]] = {}
    for index, (_iface, current, desired) in enumerate(pending):
        for entry in desired - current:
            adders.setdefault(_ip_of(entry), set()).add(index)
    done: set[int] = set()
    for index, (iface, current, desired) in enumerate(pending):
        released = {_ip_of(e) for e in current - desired}
        # Released here and added by another interface of the task.
        if not any(adders.get(ip, set()) - {index} for ip in released):
            continue
        if desired - current:
            _put_addresses(connection, iface, current & desired, writes)
        else:
            _put_addresses(connection, iface, desired, writes)
            done.add(index)
    for index, (iface, _current, desired) in enumerate(pending):
        if index not in done:
            _put_addresses(connection, iface, desired, writes)


def _put_addresses(connection: Connection, iface: InterfaceId, addresses: set[str], writes: _WriteTracker) -> None:
    """PUT one interface's address set and record the write.

    A PUT without an answer (a lost connection) may have been applied, so it
    fails with changed=true and details.outcome unknown.
    """
    try:
        if iface.type == "vlan":
            put_vlan_addresses(connection, iface.identifier, addresses)
        elif iface.type == "loopback":
            put_loopback_addresses(connection, iface.identifier, addresses)
    except ConnectionError as exc:
        # Only an HTTP status (100-599) is a refusal; no code, or a negative
        # JSON-RPC code of the persistent connection, means no answer.
        if not answer_unknown(exc):
            raise
        raise ExtremeFeL3InterfacesError(
            "%s. The address PUT of %s may have been applied before the answer was lost; check it on the device."
            % (to_text(exc).rstrip("."), iface.label()),
            details={"outcome": "unknown", "interface": iface.label()},
            extra={"code": None},
            changed=True,
        ) from exc
    writes.record(iface.label())


def _capture_after_state(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    config_map: InterfaceMap,
    existing: InterfaceMap,
    results: InterfaceMap,
    changed_keys: list[tuple[str, int]],
) -> InterfaceMap:
    """Re-read the device after a real change; project locally otherwise."""
    after_map = existing.copy()
    if not changed_keys or module.check_mode:
        # No change or check_mode - project locally.
        after_map.update(results)
        return after_map
    # Re-gather from device to confirm actual state.
    if state == "overridden":
        refreshed = gather_all(connection)
    else:
        refreshed = gather_selected(
            connection,
            [value[0] for value in config_map.values()],
            skip_missing=state == "deleted",
        )
    after_map.update(refreshed)
    # Interfaces that were changed but are absent from
    # refreshed had their addresses cleared (e.g. loopback
    # removed from rcIpAddrTbl).  Set them to empty so
    # after/differences reflect the actual device state.
    for key in changed_keys:
        if key not in refreshed:
            after_map[key] = (results[key][0], set())
    return after_map


def _verify_written(
    changed_keys: list[tuple[str, int]],
    existing: InterfaceMap,
    after_map: InterfaceMap,
    writes: _WriteTracker,
) -> None:
    """Fail when the re-read shows an interface still holding exactly its previous addresses.

    Fabric Engine can answer an address PUT with 204 and keep the addresses
    (the virtual IST VLAN while the vIST exists). Such a write did not
    change the device: it is taken off the write tracker, so the failure only
    reports changed=true when another interface of the task was written.
    """
    ignored = []
    for key in changed_keys:
        before = existing.get(key, (None, set()))[1]
        iface, after = after_map.get(key, (None, set()))
        if iface is not None and after == before:
            ignored.append(iface.label())
    if not ignored:
        return
    writes.done = [label for label in writes.done if label not in ignored]
    raise ExtremeFeL3InterfacesError(
        "The device accepted the address PUT of %s but kept the previous addresses, so nothing was changed there"
        % ", ".join(ignored),
        details={"not_applied": ignored},
    )


def _compute_differences(
    changed_keys: list[tuple[str, int]],
    existing: InterfaceMap,
    after_map: InterfaceMap,
    final_sets: InterfaceMap,
) -> list[dict[str, object]]:
    """Per-interface address differences for the interfaces that changed."""
    differences: list[dict[str, object]] = []
    for key in changed_keys:
        iface_before = existing.get(key, (None, set()))
        iface_after = after_map.get(key, (None, set()))
        before_entry = build_result_entry(iface_before[0] or final_sets[key][0], iface_before[1])
        after_entry = build_result_entry(iface_after[0] or final_sets[key][0], iface_after[1])
        diff: dict[str, object] = {}
        for field in ("ipv4", "ipv6"):
            bval = before_entry.get(field, [])
            aval = after_entry.get(field, [])
            if bval != aval:
                diff[field] = {"before": bval, "after": aval}
        if diff:
            diff["type"] = before_entry.get("type")
            if before_entry.get("vlan_id") is not None:
                diff["vlan_id"] = before_entry["vlan_id"]
            if before_entry.get("loopback_id") is not None:
                diff["loopback_id"] = before_entry["loopback_id"]
            if before_entry.get("name"):
                diff["name"] = before_entry["name"]
            differences.append(diff)
    return differences


def _handle_action_state(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    config: list[dict[str, object]],
    writes: _WriteTracker,
) -> dict[str, object]:
    """merged / replaced / overridden / deleted: read, compare, PUT, re-read."""
    config_map = _build_config_map(config)
    # deleted without config removes the addressing of every interface, like the
    # Ansible resource modules of other vendors: it is overridden with an empty
    # config, so it reads every interface, skips the protected VLANs with a
    # warning and re-reads every interface afterwards.
    delete_all = state == "deleted" and not config_map
    if not config_map and state in ACTION_STATES and not delete_all:
        raise ExtremeFeL3InterfacesError("'config' is required for the selected state")
    plan_state = "overridden" if delete_all else state

    # Protected VLAN keys -> reason (populated by overridden and delete-all).
    protected: dict[tuple[str, int], str] = {}
    existing = _gather_existing(connection, plan_state, config_map, protected)
    if state == "deleted":
        # A VLAN that does not exist has nothing to delete: leave it out.
        config_map = {key: value for key, value in config_map.items() if key in existing}
    final_sets = compute_final_sets(plan_state, config_map, existing)

    results, changed_keys, warnings = _apply_changes(
        module, connection, final_sets, existing, protected, writes, set(config_map), plan_state == "overridden"
    )
    after_map = _capture_after_state(module, connection, plan_state, config_map, existing, results, changed_keys)
    if changed_keys and not module.check_mode:
        _verify_written(changed_keys, existing, after_map, writes)

    # before: captured from existing (pre-change state).
    # after:  fresh read after a real change, local projection otherwise.
    before_list = [build_result_entry(iface, addresses) for iface, addresses in existing.values()]
    after_list = [build_result_entry(iface, addresses) for iface, addresses in after_map.values()]
    differences = _compute_differences(changed_keys, existing, after_map, final_sets)

    # Emit warnings for skipped protected VLANs.
    for msg in warnings:
        module.warn(msg)

    result: dict[str, object] = {
        "changed": bool(changed_keys),
        # interfaces mirrors after, so both reflect the same view of the device.
        "interfaces": after_list,
        "before": before_list,
        "after": after_list,
        "differences": differences,
    }
    # Diff mode (--diff): Ansible renders the pair itself. Populated even
    # when nothing changed, so --check --diff shows a converged play.
    if module._diff:
        result["diff"] = {"before": before_list, "after": after_list}
    return result


# ── Entry point ───────────────────────────────────────────────────────────────


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    state = module.params["state"]
    config = module.params.get("config") or []

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        # Every state: an interface listed twice fails before any request (the
        # gathered path builds its interface list without this check).
        _build_config_map(config)
        if state == "gathered":
            result = _handle_gathered(connection, config)
        else:
            # Every PUT is recorded, so a failure after one of them reports
            # changed=true and names the interfaces written (see _WriteTracker).
            with _WriteTracker() as writes:
                result = _handle_action_state(module, connection, state, config, writes)
        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except ExtremeFeL3InterfacesError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
