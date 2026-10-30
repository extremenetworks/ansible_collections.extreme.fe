# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage ExtremeNetworks Fabric Engine VLANs via HTTPAPI.

REST endpoints used:
  GET    /v0/configuration/vlan              - list all VLANs
  GET    /v0/configuration/vlan/{vlan_id}    - get single VLAN
  POST   /v0/configuration/vrf/{vr_name}/vlan - create VLAN
  PATCH  /v0/configuration/vlan/{vlan_id}    - update VLAN scalars
  DELETE /v0/configuration/vrf/{vr_name}/vlan/{vlan_id} - delete VLAN
  POST   /v0/operation/vlan/{vlan_id}/interfaces/:add    - add membership
  POST   /v0/operation/vlan/{vlan_id}/interfaces/:remove  - remove membership
  GET    /v0/configuration/spbm/isis/logical-ifs - existing ISIS logical interfaces
"""

from __future__ import annotations

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
  - Bjorn Haas (@bhaas_extr)
notes:
  - A VLAN is deleted with C(DELETE /v0/configuration/vrf/{vr_name}/vlan/{vlan_id}). The VLAN list the module re-reads
    for C(after) once the task has changed the device is checked against the deleted VLANs, because a device has been
    seen to answer that request as successful and keep the VLAN. A VLAN still listed is not reported as deleted; it
    fails C(deleted) and is listed in C(skipped_vlans) by C(overridden). Delete it from the CLI (C(vlan delete)).
  - A VLAN DELETE that fails without an HTTP status (a lost connection) may have been applied before the answer was
    lost. Its outcome is unknown, and the task fails with C(changed=true), C(details.outcome=unknown) and the DELETE
    error in C(details.delete_error), in both states. A DELETE answered with 404 counts as deleted, since the VLAN
    was just read as present and a resent DELETE (after a lost answer) finds it gone; the check against C(after)
    still reports it if it is listed. A DELETE refused with any other HTTP status is reported as it is.
  - VLANs are supplied through the C(config) list. The former top-level
    parameters (C(vlan_id), C(vlan_name), C(vlan_type), ...) still work as a
    single-entry config and emit a deprecation warning; the two forms cannot
    be mixed in one task.
  - Tested against Fabric Engine Version 9.3.2.
  - A VLAN create (C(POST)) that fails without an answer (a lost connection), or a C(PATCH) that does and cannot
    be re-read, may have been applied, so the task reports C(changed=true) with C(details.outcome=unknown).
    A create answered with 409 (a resend after a lost answer) is checked against a re-read; it counts as done
    when the VLAN is there with the submitted settings, otherwise the outcome is unknown.
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
  - ISIS logical interfaces named in C(isis_logical_interfaces) must already
    exist on the device; create them first through the SPBM Isis Circuit
    Management endpoints. The VLAN endpoints return HTTP 204 even for an
    interface that does not exist and then drop the entry, so the module
    checks existence before writing and re-reads the VLAN afterwards. The
    REST API can only create layer-3 ISIS logical interfaces, which do not
    carry VLANs, so ISIS logical interface VLAN membership may not be
    manageable through the VLAN endpoints on a given device; the task then
    fails with a message saying the membership was accepted but not stored.
    An ISIS membership already present on the VLAN is left alone and sends
    nothing.
  - The VLAN name, type and STP instance (and the ISIS logical interface
    lists) are written in one PATCH, which the device may apply in part
    before refusing it. When that PATCH fails, the module re-reads the VLAN
    and the error message and C(details) report which fields were and were
    not applied (C(applied_fields), C(not_applied_fields), as REST key
    names), together with
    C(attempted_payload), C(status_code) and C(resource); the task then
    reports C(changed=true) if any field was applied. If the re-read fails
    too, C(details.reread_error) says why and nothing is attributed.
  - A LAG membership request is answered per interface. When some of its
    interfaces fail and others are applied, the task fails with
    C(changed=true) and C(details.applied_interfaces) lists the applied ones
    next to C(details.failures). Each requested interface must be
    confirmed by a successful result naming it; a duplicate or unrelated
    result, an empty list or a body the module does not recognise confirms
    nothing, and the task fails as incomplete, listing the interfaces without
    a result in C(details.unconfirmed_interfaces); a body it does not
    recognise is returned in C(details.response). A LAG requested both
    tagged and untagged needs a result for each tag; a result without a
    tagType then confirms neither. An answer without a body
    is a success.
  - A task that fails after one of its writes succeeded (a VLAN create,
    PATCH, membership request or delete) reports C(changed=true), whichever
    later request or read-back failed, and the failure message lists the
    writes already applied, for example C(created VLAN 20). Writes that a
    read-back shows changed nothing, such as an ISIS membership the device
    accepted but did not store, are not counted.
  - C(overridden) deletes every VLAN not listed in C(config), so an
    incomplete C(config) removes working configuration. VLANs carrying L3
    interfaces, SPBM ISIDs or RSMLT instances may be refused by the
    device; those are reported in C(skipped_vlans) and raised as warnings
    rather than aborting the run.
  - C(overridden) and C(deleted) without C(config) never delete a protected
    VLAN. Protected are VLAN 1 (default VLAN), VLAN 4048 (reserved system
    VLAN), the management VLAN (C(isMgmtInterface) true), dynamically created
    VLANs (C(dynamic) true) and BROUTER VLANs (C(vlanType) BROUTER), all read
    from the VLAN list the module already fetches. A VLAN whose list record
    omits C(vlanType) is re-read on its own first; one whose type is still not
    reported is protected too, since it could be a BROUTER VLAN. VLANs 1 and 4048 are kept
    silently, as before. Every other protected VLAN left alone is raised as
    a warning with the reason and listed in C(skipped_vlans) with
    C(protected=true).
  - A VLAN listed in C(config) is never skipped. C(overridden) applies it as
    C(replaced), and C(deleted) with C(config) sends the delete for it even
    when it is protected, leaving the decision to the device.
  - Supports check mode and diff mode. Under C(--diff) the module reports the
    whole VLAN configuration of the device before and after the change,
    including the VLANs that C(overridden) or C(deleted) removes; combined
    with C(--check) the reported C(after) is the state that would have been
    written.
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
        with this state. Protected VLANs (VLANs 1 and 4048, the management,
        dynamic and BROUTER VLANs, see the notes) are never deleted, and a
        VLAN the device refuses to remove is reported in C(skipped_vlans)
        rather than failing the task. Use C(replaced) to confine changes to the
        VLANs the task lists.
      - C(deleted) removes the specified VLANs from the device. If C(config)
        is empty or omitted, deletes all user-created VLANs except the
        protected ones (see the notes).
      - C(gathered) returns current VLAN information without applying changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - List of VLAN configurations to manage.
      - Each C(vlan_id) may appear only once. A duplicated C(vlan_id) fails
        the task before any request is sent, also in check mode.
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
          - When omitted, C(replaced) and C(overridden) reset it to PORT_MSTP_RSTP,
            except on a VLAN whose current type is not one of the choices (for example
            BROUTER), which keeps its type.
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
          - Each interface must already exist on the device (see the SPBM
            Isis Circuit Management endpoints). The module reads
            C(/v0/configuration/spbm/isis/logical-ifs) before any write and
            fails, also in check mode, naming the VLAN and the interface when
            one is missing. The check is skipped if that list cannot be read.
          - After the write the VLAN is read back. If the device accepted the
            request (HTTP 204) but did not store the membership, the task
            fails instead of reporting a change.
          - See the notes for the device limitation.
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
          - No existence check is made. An interface that is not a member of
            the VLAN is a no-op and reports no change.
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
        required: true
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
        required: true
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
        required: true
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
        required: true
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
# - name: Manage VLANs on Fabric Engine devices
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
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

# Deletes every other user VLAN on the device. VLANs 1 and 4048 are kept
# silently. The management, dynamic and BROUTER VLANs are kept with a
# warning; they and anything the device refuses to delete are reported
# in skipped_vlans.
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
    - Each VLAN has the form of C(vlans) under C(state=gathered), with
      C(vr_name) and the members of every interface type, PORT included, in
      C(tagged_interfaces) and C(untagged_interfaces) lists of
      C(interfaceType) and C(interfaceName). It is not the C(config) form of
      C(gathered).
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
after:
  description:
    - Full VLAN configuration state after changes.
    - Returned whether or not the module made changes.
    - In check mode this is the predicted state.
  returned: when state is merged, replaced, overridden, or deleted
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
    - VLANs that C(state=overridden) (the VLANs absent from C(config)) or
      C(state=deleted) without C(config) did not delete. Each is also raised
      as a warning.
    - The protected VLANs these sweeps leave alone (the management, dynamic
      and BROUTER VLANs), with C(protected=true). VLANs 1 and 4048 are kept
      too but not listed.
    - For C(overridden), also the VLANs the device refused to delete,
      typically because an L3 interface, SPBM ISID or RSMLT instance still
      references them, with C(protected=false).
  returned: when state is overridden, or deleted without config, and a VLAN was skipped
  type: list
  elements: dict
  sample: [{"vlan_id": 4000, "reason": "management VLAN", "protected": true}]
  contains:
    vlan_id:
      description: The VLAN that was not deleted.
      type: int
    reason:
      description:
        - Why it was not deleted. For a protected VLAN one of C(management VLAN),
          C(dynamic VLAN) or C(BROUTER VLAN); otherwise the error the device
          returned.
      type: str
    protected:
      description: True for a protected VLAN, false for a delete the device refused.
      type: bool
gathered:
  description:
    - VLAN configuration gathered from the device, one entry per VLAN in the
      form the C(config) option accepts, so it can be supplied back as
      C(config) unchanged. Re-applying an unfiltered result (no
      C(gather_filter)) with C(merged), C(replaced) or C(overridden)
      changes nothing.
    - With C(gather_filter) the result lists only the selected VLANs. It is
      still safe to re-apply with C(merged) or C(replaced), but C(overridden)
      takes it as the complete VLAN list and deletes every unlisted VLAN that
      is not protected, so re-apply a filtered result with C(overridden) only
      to do that.
    - LAG and ISIS logical interface members are listed in C(lag_interfaces)
      and C(isis_logical_interfaces) with their C(tag). Both lists are always
      present, empty when the VLAN has no such members.
    - PORT members are not included, because C(config) cannot express them.
      They are managed by C(extreme_fe_l2_interfaces), are left in place when
      the result is re-applied, and are still listed in C(vlans).
    - A scalar the device does not report, or a C(vlan_type) outside the
      choices of the option, is left out. Such a type is kept when the result
      is re-applied. An unreported C(stp_name) is STP instance 0 and is
      returned as an empty string.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
  contains:
    vlan_id:
      description: VLAN identifier.
      type: int
    vlan_name:
      description: VLAN name.
      type: str
    vlan_type:
      description: VLAN type.
      type: str
    stp_name:
      description: STP instance name, empty for STP instance 0.
      type: str
    vr_name:
      description: Virtual router the VLAN belongs to.
      type: str
    lag_interfaces:
      description: LAG members, each with C(name) and C(tag) (C(tagged) or C(untagged)).
      type: list
      elements: dict
    isis_logical_interfaces:
      description: ISIS logical interface members, each with C(name) and C(tag).
      type: list
      elements: dict
  sample:
    - vlan_id: 20
      vlan_name: Campus-20
      vlan_type: PORT_MSTP_RSTP
      stp_name: ""
      vr_name: GlobalRouter
      lag_interfaces:
        - name: "10"
          tag: tagged
      isis_logical_interfaces: []
vlans:
  description:
    - Under the action states, per-VLAN operation results with differences.
    - Under C(state=gathered) this instead lists the gathered VLANs in the
      form of C(before), which is what the module returned for that state up
      to 1.2.1. It includes the PORT members but cannot be supplied back as
      C(config). That form is deprecated and will be removed in 2.0.0 - use
      C(gathered).
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

import copy

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown, http_status

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
#   _to_config_entry()              the gathered form: the scalars config
#                                   accepts, membership as LAG/ISIS lists
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
# The vlan_type values this module accepts. Fabric Engine can also report types
# that cannot be created here (e.g. BROUTER); see _build_scalar_update_replaced().
VLAN_TYPE_CHOICES = ("PORT_MSTP_RSTP", "PROTOCOL_MSTP_RSTP", "PVLAN_MSTP_RSTP", "SPBM_BVLAN")

FULL_DEFAULTS = {
    "vlan_name": None,  # Will be computed as "VLAN-{id}" per VLAN
    "vlan_type": "PORT_MSTP_RSTP",
    "stp_name": "",  # Empty string = STP instance 0 (from OpenAPI spec)
}

# System VLANs that overridden and deleted without config never delete, with
# the reason reported for each
SYSTEM_VLANS = {1: "default VLAN", 4048: "reserved system VLAN"}

# Interface type constants for membership payloads
INTERFACE_TYPE_LAG = "LAG"
INTERFACE_TYPE_ISIS = "ISIS_LOGICAL_INTERFACE"

# SPBM ISIS circuit endpoint listing existing ISIS logical interfaces
ISIS_LOGICAL_IFS_PATH = "/v0/configuration/spbm/isis/logical-ifs"

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
        "choices": [STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED, STATE_GATHERED],
        "default": STATE_MERGED,
    },
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "vlan_id": {"type": "int", "required": True},
            "vlan_name": {"type": "str"},
            # One source for the choices, so the spec (and the deprecated
            # top-level vlan_type copied from it below) cannot drift from
            # the type check of _build_scalar_update_replaced().
            "vlan_type": {"type": "str", "choices": list(VLAN_TYPE_CHOICES)},
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
    name: spec["default"] for name, spec in ARGUMENT_SPEC["config"]["options"].items() if "default" in spec
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
            "into 'config'."
        )
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
                "the 'config' list where it is enforced."
            )
        return [{name: module.params.get(name) for name in _FLAT_PARAMS}]
    return []


def _reject_duplicate_vlan_ids(module, config):
    """Fail when the same vlan_id appears in more than one config entry.

    Every entry is planned against the device state read once at the start of
    the run, so a second entry for the same VLAN cannot see what the first one
    changed: the check-mode 'after' would keep only the last entry, and a
    real run could try to create a new VLAN twice. Rejecting duplicates up
    front, before any request is sent, avoids both.
    """
    seen = set()
    duplicates = []
    for entry in config:
        vlan_id = entry.get("vlan_id")
        # Report each duplicated ID once, in the order it was first repeated.
        if vlan_id in seen and vlan_id not in duplicates:
            duplicates.append(vlan_id)
        seen.add(vlan_id)
    if duplicates:
        module.fail_json(
            msg=(
                "VLAN '%s' is listed more than once in 'config'; list each VLAN once" % duplicates[0]
                if len(duplicates) == 1
                else "VLANs %s are listed more than once in 'config'; list each VLAN once"
                % ", ".join("'%s'" % vid for vid in duplicates)
            )
        )


# -- Custom Exception ----------------------------------------------------------


class FeVlansError(Exception):
    """Base exception for module-level errors."""

    def __init__(self, message, *, details=None, extra=None, changed=None):
        super().__init__(message)
        self.details = details or {}
        # Extra fail_json keys, e.g. the 'code' of a transport error, so a
        # wrapped ConnectionError keeps the result shape it had unwrapped.
        self.extra = extra or {}
        # True when the module knows the device was left modified (a PATCH or a
        # membership request that failed after part of it was applied, or any
        # failure after an earlier write of the same task succeeded - see
        # _WriteTracker); None keeps the default result.
        self.changed = changed

    def to_fail_kwargs(self):
        data = {"msg": to_text(self)}
        data.update(self.extra)
        if self.details:
            data["details"] = self.details
        if self.changed is not None:
            data["changed"] = self.changed
        return data


class FeVlansDeleteUnknown(FeVlansError):
    """A VLAN DELETE failed without an HTTP status; it may have been applied.

    The VLAN may or may not be gone, so the delete counts as a write
    (changed=true) and must not be reported as a skipped or failed no-op.
    """


class _WriteTracker:
    """Remember which writes of this task already modified the device.

    Used as a context manager around the write phase of a task. Once a write
    has succeeded (record()), a later failure - for another VLAN, a membership
    request, or the read-back of the after state - must not hide that change:
    the failure is re-raised as an FeVlansError with changed=true and its
    message lists the writes already applied (for example "created VLAN 20").
    A ConnectionError keeps its msg and code. Before the first write, failures
    pass through untouched.
    """

    def __init__(self):
        # [(vlan_id, description), ...] in the order the writes succeeded.
        self.done = []

    def record(self, vlan_id, what):
        self.done.append((vlan_id, what))

    def forget(self, vlan_id):
        """Drop the writes of one VLAN, once a read-back shows they changed nothing."""
        self.done = [item for item in self.done if item[0] != vlan_id]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc is None or not self.done or not isinstance(exc, (ConnectionError, FeVlansError)):
            return False
        suffix = "The task had already changed the device before this failure: %s." % ", ".join(
            what for _vid, what in self.done
        )
        if isinstance(exc, FeVlansError):
            # The failing request's own attribution may have left changed unset
            # (nothing of ITS payload applied); the earlier writes still count.
            raise FeVlansError(
                _extend_msg(to_text(exc), suffix), details=exc.details, extra=exc.extra, changed=True
            ) from exc
        # Mirror main(): an unwrapped ConnectionError failed with msg and code.
        raise FeVlansError(
            _extend_msg(to_text(exc), suffix), extra={"code": getattr(exc, "code", None)}, changed=True
        ) from exc


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
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
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

    Membership operations do not come through here: they are sent directly and
    checked by _validate_multi_status(), which understands the per-interface
    response shapes (where an errorCode of 200 or 204 is a success).
    """
    if not isinstance(payload, dict):
        return
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    errors = payload.get("errors")
    has_errors = isinstance(errors, list) and bool(errors)
    # Only an explicit error marker counts -- a normal VLAN document carries
    # none of these keys, so this cannot misfire on a successful read. The
    # markers are those extreme_fe_l2_interfaces and extreme_fe_autosense
    # recognise: errorCode, a statusCode/code of 400 or more (bool is an int
    # subclass, True is not a status), or a non-empty errors list.
    is_status = isinstance(code, int) and not isinstance(code, bool) and code >= 400
    if not (payload.get("errorCode") or is_status or has_errors):
        return
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if not message and has_errors:
        message = "%d error(s) reported: %s" % (len(errors), errors)
    raise FeVlansError(
        "Device rejected %s %s%s" % (method, path, ": %s" % message if message else ""),
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
        raise FeVlansError("Unsupported tag value '%s' for interface '%s'" % (tag_choice, name))
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
        sanitized.append(
            {
                "interfaceType": str(interface_type),
                "interfaceName": str(interface_name),
            }
        )
    return sanitized


def _membership_key(entry):
    """Return a hashable key for a membership entry."""
    return (str(entry.get("interfaceType", "")).upper(), str(entry.get("interfaceName", "")))


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


# Status keys of a membership result entry, in the order the httpapi plugin's
# multi-status parser reads them (errorCode first, as Fabric Engine's error
# documents use it).
_MULTI_STATUS_CODE_KEYS = ("errorCode", "statusCode", "code", "status")


def _multi_status_entries(response):
    """Return the per-interface result entries of a membership response, or None.

    The httpapi plugin returns a 207 on the membership paths to the module
    instead of raising, so every shape its own parser classifies is accepted
    here too: a bare list, a list under a wrapper key, or a single result
    entry (a dict carrying a status key or an errorMessage).
    """
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return None
    for key in ("interfaces", "entries", "items", "results", "responses"):
        candidate = response.get(key)
        if isinstance(candidate, list):
            return candidate
    if any(response.get(key) not in (None, "") for key in _MULTI_STATUS_CODE_KEYS + ("errorMessage",)):
        return [response]
    return None


def _first_status_value(item):
    """Return a result entry's raw status value, read in _MULTI_STATUS_CODE_KEYS order."""
    for key in _MULTI_STATUS_CODE_KEYS:
        if item.get(key):
            return item.get(key)
    return None


def _entry_status(item):
    """Return a result entry's status as an int, or None when it has no usable one."""
    status = _first_status_value(item)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _result_key(entry):
    """Identity of a membership request or result entry, (interfaceType, interfaceName), or None without a name."""
    name = entry.get("interfaceName")
    if name is None or str(name).strip() == "":
        return None
    return (str(entry.get("interfaceType") or "").upper(), str(name).strip())


def _tag_key(entry):
    """The tagType of a membership entry, upper-cased, or "" when it has none."""
    tag = entry.get("tagType")
    return str(tag).strip().upper() if tag not in (None, "") else ""


def _match_requested(item, wanted, by_interface):
    """The requested key a result entry answers, or None.

    A result that reports a tagType matches the requested entry with the same
    interface and tag only. One without a tagType matches only when exactly one
    requested entry names that interface; with both tags requested it is
    ambiguous and confirms nothing.
    """
    iface = _result_key(item)
    if iface is None:
        return None
    tag = _tag_key(item)
    if tag:
        key = iface + (tag,)
        return key if key in wanted else None
    candidates = by_interface.get(iface, [])
    return candidates[0] if len(candidates) == 1 else None


def _membership_ref(entry):
    """The interface fields reported in details for a membership entry."""
    return {
        "interfaceType": entry.get("interfaceType"),
        "interfaceName": entry.get("interfaceName"),
        "tagType": entry.get("tagType"),
    }


def _validate_multi_status(operation, vlan_id, response, requested=None):
    """Check a multi-status membership response against the *requested* entries.

    A bodyless answer is a plain success. Otherwise each requested interface
    must be confirmed by a successful result naming the same interface type
    and name (and the same tagType, when the result reports one), exactly
    once: a duplicated result leaves the interface unconfirmed, an unrelated
    one confirms nothing, and a body the module does not
    recognise (for example {} or an unknown wrapper) confirms nothing either:
    the requested interfaces without a result are reported as unconfirmed
    and the request fails. Every failed result fails the request.
    """
    if response in (None, ""):
        return
    requested = [entry for entry in (requested or []) if isinstance(entry, dict)]
    # A requested entry is identified by interface type, name AND tag: the same
    # LAG can be requested tagged and untagged in one payload.
    wanted = {}
    by_interface = {}
    for entry in requested:
        iface = _result_key(entry)
        if iface is None:
            continue
        key = iface + (_tag_key(entry),)
        if key not in wanted:
            wanted[key] = entry
            by_interface.setdefault(iface, []).append(key)
    entries = _multi_status_entries(response)
    failures = []
    successes = {}
    failed = set()
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        key = _match_requested(item, wanted, by_interface)
        request = wanted.get(key) if key is not None else None
        if _entry_status(item) in _SUCCESS_STATUS_CODES:
            if request is not None:
                successes[key] = successes.get(key, 0) + 1
            continue
        if request is not None:
            failed.add(key)
        failures.append(
            dict(_membership_ref(item), statusCode=_first_status_value(item), errorMessage=item.get("errorMessage"))
        )
    # Exactly one successful result confirms an interface: a duplicated one is
    # ambiguous and stays unconfirmed, and any failed result wins.
    applied = [key for key in wanted if successes.get(key) == 1 and key not in failed]
    unconfirmed = [key for key in wanted if successes.get(key) != 1 and key not in failed]
    if not failures and not unconfirmed:
        return
    msg = "Failed to %s VLAN membership for VLAN %d" % (operation, vlan_id)
    details = {"failures": failures}
    if entries is None:
        # Not a shape the module (or the httpapi plugin) knows: returned as is
        # for diagnosis (membership answers carry no credentials).
        msg += "; the device answered with a response the module does not recognise"
        details["response"] = response
    if unconfirmed:
        msg += "; the device returned no result for %d of the %d interface(s) in the request" % (
            len(unconfirmed),
            len(wanted),
        )
        details["unconfirmed_interfaces"] = [_membership_ref(wanted[key]) for key in unconfirmed]
    if not applied:
        raise FeVlansError(msg, details=details)
    # The other interfaces of the same request were applied, so the device was
    # modified even though the request as a whole failed.
    details["applied_interfaces"] = [_membership_ref(wanted[key]) for key in applied]
    raise FeVlansError(
        "%s; the device applied %d of the %d interface(s) in the request" % (msg, len(applied), len(wanted)),
        details=details,
        changed=True,
    )


# -- Data-Fetching Functions ---------------------------------------------------


def _get_all_vlans(connection):
    """GET /v0/configuration/vlan -- retrieve all VLANs from device."""
    data = _call_api(connection, "GET", "/v0/configuration/vlan", allow_not_found=True)
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
        data = _call_api(connection, "GET", "/v0/configuration/vlan/%d" % vlan_id, allow_not_found=True)
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        # The per-ID record (OpenAPI VlanInterfaceGetSettingsPerId) carries no
        # id, and Fabric Engine leaves it out: without it the re-read reported
        # vlan_id null (a change on every run) and a filtered gathered dropped
        # the VLAN.
        if data.get("id") is None:
            data = dict(data, id=vlan_id)
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
    path = "/v0/configuration/vrf/%s/vlan" % vr_name
    try:
        _call_api(connection, "POST", path, payload)
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 409:
            # HTTPAPI resends a request after some transport failures, so a first
            # POST that created the VLAN and lost its answer makes the resend
            # answer 409 (already exists): check the VLAN before deciding.
            _verify_created_vlan(connection, vlan_id, payload, path, exc)
            return
        if not answer_unknown(exc):
            raise
        # No answer (a lost connection; no code, or a negative JSON-RPC code of
        # the persistent connection): the VLAN may have been created.
        raise FeVlansError(
            "%s. The POST %s creating VLAN %d may have been applied before the answer was lost; check the VLAN on "
            "the device." % (to_text(exc).rstrip("."), path, vlan_id),
            details={"vlan_id": vlan_id, "path": path, "outcome": "unknown"},
            extra={"code": None},
            changed=True,
        ) from exc


def _verify_created_vlan(connection, vlan_id, payload, path, exc):
    """Accept a VLAN POST answered 409 when the VLAN is there with the submitted settings.

    The VLAN was read as absent before the POST, so a 409 means it now exists -
    most likely created by a first attempt whose answer was lost. It counts as
    created when the re-read shows the submitted name, type and STP instance;
    otherwise (other settings, or no re-read) the outcome is unknown and the
    task fails with changed=true.
    """
    try:
        record = _get_vlan(connection, vlan_id)
    except (ConnectionError, FeVlansError) as reread_exc:
        record = None
        reread_error = to_text(reread_exc)
    else:
        reread_error = None if record is not None else "VLAN %d is not listed" % vlan_id
    if record is not None:
        # A submitted field the re-read omits is not verified: it counts as a mismatch.
        mismatched = [key for key in ("name", "vlanType") if key in payload and record.get(key) != payload[key]]
        if "stpName" in payload and _normalize_stp_name(record.get("stpName")) != _normalize_stp_name(
            payload["stpName"]
        ):
            mismatched.append("stpName")
        if not mismatched:
            return
        reread_error = "the re-read shows other settings (%s)" % ", ".join(mismatched)
    raise FeVlansError(
        "The POST %s creating VLAN %d answered 409 (already exists), and %s; it may have been created by a first "
        "attempt whose answer was lost, so the outcome is unknown." % (path, vlan_id, reread_error),
        details={"vlan_id": vlan_id, "path": path, "outcome": "unknown", "reread_error": reread_error},
        extra={"code": 409},
        changed=True,
    ) from exc


def _update_vlan(connection, vlan_id, payload, before=None, writes=None):
    """PATCH /v0/configuration/vlan/{vlan_id} -- update VLAN scalars or memberships.

    One PATCH can carry several fields (name, vlanType, stpName, or the
    tagged/untagged interface lists). Fabric Engine has been seen to apply part
    of such a PATCH and then answer with an error, so a failure is
    turned into an error that says which fields the device actually applied.
    before is the VLAN record the payload was built against; it only decides
    whether an applied field really changed the device. A successful PATCH is
    recorded in writes (a _WriteTracker), when given.
    """
    if not payload:
        return
    path = "/v0/configuration/vlan/%d" % vlan_id
    try:
        _call_api(connection, "PATCH", path, payload)
    except (ConnectionError, FeVlansError) as exc:
        # Transport/HTTP errors and 2xx error bodies alike: re-read and attribute.
        raise _attribute_patch_failure(connection, vlan_id, path, payload, before, exc)
    if writes is not None:
        writes.record(vlan_id, "updated VLAN %d" % vlan_id)


# -- PATCH Failure Attribution ------------------------------------------------

# Payload keys holding membership lists; the device may return them in another
# order, so they are compared as sets of (interfaceType, interfaceName).
_MEMBERSHIP_LIST_KEYS = ("taggedInterfaces", "untaggedInterfaces")

# Marks a payload path that is absent from the re-read record.
_MISSING = object()


def _field_paths(payload, prefix=""):
    """Flatten a PATCH payload into [(dotted REST key path, value), ...].

    Nested dicts recurse (e.g. fabricAttach.proxy.mgmtIsid); lists and scalars
    are leaves. The VLAN payload is flat today, so this yields its top-level keys.
    """
    fields = []
    for key, value in payload.items():
        path = prefix + key
        if isinstance(value, dict) and value:
            fields.extend(_field_paths(value, path + "."))
        else:
            fields.append((path, value))
    return fields


def _lookup_path(record, path):
    """Return the value at a dotted path in a VLAN record, or _MISSING."""
    value = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _field_matches(path, attempted, record):
    """True when the record holds the attempted value for one payload path."""
    if path in _MEMBERSHIP_LIST_KEYS:
        # An absent list reads as empty, the same as _sanitize_membership(None).
        actual = record.get(path)
        attempted_keys = {_membership_key(e) for e in _sanitize_membership(attempted)}
        return attempted_keys == {_membership_key(e) for e in _sanitize_membership(actual)}
    actual = _lookup_path(record, path)
    if path == "stpName":
        return _normalize_stp_name(None if actual is _MISSING else actual) == _normalize_stp_name(attempted)
    return actual is not _MISSING and actual == attempted


def _error_status_code(exc):
    """HTTP status of a failed request: the ConnectionError code or the error body's code."""
    code = getattr(exc, "code", None)
    if code is None and isinstance(exc, FeVlansError):
        # _raise_for_error_payload keeps the device's error document here.
        response = exc.details.get("response")
        if isinstance(response, dict):
            code = response.get("errorCode") or response.get("statusCode") or response.get("code")
    # A negative JSON-RPC code (a lost answer) is not an HTTP status.
    return http_status(code)


def _extend_msg(msg, suffix):
    """Append a sentence to an error message, adding the full stop it may lack."""
    msg = msg.rstrip()
    return "%s %s" % (msg if msg.endswith((".", "!", "?")) else msg + ".", suffix)


def _attribute_patch_failure(connection, vlan_id, path, payload, before, exc):
    """Build the FeVlansError for a failed PATCH, naming the fields the device applied.

    The VLAN is re-read with the same GET the module uses elsewhere and every
    payload field is compared with the read-back value. The error keeps the
    original message (extended by one attribution sentence) and, for a
    ConnectionError, its 'code'. changed is reported True only when an applied
    field differs from what the VLAN held before the PATCH; otherwise the
    failure result keeps its previous shape.
    """
    fields = _field_paths(payload)
    names = ", ".join(p for p, _v in fields)
    details = dict(exc.details) if isinstance(exc, FeVlansError) else {}
    details.update({"attempted_payload": copy.deepcopy(payload), "resource": path})
    status_code = _error_status_code(exc)
    if status_code is not None:
        details["status_code"] = status_code
    # Mirror main(): an unwrapped ConnectionError failed with msg and code.
    extra = {"code": getattr(exc, "code", None)} if isinstance(exc, ConnectionError) else {}

    try:
        record = _get_vlan(connection, vlan_id)
        if record is None:
            raise FeVlansError("VLAN '%d' does not exist on the device" % vlan_id)
    except (ConnectionError, FeVlansError) as reread_exc:
        # Without a read-back nothing can be attributed; say so explicitly.
        details["reread_error"] = to_text(reread_exc)
        suffix = (
            "VLAN %d could not be re-read to check which of the %d attempted field(s) (%s) the device "
            "applied before refusing (%s); it may have changed part of the configuration."
            % (vlan_id, len(fields), names, to_text(reread_exc))
        )
        # A transport failure without an HTTP status (no answer): the PATCH may
        # have been applied, so changed is reported.
        no_answer = isinstance(exc, ConnectionError) and answer_unknown(exc)
        if no_answer:
            details["outcome"] = "unknown"
        return FeVlansError(
            _extend_msg(to_text(exc), suffix), details=details, extra=extra, changed=True if no_answer else None
        )

    applied = [p for p, v in fields if _field_matches(p, v, record)]
    not_applied = [p for p, _v in fields if p not in applied]
    details["applied_fields"] = applied
    details["not_applied_fields"] = not_applied
    if applied:
        suffix = "The device rejected the PATCH of VLAN %d after applying %d of %d field(s): %s; not applied: %s." % (
            vlan_id,
            len(applied),
            len(fields),
            ", ".join(applied),
            ", ".join(not_applied) or "none",
        )
    else:
        suffix = "A re-read of VLAN %d shows none of the %d attempted field(s) was applied (%s)." % (
            vlan_id,
            len(fields),
            names,
        )
    # An applied field that already held its value (or an unknown before) is
    # not a change made by this PATCH; with no before, assume it was.
    payload_values = dict(fields)
    modified = [p for p in applied if before is None or not _field_matches(p, payload_values[p], before)]
    return FeVlansError(
        _extend_msg(to_text(exc), suffix),
        details=details,
        extra=extra,
        changed=True if modified else None,
    )


def _delete_vlan(connection, vr_name, vlan_id):
    """DELETE /v0/configuration/vrf/{vr_name}/vlan/{vlan_id}.

    No re-read here: the 'after' snapshot that follows a real change lists the
    VLANs still on the device, and _check_deletes_applied() compares the deleted
    VLANs against it. A DELETE that fails without an HTTP status (HTTPAPI raises
    a ConnectionError without a code, for example "Retries exhausted") may have
    been applied before the answer was lost, so its outcome is unknown
    (FeVlansDeleteUnknown, changed=true). A 404 (a status or a not-found error
    body) means the VLAN is gone: the caller only deletes a VLAN it has just read
    as present, and HTTPAPI resends a DELETE after some transport failures, so a
    first attempt that deleted the VLAN and lost its answer makes the resend
    answer 404. It is returned as a delete; the check against 'after' still
    reports the VLAN if it is in fact listed. Any other rejection with an HTTP
    status, or an error body, is raised as it is.
    """
    path = "/v0/configuration/vrf/%s/vlan/%d" % (vr_name, vlan_id)
    try:
        _call_api(connection, "DELETE", path, allow_not_found=True)
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return
        if not answer_unknown(exc):
            raise
        raise FeVlansDeleteUnknown(
            "DELETE %s failed without an HTTP status (%s) and may have been applied; check VLAN %d on the "
            "device." % (path, to_text(exc), vlan_id),
            details={
                "vlan_id": vlan_id,
                "vr_name": vr_name,
                "path": path,
                "outcome": "unknown",
                "delete_error": to_text(exc),
            },
            extra={"code": None},
            changed=True,
        ) from exc


def _still_present_message(vlan_id):
    return (
        "The device accepted the DELETE of VLAN %d, but the re-read still lists it; it was not deleted. "
        "Delete it from the CLI (vlan delete %d)." % (vlan_id, vlan_id)
    )


def _check_deletes_applied(after, deleted_ids, writes=None):
    """Return the deleted VLAN IDs that the re-read 'after' snapshot still lists.

    A device has been seen to answer the VLAN DELETE as successful (204) and
    keep the VLAN, so a DELETE status alone is not trusted. The writes of a VLAN
    still listed are dropped from *writes*: it was not changed.
    """
    listed = {vlan.get("vlan_id") for vlan in after}
    present = [vid for vid in deleted_ids if vid in listed]
    if writes is not None:
        for vid in present:
            writes.forget(vid)
    return present


# -- Output Formatter ----------------------------------------------------------


def _normalize_stp_name(value):
    """Return "" for STP instance 0, else the instance name.

    OpenAPI: an empty or not present stpName is STP instance 0; Fabric Engine
    reports that instance as "0" (7520, 9.4). All three mean the same, so they
    compare equal and are shown as "" (the value config uses for instance 0).
    """
    if value is None or value == "" or value == "0":
        return ""
    return value


def _to_ansible_output(raw):
    """Convert a raw REST VLAN dict to Ansible-friendly output format."""
    out = {}
    out["vlan_id"] = raw.get("id")
    out["vlan_name"] = raw.get("name")
    out["vlan_type"] = raw.get("vlanType")
    out["stp_name"] = _normalize_stp_name(raw.get("stpName"))
    out["vr_name"] = raw.get("vrName")
    out["tagged_interfaces"] = _sanitize_membership(raw.get("taggedInterfaces"))
    out["untagged_interfaces"] = _sanitize_membership(raw.get("untaggedInterfaces"))
    return out


def _to_ansible_list(raw_list):
    """Convert a list of raw REST VLAN dicts to Ansible output format."""
    return [_to_ansible_output(v) for v in raw_list]


def _to_config_entry(raw):
    """Convert a raw REST VLAN dict to a config entry, for the gathered result.

    Unlike _to_ansible_output() (the before/after and 'vlans' form), the entry
    uses the option names config accepts: LAG and ISIS logical interface
    members become lag_interfaces / isis_logical_interfaces as {name, tag}
    lists. PORT members have no config option here (extreme_fe_l2_interfaces
    manages them) and are left out; replaced and overridden never touch them,
    so re-applying the entry leaves them in place. Each membership list is
    always present, so re-applying keeps it authoritative even when empty.
    Unreported scalars and a vlanType outside the vlan_type choices are left
    out, so the entry passes argument validation.
    """
    options = ARGUMENT_SPEC["config"]["options"]
    entry = {"vlan_id": raw.get("id")}
    for ansible_key, rest_key in (
        ("vlan_name", "name"),
        ("vlan_type", "vlanType"),
        ("stp_name", "stpName"),
        ("vr_name", "vrName"),
    ):
        value = raw.get(rest_key)
        if rest_key == "stpName":
            # Absent, "" and "0" are all STP instance 0, shown as "".
            value = _normalize_stp_name(value)
        if not isinstance(value, str):
            continue
        choices = options[ansible_key].get("choices")
        if choices and value not in choices:
            continue
        entry[ansible_key] = value
    for option, interface_type in (
        ("lag_interfaces", INTERFACE_TYPE_LAG),
        ("isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    ):
        members = []
        for tag, rest_key in (("tagged", "taggedInterfaces"), ("untagged", "untaggedInterfaces")):
            for member in _sanitize_membership(raw.get(rest_key)):
                key = _membership_key(member)
                if key[0] == interface_type:
                    members.append({"name": key[1], "tag": tag})
        entry[option] = members
    return entry


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
        result[tag_value].append(
            {
                "interfaceType": interface_type,
                "interfaceName": name,
            }
        )
    return result


def _membership_ops_for_merge(config_entry):
    """Compute membership additions/removals for merged state."""
    additions = {"TAG": [], "UNTAG": []}
    removals = {"TAG": [], "UNTAG": []}

    for option, itype in (
        ("lag_interfaces", INTERFACE_TYPE_LAG),
        ("isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    ):
        parsed = _parse_interface_list(config_entry.get(option), option, itype)
        for tv in ("TAG", "UNTAG"):
            additions[tv].extend(parsed[tv])

    for option, itype in (
        ("remove_lag_interfaces", INTERFACE_TYPE_LAG),
        ("remove_isis_logical_interfaces", INTERFACE_TYPE_ISIS),
    ):
        parsed = _parse_interface_list(config_entry.get(option), option, itype)
        for tv in ("TAG", "UNTAG"):
            removals[tv].extend(parsed[tv])

    return additions, removals


def _current_membership_sets(existing):
    """Group the VLAN's current members as {(tag_value, interface_type): {keys}}."""
    current_sets = {}
    for tv, source in (
        ("TAG", existing.get("taggedInterfaces")),
        ("UNTAG", existing.get("untaggedInterfaces")),
    ):
        for entry in _sanitize_membership(source):
            key = _membership_key(entry)
            combo = (tv, key[0])
            current_sets.setdefault(combo, set()).add(key)
    return current_sets


def _desired_membership_sets(config_entry, *, purge_missing):
    """Build the desired {(tag_value, interface_type): {keys} | None} map.

    None means the combination is not authoritative and is left alone.
    """
    desired_sets = {}
    for tv in ("TAG", "UNTAG"):
        for itype in (INTERFACE_TYPE_LAG, INTERFACE_TYPE_ISIS):
            desired_sets[(tv, itype)] = None

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
    return desired_sets


def _explicit_removal_sets(config_entry):
    """Build {(tag_value, interface_type): {keys}} from the remove_* options."""
    explicit_removals = {}
    for tv in ("TAG", "UNTAG"):
        for itype in (INTERFACE_TYPE_LAG, INTERFACE_TYPE_ISIS):
            explicit_removals[(tv, itype)] = set()

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
    return explicit_removals


def _membership_ops_authoritative(config_entry, existing, *, purge_missing):
    """Compute membership adds/removes for replaced/overridden state.

    When purge_missing=True (overridden), interface types not mentioned in
    config are also purged. When False (replaced), unmentioned types are
    left alone.
    """
    # Build current sets from device state
    current_sets = _current_membership_sets(existing)
    # Process user-specified additions
    desired_sets = _desired_membership_sets(config_entry, purge_missing=purge_missing)
    # Process explicit removals
    explicit_removals = _explicit_removal_sets(config_entry)

    # Compute final additions and removals
    additions_sets = {"TAG": set(), "UNTAG": set()}
    removals_sets = {"TAG": set(), "UNTAG": set()}

    all_combos = set(current_sets.keys()) | set(desired_sets.keys()) | set(explicit_removals.keys())
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

    additions = {tv: [_key_to_entry(k) for k in sorted(additions_sets[tv])] for tv in ("TAG", "UNTAG")}
    removals = {tv: [_key_to_entry(k) for k in sorted(removals_sets[tv])] for tv in ("TAG", "UNTAG")}
    return additions, removals


def _resolve_membership_ops(config_entry, existing, state):
    """Dispatch to the correct membership operation builder."""
    if state == STATE_MERGED:
        return _membership_ops_for_merge(config_entry)
    if state == STATE_REPLACED:
        return _membership_ops_authoritative(config_entry, existing, purge_missing=False)
    if state == STATE_OVERRIDDEN:
        return _membership_ops_authoritative(config_entry, existing, purge_missing=True)
    return {"TAG": [], "UNTAG": []}, {"TAG": [], "UNTAG": []}


def _current_membership_keys(existing):
    """Return {"TAG": set(keys), "UNTAG": set(keys)} for a raw VLAN record."""
    existing = existing or {}
    return {
        "TAG": {_membership_key(e) for e in _sanitize_membership(existing.get("taggedInterfaces"))},
        "UNTAG": {_membership_key(e) for e in _sanitize_membership(existing.get("untaggedInterfaces"))},
    }


def _new_isis_entries(additions, removals, existing):
    """List ISIS memberships a write would add: [(tag_value, name), ...].

    Entries already present on the VLAN (nothing is sent for them, so they
    are not new) and entries removed again in the same task are left out.
    """
    current = _current_membership_keys(existing)
    # Keep the tag side: removing an interface from TAG does not cancel
    # adding it to UNTAG (a tagged<->untagged move is still a new membership).
    removed = {(tv, _membership_key(e)) for tv in ("TAG", "UNTAG") for e in removals.get(tv, [])}
    new_entries = []
    for tv in ("TAG", "UNTAG"):
        for entry in additions.get(tv, []):
            key = _membership_key(entry)
            if (
                entry.get("interfaceType") == INTERFACE_TYPE_ISIS
                and key not in current[tv]
                and (tv, key) not in removed
            ):
                new_entries.append((tv, entry["interfaceName"]))
    return new_entries


def _get_isis_logical_if_ids(connection):
    """GET /v0/configuration/spbm/isis/logical-ifs -- IDs of existing interfaces.

    Returns a set of ID strings, or None when the endpoint cannot be read
    (missing endpoint, error, unexpected body); the caller then skips the
    existence check rather than breaking the task.
    """
    try:
        data = _call_api(connection, "GET", ISIS_LOGICAL_IFS_PATH, allow_not_found=True)
    except (ConnectionError, FeVlansError):
        return None
    if not isinstance(data, list):
        return None
    # Each item identifies its interface through 'logicalIfId'.
    return {
        str(item.get("logicalIfId")) for item in data if isinstance(item, dict) and item.get("logicalIfId") is not None
    }


def _validate_isis_interfaces_exist(connection, config, existing_map):
    """Fail before any write if a requested ISIS logical interface is missing.

    The VLAN endpoints accept an ISIS_LOGICAL_INTERFACE entry for an ID that
    does not exist (HTTP 204) and silently drop it, so existence has to be
    confirmed against the SPBM ISIS circuit endpoint. Only additions are
    checked (isis_logical_interfaces); removals never are. The device list is
    read lazily, once per run, and the check is skipped if it cannot be read.
    """
    requested = []
    for entry in config:
        vlan_id = entry["vlan_id"]
        # Merge-style addition list; replaced/overridden add the same entries.
        additions, removals = _membership_ops_for_merge(entry)
        for _tv, name in _new_isis_entries(additions, removals, existing_map.get(vlan_id)):
            requested.append((vlan_id, name))
    if not requested:
        return
    known_ids = _get_isis_logical_if_ids(connection)
    if known_ids is None:
        return
    missing = [(vid, name) for vid, name in requested if name not in known_ids]
    if missing:
        raise FeVlansError(
            "; ".join(
                "VLAN %d: ISIS logical interface %s does not exist on the "
                "device; create it first (SPBM Isis Circuit Management)" % (vid, name)
                for vid, name in missing
            ),
            details={"missing_isis_logical_interfaces": [{"vlan_id": vid, "name": name} for vid, name in missing]},
        )


def _verify_isis_membership_stored(vlan_id, expected, refreshed):
    """Fail if the device did not keep an ISIS membership it accepted.

    expected is the list from _new_isis_entries(); refreshed is the VLAN
    re-read after the write, or None if the VLAN could not be read back. The
    device answers the PATCH with 204 even when it discards the ISIS entry, so
    only the read-back proves it was stored.
    """
    if not expected:
        return
    if refreshed is None:
        names = ", ".join(name for _tv, name in expected)
        raise FeVlansError(
            "VLAN %d: could not read the VLAN back after the write, so the ISIS "
            "logical interface membership for %s could not be verified as stored." % (vlan_id, names),
            details={"vlan_id": vlan_id, "isis_logical_interfaces": [name for _tv, name in expected]},
        )
    stored = _current_membership_keys(refreshed)
    absent = [name for tv, name in expected if (INTERFACE_TYPE_ISIS, name) not in stored[tv]]
    if absent:
        raise FeVlansError(
            "VLAN %d: the device accepted the request (HTTP 204) but did not "
            "store the ISIS logical interface membership for %s. ISIS "
            "logical interface VLAN membership may not be manageable through "
            "the VLAN endpoints on this device." % (vlan_id, ", ".join(absent)),
            details={"vlan_id": vlan_id, "isis_logical_interfaces": absent},
        )


def _post_lag_membership(connection, vlan_id, operation, payload, writes=None):
    """POST /v0/operation/vlan/{vlan_id}/interfaces/:add or :remove for LAG members.

    The multi-status response is checked per interface; a request that
    succeeded is recorded in writes (a _WriteTracker), when given.
    """
    # Sent directly, not through _call_api(): its error-document check rejects
    # any truthy errorCode, also a per-interface 200/204, before the body is
    # classified. _validate_multi_status() classifies every shape itself, and
    # the httpapi plugin still raises for an HTTP error status.
    response = connection.send_request(
        payload, path="/v0/operation/vlan/%d/interfaces/:%s" % (vlan_id, operation), method="POST"
    )
    _validate_multi_status(operation, vlan_id, response, requested=payload)
    if writes is not None:
        verb = "added LAG members to" if operation == "add" else "removed LAG members from"
        writes.record(vlan_id, "%s VLAN %d" % (verb, vlan_id))


def _apply_membership_changes(
    module,
    connection,
    vlan_id,
    existing,
    additions,
    removals,
    writes=None,
):
    """Apply membership additions/removals. Returns (changed, updated).

    Each request that succeeds is recorded in writes (a _WriteTracker), when given.
    """
    current_tagged = _sanitize_membership(existing.get("taggedInterfaces"))
    current_untagged = _sanitize_membership(existing.get("untaggedInterfaces"))

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
        _post_lag_membership(connection, vlan_id, "add", lag_add_payload, writes)

    if lag_remove_payload:
        _post_lag_membership(connection, vlan_id, "remove", lag_remove_payload, writes)

    if patch_required:
        payload = {}
        if tagged_changed:
            payload["taggedInterfaces"] = current_tagged
        if untagged_changed:
            payload["untaggedInterfaces"] = current_untagged
        if payload:
            # existing is the record the lists were built from (before this write).
            _update_vlan(connection, vlan_id, payload, before=existing, writes=writes)

    return True, working_copy


def _comparable_output(output):
    """An Ansible VLAN output with its membership lists in a fixed order."""
    if output is None:
        return None
    result = dict(output)
    for key in ("tagged_interfaces", "untagged_interfaces"):
        result[key] = sorted(_membership_key(e) for e in output.get(key) or [])
    return result


def _refresh_and_verify(connection, vlan_id, existing_raw, before_output, isis_expected, writes=None):
    """Re-read the VLAN after a real write and verify the ISIS memberships it added.

    Returns the re-read record, or existing_raw when the VLAN cannot be read.
    The device may accept an ISIS entry (204) without storing it; a missing
    read-back (None) proves nothing, so it fails as well. When it fails and the
    read-back still equals 'before', this VLAN's writes changed nothing - a
    dropped ISIS entry was all they carried - so they are not reported as a
    change of the failed task.
    """
    refreshed = _get_vlan(connection, vlan_id)
    try:
        _verify_isis_membership_stored(vlan_id, isis_expected, refreshed)
    except FeVlansError:
        if (
            writes is not None
            and refreshed is not None
            and _comparable_output(_to_ansible_output(refreshed)) == _comparable_output(before_output)
        ):
            writes.forget(vlan_id)
        raise
    return refreshed if refreshed is not None else existing_raw


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
        current = existing.get(rest_key)
        if rest_key == "stpName" and value is not None:
            if _normalize_stp_name(value) != _normalize_stp_name(current):
                payload[rest_key] = value
        elif value is not None and value != current:
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
    desired_name = user_name if user_name is not None else _vlan_default_name(vlan_id)
    if desired_name != existing.get("name"):
        payload["name"] = desired_name

    # vlan_type: user value or default PORT_MSTP_RSTP. A type the option cannot
    # express (e.g. BROUTER) is kept when omitted: it cannot be stated in config,
    # so resetting it would make a re-applied gathered result change the VLAN.
    user_type = config_entry.get("vlan_type")
    current_type = existing.get("vlanType")
    if user_type is None and current_type is not None and current_type not in VLAN_TYPE_CHOICES:
        desired_type = current_type
    else:
        desired_type = user_type if user_type is not None else FULL_DEFAULTS["vlan_type"]
    if desired_type != current_type:
        payload["vlanType"] = desired_type

    # stp_name: user value or default "" (STP instance 0)
    user_stp = config_entry.get("stp_name")
    desired_stp = user_stp if user_stp is not None else FULL_DEFAULTS["stp_name"]
    if _normalize_stp_name(desired_stp) != _normalize_stp_name(existing.get("stpName")):
        payload["stpName"] = desired_stp

    return payload


# -- Before/After Snapshots ----------------------------------------------------


def _predict_after_snapshot(before_snapshot, per_vlan_results):
    """Predict the device's VLAN list after the per-VLAN results are applied.

    Starts from the 'before' snapshot and applies every changed result: a VLAN
    whose result has no 'after' was deleted and drops out, any other changed
    VLAN is replaced (or appended when it is new). Used for check mode, where
    nothing is written and the device cannot be re-read, and for runs where
    nothing changed, which leave the list as it was.
    """
    snapshot = copy.deepcopy(before_snapshot)
    appended = False
    for res in per_vlan_results:
        if not res["changed"]:
            continue
        vlan_id = res["vlan_id"]
        positions = [i for i, vlan in enumerate(snapshot) if vlan.get("vlan_id") == vlan_id]
        if res["after"] is None:
            for pos in reversed(positions):
                del snapshot[pos]
        elif positions:
            snapshot[positions[0]] = copy.deepcopy(res["after"])
        else:
            snapshot.append(copy.deepcopy(res["after"]))
            appended = True
    # The device lists VLANs by ID; keep that order when new VLANs were added.
    if appended and all(isinstance(vlan.get("vlan_id"), int) for vlan in snapshot):
        snapshot.sort(key=lambda vlan: vlan["vlan_id"])
    return snapshot


def _after_snapshot(module, connection, before_snapshot, per_vlan_results, changed):
    """Return the 'after' VLAN list: re-read after a real change, else predicted."""
    if changed and not module.check_mode:
        return _to_ansible_list(_get_all_vlans(connection))
    return _predict_after_snapshot(before_snapshot, per_vlan_results)


# -- State Handlers ------------------------------------------------------------


def _hydrate_scalars(connection, vlan):
    """Re-read a VLAN whose bulk record omits name, vlanType or stpName.

    replaced/overridden reset an omitted scalar, so gathered must carry every
    scalar the device has; the per-VLAN GET reports what the bulk listing
    leaves out.
    """
    if not isinstance(vlan, dict) or vlan.get("id") is None:
        return vlan
    if all(vlan.get(key) is not None for key in ("name", "vlanType", "stpName")):
        return vlan
    full = _get_vlan(connection, vlan["id"])
    return dict(vlan, **full) if isinstance(full, dict) else vlan


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
        raw_list = [_hydrate_scalars(connection, vlan) for vlan in _get_all_vlans(connection)]
    # 'gathered' is the standard key, in the form config accepts, so it can be
    # applied back as is. 'vlans' is the key this module returned for
    # state=gathered up to 1.2.0, in the before/after form with the PORT
    # members; it is kept unchanged so existing playbooks keep working, and is
    # deprecated and goes away in 2.0.0. Note that under the action states
    # 'vlans' carries per-VLAN operation results instead, so consumers should
    # prefer 'gathered' here.
    return {
        "changed": False,
        "gathered": [_to_config_entry(vlan) for vlan in raw_list if vlan.get("id") is not None],
        "vlans": _to_ansible_list(raw_list),
    }


def _handle_single_vlan_merge(module, connection, config_entry, existing_map, writes=None):
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
            _create_vlan(connection, vr_name, vlan_id, vlan_name, vlan_type, stp_name)
            if writes is not None:
                writes.record(vlan_id, "created VLAN %d" % vlan_id)
            existing_raw = _get_vlan(connection, vlan_id) or {"id": vlan_id, "vrName": vr_name}
        else:
            existing_raw = {"id": vlan_id, "vrName": vr_name}
            # An omitted name is auto-assigned by the device as VLAN-<id>,
            # so predict that rather than leaving it unset -- otherwise the
            # check-mode diff shows a name change that never happens.
            existing_raw["name"] = vlan_name if vlan_name is not None else _vlan_default_name(vlan_id)
            if vlan_type is not None:
                existing_raw["vlanType"] = vlan_type
            # _create_vlan() always sends stpName, falling back to "" (STP
            # instance 0), so predict that rather than leaving it unset.
            existing_raw["stpName"] = stp_name if stp_name is not None else FULL_DEFAULTS["stp_name"]
    else:
        existing_raw = copy.deepcopy(existing_raw)

    update_payload = _build_scalar_update_merged(config_entry, existing_raw)
    if update_payload:
        changed = True
        if not module.check_mode:
            # existing_raw is still the pre-PATCH record, used to attribute a failure.
            _update_vlan(connection, vlan_id, update_payload, before=existing_raw, writes=writes)
        for k, v in update_payload.items():
            existing_raw[k] = v

    additions, removals = _resolve_membership_ops(config_entry, existing_raw, STATE_MERGED)
    # ISIS memberships this write adds; verified against the read-back below.
    isis_expected = _new_isis_entries(additions, removals, existing_raw)
    has_ops = any(additions.values()) or any(removals.values())
    if has_ops:
        mem_changed, existing_raw = _apply_membership_changes(
            module,
            connection,
            vlan_id,
            existing_raw,
            additions,
            removals,
            writes,
        )
        if mem_changed:
            changed = True

    if changed and not module.check_mode:
        existing_raw = _refresh_and_verify(connection, vlan_id, existing_raw, before_output, isis_expected, writes)

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
    module,
    connection,
    config_entry,
    existing_map,
    state,
    writes=None,
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
            _create_vlan(connection, vr_name, vlan_id, vlan_name, vlan_type, stp_name)
            if writes is not None:
                writes.record(vlan_id, "created VLAN %d" % vlan_id)
            existing_raw = _get_vlan(connection, vlan_id) or {"id": vlan_id, "vrName": vr_name}
        else:
            existing_raw = {"id": vlan_id, "vrName": vr_name}
            # Same as the merged path: the device auto-names an unnamed VLAN
            # VLAN-<id>, so predict that instead of leaving it unset.
            existing_raw["name"] = vlan_name if vlan_name is not None else _vlan_default_name(vlan_id)
            existing_raw["vlanType"] = vlan_type
            existing_raw["stpName"] = stp_name
    else:
        existing_raw = copy.deepcopy(existing_raw)

    # Sub-issue A fix: reset omitted scalars to FULL_DEFAULTS
    update_payload = _build_scalar_update_replaced(config_entry, existing_raw, vlan_id)
    if update_payload:
        changed = True
        if not module.check_mode:
            # existing_raw is still the pre-PATCH record, used to attribute a failure.
            _update_vlan(connection, vlan_id, update_payload, before=existing_raw, writes=writes)
        for k, v in update_payload.items():
            existing_raw[k] = v

    # Authoritative membership
    purge = state == STATE_OVERRIDDEN
    additions, removals = _membership_ops_authoritative(
        config_entry,
        existing_raw,
        purge_missing=purge,
    )
    # ISIS memberships this write adds; verified against the read-back below.
    isis_expected = _new_isis_entries(additions, removals, existing_raw)
    has_ops = any(additions.values()) or any(removals.values())
    if has_ops:
        mem_changed, existing_raw = _apply_membership_changes(
            module,
            connection,
            vlan_id,
            existing_raw,
            additions,
            removals,
            writes,
        )
        if mem_changed:
            changed = True

    if changed and not module.check_mode:
        existing_raw = _refresh_and_verify(connection, vlan_id, existing_raw, before_output, isis_expected, writes)

    after_output = _to_ansible_output(existing_raw)
    differences = _compute_diff(before_output, after_output) if changed else {}

    return {
        "vlan_id": vlan_id,
        "before": before_output,
        "after": after_output,
        "changed": changed,
        "differences": differences,
    }


def _vlan_protected_reason(raw_vlan):
    """Why a sweep must not delete this VLAN, or None when it may.

    Shared by the overridden pre-pass and deleted without config. Protected
    are VLANs 1 and 4048, the management VLAN (isMgmtInterface), dynamically
    created VLANs (dynamic) and BROUTER VLANs (vlanType BROUTER) -- the same
    rules extreme_fe_l3_interfaces applies.
    """
    vid = raw_vlan.get("id")
    if vid in SYSTEM_VLANS:
        return SYSTEM_VLANS[vid]
    if raw_vlan.get("isMgmtInterface") is True:
        return "management VLAN"
    if raw_vlan.get("dynamic") is True:
        return "dynamic VLAN"
    if str(raw_vlan.get("vlanType") or "").upper() == "BROUTER":
        return "BROUTER VLAN"
    if raw_vlan.get("vlanType") is None:
        # The sweeps hydrate every candidate first (_hydrate_scalars), so a
        # type still missing is unknown: it could be a BROUTER VLAN.
        return "VLAN type not reported"
    return None


def _skip_protected(module, state, raw_vlan, skipped):
    """Record and warn about a protected VLAN a sweep leaves alone; True if skipped."""
    reason = _vlan_protected_reason(raw_vlan)
    if reason is None:
        return False
    vid = raw_vlan.get("id")
    if vid in SYSTEM_VLANS:
        # VLANs 1 and 4048 are always kept and every device has them, so
        # skipping them is silent and they are not reported, as before.
        return True
    module.warn("%s: VLAN %s is protected (%s) and was not deleted" % (state.capitalize(), vid, reason))
    skipped.append({"vlan_id": vid, "reason": reason, "protected": True})
    return True


def _handle_overridden_prepass(module, connection, config, all_vlans, writes=None):
    """Delete VLANs the task did not list (overridden pre-pass).

    overridden is authoritative across the whole device, so a VLAN absent
    from 'config' is removed rather than reset -- matching the resource
    module convention used by ios_vlans, nxos_vlans, eos_vlans and
    junos_vlans. Use state=replaced to confine changes to listed VLANs.

    Protected VLANs (see _vlan_protected_reason) are skipped with a
    warning and reported with protected=True. The reference implementations
    do delete their reserved VLANs, but on Fabric Engine removing the default,
    reserved, management, dynamic or BROUTER VLANs is not recoverable from a
    playbook (or cuts the management connection). A VLAN listed in 'config'
    is never skipped; it is applied as replaced.

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
        if vid is None or vid in listed_ids or _skip_protected(module, STATE_OVERRIDDEN, raw_vlan, skipped):
            continue

        before_output = _to_ansible_output(raw_vlan)
        vr_name = raw_vlan.get("vrName", "GlobalRouter")

        if not module.check_mode:
            try:
                _delete_vlan(connection, vr_name, vid)
            except FeVlansDeleteUnknown:
                # The answer was lost: not a skipped no-op; the task fails
                # with changed true (set by FeVlansDeleteUnknown).
                raise
            except (ConnectionError, FeVlansError) as exc:
                # Report it -- a silently skipped delete looks like success
                # while the VLAN is still on the device.
                skipped.append({"vlan_id": vid, "reason": to_text(exc), "protected": False})
                continue
            if writes is not None:
                writes.record(vid, "deleted VLAN %d" % vid)

        deleted.append(vid)
        results.append(
            {
                "vlan_id": vid,
                "before": before_output,
                "after": None,
                "changed": True,
                "differences": _compute_diff(before_output, None),
            }
        )

    return results, deleted, skipped


def _handle_merge_replace(module, connection, config, state, writes=None):
    """Handle merged/replaced/overridden states."""
    # Bulk GET all VLANs once for efficiency. A listed VLAN whose bulk record
    # omits a scalar is re-read, so replaced does not mistake the omission for
    # a value to reset (gathered hydrates the same way). Under overridden every
    # VLAN is re-read when needed: the pre-pass decides from vlanType whether an
    # unlisted VLAN is a protected BROUTER VLAN.
    listed_ids = {entry.get("vlan_id") for entry in config}
    all_vlans = [
        _hydrate_scalars(connection, vlan) if state == STATE_OVERRIDDEN or vlan.get("id") in listed_ids else vlan
        for vlan in _get_all_vlans(connection)
    ]
    existing_map = {v["id"]: v for v in all_vlans if "id" in v}

    # Capture before snapshot (Sub-issue E fix)
    before_snapshot = _to_ansible_list(all_vlans)

    # Fail before any write (also in check mode) if a requested ISIS logical
    # interface does not exist on the device.
    _validate_isis_interfaces_exist(connection, config, existing_map)

    per_vlan_results = []
    any_changed = False
    deleted_vlans = []
    skipped_vlans = []

    # Overridden pre-pass: delete unlisted VLANs
    if state == STATE_OVERRIDDEN:
        prepass_results, deleted_vlans, skipped_vlans = _handle_overridden_prepass(
            module, connection, config, all_vlans, writes
        )
        per_vlan_results.extend(prepass_results)
        if any(r["changed"] for r in prepass_results):
            any_changed = True
        for skip in (entry for entry in skipped_vlans if not entry["protected"]):
            module.warn(
                "Overridden: VLAN %s could not be deleted and was skipped: %s" % (skip["vlan_id"], skip["reason"])
            )
        # A deleted VLAN must not then be treated as existing config.
        for vid in deleted_vlans:
            existing_map.pop(vid, None)

    # Process each VLAN in config
    for entry in config:
        if state == STATE_MERGED:
            result = _handle_single_vlan_merge(
                module,
                connection,
                entry,
                existing_map,
                writes,
            )
        else:
            result = _handle_single_vlan_replace(
                module,
                connection,
                entry,
                existing_map,
                state,
                writes,
            )
        per_vlan_results.append(result)
        if result["changed"]:
            any_changed = True

    # 'after' is re-read from the device after a real change; in check mode
    # (or when nothing changed) it is predicted from the per-VLAN results.
    after = _after_snapshot(module, connection, before_snapshot, per_vlan_results, any_changed)
    if deleted_vlans and not module.check_mode:
        # 'after' was re-read (the deletes are changes): a VLAN it still lists
        # was not deleted, so it is reported as skipped and not as a change.
        for vid in _check_deletes_applied(after, deleted_vlans, writes):
            deleted_vlans.remove(vid)
            reason = _still_present_message(vid)
            skipped_vlans.append({"vlan_id": vid, "reason": reason, "protected": False})
            module.warn("Overridden: VLAN %s could not be deleted and was skipped: %s" % (vid, reason))
            for res in per_vlan_results:
                if res["vlan_id"] == vid and res["after"] is None:
                    res.update(after=res["before"], changed=False, differences={})
        any_changed = any(res["changed"] for res in per_vlan_results)
    output = {
        "changed": any_changed,
        "before": before_snapshot,
        "after": after,
        "vlans": per_vlan_results,
    }
    if deleted_vlans:
        output["deleted_vlans"] = deleted_vlans
    if skipped_vlans:
        output["skipped_vlans"] = skipped_vlans

    return output


def _handle_deleted(module, connection, config, writes=None):
    """Handle state=deleted: remove specified VLANs or all user VLANs."""
    all_vlans = _get_all_vlans(connection)
    if not config:
        # The sweep decides from vlanType whether a VLAN is a protected BROUTER
        # VLAN, so a record that omits it is re-read first.
        all_vlans = [_hydrate_scalars(connection, vlan) for vlan in all_vlans]
    existing_map = {v["id"]: v for v in all_vlans if "id" in v}
    before_snapshot = _to_ansible_list(all_vlans)

    per_vlan_results = []
    any_changed = False
    skipped_vlans = []

    if config:
        # An explicitly listed VLAN is deleted even when it is protected; the
        # device decides whether it can be removed.
        targets = config
    else:
        # Delete all user-created VLANs, skipping the protected ones
        targets = [
            {"vlan_id": vid, "vr_name": v.get("vrName", "GlobalRouter")}
            for vid, v in existing_map.items()
            if not _skip_protected(module, STATE_DELETED, v, skipped_vlans)
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
        vr_name = (existing or {}).get("vrName") or entry.get("vr_name", "GlobalRouter")

        if existing is None:
            per_vlan_results.append(
                {
                    "vlan_id": vlan_id,
                    "before": None,
                    "after": None,
                    "changed": False,
                    "differences": {},
                }
            )
            continue

        before_output = _to_ansible_output(existing)
        any_changed = True

        if not module.check_mode:
            _delete_vlan(connection, vr_name, vlan_id)
            if writes is not None:
                writes.record(vlan_id, "deleted VLAN %d" % vlan_id)

        per_vlan_results.append(
            {
                "vlan_id": vlan_id,
                "before": before_output,
                "after": None,
                "changed": True,
                "differences": _compute_diff(before_output, None),
            }
        )

    # VLANs removed by the delete are in 'before' and absent from 'after'.
    after = _after_snapshot(module, connection, before_snapshot, per_vlan_results, any_changed)
    if any_changed and not module.check_mode:
        # 'after' was re-read: a VLAN it still lists was not deleted.
        present = _check_deletes_applied(after, [r["vlan_id"] for r in per_vlan_results if r["changed"]], writes)
        if present:
            raise FeVlansError(
                " ".join(_still_present_message(vid) for vid in present),
                details={"still_present": present},
            )
    output = {
        "changed": any_changed,
        "before": before_snapshot,
        "after": after,
        "vlans": per_vlan_results,
    }
    if skipped_vlans:
        output["skipped_vlans"] = skipped_vlans
    return output


# -- Entry Point ---------------------------------------------------------------


def _add_diff(module, result):
    """Set result["diff"] when --diff is active (never called for gathered).

    Ansible renders the before/after pair itself. It is populated whether or
    not anything changed (identical lists render as no diff) and in check mode
    'after' is the predicted state. VLANs removed by 'overridden' or 'deleted'
    are in 'before' and absent from 'after', so --diff shows them.
    """
    # Diff mode (--diff): the same lists as the top-level before/after.
    if module._diff:
        result["diff"] = {"before": result["before"], "after": result["after"]}


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
            msg="value of config parameter must not be empty for state %s (or supply the "
            "deprecated top-level VLAN parameters)" % state
        )
    # Each VLAN may be listed once; checked before the connection is opened so
    # a duplicate fails without any request, also in check mode. 'gathered'
    # ignores config, so it is left alone there.
    if state != STATE_GATHERED:
        _reject_duplicate_vlan_ids(module, config)

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == STATE_GATHERED:
            result = _handle_gathered(module, connection)
            module.exit_json(**result)
        elif state == STATE_DELETED:
            # Every write is recorded, so a failure after one of them reports
            # changed=true and names what was already done (see _WriteTracker).
            with _WriteTracker() as writes:
                result = _handle_deleted(module, connection, config if config else None, writes)
            _add_diff(module, result)
            module.exit_json(**result)
        else:
            # merged, replaced, or overridden
            with _WriteTracker() as writes:
                result = _handle_merge_replace(module, connection, config, state, writes)
            _add_diff(module, result)
            module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeVlansError as err:
        module.fail_json(**err.to_fail_kwargs())


if __name__ == "__main__":
    main()
