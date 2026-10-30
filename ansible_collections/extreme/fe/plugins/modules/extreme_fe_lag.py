# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage ExtremeNetworks Fabric Engine LAGs via HTTPAPI."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_lag
short_description: Manage LAGs on ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
    - "Create and delete Link Aggregation Groups (LAGs) on ExtremeNetworks Fabric Engine switches using the custom
      C(extreme_fe) HTTPAPI transport."
    - "Update Fabric Engine specific LAG attributes such as friendly names, load balancing algorithms, and Fabric Engine
      LACP keys."
    - "Add or remove member ports through the Fabric Engine LAG REST endpoints while propagating device errors back to
      Ansible."
author:
    - Bjorn Haas (@bhaas_extr)
notes:
    - "Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project."
    - "A write that fails without an answer (a lost connection) may have been applied, so the task reports
      C(changed=true) and lists it in C(details.applied_requests) as possibly applied; the delete sweep
      (C(deleted) without C(config), C(overridden)) fails then instead of listing the LAG in C(skipped_lags).
      A LAG or member-port DELETE answered with 404 counts as done, since a DELETE resent after a lost
      answer finds it gone. A LAG create or member-port addition answered with 409 (a resend) is checked
      against a re-read; it counts as done when the LAG shows the submitted settings and reports a valid
      member list (a missing one leaves the members unknown, even for a LAG created without members),
      otherwise the outcome is unknown."
    - "Fabric Engine does not support patching an existing LAG's aggregation mode; delete and recreate the LAG to modify
      C(mode)."
    - "LAGs are supplied through the C(config) list. The former top-level parameters (C(lag_id), C(name),
      C(member_ports), ...) still work as a
      single-entry config and emit a deprecation warning; the two forms cannot be mixed in one task."
    - "Each C(lag_id) may appear only once in C(config). A task that lists the same LAG twice (also as C(80) and
      C('80')) fails before any request is sent, in check mode as well; merge the attributes into one entry."
    - "With C(config), C(overridden) is authoritative across the whole device: LAGs that the task does not list are
      deleted. LAGs it could not delete
      are reported in C(skipped_lags) and raised as warnings. The deprecated top-level form manages a single LAG and
      never deletes unlisted ones."
    - "C(state=deleted) with C(config) omitted or empty (and no deprecated top-level LAG parameter) deletes every LAG on
      the device except the protected ones, in the order the device lists them. A LAG whose delete the device rejects
      is skipped and reported as for C(overridden). C(overridden) keeps the same protected LAGs when it deletes the
      unlisted ones."
    - "A LAG is protected when it is a member (tagged or untagged) of the management VLAN (C(isMgmtInterface) in
      C(GET /v0/configuration/vlan)), when it is the vIST LAG (C(lagId)) or an MLAG port of an MLAG peer
      (C(GET /v0/configuration/mlag/peers) and its C(ports)), or when it is a member of the vIST VLAN of an MLAG peer
      (C(vistVlanId)). Each protected LAG is kept with a warning and listed in C(skipped_lags) with C(protected=true).
      A LAG listed in C(config) is never skipped, and naming a protected LAG in a C(deleted) task deletes it."
    - "The protection data is read only when there is a LAG to delete, and before the first write. MLAG endpoints that
      answer HTTP 404, an empty body or an empty list mean no MLAG protection (an empty object does not). Any other
      read error or response shape, on those endpoints or on the VLAN list, fails the task with C(changed=false) and no LAG deleted. So does an
      error document (also as one entry of a list), an MLAG peer without C(peerId), an MLAG port without C(portId), a
      VLAN without C(id), or a management or vIST VLAN whose C(taggedInterfaces) or C(untaggedInterfaces) is not a
      list of C(interfaceType)/C(interfaceName) entries."
    - "C(replaced) and C(overridden) reset omitted attributes to the factory defaults of a bare MLT: C(name) back to
      C(MLT-<lag_id>),
      C(load_balance_algo) to C(CUSTOM), and C(flex_uni) to C(false)."
    - "Fabric Engine always uses C(CUSTOM) load balancing. When C(load_balance_algo) is set to another value and the
      device reports C(CUSTOM),
      the module emits a warning (once per LAG) and ignores the value: it is not sent, not counted as a difference, and
      check mode predicts C(CUSTOM)."
    - "C(mode) and C(lacp_key) are never reset. Fabric Engine cannot patch the aggregation mode, and C('0') — the key an
      MLT created without one
      carries — is a value the device computes but will not accept as input. To clear either, delete and recreate the
      LAG."
    - "The LACP key space is partitioned by the device: C(0) means no key configured, C(1)-C(512) are the configurable
      keys (matching the CLI C(lacp
      key <1-512|defVal>)), and values of C(1024) and above are assigned internally per port (C(1024) bitwise-OR the
      port ifIndex) so that
      unaggregated ports can never match one another. The module rejects values outside C(1)-C(512) before contacting
      the device. C('0') is the one
      exception: it is accepted as a no-op when the LAG has no key configured yet, so a task that echoes the value the
      device reports still applies, and
      rejected with an explanation when the LAG has a real key."
    - "C(state=gathered) returns the LAGs under C(gathered) in the shape of C(config), so the list can be fed straight
      back as C(config) into a C(merged), C(replaced) or C(overridden) task, which then reports no change.
      C(lacp_key) is included only for a configurable key (C(1)-C(512)); it is left out for a LAG without a key, and
      an omitted C(lacp_key) is never reset. The raw REST records are still returned
      under C(lags), as up to 1.2.1. The gather fails when a LAG record has no C(memberPorts) list (or a null or
      blank member), since publishing C([]) for unknown members would make a C(replaced) or C(overridden)
      re-apply remove them; an empty list is gathered as C(member_ports=[])."
    - "A task that fails after one of its requests already changed the device (a LAG created or deleted, an attribute
      or a member port written) reports C(changed=true). The message names what was already applied, for example
      C(LAG 81 was created, but failed to set 'flexUni'), and C(details) lists it (C(lag_created), C(applied_fields),
      C(failed_field), C(added_ports), C(removed_ports), C(failed_port), C(changed_lags), C(deleted_lags)).
      C(details.applied_requests) lists every write the device accepted, also when only a later read failed. A write
      answered with a success status but an error document counts as rejected, not as applied."
    - "Supports check mode and diff mode. Under C(--diff) the module reports the whole LAG configuration of the device
      before and after the change,
      including LAGs that C(overridden) deletes; combined with C(--check) the reported C(after) is the state that would
      have been written."
requirements:
    - ansible.netcommon
options:
    state:
        description:
            - Desired LAG operation.
            - "C(merged) creates the target LAG when missing and merges the supplied attributes and member ports."
            - "C(replaced) enforces the supplied member list and attributes for the target LAG, removing unstated
              members and resetting omitted
              attributes to their factory defaults."
            - "C(overridden) is like C(replaced) for each listed LAG, and additionally deletes any LAG on the device
              that C(config) does not list, except the protected ones (see the notes)."
            - "C(deleted) removes the specified LAG entirely or prunes the provided members when C(member_ports) or
              C(remove_member_ports) is supplied."
            - "C(deleted) with C(config) omitted or empty deletes every LAG on the device except the protected ones
              (members of the management VLAN or of a vIST VLAN, vIST LAGs and MLAG ports), which are kept with a
              warning and listed in C(skipped_lags). See the notes."
            - "C(gathered) returns the current LAG configuration without applying changes."
        type: str
        choices: [merged, replaced, overridden, deleted, gathered]
        default: merged
    config:
        description:
            - "List of LAGs to manage. Each entry describes one LAG and its desired attributes."
            - "Required for C(merged), C(replaced) and C(overridden), unless the deprecated top-level parameters are
              used instead."
            - "Omitting it, or an empty list, with C(state=deleted) deletes every LAG except the protected ones."
        type: list
        elements: dict
        suboptions:
            lag_id:
                description:
                    - "LAG identifier (Fabric Engine MLT identifier)."
                    - "Accepts string or integer values in the Fabric Engine supported range (1-512)."
                    - "Each LAG may appear only once in C(config). Entries that resolve to the same identifier (for
                      example C(80) and C('80')) are rejected before the device is contacted."
                type: raw
            name:
                description:
                    - "Friendly Fabric Engine name assigned to the LAG."
                type: str
            mode:
                description:
                    - "Fabric Engine aggregation mode to use when creating the LAG."
                    - "A LAG created with C(VLACP) needs at least one C(member_ports) (or C(add_member_ports)) entry:
                      Fabric Engine creates a VLACP LAG without members as C(LACP), so the module refuses it."
                type: str
                choices: [STATIC, LACP, VLACP]
            lacp_key:
                description:
                    - "Fabric Engine aggregation key used when the LAG operates in LACP or VLACP mode."
                    - "Valid values are C(1)-C(512). C(0) is the key the device reports for a LAG with none configured
                      and cannot be written back."
                    - "Not reset by C(replaced) or C(overridden)."
                type: str
            load_balance_algo:
                description:
                    - "Load balancing algorithm applied to the LAG."
                    - "Fabric Engine always reports and applies C(CUSTOM)."
                    - "Another value for an existing LAG the device reports as C(CUSTOM) emits a warning and is ignored,
                      so it never causes a change."
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
                    - "Incremental list of member ports to remove from the LAG when C(state=merged) or
                      C(state=deleted)."
                type: list
                elements: str
            purge_member_ports:
                description:
                    - "Remove member ports that are not present in C(member_ports) (only evaluated when
                      C(state=merged))."
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
            - "A LAG created with C(VLACP) needs at least one C(member_ports) (or C(add_member_ports)) entry:
              Fabric Engine creates a VLACP LAG without members as C(LACP), so the module refuses it."
        type: str
        choices: [STATIC, LACP, VLACP]
    lacp_key:
        description:
            - "Fabric Engine aggregation key used when the LAG operates in LACP or VLACP mode."
            - "Valid values are C(1)-C(512). C(0) is what the device reports for a LAG with no key configured; supplying
              it is accepted only when the
              LAG already has no key, and is rejected with a clear message otherwise because the device provides no way
              to write it back."
            - "Not reset by C(replaced) or C(overridden), so an omitted C(lacp_key) leaves the current value in place."
        type: str
    load_balance_algo:
        description:
            - "Load balancing algorithm applied to the LAG."
            - "Fabric Engine always reports and applies C(CUSTOM); other values are accepted by the API and ignored by
              the device."
            - "For an existing LAG the device reports as C(CUSTOM), a different value emits a warning and is ignored, so
              it never causes a change."
        type: str
        choices: [L2, L3, L3_L4, CUSTOM, PORT]
    flex_uni:
        description:
            - "Enable or disable Flex-UNI (switched UNI) on the Fabric Engine LAG."
            - "Must be true before the LAG can be used in a Switched UNI (SUNI) ISID endpoint; the device otherwise
              rejects the endpoint with
              C(flex-uni must be enabled before creating endpoint)."
            - "Must be false for the LAG to be usable as a Transparent UNI (TUNI) member."
            - "With C(state=merged) omitting this leaves the current device value untouched; with C(state=replaced) or
              C(state=overridden) an omitted
              value is reset to the factory default (false)."
        type: bool
    member_ports:
        description:
            - "List of member ports that participate in the LAG."
            - "With C(state=merged) missing members are added while existing members remain unless C(purge_member_ports)
              is true."
            - "With C(state=replaced) or C(state=overridden) the provided ports become authoritative; unspecified
              members are removed and an empty
              list clears all members."
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
# Task 8: Delete all LAGs (except protected)
# Description:
#   - 'deleted' with config omitted (or empty) deletes EVERY LAG. LAGs
#     in the management VLAN or a vIST VLAN, vIST LAGs and MLAG ports are protected:
#     they are kept, warned about and listed in skipped_lags.
#   - Run it with --check first to see what deleted_lags would contain.
# -------------------------------------------------------------------------
# - name: "Task 8: Delete all Fabric Engine LAGs (except protected)"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Delete all LAGs (except protected)
  extreme.fe.extreme_fe_lag:
    state: deleted

# -------------------------------------------------------------------------
# Task 9: Gather the current LAG configuration
# -------------------------------------------------------------------------
# - name: "Task 9: Gather Fabric Engine LAG configuration"
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
        - "When C(state=gathered), the raw LAG records retrieved from the device (REST field names such as C(lagId) and
          C(memberPorts)), as returned up to 1.2.1. Use C(gathered) to feed the configuration back into a task."
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
  description:
    - LAG configuration on the device after the task ran.
    - In check mode this is the predicted state.
  returned: when state is not gathered
  type: list
  elements: dict
gathered:
  description:
    - Current LAG configuration in the shape of the C(config) option, so it can be supplied back as C(config).
    - Each entry holds the C(config) suboptions C(lag_id), C(name), C(mode), C(lacp_key), C(load_balance_algo),
      C(flex_uni) and C(member_ports).
    - C(lacp_key) is present only when the LAG has a configurable key (C(1)-C(512)).
    - The gather fails when a LAG record has no C(memberPorts) list (or a null or blank member), since its
      member ports are unknown; an empty list is gathered as C(member_ports=[]).
    - Changed in 1.3.0. Up to 1.2.1 this key held the raw REST records, which are still returned under C(lags).
  returned: when state == gathered
  type: list
  elements: dict
  sample:
    - lag_id: "10"
      name: Uplink-LAG-10
      mode: LACP
      lacp_key: "10"
      load_balance_algo: CUSTOM
      flex_uni: false
      member_ports: ["1:5", "1:6"]
deleted_lags:
  description:
    - LAG identifiers deleted by overridden because config did not list them.
    - With state=deleted and config omitted or empty, every LAG deleted (would be deleted in check mode).
  returned: when state == overridden or state == deleted without config, and LAGs were removed
  type: list
  elements: str
  sample: ["40", "50"]
skipped_lags:
  description:
    - LAGs that overridden, or deleted without config, left on the device. Each entry holds C(lag_id) and C(reason).
    - A LAG whose delete the device rejected carries the device error as C(reason).
    - A protected LAG carries C(protected=true) and the protection as C(reason).
  returned: when state == overridden or state == deleted without config, and a LAG was skipped
  type: list
  elements: dict
  sample:
    - lag_id: "10"
      reason: member of management VLAN 4000
      protected: true
    - lag_id: "40"
      reason: "HTTP Error 500: rejected"
"""

from copy import deepcopy
from typing import Any
from urllib.parse import quote, unquote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown

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
    "flexUni": False,  # OpenAPI default: false; device: FLEX-UNI disable
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
    "memberPorts": [],  # Device: a new MLT has no member ports
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


def _validate_lacp_key(lag_id: str, lacp_key: str | None, existing: dict[str, Any] | None) -> None:
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
                "written back; delete and recreate the LAG to clear the key." % (lag_id, current),
                details={"lag_id": lag_id, "current_lacp_key": current},
            )
        return

    try:
        value = int(text)
    except (TypeError, ValueError):
        raise FeLagError("'lacp_key' must be a numeric string; got %r" % (lacp_key,), details={"lag_id": lag_id})
    if not LACP_KEY_MIN <= value <= LACP_KEY_MAX:
        raise FeLagError(
            "'lacp_key' %s is outside the configurable range %d-%d. Values of "
            "0 and >= 1024 are assigned by the device and cannot be set." % (text, LACP_KEY_MIN, LACP_KEY_MAX),
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
    # lacp_key is the LACP aggregation key (1-512), not a credential. no_log must
    # stay False: masking it would make 'gathered' return
    # VALUE_SPECIFIED_IN_NO_LOG_PARAMETER and break feeding gathered output back in.
    "lacp_key": {"type": "str", "no_log": False},
    "load_balance_algo": {"type": "str", "choices": ["L2", "L3", "L3_L4", "CUSTOM", "PORT"]},
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
    "config": {"type": "list", "elements": "dict", "options": {k: dict(v) for k, v in _LAG_ENTRY_SPEC.items()}},
    "gather_filter": {"type": "list", "elements": "str"},
}
# Flat form: same options at the top level. 'purge_member_ports' keeps its
# default here so existing playbooks behave exactly as before.
for _name, _spec in _LAG_ENTRY_SPEC.items():
    ARGUMENT_SPEC[_name] = dict(_spec)


class FeLagError(Exception):
    """Base exception for Fabric Engine LAG module errors."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        changed: bool = False,
        code: Any = None,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        self.changed = changed
        self.code = code

    def to_fail_kwargs(self) -> dict[str, Any]:
        data: dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        if self.code is not None:
            data["code"] = self.code
        if self.changed:
            data["changed"] = True
        return data


def _embedded_error_text(payload: Any) -> str | None:
    """Return the device's error text when a 2xx response body is an error document, else None.

    The httpapi plugin raises for HTTP error statuses, but Fabric Engine can also
    answer a write with a success status and an error body. The markers are those
    the other modules recognise: a non-empty errorCode, a statusCode/code of 400
    or more, or a non-empty errors list. A normal response carries none of them.
    """
    if not isinstance(payload, dict):
        return None
    code = payload.get("statusCode", payload.get("code"))
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    errors = payload.get("errors")
    is_status = isinstance(code, int) and not isinstance(code, bool) and code >= 400
    if not (payload.get("errorCode") or is_status or (isinstance(errors, list) and errors)):
        return None
    text = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if not text and isinstance(errors, list) and errors:
        text = "%d error(s) reported: %s" % (len(errors), errors)
    return to_text(text or "the device returned an error document")


def _describe_write(method: str, path: str, payload: Any) -> str:
    """Name one accepted write for a failure message, e.g. 'updated LAG 10 (name)'."""
    base = "/v0/configuration/lag"
    rest = path[len(base) :].strip("/") if path.startswith(base) else path
    parts = [unquote(part) for part in rest.split("/")] if rest else []
    if method == "POST" and not parts:
        lag_id = payload.get("lagId") if isinstance(payload, dict) else None
        return "created LAG %s" % lag_id if lag_id is not None else "created a LAG"
    if len(parts) == 1:
        if method == "DELETE":
            return "deleted LAG %s" % parts[0]
        fields = ", ".join(sorted(payload)) if isinstance(payload, dict) else ""
        return "updated LAG %s%s" % (parts[0], " (%s)" % fields if fields else "")
    if len(parts) >= 2 and parts[1] == "memberPorts":
        if method == "POST":
            ports = ", ".join(payload) if isinstance(payload, list) else ""
            return "added member ports %s to LAG %s" % (ports, parts[0])
        if method == "DELETE" and len(parts) == 3:
            return "removed member port %s from LAG %s" % (parts[2], parts[0])
    return "%s %s" % (method, path)


class _TrackedConnection:
    """Connection wrapper that remembers which writes of the task the device accepted.

    Every request goes through send_request(). A POST, PATCH, PUT or DELETE counts
    as a successful write only when it returns without raising AND its response is
    not an embedded error document: such a body is raised as a ConnectionError
    here, before anything is recorded, so the write helpers' own failure handling
    sees it like an HTTP error. Once a write has succeeded, a later failure
    (another entry, a member request, a re-read) must not report changed=false
    nor lose what was applied, so run_module() reads *wrote* and *applied*.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.wrote = False
        self.applied: list[str] = []

    def send_request(self, payload: Any, path: str | None = None, method: str | None = None) -> Any:
        verb = (method or "GET").upper()
        try:
            response = self._connection.send_request(payload, path=path, method=method)
        except ConnectionError as exc:
            if verb != "GET" and answer_unknown(exc):
                # No answer (a lost connection; no code, or a negative JSON-RPC
                # code of the persistent connection): the device may have applied
                # the write, so the task reports changed and lists it, marked as such.
                self.wrote = True
                self.applied.append(
                    "%s (answer lost, may have been applied)" % _describe_write(verb, path or "", payload)
                )
            raise
        if verb != "GET":
            embedded = _embedded_error_text(response)
            if embedded is not None:
                raise ConnectionError(
                    "Device rejected %s %s: %s" % (verb, path, embedded), code=_embedded_error_code(response)
                )
            self.wrote = True
            self.applied.append(_describe_write(verb, path or "", payload))
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _embedded_error_code(payload: dict[str, Any]) -> Any:
    """The status an error document carries (errorCode, statusCode or code), as an int when numeric."""
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    return code


def _with_applied_requests(fail_kwargs: dict[str, Any], connection: _TrackedConnection) -> dict[str, Any]:
    """Add the writes the device already accepted to a failure result.

    Every failure after a write reports changed=true and lists the accepted
    writes in details.applied_requests. When the error itself does not already
    state what it completed (a re-read failing after a PATCH or a member removal,
    or the final read-back failing), the list is also named in the message.
    """
    stated = bool(fail_kwargs.get("changed"))
    if not connection.wrote:
        fail_kwargs["changed"] = stated
        return fail_kwargs
    fail_kwargs["changed"] = True
    details = dict(fail_kwargs.get("details") or {})
    details["applied_requests"] = list(connection.applied)
    fail_kwargs["details"] = details
    if not stated:
        lead = to_text(fail_kwargs.get("msg", "")).rstrip()
        if lead and not lead.endswith("."):
            lead += "."
        fail_kwargs["msg"] = "%s The task had already applied: %s." % (lead, "; ".join(connection.applied))
    return fail_kwargs


def _wrap_after_write(exc: Exception, prefix: str, details: dict[str, Any]) -> FeLagError:
    """Re-raise *exc* as an FeLagError that states what was already written (changed=true).

    *prefix* names the completed part ("LAG 10 was created"); *details* is
    merged over the original error's details so its own attribution
    (failed_field, applied_fields, ...) is kept.
    """
    merged: dict[str, Any] = {}
    code = getattr(exc, "code", None)
    if isinstance(exc, FeLagError):
        merged.update(exc.details)
    merged.update(details)
    text = to_text(exc)
    # "Failed to set ..." reads as a clause after the prefix; "HTTP Error ..." keeps its case.
    if len(text) > 1 and text[0].isupper() and text[1].islower():
        text = text[0].lower() + text[1:]
    # An error that already states its own completed part is joined with ';' instead of a second 'but'.
    sep = "; " if isinstance(exc, FeLagError) and exc.changed else ", but "
    return FeLagError("%s%s%s" % (prefix, sep, text), details=merged, changed=True, code=code)


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
        raise FeLagError("'lag_id' is required for every 'config' entry")
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


def _reject_duplicate_lag_ids(entries: list[dict[str, Any]]) -> None:
    """Fail when the same LAG appears more than once in the entry list.

    Every entry is planned against the device state read before the task, so a
    second entry for the same LAG would not see the first one's changes and
    the check-mode 'after' would keep only the last entry's prediction.
    """
    seen: set = set()
    duplicates: list[str] = []
    for entry in entries:
        try:
            # Same normalisation as the processing path, so 80 and '80' collide.
            lag_id = _normalize_lag_id(entry.get("lag_id"))
        except FeLagError:
            # Missing/invalid ids keep their existing, more specific error.
            continue
        if lag_id in seen and lag_id not in duplicates:
            duplicates.append(lag_id)
        seen.add(lag_id)
    if duplicates:
        raise FeLagError(
            (
                "LAG '%s' is listed more than once in 'config'; list each LAG once" % duplicates[0]
                if len(duplicates) == 1
                else "LAGs %s are listed more than once in 'config'; list each LAG once"
                % ", ".join("'%s'" % lag for lag in duplicates)
            ),
            details={"duplicate_lag_ids": duplicates},
        )


def _unique_port_list(values: list[str] | None, *, param_name: str) -> list[str]:
    if not values:
        return []
    unique: list[str] = []
    seen = set()
    for raw in values:
        if not isinstance(raw, str):
            raise FeLagError(f"All entries in '{param_name}' must be strings", details={"invalid_value": raw})
        port = raw.strip()
        if not port:
            raise FeLagError(f"Port names in '{param_name}' cannot be empty")
        if port not in seen:
            seen.add(port)
            unique.append(port)
    return unique


def _has_valid_member_list(record: dict[str, Any]) -> bool:
    """True when the record reports its members: a memberPorts list without a null or blank member.

    Otherwise the members are unknown (_extract_member_ports() would read them as []).
    """
    raw = record.get("memberPorts")
    return isinstance(raw, list) and not any(item is None or str(item).strip() == "" for item in raw)


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
    raise FeLagError("Unexpected response when retrieving LAG configuration summary", details={"response": data})


def _lag_to_config_entry(record: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one REST LAG record into a 'config' entry the module accepts back unchanged.

    Only declared suboptions are emitted, so 'config: "{{ result.gathered }}"'
    passes argument validation and re-applying it is a no-op:
      - lacp_key is left out unless it is a configurable key (1-512). The '0' of
        a LAG with no key and the >= 1024 keys the device assigns itself cannot
        be written, and an omitted lacp_key is never reset.
      - mode and load_balance_algo are left out when the device reports a value
        outside the option choices.
      - member_ports is always present, so replaced/overridden keep the members.
        A record without a memberPorts list (or with a null or blank member)
        fails the gather: publishing [] for an unconfirmed list would make a
        replaced/overridden re-apply remove the real members, and leaving the
        LAG out would make overridden delete it. An empty list is kept.
    Returns None for a record without an identifier.
    """
    lag_id = record.get("lagId")
    if lag_id is None or isinstance(lag_id, bool) or str(lag_id).strip() == "":
        return None
    entry: dict[str, Any] = {"lag_id": str(lag_id).strip()}
    if isinstance(record.get("name"), str):
        entry["name"] = record["name"]
    if record.get("mode") in _LAG_ENTRY_SPEC["mode"]["choices"]:
        entry["mode"] = record["mode"]
    lacp_key = record.get("lacpKey")
    if lacp_key is not None and str(lacp_key).strip().isdigit():
        if LACP_KEY_MIN <= int(str(lacp_key).strip()) <= LACP_KEY_MAX:
            entry["lacp_key"] = str(lacp_key).strip()
    if record.get("loadBalanceAlgo") in _LAG_ENTRY_SPEC["load_balance_algo"]["choices"]:
        entry["load_balance_algo"] = record["loadBalanceAlgo"]
    if "flexUni" in record and record["flexUni"] is not None:
        entry["flex_uni"] = bool(record["flexUni"])
    raw_members = record.get("memberPorts")
    if not _has_valid_member_list(record):
        raise FeLagError(
            "LAG %s: the device did not report a valid memberPorts list, so its member ports are unknown and "
            "cannot be gathered as configuration" % entry["lag_id"],
            details={"lag_id": entry["lag_id"], "memberPorts": raw_members},
        )
    entry["member_ports"] = _extract_member_ports(record)
    return entry


def lags_to_config(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return *records* (REST shape) as the 'config' list returned under 'gathered'."""
    entries = (_lag_to_config_entry(record) for record in records)
    return [entry for entry in entries if entry is not None]


def get_lag_config(connection: Connection, lag_id: str) -> dict[str, Any] | None:
    try:
        data = connection.send_request(None, path=f"/v0/configuration/lag/{lag_id}", method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        return data
    raise FeLagError("Unexpected response when retrieving LAG configuration", details={"response": data})


def _verify_post_conflict(
    connection: Connection, path: str, payload: Any, lag_id: str, applied: Any, what: str
) -> None:
    """Accept a POST answered 409 when a re-read shows it applied; otherwise the outcome is unknown.

    HTTPAPI resends a request after some transport failures, so a first POST
    that created the LAG (or added its member ports) and lost its answer makes
    the resend answer 409 (already exists). The LAG is re-read: when *applied*
    (a check of the re-read record) holds, the POST counts as done and is recorded
    as an accepted write; otherwise, or when the re-read fails, the task fails
    with changed=true and details.outcome unknown. Both POSTs set membership, so
    a record without a valid memberPorts list (see _has_valid_member_list()) is
    never accepted: its members are unknown, even when none were submitted.
    """
    try:
        record = get_lag_config(connection, lag_id)
        reason = None if record is not None else "the re-read does not list LAG %s" % lag_id
    except (ConnectionError, FeLagError) as reread_exc:
        record, reason = None, "LAG %s could not be re-read (%s)" % (lag_id, to_text(reread_exc))
    if record is not None and not _has_valid_member_list(record):
        record, reason = None, "the re-read of LAG %s does not report a valid memberPorts list" % lag_id
    if record is not None:
        if applied(record):
            if isinstance(connection, _TrackedConnection):
                connection.wrote = True
                connection.applied.append(_describe_write("POST", path, payload))
            return
        reason = "the re-read of LAG %s shows other settings" % lag_id
    raise FeLagError(
        "The POST %s %s answered 409 (already exists), and %s; it may have been applied by a first attempt whose "
        "answer was lost, so the outcome is unknown." % (path, what, reason),
        details={"lag_id": lag_id, "outcome": "unknown"},
        changed=True,
        code=409,
    )


def create_lag(connection: Connection, payload: dict[str, Any]) -> None:
    path = "/v0/configuration/lag"
    try:
        connection.send_request(payload, path=path, method="POST")
    except ConnectionError as exc:
        if getattr(exc, "code", None) != 409:
            raise
        lag_id = _normalize_lag_id(payload.get("lagId"))
        members = set(_unique_port_list(payload.get("memberPorts"), param_name="member_ports") or [])

        def created(record: dict[str, Any]) -> bool:
            same = all(record.get(key) == payload[key] for key in ("name", "mode") if key in payload)
            return same and members.issubset(set(_extract_member_ports(record)))

        _verify_post_conflict(connection, path, payload, lag_id, created, "creating LAG %s" % lag_id)


def update_lag(connection: Connection, lag_id: str, payload: dict[str, Any]) -> None:
    if payload:
        connection.send_request(payload, path=f"/v0/configuration/lag/{lag_id}", method="PATCH")


def apply_lag_attributes(connection: Connection, lag_id: str, payload: dict[str, Any]) -> list[str]:
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
                details={"lag_id": lag_id, "failed_field": field, "applied_fields": applied, "attempted": payload},
                changed=bool(applied),
                code=getattr(exc, "code", None),
            )
        applied.append(field)
    return applied


def _gone_on_resend(connection: Connection, exc: ConnectionError, method: str, path: str) -> bool:
    """Return True when a DELETE answered 404, recording it as done.

    The LAG (or member port) was just read as present, and HTTPAPI resends a
    DELETE after some transport failures, so a first attempt that deleted it and
    lost its answer makes the resend answer 404: the delete is done.
    """
    if getattr(exc, "code", None) != 404:
        return False
    if isinstance(connection, _TrackedConnection):
        connection.wrote = True
        connection.applied.append(_describe_write(method, path, None))
    return True


def delete_lag(connection: Connection, lag_id: str) -> None:
    path = f"/v0/configuration/lag/{lag_id}"
    try:
        connection.send_request(None, path=path, method="DELETE")
    except ConnectionError as exc:
        if not _gone_on_resend(connection, exc, "DELETE", path):
            raise


def add_member_ports(connection: Connection, lag_id: str, ports: list[str]) -> None:
    """Add *ports* to the LAG in one POST; a rejection names the ports and the LAG."""
    if not ports:
        return
    path = f"/v0/configuration/lag/{lag_id}/memberPorts"
    try:
        connection.send_request(ports, path=path, method="POST")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 409:
            _verify_post_conflict(
                connection,
                path,
                ports,
                lag_id,
                lambda record: set(ports).issubset(set(_extract_member_ports(record))),
                "adding member ports %s to LAG %s" % (", ".join(ports), lag_id),
            )
            return
        raise FeLagError(
            "Adding member ports %s to LAG %s failed: %s" % (", ".join(ports), lag_id, to_text(exc)),
            details={"lag_id": lag_id, "failed_request": "add_member_ports", "failed_ports": list(ports)},
            code=getattr(exc, "code", None),
        )


def remove_member_ports(connection: Connection, lag_id: str, ports: list[str]) -> None:
    """Remove *ports* one DELETE per port; a rejection names the port and the ones already removed."""
    removed: list[str] = []
    for port in ports:
        path = f"/v0/configuration/lag/{lag_id}/memberPorts/{port}"
        try:
            connection.send_request(None, path=path, method="DELETE")
        except ConnectionError as exc:
            if _gone_on_resend(connection, exc, "DELETE", path):
                removed.append(port)
                continue
            if removed:
                progress = " (member ports already removed: %s)" % ", ".join(removed)
            else:
                progress = " (no member port was removed)"
            raise FeLagError(
                "Removing member port %s from LAG %s failed%s: %s" % (port, lag_id, progress, to_text(exc)),
                details={
                    "lag_id": lag_id,
                    "failed_request": "remove_member_ports",
                    "failed_port": port,
                    "removed_ports": list(removed),
                    "not_removed_ports": [p for p in ports if p not in removed],
                },
                changed=bool(removed),
                code=getattr(exc, "code", None),
            )
        removed.append(port)


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


def _predict_created_lag(lag_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Predict what Fabric Engine reads back for a LAG created with *payload*.

    Starts from the factory state of a bare MLT (name MLT-<id>, mode STATIC,
    lacpKey "0", CUSTOM load balancing, flexUni false, no member ports) and
    overlays the attributes the user supplied. loadBalanceAlgo is always
    CUSTOM because the device ignores any other requested value.
    """
    predicted: dict[str, Any] = {
        "lagId": lag_id,
        "name": _default_lag_name(lag_id),
        "mode": "STATIC",
        "lacpKey": LACP_KEY_FACTORY_DEFAULT,
        "loadBalanceAlgo": LAG_FULL_DEFAULTS["loadBalanceAlgo"],
        "flexUni": LAG_FULL_DEFAULTS["flexUni"],
        "memberPorts": list(LAG_FULL_DEFAULTS["memberPorts"]),
    }
    for key, value in payload.items():
        if key != "loadBalanceAlgo":
            predicted[key] = deepcopy(value)
    return predicted


def _algo_ignored_by_device(requested: str | None, existing: dict[str, Any] | None) -> bool:
    """Return True when Fabric Engine will ignore the requested load balance algorithm.

    Fabric Engine (VOSS) always reports and applies CUSTOM (OpenAPI schema
    LagLoadBalanceAlgo). A non-CUSTOM request against a LAG the device already
    reports as CUSTOM can never converge, so it must not count as a difference.
    """
    if requested is None or requested == "CUSTOM" or not existing:
        return False
    return existing.get("loadBalanceAlgo") == "CUSTOM"


def _warn_algo_ignored(
    module: AnsibleModule, lag_id: str, requested: str | None, existing: dict[str, Any] | None
) -> None:
    """Warn that a non-CUSTOM load_balance_algo is ignored (called once per LAG)."""
    if _algo_ignored_by_device(requested, existing):
        module.warn(
            f"LAG {lag_id}: load_balance_algo '{requested}' is ignored because Fabric Engine always uses CUSTOM; "
            "the value is not applied and is not treated as a change."
        )


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
    if lacp_key is not None and not _is_factory_lacp_key(lacp_key) and lacp_key != existing.get("lacpKey"):
        update_payload["lacpKey"] = lacp_key
    # A non-CUSTOM request on a device that always reports CUSTOM can never
    # converge: skip it so it neither triggers a PATCH nor a reported change.
    if (
        load_balance_algo is not None
        and not _algo_ignored_by_device(load_balance_algo, existing)
        and load_balance_algo != existing.get("loadBalanceAlgo")
    ):
        update_payload["loadBalanceAlgo"] = load_balance_algo
    # Flex-UNI (switched UNI) — compare against the device default (false)
    # so an absent flexUni field is treated as disabled rather than "unknown".
    if flex_uni is not None and flex_uni != bool(existing.get("flexUni", False)):
        update_payload["flexUni"] = flex_uni
    # Fabric Engine cannot PATCH the aggregation mode — surface a clear error
    # instead of silently ignoring the request.
    if mode is not None and mode != existing.get("mode"):
        raise FeLagError(
            "Changing LAG mode on Fabric Engine is not supported via PATCH; "
            "delete and recreate the LAG to modify the mode.",
            details={"current_mode": existing.get("mode"), "requested_mode": mode},
        )
    return update_payload


def _resolve_member_intent(entry: dict[str, Any], state: str) -> tuple[list[str] | None, list[str], list[str], bool]:
    """Validate the member-port parameters for *state* and normalise them.

    Returns (desired_members, add_members, remove_members, purge_members).
    """
    desired_members_param = entry.get("member_ports")
    add_members_param = entry.get("add_member_ports")
    remove_members_param = entry.get("remove_member_ports")

    if state == STATE_MERGED:
        desired_members = (
            _unique_port_list(desired_members_param, param_name="member_ports")
            if desired_members_param is not None
            else None
        )
        add_members = _unique_port_list(add_members_param, param_name="add_member_ports")
        remove_members = _unique_port_list(remove_members_param, param_name="remove_member_ports")
        purge_members = bool(entry.get("purge_member_ports"))
        if purge_members and desired_members is None:
            raise FeLagError("'member_ports' is required for state merged when 'purge_member_ports' is true")
        return desired_members, add_members, remove_members, purge_members

    if state not in (STATE_REPLACED, STATE_OVERRIDDEN):
        raise FeLagError(f"Unsupported state '{state}'")

    # replaced/overridden: the member list is authoritative.
    if add_members_param:
        raise FeLagError(f"'add_member_ports' is not valid for state {state}")
    if remove_members_param:
        raise FeLagError(f"'remove_member_ports' is not valid for state {state}")
    if desired_members_param is None:
        if state == STATE_REPLACED:
            raise FeLagError("'member_ports' is required for state replaced")
        return [], [], [], True
    desired_members = _unique_port_list(desired_members_param, param_name="member_ports")
    return desired_members, [], [], True


def _initial_members(desired_members: list[str] | None, add_members: list[str]) -> list[str]:
    """The member ports a new LAG is created with.

    member_ports when it names any, else add_member_ports (also when
    member_ports is []), so the create already carries the members the task
    supplies instead of adding them afterwards.
    """
    if desired_members:
        return list(desired_members)
    return list(add_members)


def _require_vlacp_members(entry: dict[str, Any], lag_id: str, initial_members: list[str]) -> None:
    """Fabric Engine silently creates a VLACP LAG without member ports as LACP: refuse it."""
    if entry.get("mode") == "VLACP" and not initial_members:
        raise FeLagError(
            "Fabric Engine requires at least one member_ports entry when mode is VLACP",
            details={"lag_id": lag_id, "mode": "VLACP"},
        )


def _preflight_creations(
    connection: Connection, entries: list[dict[str, Any]], state: str, before_snapshot: list[dict[str, Any]]
) -> None:
    """Refuse, before any write, the LAG creations the device would not apply as requested.

    Runs before the delete phase of overridden and before the first entry, so
    a task that cannot succeed changes nothing. Only a LAG that does not exist
    is created; an existing LAG needs no members. *before_snapshot* follows
    gather_filter, so a LAG it leaves out is confirmed absent with its own GET
    before the entry is refused.
    """
    if state not in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
        return
    existing = {_normalize_lag_id(r["lagId"]) for r in before_snapshot if r.get("lagId") is not None}
    for entry in entries:
        lag_id = _normalize_lag_id(entry.get("lag_id"))
        if lag_id in existing:
            continue
        desired_members, add_members, _remove, _purge = _resolve_member_intent(entry, state)
        try:
            _require_vlacp_members(entry, lag_id, _initial_members(desired_members, add_members))
        except FeLagError:
            if get_lag_config(connection, lag_id) is not None:
                continue
            raise


def _create_missing_lag(
    module: AnsibleModule,
    connection: Connection,
    entry: dict[str, Any],
    lag_id: str,
    desired_members: list[str] | None,
    add_members: list[str],
) -> tuple[dict[str, Any], bool, list[str]]:
    """Create a LAG that does not exist yet.

    Returns (current, refreshed_required, initial_members). In check mode
    nothing is sent and *current* is the predicted LAG.
    """
    name = entry.get("name")
    lacp_key = entry.get("lacp_key")
    load_balance_algo = entry.get("load_balance_algo")
    flex_uni = entry.get("flex_uni")

    initial_members = _initial_members(desired_members, add_members)
    # Checked for every creation by _preflight_creations() before any write;
    # repeated here so this path never sends a memberless VLACP create.
    _require_vlacp_members(entry, lag_id, initial_members)
    # Fabric Engine always uses CUSTOM: a different requested value is never
    # sent (neither in the POST nor in the follow-up PATCH). The original
    # *load_balance_algo* is kept so the warning can name what was requested.
    sendable_algo = load_balance_algo if load_balance_algo in (None, "CUSTOM") else None
    payload: dict[str, Any] = _build_create_payload(
        lag_id=lag_id,
        name=name,
        mode=entry.get("mode"),
        lacp_key=lacp_key,
        load_balance_algo=sendable_algo,
        flex_uni=flex_uni,
    )
    if initial_members:
        payload["memberPorts"] = initial_members
    if module.check_mode:
        current = _predict_created_lag(lag_id, payload)
        _warn_algo_ignored(module, lag_id, load_balance_algo, current)
        return current, False, initial_members

    create_lag(connection, payload)
    try:
        current = _complete_created_lag(module, connection, entry, lag_id, payload, sendable_algo)
    except (FeLagError, ConnectionError) as exc:
        # The POST succeeded: the failure must say so and report changed=true.
        raise _wrap_after_write(exc, "LAG %s was created" % lag_id, {"lag_id": lag_id, "lag_created": True})
    return current, True, initial_members


def _complete_created_lag(
    module: AnsibleModule,
    connection: Connection,
    entry: dict[str, Any],
    lag_id: str,
    payload: dict[str, Any],
    sendable_algo: str | None,
) -> dict[str, Any]:
    """Re-read a just-created LAG and PATCH the attributes the POST did not apply."""
    name = entry.get("name")
    lacp_key = entry.get("lacp_key")
    load_balance_algo = entry.get("load_balance_algo")
    flex_uni = entry.get("flex_uni")
    current = get_lag_config(connection, lag_id) or payload
    # A non-CUSTOM request was omitted from the POST; warn (once) that it
    # is ignored because the device reports CUSTOM.
    _warn_algo_ignored(module, lag_id, load_balance_algo, current)
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
        load_balance_algo=sendable_algo,
        flex_uni=flex_uni,
        reset_omitted=False,
    )
    if followup:
        apply_lag_attributes(connection, lag_id, followup)
        current = get_lag_config(connection, lag_id) or current
    return current


def _update_existing_lag(
    module: AnsibleModule,
    connection: Connection,
    entry: dict[str, Any],
    state: str,
    lag_id: str,
    existing: dict[str, Any],
) -> tuple[dict[str, Any], bool, bool]:
    """Patch the attributes of an existing LAG.

    Returns (current, changed, refreshed_required).
    """
    current = existing.copy()
    # replaced/overridden are authoritative: attributes the user omitted
    # are reset to their factory defaults. merged leaves them alone.
    update_payload: dict[str, Any] = _build_update_payload(
        existing=existing,
        lag_id=lag_id,
        name=entry.get("name"),
        mode=entry.get("mode"),
        lacp_key=entry.get("lacp_key"),
        load_balance_algo=entry.get("load_balance_algo"),
        flex_uni=entry.get("flex_uni"),
        reset_omitted=state in (STATE_REPLACED, STATE_OVERRIDDEN),
    )
    if not update_payload:
        return current, False, False
    if module.check_mode:
        current.update(update_payload)
        return current, True, False

    apply_lag_attributes(connection, lag_id, update_payload)
    refreshed = get_lag_config(connection, lag_id)
    if refreshed is not None:
        current = refreshed
    else:
        current.update(update_payload)
    return current, True, True


def _plan_member_changes(
    current_members: list[str],
    desired_members: list[str] | None,
    add_members: list[str],
    remove_members: list[str],
    purge_members: bool,
) -> tuple[list[str], list[str]]:
    """Work out which member ports to add and which to remove."""
    current_member_set = set(current_members)

    ports_to_add: list[str] = []
    for port in (desired_members or []) + add_members:
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
    return ports_to_add, ports_to_remove


def _entry_result(
    lag_id: str,
    changed: bool,
    lag: dict[str, Any] | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    member_additions: list[str],
    member_removals: list[str],
) -> dict[str, Any]:
    """Assemble the per-LAG result returned by _process_entry."""
    result: dict[str, Any] = {"lag_id": lag_id, "changed": changed, "lag": lag, "before": before, "after": after}
    if member_additions:
        result["member_additions"] = _unique_port_list(member_additions, param_name="member_additions")
    if member_removals:
        result["member_removals"] = _unique_port_list(member_removals, param_name="member_removals")
    return result


def _process_entry(module: AnsibleModule, connection: Connection, entry: dict[str, Any], state: str) -> dict[str, Any]:
    """Apply one LAG entry. Returns a per-LAG result including before/after."""
    lag_id = _normalize_lag_id(entry.get("lag_id"))
    desired_members, add_members, remove_members, purge_members = _resolve_member_intent(entry, state)

    existing = get_lag_config(connection, lag_id)
    _validate_lacp_key(lag_id, entry.get("lacp_key"), existing)
    before = deepcopy(existing)
    member_additions: list[str] = []

    # Existing LAG: warn once if the requested algorithm will be ignored.
    _warn_algo_ignored(module, lag_id, entry.get("load_balance_algo"), existing)

    if existing is None:
        changed = True
        current, refreshed_required, initial_members = _create_missing_lag(
            module, connection, entry, lag_id, desired_members, add_members
        )
        member_additions.extend(initial_members)
        progress = "LAG %s was created" % lag_id
    else:
        current, changed, refreshed_required = _update_existing_lag(module, connection, entry, state, lag_id, existing)
        progress = "The attributes of LAG %s were updated" % lag_id if changed else ""

    current_members = _extract_member_ports(current)
    ports_to_add, ports_to_remove = _plan_member_changes(
        current_members, desired_members, add_members, remove_members, purge_members
    )
    if ports_to_add or ports_to_remove:
        changed = True
    member_additions.extend(ports_to_add)
    member_removals = list(ports_to_remove)

    if module.check_mode:
        simulated_members = current_members.copy()
        for port in ports_to_add:
            if port not in simulated_members:
                simulated_members.append(port)
        for port in ports_to_remove:
            if port in simulated_members:
                simulated_members.remove(port)
        current["memberPorts"] = simulated_members
        return _entry_result(
            lag_id, changed, current, before, current if changed else before, member_additions, member_removals
        )

    try:
        final_lag = _apply_member_changes(connection, lag_id, current, ports_to_add, ports_to_remove, progress)
    except (FeLagError, ConnectionError) as exc:
        if not progress:
            raise
        # The LAG itself was already created or patched: say so, changed=true.
        raise _wrap_after_write(exc, progress, {"lag_id": lag_id, "lag_created": existing is None})
    return _entry_result(
        lag_id, changed, final_lag or current, before, final_lag or current, member_additions, member_removals
    )


def _apply_member_changes(
    connection: Connection,
    lag_id: str,
    current: dict[str, Any],
    ports_to_add: list[str],
    ports_to_remove: list[str],
    progress: str,
) -> dict[str, Any] | None:
    """Send the member additions/removals and return the LAG as re-read afterwards.

    The LAG is re-read whenever this entry wrote something (*progress* set or a
    member request sent); otherwise *current* is returned as-is. A removal or
    re-read failing after a successful addition states that the addition happened.
    """
    if ports_to_add:
        add_member_ports(connection, lag_id, ports_to_add)
    if not (progress or ports_to_add or ports_to_remove):
        return current
    try:
        if ports_to_remove:
            remove_member_ports(connection, lag_id, ports_to_remove)
        return get_lag_config(connection, lag_id)
    except (FeLagError, ConnectionError) as exc:
        if not ports_to_add:
            raise
        added = "Member ports %s were added to LAG %s" % (", ".join(ports_to_add), lag_id)
        raise _wrap_after_write(exc, added, {"added_ports": list(ports_to_add)})


def _process_entry_deleted(module: AnsibleModule, connection: Connection, entry: dict[str, Any]) -> dict[str, Any]:
    """Delete one LAG, or prune the listed members from it."""
    lag_id = _normalize_lag_id(entry.get("lag_id"))
    add_members_param = entry.get("add_member_ports")
    if add_members_param:
        raise FeLagError("'add_member_ports' is not valid for state deleted")

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
        return {"lag_id": lag_id, "changed": False, "lag": None, "before": None, "after": None}

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
        return {"lag_id": lag_id, "changed": False, "lag": existing, "before": before, "after": before}

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


VLAN_PATH = "/v0/configuration/vlan"
MLAG_PEERS_PATH = "/v0/configuration/mlag/peers"


def _protection_prefix(source: str, path: str) -> str:
    """The lead of every protection-read failure message."""
    return "Cannot identify the protected LAGs, so no LAG was deleted: reading the %s (GET %s)" % (source, path)


def _protection_read(connection: Connection, path: str, source: str, *, missing_ok: bool) -> list[dict[str, Any]]:
    """GET *path* for the protection rules and return its records.

    Only an answer that means the feature has nothing configured is read as
    "no protection from this source": an empty list, and, when *missing_ok*
    (the MLAG endpoints), also HTTP 404, an empty body or a not-found document.
    An empty object ({}) is not an empty body: it is an unexpected shape.
    Any other error or response shape raises FeLagError naming the source,
    including an error document, at the top level or as one of the rows, that
    came with a success status. The reads run before the first DELETE, so such
    a failure leaves the device untouched (changed=false) instead of deleting a
    LAG that might be protected. The rows themselves are checked by the callers
    (_require_protection_id, _protection_members).
    """
    prefix = _protection_prefix(source, path)
    try:
        data = connection.send_request(None, path=path, method="GET")
    except ConnectionError as exc:
        if missing_ok and getattr(exc, "code", None) == 404:
            return []
        raise FeLagError(
            "%s failed: %s" % (prefix, to_text(exc)),
            details={"protection_source": path},
            code=getattr(exc, "code", None),
        )
    # An empty body reaches the module as None (or ""). {} is a JSON object, not
    # an empty body, and does not identify the vIST LAGs or MLAG ports: it is
    # rejected by the shape check below, before any DELETE.
    if missing_ok and (data in (None, "") or _is_not_found_response(data)):
        return []
    embedded = _embedded_error_text(data)
    if embedded is not None:
        raise FeLagError(
            "%s returned an error document: %s" % (prefix, embedded),
            details={"protection_source": path, "response": data},
        )
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        for index, item in enumerate(data):
            embedded = _embedded_error_text(item)
            if embedded is not None:
                raise FeLagError(
                    "%s returned an error document as entry %d: %s" % (prefix, index, embedded),
                    details={"protection_source": path, "response": data},
                )
        return data
    raise FeLagError(
        "%s returned an unexpected response" % prefix, details={"protection_source": path, "response": data}
    )


def _require_protection_id(row: dict[str, Any], keys: tuple[str, ...], source: str, path: str) -> str:
    """Return the first non-empty identifier of *keys* in a protection row, or raise FeLagError naming the source.

    A row without the identifier its rule needs cannot be read as "protects
    nothing": the task fails before the first DELETE instead.
    """
    for key in keys:
        value = row.get(key)
        if value is not None and not isinstance(value, (dict, list)) and str(value).strip() != "":
            return str(value).strip()
    raise FeLagError(
        "%s returned an entry without %s" % (_protection_prefix(source, path), " or ".join(keys)),
        details={"protection_source": path, "entry": row},
    )


def _protection_members(vlan: dict[str, Any], vlan_id: str, path: str) -> list[str]:
    """LAG ids among the tagged and untagged members of a protecting VLAN record.

    An omitted or null membership list is empty. Anything else that is not a
    list of {interfaceType, interfaceName} dicts raises FeLagError, since the
    LAGs it protects cannot be identified.
    """
    lag_ids: list[str] = []
    source = "VLAN list"
    for key in ("taggedInterfaces", "untaggedInterfaces"):
        members = vlan.get(key)
        if members is None:
            continue
        valid = isinstance(members, list) and all(
            isinstance(member, dict)
            and str(member.get("interfaceType") or "").strip()
            and member.get("interfaceName") is not None
            and str(member.get("interfaceName")).strip()
            for member in members
        )
        if not valid:
            raise FeLagError(
                "%s returned VLAN %s with a malformed %s (expected a list of interfaceType/interfaceName entries)"
                % (_protection_prefix(source, path), vlan_id, key),
                details={"protection_source": path, "entry": vlan},
            )
        for member in members:
            if str(member["interfaceType"]).upper() != "LAG":
                continue
            name = str(member["interfaceName"]).strip()
            if name not in lag_ids:
                lag_ids.append(name)
    return lag_ids


def _add_protection(protected: dict[str, str], lag_id: Any, reason: str) -> None:
    lag_id = str(lag_id).strip()
    if not lag_id:
        return
    if lag_id not in protected:
        protected[lag_id] = reason
    elif reason not in protected[lag_id]:
        protected[lag_id] += "; " + reason


def _mlag_protection(connection: Connection, protected: dict[str, str]) -> dict[str, str]:
    """Add the vIST LAG and the MLAG ports of every MLAG peer to *protected*; return {vistVlanId: peerId}."""
    vist_vlans: dict[str, str] = {}
    for peer in _protection_read(connection, MLAG_PEERS_PATH, "MLAG peers", missing_ok=True):
        peer_id = _require_protection_id(peer, ("peerId",), "MLAG peers", MLAG_PEERS_PATH)
        if peer.get("vistVlanId") not in (None, "", 0, "0"):
            vist_vlans[str(peer["vistVlanId"]).strip()] = peer_id
        if peer.get("lagId") not in (None, "", 0, "0"):
            _add_protection(protected, peer["lagId"], "vIST LAG of MLAG peer %s" % peer_id)
        ports_path = "%s/%s/ports" % (MLAG_PEERS_PATH, quote(peer_id, safe=""))
        ports_source = "MLAG ports of peer %s" % peer_id
        for port in _protection_read(connection, ports_path, ports_source, missing_ok=True):
            port_id = _require_protection_id(port, ("portId",), ports_source, ports_path)
            _add_protection(protected, port_id, "MLAG port of peer %s" % peer_id)
    return vist_vlans


def _protected_lags(connection: Connection) -> dict[str, str]:
    """Map each LAG that a device-wide delete must keep to the reason it is protected.

    Shared by overridden and by deleted without config, so the two never disagree.
    - MLAG: the vIST LAG (lagId of MlagPeerObject) of every peer in GET
      /v0/configuration/mlag/peers and every port (portId of MlagPortId, the MLT id)
      in .../peers/<peerId>/ports, as extreme_fe_mlag reads them.
    - Management and vIST VLANs: every LAG member (interfaceType LAG, interfaceName
      the LAG id) of a VLAN in GET /v0/configuration/vlan (VLAN id in field id,
      vlanId accepted as a fallback) with isMgmtInterface true, or whose id is the
      vistVlanId of an MLAG peer.
    Raises FeLagError when a source cannot be read (see _protection_read) or a row
    lacks what its rule needs: a peer without peerId, a port without portId, a VLAN
    without id/vlanId, or a protecting VLAN whose membership lists are malformed.
    """
    protected: dict[str, str] = {}
    vist_vlans = _mlag_protection(connection, protected)
    for vlan in _protection_read(connection, VLAN_PATH, "VLAN list", missing_ok=False):
        vlan_id = _require_protection_id(vlan, ("id", "vlanId"), "VLAN list", VLAN_PATH)
        reasons = []
        if vlan.get("isMgmtInterface") is True:
            reasons.append("member of management VLAN %s" % vlan_id)
        if vlan_id in vist_vlans:
            reasons.append("member of vIST VLAN %s of MLAG peer %s" % (vlan_id, vist_vlans[vlan_id]))
        for lag_id in _protection_members(vlan, vlan_id, VLAN_PATH) if reasons else []:
            for reason in reasons:
                _add_protection(protected, lag_id, reason)
    return protected


def _delete_lags_except(
    module: AnsibleModule, connection: Connection, keep: set, protected: dict[str, str] | None = None
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Delete every LAG on the device that is neither in *keep* nor in *protected*.

    Shared by overridden (keep = the LAGs config lists) and deleted without
    config (keep empty); both pass *protected* from _protected_lags. LAGs are deleted in the
    order the device lists them; in check mode nothing is sent. A protected LAG
    and a LAG whose DELETE the device rejects are both returned in *skipped*
    ({lag_id, reason}, plus protected=true for a protected one) instead of
    failing the task. The deprecated flat form never reaches this: it manages a
    single LAG and cannot express "everything else".
    """
    deleted: list[str] = []
    skipped: list[dict[str, Any]] = []
    changed = False
    for record in gather_lags(module, connection):
        device_id = record.get("lagId")
        if device_id is None or _normalize_lag_id(device_id) in keep:
            continue
        lag_id = _normalize_lag_id(device_id)
        if protected and lag_id in protected:
            skipped.append({"lag_id": lag_id, "reason": protected[lag_id], "protected": True})
            continue
        if not module.check_mode:
            try:
                delete_lag(connection, lag_id)
            except ConnectionError as exc:
                if answer_unknown(exc):
                    # No answer: the LAG may be deleted, so it is not reported
                    # as skipped; the task fails with changed=true.
                    raise
                # Report it — a silently skipped delete looks like success
                # while the LAG is still on the device.
                skipped.append({"lag_id": lag_id, "reason": to_text(exc)})
                continue
        deleted.append(lag_id)
        changed = True
    return changed, deleted, skipped


def _predict_after(
    before_snapshot: list[dict[str, Any]], results: list[dict[str, Any]], deleted_lags: list[str]
) -> list[dict[str, Any]]:
    """Predict the LAG list after the task from the per-LAG results.

    Used in check mode, where nothing is written and the device cannot be
    re-read. Starts from the pre-change snapshot, drops the LAGs 'overridden'
    would delete, then applies each changed entry: an entry whose 'after' is
    None is removed, any other replaces (or adds) that LAG. Order is kept, new
    LAGs are appended.
    """
    removed = set(deleted_lags)
    changes = {str(res["lag_id"]): res.get("after") for res in results if res.get("changed")}
    predicted: list[dict[str, Any]] = []
    for record in before_snapshot:
        lag_id = _normalize_lag_id(record.get("lagId")) if record.get("lagId") is not None else None
        if lag_id in removed:
            continue
        if lag_id in changes:
            replacement = changes.pop(lag_id)
            if replacement is not None:
                predicted.append(deepcopy(replacement))
            continue
        predicted.append(deepcopy(record))
    predicted.extend(deepcopy(after) for after in changes.values() if after is not None)
    return predicted


def _delete_all_requested(module: AnsibleModule, state: str) -> bool:
    """True for state=deleted with config omitted or empty and no deprecated top-level LAG parameter."""
    return state == STATE_DELETED and not module.params.get("config") and not _flat_form_used(module)


def _delete_phase(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    entries: list[dict[str, Any]],
    before_snapshot: list[dict[str, Any]],
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Phase 1, before the entries are applied: the deletes that span the whole device.

    overridden with config deletes the LAGs config does not list; deleted with
    config omitted or empty (and without the deprecated top-level parameters)
    deletes every LAG. Both keep the protected LAGs (_protected_lags), read
    only when there is a LAG to delete, and warn about every LAG they skip.
    Any other task deletes nothing here.
    """
    if state == STATE_OVERRIDDEN and module.params.get("config"):
        label = "Overridden"
        keep = {_normalize_lag_id(e.get("lag_id")) for e in entries}
    elif not entries and _delete_all_requested(module, state):
        label = "Deleted"
        keep = set()
    else:
        return False, [], []
    candidates = [
        r for r in before_snapshot if r.get("lagId") is not None and _normalize_lag_id(r["lagId"]) not in keep
    ]
    protected = _protected_lags(connection) if candidates else {}
    changed, deleted, skipped = _delete_lags_except(module, connection, keep, protected)
    for skip in skipped:
        if skip.get("protected"):
            module.warn("%s: LAG %s is protected (%s) and was not deleted." % (label, skip["lag_id"], skip["reason"]))
        else:
            module.warn(
                "%s: LAG %s could not be deleted and was skipped: %s"
                % (label, skip.get("lag_id"), skip.get("reason", "unknown"))
            )
    return changed, deleted, skipped


def _apply_entries(
    module: AnsibleModule,
    connection: Connection,
    entries: list[dict[str, Any]],
    state: str,
    deleted_lags: list[str],
) -> tuple[list[dict[str, Any]], bool]:
    """Apply every config entry; returns (per-LAG results, any_changed).

    When an entry fails after earlier entries changed LAGs (or 'overridden'
    deleted some in *deleted_lags*), the failure names them and reports
    changed=true. In check mode those are only predictions and the original
    error is raised unchanged.
    """
    results: list[dict[str, Any]] = []
    changed = False
    for entry in entries:
        try:
            if state == STATE_DELETED:
                result = _process_entry_deleted(module, connection, entry)
            else:
                result = _process_entry(module, connection, entry, state)
        except (FeLagError, ConnectionError) as exc:
            done = [str(res["lag_id"]) for res in results if res.get("changed")]
            # In check mode deleted_lags and the earlier results are predictions:
            # nothing was written, so the failure must not claim it was.
            if module.check_mode or (not done and not deleted_lags):
                raise
            parts = []
            if deleted_lags:
                parts.append("deleted LAG(s) %s" % ", ".join(deleted_lags))
            if done:
                parts.append("changed LAG(s) %s" % ", ".join(done))
            raise _wrap_after_write(
                exc,
                "This task already %s" % " and ".join(parts),
                {"changed_lags": done, "deleted_lags": list(deleted_lags)},
            )
        results.append(result)
        if result.get("changed"):
            changed = True
    return results, changed


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    if not module._socket_path:
        module.fail_json(msg="Connection type httpapi is required for this module")

    try:
        # Wrapped so any failure after a successful write reports changed=true.
        connection = _TrackedConnection(Connection(module._socket_path))
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))
        return

    state = module.params.get("state")

    try:
        if state == STATE_GATHERED:
            lags = gather_lags(module, connection)
            # 'gathered' is in the 'config' shape, so it can be fed straight back
            # into a task. 'lags' keeps the raw REST records it carried up to
            # 1.2.1, for backward compatibility with existing playbooks.
            module.exit_json(changed=False, lags=lags, gathered=lags_to_config(lags))

        entries = _entries_from_params(module)
        # deleted with config omitted or empty deletes every unprotected LAG (see _delete_phase).
        if not entries and not _delete_all_requested(module, state):
            module.fail_json(
                msg="value of config parameter must not be empty for state %s "
                "(or supply the deprecated top-level LAG parameters)" % state
            )
        # Reject repeated LAGs before the first GET, so nothing is read or written.
        _reject_duplicate_lag_ids(entries)

        before_snapshot = gather_lags(module, connection)
        # Refuse creations that cannot succeed before the delete phase and the
        # first entry write anything (also in check mode).
        _preflight_creations(connection, entries, state, before_snapshot)

        # Phase 1: overridden removes LAGs absent from config; deleted without
        # config removes every LAG that is not protected.
        changed, deleted_lags, skipped_lags = _delete_phase(module, connection, state, entries, before_snapshot)

        # Phase 2: apply each entry.
        results, entries_changed = _apply_entries(module, connection, entries, state, deleted_lags)
        changed = changed or entries_changed

        # 'after' is re-read from the device after a real change; in check mode
        # (or when nothing changed) it is predicted from the per-LAG results.
        if changed and not module.check_mode:
            after_snapshot = gather_lags(module, connection)
        else:
            after_snapshot = _predict_after(before_snapshot, results, deleted_lags)
        output: dict[str, Any] = {
            "changed": changed,
            "before": before_snapshot,
            "after": after_snapshot,
            "lags": results,
        }
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

        # Diff mode (--diff): Ansible renders the before/after pair itself. It is
        # populated whether or not anything changed (identical lists render as no
        # diff) and in check mode 'after' is the predicted state. LAGs deleted by
        # 'overridden' are in 'before' and absent from 'after', so --diff shows them.
        if module._diff:
            output["diff"] = {"before": before_snapshot, "after": after_snapshot}

        module.exit_json(**output)
    except ConnectionError as exc:
        fail_kwargs = {"msg": to_text(exc), "code": getattr(exc, "code", None), "changed": False}
        module.fail_json(**_with_applied_requests(fail_kwargs, connection))
    except FeLagError as err:
        module.fail_json(**_with_applied_requests(err.to_fail_kwargs(), connection))


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
