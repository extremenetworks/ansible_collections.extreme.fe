# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage syslog configuration on Extreme Fabric Engine switches.

Module Architecture Overview
============================
This module manages the global syslog admin state and the list of syslog
servers on Extreme Fabric Engine switches via the REST OpenAPI.

REST Endpoints used:
  GET   /v0/configuration/syslog
        -> Retrieve a SyslogSettings object: {enabled, servers: [SyslogServer]}
  PATCH /v0/configuration/syslog
        -> Partially update the global syslog admin state
           (body is a SyslogSettingsUpdate object: {enabled}, x-nos:
           fabric-engine, success response is 204 No Content)
  PUT   /v0/configuration/syslog/servers
        -> Replace the COMPLETE syslog servers list
           (body is a SyslogServerUpdate object: {servers: [SyslogServer]},
           success response is 204 No Content)

Fields used (OpenAPI schema SyslogSettings / SyslogServer):
  enabled            - global syslog admin state (x-nos: fabric-engine)
  servers[].hostId   - resource identifier (string, 1-10 chars per OpenAPI;
                        the VOSS CLI further restricts it to the decimal
                        range 1-10, confirmed via User Guide and a live
                        device - see HOST_ID_MIN/HOST_ID_MAX)
  servers[].ipAddress.address / .ipAddressType - GeneralIpAddress
                        (IPv4 or IPv6 only - this schema has no "hostname"
                        discriminator, unlike NTP's GeneralHostOrIp)
  servers[].port     - UDP port (OpenAPI: 0-65535; VOSS range and default
                        confirmed 514-530 / 514 - see below)
  servers[].enabled  - per-server admin state
  servers[].facility - enum LOCAL0-LOCAL7
  servers[].logLevel - array of SeverityLevels (EMERGENCY, ALERT, CRITICAL,
                        ERROR, WARNING, NOTICE, INFORMATIONAL, DEBUG). VOSS
                        has four severities and stores EMERGENCY and ALERT
                        as CRITICAL, NOTICE and DEBUG as INFORMATIONAL
                        (OpenAPI SeverityLevels)

Fields excluded (out of scope):
  servers[].vrName            - x-nos: switch-engine (EXOS only)
  secure-forwarding mode / tcp-port / server-cert-name, syslog max-hosts
                               - documented in the User Guide CLI but not
                                 present anywhere in the OpenAPI schema for
                                 these two endpoints, so this module never
                                 reads or writes them

Fabric Engine constraints:
  - PATCH only carries {enabled}; PUT only carries {servers}. A single
    Ansible task can change both, but they are always two independent
    REST calls, each skipped when its own part of the config already
    matches the device.
  - There is no PATCH, POST or DELETE for individual servers - only a full
    PUT of the complete list. Every state that changes the servers list is
    therefore a read-modify-write: fold the user's config into the current
    list according to the requested state, then PUT the complete result.
    The PUT is skipped when the folded result already matches the device.
  - Per the module skill's singleton-with-sub-resource-list pattern: for
    'replaced' and 'overridden', the servers list is a SET - the supplied
    list (when the 'servers' key is present in config at all) becomes the
    complete list, and servers on the device but not in it are removed.
    'replaced' leaves the current list untouched only when 'servers' is
    omitted from config entirely; 'overridden' always treats an omitted
    'servers' key as "no servers desired" (full wipe). This makes
    'replaced' and 'overridden' behave identically for the servers list
    whenever 'servers' is supplied - the only state that behaves
    differently between them is the scalar 'enabled' field, which
    'replaced' leaves alone when omitted and 'overridden' resets to its
    factory default when omitted. This mirrors extreme_fe_ntp_global's own
    servers-list handling exactly, adapted for a hostId identity instead
    of an address identity.
  - address (servers[].address) is required on every server entry for
    merged, replaced and overridden - including one that already exists
    on the device - matching the collection's config-list convention
    (e.g. extreme_fe_local_users requires level/enabled on every entry).
    This trades a little repetition for not inventing a "required only
    when creating" rule the skill does not describe anywhere.
  - Neither servers[].port, servers[].enabled, servers[].facility nor
    servers[].logLevel has a documented OpenAPI default. All four factory
    defaults below were confirmed directly against a live device GET
    response (2026-09-23) for a syslog host created with none of them
    supplied, and the global 'enabled' default was confirmed the same way
    - see FULL_DEFAULTS and SERVER_FULL_DEFAULTS.

Supported states:
  - merged     : Additive - the supplied 'enabled' (if any) is applied, and
                 supplied servers are added or updated; servers already on
                 the device that are not mentioned are kept as-is
  - replaced   : 'enabled', if supplied, is applied (left alone if
                 omitted). If 'servers' is supplied, it becomes the
                 complete servers list - unlisted servers are removed. If
                 'servers' is omitted, the current list is left untouched
  - overridden : 'enabled' is applied or reset to its factory default if
                 omitted. The supplied 'servers' list (empty list if
                 omitted) becomes the complete servers list
  - deleted    : With config, only the fields/servers named are reset or
                 removed. Without config, the whole syslog configuration
                 is reset to factory defaults (enabled: true, servers: [])
  - gathered   : Read-only, returns the current syslog configuration

Code Flow (run_module):
  1. Connect to the switch via httpapi
  2. GET the current syslog configuration (enabled + servers)
  3. Build the desired {enabled, servers} block for the requested state
  4. PATCH {enabled} only if it differs, PUT {servers} only if it differs
  5. Re-read and return before/after/differences
"""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_syslog
short_description: Manage syslog configuration on ExtremeNetworks Fabric Engine switches
version_added: "1.3.0"
description:
  - Manage the global syslog admin state and the syslog servers list on
    ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe)
    HTTPAPI plugin.
  - Uses C(/v0/configuration/syslog) and C(/v0/configuration/syslog/servers)
    from the NOS OpenAPI schema.
  - C(/v0/configuration/syslog) exposes C(PATCH) for the global C(enabled)
    flag only. C(/v0/configuration/syslog/servers) exposes C(PUT) only, and
    always replaces the complete servers list - there is no per-server
    C(PATCH), C(POST) or C(DELETE). A single task may change both
    C(enabled) and C(servers); each is sent as its own request and each is
    skipped independently when that part of the configuration already
    matches the device.
author:
  - Andreea-Lavinia Vraja (@avraja_extr)
requirements:
  - ansible.netcommon
notes:
  - Tested against Fabric Engine Version 9.3.2.
  - A PATCH or PUT that fails without an answer (a lost connection) may have been applied, so the task
    reports C(changed=true) with C(details.outcome=unknown).
  - C(enabled) (the global syslog admin state) is marked C(x-nos=fabric-engine)
    in the OpenAPI spec, meaning it applies only to Fabric Engine (VOSS),
    which matches this collection's target platform.
  - C(config.servers[].vr_name) does not exist in this module - the REST
    C(vrName) field is marked C(x-nos=switch-engine) (Switch Engine/EXOS
    only) and is never read or written.
  - Secure forwarding (mode, TCP port, server certificate name) and
    C(syslog max-hosts) are documented in the Fabric Engine CLI but are not
    present anywhere in the OpenAPI schema for these two endpoints, so this
    module never reads or writes them.
  - C(config.servers[].host_id) is the resource identifier for a syslog
    server, matching the VOSS CLI's C(syslog host <1-10>). The OpenAPI
    spec types it as a 1-10 character string; the VOSS CLI further
    restricts it to the decimal range 1-10, confirmed against a live
    device, and that firmware-confirmed range is what this module enforces.
  - C(config.servers[].address) is required on every server entry for
    C(merged), C(replaced) and C(overridden), including one that already
    exists on the device. There is no per-server C(PATCH), so every write
    is a full read-modify-write of the whole servers list, and requiring
    the address on every entry avoids inventing a "required only when
    creating" rule.
  - C(config.servers[].port) accepts the OpenAPI-documented Fabric Engine
    (VOSS) range of 514-530, confirmed by the User Guide's C(udp-port
    <514-530>) parameter and by a live device. This is narrower than the
    OpenAPI schema's raw C(0-65535) bounds, which describe the field's
    general type rather than the Fabric Engine-specific range stated in
    the same field's description.
  - Neither C(config.servers[].port), C(config.servers[].enabled),
    C(config.servers[].facility) nor C(config.servers[].log_level) has a
    documented OpenAPI default. All four factory defaults, and the global
    C(config.enabled) default, were confirmed against a live device on
    2026-09-22/2026-09-23 rather than assumed - see the module's
    FULL_DEFAULTS and SERVER_FULL_DEFAULTS comments for the exact source
    of each value.
  - For C(replaced) and C(overridden), the servers list is treated as a
    set, matching the module skill's singleton-with-sub-resource-list
    pattern - the supplied C(servers) list (when that key is present in
    config at all) becomes the complete list, and any server on the
    device but not in it is removed. C(replaced) leaves the current list
    untouched only when C(servers) is omitted from config entirely;
    C(overridden) always treats an omitted C(servers) key as "no servers
    desired" (a full wipe). The two states therefore behave identically
    for the servers list whenever C(servers) is supplied, and differ only
    in how they treat the scalar C(enabled) field when it is omitted.
  - Supports check mode and diff mode. Under C(--diff) the module reports
    the syslog configuration before and after the change; combined with
    C(--check) the reported "after" is the state that would have been
    written.
  - The admin state (C(enabled), a PATCH) and the servers list (a PUT) are
    two requests. When the PUT fails after the PATCH succeeded, the task fails
    with C(changed=true) and a message saying the admin state was already
    applied. A failure of the first request reports C(changed=false); a
    failure of the re-read after the writes reports C(changed=true).
options:
  config:
    description:
      - Syslog configuration to manage.
      - Required when C(state) is C(merged), C(replaced) or C(overridden).
      - A C(config) with no option set (for example C({})) counts as omitted for these
        states and fails before any request is sent.
      - Optional when C(state=deleted); if omitted, or given with no option set, C(enabled) and
        C(servers) are both reset to their factory defaults.
    type: dict
    suboptions:
      enabled:
        description:
          - Global syslog admin state.
          - Factory default is C(true) (see the module notes).
          - When omitted, C(merged) and C(replaced) leave the current
            value alone and C(overridden) resets it to C(true).
        type: bool
      servers:
        description:
          - List of syslog servers.
          - C(merged) adds the listed servers and keeps the ones already
            configured that are not listed.
          - C(replaced) and C(overridden) make this list the complete
            server list; servers that are not listed are removed.
          - C(deleted) removes only the listed servers (by C(host_id)).
        type: list
        elements: dict
        suboptions:
          host_id:
            description:
              - Identifier of the syslog host slot, matching the VOSS CLI
                C(syslog host <1-10>). Accepts C(1) to C(10).
              - Compared as a number, so C("01") and C("1") name the same
                server.
            type: str
            required: true
          address:
            description:
              - IPv4 or IPv6 address of the syslog server.
              - Required when C(state) is C(merged), C(replaced) or
                C(overridden), including for a C(host_id) that already
                exists on the device.
            type: str
          address_type:
            description:
              - Type of identifier supplied in C(address).
              - When omitted it is derived from C(address).
              - Supplying a value that contradicts C(address) fails the
                task.
            type: str
            choices: [IPv4, IPv6]
          port:
            description:
              - UDP port used to send syslog messages to this server.
              - Accepts 514 to 530. Factory default is C(514).
              - When omitted, C(merged) and C(replaced) leave an existing
                server's current value alone and default a newly added
                server to C(514); C(overridden) always resets an omitted
                value to C(514).
            type: int
          enabled:
            description:
              - Admin state of this syslog server.
              - Factory default is C(false).
              - Follows the same omitted-value rule as C(port).
            type: bool
          facility:
            description:
              - UNIX syslog facility used for messages sent to this server.
              - Factory default is C(LOCAL7).
              - Follows the same omitted-value rule as C(port).
            type: str
            choices: [LOCAL0, LOCAL1, LOCAL2, LOCAL3, LOCAL4, LOCAL5, LOCAL6, LOCAL7]
          log_level:
            description:
              - Severity levels for which to send syslog messages to this
                server.
              - Factory default is C([CRITICAL, ERROR, WARNING, INFORMATIONAL]).
              - Follows the same omitted-value rule as C(port).
              - Treated as a set - order and duplicates are ignored, and the
                module reports levels in severity order.
              - Fabric Engine stores four severities. C(EMERGENCY) and
                C(ALERT) are stored as C(CRITICAL), C(NOTICE) and C(DEBUG)
                as C(INFORMATIONAL). The module applies the same mapping to
                the requested levels, compares and sends the stored values,
                and warns when it mapped a level, so a repeated task reports
                no change.
            type: list
            elements: str
            choices: [EMERGENCY, ALERT, CRITICAL, ERROR, WARNING, NOTICE, INFORMATIONAL, DEBUG]
  state:
    description:
      - Desired module operation.
      - C(merged) applies the supplied C(enabled) and adds/updates the
        supplied servers, leaving everything else on the device untouched.
      - C(replaced) applies the supplied C(enabled) (left alone if
        omitted). If C(servers) is supplied, it becomes the complete
        servers list.
      - C(overridden) applies C(enabled) or resets it to its factory
        default if omitted, and makes the supplied C(servers) (empty if
        omitted) the complete servers list.
      - C(deleted) resets the fields/removes the servers named in
        C(config). When C(config) is omitted, the whole syslog
        configuration is reset to its factory defaults.
      - C(gathered) returns the current syslog configuration without
        making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
"""

EXAMPLES = r"""
# - name: Configure syslog
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Enable syslog globally and add a server
  extreme.fe.extreme_fe_syslog:
    state: merged
    config:
      enabled: true
      servers:
        - host_id: "1"
          address: 10.10.10.1
          port: 514
          enabled: true
          facility: LOCAL7
          log_level: [ERROR, CRITICAL]

- name: Update one server without touching the others
  extreme.fe.extreme_fe_syslog:
    state: merged
    config:
      servers:
        - host_id: "1"
          address: 10.10.10.1
          enabled: false

- name: Make the listed servers the complete server list
  extreme.fe.extreme_fe_syslog:
    state: replaced
    config:
      servers:
        - host_id: "1"
          address: 10.10.10.1
        - host_id: "2"
          address: "2001:db8::1"

- name: Enforce the exact syslog configuration
  extreme.fe.extreme_fe_syslog:
    state: overridden
    config:
      enabled: true
      servers:
        - host_id: "1"
          address: 10.10.10.1

- name: Remove one syslog server
  extreme.fe.extreme_fe_syslog:
    state: deleted
    config:
      servers:
        - host_id: "1"

- name: Reset the whole syslog configuration to factory defaults
  extreme.fe.extreme_fe_syslog:
    state: deleted

- name: Collect the current syslog configuration
  extreme.fe.extreme_fe_syslog:
    state: gathered
  register: syslog_info
"""

RETURN = r"""
---
changed:
  description: Indicates whether any configuration changes were made.
  returned: always
  type: bool
before:
  description:
    - Syslog configuration before any changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
after:
  description:
    - Syslog configuration after changes.
    - Returned for every action state, also when nothing changed (then equal to C(before)).
    - In check mode this is the predicted state that would have been written.
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
gathered:
  description:
    - Current syslog configuration gathered from the device.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: dict
syslog:
  description: Syslog configuration state with differences (per-resource detail).
  returned: always
  type: dict
  contains:
    before:
      description: Syslog configuration before the requested change.
      returned: when state != gathered
      type: dict
    after:
      description: Syslog configuration after the requested change.
      returned: when state != gathered
      type: dict
    config:
      description: Current syslog configuration in gathered mode.
      returned: when state == gathered
      type: dict
    differences:
      description: Changed fields with before and after values.
      returned: when state != gathered
      type: dict
submitted:
  description: Payload(s) submitted to the device (the PATCH and/or PUT bodies) when a change was required.
  returned: when a change was required
  type: dict
"""

# ip_address - standard library helper used to validate addresses and to
# normalize IPv6 into its compressed canonical form so comparisons are stable
from ipaddress import ip_address

# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any

# AnsibleModule - the core class every Ansible module must instantiate;
# it handles argument parsing, check mode, exit/fail, etc.
from ansible.module_utils.basic import AnsibleModule

# to_text - safely converts bytes/strings to unicode text
from ansible.module_utils.common.text.converters import to_text

# Connection - communicates with the device through the httpapi plugin;
# ConnectionError - raised when the device is unreachable or returns a
# transport error
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import is_answer_unknown_code

# ── Constants ─────────────────────────────────────────────────────────────────
# These constants define the REST API endpoints the module communicates with.
# The NOS OpenAPI spec exposes syslog under /v0/configuration/syslog (global
# 'enabled' + the 'servers' list on GET, 'enabled' only on PATCH) and
# /v0/configuration/syslog/servers (full-list PUT for 'servers').

SYSLOG_CONFIG_PATH = "/v0/configuration/syslog"
SYSLOG_SERVERS_PATH = "/v0/configuration/syslog/servers"

# host_id range confirmed by the VOSS CLI ("syslog host <1-10>") and by a
# live device (Id: 2, Id: 7 in 'show syslog host <n>' output). The OpenAPI
# schema only bounds it as a 1-10 character string; this narrower,
# firmware-confirmed numeric range is what the module enforces.
HOST_ID_MIN = 1
HOST_ID_MAX = 10

# Port range from the OpenAPI field description ("Fabric Engine (VOSS)
# range is 514-530") and the User Guide's "udp-port <514-530>" parameter -
# narrower than the schema's raw 0-65535 bounds, which describe the
# field's general type rather than the Fabric Engine-specific range
# stated in that same description.
PORT_MIN = 514
PORT_MAX = 530

# Valid values for the GeneralIpAddress discriminator (OpenAPI enum). This
# schema has no "hostname" option, unlike NTP's GeneralHostOrIp.
ADDRESS_TYPES = ["IPv4", "IPv6"]

# OpenAPI SyslogServer.facility enum.
FACILITY_CHOICES = [
    "LOCAL0",
    "LOCAL1",
    "LOCAL2",
    "LOCAL3",
    "LOCAL4",
    "LOCAL5",
    "LOCAL6",
    "LOCAL7",
]

# OpenAPI SeverityLevels enum. VOSS accepts any combination in a request,
# but stores only four severities (see SEVERITY_STORED_AS).
SEVERITY_CHOICES = [
    "EMERGENCY",
    "ALERT",
    "CRITICAL",
    "ERROR",
    "WARNING",
    "NOTICE",
    "INFORMATIONAL",
    "DEBUG",
]

# Levels Fabric Engine does not store as such, and the level it stores and
# reads back instead (OpenAPI SeverityLevels: EMERGENCY, ALERT, CRITICAL ->
# FATAL, read as CRITICAL; NOTICE, INFORMATIONAL, DEBUG -> INFO, read as
# INFORMATIONAL). Confirmed on 9.4 and 9.5: without this mapping a
# task naming one of these levels reported a change on every run.
SEVERITY_STORED_AS = {
    "EMERGENCY": "CRITICAL",
    "ALERT": "CRITICAL",
    "NOTICE": "INFORMATIONAL",
    "DEBUG": "INFORMATIONAL",
}

# Ansible parameter name -> REST API field name mapping for the global
# scalar. Only one field: the PATCH body (SyslogSettingsUpdate) carries
# nothing else.
FIELD_MAP = {
    "enabled": "enabled",  # Global syslog admin state
}

# Ansible parameter name -> REST API field name mapping for one server
# entry. Excluded: vrName (x-nos: switch-engine).
SERVER_FIELD_MAP = {
    "host_id": "hostId",  # Resource identifier, VOSS CLI "syslog host <n>"
    "port": "port",  # UDP port, VOSS range 514-530
    "enabled": "enabled",  # Per-server admin state
    "facility": "facility",  # UNIX syslog facility enum
    "log_level": "logLevel",  # Array of SeverityLevels
}

# Factory default for the global scalar. Not in the OpenAPI schema -
# confirmed against a live device GET response (2026-09-23) and matching
# the User Guide's "syslog enable ... The default is enabled."
# Default from User Guide + live device (not in OpenAPI), confirmed by user.
FULL_DEFAULTS: dict[str, Any] = {
    "enabled": True,  # Syslog is on at factory default
    "servers": [],  # No syslog servers configured at factory default
}

# Factory defaults for a server's own fields, used to fill a field the
# user omitted: for a newly added entry under 'merged', and for any
# omitted entry field under 'replaced'/'overridden' (both are
# authoritative per-entry, per the module skill's config-list convention).
# None of these has an OpenAPI default; all four were confirmed against a
# live device GET response (2026-09-23) for a host created via
# "syslog host 2 address 192.0.2.1" with nothing else supplied:
#   {"enabled": false, "facility": "LOCAL7", "port": 514,
#    "logLevel": ["CRITICAL", "ERROR", "WARNING", "INFORMATIONAL"]}
# Default from User Guide + live device (not in OpenAPI), confirmed by user.
SERVER_FULL_DEFAULTS: dict[str, Any] = {
    "port": PORT_MIN,  # 514
    "enabled": False,
    "facility": "LOCAL7",
    "log_level": ["CRITICAL", "ERROR", "WARNING", "INFORMATIONAL"],
}

# Values 'deleted' resets a NAMED field to. The global scalar resets to its
# factory default; a NAMED server is removed entirely rather than reset in
# place (a syslog server with no address is meaningless) - see
# _desired_deleted().
DEFAULTS: dict[str, Any] = dict(FULL_DEFAULTS)

# State constants - each state defines a different module behaviour.
# See the DOCUMENTATION string above for what each state does.
STATE_MERGED = "merged"  # Additive - apply enabled, add/update servers
STATE_REPLACED = "replaced"  # enabled applied if supplied; servers list is a set
STATE_OVERRIDDEN = "overridden"  # enabled defaults if omitted; servers list is a set
STATE_DELETED = "deleted"  # Reset to factory defaults (all, or only what is named)
STATE_GATHERED = "gathered"  # Read-only - just return the current configuration

# These states require the user to provide a 'config' parameter. Without
# this guard, 'overridden' with no config would wipe the syslog
# configuration.
REQUIRES_CONFIG = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}

# ── Argument Spec ─────────────────────────────────────────────────────────────
# ARGUMENT_SPEC defines all parameters the user can pass to this module.
# Ansible uses this to validate user input before the module runs.

ARGUMENT_SPEC = {
    "config": {
        "type": "dict",
        "options": {
            # enabled - global syslog admin state. No default here on
            # purpose: None means "not supplied", which each state
            # interprets itself.
            "enabled": {"type": "bool"},
            # servers - the syslog servers to manage.
            "servers": {
                "type": "list",
                "elements": "dict",
                "options": {
                    # host_id - resource identifier (required always,
                    # including for 'deleted', which needs only this).
                    "host_id": {"type": "str", "required": True},
                    # address - required for merged/replaced/overridden,
                    # enforced in _validate_config() rather than here so
                    # that 'deleted' needs only host_id.
                    "address": {"type": "str"},
                    # address_type - discriminator; derived from address
                    # when omitted.
                    "address_type": {"type": "str", "choices": ADDRESS_TYPES},
                    # port, enabled, facility, log_level - all optional on
                    # purpose: None means "not supplied", which each state
                    # interprets itself (see SERVER_FULL_DEFAULTS).
                    "port": {"type": "int"},
                    "enabled": {"type": "bool"},
                    "facility": {"type": "str", "choices": FACILITY_CHOICES},
                    "log_level": {
                        "type": "list",
                        "elements": "str",
                        "choices": SEVERITY_CHOICES,
                    },
                },
            },
        },
    },
    # state - controls what the module does with the config
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
}


# ── Custom Exception ─────────────────────────────────────────────────────────
# Every module defines its own exception class so errors can carry
# structured details (not just a message string) back to the user.


class FeSyslogError(Exception):
    """Raised for syslog module validation or response issues.

    Args:
        message: Human-readable error description.
        details: Optional dict with extra context (shown in Ansible output).
    """

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        # Top-level fail_json keys (code, err) of a transport failure.
        self.extra = extra or {}

    def to_fail_kwargs(self) -> dict[str, Any]:
        """Convert this exception into keyword args for module.fail_json()."""
        data: dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        data.update(self.extra)
        return data


# ── Helper Functions ──────────────────────────────────────────────────────────
# These utility functions handle common tasks: detecting errors in REST
# responses, establishing the device connection, and sending API requests.


def _error_code(payload: dict[str, Any]) -> int | str | None:
    """Return the application-error code from a Fabric Engine error document."""
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    return code


def _is_not_found_response(payload: Any) -> bool:
    """Return True when a REST response means "this resource does not exist"."""
    if not isinstance(payload, dict):
        return False
    if _error_code(payload) == 404:
        return True
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if isinstance(message, str):
        lowered = message.lower()
        return "not found" in lowered or "does not exist" in lowered
    return False


def _extract_error(payload: Any) -> dict[str, Any] | None:
    """Check if the REST response contains an error (HTTP 4xx/5xx or error list)."""
    if not isinstance(payload, dict):
        return None
    code = _error_code(payload)
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if isinstance(code, int) and code >= 400:
        return {
            "code": code,
            "message": message or "Device reported a syslog error",
            "payload": payload,
        }
    errors = payload.get("errors") or payload.get("error")
    if errors:
        return {
            "message": message or "Device reported syslog errors",
            "errors": errors,
            "payload": payload,
        }
    return None


def _has_supplied_value(value: Any) -> bool:
    """Return True when value carries at least one user-supplied setting.

    Ansible fills every omitted suboption with None, so C(config: {}) arrives
    as a dict whose values are all None. Such a dict (recursively) counts as
    not supplied. Any non-None scalar counts as supplied, and so does any list,
    including an empty one, because an explicit C(servers: []) is a real value.
    """
    if value is None:
        return False
    if isinstance(value, dict):
        return any(_has_supplied_value(item) for item in value.values())
    return True


def _get_connection(module: AnsibleModule) -> Connection:
    """Create and return a Connection object for talking to the device."""
    if not module._socket_path:
        raise FeSyslogError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    payload: Any | None = None,
    expect_content: bool = True,
    allow_not_found: bool = False,
) -> Any:
    """Send a single REST API request to the device and return the response.

    Args:
        allow_not_found: when True, a 404 is returned to the caller rather than
            failing the task. The device reports the syslog resource as
            missing when it has never been configured, which is not an
            error for a read - see _fetch_syslog_config().
    """
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        # A 404 raised as a connection error is still "not configured yet" when
        # the caller asked for that to be tolerated, so hand it back rather
        # than failing here.
        if allow_not_found and getattr(exc, "code", None) == 404:
            # Keep the device's own text - if the caller does not tolerate
            # this 404 after all, it becomes the only record of why.
            return {"statusCode": 404, "errorMessage": to_text(exc)}
        # Raised rather than failed here so a failure after an earlier write
        # can say what was applied; run_module() fails with the same msg,
        # code and err.
        raise FeSyslogError(
            to_text(exc),
            extra={"code": getattr(exc, "code", None), "err": getattr(exc, "err", None)},
        )

    if isinstance(response, bytes):
        response = to_text(response)

    # Handle empty responses - PATCH and PUT here answer 204 No Content
    if response in (None, ""):
        return None if not expect_content else {}

    # A "not found" body is handed back untouched when the caller allows it,
    # so the generic error path below cannot pre-empt the caller's own 404
    # handling.
    if isinstance(response, dict):
        if allow_not_found and _is_not_found_response(response):
            return response
        error = _extract_error(response)
        if error:
            raise FeSyslogError(to_text(error.get("message")), details=error)

    return response


# ── Data-Fetching Functions ───────────────────────────────────────────────────


def _fetch_syslog_config(
    module: AnsibleModule,
    connection: Connection,
    *,
    allow_not_found: bool = True,
) -> dict[str, Any]:
    """Fetch the syslog configuration from the device.

    Sends GET /v0/configuration/syslog, which returns a SyslogSettings
    object: {enabled, servers: [SyslogServer, ...]}.

    Args:
        allow_not_found: True (the default) tolerates a 404 as "never
            configured" and returns factory defaults - correct for the
            'before' read, which may legitimately hit a device that has
            never had syslog touched. False fails instead: used for the
            'after' read following a write, where a 404 does not mean
            unconfigured - it means the write could not be confirmed - and
            reporting fabricated factory defaults as the result would hide
            that from the caller. See the merged/replaced/overridden write
            path for the strict re-read.

    Returns:
        The raw SyslogSettings dict (REST field names), or - under
        allow_not_found - a dict with default-shaped empty values when the
        device reports nothing.

    Raises:
        FeSyslogError: under allow_not_found=False, if the device answers
            not-found; or, in either mode, if the response is not a valid
            SyslogSettings shape.
    """
    raw = _call_api(
        module,
        connection,
        method="GET",
        path=SYSLOG_CONFIG_PATH,
        allow_not_found=True,
    )
    if _is_not_found_response(raw):
        if not allow_not_found:
            # The write just above this call succeeded, so the device HAS a
            # syslog configuration now - a 404 here means it isn't reporting
            # it back, not that it is unconfigured. Falling back to
            # allow_not_found's factory-default reading would report a
            # write nothing actually confirmed.
            raise FeSyslogError(
                "The device accepted the syslog write but does not report "
                "its configuration back from {0}, so the result could not "
                "be confirmed".format(SYSLOG_CONFIG_PATH),
                details={"response": raw},
            )
        module.warn(
            "The device reports no syslog configuration at {0}; treating it "
            "as unconfigured and using factory defaults.".format(SYSLOG_CONFIG_PATH)
        )
        # A fresh list, not FULL_DEFAULTS["servers"] itself - this dict is
        # handed back to a caller that may go on to treat it as "current"
        # state, and must not risk mutating the shared module-level default.
        return {"enabled": FULL_DEFAULTS["enabled"], "servers": []}
    if not isinstance(raw, dict):
        # Reading an unexpected shape as "unconfigured" would let the action
        # states PUT factory defaults over a configuration that is really there.
        raise FeSyslogError(
            "Unexpected response when reading the syslog configuration " "from {0}".format(SYSLOG_CONFIG_PATH),
            details={"response": raw},
        )
    if not isinstance(raw.get("servers"), list):
        # Coercing this to an empty list, rather than failing, would read a
        # transient or schema-mismatched 200 as "no servers configured" - and
        # merged/replaced both PUT the full server list, so the next write
        # would silently erase every server actually on the device.
        raise FeSyslogError(
            "The syslog configuration at {0} carries no 'servers' " "list".format(SYSLOG_CONFIG_PATH),
            details={"response": raw},
        )
    if not all(isinstance(srv, dict) for srv in raw["servers"]):
        # Same hazard per entry: skipping an unparseable item would drop it
        # from 'current', and the next full-list PUT would erase it.
        raise FeSyslogError(
            "The syslog configuration at {0} carries a 'servers' entry that "
            "is not a SyslogServer object".format(SYSLOG_CONFIG_PATH),
            details={"response": raw},
        )
    return raw


# ── Address Helpers ───────────────────────────────────────────────────────────
# The REST API nests each server address inside a GeneralIpAddress object
# with an "ipAddressType" discriminator. These helpers derive, normalize
# and compare it. Unlike NTP's GeneralHostOrIp, this schema is IP-only -
# there is no "hostname" discriminator value.


def _determine_address_type(address: str, explicit: str | None) -> str:
    """Return the GeneralIpAddress discriminator for an address.

    An explicitly supplied address_type always wins. Otherwise the address
    is parsed as an IP: IPv4 or IPv6.
    """
    if explicit:
        return explicit
    try:
        return "IPv4" if ip_address(address).version == 4 else "IPv6"
    except ValueError:
        raise FeSyslogError("'{0}' is not a valid IPv4 or IPv6 address".format(address))


def _normalize_address(address: str) -> str:
    """Normalize an IP address to its canonical form so comparisons are stable."""
    try:
        return str(ip_address(address))
    except ValueError:
        return address


def _server_key(server: dict[str, Any]) -> str:
    """Return the identity of a server entry: its host_id.

    Two entries with the same host_id are the same syslog server slot,
    which is what the merge, replace, override and delete logic uses to
    match desired against current.
    """
    return server.get("host_id", "")


def _canonical_host_id(host_id: Any) -> Any:
    """Return host_id in its canonical decimal form ("01" -> "1").

    _validate_host_id() accepts anything int() parses, so without this a
    "01" would pass validation yet never match the device's "1" - merged
    would add a second entry for the same slot and deleted would remove
    nothing. A value int() cannot parse is returned unchanged for
    _validate_host_id() to reject.
    """
    try:
        return str(int(host_id))
    except (TypeError, ValueError):
        return host_id


def _normalize_log_level(levels: list[str]) -> list[str]:
    """Return levels as the device stores them, de-duplicated, in SEVERITY_CHOICES order.

    log_level is a set of severities, but it travels as a list - comparing
    it as-is would treat [ERROR, CRITICAL] and [CRITICAL, ERROR] as
    different and report a change (and PUT) on every run. Levels the device
    does not store are mapped to the one it stores (SEVERITY_STORED_AS), so
    [ERROR, ALERT] compares equal to the [CRITICAL, ERROR] read back.
    """
    order = {level: idx for idx, level in enumerate(SEVERITY_CHOICES)}
    stored = {SEVERITY_STORED_AS.get(level, level) for level in levels}
    return sorted(stored, key=lambda level: (order.get(level, len(order)), level))


def _warn_stored_log_levels(module: AnsibleModule, servers: list[dict[str, Any]]) -> None:
    """Warn once per server whose requested log_level the device stores differently."""
    for srv in servers:
        levels = srv.get("log_level") or []
        mapped = sorted({level for level in levels if level in SEVERITY_STORED_AS}, key=SEVERITY_CHOICES.index)
        if not mapped:
            continue
        module.warn(
            "Syslog server {0}: Fabric Engine stores {1}; log_level is applied and reported as {2}.".format(
                srv.get("host_id"),
                ", ".join("{0} as {1}".format(level, SEVERITY_STORED_AS[level]) for level in mapped),
                ", ".join(_normalize_log_level(levels)),
            )
        )


# ── Validation ────────────────────────────────────────────────────────────────


def _validate_host_id(module: AnsibleModule, host_id: str) -> None:
    """Fail early when host_id is outside the confirmed firmware range.

    The OpenAPI schema only bounds hostId as a 1-10 character string, but
    the VOSS CLI ("syslog host <1-10>") and a live device confirm the
    real range is the decimal integers 1 to 10.
    """
    try:
        value = int(host_id)
    except (TypeError, ValueError):
        value = None
    if value is None or not (HOST_ID_MIN <= value <= HOST_ID_MAX):
        module.fail_json(
            msg="host_id must be an integer between {0} and {1} (as a "
            "string), got '{2}'".format(HOST_ID_MIN, HOST_ID_MAX, host_id)
        )


def _validate_port(module: AnsibleModule, host_id: str, port: int | None) -> None:
    """Fail early when port is outside the confirmed Fabric Engine range."""
    if port is None:
        return
    if port < PORT_MIN or port > PORT_MAX:
        module.fail_json(
            msg="port must be between {0} and {1} for syslog server '{2}', "
            "got {3}".format(PORT_MIN, PORT_MAX, host_id, port)
        )


def _validate_servers(module: AnsibleModule, state: str, servers: list[dict[str, Any]]) -> None:
    """Validate each server entry before anything is sent to the device."""
    seen: set[str] = set()
    for srv in servers:
        _validate_host_id(module, srv.get("host_id"))
        # Canonical form, so "1" and "01" are caught as the same slot
        host_id = _canonical_host_id(srv.get("host_id"))
        if host_id in seen:
            module.fail_json(
                msg="Syslog server '{0}' is listed more than once in 'config.servers'; list each server once".format(
                    host_id
                )
            )
        seen.add(host_id)

        if state in REQUIRES_CONFIG and not srv.get("address"):
            module.fail_json(msg="'address' is required for state {0} (host_id '{1}')".format(state, host_id))

        address = srv.get("address")
        explicit_type = srv.get("address_type")
        if address:
            if explicit_type:
                try:
                    parsed = ip_address(address)
                except ValueError:
                    module.fail_json(
                        msg="Address '{0}' is not a valid IP but "
                        "address_type is set to '{1}' (host_id "
                        "'{2}')".format(address, explicit_type, host_id)
                    )
                    return
                detected = "IPv4" if parsed.version == 4 else "IPv6"
                if detected != explicit_type:
                    module.fail_json(
                        msg="Address '{0}' is {1} but address_type is set "
                        "to '{2}' (host_id '{3}')".format(address, detected, explicit_type, host_id)
                    )
            else:
                try:
                    ip_address(address)
                except ValueError:
                    module.fail_json(
                        msg="'{0}' is not a valid IPv4 or IPv6 address " "(host_id '{1}')".format(address, host_id)
                    )

        _validate_port(module, host_id, srv.get("port"))


# ── Output Formatter ──────────────────────────────────────────────────────────


def _to_ansible_server(rest_server: dict[str, Any]) -> dict[str, Any]:
    """Convert one REST SyslogServer object into the Ansible output format."""
    ip = rest_server.get("ipAddress") or {}
    address = str(ip.get("address") or "")
    address_type = ip.get("ipAddressType") or _determine_address_type(address, None)
    return {
        "host_id": _canonical_host_id(rest_server.get("hostId")),
        "address": _normalize_address(address),
        "address_type": address_type,
        "port": rest_server.get("port", SERVER_FULL_DEFAULTS["port"]),
        "enabled": bool(rest_server.get("enabled", SERVER_FULL_DEFAULTS["enabled"])),
        "facility": rest_server.get("facility", SERVER_FULL_DEFAULTS["facility"]),
        "log_level": (
            _normalize_log_level(rest_server["logLevel"])
            if isinstance(rest_server.get("logLevel"), list)
            else list(SERVER_FULL_DEFAULTS["log_level"])
        ),
    }


def _to_ansible_output(rest_settings: dict[str, Any]) -> dict[str, Any]:
    """Convert one REST SyslogSettings object into the Ansible output format."""
    # Every entry is a dict - _fetch_syslog_config() rejects anything else.
    servers = [_to_ansible_server(srv) for srv in rest_settings["servers"]]
    return {
        "enabled": bool(rest_settings.get(FIELD_MAP["enabled"], FULL_DEFAULTS["enabled"])),
        "servers": servers,
    }


# ── Payload Builders ───────────────────────────────────────────────────────────


def _build_patch_payload(current: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    """Build the PATCH body for the global 'enabled' field, if it changed."""
    if current.get("enabled") == desired.get("enabled"):
        return {}
    return {FIELD_MAP["enabled"]: desired["enabled"]}


def _build_server_rest(server: dict[str, Any]) -> dict[str, Any]:
    """Build one REST SyslogServer object from an Ansible-format server block.

    Every writable field is always included - PUT replaces the whole
    servers list, so a field left out of an entry would be reset by the
    device rather than kept.
    """
    return {
        "hostId": server["host_id"],
        "ipAddress": {
            "ipAddressType": server["address_type"],
            "address": server["address"],
        },
        "port": server["port"],
        "enabled": server["enabled"],
        "facility": server["facility"],
        "logLevel": list(server["log_level"]),
    }


def _build_put_payload(servers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the PUT body (SyslogServerUpdate) for the complete servers list."""
    return {"servers": [_build_server_rest(srv) for srv in servers]}


# ── Diff / Comparison Logic ──────────────────────────────────────────────────


def _sorted_servers(servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a servers list sorted by host_id so order causes no false diff."""
    return sorted(servers, key=_server_key)


def _servers_equal(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> bool:
    """Return True when two servers lists hold the same writable configuration."""
    return _sorted_servers(before) == _sorted_servers(after)


def _compute_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compute the differences between the before and after syslog states."""
    diff: dict[str, Any] = {}
    if before.get("enabled") != after.get("enabled"):
        diff["enabled"] = {"before": before.get("enabled"), "after": after.get("enabled")}
    before_servers = _sorted_servers(before.get("servers") or [])
    after_servers = _sorted_servers(after.get("servers") or [])
    if before_servers != after_servers:
        diff["servers"] = {"before": before_servers, "after": after_servers}
    return diff


# ── Server-Entry Normalization ────────────────────────────────────────────────


def _normalize_config_servers(servers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Turn the user's server entries into the module's internal format.

    Derives address_type when it was omitted and normalizes the address.
    Every other field is kept as None when not supplied, so each state's
    builder can decide what "not supplied" means (inherit from current,
    or fall back to SERVER_FULL_DEFAULTS). Duplicate host_ids are
    collapsed, last one wins (_validate_servers() already rejects
    duplicates, so this only ever matters if validation is bypassed).
    """
    normalized: dict[str, dict[str, Any]] = {}
    for srv in servers or []:
        host_id = _canonical_host_id(srv["host_id"])
        address = srv.get("address")
        log_level = srv.get("log_level")
        entry: dict[str, Any] = {
            "host_id": host_id,
            "port": srv.get("port"),
            "enabled": srv.get("enabled"),
            "facility": srv.get("facility"),
            "log_level": None if log_level is None else _normalize_log_level(log_level),
        }
        if address:
            address_type = _determine_address_type(address, srv.get("address_type"))
            entry["address"] = _normalize_address(address)
            entry["address_type"] = address_type
        else:
            entry["address"] = None
            entry["address_type"] = None
        normalized[host_id] = entry
    return list(normalized.values())


def _fill_server_defaults(entry: dict[str, Any]) -> dict[str, Any]:
    """Return entry with every None field replaced by SERVER_FULL_DEFAULTS.

    Used to complete a brand-new server entry (merged) or any entry under
    replaced/overridden, both of which are authoritative per-entry.
    """
    filled = dict(entry)
    for field, default in SERVER_FULL_DEFAULTS.items():
        if filled.get(field) is None:
            filled[field] = default
    return filled


def _merge_server(existing: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Fold a supplied entry onto an existing server, keeping omitted fields."""
    merged = dict(existing)
    merged["address"] = entry["address"]
    merged["address_type"] = entry["address_type"]
    for field in ("port", "enabled", "facility", "log_level"):
        if entry.get(field) is not None:
            merged[field] = entry[field]
    return merged


# ── Desired-State Builders ────────────────────────────────────────────────────


def _desired_servers_merged(
    current_servers: list[dict[str, Any]], entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """MERGED - add or update the supplied servers, keep everything else."""
    by_id = {_server_key(srv): dict(srv) for srv in current_servers}
    for entry in entries:
        host_id = entry["host_id"]
        if host_id in by_id:
            by_id[host_id] = _merge_server(by_id[host_id], entry)
        else:
            by_id[host_id] = _fill_server_defaults(entry)
    return list(by_id.values())


def _desired_servers_authoritative(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OVERRIDDEN - the supplied list is the complete list. Every entry is
    authoritative per-entry: omitted fields fall back to
    SERVER_FULL_DEFAULTS regardless of what the device currently holds for
    that host_id - overridden never inherits from current state, unlike
    replaced (see _desired_servers_replaced()).
    """
    return [_fill_server_defaults(entry) for entry in entries]


def _desired_servers_replaced(
    current_servers: list[dict[str, Any]], entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """REPLACED (servers supplied) - the supplied list is the complete list
    (any current server not named here is removed), but a NAMED server that
    already exists keeps its own omitted fields rather than resetting them -
    only a genuinely new entry (no current server with that host_id)
    defaults omitted fields to SERVER_FULL_DEFAULTS. Per
    docs/extreme_fe_syslog.md's Parameters table: port/enabled/facility/
    log_level are "left alone when omitted for an existing server,
    defaulted ... for a new one". This is what tells replaced apart from
    overridden, which always resets omitted fields regardless of whether
    the server already exists.
    """
    by_id = {_server_key(srv): srv for srv in current_servers}
    servers: list[dict[str, Any]] = []
    for entry in entries:
        current = by_id.get(entry["host_id"])
        if current is not None:
            servers.append(_merge_server(current, entry))
        else:
            servers.append(_fill_server_defaults(entry))
    return servers


def _desired_servers_deleted(
    current_servers: list[dict[str, Any]], entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """DELETED with config - remove only the named servers."""
    remove_ids = {_server_key(entry) for entry in entries}
    return [srv for srv in current_servers if _server_key(srv) not in remove_ids]


def _build_desired(
    state: str, current: dict[str, Any], config: dict[str, Any], *, config_supplied: bool
) -> dict[str, Any]:
    """Dispatch to the desired-state builder for the requested state.

    Returns a complete {enabled, servers} block, in Ansible output format.

    Args:
        config_supplied: Whether the task's 'config' sets any option. Only
            STATE_DELETED cares: a config with no option set (omitted, or
            {} which arrives with every suboption None) resets the whole
            syslog configuration; a config naming something resets only
            that.
    """
    entries = _normalize_config_servers(config.get("servers"))
    servers_supplied = config.get("servers") is not None

    if state == STATE_MERGED:
        enabled = current["enabled"] if config.get("enabled") is None else config["enabled"]
        servers = _desired_servers_merged(current["servers"], entries)
        return {"enabled": enabled, "servers": servers}

    if state == STATE_REPLACED:
        enabled = current["enabled"] if config.get("enabled") is None else config["enabled"]
        servers = _desired_servers_replaced(current["servers"], entries) if servers_supplied else current["servers"]
        return {"enabled": enabled, "servers": servers}

    if state == STATE_OVERRIDDEN:
        enabled = FULL_DEFAULTS["enabled"] if config.get("enabled") is None else config["enabled"]
        servers = _desired_servers_authoritative(entries) if servers_supplied else []
        return {"enabled": enabled, "servers": servers}

    # STATE_DELETED
    if not config_supplied:
        return dict(DEFAULTS)
    enabled = current["enabled"]
    if config.get("enabled") is not None:
        enabled = DEFAULTS["enabled"]
    servers = current["servers"]
    if servers_supplied:
        servers = _desired_servers_deleted(current["servers"], entries)
    return {"enabled": enabled, "servers": servers}


# ── State Handlers ────────────────────────────────────────────────────────────


def _handle_gathered(current: dict[str, Any], result: dict[str, Any]) -> None:
    """GATHERED - read-only, return the current syslog configuration."""
    result["syslog"] = {"config": current}
    result["gathered"] = current


def _no_answer(exc: FeSyslogError, method: str, path: str, result: dict[str, Any]) -> FeSyslogError:
    """Return *exc*, or for a write without an answer, the same error marked as possibly applied.

    A transport failure without an HTTP status (a lost connection) leaves the
    write's outcome unknown: the device may have applied it, so result changed
    is set and details.outcome is "unknown". An HTTP error carries a numeric
    code and an error document no code in extra; both are returned unchanged.
    """
    if not ("code" in (exc.extra or {}) and is_answer_unknown_code(exc.extra["code"])):
        return exc
    result["changed"] = True
    return FeSyslogError(
        "%s. The %s %s may have been applied before the answer was lost; check the syslog configuration on "
        "the device." % (to_text(exc).rstrip("."), method, path),
        details=dict(exc.details, outcome="unknown"),
        extra=exc.extra,
    )


def _apply_desired(
    module: AnsibleModule,
    connection: Connection,
    current: dict[str, Any],
    desired: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Send the desired {enabled, servers} block to the device.

    'enabled' and 'servers' are two independent REST calls (PATCH and PUT
    respectively); each is sent only when that part differs from the
    current configuration.
    """
    result["syslog"] = {"before": current}
    submitted: dict[str, Any] = {}

    patch_payload = _build_patch_payload(current, desired)
    put_payload = (
        _build_put_payload(desired["servers"]) if not _servers_equal(current["servers"], desired["servers"]) else None
    )

    if not patch_payload and put_payload is None:
        # Nothing to do - the device already holds the desired configuration
        result["syslog"]["after"] = current
        result["syslog"]["differences"] = {}
        return

    if module.check_mode:
        result["changed"] = True
        result["syslog"]["after"] = desired
        if patch_payload:
            submitted["patch"] = {"path": SYSLOG_CONFIG_PATH, "payload": patch_payload}
        if put_payload is not None:
            submitted["put"] = {"path": SYSLOG_SERVERS_PATH, "payload": put_payload}
        result["submitted"] = submitted
        result["syslog"]["differences"] = _compute_diff(current, desired)
        return

    # 'changed' is set only once a request succeeded, so a failure of the
    # first request reports changed=false and a later one changed=true - except
    # a request that got no answer, which may have been applied (_no_answer()).
    if patch_payload:
        try:
            _call_api(
                module,
                connection,
                method="PATCH",
                path=SYSLOG_CONFIG_PATH,
                payload=patch_payload,
                expect_content=False,  # the endpoint answers 204 No Content
            )
        except FeSyslogError as exc:
            raise _no_answer(exc, "PATCH", SYSLOG_CONFIG_PATH, result)
        result["changed"] = True
        submitted["patch"] = {"path": SYSLOG_CONFIG_PATH, "payload": patch_payload}

    if put_payload is not None:
        try:
            _call_api(
                module,
                connection,
                method="PUT",
                path=SYSLOG_SERVERS_PATH,
                payload=put_payload,
                expect_content=False,  # the endpoint answers 204 No Content
            )
        except FeSyslogError as exc:
            exc = _no_answer(exc, "PUT", SYSLOG_SERVERS_PATH, result)
            if not patch_payload:
                raise exc
            raise FeSyslogError(
                "The syslog admin state was already applied (PATCH %s enabled=%s), but the PUT of the servers "
                "list to %s failed: %s"
                % (SYSLOG_CONFIG_PATH, patch_payload.get("enabled"), SYSLOG_SERVERS_PATH, to_text(exc)),
                details=dict(exc.details, applied=["enabled"], failed_request="PUT %s" % SYSLOG_SERVERS_PATH),
                extra=exc.extra,
            )
        result["changed"] = True
        submitted["put"] = {"path": SYSLOG_SERVERS_PATH, "payload": put_payload}

    result["submitted"] = submitted

    # Re-read so the reported "after" is what the device really holds
    try:
        after_raw = _fetch_syslog_config(
            module,
            connection,
            allow_not_found=False,
        )
    except FeSyslogError as exc:
        raise FeSyslogError(
            "The syslog configuration was applied (%s), but re-reading it afterwards failed: %s"
            % (", ".join(sorted(submitted)), to_text(exc)),
            details=dict(exc.details, applied=sorted(submitted)),
            extra=exc.extra,
        )
    result["syslog"]["after"] = _to_ansible_output(after_raw)
    result["syslog"]["differences"] = _compute_diff(current, result["syslog"]["after"])


# ── Main Entry Point ─────────────────────────────────────────────────────────


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    try:
        connection = _get_connection(module)
    except FeSyslogError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    result: dict[str, Any] = {
        "changed": False,
    }

    try:
        state = module.params["state"]
        # For STATE_DELETED, a config with no option set - omitted, or
        # config: {} (which arrives with every suboption None) - means "reset
        # everything", as for every other module of the collection; a config
        # naming something (including servers: []) resets only what it names.
        # See _build_desired()'s STATE_DELETED branch.
        config_supplied = _has_supplied_value(module.params.get("config"))
        config = module.params.get("config") or {}

        # merged/replaced/overridden need something to work with. Without
        # this guard, 'overridden' with no config would wipe the syslog
        # configuration.
        # Ansible fills omitted suboptions with None, so config: {} arrives as
        # a non-empty dict - only a non-null value counts as supplied.
        if state in REQUIRES_CONFIG and not _has_supplied_value(config):
            raise FeSyslogError("value of config parameter must not be empty for state {0}".format(state))

        _validate_servers(module, state, config.get("servers") or [])
        if state in REQUIRES_CONFIG:
            _warn_stored_log_levels(module, config.get("servers") or [])

        # ── GET the current syslog configuration ──────────────────────
        current_raw = _fetch_syslog_config(module, connection)
        current = _to_ansible_output(current_raw)

        # ── Read-only path returns early ─────────────────────────────
        if state == STATE_GATHERED:
            _handle_gathered(current, result)
            module.exit_json(**result)
            return

        # ── Build and apply the desired configuration ────────────────
        result["before"] = current
        desired = _build_desired(state, current, config, config_supplied=config_supplied)
        _apply_desired(module, connection, current, desired, result)
        # Top-level "after" is returned for every action state: the re-read
        # state after a change, the prediction in check mode, and the
        # unchanged "before" when nothing had to be written.
        result["after"] = result["syslog"]["after"]

        # ── Diff mode (--diff) ───────────────────────────────────────
        if module._diff:
            result["diff"] = {
                "before": result["before"],
                "after": result["after"],
            }

        module.exit_json(**result)

    except FeSyslogError as exc:
        module.fail_json(changed=result.get("changed", False), **exc.to_fail_kwargs())
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            changed=result.get("changed", False),
        )


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
