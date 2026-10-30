# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage global NTP settings on Extreme Fabric Engine switches.

Module Architecture Overview
============================
This module manages the Network Time Protocol (NTP) configuration on Extreme
Fabric Engine switches via the REST OpenAPI.

REST Endpoints used:
  GET  /v0/configuration/ntp
       -> Retrieve the NTP settings for every virtual router (NtpSettings,
          which wraps a "vrBasedSettings" list of NtpSettingsByVr objects)
  PUT  /v0/configuration/ntp/{vr_name}
       -> Replace the complete NTP configuration of one virtual router
          (body is an NtpSettingsByVr object, response is 204 No Content)

Fields used (OpenAPI schema NtpSettingsByVr / NtpServer):
  vrName                 - read-only, returned by GET only
  enabled                - global NTP on/off              (default false)
  pollInterval           - 2^value seconds, range 4-17    (default 8)
  servers[].ipAddress    - GeneralHostOrIp (hostType + address)
  servers[].enabled      - per-server on/off              (default true)

Fabric Engine constraints:
  - There is no PATCH and there are no per-server POST/DELETE endpoints, so
    every change is a read-modify-write: GET the current settings, fold the
    user's config into them according to the requested state, then PUT the
    complete NtpSettingsByVr object back.
  - The OpenAPI spec notes that vrName is ignored on Fabric Engine and that
    the properties below it are treated as global. The path parameter is
    still required by the API, so vr_name is a required module parameter.
  - The PUT path is case-sensitive, so vr_name goes through the collection's
    shared normalize_vrf_name() helper before the URL is built - the same
    one extreme_fe_vrf uses. User virtual router names are lowercased and
    the system routers get their canonical casing ("globalrouter" becomes
    "GlobalRouter", "mgmtrouter" becomes "MgmtRouter").
  - broadcastClientEnabled, servers[].version, servers[].minPoll and
    servers[].maxPoll are Switch Engine (EXOS) only and are not exposed.

Supported states:
  - merged     : Additive - supplied fields are applied, servers are added,
                 nothing already on the device is removed
  - replaced   : The supplied servers list IS the final list for the VR;
                 scalar fields that are not supplied are left alone
  - overridden : Full authority - anything not supplied is reset to its
                 factory default before the PUT is sent
  - deleted    : Reset to factory defaults; with a config only the items
                 named in it are removed or reset
  - gathered   : Read-only, returns the current NTP configuration

Code Flow (run_module):
  1. Connect to the switch via httpapi
  2. Fetch the current NTP config (GET /v0/configuration/ntp)
  3. Select the virtual router block the user asked for
  4. Build the desired block for the requested state
  5. PUT it only when it differs from the current block (idempotency)
  6. Re-read the config and return before/after/differences
"""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_ntp_global
short_description: Manage global NTP settings on ExtremeNetworks Fabric Engine switches
version_added: "1.3.0"
description:
  - Manage the Network Time Protocol (NTP) configuration on ExtremeNetworks Fabric Engine
    switches using the custom C(extreme_fe) HTTPAPI plugin.
  - Uses C(/v0/configuration/ntp) and C(/v0/configuration/ntp/{vr_name}) from the NOS
    OpenAPI schema.
  - Manages the global NTP admin state, the poll interval and the list of NTP servers.
  - The REST API exposes only GET and PUT for NTP, so every state is applied as a
    read-modify-write - the module reads the current settings, folds the supplied
    config into them and replaces the virtual router configuration with a single PUT.
  - The PUT is skipped when the desired configuration already matches the device,
    so every state is idempotent.
author:
  - Andreea-Lavinia Vraja (@avraja_extr)
requirements:
  - ansible.netcommon
notes:
  - When the device reports no NTP configuration at all, the module warns and treats
    the device as unconfigured, returning factory defaults rather than failing.
  - Tested against Fabric Engine Version 9.3.2.
  - Each server may be listed once in C(config.servers). An address is compared in its canonical form
    (an IPv6 address in any notation, a host name in any case), so the same server written twice fails
    before any request.
  - A PUT that fails without an answer (a lost connection) may have been applied, so the task reports
    C(changed=true) with C(details.outcome=unknown).
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin
    shipped with this project.
  - The OpenAPI schema marks C(vrName) as read-only and states that it is ignored on
    Fabric Engine, where the NTP properties are global. The PUT endpoint still requires
    the virtual router in the URL, so C(vr_name) is a required parameter and is never
    sent in the request body.
  - C(vr_name) is normalized the same way C(extreme_fe_vrf) normalizes VRF names,
    because the REST path is case-sensitive. User virtual router names are lowercased
    and the system routers are mapped to their canonical casing, so C(globalrouter)
    and C(GlobalRouter) both reach C(/v0/configuration/ntp/GlobalRouter). Supplying a
    mixed-case name that has to be converted raises a warning.
  - The broadcast client setting and the per-server NTP version, minimum poll and
    maximum poll attributes are Switch Engine (EXOS) only and are not supported by
    this module.
  - C(poll_interval) is an exponent - the interval between NTP updates in seconds is
    2 raised to the power of this value.
  - Server addresses are canonicalized before they are compared, so the same server
    is recognised however it is spelled. IP addresses are put in their canonical form
    and host names are lowercased, DNS being case-insensitive; both are reported and
    sent to the device in that form.
  - Supports check mode and diff mode. Under C(--diff) the module reports the whole
    NTP configuration before and after the change; combined with C(--check) the
    reported "after" is the state that would have been written.
  - C(gathered), C(before) and C(after) contain only the C(config) option fields
    (C(enabled), C(poll_interval), C(servers)), so C(gathered) can be passed back as
    C(config). The virtual router is reported in the separate top-level C(vr_name)
    result.
  - A rejected PUT fails the task with C(changed=false). When the PUT succeeds but
    the re-read that follows it fails, the task fails with C(changed=true) and a
    message saying the configuration was applied.
options:
  vr_name:
    description:
      - Name of the virtual router whose NTP configuration is managed.
      - Required by the C(/v0/configuration/ntp/{vr_name}) endpoint, so it must always
        be supplied. On Fabric Engine this is normally C(GlobalRouter).
      - Accepts 1 to 16 characters. The OpenAPI spec allows 32, but the device
        firmware rejects virtual router names longer than 16 characters.
      - Normalized before the REST path is built - user virtual router names are
        lowercased and the system routers are mapped to their canonical casing, so
        C(globalrouter) and C(GlobalRouter) are equivalent.
    type: str
    required: true
  config:
    description:
      - Structured NTP settings to manage for the virtual router.
      - Required when C(state) is C(merged), C(replaced) or C(overridden).
      - A C(config) with no option set (for example C({})) counts as omitted for these
        states and fails before any request is sent.
      - Optional when C(state=deleted); if omitted, or given with no option set, the whole NTP
        configuration is reset to its factory defaults.
    type: dict
    suboptions:
      enabled:
        description:
          - Global NTP admin state for the virtual router.
          - Factory default is C(false).
          - When omitted, C(merged) and C(replaced) leave the current value alone and
            C(overridden) resets it to C(false).
        type: bool
      poll_interval:
        description:
          - Exponent used to derive the interval between NTP updates. The interval in
            seconds is 2 raised to the power of this value.
          - Accepts 4 to 17. Factory default is C(8).
          - When omitted, C(merged) and C(replaced) leave the current value alone and
            C(overridden) resets it to C(8).
        type: int
      servers:
        description:
          - List of NTP servers for the virtual router.
          - C(merged) adds the listed servers and keeps the ones already configured.
          - C(replaced) and C(overridden) make this list the complete server list;
            servers that are not listed are removed.
          - C(deleted) removes only the listed servers. An empty list removes nothing.
        type: list
        elements: dict
        suboptions:
          address:
            description:
              - Host name, IPv4 address or IPv6 address of the NTP server.
            type: str
            required: true
          host_type:
            description:
              - Type of identifier supplied in C(address).
              - When omitted it is derived from C(address) - an address that parses as
                an IP becomes C(IPv4) or C(IPv6), anything else becomes C(hostname).
              - Supplying a value that contradicts C(address) fails the task. That
                includes tagging an IP address as C(hostname), which would otherwise be
                sent to the device under the wrong discriminator.
            type: str
            choices: [hostname, IPv4, IPv6]
          enabled:
            description:
              - Admin state of this NTP server.
              - When omitted, an existing server keeps its current state and a newly
                added server is enabled, which is the factory default.
            type: bool
  state:
    description:
      - Desired module operation.
      - C(merged) applies the supplied fields and adds the supplied servers, leaving
        everything else on the device untouched.
      - C(replaced) makes the supplied servers list the final list for the virtual
        router. Scalar fields that are not supplied keep their current value.
      - C(overridden) enforces the supplied configuration exactly. Every field and
        every server that is not supplied is reset to its factory default.
      - C(deleted) resets the NTP configuration to its factory defaults. When C(config)
        is supplied, only the servers listed in it are removed and only the scalar
        fields named in it are reset.
      - C(gathered) returns the current NTP configuration without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
"""

EXAMPLES = r"""
# - name: Configure NTP
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Enable NTP and add two servers
  extreme.fe.extreme_fe_ntp_global:
    state: merged
    vr_name: GlobalRouter
    config:
      enabled: true
      poll_interval: 10
      servers:
        - address: 10.10.10.1
          host_type: IPv4
        - address: time.example.com
          host_type: hostname

- name: Make the listed servers the complete server list
  extreme.fe.extreme_fe_ntp_global:
    state: replaced
    vr_name: GlobalRouter
    config:
      servers:
        - address: 10.10.10.1
        - address: "2001:db8::1"

- name: Enforce the exact NTP configuration and reset everything else
  extreme.fe.extreme_fe_ntp_global:
    state: overridden
    vr_name: GlobalRouter
    config:
      enabled: true
      servers:
        - address: 10.10.10.1

- name: Remove one NTP server
  extreme.fe.extreme_fe_ntp_global:
    state: deleted
    vr_name: GlobalRouter
    config:
      servers:
        - address: 10.10.10.1

- name: Reset the whole NTP configuration to factory defaults
  extreme.fe.extreme_fe_ntp_global:
    state: deleted
    vr_name: GlobalRouter

- name: Collect the current NTP configuration
  extreme.fe.extreme_fe_ntp_global:
    state: gathered
    vr_name: GlobalRouter
  register: ntp_info
"""

RETURN = r"""
---
changed:
  description: Indicates whether any configuration changes were made.
  returned: always
  type: bool
before:
  description:
    - NTP configuration of the virtual router before any changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
after:
  description:
    - NTP configuration of the virtual router after changes.
    - Returned for every action state, also when nothing changed (then equal to C(before)).
    - In check mode this is the predicted state that would have been written.
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
gathered:
  description:
    - Current NTP configuration gathered from the device.
    - Uses the C(config) option shape (C(enabled), C(poll_interval), C(servers)), so it can be passed back as C(config).
    - The virtual router is reported separately in C(vr_name).
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: dict
vr_name:
  description:
    - Virtual router the reported NTP configuration belongs to, as the device names it.
    - Pass it back as the C(vr_name) option together with C(gathered) as C(config).
  returned: always
  type: str
  sample: GlobalRouter
ntp_global:
  description: NTP configuration state with differences (per-resource detail).
  returned: always
  type: dict
  contains:
    before:
      description: NTP configuration before the requested change.
      returned: when state != gathered
      type: dict
    after:
      description: NTP configuration after the requested change.
      returned: when state != gathered
      type: dict
    config:
      description: Current NTP configuration in gathered mode.
      returned: when state == gathered
      type: dict
    differences:
      description: Changed attributes with before and after values.
      returned: when state != gathered
      type: dict
submitted:
  description: Payload submitted to the device (the PUT body) when a change was required.
  returned: when a change was required
  type: dict
"""

# ip_address - standard library helper used to validate addresses and to
# normalize IPv6 into its compressed canonical form so comparisons are stable
from ipaddress import ip_address

# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any

# quote() safely encodes the {vr_name} segment of the PUT URL
from urllib.parse import quote

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

# Shared virtual router name normalization logic, the same helper
# extreme_fe_vrf uses, so every module in the collection resolves a virtual
# router name to the identifier the REST API expects in exactly one way
from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_vrf_utils import (
    normalize_vrf_name,
)

# ── Module Documentation ──────────────────────────────────────────────────────

# ── Constants ─────────────────────────────────────────────────────────────────
# These constants define the REST API endpoints the module communicates with.
# The NOS OpenAPI spec exposes NTP management under /v0/configuration/ntp.

# GET returns an NtpSettings object: {"vrBasedSettings": [NtpSettingsByVr, ...]}
NTP_CONFIG_PATH = "/v0/configuration/ntp"

# PUT replaces the complete NTP configuration of one virtual router.
# Example: /v0/configuration/ntp/GlobalRouter
NTP_VR_CONFIG_TEMPLATE = "/v0/configuration/ntp/{vr_name}"

# Maximum length of a virtual router name accepted by the device.
# The OpenAPI spec declares maxLength 32, but the firmware rejects anything
# longer than 16 characters - the same limit extreme_fe_vrf enforces.
MAX_VR_NAME_LENGTH = 16

# Poll interval bounds taken from the OpenAPI schema NtpSettingsByVr.pollInterval
# (minimum 4, maximum 17). The value is an exponent: the interval in seconds is
# 2 raised to this power.
MIN_POLL_INTERVAL = 4
MAX_POLL_INTERVAL = 17

# Ansible parameter name -> REST API field name mapping.
# Only writable Fabric Engine fields appear here.
# Excluded: broadcastClientEnabled (x-nos: switch-engine),
#           servers[].version / minPoll / maxPoll (x-nos: switch-engine),
#           vrName (readOnly: true - returned by GET, never sent in the PUT body).
FIELD_MAP = {
    "enabled": "enabled",  # Global NTP admin state for the VR
    "poll_interval": "pollInterval",  # Update interval exponent (2^value seconds)
    "servers": "servers",  # List of NtpServer objects
}

# Ansible parameter name -> REST API field name mapping for one server entry.
SERVER_FIELD_MAP = {
    "address": "ipAddress.address",  # Host name or IP, nested in a GeneralHostOrIp
    "host_type": "ipAddress.hostType",  # Discriminator: hostname, IPv4 or IPv6
    "enabled": "enabled",  # Per-server admin state
}

# Factory defaults for the writable virtual router fields.
# Both values come from the OpenAPI schema NtpSettingsByVr:
#   enabled      -> "default: false"
#   pollInterval -> "default: 8"
# An empty server list is the factory state - no NTP servers are preconfigured.
FULL_DEFAULTS: dict[str, Any] = {
    "enabled": False,  # NTP is off at factory reset (OpenAPI default)
    "poll_interval": 8,  # 2^8 = 256 seconds between updates (OpenAPI default)
    "servers": [],  # No NTP servers configured at factory reset
}

# Values the 'deleted' state resets a field to. NTP is a singleton resource, so
# resetting it to factory defaults is the same as FULL_DEFAULTS.
DEFAULTS: dict[str, Any] = dict(FULL_DEFAULTS)

# Factory default admin state of a newly added NTP server.
# From the OpenAPI schema NtpServer.enabled -> "default: true".
SERVER_DEFAULT_ENABLED = True

# State constants - each state defines a different module behaviour.
# See the DOCUMENTATION string above for what each state does.
STATE_MERGED = "merged"  # Additive - apply supplied fields, add supplied servers
STATE_REPLACED = "replaced"  # Supplied server list becomes the final list
STATE_OVERRIDDEN = "overridden"  # Full authority - omitted fields reset to defaults
STATE_DELETED = "deleted"  # Reset to factory defaults (all, or only what is named)
STATE_GATHERED = "gathered"  # Read-only - just return the current config

# These states require the user to provide a 'config' parameter. Without this
# guard, 'overridden' with no config would silently wipe the NTP configuration.
REQUIRES_CONFIG = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}

# Valid values for the GeneralHostOrIp discriminator (OpenAPI enum).
HOST_TYPES = ["hostname", "IPv4", "IPv6"]

# ── Argument Spec ─────────────────────────────────────────────────────────────
# ARGUMENT_SPEC defines all parameters the user can pass to this module.
# Ansible uses this to validate user input before the module runs.

ARGUMENT_SPEC = {
    # vr_name - required because it is a required path parameter of the PUT
    # endpoint. It is deliberately not defaulted: defaulting a resource
    # identifier hides the API contract and risks writing to the wrong VR.
    "vr_name": {"type": "str", "required": True},
    # config - the NTP settings the user wants to manage.
    # It is a dict (not a list) because NTP is a singleton resource on the device.
    "config": {
        "type": "dict",
        "options": {
            # enabled - global NTP admin state. No default here on purpose:
            # None means "not supplied", which each state interprets itself.
            "enabled": {"type": "bool"},
            # poll_interval - update interval exponent, validated against 4-17
            # before the request is built.
            "poll_interval": {"type": "int"},
            # servers - the NTP servers for this virtual router
            "servers": {
                "type": "list",
                "elements": "dict",
                "options": {
                    # address - host name or IP of the NTP server (required)
                    "address": {"type": "str", "required": True},
                    # host_type - discriminator; derived from address when omitted
                    "host_type": {"type": "str", "choices": HOST_TYPES},
                    # enabled - per-server admin state. No default here on purpose:
                    # None means "keep the current value, or enable a new server".
                    "enabled": {"type": "bool"},
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


class FeNtpGlobalError(Exception):
    """Raised for NTP module validation or response issues.

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


def _is_not_found_response(payload: Any) -> bool:
    """Return True when a REST response means "this resource does not exist".

    The device signals a missing resource either with a 404 status code inside
    the JSON body or with a "not found" / "does not exist" message.
    """
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
        return "not found" in lowered or "does not exist" in lowered
    return False


def _extract_error(payload: Any) -> dict[str, Any] | None:
    """Check if the REST response contains an error (HTTP 4xx/5xx or error list).

    This is called after every API request to detect failures that the
    device reports inside the JSON body (rather than via HTTP status code).

    Args:
        payload: The parsed JSON response from the device.

    Returns:
        A dict with error details if an error was found, or None if the
        response is successful.
    """
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    errors = payload.get("errors")
    # Check for HTTP error codes (400+)
    if isinstance(code, int) and code >= 400:
        return {
            "code": code,
            "message": message or "Device reported an NTP error",
            "payload": payload,
        }
    # Check for an explicit errors list in the response
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported NTP errors",
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
    """Create and return a Connection object for talking to the device.

    The connection uses the httpapi plugin (extreme_fe) which handles
    authentication and REST API communication.

    Args:
        module: The AnsibleModule instance.

    Returns:
        A Connection object ready to send REST requests.

    Raises:
        FeNtpGlobalError: If no socket path is available (wrong connection type).
    """
    if not module._socket_path:
        raise FeNtpGlobalError("Connection type httpapi is required for this module")
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

    This is the central function all REST calls go through. It:
    1. Sends the HTTP request (GET or PUT)
    2. Checks for errors in the response
    3. Returns the parsed response data

    Args:
        module:          The AnsibleModule instance.
        connection:      The device Connection object.
        method:          HTTP method ("GET" or "PUT").
        path:            REST API path (e.g. "/v0/configuration/ntp").
        payload:         Request body data (for PUT), or None for GET.
        expect_content:  If True, treat empty responses as empty dicts;
                         if False, treat empty responses as None (for 204 No Content).
        allow_not_found: when True, a 404 is returned to the caller rather than
                         failing the task. The device reports a resource that
                         has never been configured as missing, which is not an
                         error for a read.

    Returns:
        The parsed response (dict, list, string, or None).
    """
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        # A 404 raised as a connection error is still "not configured yet" when
        # the caller asked for that to be tolerated, so hand it back rather
        # than failing here.
        if allow_not_found and getattr(exc, "code", None) == 404:
            return {"statusCode": 404}
        # Connection-level failure (device unreachable, auth error, etc.).
        # Raised rather than failed here so a failure after the PUT reports
        # changed=true; run_module() fails with the same msg, code and err.
        raise FeNtpGlobalError(
            to_text(exc),
            extra={"code": getattr(exc, "code", None), "err": getattr(exc, "err", None)},
        )

    # Ensure the response is a string if it came back as bytes
    if isinstance(response, bytes):
        response = to_text(response)

    # Handle empty responses - the PUT endpoint answers 204 No Content
    if response in (None, ""):
        return None if not expect_content else {}

    # Check for application-level errors inside the JSON response body.
    # A "not found" body is handed back untouched when the caller allows it,
    # so the generic error path below cannot pre-empt the caller's own 404
    # handling.
    if isinstance(response, dict):
        if allow_not_found and _is_not_found_response(response):
            return response
        error = _extract_error(response)
        if error:
            raise FeNtpGlobalError(to_text(error.get("message")), details=error)

    return response


# ── Data-Fetching Functions ───────────────────────────────────────────────────
# These functions retrieve data from the device. They wrap _call_api()
# with the correct endpoint and method for each resource type.


def _fetch_ntp_config(
    module: AnsibleModule,
    connection: Connection,
) -> dict[str, Any]:
    """Fetch the full NTP configuration from the device.

    Sends GET /v0/configuration/ntp which returns an NtpSettings object
    holding a "vrBasedSettings" list, one entry per virtual router.

    Args:
        module:        The AnsibleModule instance.
        connection:    The device Connection object.

    Returns:
        The raw NtpSettings dict from the device. The documented unconfigured
        device is returned as an explicit empty C(vrBasedSettings) list.

    Raises:
        FeNtpGlobalError: If the device answered with something other than an
            NtpSettings object.
    """
    raw = _call_api(
        module,
        connection,
        method="GET",
        path=NTP_CONFIG_PATH,
        allow_not_found=True,
    )
    if _is_not_found_response(raw):
        module.warn(
            "The device reports no NTP configuration at {0}; treating it as "
            "unconfigured and using factory defaults.".format(NTP_CONFIG_PATH)
        )
        # Stated as an empty list rather than an empty dict, so "unconfigured"
        # cannot be confused with a response that simply lost its shape.
        return {"vrBasedSettings": []}
    if not isinstance(raw, dict):
        # Reading an unexpected shape as "unconfigured" would let the action
        # states PUT factory defaults over a configuration that is really there.
        raise FeNtpGlobalError(
            "Unexpected response when reading the NTP configuration from " "{0}".format(NTP_CONFIG_PATH),
            details={"response": raw},
        )
    if not isinstance(raw.get("vrBasedSettings"), list):
        raise FeNtpGlobalError(
            "The NTP configuration at {0} carries no 'vrBasedSettings' " "list".format(NTP_CONFIG_PATH),
            details={"response": raw},
        )
    return raw


# ── Address Helpers ───────────────────────────────────────────────────────────
# The REST API nests each server address inside a GeneralHostOrIp object with a
# "hostType" discriminator. These helpers derive, normalize and compare it.


def _determine_host_type(address: str, explicit: str | None) -> str:
    """Return the GeneralHostOrIp discriminator for an address.

    An explicitly supplied host_type always wins. Otherwise the address is
    parsed: anything that is a valid IP becomes IPv4 or IPv6, everything else
    is treated as a host name.
    """
    if explicit:
        return explicit
    try:
        return "IPv4" if ip_address(address).version == 4 else "IPv6"
    except ValueError:
        return "hostname"


def _normalize_address(address: str, host_type: str) -> str:
    """Normalize an address so repeated runs compare equal.

    IP addresses are rewritten in their canonical form (for example
    "2001:0db8:0000::1" becomes "2001:db8::1") so that a server already on the
    device is not seen as a different one. Host names are lowercased for the
    same reason: DNS is case-insensitive, so a device reporting
    "Time.Example.com" against a playbook asking for "time.example.com" is the
    same server, not a second one to add.
    """
    if host_type in ("IPv4", "IPv6"):
        try:
            return str(ip_address(address))
        except ValueError:
            return address
    return address.lower()


def _server_key(server: dict[str, Any]) -> tuple[str, str]:
    """Return the identity of a server entry: its type and normalized address.

    Two entries with the same key are the same NTP server, which is what the
    merge, replace and delete logic uses to match desired against current.
    """
    return (server.get("host_type", ""), server.get("address", ""))


# ── Validation ────────────────────────────────────────────────────────────────


def _normalize_vr_name(module: AnsibleModule, vr_name: str | None) -> str:
    """Validate vr_name and return it in the form the REST API expects.

    The OpenAPI spec allows 1-32 characters, but the device firmware rejects
    virtual router names longer than 16, so the firmware limit is enforced.

    The name is then put through the collection's shared normalization, the
    same helper extreme_fe_vrf uses: Fabric Engine stores user virtual router
    names in lowercase, while the system routers keep their canonical casing,
    so "globalrouter" becomes "GlobalRouter". The PUT path is case-sensitive,
    which is why the normalized name is what builds the URL.
    """
    if not vr_name or len(vr_name) > MAX_VR_NAME_LENGTH:
        module.fail_json(
            msg="vr_name must be 1-{0} characters, got '{1}' ({2} chars)".format(
                MAX_VR_NAME_LENGTH, vr_name, len(vr_name) if vr_name else 0
            )
        )
    normalized = normalize_vrf_name(vr_name)
    # Warn only when the user typed mixed case that had to be changed. A name
    # already in lowercase is the documented form, so converting it to the
    # canonical system casing is expected and needs no warning.
    if vr_name != normalized and vr_name.lower() != vr_name:
        module.warn(
            "Virtual router name '{0}' is not in canonical form. Fabric Engine "
            "stores user virtual router names in lowercase, but system virtual "
            "routers require canonical casing; the name will be converted to "
            "'{1}'.".format(vr_name, normalized)
        )
    return normalized


def _validate_poll_interval(module: AnsibleModule, poll_interval: int | None) -> None:
    """Fail early when poll_interval is outside the range the API accepts."""
    if poll_interval is None:
        return
    if poll_interval < MIN_POLL_INTERVAL or poll_interval > MAX_POLL_INTERVAL:
        module.fail_json(
            msg="poll_interval must be between {0} and {1}, got {2}".format(
                MIN_POLL_INTERVAL, MAX_POLL_INTERVAL, poll_interval
            )
        )


def _validate_servers(module: AnsibleModule, servers: list[dict[str, Any]]) -> None:
    """Validate each server entry before anything is sent to the device.

    Checks that the address is not empty and that an explicitly supplied
    host_type of IPv4 or IPv6 actually matches the address that was given.
    """
    for srv in servers:
        raw_address = srv.get("address")
        if raw_address is None or not str(raw_address).strip():
            module.fail_json(msg="NTP server 'address' is required and cannot be empty")
        # Validate the address in the form the payload will carry it:
        # _normalize_config_servers() strips it before building the request, so
        # checking the untrimmed value would let " 10.0.0.1 " past the mismatch
        # check and reject the same value as "not a valid IP" in the other branch.
        address = str(raw_address).strip()
        explicit = srv.get("host_type")
        if explicit == "hostname":
            # An IP literal tagged as a host name is a mismatch just as an
            # IPv4 address tagged IPv6 is. _determine_host_type() keeps an
            # explicit discriminator, so the PUT would send an address under
            # the wrong hostType, and _normalize_address() would skip
            # canonicalising it - breaking idempotency as well.
            try:
                parsed = ip_address(address)
            except ValueError:
                continue
            module.fail_json(
                msg="Address '{0}' is a valid {1} address but host_type is set "
                "to 'hostname'. Omit host_type to let it be detected, or "
                "set it to '{1}'.".format(address, "IPv4" if parsed.version == 4 else "IPv6")
            )
            return
        if explicit not in ("IPv4", "IPv6"):
            # host_type omitted - it is detected from the address
            continue
        try:
            parsed = ip_address(address)
        except ValueError:
            module.fail_json(
                msg="Address '{0}' is not a valid IP but host_type is set to '{1}'".format(address, explicit)
            )
            return
        detected = "IPv4" if parsed.version == 4 else "IPv6"
        if detected != explicit:
            module.fail_json(
                msg="Address '{0}' is {1} but host_type is set to '{2}'".format(address, detected, explicit)
            )


def _normalize_config_servers(module: AnsibleModule, servers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Turn the user's server entries into the module's internal format.

    Derives host_type when it was omitted, normalizes the address and keeps
    'enabled' as None when the user did not supply it, so each state can decide
    what "not supplied" means. A server listed twice - the same address, or
    one address in two notations (2001:db8::1 and 2001:db8:0:0:0:0:0:1, or a
    host name in two cases) - fails the task, as in the other modules of the
    collection: silently keeping one entry could keep the wrong 'enabled'.
    """
    raw = servers or []
    _validate_servers(module, raw)
    normalized: dict[tuple[str, str], dict[str, Any]] = {}
    for srv in raw:
        address = str(srv["address"]).strip()
        host_type = _determine_host_type(address, srv.get("host_type"))
        entry = {
            "address": _normalize_address(address, host_type),
            "host_type": host_type,
            "enabled": srv.get("enabled"),  # None means "not supplied"
        }
        key = _server_key(entry)
        if key in normalized:
            module.fail_json(
                msg="NTP server '{0}' is listed more than once in 'config.servers'; list each server once".format(
                    address
                )
            )
        normalized[key] = entry
    return list(normalized.values())


# ── Output Formatter ──────────────────────────────────────────────────────────
# These functions do the reverse of the payload builder: they convert the REST
# API response format back into the simpler Ansible format that users see in
# playbook output and registered variables.


def _to_ansible_server(rest_server: dict[str, Any]) -> dict[str, Any]:
    """Convert one REST NtpServer object into the Ansible output format.

    Example transformation:
        REST input:     {"ipAddress": {"hostType": "IPv4", "address": "10.10.10.1"},
                         "enabled": true}
        Ansible output: {"address": "10.10.10.1", "host_type": "IPv4", "enabled": true}
    """
    ip = rest_server.get("ipAddress") or {}
    address = str(ip.get("address") or "")
    # Older responses may omit the discriminator - derive it from the address
    host_type = _determine_host_type(address, ip.get("hostType"))
    return {
        "address": _normalize_address(address, host_type),
        "host_type": host_type,
        # OpenAPI default for NtpServer.enabled is true
        "enabled": bool(rest_server.get("enabled", SERVER_DEFAULT_ENABLED)),
    }


def _to_ansible_output(rest_block: dict[str, Any]) -> dict[str, Any]:
    """Convert one REST NtpSettingsByVr object into the Ansible output format.

    vrName is read-only on the device but is still reported back to the user so
    the output says which virtual router the settings belong to.
    """
    servers = [_to_ansible_server(srv) for srv in rest_block.get(FIELD_MAP["servers"]) or [] if isinstance(srv, dict)]
    return {
        "vr_name": rest_block.get("vrName"),
        "enabled": bool(rest_block.get(FIELD_MAP["enabled"], FULL_DEFAULTS["enabled"])),
        "poll_interval": rest_block.get(FIELD_MAP["poll_interval"], FULL_DEFAULTS["poll_interval"]),
        "servers": servers,
    }


def _all_vr_blocks(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a raw NtpSettings response into a list of Ansible-format blocks."""
    return [_to_ansible_output(block) for block in raw.get("vrBasedSettings") or [] if isinstance(block, dict)]


def _select_vr_block(blocks: list[dict[str, Any]], vr_name: str) -> dict[str, Any] | None:
    """Return the block belonging to vr_name, or None when the device has none.

    Virtual router names are matched case-insensitively so that "globalrouter"
    and "GlobalRouter" both find the same block.
    """
    wanted = vr_name.lower()
    for block in blocks:
        current_name = block.get("vr_name")
        if isinstance(current_name, str) and current_name.lower() == wanted:
            return block
    return None


def _public_block(block: dict[str, Any]) -> dict[str, Any]:
    """Return a block in the config option shape, without the internal vr_name.

    vr_name is the separate top-level option, so it is reported as the
    top-level vr_name result instead; this keeps gathered, before and after
    reusable as config.
    """
    return {key: value for key, value in block.items() if key != "vr_name"}


def _empty_block(vr_name: str) -> dict[str, Any]:
    """Return a factory-default block for a virtual router with no settings yet."""
    return {
        "vr_name": vr_name,
        "enabled": FULL_DEFAULTS["enabled"],
        "poll_interval": FULL_DEFAULTS["poll_interval"],
        "servers": [],
    }


# ── Payload Builder ───────────────────────────────────────────────────────────
# Converts an Ansible-format block into the NtpSettingsByVr body the PUT expects.


def _build_put_payload(block: dict[str, Any]) -> dict[str, Any]:
    """Build the NtpSettingsByVr REST payload for PUT.

    Every writable field is always included - the PUT replaces the whole
    configuration of the virtual router, so a field left out of the body would
    be reset by the device rather than kept.

    vrName is deliberately absent: the schema marks it readOnly and the value
    is already carried by the {vr_name} path segment.

    Args:
        block: An Ansible-format block with enabled, poll_interval and servers.

    Returns:
        A dict ready to send as the PUT request body.
    """
    return {
        FIELD_MAP["enabled"]: block["enabled"],
        FIELD_MAP["poll_interval"]: block["poll_interval"],
        FIELD_MAP["servers"]: [
            {
                # The REST API nests the address inside a GeneralHostOrIp object
                # with a "hostType" discriminator for hostname / IPv4 / IPv6
                "ipAddress": {
                    "hostType": srv["host_type"],
                    "address": srv["address"],
                },
                "enabled": srv["enabled"],
            }
            for srv in block["servers"]
        ],
    }


# ── Diff / Comparison Logic ──────────────────────────────────────────────────
# These functions compare the NTP state before and after changes to produce a
# human-readable summary, and to decide whether the PUT is needed at all.


def _sorted_servers(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a block's servers sorted by identity so order causes no false diff."""
    return sorted(block.get("servers") or [], key=_server_key)


def _blocks_equal(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Return True when two blocks hold the same writable configuration.

    Only writable fields are compared - vr_name is read-only, so a difference
    there would never be something the module could or should act on.
    """
    return (
        before.get("enabled") == after.get("enabled")
        and before.get("poll_interval") == after.get("poll_interval")
        and _sorted_servers(before) == _sorted_servers(after)
    )


def _compute_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compute the differences between the before and after NTP states.

    Args:
        before: NTP block before the module ran.
        after:  NTP block after the module ran.

    Returns:
        A dict where each key is a changed field and the value is a dict with
        'before' and 'after' values. Empty when nothing changed.
    """
    diff: dict[str, dict[str, Any]] = {}
    for field in ("enabled", "poll_interval"):
        if before.get(field) != after.get(field):
            diff[field] = {"before": before.get(field), "after": after.get(field)}
    before_servers = _sorted_servers(before)
    after_servers = _sorted_servers(after)
    if before_servers != after_servers:
        diff["servers"] = {"before": before_servers, "after": after_servers}
    return diff


# ── Desired-State Builders ────────────────────────────────────────────────────
# One builder per state. Each returns the complete block that should end up on
# the device, which _apply_desired() then compares against the current block.


def _desired_merged(
    current: dict[str, Any], config: dict[str, Any], desired_servers: list[dict[str, Any]]
) -> dict[str, Any]:
    """MERGED - apply supplied fields, add supplied servers, remove nothing.

    Scalar fields the user did not supply keep their current value. A server
    that is already configured keeps its admin state unless the user gave one;
    a server that is new is enabled, matching the OpenAPI default.
    """
    block = {
        "vr_name": current.get("vr_name"),
        "enabled": current["enabled"],
        "poll_interval": current["poll_interval"],
        "servers": [dict(srv) for srv in current["servers"]],
    }
    if config.get("enabled") is not None:
        block["enabled"] = config["enabled"]
    if config.get("poll_interval") is not None:
        block["poll_interval"] = config["poll_interval"]

    existing_by_key = {_server_key(srv): srv for srv in block["servers"]}
    for srv in desired_servers:
        match = existing_by_key.get(_server_key(srv))
        if match is None:
            # Not on the device yet - add it, defaulting the admin state to on
            new_entry = {
                "address": srv["address"],
                "host_type": srv["host_type"],
                "enabled": SERVER_DEFAULT_ENABLED if srv["enabled"] is None else srv["enabled"],
            }
            block["servers"].append(new_entry)
            existing_by_key[_server_key(new_entry)] = new_entry
        elif srv["enabled"] is not None:
            # Already there - only touch the admin state if the user supplied one
            match["enabled"] = srv["enabled"]
    return block


def _desired_replaced(
    current: dict[str, Any], config: dict[str, Any], desired_servers: list[dict[str, Any]]
) -> dict[str, Any]:
    """REPLACED - the supplied servers list becomes the final list for the VR.

    Servers on the device that are not in the list are removed, servers in the
    list that are missing are added, and servers in both keep their admin state
    unless the user supplied one. Omitting the 'servers' key entirely leaves the
    current list alone. Scalar fields that are not supplied are left alone too.
    """
    block = {
        "vr_name": current.get("vr_name"),
        "enabled": current["enabled"],
        "poll_interval": current["poll_interval"],
        "servers": [dict(srv) for srv in current["servers"]],
    }
    if config.get("enabled") is not None:
        block["enabled"] = config["enabled"]
    if config.get("poll_interval") is not None:
        block["poll_interval"] = config["poll_interval"]

    if config.get("servers") is None:
        # The key was omitted - the current server list stays as it is
        return block

    current_by_key = {_server_key(srv): srv for srv in current["servers"]}
    final_servers = []
    for srv in desired_servers:
        previous = current_by_key.get(_server_key(srv))
        enabled = srv["enabled"]
        if enabled is None:
            # Keep what the device has, or enable the server if it is new
            enabled = previous["enabled"] if previous else SERVER_DEFAULT_ENABLED
        final_servers.append({"address": srv["address"], "host_type": srv["host_type"], "enabled": enabled})
    block["servers"] = final_servers
    return block


def _desired_overridden(vr_name: str, config: dict[str, Any], desired_servers: list[dict[str, Any]]) -> dict[str, Any]:
    """OVERRIDDEN - enforce the supplied config exactly.

    Every writable field that the user did not supply is reset to its factory
    default from FULL_DEFAULTS, and the supplied servers list is the complete
    server list - anything else on the device is removed.
    """
    enabled = config.get("enabled")
    poll_interval = config.get("poll_interval")
    return {
        "vr_name": vr_name,
        "enabled": FULL_DEFAULTS["enabled"] if enabled is None else enabled,
        "poll_interval": (FULL_DEFAULTS["poll_interval"] if poll_interval is None else poll_interval),
        "servers": [
            {
                "address": srv["address"],
                "host_type": srv["host_type"],
                "enabled": (SERVER_DEFAULT_ENABLED if srv["enabled"] is None else srv["enabled"]),
            }
            for srv in desired_servers
        ],
    }


def _desired_deleted(
    current: dict[str, Any], config: dict[str, Any], desired_servers: list[dict[str, Any]]
) -> dict[str, Any]:
    """DELETED - reset to factory defaults.

    Without a config the whole NTP configuration goes back to DEFAULTS. With a
    config, only the scalar fields named in it are reset and only the servers
    listed in it are removed; an empty servers list removes nothing. A config
    with no option set (config: {} arrives with every suboption None) counts as
    omitted, as for every other module of the collection.
    """
    if not _has_supplied_value(config):
        # Delete-all - every field returns to its factory default
        block = _empty_block(current.get("vr_name"))
        block["enabled"] = DEFAULTS["enabled"]
        block["poll_interval"] = DEFAULTS["poll_interval"]
        return block

    block = {
        "vr_name": current.get("vr_name"),
        "enabled": current["enabled"],
        "poll_interval": current["poll_interval"],
        "servers": [dict(srv) for srv in current["servers"]],
    }
    if config.get("enabled") is not None:
        block["enabled"] = DEFAULTS["enabled"]
    if config.get("poll_interval") is not None:
        block["poll_interval"] = DEFAULTS["poll_interval"]
    if config.get("servers") is not None:
        remove_keys = {_server_key(srv) for srv in desired_servers}
        block["servers"] = [srv for srv in block["servers"] if _server_key(srv) not in remove_keys]
    return block


# ── State Handlers ────────────────────────────────────────────────────────────
# Each handler fills ``result`` in place and returns without calling exit_json().


def _handle_gathered(
    module: AnsibleModule, vr_name: str, current: dict[str, Any] | None, result: dict[str, Any]
) -> None:
    """GATHERED - read-only, return the current configuration of the VR.

    A virtual router the device does not report is not an error for a read-only
    operation, so the factory-default shape is returned with a warning instead.
    """
    if current is None:
        module.warn("No NTP settings returned for virtual router '{0}'".format(vr_name))
        current = _empty_block(vr_name)
    result["vr_name"] = current.get("vr_name") or vr_name
    result["ntp_global"] = {"config": _public_block(current)}
    result["gathered"] = _public_block(current)


def _apply_desired(
    module: AnsibleModule,
    connection: Connection,
    vr_name: str,
    current: dict[str, Any],
    desired: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Send the desired block to the device, but only when it differs.

    The NTP API offers no PATCH, so a change always means replacing the whole
    virtual router configuration with PUT /v0/configuration/ntp/{vr_name}. The
    device is read first and the PUT skipped when nothing would change, which is
    what makes every state idempotent.
    """
    result["ntp_global"] = {"before": current}

    if _blocks_equal(current, desired):
        # Nothing to do - the device already holds the desired configuration
        result["ntp_global"]["after"] = current
        result["ntp_global"]["differences"] = {}
        return

    payload = _build_put_payload(desired)
    path = NTP_VR_CONFIG_TEMPLATE.format(vr_name=quote(vr_name, safe=""))
    result["submitted"] = {"path": path, "payload": payload}

    if not module.check_mode:
        # PUT replaces the complete NTP configuration of this virtual router
        try:
            _call_api(
                module,
                connection,
                method="PUT",
                path=path,
                payload=payload,
                expect_content=False,  # the endpoint answers 204 No Content
            )
        except FeNtpGlobalError as exc:
            if "code" in exc.extra and is_answer_unknown_code(exc.extra["code"]):
                # A transport failure without an HTTP status: the answer was
                # lost and the device may have applied the PUT, so changed is
                # reported (an error document or an HTTP error carries a code).
                result["changed"] = True
                raise FeNtpGlobalError(
                    "%s. The PUT %s may have been applied before the answer was lost; check the NTP "
                    "configuration of virtual router '%s' on the device." % (to_text(exc).rstrip("."), path, vr_name),
                    details=dict(exc.details, outcome="unknown"),
                    extra=exc.extra,
                ) from exc
            raise
        # Set only now: a rejected PUT must report changed=false, any failure
        # after it (the re-read below) changed=true.
        result["changed"] = True
        # Re-read so the reported "after" is what the device really holds
        try:
            after_raw = _fetch_ntp_config(module, connection)
        except FeNtpGlobalError as exc:
            raise FeNtpGlobalError(
                "The NTP configuration of virtual router '%s' was applied (PUT %s), but re-reading it afterwards "
                "failed: %s" % (vr_name, path, to_text(exc)),
                details=exc.details,
                extra=exc.extra,
            )
        after_block = _select_vr_block(_all_vr_blocks(after_raw), vr_name)
        if after_block is None:
            # The device took the write but will not say what it holds. Falling
            # back to `desired` here would report a state nothing confirmed and
            # hide an inconsistent write behind a success.
            raise FeNtpGlobalError(
                "The device accepted the NTP write for virtual router '{0}' but "
                "does not report its settings back, so the result could not be "
                "confirmed".format(vr_name),
                details={
                    "path": path,
                    "available_vr_names": [block.get("vr_name") for block in _all_vr_blocks(after_raw)],
                },
            )
        result["ntp_global"]["after"] = after_block
    else:
        # Check mode - report the state that would have been written
        result["changed"] = True
        result["ntp_global"]["after"] = desired

    result["ntp_global"]["differences"] = _compute_diff(current, result["ntp_global"]["after"])


def _build_desired(
    module: AnsibleModule,
    state: str,
    vr_name: str,
    current: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to the desired-state builder for the requested state."""
    desired_servers = _normalize_config_servers(module, config.get("servers"))
    if state == STATE_MERGED:
        return _desired_merged(current, config, desired_servers)
    if state == STATE_REPLACED:
        return _desired_replaced(current, config, desired_servers)
    if state == STATE_OVERRIDDEN:
        return _desired_overridden(vr_name, config, desired_servers)
    return _desired_deleted(current, config, desired_servers)


# ── Main Entry Point ─────────────────────────────────────────────────────────
# This is where the module logic starts. The function:
# 1. Creates the AnsibleModule (validates user input against ARGUMENT_SPEC)
# 2. Connects to the device via httpapi
# 3. Reads the current NTP config from the device
# 4. Builds the desired block for the requested state and PUTs it if needed
# 5. Returns results with changed=true/false and before/after config


def run_module() -> None:
    # supports_check_mode=True means this module can simulate changes
    # without actually modifying the device (--check flag in ansible-playbook)
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    # Establish connection to the device via the httpapi plugin
    try:
        connection = _get_connection(module)
    except FeNtpGlobalError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    # Initialize the result dict - this is what gets returned to the user
    result: dict[str, Any] = {
        "changed": False,  # Will be set to True if we modify anything
    }

    try:
        state = module.params["state"]  # Which operation to perform
        config = module.params.get("config") or {}  # User's desired NTP config

        # ── Validate input before touching the device ────────────────
        # vr_name is resolved to the exact, case-sensitive identifier the REST
        # path needs, using the same shared helper extreme_fe_vrf relies on
        vr_name = _normalize_vr_name(module, module.params["vr_name"])
        _validate_poll_interval(module, config.get("poll_interval"))
        if state != STATE_GATHERED:
            # The server entries (addresses, host_type, a server listed twice in
            # any notation) are checked here, before the first GET, so a bad or
            # duplicate entry fails without any request; _build_desired()
            # normalizes them again from the same input.
            _normalize_config_servers(module, config.get("servers"))

        # merged/replaced/overridden need something to work with. Without this
        # guard, 'overridden' with no config would wipe the NTP configuration.
        # Ansible fills omitted suboptions with None, so config: {} arrives as
        # a non-empty dict - only a non-null value counts as supplied.
        if state in REQUIRES_CONFIG and not _has_supplied_value(config):
            raise FeNtpGlobalError("value of config parameter must not be empty for state {0}".format(state))

        # ── GET the current NTP configuration ────────────────────────
        # Always read first: it provides the "before" output and the baseline
        # every state folds the user's config into.
        current_raw = _fetch_ntp_config(module, connection)
        blocks = _all_vr_blocks(current_raw)
        current = _select_vr_block(blocks, vr_name)

        # ── Read-only path returns early ─────────────────────────────
        if state == STATE_GATHERED:
            _handle_gathered(module, vr_name, current, result)
            module.exit_json(**result)
            return

        if current is None:
            if blocks:
                # The device does report NTP settings, just not for this virtual
                # router, so writing would target the wrong resource.
                raise FeNtpGlobalError(
                    "No NTP settings found for virtual router '{0}'".format(vr_name),
                    details={"available_vr_names": [b.get("vr_name") for b in blocks]},
                )
            # Nothing is configured anywhere: this is a device being set up for
            # the first time, so the factory defaults are the baseline the
            # requested state folds the user's config into.
            current = _empty_block(vr_name)

        # ── Build and apply the desired configuration ────────────────
        result["vr_name"] = current.get("vr_name") or vr_name
        desired = _build_desired(module, state, vr_name, current, config)
        _apply_desired(module, connection, vr_name, current, desired, result)
        # Output uses the config option shape; vr_name is its own result key.
        ntp_result = result["ntp_global"]
        ntp_result["before"] = _public_block(ntp_result["before"])
        ntp_result["after"] = _public_block(ntp_result["after"])
        result["before"] = ntp_result["before"]
        # Top-level "after" is returned for every action state: the re-read
        # state after a change, the prediction in check mode, and the
        # unchanged "before" when nothing had to be written.
        result["after"] = ntp_result["after"]

        # ── Diff mode (--diff) ───────────────────────────────────────
        # Ansible renders the before/after pair itself, so the module only
        # has to supply it. It is populated whether or not anything changed
        # (two identical dicts simply render as no diff), and in check mode
        # the "after" is the predicted state, which is exactly what
        # --check --diff is meant to show.
        if module._diff:
            result["diff"] = {
                "before": result["before"],
                "after": result["after"],
            }

        module.exit_json(**result)

    # ── Error Handling ───────────────────────────────────────────────
    # Two types of errors can occur:
    # 1. FeNtpGlobalError - our own validation or logic errors
    # 2. ConnectionError - device communication failures
    except FeNtpGlobalError as exc:
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
