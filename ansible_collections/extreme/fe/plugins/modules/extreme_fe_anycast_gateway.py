# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""
Ansible module to manage Anycast Gateway interfaces on Extreme Fabric Engine switches.

REST API endpoints used:
  GET    /v0/configuration/anycast-gateway/interfaces          — list all interfaces
  POST   /v0/configuration/anycast-gateway/vlan/{vlan_id}      — create interface
  PATCH  /v0/configuration/anycast-gateway/vlan/{vlan_id}/interface — update enabled
  DELETE /v0/configuration/anycast-gateway/vlan/{vlan_id}      — delete interface
  GET    /v0/state/anycast-gateway/interfaces                  — operational state

Writable fields (POST only — immutable after creation):
  ipAddress.address    — IPv4 address of the anycast gateway
  ipAddress.maskLength — IPv4 mask length (0-32), ONLY with oneIp=true. A gateway that is
                         not ONE-IP has no mask: the device reports maskLength 0 for it
                         and rejects a POST that carries one (HTTP 422).
  oneIp                — ONE-IP mode (bool, default false)
  vrId                 — Virtual Router ID (int, 1-255, optional)

Writable fields (PATCH):
  enabled              — Administrative status (bool, default false)

Read-only fields (anycast_gateways_state for gathered, anycast_gateways[].before/after otherwise):
  mac_address, l2vsn_isid, oper_state
gathered, before and after hold only the config suboptions, so they can be fed back as config.

Changing an immutable field under replaced/overridden is DELETE + POST. The POST body is
validated locally before the DELETE, and if the re-create fails the original interface is
restored from the state captured before the change.
"""

from __future__ import annotations

# ── Ansible module metadata ──────────────────────────────────────────────────

DOCUMENTATION = r"""
---
module: extreme_fe_anycast_gateway
short_description: Manage Anycast Gateway interfaces on Extreme Fabric Engine switches
version_added: "1.2.0"
description:
  - Create, update, delete, and query Anycast Gateway interfaces on Extreme
    Fabric Engine switches via the REST API.
  - Supports all five Ansible resource module states.
  - Each Anycast Gateway interface is identified by its C(vlan_id).
  - "Writable fields at creation (immutable after): C(ip_address), C(mask_length), C(one_ip), C(vr_id)."
  - Only C(enabled) can be updated on an existing interface via PATCH.
author:
  - Andreea-Lavinia Vraja (@avraja_extr)
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI
    connection plugin.
  - Once created, C(ip_address), C(mask_length), C(one_ip), and C(vr_id) cannot
    be changed. Use C(state=replaced) (DELETE + re-POST) to change these fields.
  - C(state=merged) will fail if you try to change immutable fields on an existing
    interface. Use C(state=replaced) or delete the interface first.
  - For C(state=replaced) and C(state=overridden), omitted immutable fields are
    treated as "don't care" — only provided immutable fields are compared for
    differences. If you want to enforce specific immutable values on an existing
    interface, provide all immutable fields or use C(state=deleted) first.
  - "C(mask_length) can only be specified when C(one_ip=true). Fabric Engine constraint:
    'IP Address mask allowed only with Anycast Gateway ONE-IP.' The module never sends
    a mask length for a gateway that is not in ONE-IP mode, and it reports
    C(mask_length) as C(null) for such a gateway (the device reports 0 for it, which
    means not set)."
  - The module automatically disables an interface (C(enabled=false)) before
    deleting it, as required by Fabric Engine.
  - With C(state=replaced) or C(state=overridden), changing an immutable field of an
    existing interface is a DELETE followed by a POST. Immutable fields that are
    omitted are taken from the existing interface (C(mask_length) only when the
    resulting interface is in ONE-IP mode). The POST body is validated locally
    before the interface is deleted, so a request that cannot succeed (for example
    a C(mask_length) without ONE-IP, or ONE-IP without a C(mask_length)) fails
    without touching the device.
  - Creating a new interface with C(one_ip=true) requires C(mask_length). Without it the
    task fails before anything is sent to the device, also in check mode.
  - If the re-create fails after the DELETE (the POST or the follow-up C(enabled)
    PATCH is rejected), the module restores the original interface from the state
    it captured before the change, re-enables it if it was enabled, and then fails
    the task with the original error plus a statement that the original was
    restored. In that case C(changed) is C(false) unless other interfaces of the
    same task were already modified. If the restore itself fails, the message says
    so, C(changed) is C(true), and C(details.original_payload) holds the POST body
    needed to re-create the interface by hand.
  - A DELETE or POST of a re-create that fails without an answer from the device (a
    transport error, for example a lost response) does not prove the device did not
    carry it out, so the module reads that VLAN back. If the DELETE was in fact carried
    out (the gateway is gone), or the POST was (the gateway exists with the requested
    C(ip_address), C(one_ip), C(vr_id) and, for ONE-IP, C(mask_length)), the re-create
    continues and a warning says the response was lost. Otherwise the failure is
    handled as described above. An error that the device returns in the response body,
    or an HTTP error status, is definitive and is handled as described above without
    reading the VLAN back. The exceptions are HTTP 409 on the POST and HTTP 404 on the
    DELETE, which a resend of a request that was already carried out gets back; the
    VLAN is read back for them as for a transport error.
  - If the follow-up C(enabled) PATCH fails without an answer, the new interface is read
    back. If it already has the requested C(enabled), the re-create succeeds and a warning
    says the response was lost; if it does not, the original is restored as described
    above. If it cannot be read back, the new interface may be enabled, so before it is
    deleted to restore the original it is disabled (checked the same way as any disable
    before a delete). If it cannot be disabled, it is not deleted; the task fails with a
    message that the new interface still exists and the original was not restored,
    C(changed) is C(true), and C(details) hold C(rollback=not restored),
    C(replacement_kept=true) and C(original_payload).
  - The DELETE of the new interface and the POST of the original during that restore
    are checked the same way. If one of them fails without an answer (or with the HTTP
    404 or 409 of a resend) and the read-back shows it was carried out (the new
    interface is gone, or the original exists again with its C(ip_address), C(one_ip),
    C(vr_id) and, for ONE-IP, C(mask_length)), the restore continues, the original is
    re-enabled if it was enabled, and a warning says the response was lost; the task
    then fails exactly as after any successful restore. If the device rejects the DELETE
    of the new interface (an error in the response body or an HTTP error status), or the
    read-back shows that it was not deleted, or that the VLAN holds a gateway with other
    values than the original, the message says so, C(changed) is C(true), and C(details)
    hold C(rollback=not restored) (with C(replacement_kept=true) when the new interface
    is still there). If the VLAN cannot be read back, the task fails with a message that
    the state of the gateway is unknown, C(changed) is C(true), and C(details) also
    hold C(rollback=unknown) and C(rollback_error).
  - The PATCH that disables an interface before it is deleted (re-create, C(deleted),
    C(overridden)) is checked the same way. If it fails without an answer and the
    read-back shows the interface disabled, the module re-enables it and fails the task
    with the original error plus a statement that the gateway was re-enabled;
    C(changed) is then C(false) unless other interfaces of the same task were already
    modified, and C(true) if it could not be re-enabled. The same C(changed) rule applies
    when the disable of C(deleted) or C(overridden) fails without changing that interface.
  - The DELETE of C(deleted) and of the C(overridden) pre-pass is checked the same way.
    If it fails without an answer (or with the HTTP 404 of a resend), the module reads
    that VLAN back. If the gateway is gone, the DELETE was carried out; the interface is
    reported as deleted, a warning says the response was lost and the task continues. If
    the gateway is still there, the task fails with the DELETE error plus a statement
    that the gateway is still configured (and disabled, if the module disabled it for the
    delete; it is not re-enabled). Any other DELETE failure is definitive and the VLAN is
    not read back. When the task fails because the gateway is still configured, C(changed)
    is C(true) if the module left it disabled, and otherwise C(false) unless other
    interfaces of the same task were already modified.
  - If the VLAN cannot be read back after such a failure, the task fails with a message
    that the state of the gateway is unknown, C(changed) is C(true), and C(details) hold
    C(vlan_id), C(original_payload), C(original_enabled), the request error
    (C(patch_error), C(delete_error) or C(post_error)) and C(read_error). After the
    DELETE of C(deleted) or the C(overridden) pre-pass the message advises running the
    task again if the gateway is still there; after a re-create it advises re-creating
    the original from C(original_payload) if the VLAN has no gateway.
  - A read of a single VLAN treats HTTP 404 and 422 as "no Anycast Gateway", whether the
    device raises the status or returns it in the response body (for example a body
    with C(statusCode) 404). The same applies to the read of the state endpoint that
    checks whether a gateway is still there after a failed request.
  - An C(enabled) PATCH (of C(merged), of C(replaced) or C(overridden) when only
    C(enabled) differs, after a create or re-create, and when the original is re-enabled
    during a restore) and the POST that creates a missing interface are checked the same
    way when they fail without an answer (for the POST also the HTTP 409 of a resend).
    The VLAN is read back. If the request was carried out (the gateway has the requested
    C(enabled), or exists with the requested C(ip_address), C(one_ip), C(vr_id) and, for
    ONE-IP, C(mask_length)), the task continues and a warning says the response was lost.
    If it was not, the task fails with the request error. If the VLAN cannot be read back,
    the task fails with a message that the state of the gateway is unknown, C(changed) is
    C(true), and C(details) hold C(vlan_id), C(state=unknown), the request error and
    C(read_error) (a restore that cannot tell whether the original was re-enabled also
    holds C(rollback=unknown)).
  - A failed task reports C(changed=true) whenever the device was already modified, for
    example by an earlier entry of C(config), by the C(overridden) pre-pass, or by the
    POST of a new interface whose C(enabled) PATCH then failed (the message then says
    the interface was created). It reports C(changed=false) when nothing was written,
    and always in check mode.
  - IPv6 Anycast is currently not supported by the device firmware.
  - Supports check mode and diff mode. Under C(--diff) the module reports the
    Anycast Gateway configuration of the whole device before and after the change;
    combined with C(--check) the reported C(after) is the state that would have been
    written.
requirements:
  - ansible.netcommon
options:
  state:
    description:
      - Desired operation state.
      - C(merged) creates interfaces that do not exist and updates C(enabled) on
        existing interfaces. Fails if immutable fields differ.
      - C(replaced) makes the provided config authoritative per listed interface.
        If immutable fields differ, the interface is deleted and recreated; if the
        re-create fails, the original interface is restored.
      - C(overridden) deletes unlisted interfaces, then applies C(replaced) logic
        to listed ones.
      - C(deleted) removes the specified interfaces. If C(config) is omitted, all
        Anycast Gateway interfaces are deleted.
      - C(gathered) returns current interface information without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - List of Anycast Gateway interface configurations to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional for C(deleted) (omit to delete all) and C(gathered).
    type: list
    elements: dict
    suboptions:
      vlan_id:
        description:
          - VLAN ID (1-4094). This is the resource identifier.
        type: int
        required: true
      ip_address:
        description:
          - IPv4 address of the Anycast Gateway interface.
          - Immutable after creation. Use C(state=replaced) to change.
        type: str
      mask_length:
        description:
          - IPv4 subnet mask length (0-32).
          - Only allowed when C(one_ip=true). It is never sent for a gateway that is
            not in ONE-IP mode, and it is reported as C(null) for such a gateway.
          - Required to create an interface with C(one_ip=true).
          - Immutable after creation. Use C(state=replaced) to change.
        type: int
      enabled:
        description:
          - Administrative status of the Anycast Gateway on the VLAN.
          - This is the only field that can be updated on an existing interface.
        type: bool
      one_ip:
        description:
          - Enable ONE-IP mode. Fabric Engine only.
          - Immutable after creation. Use C(state=replaced) to change.
        type: bool
      vr_id:
        description:
          - Virtual Router ID (1-255). Fabric Engine only.
          - If omitted at creation, the device uses the default GW MAC.
          - Reported as C(null) for a gateway without a VRID (the device reports C(vrId) 0).
          - Immutable after creation. Use C(state=replaced) to change.
        type: int
  gather_filter:
    description:
      - Limit gathered results to these VLAN IDs.
    type: list
    elements: int
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

# -------------------------------------------------------------------------
# Task 1: Gather all Anycast Gateway interfaces
# -------------------------------------------------------------------------
# - name: "Task 1: Gather Anycast Gateway interfaces"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather current Anycast Gateway configuration
  extreme.fe.extreme_fe_anycast_gateway:
    state: gathered

# -------------------------------------------------------------------------
# Task 2: Gather selected VLANs only
# -------------------------------------------------------------------------
# - name: "Task 2: Gather Anycast Gateway for selected VLANs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gather Anycast GW for VLANs 100 and 200
  extreme.fe.extreme_fe_anycast_gateway:
    state: gathered
    gather_filter:
      - 100
      - 200

# gathered holds only the config options, so it can be re-applied as is (no change)
- name: Gather Anycast GW configuration
  extreme.fe.extreme_fe_anycast_gateway:
    state: gathered
  register: ag

- name: Re-apply the gathered configuration
  extreme.fe.extreme_fe_anycast_gateway:
    state: replaced
    config: "{{ ag.gathered }}"

# -------------------------------------------------------------------------
# Task 3: Create Anycast Gateway interfaces
# -------------------------------------------------------------------------
# - name: "Task 3: Create Anycast Gateway interfaces"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Create Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: merged
    config:
      - vlan_id: 100
        ip_address: 10.10.10.1
        mask_length: 24
        one_ip: true
        enabled: true

- name: Create Anycast GW with ONE-IP and VRID
  extreme.fe.extreme_fe_anycast_gateway:
    state: merged
    config:
      - vlan_id: 200
        ip_address: 192.168.1.1
        mask_length: 24
        one_ip: true
        vr_id: 21
        enabled: true

# -------------------------------------------------------------------------
# Task 4: Replace/override Anycast Gateway interfaces
# -------------------------------------------------------------------------
# - name: "Task 4: Replace or override Anycast Gateway configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Replace Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: replaced
    config:
      - vlan_id: 100
        ip_address: 10.10.10.254
        mask_length: 24
        one_ip: true
        enabled: true

- name: Change the address of a regular (not ONE-IP) Anycast GW on VLAN 300
  extreme.fe.extreme_fe_anycast_gateway:
    state: replaced
    config:
      - vlan_id: 300
        ip_address: 10.30.30.254
        vr_id: 30
        enabled: true

- name: Override all Anycast GW interfaces
  extreme.fe.extreme_fe_anycast_gateway:
    state: overridden
    config:
      - vlan_id: 100
        ip_address: 10.10.10.1
        mask_length: 24
        one_ip: true
        enabled: true

# -------------------------------------------------------------------------
# Task 5: Delete Anycast Gateway interfaces
# -------------------------------------------------------------------------
# - name: "Task 5: Delete Anycast Gateway interfaces"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Delete Anycast GW on VLAN 100
  extreme.fe.extreme_fe_anycast_gateway:
    state: deleted
    config:
      - vlan_id: 100

- name: Delete all Anycast GW interfaces
  extreme.fe.extreme_fe_anycast_gateway:
    state: deleted
"""

RETURN = r"""
before:
  description:
    - Full Anycast Gateway resource configuration before changes.
    - Returned for action states (merged, replaced, overridden, deleted).
    - Lists every Anycast Gateway interface of the device.
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
after:
  description:
    - Full Anycast Gateway resource configuration after changes.
    - Returned for action states (merged, replaced, overridden, deleted), whether or
      not anything changed. When nothing changed it equals C(before).
    - After a real change it is re-read from the device. An interface of the task that
      this read does not return (the device can omit recently created interfaces) is
      read on its own, or predicted if that does not return it either. If the re-read
      fails, it is the predicted state and a warning says so. In check mode it is the
      predicted state.
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
gathered:
  description:
    - Anycast Gateway configuration gathered from the device.
    - Returned only for C(state=gathered).
    - Holds only the C(config) suboptions, so it can be passed back as C(config) unchanged. Re-applying it
      with C(merged), C(replaced) or C(overridden) changes nothing.
    - C(mask_length) is C(null) for a gateway that is not in ONE-IP mode and C(vr_id) is C(null) for a
      gateway without a VRID.
    - The read-only fields are returned in C(anycast_gateways_state).
  returned: when state is gathered
  type: list
  elements: dict
  sample:
    - vlan_id: 100
      ip_address: 10.10.10.1
      mask_length: 24
      enabled: true
      one_ip: true
      vr_id: 21
anycast_gateways_state:
  description:
    - Read-only data of the gathered Anycast Gateway interfaces, one entry per entry of C(gathered).
    - These fields cannot be configured and are therefore not part of C(gathered).
  returned: when state is gathered
  type: list
  elements: dict
  contains:
    vlan_id:
      description: VLAN ID (resource identifier).
      type: int
    mac_address:
      description: Gateway MAC address reported by the device.
      type: str
    l2vsn_isid:
      description: I-SID of the L2 VSN of the VLAN.
      type: int
    oper_state:
      description: Operational state from the state endpoint, C(null) when the device does not report it.
      type: str
anycast_gateways:
  description: Per-resource Anycast Gateway operation results with differences.
  returned: when state is not gathered
  type: list
  elements: dict
  contains:
    vlan_id:
      description: VLAN ID (resource identifier).
      type: int
    before:
      description:
        - Interface configuration before the operation.
        - Also holds the read-only C(mac_address), C(l2vsn_isid) and C(oper_state).
      type: dict
    after:
      description:
        - Interface configuration after the operation.
        - Re-read from the device after a real change, the predicted state otherwise
          (check mode, or when the device does not return the interface).
        - Also holds the read-only C(mac_address), C(l2vsn_isid) and C(oper_state).
      type: dict
    changed:
      description: Whether this interface was modified.
      type: bool
    differences:
      description: Fields that changed with before/after values.
      type: dict
api_responses:
  description:
    - Raw REST API responses for debugging.
    - Deprecated and will be removed in 2.0.0.
    - Use C(before) and C(after) for the configuration before and after a change, C(gathered) for
      C(state=gathered), and C(anycast_gateways) for the per-interface results. When a re-create fails, the
      failure C(details) report whether the original gateway was restored.
  returned: always
  type: dict
changed:
  description: Whether any interface was modified.
  returned: always
  type: bool
"""

# ipaddress — standard library module for validating and comparing IP addresses/networks
import ipaddress

# json — parse REST responses that arrive as text
import json

# time — used for retry delays when PATCH follows POST (API timing)
import time as _time

# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any

# AnsibleModule — the core class every Ansible module must instantiate;
# it handles argument parsing, check mode, exit/fail, etc.
from ansible.module_utils.basic import AnsibleModule

# to_text — safely converts bytes/strings to unicode text
from ansible.module_utils.common.text.converters import to_text

# Connection — communicates with the device through the httpapi plugin;
# ConnectionError — raised when the device is unreachable or returns a transport error
from ansible.module_utils.connection import Connection, ConnectionError

# ── Constants ─────────────────────────────────────────────────────────────────

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# REST API paths
AG_LIST_PATH = "/v0/configuration/anycast-gateway/interfaces"
AG_VLAN_PATH = "/v0/configuration/anycast-gateway/vlan/{vlan_id}"
AG_PATCH_PATH = "/v0/configuration/anycast-gateway/vlan/{vlan_id}/interface"
AG_STATE_PATH = "/v0/state/anycast-gateway/interfaces"

# Status codes a read of one VLAN treats as "no Anycast Gateway there", whether the device
# raises them as an HTTP error or returns them in-band in the response body
NOT_FOUND_CODES = (404, 422)

# HTTP statuses that a RETRY of an already-applied request gets back. The httpapi plugin resends a request
# whose transport failed (RETRY_SIGNATURES), so a POST whose first attempt created the gateway can come back
# 409 (already exists) and a DELETE whose first attempt deleted it 404 (not found).
RETRY_OF_APPLIED_STATUSES = frozenset({("POST", 409), ("DELETE", 404)})

# Factory defaults
FACTORY_DEFAULTS = {
    "enabled": False,
    "one_ip": False,
}

# Fields set at creation that cannot be PATCHed
IMMUTABLE_FIELDS = {"ip_address", "mask_length", "one_ip", "vr_id"}

# Fabric Engine constraint, also reported by the device itself (HTTP 422)
MASK_REQUIRES_ONE_IP_MSG = (
    "IP Address mask allowed only with Anycast Gateway ONE-IP. "
    "Set one_ip=true when mask_length is specified (vlan_id {0})"
)

# A ONE-IP gateway needs a mask: {0} = create / re-create, {1} = vlan_id, {2} = optional reason
MASK_REQUIRED_FOR_ONE_IP_MSG = (
    "mask_length is required to {0} Anycast Gateway vlan_id={1} in ONE-IP mode{2}; nothing was changed"
)

# Writable fields for diff comparison (exclude identifier and read-only)
DIFF_FIELDS = ("ip_address", "mask_length", "enabled", "one_ip", "vr_id")

# Read-only fields of the full interface record: reported in anycast_gateways_state (gathered)
# and anycast_gateways[].before/after, never in gathered/before/after (not config suboptions)
READ_ONLY_FIELDS = ("mac_address", "l2vsn_isid", "oper_state")

# Argument spec
ARGUMENT_SPEC = {
    "state": {
        "type": "str",
        "default": STATE_MERGED,
        "choices": [
            STATE_MERGED,
            STATE_REPLACED,
            STATE_OVERRIDDEN,
            STATE_DELETED,
            STATE_GATHERED,
        ],
    },
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "vlan_id": {"type": "int", "required": True},
            "ip_address": {"type": "str"},
            "mask_length": {"type": "int"},
            "enabled": {"type": "bool"},
            "one_ip": {"type": "bool"},
            "vr_id": {"type": "int"},
        },
    },
    "gather_filter": {
        "type": "list",
        "elements": "int",
    },
}


# ── Custom Exception ─────────────────────────────────────────────────────────


class FeAnycastGwError(Exception):
    """Raised for module-specific errors."""

    def __init__(
        self,
        msg: str,
        details: dict[str, Any] | None = None,
        *,
        extra: dict[str, Any] | None = None,
        changed: bool | None = None,
    ) -> None:
        super().__init__(msg)
        self.msg = msg
        self.details = details or {}
        # Extra fail_json keys (code / err of a transport error)
        self.extra = extra or {}
        # Whether the device was left modified; only set where the module knows it
        self.changed = changed
        # True when a read-back proved that this request, although it failed without an answer, was NOT applied
        self.not_applied = False

    def to_fail_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"msg": self.msg}
        kwargs.update(self.extra)
        if self.details:
            kwargs["details"] = self.details
        if self.changed is not None:
            kwargs["changed"] = self.changed
        return kwargs


class _GatewayStateUnknown(FeAnycastGwError):
    """A disable PATCH, DELETE or POST failed and the VLAN could not be read back: its state is unknown.

    Nothing may be rolled back on top of an unknown state, so this error is passed through as is.
    """


class _EnableStateUnknown(FeAnycastGwError):
    """An enabled PATCH failed without an answer and the gateway could not be read back (see _patch_enabled_retry).

    Not a _GatewayStateUnknown: the gateway itself exists, only its enabled state is unknown, so a
    re-create still restores the original (its rollback disables the replacement first). Each caller
    words the outcome; ``details`` hold vlan_id, patch_error and read_error, ``extra`` the PATCH error.
    """


# ── REST API Helper ───────────────────────────────────────────────────────────
# This utility function handles communication with the device's REST API.
# It sends HTTP requests (GET, POST, PATCH, DELETE) and processes responses.


def _parse_response(raw: Any) -> Any:
    """Return a dict/list body as is, decode a JSON string, anything else is None."""
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return raw
    return None


def _decode_json_text(raw: Any) -> Any:
    """Decode a JSON string response; any other value (or invalid JSON) is returned unchanged."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return raw
    return raw


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: dict[str, Any],
    response_key: str,
    payload: Any = None,
    raising: bool = False,
) -> Any:
    """Send a single REST API request.

    Args:
        module:         The AnsibleModule instance.
        connection:     The device Connection object.
        method:         HTTP method (GET, POST, PATCH, DELETE).
        path:           REST API path.
        payload:        Request body (dict for JSON, None for no body).
        api_responses:  Dict to store raw API responses for debugging.
        response_key:   Key name to store this response under.
        raising:        When True a transport error is RAISED as FeAnycastGwError
                        (see _request) instead of ending the task with fail_json().

    Returns:
        Parsed response payload, or None if no content.
    """
    if raising:
        # Callers that have a fallback (e.g. the final re-read) must be able to catch the error
        return _request(
            connection,
            method=method,
            path=path,
            api_responses=api_responses,
            response_key=response_key,
            payload=payload,
        )
    try:
        raw = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        module.fail_json(
            msg=f"REST API call failed: {method} {path}: {to_text(exc)}",
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=api_responses,
        )

    parsed = _parse_response(raw)

    api_responses[response_key] = {
        "method": method,
        "path": path,
        "body": parsed,
    }

    if parsed is not None and isinstance(parsed, (dict, list)):
        err = _extract_error(parsed)
        if err:
            raise FeAnycastGwError(
                f"{method} {path} returned an error: {err}",
                details={"response": parsed},
            )

    return parsed


def _request(
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: dict[str, Any],
    response_key: str,
    payload: Any = None,
) -> Any:
    """Send one REST request and RAISE on failure instead of ending the task.

    _call_api() calls fail_json() on a transport error, which ends the module on
    the spot. The delete + re-create sequence cannot use it: after the DELETE a
    failure has to be caught so the original interface can be restored first.
    The response (or the error) is recorded in api_responses under response_key.

    Raises:
        FeAnycastGwError: transport error (code/err in ``extra``) or in-band error body.
    """
    try:
        raw = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        code = getattr(exc, "code", None)
        api_responses[response_key] = {"method": method, "path": path, "error": to_text(exc), "code": code}
        raise FeAnycastGwError(
            f"REST API call failed: {method} {path}: {to_text(exc)}",
            extra={"code": code, "err": getattr(exc, "err", None)},
        )

    parsed = _parse_response(raw)
    api_responses[response_key] = {"method": method, "path": path, "body": parsed}
    if isinstance(parsed, (dict, list)):
        err = _extract_error(parsed)
        if err:
            raise FeAnycastGwError(f"{method} {path} returned an error: {err}", details={"response": parsed})
    return parsed


def _http_status(exc: FeAnycastGwError) -> int | None:
    """The HTTP status of a failed request, or None when the device sent no HTTP answer.

    The httpapi plugin raises every HTTP status >= 400 as ConnectionError(code=<status>).
    A transport failure carries no status: no code, or the JSON-RPC error code of the
    persistent connection (a negative number such as -32603).
    """
    code = exc.extra.get("code")
    # bool is an int subclass but never a status code
    if isinstance(code, int) and not isinstance(code, bool) and 100 <= code <= 599:
        return code
    return None


def _is_ambiguous_failure(exc: FeAnycastGwError, method: str) -> bool:
    """Whether a failed request may still have been applied, so the device must be read back.

    Rule, per method:

    - an error in the response body (``details["response"]``) is a definitive rejection;
    - a ConnectionError WITHOUT an HTTP status (a transport failure, e.g. a lost response)
      is ambiguous: the device may have carried the request out;
    - a ConnectionError WITH an HTTP status is a definitive rejection (nothing was applied),
      EXCEPT the statuses a plugin retry of an already-applied request gets back (see
      RETRY_OF_APPLIED_STATUSES): POST 409 and DELETE 404 stay ambiguous. For the disable
      PATCH (``method`` "PATCH") any HTTP status is definitive.
    """
    if "response" in exc.details or "code" not in exc.extra:
        # In-band rejection (or an error that did not come from the transport): the device refused
        return False
    status = _http_status(exc)
    if status is None:
        # No HTTP answer at all: the request may or may not have been applied
        return True
    return (method, status) in RETRY_OF_APPLIED_STATUSES


def _body_status_code(data: Any) -> int | None:
    """The errorCode/statusCode/code of an in-band response body as an int, or None."""
    if not isinstance(data, dict):
        return None
    code = data.get("errorCode") or data.get("statusCode") or data.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    # bool is an int subclass but never a status code
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def _is_not_found_body(data: Any) -> bool:
    """Whether an in-band response body reports one of NOT_FOUND_CODES (the VLAN has no gateway)."""
    return _body_status_code(data) in NOT_FOUND_CODES


def _extract_error(data: Any) -> str | None:
    """Extract an error message from a REST response, if present."""
    if not isinstance(data, dict):
        return None
    # Check for errorCode/statusCode/code pattern (Fabric Engine REST convention)
    code = data.get("errorCode") or data.get("statusCode") or data.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    message = data.get("errorMessage") or data.get("message") or data.get("detail")
    if code and isinstance(code, int) and code >= 400:
        return message or f"Device reported an error (code {code})"
    # Check for error/errors keys
    if data.get("error"):
        err = data["error"]
        if isinstance(err, dict):
            return err.get("message", str(err))
        return str(err)
    if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
        msgs = [e.get("message", str(e)) if isinstance(e, dict) else str(e) for e in data["errors"]]
        return "; ".join(msgs)
    return None


# ── Disable-before-Delete Helper ──────────────────────────────────────────────


def _disable_and_delete(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    current: dict[str, Any] | None,
    api_responses: dict[str, Any],
    response_prefix: str,
    changed_before: bool,
) -> None:
    """Disable an Anycast GW interface (if enabled) then DELETE it.

    Fabric Engine requires enabled=false before DELETE is allowed. A disable
    whose response was lost is reconciled with the device (see _disable_for_delete).
    ``changed_before`` is the device state before this interface was touched.

    A DELETE that fails without an HTTP answer (or with the 404 of a plugin retry, see
    _is_ambiguous_failure) is checked against the device: if the gateway is gone, the
    DELETE was applied and only its response was lost, so a warning is issued and the
    VLAN counts as deleted. The read-back is recorded as
    <response_prefix>_verify_delete_filtered_<vid> (and _state_<vid>).

    Raises:
        FeAnycastGwError: the disable or the DELETE failed and the gateway is still
        configured. ``changed`` is True when the gateway was left disabled, else
        ``changed_before`` (earlier entries of the task may have modified the device).
        _GatewayStateUnknown: the DELETE failed without a definitive answer and the
        VLAN could not be read back (``changed`` True, see _state_unknown).
    """
    disabled = False
    if current and current.get("enabled"):
        _disable_for_delete(
            connection, vid, current, api_responses, f"{response_prefix}_disable_{vid}", response_prefix, changed_before
        )
        disabled = True
    del_path = AG_VLAN_PATH.format(vlan_id=vid)
    try:
        _call_api(
            module,
            connection,
            method="DELETE",
            path=del_path,
            api_responses=api_responses,
            response_key=f"{response_prefix}_{vid}",
            raising=True,
        )
    except FeAnycastGwError as exc:
        if not _is_ambiguous_failure(exc, "DELETE"):
            # Definitive rejection: nothing was deleted. The device was modified only if the gateway was
            # left disabled; otherwise it is as the earlier entries of the task left it
            exc.changed = disabled or changed_before
            raise
        # No definitive answer (or the 404 of a retry): ask the device whether the gateway still exists.
        # A failed read raises _GatewayStateUnknown (changed True)
        if not _gateway_exists_after_failure(
            connection, vid, "DELETE", exc, current or {}, api_responses, f"{response_prefix}_verify", "delete"
        ):
            # The gateway is gone: the DELETE was applied and only its response was lost
            module.warn(
                f"The DELETE of the Anycast Gateway on VLAN {vid} reported an error ({exc.msg}), but the gateway "
                "is gone: the delete was applied and only its response was lost."
            )
            return
        # The DELETE was not applied: the gateway is still configured (disabled, if this task disabled it)
        state = "still configured but disabled (it was disabled for the delete)" if disabled else "still configured"
        msg = _extend_msg(exc.msg, f"The Anycast Gateway on VLAN {vid} was not deleted; it is {state}.")
        raise FeAnycastGwError(msg, details=exc.details, extra=exc.extra, changed=disabled or changed_before)


# ── Data-Fetching Functions ───────────────────────────────────────────────────
# These functions retrieve the current configuration from the device via
# REST GET requests and normalize the response into Python data structures.


def _fetch_all_interfaces(
    module: AnsibleModule,
    connection: Connection,
    api_responses: dict[str, Any],
    response_key: str = "get_all",
    raising: bool = False,
) -> list[dict[str, Any]]:
    """Fetch all Anycast Gateway interfaces from the device (raising: see _call_api)."""
    raw = _call_api(
        module,
        connection,
        method="GET",
        path=AG_LIST_PATH,
        api_responses=api_responses,
        response_key=response_key,
        raising=raising,
    )
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if not raw:
            return []
        # Handle dict wrappers (data, items, interfaces, etc.)
        for key in ["data", "items", "interfaces", "anycast_gateways"]:
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    return []


def _fetch_state_interfaces(
    module: AnsibleModule,
    connection: Connection,
    api_responses: dict[str, Any],
    response_key: str = "get_state",
    raising: bool = False,
) -> dict[int, dict[str, Any]]:
    """Fetch operational state for all Anycast Gateway interfaces (raising: see _call_api).

    Returns a dict keyed by vlan_id with state data.
    """
    raw = _call_api(
        module,
        connection,
        method="GET",
        path=AG_STATE_PATH,
        api_responses=api_responses,
        response_key=response_key,
        raising=raising,
    )
    state_map: dict[int, dict[str, Any]] = {}
    if isinstance(raw, list):
        for entry in raw:
            vid = entry.get("vlanId")
            if vid is not None:
                state_map[vid] = entry
    elif isinstance(raw, dict):
        # Handle dict wrappers (data, items, state, etc.)
        list_data = None
        for key in ["data", "items", "state", "interfaces", "anycast_gateways"]:
            if key in raw and isinstance(raw[key], list):
                list_data = raw[key]
                break
        if list_data:
            for entry in list_data:
                vid = entry.get("vlanId")
                if vid is not None:
                    state_map[vid] = entry
    return state_map


# ── Output Converters ─────────────────────────────────────────────────────────
# Converts raw REST API responses (device field names) into Ansible-friendly
# output format (snake_case field names matching the module's argument spec).


def _reported_mask_length(mask: Any, one_ip: Any) -> Any:
    """Return the mask length to report for a gateway.

    A gateway that is not in ONE-IP mode has no mask: the device reports
    maskLength 0 for it. That 0 means "not set", so it is reported as None.
    For a ONE-IP gateway the value is real (0 included) and is kept.
    """
    if not one_ip and not mask:
        return None
    return mask


def _to_ansible_output(raw: dict[str, Any], state_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convert a single REST InterfaceAnycastGateway to Ansible output format."""
    ip_obj = raw.get("ipAddress") or {}
    result: dict[str, Any] = {
        "vlan_id": raw.get("vlanId"),
        "enabled": raw.get("enabled"),
        "one_ip": raw.get("oneIp"),
        "vr_id": raw.get("vrId"),
        "mac_address": raw.get("macAddress"),
        "l2vsn_isid": raw.get("L2vsnISID"),
    }
    if isinstance(ip_obj, dict):
        result["ip_address"] = ip_obj.get("address")
        result["mask_length"] = _reported_mask_length(ip_obj.get("maskLength"), raw.get("oneIp"))
    else:
        result["ip_address"] = None
        result["mask_length"] = None

    # Merge operational state if available
    if state_data:
        result["oper_state"] = state_data.get("operState")
    else:
        result["oper_state"] = None

    return result


def _to_config_shape(entry: dict[str, Any]) -> dict[str, Any]:
    """Project a full interface record onto the config suboptions (gathered/before/after).

    The result is accepted back as a ``config`` entry and re-applying it is a no-op:
    the read-only fields are dropped, ``mask_length`` is None unless the gateway is
    ONE-IP (a mask is only allowed with one_ip=true) and ``vr_id`` is None unless it is
    a valid VRID (the device reports vrId 0 for a gateway without one).
    """
    one_ip = entry.get("one_ip")
    vr_id = entry.get("vr_id")
    valid_vr_id = isinstance(vr_id, int) and not isinstance(vr_id, bool) and 1 <= vr_id <= 255
    return {
        "vlan_id": entry.get("vlan_id"),
        "ip_address": entry.get("ip_address"),
        "mask_length": entry.get("mask_length") if one_ip else None,
        "enabled": entry.get("enabled"),
        "one_ip": one_ip,
        "vr_id": vr_id if valid_vr_id else None,
    }


def _config_list(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Config shape of a list of full interface records (see _to_config_shape)."""
    return [_to_config_shape(entry) for entry in entries]


def _read_only_shape(entry: dict[str, Any]) -> dict[str, Any]:
    """The read-only fields of a full interface record, keyed by its vlan_id (anycast_gateways_state)."""
    ro: dict[str, Any] = {"vlan_id": entry.get("vlan_id")}
    for field in READ_ONLY_FIELDS:
        ro[field] = entry.get(field)
    return ro


def _to_ansible_list(
    raw_list: list[dict[str, Any]],
    state_map: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Convert a list of REST responses to Ansible output format."""
    results = []
    for raw in raw_list:
        vid = raw.get("vlanId")
        s = state_map.get(vid) if state_map else None
        results.append(_to_ansible_output(raw, s))
    return results


# ── Diff / Comparison ─────────────────────────────────────────────────────────
# Compares the "before" (current device state) with the "after" (desired state)
# to determine what changes need to be made. This drives idempotency — if
# before == after, no API calls are needed.


def _compute_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compute differences between before and after states.

    Only compares writable/meaningful fields, excluding the identifier
    and read-only fields.
    """
    diff: dict[str, Any] = {}
    for key in DIFF_FIELDS:
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            diff[key] = {"before": old_val, "after": new_val}
    return diff


def _effective_one_ip(entry: dict[str, Any], current: dict[str, Any] | None) -> bool:
    """one_ip the interface will have: the requested value, else the existing one."""
    one_ip = entry.get("one_ip")
    if one_ip is None and current:
        one_ip = current.get("one_ip")
    return bool(one_ip)


def _immutable_fields_differ(entry: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Check if any immutable (POST-only) fields differ.

    Returns a sorted list of field names that differ, or empty list if all match.
    Only checks fields that the user explicitly provided (not None).
    A mask_length of 0 on a gateway that is not in ONE-IP mode means "not set" and
    equals the None the module reports for it, so it is not a difference.
    """
    one_ip = _effective_one_ip(entry, current)
    diffs = []
    for field in sorted(IMMUTABLE_FIELDS):
        desired = entry.get(field)
        if desired is None:
            continue
        current_val = current.get(field)
        if field == "mask_length":
            desired = _reported_mask_length(desired, one_ip)
            current_val = _reported_mask_length(current_val, one_ip)
        if desired != current_val:
            diffs.append(field)
    return diffs


# ── Payload Builders ──────────────────────────────────────────────────────────
# These functions convert Ansible parameters into the JSON payloads expected
# by the device REST API (POST for create, PATCH for update).


def _build_post_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """Build the AnycastGatewayInterfaceCreate POST payload.

    The POST schema (AnycastGatewayInterfaceCreate) only supports:
      ipAddress, oneIp, vrId.
    The 'enabled' field is NOT part of the POST schema — it must be
    set via a separate PATCH after creation.

    ipAddress.maskLength is sent ONLY when one_ip is true: the device rejects
    a mask on a gateway that is not in ONE-IP mode (HTTP 422, "IP Address mask
    allowed only with Anycast Gateway ONE-IP."), so it is never included
    otherwise, even if the caller passed one.

    Args:
        entry: User config dict with Ansible field names.

    Returns:
        REST-ready dict for POST.
    """
    payload: dict[str, Any] = {}
    one_ip = entry.get("one_ip")

    # IP address (required for POST)
    ip_addr = entry.get("ip_address")
    mask_len = entry.get("mask_length")
    if ip_addr is not None:
        ip_obj: dict[str, Any] = {"address": ip_addr}
        if one_ip and mask_len is not None:
            ip_obj["maskLength"] = mask_len
        payload["ipAddress"] = ip_obj

    # oneIp
    if one_ip is not None:
        payload["oneIp"] = one_ip

    # vrId
    vr_id = entry.get("vr_id")
    if vr_id is not None:
        payload["vrId"] = vr_id

    # NOTE: 'enabled' is intentionally NOT included here.
    # The AnycastGatewayInterfaceCreate schema does not support it.
    # Use _patch_enabled_after_create() after POST to set enabled.

    return payload


def _enabled_applied_after_failure(
    connection: Connection,
    vid: int,
    enabled: bool,
    failure: FeAnycastGwError,
    api_responses: dict[str, Any],
    key_prefix: str,
) -> bool:
    """Re-read VLAN vid after an enabled PATCH failed without an answer. Returns whether it was applied.

    A lost response does not prove the device did not carry the PATCH out, so the
    gateway's ``enabled`` is compared with the requested value. The read is recorded
    as <key_prefix>_verify_filtered_<vid>.

    Raises:
        _EnableStateUnknown: the gateway could not be read back.
    """
    try:
        entry = _config_entry(connection, vid, api_responses, f"{key_prefix}_verify")
    except FeAnycastGwError as exc:
        raise _EnableStateUnknown(
            _extend_msg(
                failure.msg,
                f"The Anycast Gateway on VLAN {vid} could not be read back to check whether the PATCH was "
                f"applied ({exc.msg}).",
            ),
            details={"vlan_id": vid, "patch_error": failure.msg, "read_error": exc.msg},
            extra=failure.extra,
        )
    return isinstance(entry, dict) and entry.get("enabled") is enabled


def _enable_patch_failure(vid: int, exc: ConnectionError) -> FeAnycastGwError:
    """The error for an enabled PATCH that failed with a transport error (see _patch_enabled_retry)."""
    err_text = to_text(exc)
    if "IP interface not found" in err_text:
        err_text = (
            f"{err_text}. The VLAN must have a real IP interface configured "
            f"(via L3 interfaces module or 'interface vlan {vid}; ip address ...') "
            "before Anycast Gateway can be enabled."
        )
    return FeAnycastGwError(
        f"Failed to PATCH enabled on Anycast Gateway vlan_id={vid} after POST creation: {err_text}",
        extra={"code": getattr(exc, "code", None), "err": getattr(exc, "err", None)},
    )


def _patch_enabled_retry(
    connection: Connection,
    vid: int,
    enabled: bool,
    api_responses: dict[str, Any],
    response_key: str,
    notes: list[str] | None = None,
) -> None:
    """PATCH the enabled field after a POST, retrying while the device settles.

    After POST creates an Anycast Gateway interface, Fabric Engine needs a brief
    moment before the IP interface is visible to the PATCH endpoint.
    This function retries the PATCH up to 5 times with a short delay to
    handle this timing issue (HTTP 422 "IP interface not found").

    NOTE: If the VLAN does not have a real IP interface configured (via
    L3 interfaces / ip address command), PATCH enabled will always fail
    with "IP interface not found" regardless of retries. In that case,
    the error message includes guidance to configure L3 interface first.

    A failure without an HTTP answer (see _is_ambiguous_failure) may hide a PATCH that
    was applied, so the gateway is read back (see _enabled_applied_after_failure): if it
    already has the requested ``enabled`` the PATCH counts as applied, a note is added
    to ``notes`` (when given) and nothing is raised.

    Raises:
        FeAnycastGwError: on an in-band error, a non-retryable / final transport error, or a
        failure without an answer that the read-back shows was not applied.
        _EnableStateUnknown: a failure without an answer and the gateway could not be read back.
    """
    patch_path = AG_PATCH_PATH.format(vlan_id=vid)
    patch_payload = {"enabled": enabled}
    max_retries = 5
    retry_delay = 3.0  # seconds

    for attempt in range(max_retries):
        try:
            raw = connection.send_request(patch_payload, path=patch_path, method="PATCH")
            raw = _decode_json_text(raw)
            # Fail fast on in-band error payloads
            err = _extract_error(raw) if isinstance(raw, dict) else None
            if err:
                raise FeAnycastGwError(f"REST API error on PATCH {patch_path}: {err}")
            # Success — record response and return
            api_responses[response_key] = {
                "method": "PATCH",
                "path": patch_path,
                "body": raw,
                "attempt": attempt + 1,
            }
            return
        except ConnectionError as exc:
            code = getattr(exc, "code", None)
            # HTTP 422 = IP interface not yet visible — retry
            if code == 422 and attempt < max_retries - 1:
                _time.sleep(retry_delay)
                continue
            # Final attempt or non-retryable error — fail, unless a lost response hides an applied PATCH
            failure = _enable_patch_failure(vid, exc)
            if not _is_ambiguous_failure(failure, "PATCH"):
                raise failure
            if not _enabled_applied_after_failure(connection, vid, enabled, failure, api_responses, response_key):
                failure.not_applied = True
                raise failure
            api_responses[response_key] = {
                "method": "PATCH",
                "path": patch_path,
                "error": to_text(exc),
                "code": code,
                "attempt": attempt + 1,
            }
            if notes is not None:
                notes.append(
                    f"The PATCH that sets enabled={str(enabled).lower()} on the Anycast Gateway on VLAN {vid} "
                    f"reported an error ({failure.msg}), but the gateway is {'enabled' if enabled else 'disabled'}: "
                    "the PATCH was applied and only its response was lost."
                )
            return


def _enable_unknown_error(vid: int, enabled: bool, exc: _EnableStateUnknown, state: str) -> _GatewayStateUnknown:
    """The task error for an enabled PATCH whose effect could not be read back (``changed`` True).

    ``state`` says what is known about the gateway (e.g. "was created" or "exists").
    """
    value = str(enabled).lower()
    details = dict(exc.details)
    details["state"] = "unknown"
    msg = _extend_msg(
        exc.msg,
        f"The Anycast Gateway on VLAN {vid} {state}, but whether it has enabled={value} is UNKNOWN. Check the "
        f"device and set enabled={value} if it is not (or run the task again).",
    )
    return _GatewayStateUnknown(msg, details=details, extra=exc.extra, changed=True)


def _patch_enabled_after_create(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    enabled: bool,
    api_responses: dict[str, Any],
) -> None:
    """PATCH the enabled field after POST creation (see _patch_enabled_retry); RAISE on error.

    The POST already created the gateway, so every error carries ``changed`` True.
    """
    notes: list[str] = []
    try:
        _patch_enabled_retry(connection, vid, enabled, api_responses, f"patch_enabled_{vid}", notes)
    except _EnableStateUnknown as exc:
        raise _enable_unknown_error(vid, enabled, exc, "was created")
    except FeAnycastGwError as exc:
        # The POST created the gateway: say so, and that the requested enabled state is not set
        exc.msg = _extend_msg(
            exc.msg,
            f"The Anycast Gateway on VLAN {vid} was created, but enabled={str(enabled).lower()} was not applied.",
        )
        exc.changed = True
        raise
    finally:
        for note in notes:
            module.warn(note)


def _build_patch_payload(
    entry: dict[str, Any],
    current: dict[str, Any],
    use_factory_defaults: bool = False,
) -> dict[str, Any] | None:
    """Build PATCH payload for updating enabled status.

    Args:
        entry:                User config dict.
        current:              Current device state dict.
        use_factory_defaults: When True (for replaced/overridden),
            treat omitted ``enabled`` as the factory default (False)
            instead of "no change".

    Returns None if no changes are needed (idempotent).
    """
    desired_enabled = entry.get("enabled")
    if desired_enabled is None:
        if use_factory_defaults:
            desired_enabled = FACTORY_DEFAULTS["enabled"]
        else:
            return None

    current_enabled = current.get("enabled")
    if desired_enabled == current_enabled:
        return None

    return {"enabled": desired_enabled}


# ── Validation ────────────────────────────────────────────────────────────────


def _validate_ip_address(module: AnsibleModule, entry: dict[str, Any]) -> None:
    """Validate that ip_address is a valid IPv4 address."""
    addr = entry.get("ip_address")
    if addr is None:
        return
    try:
        parsed = ipaddress.ip_address(addr)
    except ValueError:
        module.fail_json(msg="Invalid IP address '{0}' for vlan_id {1}".format(addr, entry.get("vlan_id")))
    if parsed.version != 4:
        module.fail_json(
            msg="IPv6 Anycast is not supported. "
            "Address '{0}' for vlan_id {1} must be IPv4".format(addr, entry.get("vlan_id"))
        )


def _validate_mask_length(module: AnsibleModule, entry: dict[str, Any]) -> None:
    """Validate mask_length is within range."""
    mask = entry.get("mask_length")
    if mask is None:
        return
    if not 0 <= mask <= 32:
        module.fail_json(msg="mask_length must be 0-32, got {0} for vlan_id {1}".format(mask, entry.get("vlan_id")))


def _validate_vlan_id(module: AnsibleModule, entry: dict[str, Any]) -> None:
    """Validate vlan_id is within range."""
    vid = entry.get("vlan_id")
    if vid is None:
        return
    if not 1 <= vid <= 4094:
        module.fail_json(msg=f"vlan_id must be 1-4094, got {vid}")


def _validate_vr_id(module: AnsibleModule, entry: dict[str, Any]) -> None:
    """Validate vr_id is within range."""
    vr_id = entry.get("vr_id")
    if vr_id is None:
        return
    if not 1 <= vr_id <= 255:
        module.fail_json(msg="vr_id must be 1-255, got {0} for vlan_id {1}".format(vr_id, entry.get("vlan_id")))


def _validate_mask_requires_one_ip(module: AnsibleModule, entry: dict[str, Any]) -> None:
    """Validate that mask_length requires one_ip=true (Fabric Engine constraint).

    Only enforced when one_ip is explicitly provided in the entry.
    If one_ip is omitted, the existing device value may already be true.
    """
    mask = entry.get("mask_length")
    if mask is None:
        return
    one_ip = entry.get("one_ip")
    if one_ip is None:
        # one_ip not specified — skip validation (device may already have it set)
        return
    if not one_ip:
        module.fail_json(msg=MASK_REQUIRES_ONE_IP_MSG.format(entry.get("vlan_id")))


def _validate_entry(module: AnsibleModule, entry: dict[str, Any]) -> None:
    """Run all validations on a single config entry."""
    _validate_vlan_id(module, entry)
    _validate_ip_address(module, entry)
    _validate_mask_length(module, entry)
    _validate_vr_id(module, entry)
    _validate_mask_requires_one_ip(module, entry)


# ── Predict After State (check mode) ─────────────────────────────────────────


def _predict_after_create(entry: dict[str, Any]) -> dict[str, Any]:
    """Predict the after state for a newly created interface."""
    # Ansible pre-populates every declared suboption, so these keys are always
    # present and get()'s default never fires -- an omitted field arrives as
    # None. Test the value instead, the way _predict_after_patch() does.
    # Otherwise check mode predicts enabled/one_ip as None while the device
    # actually settles on the factory defaults, and the diff is misleading.
    enabled = entry.get("enabled")
    one_ip = entry.get("one_ip")
    one_ip = FACTORY_DEFAULTS["one_ip"] if one_ip is None else one_ip
    predicted: dict[str, Any] = {
        "vlan_id": entry["vlan_id"],
        "ip_address": entry.get("ip_address"),
        # A gateway that is not ONE-IP has no mask (the device reports it as not set)
        "mask_length": _reported_mask_length(entry.get("mask_length"), one_ip),
        "enabled": FACTORY_DEFAULTS["enabled"] if enabled is None else enabled,
        "one_ip": one_ip,
        "vr_id": entry.get("vr_id"),
        "mac_address": None,
        "l2vsn_isid": None,
        "oper_state": None,
    }
    return predicted


def _predict_after_patch(
    entry: dict[str, Any],
    current: dict[str, Any],
    use_factory_defaults: bool = False,
) -> dict[str, Any]:
    """Predict the after state for a PATCH (enabled toggle)."""
    predicted = dict(current)
    desired_enabled = entry.get("enabled")
    if desired_enabled is None and use_factory_defaults:
        desired_enabled = FACTORY_DEFAULTS["enabled"]
    if desired_enabled is not None:
        predicted["enabled"] = desired_enabled
    return predicted


def _predict_after_replaced(entry: dict[str, Any]) -> dict[str, Any]:
    """Predict the after state for replaced (DELETE + re-POST)."""
    return _predict_after_create(entry)


# ── Handler helpers (extracted from main to reduce cyclomatic complexity) ─────
# Each function below implements one Ansible "state" (gathered, deleted,
# merged, replaced, overridden). They are called from main() based on the
# user's chosen state. This keeps main() short and readable.


def _handle_gathered(
    module: AnsibleModule,
    connection: Connection,
    gather_filter: list[int],
    result: dict[str, Any],
) -> None:
    """Handle the GATHERED state — read-only, return current state."""
    raw_list = _fetch_all_interfaces(module, connection, result["api_responses"])
    state_map = _fetch_state_interfaces(module, connection, result["api_responses"])
    all_ifs = _to_ansible_list(raw_list, state_map)

    if gather_filter:
        filter_set = set(gather_filter)
        all_ifs = [i for i in all_ifs if i["vlan_id"] in filter_set]

    all_ifs = sorted(all_ifs, key=lambda x: x["vlan_id"])
    # gathered is exactly what config accepts; the read-only fields go to anycast_gateways_state
    result["gathered"] = _config_list(all_ifs)
    result["anycast_gateways_state"] = [_read_only_shape(i) for i in all_ifs]
    result.pop("anycast_gateways", None)
    module.exit_json(**result)


def _targeted_after(
    connection: Connection,
    vid: int,
    state_map: dict[int, Any],
    api_responses: dict[str, Any],
    cache: dict[int, dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Output of ONE VLAN that the bulk read after the change did not return, or None.

    The bulk GET can omit recently created interfaces (see _try_fallback_get), so the
    VLAN is read with the targeted GET (recorded as after_get_filtered_<vid>). A read
    that fails or does not return it gives None and the caller keeps the prediction.
    ``cache`` lets the per-interface and the module-level 'after' share one read.
    """
    if vid not in cache:
        try:
            raw = _filtered_get_raw(connection, vid, api_responses, f"after_get_filtered_{vid}")
            iface = _extract_iface_from_response(raw, vid)
        except FeAnycastGwError:
            # The writes are done: a failed read must not fail the task
            iface = None
        cache[vid] = _to_ansible_output(iface, state_map.get(vid)) if iface else None
    return cache[vid]


def _missing_after_entries(
    module: AnsibleModule,
    connection: Connection,
    after: list[dict[str, Any]],
    state_map: dict[int, Any],
    result: dict[str, Any],
    cache: dict[int, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Entries for the interfaces of this task that the final bulk read did not return.

    Every listed interface that should exist after the task (its per-interface
    'after' is not empty) and is missing from ``after`` is read with the targeted
    GET; if that does not return it either, its predicted 'after' is used and a
    warning says so. Interfaces this task deleted stay absent.
    """
    present = {item.get("vlan_id") for item in after}
    missing: list[dict[str, Any]] = []
    for gw_res in result["anycast_gateways"]:
        vid = gw_res["vlan_id"]
        if not gw_res.get("after") or vid in present:
            # Deleted by this task, or returned by the bulk read
            continue
        found = _targeted_after(connection, vid, state_map, result["api_responses"], cache)
        if found is None:
            found = gw_res["after"]
            module.warn(
                f"The Anycast Gateway on VLAN {vid} was not returned by the device after the change; "
                "its entry in 'after' is the predicted state."
            )
        missing.append(found)
        present.add(vid)
    return missing


def _final_after_state(
    module: AnsibleModule,
    connection: Connection,
    current_map: dict[int, dict[str, Any]],
    result: dict[str, Any],
    cache: dict[int, dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    """Return the module-level 'after' list for an action state.

    * nothing changed: equal to 'before';
    * check mode: the PREDICTED state (current state with every per-interface
      'after' applied, deleted interfaces removed);
    * real change: re-read from the device; an interface of the task that the bulk
      read omits is read with the targeted GET, else predicted; if the re-read
      fails, the whole list is the prediction and a warning says so.
    """
    if not result["changed"]:
        return sorted(current_map.values(), key=lambda x: x["vlan_id"])

    def _predict() -> list[dict[str, Any]]:
        amap = dict(current_map)
        for gw_res in result["anycast_gateways"]:
            vid = gw_res["vlan_id"]
            if gw_res.get("after"):
                amap[vid] = gw_res["after"]
            else:
                amap.pop(vid, None)
        return sorted(amap.values(), key=lambda x: x["vlan_id"])

    if module.check_mode:
        return _predict()
    api_responses = result["api_responses"]
    try:
        # raising=True: a failed read must reach the fallback below, not end the task after the writes
        final_raw = _fetch_all_interfaces(module, connection, api_responses, "after_all", raising=True)
        final_state = _fetch_state_interfaces(module, connection, api_responses, "state_after_all", raising=True)
    except FeAnycastGwError as exc:
        module.warn(
            f"Could not read the Anycast Gateway configuration back after the change ({exc.msg}); "
            "'after' (and the --diff 'after') is the predicted state."
        )
        return _predict()
    after = _to_ansible_list(final_raw, final_state)
    # The bulk read can omit recently created interfaces: complete it
    after += _missing_after_entries(module, connection, after, final_state, result, {} if cache is None else cache)
    return sorted(after, key=lambda x: x["vlan_id"])


def _finish(module: AnsibleModule, result: dict[str, Any]) -> None:
    """Add the diff pair (when --diff is set) and end the task successfully."""
    # Diff mode (--diff): Ansible renders the before/after pair itself. It is
    # populated whether or not anything changed (identical lists render as no
    # diff) and in check mode 'after' is the predicted state.
    if module._diff:
        result["diff"] = {"before": result["before"], "after": result["after"]}
    module.exit_json(**result)


def _handle_deleted(
    module: AnsibleModule,
    connection: Connection,
    config: list[dict[str, Any]],
    current_map: dict[int, dict[str, Any]],
    state_map: dict[int, Any],
    result: dict[str, Any],
) -> None:
    """Handle the DELETED state — remove interfaces."""
    if config:
        vids_to_delete = [e["vlan_id"] for e in config]
    else:
        # Delete ALL anycast gateway interfaces
        vids_to_delete = list(current_map.keys())

    for vid in vids_to_delete:
        gw_result: dict[str, Any] = {"vlan_id": vid}

        if vid not in current_map:
            gw_result["before"] = {}
            gw_result["after"] = {}
            gw_result["changed"] = False
            gw_result["differences"] = {}
            result["anycast_gateways"].append(gw_result)
            continue

        gw_result["before"] = current_map[vid]
        gw_result["after"] = {}
        gw_result["changed"] = True
        # Device state before this interface is touched (reported if a lost disable is undone)
        changed_before = bool(result["changed"])
        result["changed"] = True

        if not module.check_mode:
            _disable_and_delete(
                module,
                connection,
                vid,
                current_map.get(vid),
                result["api_responses"],
                "delete",
                changed_before,
            )

        gw_result["differences"] = _compute_diff(gw_result["before"], gw_result["after"])
        result["anycast_gateways"].append(gw_result)

    # Module-level "after" state (always reported)
    result["after"] = _final_after_state(module, connection, current_map, result)
    _finish(module, result)


def _handle_overridden_prepass(
    module: AnsibleModule,
    connection: Connection,
    config: list[dict[str, Any]],
    current_map: dict[int, dict[str, Any]],
    result: dict[str, Any],
) -> None:
    """OVERRIDDEN pre-pass: delete interfaces not in desired config."""
    config_vids = {e["vlan_id"] for e in config}
    for vid, current in current_map.items():
        if vid in config_vids:
            continue
        # Delete this interface — not in desired config
        gw_result: dict[str, Any] = {
            "vlan_id": vid,
            "before": current,
            "after": {},
            "changed": True,
        }
        # Device state before this interface is touched (reported if a lost disable is undone)
        changed_before = bool(result["changed"])
        result["changed"] = True

        if not module.check_mode:
            _disable_and_delete(
                module,
                connection,
                vid,
                current,
                result["api_responses"],
                "override_delete",
                changed_before,
            )

        gw_result["differences"] = _compute_diff(gw_result["before"], gw_result["after"])
        result["anycast_gateways"].append(gw_result)


def _fallback_filtered_get(connection: Connection, vid: int, result: dict[str, Any]) -> Any:
    """Strategy 1 of the fallback: the list endpoint filtered with ?vlan_id=N.

    The OpenAPI spec confirms: GET /v0/configuration/anycast-gateway/interfaces?vlan_id=N
    Returns the decoded response (None when the device reports not-found).

    Raises:
        FeAnycastGwError: the read failed (``changed`` is set by _handle_merge_replace: earlier
        entries of the task may have modified the device).
    """
    return _filtered_get_raw(connection, vid, result["api_responses"], f"get_filtered_{vid}")


def _filtered_get_raw(connection: Connection, vid: int, api_responses: dict[str, Any], response_key: str) -> Any:
    """GET /v0/configuration/anycast-gateway/interfaces?vlan_id=N and RAISE on failure.

    HTTP 404/422 mean "not found" and return None, whether the device raises them as an
    HTTP error or returns them in-band ({"statusCode": 404}). The response (or the error)
    is recorded in api_responses under response_key.

    Raises:
        FeAnycastGwError: any other transport error (code/err in ``extra``) or an in-band error body.
    """
    fallback_path = AG_LIST_PATH + f"?vlan_id={vid}"
    single_raw = None
    try:
        single_raw = connection.send_request(None, path=fallback_path, method="GET")
    except ConnectionError as exc:
        code = getattr(exc, "code", None)
        # Only treat not-found / transient cases as "missing"; raise on everything else.
        if code not in (404, 422):
            api_responses[response_key] = {"method": "GET", "path": fallback_path, "error": to_text(exc), "code": code}
            raise FeAnycastGwError(
                f"REST API call failed: GET {fallback_path}: {to_text(exc)}",
                extra={"code": code, "err": getattr(exc, "err", None)},
            )
        single_raw = None

    # Parse string responses
    single_raw = _decode_json_text(single_raw)

    api_responses[response_key] = {
        "method": "GET",
        "path": fallback_path,
        "body": single_raw,
    }

    # An in-band 404/422 body means "not found" exactly like the HTTP 404/422 above; it is
    # checked before _extract_error(), which would report it as an error
    if _is_not_found_body(single_raw):
        return None

    # Fail fast if the device returned any other in-band error payload.
    if isinstance(single_raw, dict):
        err = _extract_error(single_raw)
        if err:
            raise FeAnycastGwError(f"REST API error on fallback GET {fallback_path}: {err}")
    return single_raw


def _gateway_present(connection: Connection, vid: int, api_responses: dict[str, Any], key_prefix: str) -> bool:
    """Whether the device reports an Anycast Gateway on VLAN vid. RAISES when it cannot be read.

    Same two strategies as _try_fallback_get(): the filtered config GET, then the
    state endpoint, which may know the interface even if the config read does not.
    Both treat NOT_FOUND_CODES (HTTP status or in-band body) as "no gateway".
    """
    if _config_entry(connection, vid, api_responses, key_prefix) is not None:
        return True
    try:
        state_raw = _request(
            connection,
            method="GET",
            path=AG_STATE_PATH,
            api_responses=api_responses,
            response_key=f"{key_prefix}_state_{vid}",
        )
    except FeAnycastGwError as exc:
        # Not found, as for the filtered GET (_filtered_get_raw): the device reports no gateway
        if _http_status(exc) in NOT_FOUND_CODES or _is_not_found_body(exc.details.get("response")):
            return False
        raise
    return _find_in_state_payload(state_raw, vid) is not None


def _config_entry(connection: Connection, vid: int, api_responses: dict[str, Any], key_prefix: str) -> Any:
    """The configuration entry of VLAN vid (raw device fields) or None when it has none. RAISES when unreadable.

    Only the filtered config GET is used: the state endpoint reports neither the
    addresses nor ``enabled``. Recorded as <key_prefix>_filtered_<vid>.
    """
    raw = _filtered_get_raw(connection, vid, api_responses, f"{key_prefix}_filtered_{vid}")
    return _extract_iface_from_response(raw, vid)


def _find_in_state_payload(state_raw: Any, vid: int) -> dict[str, Any] | None:
    """Find the entry of one VLAN in a state-endpoint response (a list, or a dict wrapping lists)."""
    if isinstance(state_raw, list):
        candidates = [state_raw]
    elif isinstance(state_raw, dict):
        wrap_keys = ("data", "items", "state", "interfaces", "anycast_gateways")
        candidates = [state_raw.get(wrap_key) for wrap_key in wrap_keys]
    else:
        return None
    for entries in candidates:
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("vlanId") == vid:
                return entry
    return None


def _fallback_state_get(connection: Connection, vid: int, result: dict[str, Any]) -> dict[str, Any] | None:
    """Strategy 2 of the fallback: the state endpoint may know the interface even if config does not."""
    state_raw = None
    try:
        state_raw = connection.send_request(None, path=AG_STATE_PATH, method="GET")
    except ConnectionError:
        state_raw = None

    state_raw = _decode_json_text(state_raw)

    result["api_responses"][f"get_state_fallback_{vid}"] = {
        "method": "GET",
        "path": AG_STATE_PATH,
        "body": state_raw,
    }

    # The state endpoint returns a list — find our VLAN
    return _find_in_state_payload(state_raw, vid)


def _try_fallback_get(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    state_map: dict[int, Any],
    current_map: dict[int, dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    """Try a filtered GET when bulk GET missed an interface.

    The bulk GET /v0/configuration/anycast-gateway/interfaces may not return
    recently-created interfaces due to a known Fabric Engine API timing issue.  This
    function uses the same endpoint with the vlan_id query parameter to ask
    the device specifically about the target VLAN.  If that also fails, it
    falls back to the state endpoint as a last resort.

    Returns the parsed current output if found, else None.
    """
    single_raw = _fallback_filtered_get(connection, vid, result)

    # Try to extract interface data from the filtered response
    iface_data = _extract_iface_from_response(single_raw, vid)

    # Strategy 2: If filtered config GET failed, try the state endpoint.
    if iface_data is None:
        iface_data = _fallback_state_get(connection, vid, result)

    if iface_data and isinstance(iface_data, dict) and iface_data.get("vlanId") == vid:
        current = _to_ansible_output(iface_data, state_map.get(vid))
        current_map[vid] = current
        # Update module-level "before" to include
        # this interface missed by the bulk GET.
        result["before"] = sorted(
            current_map.values(),
            key=lambda x: x["vlan_id"],
        )
        return current
    return None


def _extract_iface_from_response(raw: Any, vid: int) -> dict[str, Any] | None:
    """Extract interface data for a specific vlan_id from a REST response."""
    if raw is None:
        return None
    # Direct list response
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and entry.get("vlanId") == vid:
                return entry
        return None
    # Dict response — check if it IS the interface
    if isinstance(raw, dict):
        if raw.get("vlanId") == vid:
            return raw
        # Check for error responses
        err = _extract_error(raw)
        if err:
            return None
        # Unwrap common wrappers
        for wrap_key in ("data", "items", "interfaces", "anycast_gateways"):
            wrapped = raw.get(wrap_key)
            if isinstance(wrapped, list):
                for entry in wrapped:
                    if isinstance(entry, dict) and entry.get("vlanId") == vid:
                        return entry
            elif isinstance(wrapped, dict) and wrapped.get("vlanId") == vid:
                return wrapped
    return None


# ── Create path (interface does not exist yet) ────────────────────────────────


def _check_mask_needs_one_ip(entry: dict[str, Any], one_ip: bool, vid: int) -> None:
    """Reject a requested mask_length for an interface that will not be in ONE-IP mode.

    The device refuses it (HTTP 422), and the module never sends a mask for a
    gateway that is not ONE-IP, so the request has to fail here, not silently lose
    the mask. A mask_length of 0 means "not set" and is tolerated.

    Raises:
        FeAnycastGwError: mask_length (non-zero) requested while one_ip is not true.
    """
    if entry.get("mask_length") and not one_ip:
        raise FeAnycastGwError(MASK_REQUIRES_ONE_IP_MSG.format(vid))


def _check_create_request(entry: dict[str, Any], vid: int, changed_before: bool) -> None:
    """Validate the POST request for a MISSING interface locally, before anything is sent.

    Same rules as the re-create (_prepare_recreate): no mask without ONE-IP, and a
    ONE-IP gateway needs a mask_length. A missing interface has no current state to
    take a mask over from, so it must come from the entry itself.

    Raises:
        FeAnycastGwError: the device cannot create this request; ``changed`` is the state before this entry.
    """
    one_ip = bool(entry.get("one_ip"))
    try:
        # A mask without ONE-IP can never be created
        _check_mask_needs_one_ip(entry, one_ip, vid)
        # ONE-IP without a mask is rejected exactly like the re-create path does
        if one_ip and entry.get("mask_length") is None:
            raise FeAnycastGwError(MASK_REQUIRED_FOR_ONE_IP_MSG.format("create", vid, ""))
    except FeAnycastGwError as exc:
        exc.changed = changed_before
        raise


def _is_one_ip_conflict(entry: dict[str, Any], text: str) -> bool:
    """True when a ONE-IP create was refused because the VLAN already has an IP interface."""
    return bool(entry.get("one_ip")) and (
        "IP interface already configured" in text or "already configured" in text.lower()
    )


def _one_ip_conflict_msg(vid: int, text: str) -> str:
    """Clear error text for the ONE-IP vs existing-IP-interface conflict."""
    return (
        "Cannot create Anycast Gateway with one_ip=true "
        f"on VLAN {vid}: {text}. ONE-IP mode requires the VLAN "
        "to have no existing IP interface. Remove the IP "
        "interface first (using extreme_fe_l3_interfaces "
        "with state=deleted) or use one_ip=false."
    )


def _check_post_body(entry: dict[str, Any], vid: int, path: str, parsed: Any) -> None:
    """Raise if the POST response carries an in-band error payload (a definitive rejection).

    Raises:
        FeAnycastGwError: the device refused the POST (``changed`` is set by _handle_merge_replace).
    """
    if not isinstance(parsed, dict):
        return
    err = _extract_error(parsed)
    if not err:
        return
    if _is_one_ip_conflict(entry, err):
        raise FeAnycastGwError(_one_ip_conflict_msg(vid, err))
    raise FeAnycastGwError(f"POST {path} returned an error: {err}")


def _created_after_lost_post(
    connection: Connection,
    vid: int,
    failure: FeAnycastGwError,
    post_payload: dict[str, Any],
    api_responses: dict[str, Any],
) -> bool:
    """Re-read VLAN vid after the POST of a MISSING interface failed without an answer. Returns whether it was created.

    Only a config entry with the requested immutable values (see _matches_post_payload)
    counts. The read is recorded as create_verify_post_filtered_<vid>.

    Raises:
        _GatewayStateUnknown: the read failed as well (see _state_unknown, purpose "create").
    """
    try:
        entry = _config_entry(connection, vid, api_responses, "create_verify_post")
    except FeAnycastGwError as exc:
        raise _state_unknown(vid, "POST", failure, {}, exc.msg, "create")
    return _matches_post_payload(entry, post_payload)


def _post_new_interface(
    module: AnsibleModule, connection: Connection, vid: int, entry: dict[str, Any], result: dict[str, Any]
) -> None:
    """POST a new interface, with a clear error for the one_ip conflict; RAISE on failure.

    A failure without an HTTP answer (or the 409 of a plugin retry, see _is_ambiguous_failure)
    may hide a POST that was applied: if the VLAN now has a gateway with the requested values
    (see _created_after_lost_post), a warning is issued and the create carries on.

    Raises:
        FeAnycastGwError: the POST failed and the gateway was not created (``changed`` is set by
        _handle_merge_replace). _GatewayStateUnknown: the VLAN could not be read back.
    """
    api_responses = result["api_responses"]
    post_payload = _build_post_payload(entry)
    path = AG_VLAN_PATH.format(vlan_id=vid)

    # Wrap POST to provide a clear error for one_ip conflict.
    # We call connection.send_request directly (rather than
    # _call_api) so that ConnectionError is catchable here —
    # _call_api calls fail_json on HTTP errors immediately.
    try:
        post_raw = connection.send_request(post_payload, path=path, method="POST")
    except ConnectionError as exc:
        err_msg = to_text(exc)
        code = getattr(exc, "code", None)
        api_responses[f"post_{vid}"] = {"method": "POST", "path": path, "error": err_msg, "code": code}
        if _is_one_ip_conflict(entry, err_msg):
            raise FeAnycastGwError(_one_ip_conflict_msg(vid, err_msg))
        failure = FeAnycastGwError(
            f"REST API call failed: POST {path}: {err_msg}", extra={"code": code, "err": getattr(exc, "err", None)}
        )
        if not _is_ambiguous_failure(failure, "POST") or not _created_after_lost_post(
            connection, vid, failure, post_payload, api_responses
        ):
            raise failure
        module.warn(
            f"The POST of the new Anycast Gateway on VLAN {vid} reported an error ({failure.msg}), but the gateway "
            "exists with the requested configuration: the create was applied and only its response was lost."
        )
    else:
        # Parse and record successful response
        parsed = _decode_json_text(post_raw)
        api_responses[f"post_{vid}"] = {"method": "POST", "path": path, "body": parsed}
        _check_post_body(entry, vid, path, parsed)


def _create_missing_interface(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    entry: dict[str, Any],
    gw_result: dict[str, Any],
    modified_vids: list[int],
    result: dict[str, Any],
) -> None:
    """Interface does not exist — CREATE (POST), then PATCH enabled if requested.

    A failure before or of the POST leaves ``changed`` to _handle_merge_replace (the state
    before this entry); a failure of the enabled PATCH after the POST carries ``changed`` True.
    """
    # Validate required fields for POST (interface creation)
    if entry.get("ip_address") is None:
        raise FeAnycastGwError(f"ip_address is required to create a new Anycast Gateway interface (vlan_id={vid})")
    # Reject a request the device cannot create before anything is sent and before 'changed' is set
    _check_create_request(entry, vid, bool(result["changed"]) and not module.check_mode)

    gw_result["before"] = {}
    result["changed"] = True
    gw_result["changed"] = True

    if not module.check_mode:
        modified_vids.append(vid)
        _post_new_interface(module, connection, vid, entry, result)

        # POST does not support 'enabled' — if enabled=true was
        # requested, PATCH it separately (with retry for timing).
        desired_enabled = entry.get("enabled")
        if desired_enabled is not None and desired_enabled != FACTORY_DEFAULTS["enabled"]:
            _patch_enabled_after_create(module, connection, vid, desired_enabled, result["api_responses"])

    gw_result["after"] = _predict_after_create(entry)


# ── Replace path (interface exists) ───────────────────────────────────────────


def _merge_immutable_from_current(entry: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Complete a replaced/overridden entry so the POST body after the DELETE is whole.

    Omitted immutable fields are taken from the existing interface. mask_length is
    taken over ONLY when the resulting interface is in ONE-IP mode (one_ip from the
    entry, else from the existing interface); otherwise it is None, because a
    gateway that is not ONE-IP has no mask. An omitted ``enabled`` resets to the
    factory default (False), it is not preserved from the existing interface.
    """
    merged_entry = dict(entry)
    for field in IMMUTABLE_FIELDS - {"mask_length"}:
        if merged_entry.get(field) is None and current.get(field) is not None:
            merged_entry[field] = current[field]
    if merged_entry.get("one_ip"):
        if merged_entry.get("mask_length") is None and current.get("mask_length") is not None:
            merged_entry["mask_length"] = current["mask_length"]
    else:
        merged_entry["mask_length"] = None
    if merged_entry.get("enabled") is None:
        merged_entry["enabled"] = FACTORY_DEFAULTS["enabled"]
    return merged_entry


def _validate_recreate_payload(vid: int, merged_entry: dict[str, Any], payload: dict[str, Any]) -> None:
    """Validate the re-create POST body locally, BEFORE the interface is deleted.

    Raises:
        FeAnycastGwError: the body is incomplete or carries a mask without ONE-IP.
    """
    ip_obj = payload.get("ipAddress")
    if not ip_obj:
        raise FeAnycastGwError(
            f"ip_address is required to re-create Anycast Gateway vlan_id={vid}; nothing was changed"
        )
    one_ip = bool(merged_entry.get("one_ip"))
    if one_ip and "maskLength" not in ip_obj:
        raise FeAnycastGwError(
            MASK_REQUIRED_FOR_ONE_IP_MSG.format("re-create", vid, " (it is not set on the existing interface)")
        )
    if not one_ip and "maskLength" in ip_obj:
        raise FeAnycastGwError(MASK_REQUIRES_ONE_IP_MSG.format(vid))


def _prepare_recreate(
    vid: int, entry: dict[str, Any], current: dict[str, Any], changed_before: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build and validate the re-create request. Returns (merged_entry, post_payload).

    Runs before the DELETE, so a request that cannot succeed never reaches the device.
    """
    try:
        _check_mask_needs_one_ip(entry, _effective_one_ip(entry, current), vid)
        merged_entry = _merge_immutable_from_current(entry, current)
        post_payload = _build_post_payload(merged_entry)
        _validate_recreate_payload(vid, merged_entry, post_payload)
    except FeAnycastGwError as exc:
        exc.changed = changed_before
        raise
    return merged_entry, post_payload


def _extend_msg(msg: str, suffix: str) -> str:
    """Append a sentence to an error message, adding the full stop it may lack."""
    return f"{msg if msg.endswith(('.', '!', '?')) else msg + '.'} {suffix}"


def _after_failed_delete(
    connection: Connection,
    vid: int,
    failure: FeAnycastGwError,
    api_responses: dict[str, Any],
    changed_before: bool,
) -> FeAnycastGwError:
    """The DELETE failed after the interface was disabled: re-enable it. Returns the error to raise.

    A re-enable that fails without an answer is checked against the device (see
    _patch_enabled_retry); if it cannot be read back, the message says the enabled state
    is unknown and ``details`` hold rollback=unknown, state=unknown and read_error.
    """
    details = dict(failure.details)
    details.update({"vlan_id": vid, "rollback": "re-enabled"})
    try:
        _patch_enabled_retry(connection, vid, True, api_responses, f"replace_rollback_enable_{vid}")
    except _EnableStateUnknown as exc:
        details.update({"rollback": "unknown", "state": "unknown", "rollback_error": exc.msg})
        details["read_error"] = exc.details.get("read_error")
        msg = _extend_msg(
            failure.msg,
            f"The original Anycast Gateway on VLAN {vid} was disabled for the delete and was not deleted, but "
            f"whether it could be re-enabled is UNKNOWN ({exc.msg}). Check the device and enable it if it is "
            "disabled.",
        )
        return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=True)
    except FeAnycastGwError as exc:
        details["rollback"] = "not re-enabled"
        details["rollback_error"] = exc.msg
        msg = _extend_msg(
            failure.msg,
            f"The original Anycast Gateway on VLAN {vid} was disabled for the delete and could NOT be "
            f"re-enabled ({exc.msg}); it is still configured but disabled.",
        )
        return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=True)
    msg = _extend_msg(
        failure.msg,
        f"The original Anycast Gateway on VLAN {vid} was disabled for the delete and has been re-enabled; "
        "it was not deleted.",
    )
    return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=changed_before)


def _state_unknown(
    vid: int,
    method: str,
    failure: FeAnycastGwError,
    current: dict[str, Any],
    read_error: str,
    purpose: str = "recreate",
) -> _GatewayStateUnknown:
    """The error for a failed request whose effect could not be read back from the device.

    ``changed`` is True (nothing proves the device was not modified) and the details
    hold what is needed to put the original back by hand.

    purpose "recreate" (replaced/overridden re-create) advises re-creating the original
    if the VLAN has no gateway; purpose "delete" (state=deleted, the overridden pre-pass)
    wanted the gateway removed, so it advises running the task again if it is still there;
    purpose "create" (the POST of a missing interface) had no original, so the details hold
    no original_payload / original_enabled and it advises running the task again.
    """
    original_payload = _build_post_payload(current)
    original_enabled = bool(current.get("enabled"))
    details = dict(failure.details)
    details.update(
        {
            "vlan_id": vid,
            "state": "unknown",
            f"{method.lower()}_error": failure.msg,
            "read_error": read_error,
        }
    )
    if purpose != "create":
        details.update({"original_payload": original_payload, "original_enabled": original_enabled})
    if purpose == "create":
        advice = (
            f"The state of the Anycast Gateway on VLAN {vid} is UNKNOWN: the POST that creates it failed and the "
            f"VLAN could not be read back ({read_error}), so the POST may or may not have been applied. Check the "
            "device, then run the task again."
        )
    elif method == "PATCH":
        # Only the disable before a delete is checked this way: the gateway still exists, maybe disabled
        advice = (
            f"The state of the Anycast Gateway on VLAN {vid} is UNKNOWN: the PATCH that disables it for the "
            f"delete failed and its state could not be read back ({read_error}), so it may have been left "
            "disabled. Check the device and enable it if it is disabled."
        )
    elif purpose == "delete":
        # The task asked for the gateway to be removed: an empty VLAN is the wanted result,
        # so the open question is whether the gateway is still there
        advice = (
            f"The state of the Anycast Gateway on VLAN {vid} is UNKNOWN: the {method} failed and the VLAN could "
            f"not be read back ({read_error}), so the {method} may or may not have been applied. Check the device; "
            f"if VLAN {vid} still has an Anycast Gateway, run the task again to delete it (it may have been left "
            "disabled)."
        )
    else:
        advice = (
            f"The state of the Anycast Gateway on VLAN {vid} is UNKNOWN: the {method} failed and the VLAN could "
            f"not be read back ({read_error}), so the {method} may or may not have been applied. Check the device; "
            f"if VLAN {vid} has no Anycast Gateway, re-create the original by hand with the POST body in "
            "details.original_payload" + (" and enable it." if original_enabled else ".")
        )
    return _GatewayStateUnknown(_extend_msg(failure.msg, advice), details=details, extra=failure.extra, changed=True)


def _gateway_exists_after_failure(
    connection: Connection,
    vid: int,
    method: str,
    failure: FeAnycastGwError,
    current: dict[str, Any],
    api_responses: dict[str, Any],
    key_prefix: str = "replace_verify",
    purpose: str = "recreate",
) -> bool:
    """Re-read VLAN vid after a DELETE failed. Returns whether a gateway exists.

    A failed request does not prove the device did not apply it: a transport error
    can lose the response of a DELETE that was carried out. The caller decides
    from what the device reports now. The reads are recorded in api_responses as
    <key_prefix>_<method>_filtered_<vid> and <key_prefix>_<method>_state_<vid>
    (re-create: replace_verify_delete_*; state=deleted / the overridden pre-pass:
    delete_verify_delete_* / override_delete_verify_delete_*).

    Raises:
        _GatewayStateUnknown: the read failed as well (see _state_unknown; purpose picks its advice).
    """
    try:
        return _gateway_present(connection, vid, api_responses, f"{key_prefix}_{method.lower()}")
    except FeAnycastGwError as exc:
        raise _state_unknown(vid, method, failure, current, exc.msg, purpose)


def _matches_post_payload(raw: Any, post_payload: dict[str, Any]) -> bool:
    """Whether a config entry read from the device has the immutable values of a POST body.

    Used to tell the replacement from the original (or a stale copy of it): at
    least one of these values differs between the two, or no re-create was needed.
    """
    if not isinstance(raw, dict):
        return False
    want_ip = post_payload.get("ipAddress") or {}
    have_ip = raw.get("ipAddress") or {}
    if not isinstance(have_ip, dict) or have_ip.get("address") != want_ip.get("address"):
        return False
    if bool(raw.get("oneIp")) != bool(post_payload.get("oneIp")):
        return False
    # vrId and maskLength are compared only when the POST body sets them
    if "vrId" in post_payload and raw.get("vrId") != post_payload["vrId"]:
        return False
    return "maskLength" not in want_ip or have_ip.get("maskLength") == want_ip["maskLength"]


def _replacement_created_after_failure(
    connection: Connection,
    vid: int,
    failure: FeAnycastGwError,
    current: dict[str, Any],
    post_payload: dict[str, Any],
    api_responses: dict[str, Any],
) -> bool:
    """Re-read VLAN vid after the POST of a re-create failed. Returns whether the REPLACEMENT exists.

    The mere existence of a gateway does not prove the POST was applied: the device
    may still show the original. Only a config entry with the requested immutable
    values (see _matches_post_payload) counts. The read is recorded in api_responses
    as replace_verify_post_filtered_<vid>.

    Raises:
        _GatewayStateUnknown: the read failed as well (see _state_unknown).
    """
    try:
        entry = _config_entry(connection, vid, api_responses, "replace_verify_post")
    except FeAnycastGwError as exc:
        raise _state_unknown(vid, "POST", failure, current, exc.msg)
    return _matches_post_payload(entry, post_payload)


def _after_failed_disable(
    connection: Connection,
    vid: int,
    failure: FeAnycastGwError,
    current: dict[str, Any],
    api_responses: dict[str, Any],
    key_prefix: str,
    changed_before: bool,
    reenable: bool = True,
) -> FeAnycastGwError | None:
    """The disable PATCH before a DELETE got no answer: read the gateway back. Returns the error to raise.

    Still enabled: the disable was not applied, the original error is returned with
    ``changed`` = ``changed_before`` (nothing changed on this VLAN, but earlier entries
    of the task may have modified the device). Disabled: the disable was applied and
    only its response was lost, so the gateway is re-enabled (``changed`` is then
    ``changed_before``, as for a successful rollback, or True when the re-enable fails).
    With ``reenable`` False (the rollback disabling the replacement for its DELETE) a
    disabled gateway is what the caller wants: None is returned and the DELETE goes on.
    The read is recorded as <key_prefix>_verify_patch_filtered_<vid>, the re-enable as
    <key_prefix>_rollback_enable_<vid>.

    Raises:
        _GatewayStateUnknown: the gateway could not be read back, or the read did not report it.
    """
    try:
        entry = _config_entry(connection, vid, api_responses, f"{key_prefix}_verify_patch")
    except FeAnycastGwError as exc:
        raise _state_unknown(vid, "PATCH", failure, current, exc.msg)
    enabled = entry.get("enabled") if isinstance(entry, dict) else None
    if enabled is True:
        # The device did not apply the disable: nothing was changed on this VLAN; keep what earlier entries changed
        failure.changed = changed_before
        return failure
    if enabled is not False:
        # The read did not report the gateway (or its enabled state): it cannot be told whether it is disabled
        raise _state_unknown(vid, "PATCH", failure, current, "the read did not report the gateway's enabled state")
    if not reenable:
        # The disable was applied although its response was lost: the caller's DELETE can go on
        return None
    # The disable was applied although its response was lost: restore the original enabled state
    details = dict(failure.details)
    details.update({"vlan_id": vid, "rollback": "re-enabled"})
    try:
        _patch_enabled_retry(connection, vid, True, api_responses, f"{key_prefix}_rollback_enable_{vid}")
    except _EnableStateUnknown as exc:
        # The re-enable got no answer either and the gateway could not be read back
        details.update({"rollback": "unknown", "state": "unknown", "rollback_error": exc.msg})
        details["read_error"] = exc.details.get("read_error")
        msg = _extend_msg(
            failure.msg,
            f"The PATCH that disabled the Anycast Gateway on VLAN {vid} for the delete was applied (only its "
            f"response was lost) and whether the gateway could be re-enabled is UNKNOWN ({exc.msg}); it was not "
            "deleted. Check the device and enable it if it is disabled.",
        )
        return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=True)
    except FeAnycastGwError as exc:
        details["rollback"] = "not re-enabled"
        details["rollback_error"] = exc.msg
        msg = _extend_msg(
            failure.msg,
            f"The PATCH that disabled the Anycast Gateway on VLAN {vid} for the delete was applied (only its "
            f"response was lost) and the gateway could NOT be re-enabled ({exc.msg}); it is still configured "
            "but disabled.",
        )
        return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=True)
    msg = _extend_msg(
        failure.msg,
        f"The PATCH that disabled the Anycast Gateway on VLAN {vid} for the delete was applied (only its "
        "response was lost); the gateway was re-enabled and was not deleted.",
    )
    return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=changed_before)


def _disable_for_delete(
    connection: Connection,
    vid: int,
    current: dict[str, Any],
    api_responses: dict[str, Any],
    response_key: str,
    key_prefix: str,
    changed_before: bool,
    reenable: bool = True,
) -> None:
    """PATCH enabled=false on an enabled gateway before its DELETE; RAISE on failure.

    A definitive rejection (an in-band error or any HTTP status, see _is_ambiguous_failure)
    changed nothing on this VLAN and is raised with ``changed`` = ``changed_before``. A
    failure without an HTTP answer may hide a disable that was applied, so the gateway is
    read back and re-enabled if needed first (see _after_failed_disable; with ``reenable``
    False a gateway read back as disabled is accepted and nothing is raised).
    """
    try:
        _request(
            connection,
            method="PATCH",
            path=AG_PATCH_PATH.format(vlan_id=vid),
            payload={"enabled": False},
            api_responses=api_responses,
            response_key=response_key,
        )
    except FeAnycastGwError as exc:
        if not _is_ambiguous_failure(exc, "PATCH"):
            # Definitive: nothing changed on this VLAN; keep what earlier entries of the task changed
            exc.changed = changed_before
            raise
        error = _after_failed_disable(
            connection, vid, exc, current, api_responses, key_prefix, changed_before, reenable
        )
        if error is not None:
            raise error


def _delete_original(
    connection: Connection,
    vid: int,
    current: dict[str, Any],
    api_responses: dict[str, Any],
    changed_before: bool,
    notes: list[str],
) -> None:
    """Disable (if enabled) and DELETE the existing interface; raise instead of ending the task.

    A disable that failed is reconciled with the device (see _disable_for_delete).
    When the DELETE fails with a transport error, the VLAN is read back: if the
    original is gone the DELETE was applied (only its response was lost), a note is
    added to ``notes`` and the re-create carries on. If it is still there, or the
    device rejected the DELETE in-band, it is re-enabled (when it was disabled for
    the delete) and the DELETE error is raised. An HTTP status is definitive, except a
    404 that a plugin retry of an applied DELETE gets back (see _is_ambiguous_failure).
    """
    disabled = False
    if current.get("enabled"):
        _disable_for_delete(
            connection, vid, current, api_responses, f"replace_delete_disable_{vid}", "replace", changed_before
        )
        disabled = True
    try:
        _request(
            connection,
            method="DELETE",
            path=AG_VLAN_PATH.format(vlan_id=vid),
            api_responses=api_responses,
            response_key=f"replace_delete_{vid}",
        )
    except FeAnycastGwError as exc:
        # A definitive rejection deleted nothing; only a failure without an HTTP answer (or a 404 of a retry)
        # may hide an applied DELETE, so only then is the device asked whether the original still exists
        if not _is_ambiguous_failure(exc, "DELETE") or _gateway_exists_after_failure(
            connection, vid, "DELETE", exc, current, api_responses
        ):
            if disabled:
                raise _after_failed_delete(connection, vid, exc, api_responses, changed_before)
            # Nothing changed on this VLAN; keep what earlier entries of the task changed
            exc.changed = changed_before
            raise
        # The original is gone, so the DELETE was applied: continue the re-create
        notes.append(
            f"The DELETE of the Anycast Gateway on VLAN {vid} reported an error ({exc.msg}), but the gateway "
            "is gone: the delete was applied and only its response was lost. The re-create continued."
        )


def _disable_replacement(
    connection: Connection, vid: int, current: dict[str, Any], api_responses: dict[str, Any]
) -> str | None:
    """Disable the replacement before the rollback DELETEs it. Returns None when it is disabled, else why not.

    Called when the enable PATCH of the replacement failed without an HTTP answer and the
    replacement could not be read back, so it may be enabled and Fabric Engine refuses to
    DELETE an enabled gateway. The disable is reconciled like any disable before a delete
    (see _disable_for_delete), but a read-back that shows it disabled lets the DELETE go on.
    Recorded in api_responses as replace_rollback_disable_<vid> (read-back:
    replace_rollback_verify_patch_filtered_<vid>).
    """
    try:
        _disable_for_delete(
            connection,
            vid,
            current,
            api_responses,
            f"replace_rollback_disable_{vid}",
            "replace_rollback",
            True,
            reenable=False,
        )
    except _GatewayStateUnknown as exc:
        # The read-back failed (or did not report the gateway): report the root errors, not the generic advice
        return f"{exc.details.get('patch_error')}; its state could not be read back ({exc.details.get('read_error')})"
    except FeAnycastGwError as exc:
        return exc.msg
    return None


def _rollback_state_unknown(
    vid: int,
    method: str,
    failure: FeAnycastGwError,
    rollback_exc: FeAnycastGwError,
    current: dict[str, Any],
    read_error: str,
) -> _GatewayStateUnknown:
    """The error for a rollback DELETE/POST that failed without an answer and whose effect could not be read back.

    Like _state_unknown(), but the message starts with the error that made the re-create
    fail (``failure``) and tells what the rollback step left undecided. ``changed`` is True.
    """
    original_enabled = bool(current.get("enabled"))
    details = dict(failure.details)
    details.update(
        {
            "vlan_id": vid,
            "rollback": "unknown",
            "state": "unknown",
            "original_payload": _build_post_payload(current),
            "original_enabled": original_enabled,
            "rollback_error": rollback_exc.msg,
            f"{method.lower()}_error": rollback_exc.msg,
            "read_error": read_error,
        }
    )
    enable_hint = " and enable it." if original_enabled else "."
    if method == "DELETE":
        advice = (
            f"While the original was being restored, the DELETE of the new Anycast Gateway on VLAN {vid} failed "
            f"({rollback_exc.msg}) and the VLAN could not be read back ({read_error}), so the state of the Anycast "
            f"Gateway on VLAN {vid} is UNKNOWN: the new gateway may or may not have been deleted, and the original "
            "was not re-created. Check the device; delete the new gateway if it is still there, then re-create the "
            "original by hand with the POST body in details.original_payload" + enable_hint
        )
    else:
        advice = (
            f"While the original was being restored, its POST failed ({rollback_exc.msg}) and the VLAN could not be "
            f"read back ({read_error}), so the state of the Anycast Gateway on VLAN {vid} is UNKNOWN: the original "
            f"may or may not have been re-created. Check the device; if VLAN {vid} has no Anycast Gateway, re-create "
            "the original by hand with the POST body in details.original_payload"
            + ("; then make sure it is enabled." if original_enabled else ".")
        )
    return _GatewayStateUnknown(_extend_msg(failure.msg, advice), details=details, extra=failure.extra, changed=True)


def _rollback_delete_replacement(
    connection: Connection,
    vid: int,
    current: dict[str, Any],
    failure: FeAnycastGwError,
    api_responses: dict[str, Any],
    notes: list[str],
) -> tuple[str, str] | None:
    """DELETE the replacement so the original can be POSTed back. Returns None when it is gone, else (status, error).

    A definitive rejection deleted nothing: it returns ("replacement not deleted", error) without
    a read-back. A failure that may hide an applied DELETE (no HTTP answer, or the 404 of a plugin
    retry, see _is_ambiguous_failure) is checked against the device: no gateway left means the
    DELETE was applied (a note is added and None returned); a gateway still there returns
    ("replacement not deleted", error). The read is recorded as
    replace_rollback_verify_delete_filtered_<vid> (and _state_<vid>).

    Raises:
        _GatewayStateUnknown: the DELETE failed without an answer and the VLAN could not be read back.
    """
    try:
        _request(
            connection,
            method="DELETE",
            path=AG_VLAN_PATH.format(vlan_id=vid),
            api_responses=api_responses,
            response_key=f"replace_rollback_delete_{vid}",
        )
    except FeAnycastGwError as exc:
        if not _is_ambiguous_failure(exc, "DELETE"):
            # Definitive: the device refused the DELETE, so the replacement is still configured
            return "replacement not deleted", exc.msg
        # A lost DELETE response does not prove that nothing was deleted: ask the device
        try:
            present = _gateway_present(connection, vid, api_responses, "replace_rollback_verify_delete")
        except FeAnycastGwError as read_exc:
            raise _rollback_state_unknown(vid, "DELETE", failure, exc, current, read_exc.msg)
        if present:
            return "replacement not deleted", exc.msg
        notes.append(
            f"The rollback DELETE of the new Anycast Gateway on VLAN {vid} reported an error ({exc.msg}), but the "
            "gateway is gone: the delete was applied and only its response was lost. The restore of the original "
            "continued."
        )
    return None


def _rollback_post_original(
    connection: Connection,
    vid: int,
    current: dict[str, Any],
    failure: FeAnycastGwError,
    api_responses: dict[str, Any],
    notes: list[str],
) -> tuple[str, str] | None:
    """POST the original back. Returns None when it was re-created, else (status, error).

    A definitive rejection returns ("not restored", error) as it always did. A failure that
    may hide an applied POST (no HTTP answer, or the 409 of a plugin retry, see
    _is_ambiguous_failure) is checked against the device: a config entry with the original's
    immutable values (see _matches_post_payload) means the POST was applied (a note is added
    and None returned, so the caller re-enables it); no gateway returns ("not restored",
    error); a gateway with other values returns ("other gateway", error). The read is
    recorded as replace_rollback_verify_post_filtered_<vid>.

    Raises:
        _GatewayStateUnknown: the POST failed without an answer and the VLAN could not be read back.
    """
    original_payload = _build_post_payload(current)
    try:
        _request(
            connection,
            method="POST",
            path=AG_VLAN_PATH.format(vlan_id=vid),
            payload=original_payload,
            api_responses=api_responses,
            response_key=f"replace_rollback_post_{vid}",
        )
    except FeAnycastGwError as exc:
        if not _is_ambiguous_failure(exc, "POST"):
            # Definitive: the device refused the POST, nothing was created
            return "not restored", exc.msg
        # A lost POST response does not prove that nothing was created: the device must show the original
        try:
            entry = _config_entry(connection, vid, api_responses, "replace_rollback_verify_post")
        except FeAnycastGwError as read_exc:
            raise _rollback_state_unknown(vid, "POST", failure, exc, current, read_exc.msg)
        if entry is None:
            return "not restored", exc.msg
        if not _matches_post_payload(entry, original_payload):
            # Something else is configured on the VLAN (e.g. the replacement): the original is not back
            return "other gateway", exc.msg
        notes.append(
            f"The rollback POST of the original Anycast Gateway on VLAN {vid} reported an error ({exc.msg}), but "
            "the gateway exists with its original configuration: the create was applied and only its response was "
            "lost. The restore continued."
        )
    return None


def _restore_original(
    connection: Connection,
    vid: int,
    current: dict[str, Any],
    failure: FeAnycastGwError,
    replacement_created: bool,
    api_responses: dict[str, Any],
    notes: list[str],
) -> tuple[str, str | None]:
    """Put the original interface back. Returns (status, error).

    status is "restored", "restored but disabled" (the interface is back but could
    not be re-enabled), "replacement kept" (the replacement may
    be enabled and could not be disabled, so it was not deleted), "replacement not deleted"
    (the device refused its DELETE, or the DELETE failed without an answer and the
    read-back shows it still there), "other gateway" (the POST of the
    original failed and the read-back shows a gateway with other values) or "not
    restored". When the enable PATCH of the replacement failed without an HTTP answer
    and its read-back failed, the replacement is disabled first (see _disable_replacement). A rollback DELETE or
    POST that may have been applied is checked against the device (notes about lost
    responses go to ``notes``). Responses are recorded in api_responses as
    replace_rollback_disable_<vid>, replace_rollback_delete_<vid>,
    replace_rollback_post_<vid> and replace_rollback_enable_<vid>.

    Raises:
        _GatewayStateUnknown: a rollback DELETE/POST failed without an answer and the VLAN could not be read back.
        _EnableStateUnknown: the original is back, but its re-enable got no answer and it could not be read back.
    """
    if replacement_created and _is_ambiguous_failure(failure, "PATCH") and not failure.not_applied:
        # The replacement's enable PATCH failed without an HTTP answer and could not be read back: it may have
        # been applied, and the device refuses to DELETE an enabled gateway, so never send the DELETE unless it
        # is disabled (a read-back that showed it disabled, see _patch_enabled_retry, needs no disable)
        disable_error = _disable_replacement(connection, vid, current, api_responses)
        if disable_error is not None:
            return "replacement kept", disable_error
    if replacement_created:
        # The POST worked but the enable failed: the replacement is in the way
        outcome = _rollback_delete_replacement(connection, vid, current, failure, api_responses, notes)
        if outcome is not None:
            return outcome
    outcome = _rollback_post_original(connection, vid, current, failure, api_responses, notes)
    if outcome is not None:
        return outcome
    if current.get("enabled"):
        try:
            _patch_enabled_retry(connection, vid, True, api_responses, f"replace_rollback_enable_{vid}", notes)
        except _EnableStateUnknown:
            # The caller words it (and keeps its read_error), see _rollback_error
            raise
        except FeAnycastGwError as exc:
            return "restored but disabled", exc.msg
    return "restored", None


def _not_restored_msg(status: str, vid: int, restore_error: str | None, original_enabled: bool) -> str:
    """The sentence that tells why the original was not restored (status from _restore_original)."""
    by_hand = "re-create the original by hand with the POST body in details.original_payload" + (
        " and enable it." if original_enabled else "."
    )
    if status == "replacement kept":
        return (
            f"The original Anycast Gateway on VLAN {vid} could NOT be restored: the new gateway may have been "
            f"enabled and could not be disabled for its delete ({restore_error}), so it was not deleted and "
            f"still exists with the new values. Disable and delete it, then {by_hand}"
        )
    if status == "replacement not deleted":
        return (
            f"The original Anycast Gateway on VLAN {vid} could NOT be restored: the DELETE of the new gateway "
            f"failed ({restore_error}) and the new gateway was not deleted; it still exists with the new values. "
            f"Delete it (disable it first if it is enabled), then {by_hand}"
        )
    if status == "other gateway":
        return (
            f"The original Anycast Gateway on VLAN {vid} could NOT be restored ({restore_error}): the device "
            f"shows an Anycast Gateway on VLAN {vid} whose values differ from the original. Check it and delete it "
            f"if it is not wanted (disable it first if it is enabled), then {by_hand}"
        )
    return (
        f"The original Anycast Gateway on VLAN {vid} could NOT be restored ({restore_error}) and "
        f"no longer exists. Re-create it by hand with the POST body in details.original_payload"
        + (" and enable it." if original_enabled else ".")
    )


def _rollback_error(
    connection: Connection,
    vid: int,
    current: dict[str, Any],
    failure: FeAnycastGwError,
    replacement_created: bool,
    api_responses: dict[str, Any],
    changed_before: bool,
    notes: list[str],
) -> FeAnycastGwError:
    """Restore the original interface after a failed re-create. Returns the error to raise.

    The message is the original error extended with the outcome of the restore.
    ``changed`` is the state before this interface was touched when the restore
    worked (the device is back where it was, also when a rollback response was lost
    but the request was applied), and True when it did not (the interface was deleted
    or left disabled, or the replacement or another gateway was left in its place).

    Raises:
        _GatewayStateUnknown: a rollback step failed without an answer and the VLAN could not be read back.
    """
    original_payload = _build_post_payload(current)
    original_enabled = bool(current.get("enabled"))
    read_error = None
    try:
        status, restore_error = _restore_original(
            connection, vid, current, failure, replacement_created, api_responses, notes
        )
    except _EnableStateUnknown as exc:
        status, restore_error, read_error = "restored, enabled unknown", exc.msg, exc.details.get("read_error")
    details = dict(failure.details)
    details.update(
        {
            "vlan_id": vid,
            "rollback": status,
            "original_payload": original_payload,
            "original_enabled": original_enabled,
        }
    )
    if status == "restored":
        msg = _extend_msg(
            failure.msg, f"The original Anycast Gateway on VLAN {vid} was restored to its previous configuration."
        )
        return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=changed_before)
    details["rollback_error"] = restore_error
    if status == "restored but disabled":
        msg = _extend_msg(
            failure.msg,
            f"The original Anycast Gateway on VLAN {vid} was re-created but could NOT be re-enabled "
            f"({restore_error}); enable it manually.",
        )
        return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=True)
    if status == "restored, enabled unknown":
        # The original is back, but its re-enable got no answer and it could not be read back
        details.update({"rollback": "unknown", "state": "unknown", "read_error": read_error})
        msg = _extend_msg(
            failure.msg,
            f"The original Anycast Gateway on VLAN {vid} was re-created, but whether it could be re-enabled is "
            f"UNKNOWN ({restore_error}). Check the device and enable it if it is disabled.",
        )
        return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=True)
    # Every other status is reported as not restored; the replacement (if still there) is flagged
    details["rollback"] = "not restored"
    if status in ("replacement kept", "replacement not deleted"):
        details["replacement_kept"] = True
    msg = _extend_msg(failure.msg, _not_restored_msg(status, vid, restore_error, original_enabled))
    return FeAnycastGwError(msg, details=details, extra=failure.extra, changed=True)


def _recreate_with_rollback(
    connection: Connection,
    vid: int,
    current: dict[str, Any],
    merged_entry: dict[str, Any],
    post_payload: dict[str, Any],
    api_responses: dict[str, Any],
    changed_before: bool,
    notes: list[str],
) -> None:
    """DELETE the existing interface and POST the replacement; restore the original on failure.

    The original state (``current``) was captured before anything was written. If
    the POST or the follow-up enable PATCH fails, the original is POSTed back
    (and re-enabled if it was enabled) and the task fails with the original error
    plus the outcome of the restore. A DELETE or POST that failed is checked
    against the device first (see _gateway_exists_after_failure); notes about
    lost responses are added to ``notes``.
    """
    _delete_original(connection, vid, current, api_responses, changed_before, notes)
    created = False
    try:
        _post_replacement(connection, vid, current, post_payload, api_responses, notes)
        created = True
        # POST does not support 'enabled' — PATCH it if non-default.
        desired_enabled = merged_entry.get("enabled")
        if desired_enabled is not None and desired_enabled != FACTORY_DEFAULTS["enabled"]:
            _patch_enabled_retry(connection, vid, desired_enabled, api_responses, f"patch_enabled_{vid}", notes)
    except _GatewayStateUnknown:
        # Nothing can be restored safely on top of an unknown state: report it as is
        raise
    except FeAnycastGwError as exc:
        raise _rollback_error(connection, vid, current, exc, created, api_responses, changed_before, notes)


def _post_replacement(
    connection: Connection,
    vid: int,
    current: dict[str, Any],
    post_payload: dict[str, Any],
    api_responses: dict[str, Any],
    notes: list[str],
) -> None:
    """POST the replacement interface; a POST that may have been applied is checked against the device.

    A definitive rejection (an in-band error, or an HTTP status other than the 409 that a
    plugin retry of an applied POST gets back, see _is_ambiguous_failure) is raised at
    once, so the caller restores the original. After a failure without an HTTP answer or
    a 409, if the VLAN now has a gateway with the requested immutable values, the POST was
    applied and only its response was lost: a note is added and the re-create carries
    on. A gateway that still shows other values (e.g. the original) does not count.

    Raises:
        FeAnycastGwError: the POST failed and the replacement does not exist (the caller restores the original).
        _GatewayStateUnknown: the POST failed and the VLAN could not be read back.
    """
    try:
        _request(
            connection,
            method="POST",
            path=AG_VLAN_PATH.format(vlan_id=vid),
            payload=post_payload,
            api_responses=api_responses,
            response_key=f"replace_post_{vid}",
        )
    except FeAnycastGwError as exc:
        # The device definitively rejected the POST: nothing was created, the caller restores the original
        if not _is_ambiguous_failure(exc, "POST"):
            raise
        # A lost POST response does not prove that nothing was created: the device must show the replacement
        if not _replacement_created_after_failure(connection, vid, exc, current, post_payload, api_responses):
            raise
        notes.append(
            f"The POST of the new Anycast Gateway on VLAN {vid} reported an error ({exc.msg}), but the gateway "
            "exists with the requested configuration: the create was applied and only its response was lost. "
            "The re-create continued."
        )


def _patch_existing(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    patch: dict[str, Any],
    api_responses: dict[str, Any],
    response_key: str,
) -> None:
    """PATCH ``enabled`` of an existing gateway (merged, or replaced/overridden with only enabled differing).

    A definitive rejection (an in-band error or any HTTP status, see _is_ambiguous_failure)
    is raised as is: nothing changed on this VLAN, so _handle_merge_replace sets ``changed``
    to the state before this entry. A failure without an HTTP answer is checked against the
    device (see _enabled_applied_after_failure): applied -> a warning and the task goes on;
    not applied -> the error is raised as for a rejection.

    Raises:
        FeAnycastGwError: the PATCH was not applied.
        _GatewayStateUnknown: the PATCH failed without an answer and the gateway could not be read back.
    """
    enabled = patch["enabled"]
    try:
        _request(
            connection,
            method="PATCH",
            path=AG_PATCH_PATH.format(vlan_id=vid),
            payload=patch,
            api_responses=api_responses,
            response_key=response_key,
        )
    except FeAnycastGwError as exc:
        if not _is_ambiguous_failure(exc, "PATCH"):
            raise
        try:
            applied = _enabled_applied_after_failure(connection, vid, enabled, exc, api_responses, response_key)
        except _EnableStateUnknown as unknown:
            raise _enable_unknown_error(vid, enabled, unknown, "exists")
        if not applied:
            raise
        module.warn(
            f"The PATCH that sets enabled={str(enabled).lower()} on the Anycast Gateway on VLAN {vid} reported an "
            f"error ({exc.msg}), but the gateway is {'enabled' if enabled else 'disabled'}: the PATCH was applied "
            "and only its response was lost."
        )


def _replace_patch_only(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    entry: dict[str, Any],
    current: dict[str, Any],
    patch: dict[str, Any],
    modified_vids: list[int],
    gw_result: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Only ``enabled`` differs — just PATCH it (see _patch_existing)."""
    result["changed"] = True
    gw_result["changed"] = True

    if not module.check_mode:
        modified_vids.append(vid)
        _patch_existing(module, connection, vid, patch, result["api_responses"], f"replace_patch_{vid}")
    gw_result["after"] = _predict_after_patch(entry, current, use_factory_defaults=True)


def _replace_recreate(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    entry: dict[str, Any],
    current: dict[str, Any],
    modified_vids: list[int],
    gw_result: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Immutable fields differ — validate, DELETE + re-POST, restore the original on failure."""
    # Device state before this interface is touched: the earlier entries of the same
    # task (or the overridden pre-pass) may already have modified it.
    changed_before = bool(result["changed"]) and not module.check_mode
    result["changed"] = True
    gw_result["changed"] = True

    # Validate the re-create request BEFORE anything is deleted (also in check mode)
    merged_entry, post_payload = _prepare_recreate(vid, entry, current, changed_before)

    if not module.check_mode:
        modified_vids.append(vid)
        # Notes about DELETE/POST responses that were lost although the request was applied
        notes: list[str] = []
        try:
            _recreate_with_rollback(
                connection, vid, current, merged_entry, post_payload, result["api_responses"], changed_before, notes
            )
        except FeAnycastGwError as exc:
            if exc.changed is None:
                exc.changed = changed_before
            raise
        finally:
            # Reported as warnings whether the re-create then succeeded or failed
            for note in notes:
                module.warn(note)

    gw_result["after"] = _predict_after_replaced(merged_entry)


def _process_entry_replaced(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    entry: dict[str, Any],
    current: dict[str, Any],
    modified_vids: list[int],
    gw_result: dict[str, Any],
    result: dict[str, Any],
) -> bool:
    """Handle REPLACED/OVERRIDDEN for an existing interface.

    Returns True if processing is complete (caller should continue to next entry).
    """
    # Check if immutable fields differ → need DELETE + re-POST
    immutable_diffs = _immutable_fields_differ(entry, current)

    # Also check if enabled differs (use factory defaults
    # for omitted fields in replaced/overridden)
    patch = _build_patch_payload(entry, current, use_factory_defaults=True)

    if not immutable_diffs and patch is None:
        # No changes needed — idempotent
        gw_result["after"] = current
        gw_result["changed"] = False
        gw_result["differences"] = {}
        result["anycast_gateways"].append(gw_result)
        return True

    if not immutable_diffs and patch is not None:
        _replace_patch_only(module, connection, vid, entry, current, patch, modified_vids, gw_result, result)
    else:
        _replace_recreate(module, connection, vid, entry, current, modified_vids, gw_result, result)
    return False


def _process_entry_merged(
    module: AnsibleModule,
    connection: Connection,
    vid: int,
    entry: dict[str, Any],
    current: dict[str, Any],
    modified_vids: list[int],
    gw_result: dict[str, Any],
    result: dict[str, Any],
) -> bool:
    """Handle MERGED for an existing interface: only PATCH enabled, fail if immutable fields differ.

    Returns True if processing is complete (caller should continue to next entry).
    """
    immutable_diffs = _immutable_fields_differ(entry, current)
    if immutable_diffs:
        # Nothing is sent; _handle_merge_replace reports what the earlier entries of the task changed
        raise FeAnycastGwError(
            f"Cannot update immutable fields {immutable_diffs} on existing "
            f"Anycast Gateway interface (vlan_id={vid}). "
            "Use state=replaced to recreate, or state=deleted first."
        )

    patch = _build_patch_payload(entry, current)
    if patch is None:
        # No changes needed
        gw_result["after"] = current
        gw_result["changed"] = False
        gw_result["differences"] = {}
        result["anycast_gateways"].append(gw_result)
        return True

    result["changed"] = True
    gw_result["changed"] = True

    if not module.check_mode:
        modified_vids.append(vid)
        _patch_existing(module, connection, vid, patch, result["api_responses"], f"patch_{vid}")
    gw_result["after"] = _predict_after_patch(entry, current)
    return False


def _handle_merge_replace(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    config: list[dict[str, Any]],
    current_map: dict[int, dict[str, Any]],
    state_map: dict[int, Any],
    result: dict[str, Any],
) -> list[int]:
    """MERGED/REPLACED/OVERRIDDEN per-entry processing. Returns modified_vids.

    An error that does not set ``changed`` itself left its entry unchanged on the device:
    it gets the state before that entry, so the writes of the earlier entries (and of the
    overridden pre-pass) are still reported. An error raised after a write of its own
    entry succeeded sets ``changed`` True itself.
    """
    modified_vids: list[int] = []

    for entry in config:
        # Device state before this entry is touched (result["changed"] is set before each write)
        changed_before = bool(result["changed"]) and not module.check_mode
        try:
            _process_entry(module, connection, state, entry, current_map, state_map, modified_vids, result)
        except FeAnycastGwError as exc:
            if exc.changed is None:
                exc.changed = changed_before
            raise

    return modified_vids


def _process_entry(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    entry: dict[str, Any],
    current_map: dict[int, dict[str, Any]],
    state_map: dict[int, Any],
    modified_vids: list[int],
    result: dict[str, Any],
) -> None:
    """Create, update or re-create the interface of one config entry and record its result."""
    vid = entry["vlan_id"]
    gw_result: dict[str, Any] = {"vlan_id": vid}
    current = current_map.get(vid)

    if current is None:
        # Bulk GET may not return all interfaces (known Fabric Engine API
        # timing issue where recently-created interfaces are not
        # immediately visible).  Always try a targeted GET before
        # concluding the interface doesn't exist.
        current = _try_fallback_get(module, connection, vid, state_map, current_map, result)

    if current is None:
        # Interface does not exist — CREATE (POST)
        _create_missing_interface(module, connection, vid, entry, gw_result, modified_vids, result)
    else:
        # Interface EXISTS — update or recreate
        gw_result["before"] = current
        handler = _process_entry_merged if state == STATE_MERGED else _process_entry_replaced
        if handler(module, connection, vid, entry, current, modified_vids, gw_result, result):
            return

    gw_result["differences"] = _compute_diff(gw_result["before"], gw_result["after"])
    result["anycast_gateways"].append(gw_result)


def _refresh_interface_results(
    module: AnsibleModule,
    connection: Connection,
    modified_vids: list[int],
    result: dict[str, Any],
    cache: dict[int, dict[str, Any] | None],
) -> None:
    """Batch-fetch the final state and replace the predicted per-interface 'after'.

    A modified interface that the bulk read omits is read with the targeted GET; if
    that does not return it either, its predicted 'after' is kept.
    """
    api_responses = result["api_responses"]
    try:
        # raising=True: a failed read must reach the fallback below, not end the task after the writes
        after_raw = _fetch_all_interfaces(module, connection, api_responses, "after_batch_fetch", raising=True)
        after_state = _fetch_state_interfaces(
            module, connection, api_responses, "state_after_batch_fetch", raising=True
        )
    except FeAnycastGwError as exc:
        # If batch fetch fails, keep predicted values
        module.warn(
            f"Could not read the Anycast Gateway configuration back after the change ({exc.msg}); "
            "the per-interface 'after' in anycast_gateways is the predicted state."
        )
        return
    for gw_res in result["anycast_gateways"]:
        res_vid = gw_res["vlan_id"]
        if res_vid not in modified_vids:
            continue
        refreshed = None
        for raw_iface in after_raw:
            if raw_iface.get("vlanId") == res_vid:
                refreshed = _to_ansible_output(raw_iface, after_state.get(res_vid))
                break
        if refreshed is None:
            # Omitted by the bulk read (recently created): targeted GET, else keep the prediction
            refreshed = _targeted_after(connection, res_vid, after_state, api_responses, cache)
        if refreshed is not None:
            gw_res["after"] = refreshed
            gw_res["differences"] = _compute_diff(gw_res["before"], gw_res["after"])


def _capture_after_state(
    module: AnsibleModule,
    connection: Connection,
    current_map: dict[int, dict[str, Any]],
    modified_vids: list[int],
    result: dict[str, Any],
) -> None:
    """Batch-fetch final state and capture module-level 'after' (always reported)."""
    # Targeted reads of interfaces the bulk reads omit, shared by both 'after' views
    cache: dict[int, dict[str, Any] | None] = {}
    # ── Batch fetch after all operations (accurate final state) ───
    if result["changed"] and modified_vids and not module.check_mode:
        _refresh_interface_results(module, connection, modified_vids, result, cache)

    # Module-level "after": re-read after a change, predicted in check mode, equal to 'before' otherwise
    result["after"] = _final_after_state(module, connection, current_map, result, cache)


# ── Main entry point ─────────────────────────────────────────────────────────


def main() -> None:
    """Module entry point — dispatch based on state."""

    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
    )

    if not module._socket_path:
        module.fail_json(msg="Connection type httpapi is required for this module")

    connection = Connection(module._socket_path)
    state = module.params["state"]
    config = module.params.get("config") or []
    gather_filter = module.params.get("gather_filter") or []

    # Validate: merged/replaced/overridden require config
    if state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN) and not config:
        module.fail_json(msg=f"value of config parameter must not be empty for state {state}")

    # Validate: no duplicate VLAN IDs in config
    if config:
        seen: set = set()
        for entry in config:
            vid = entry["vlan_id"]
            if vid in seen:
                module.fail_json(
                    msg=f"Anycast gateway '{vid}' is listed more than once in 'config'; list each gateway once"
                )
            seen.add(vid)

    # Validate all config entries
    for entry in config:
        _validate_entry(module, entry)

    result: dict[str, Any] = {
        "changed": False,
        "anycast_gateways": [],
        "api_responses": {},
    }

    try:
        if state == STATE_GATHERED:
            _handle_gathered(module, connection, gather_filter, result)
            return

        # ── Fetch current state for change-making states ──────────────
        raw_list = _fetch_all_interfaces(module, connection, result["api_responses"], "configuration_before")
        state_map = _fetch_state_interfaces(module, connection, result["api_responses"], "state_before")
        current_map: dict[int, dict[str, Any]] = {}
        for raw in raw_list:
            out = _to_ansible_output(raw, state_map.get(raw.get("vlanId")))
            current_map[out["vlan_id"]] = out

        # Capture module-level "before" state
        result["before"] = sorted(current_map.values(), key=lambda x: x["vlan_id"])

        if state == STATE_DELETED:
            _handle_deleted(module, connection, config, current_map, state_map, result)
            return

        if state == STATE_OVERRIDDEN:
            _handle_overridden_prepass(module, connection, config, current_map, result)

        modified_vids = _handle_merge_replace(module, connection, state, config, current_map, state_map, result)

        _capture_after_state(module, connection, current_map, modified_vids, result)

        _finish(module, result)

    except FeAnycastGwError as exc:
        module.fail_json(**exc.to_fail_kwargs(), api_responses=result["api_responses"])
    except ConnectionError as exc:
        module.fail_json(
            msg=f"Connection error: {to_text(exc)}",
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=result["api_responses"],
        )


if __name__ == "__main__":
    main()
