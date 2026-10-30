# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage the SSH service flags on Extreme Fabric Engine switches.

Module Architecture Overview
============================
This module manages the two SSH-related flags exposed under the System
Services configuration on Extreme Fabric Engine switches via the REST
OpenAPI.

REST Endpoints used:
  GET   /v0/configuration/system-services
        -> Retrieve the full SystemServicesSettings object
  PATCH /v0/configuration/system-services
        -> Partially update the SystemServicesSettings object
           (request/response body is a SystemServicesSettings object,
           success response is 204 No Content)

Fields used (OpenAPI schema SystemServicesSettings.ssh):
  ssh.enabled        - SSH service status                          (no default in spec)
  ssh.globalEnabled   - global SSH service status (Fabric Engine only, x-nos: fabric-engine)

Fields NOT managed by this module (present in SystemServicesSettings but
out of scope, per requirements - discarded entirely, never read or written):
  telnet, ftp, iqagent, webServer, cloudConnector, vxlanGwFullInterworkingMode

Fabric Engine constraints:
  - The OpenAPI spec documents no default value for either ssh.enabled or
    ssh.globalEnabled, and the User Guide is not conclusive either: its
    Variable Definitions table for the CLI sshd boot-config flag states a
    default of "disabled", but the only default statement found for the
    separate global ssh boot-config flag is scoped to Zero Touch
    Deployment mode ("The ssh and sshd boot configuration flags are
    enabled by default"), not the plain factory-default baseline. Both
    FULL_DEFAULTS values below were confirmed with the requester rather
    than assumed - see the FULL_DEFAULTS comment.
  - PATCH is a partial update: only the "ssh" key is ever sent in the
    request body, so the other SystemServicesSettings fields (telnet,
    ftp, iqagent, webServer, cloudConnector,
    vxlanGwFullInterworkingMode) are never read from the device output
    and never touched by a write this module makes.
  - The OpenAPI description for the ssh object states: "On Fabric Engine
    (VOSS) to connect with ssh both flags must be enabled." This is a
    behavioural note, not a schema constraint - the two fields can still
    be set independently in one merged call.

Supported states:
  - merged     : Additive - supplied field(s) are applied, the other
                 field is left at its current value
  - replaced   : The supplied fields are authoritative; any omitted
                 field is reset to its factory default
  - overridden : Functionally identical to replaced - ssh is a singleton
                 object with no listed/unlisted sub-resources to
                 reconcile
  - deleted    : Reset to factory defaults; with a config only the
                 fields named in it are reset
  - gathered   : Read-only, returns the current ssh.enabled and
                 ssh.globalEnabled values

Code Flow (run_module):
  1. Connect to the switch via httpapi
  2. Fetch the current System Services config (GET) and extract only "ssh"
  3. Build the desired ssh block for the requested state
  4. PATCH only the fields that differ from the current block (idempotency)
  5. Re-read and return before/after/differences
"""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_ssh
short_description: Manage the SSH service flags on ExtremeNetworks Fabric Engine switches
version_added: "1.3.0"
description:
  - Manage the SSH service flags on ExtremeNetworks Fabric Engine switches using the
    custom C(extreme_fe) HTTPAPI plugin.
  - Uses C(/v0/configuration/system-services) from the NOS OpenAPI schema.
  - Manages only C(enabled) and C(global_enabled) under the C(ssh) object of the
    System Services configuration. Every other System Services field (C(telnet),
    C(ftp), C(iqagent), C(webServer), C(cloudConnector),
    C(vxlanGwFullInterworkingMode)) is out of scope for this module and is never
    read or written by it.
  - The REST API exposes C(PATCH) for System Services, so only the C(ssh) object,
    and only the fields that changed, are sent in the request body.
author:
  - Andreea-Lavinia Vraja (@avraja_extr)
requirements:
  - ansible.netcommon
notes:
  - Tested against Fabric Engine Version 9.3.2.
  - A PATCH that fails without an answer (a lost connection) and cannot be re-read, or whose re-read
    omits an attempted flag, may have been applied, so the task reports C(changed=true); with no flag
    confirmed applied, C(details.outcome=unknown).
  - This module manages only the C(ssh.enabled) and C(ssh.globalEnabled) flags of the
    System Services configuration. All other System Services fields are left
    completely untouched - the module never reads or writes C(telnet), C(ftp),
    C(iqagent), C(webServer), C(cloudConnector) or C(vxlanGwFullInterworkingMode).
  - C(global_enabled) (REST C(globalEnabled)) is marked with the OpenAPI attribute
    C(x-nos=fabric-engine), meaning it applies only to Fabric Engine (VOSS), which
    matches this collection's target platform.
  - The OpenAPI spec's description of the C(ssh) object states that on Fabric Engine
    (VOSS) both C(enabled) and C(global_enabled) must be C(true) to connect over SSH.
    This is a behavioural note only; the two fields can still be set independently in
    one C(merged) task.
  - C(overridden) behaves exactly like C(replaced) for this module, because the SSH
    configuration is a singleton object with no listed/unlisted sub-resources to
    reconcile.
  - Neither C(enabled) nor C(global_enabled) has a documented default in the OpenAPI
    spec. The factory default used by C(replaced), C(overridden) and C(deleted) for
    both fields is C(false), confirmed with the requester rather than assumed - the
    User Guide's own Variable Definitions table for the CLI C(sshd) boot-config flag
    states a default of "disabled", and no separate non-Zero-Touch-Deployment default
    was found for the global ssh flag.
  - A flag the device does not report (or reports as null) is unknown. It is C(null) in
    C(before) and C(after), a requested value for it is always sent, and C(gathered)
    fails rather than publishing it.
  - Supports check mode and diff mode. Under C(--diff) the module reports the ssh
    configuration before and after the change; combined with C(--check) the reported
    "after" is the state that would have been written.
  - When the PATCH fails, the module re-reads the ssh configuration and reports in the
    failure C(details) which of the attempted fields the device applied
    (C(applied_fields), C(not_applied_fields)), or C(reread_error) when the re-read
    failed too (with C(reread_error_code) when the device gave a numeric error code);
    C(changed) is true when a field was applied. An error document in a 2xx answer,
    to the GET or to the PATCH, is reported by its numeric code only, never by its
    message or payload, which could quote a stored credential. A re-read that does
    not report an attempted field (or reports it as null) lists it in
    C(unknown_fields), without assuming a default, and still attributes the fields it
    reports (one that reports none of them counts as a failed re-read). When the PATCH succeeds
    but the following re-read fails, the task fails with C(changed=true) and a message
    saying the PATCH was applied.
options:
  config:
    description:
      - SSH service flags to manage.
      - Required when C(state) is C(merged), C(replaced) or C(overridden).
      - A C(config) with no option set (for example C({})) counts as omitted for these
        states and fails before any request is sent.
      - Optional when C(state=deleted); if omitted, or given with no option set, both flags
        are reset to their factory default.
    type: dict
    suboptions:
      enabled:
        description:
          - SSH service status.
          - Factory default is C(false) (see the module notes).
          - When omitted, C(merged) leaves the current value alone, while C(replaced)
            and C(overridden) reset it to C(false).
        type: bool
      global_enabled:
        description:
          - Global SSH service status. Applicable only to Fabric Engine (VOSS).
          - On Fabric Engine, both C(enabled) and C(global_enabled) must be C(true) to
            connect over SSH.
          - Factory default is C(false) (see the module notes).
          - When omitted, C(merged) leaves the current value alone, while C(replaced)
            and C(overridden) reset it to C(false).
        type: bool
  state:
    description:
      - Desired module operation.
      - C(merged) applies the supplied field(s), leaving the other field untouched.
      - C(replaced) makes the supplied fields authoritative; an omitted field is reset
        to its factory default.
      - C(overridden) behaves exactly like C(replaced) for this singleton resource.
      - C(deleted) resets the SSH flags to their factory defaults. When C(config)
        names a field, only the fields named in it are reset; a C(config) with no
        option set (for example C({})) resets both, as when it is omitted.
      - C(gathered) returns the current SSH flags without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
"""

EXAMPLES = r"""
# - name: Configure the SSH service flags
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Enable the SSH service
  extreme.fe.extreme_fe_ssh:
    state: merged
    config:
      enabled: true
      global_enabled: true

- name: Enable only the global SSH flag, leave the service flag untouched
  extreme.fe.extreme_fe_ssh:
    state: merged
    config:
      global_enabled: true

- name: Make the supplied flags authoritative
  extreme.fe.extreme_fe_ssh:
    state: replaced
    config:
      enabled: true
      global_enabled: true

- name: Enforce the exact SSH configuration
  extreme.fe.extreme_fe_ssh:
    state: overridden
    config:
      enabled: true
      global_enabled: true

- name: Reset the global SSH flag to its factory default
  extreme.fe.extreme_fe_ssh:
    state: deleted
    config:
      global_enabled: true

- name: Reset both SSH flags to their factory defaults
  extreme.fe.extreme_fe_ssh:
    state: deleted

- name: Collect the current SSH configuration
  extreme.fe.extreme_fe_ssh:
    state: gathered
  register: ssh_info
"""

RETURN = r"""
---
changed:
  description: Indicates whether any configuration changes were made.
  returned: always
  type: bool
before:
  description:
    - SSH configuration before any changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
after:
  description:
    - SSH configuration after changes.
    - Returned for every action state, also when nothing changed (then equal to C(before)).
    - In check mode this is the predicted state that would have been written.
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
gathered:
  description:
    - Current SSH configuration gathered from the device.
    - Returned only for C(state=gathered). Always holds both flags; the gather fails when the device does not
      report one of them.
  returned: when state is gathered
  type: dict
ssh:
  description: SSH configuration state with differences (per-resource detail).
  returned: always
  type: dict
  contains:
    before:
      description: SSH configuration before the requested change.
      returned: when state != gathered
      type: dict
    after:
      description: SSH configuration after the requested change.
      returned: when state != gathered
      type: dict
    config:
      description: Current SSH configuration in gathered mode.
      returned: when state == gathered
      type: dict
    differences:
      description: Changed fields with before and after values.
      returned: when state != gathered
      type: dict
submitted:
  description: Payload submitted to the device (the PATCH body) when a change was required.
  returned: when a change was required
  type: dict
"""

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
# These constants define the REST API endpoint the module communicates with.
# The NOS OpenAPI spec exposes System Services under
# /v0/configuration/system-services. Only the nested "ssh" object is used;
# every other top-level field in the response (telnet, ftp, iqagent,
# webServer, cloudConnector, vxlanGwFullInterworkingMode) is out of scope.

# GET returns a SystemServicesSettings object; PATCH partially updates it.
SYSTEM_SERVICES_PATH = "/v0/configuration/system-services"

# The single sub-object this module manages within SystemServicesSettings.
SSH_KEY = "ssh"

# Ansible parameter name -> REST API field name mapping, both nested under
# the "ssh" object.
# Excluded (out of scope per requirements, never read or written):
#   telnet.enabled, ftp.enabled, iqagent.*, webServer.*, cloudConnector.*,
#   vxlanGwFullInterworkingMode.
FIELD_MAP = {
    "enabled": "enabled",  # SSH service status
    "global_enabled": "globalEnabled",  # Global SSH status (x-nos: fabric-engine)
}

# Factory defaults for the writable ssh fields.
# Neither field has a "default:" in the OpenAPI schema. The User Guide's own
# Variable Definitions table for the CLI "sshd" boot-config flag states a
# default of "disabled", but the only default statement found for the
# separate global "ssh" boot-config flag is scoped to Zero Touch Deployment
# mode, not the plain factory-default baseline. Both values below were
# confirmed with the requester rather than assumed.
# Default from User Guide (not in OpenAPI), confirmed by user on 2026-09-23.
FULL_DEFAULTS: dict[str, Any] = {
    "enabled": False,  # SSH service off at factory default
    "global_enabled": False,  # Global SSH flag off at factory default
}

# Values the 'deleted' state resets a field to. ssh is a singleton resource,
# so resetting it to factory defaults is the same as FULL_DEFAULTS.
DEFAULTS: dict[str, Any] = dict(FULL_DEFAULTS)

# State constants - each state defines a different module behaviour.
# See the DOCUMENTATION string above for what each state does.
STATE_MERGED = "merged"  # Additive - apply supplied field(s) only
STATE_REPLACED = "replaced"  # Supplied fields are authoritative
STATE_OVERRIDDEN = "overridden"  # Identical to replaced (singleton, no sub-resources)
STATE_DELETED = "deleted"  # Reset to factory defaults (all, or only what is named)
STATE_GATHERED = "gathered"  # Read-only - just return the current flags

# These states require the user to provide a 'config' parameter. Without this
# guard, 'overridden' with no config would silently reset both SSH flags.
REQUIRES_CONFIG = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}

# ── Argument Spec ─────────────────────────────────────────────────────────────
# ARGUMENT_SPEC defines all parameters the user can pass to this module.
# Ansible uses this to validate user input before the module runs.

ARGUMENT_SPEC = {
    # config - the SSH flags the user wants to manage.
    # It is a dict (not a list) because SSH is a singleton resource on the device.
    "config": {
        "type": "dict",
        "options": {
            # enabled - SSH service status. No default here on purpose:
            # None means "not supplied", which each state interprets itself.
            "enabled": {"type": "bool"},
            # global_enabled - global SSH status (Fabric Engine only). Same
            # "not supplied" convention as enabled.
            "global_enabled": {"type": "bool"},
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


class FeSshError(Exception):
    """Raised for SSH module validation or response issues.

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
        changed: bool = False,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        # Top-level fail_json keys (code, err) of a transport failure.
        self.extra = extra or {}
        # True when the device was already changed before this error.
        self.changed = changed

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
            "message": message or "Device reported a System Services error",
            "payload": payload,
        }
    # Check for an explicit errors list in the response
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported System Services errors",
            "errors": errors,
            "payload": payload,
        }
    return None


def _get_connection(module: AnsibleModule) -> Connection:
    """Create and return a Connection object for talking to the device.

    The connection uses the httpapi plugin (extreme_fe) which handles
    authentication and REST API communication.

    Args:
        module: The AnsibleModule instance.

    Returns:
        A Connection object ready to send REST requests.

    Raises:
        FeSshError: If no socket path is available (wrong connection type).
    """
    if not module._socket_path:
        raise FeSshError("Connection type httpapi is required for this module")
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
    1. Sends the HTTP request (GET or PATCH)
    2. Checks for errors in the response
    3. Returns the parsed response data

    Args:
        module:          The AnsibleModule instance.
        connection:      The device Connection object.
        method:          HTTP method ("GET" or "PATCH").
        path:            REST API path (e.g. "/v0/configuration/system-services").
        payload:         Request body data (for PATCH), or None for GET.
        expect_content:  If True, treat empty responses as empty dicts;
                         if False, treat empty responses as None (for 204 No Content).
        allow_not_found: when True, a 404 is returned to the caller rather than
                         failing the task.

    Returns:
        The parsed response (dict, list, string, or None).
    """
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        if allow_not_found and getattr(exc, "code", None) == 404:
            return {"statusCode": 404}
        # Connection-level failure (device unreachable, auth error, etc.).
        # Raised rather than failed here so a failed PATCH can be attributed;
        # run_module() fails with the same msg, code and err.
        raise FeSshError(
            to_text(exc),
            extra={"code": getattr(exc, "code", None), "err": getattr(exc, "err", None)},
        )

    # Ensure the response is a string if it came back as bytes
    if isinstance(response, bytes):
        response = to_text(response)

    # Handle empty responses - the PATCH endpoint answers 204 No Content
    if response in (None, ""):
        return None if not expect_content else {}

    # Check for application-level errors inside the JSON response body.
    if isinstance(response, dict):
        if allow_not_found and _is_not_found_response(response):
            return response
        error = _extract_error(response)
        if error:
            # An error document in a 2xx answer bypasses the HTTPAPI sanitizer, and
            # its free-form text or payload could quote a stored web-server or proxy
            # credential of system-services, so only its numeric code is kept, for
            # the GET and the PATCH alike.
            raise FeSshError(_error_document_message(method, path, error.get("code")), details=_numeric_code(error))

    return response


def _numeric_code(error: dict[str, Any]) -> dict[str, Any]:
    """Return {"code": <int>} for an error carrying a numeric code, else {}."""
    code = error.get("code")
    return {"code": code} if isinstance(code, int) else {}


def _error_document_message(method: str, path: str, code: Any) -> str:
    """Generic message for an error document in a 2xx answer; the device's own text is not copied."""
    return (
        "The device answered %s %s with an error document%s; its message is not shown, as it may quote a "
        "stored credential"
    ) % (
        method,
        path,
        " (error code %d)" % code if isinstance(code, int) else "",
    )


# ── Data-Fetching Functions ───────────────────────────────────────────────────
# These functions retrieve data from the device. They wrap _call_api() with
# the correct endpoint and method, and extract only the "ssh" sub-object -
# every other System Services field is discarded before it reaches any
# other part of the module.


def _fetch_ssh_config(
    module: AnsibleModule,
    connection: Connection,
) -> dict[str, Any]:
    """Fetch the System Services configuration and return only its "ssh" object.

    Sends GET /v0/configuration/system-services, which returns a full
    SystemServicesSettings object. Only the nested "ssh" object is kept;
    telnet, ftp, iqagent, webServer, cloudConnector and
    vxlanGwFullInterworkingMode are discarded here and never seen again by
    any other part of this module.

    Args:
        module:     The AnsibleModule instance.
        connection: The device Connection object.

    Returns:
        The raw "ssh" dict from the device (REST field names), or an empty
        dict when the device reports no ssh object at all.

    Raises:
        FeSshError: If the device answered with something other than a
            SystemServicesSettings object.
    """
    raw = _call_api(
        module,
        connection,
        method="GET",
        path=SYSTEM_SERVICES_PATH,
        allow_not_found=True,
    )
    if _is_not_found_response(raw):
        module.warn(
            "The device reports no System Services configuration at {0}; "
            "the '{1}' flags are unknown.".format(SYSTEM_SERVICES_PATH, SSH_KEY)
        )
        return {}
    if not isinstance(raw, dict):
        raise FeSshError(
            "Unexpected response when reading the System Services configuration "
            "from {0}".format(SYSTEM_SERVICES_PATH),
            # The raw body is not returned: it could carry stored credentials.
            details={"response_type": type(raw).__name__},
        )
    ssh_raw = raw.get(SSH_KEY)
    if ssh_raw is None:
        module.warn(
            "The device reports no '{0}' object under {1}; its flags are "
            "unknown.".format(SSH_KEY, SYSTEM_SERVICES_PATH)
        )
        return {}
    if not isinstance(ssh_raw, dict):
        raise FeSshError(
            "The System Services configuration at {0} carries a non-object "
            "'{1}' value".format(SYSTEM_SERVICES_PATH, SSH_KEY),
            details={"response": {SSH_KEY: ssh_raw}},
        )
    return ssh_raw


# ── Output Formatter ──────────────────────────────────────────────────────────
# Converts the REST "ssh" object into the simpler Ansible format users see in
# playbook output and registered variables.


def _to_ansible_output(rest_ssh: dict[str, Any]) -> dict[str, Any]:
    """Convert one REST ssh object into the Ansible output format.

    Example transformation:
        REST input:     {"enabled": true, "globalEnabled": true}
        Ansible output: {"enabled": true, "global_enabled": true}

    A field missing from the device response (or reported as null) stays
    None: its value is unknown. It is never filled with a default, so a write
    still sends a requested value for it (None differs from every value), and
    gathered refuses to publish it (_handle_gathered()).
    """
    return {
        option: None if rest_ssh.get(rest_key) is None else bool(rest_ssh[rest_key])
        for option, rest_key in FIELD_MAP.items()
    }


# ── Payload Builder ───────────────────────────────────────────────────────────
# Converts an Ansible-format ssh block into the partial PATCH body: only the
# fields whose desired value differs from the current one are included, so
# every PATCH only ever carries the "ssh" key and, within it, only the
# field(s) that actually changed.


def _build_patch_payload(current: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    """Build the PATCH body for the fields that differ between current and desired.

    Returns an empty dict when nothing differs, so the caller can skip the
    PATCH entirely and report changed=false.
    """
    changed_fields = {
        FIELD_MAP[option]: desired[option] for option in FIELD_MAP if current.get(option) != desired[option]
    }
    if not changed_fields:
        return {}
    return {SSH_KEY: changed_fields}


# ── Diff / Comparison Logic ──────────────────────────────────────────────────


def _compute_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compute the differences between the before and after ssh states.

    Args:
        before: ssh block before the module ran.
        after:  ssh block after the module ran.

    Returns:
        A dict where each key is a changed field and the value is a dict with
        'before' and 'after' values. Empty when nothing changed.
    """
    diff: dict[str, dict[str, Any]] = {}
    for option in FIELD_MAP:
        if before.get(option) != after.get(option):
            diff[option] = {"before": before.get(option), "after": after.get(option)}
    return diff


# ── Desired-State Builders ────────────────────────────────────────────────────
# One builder per state. Each returns the complete ssh block that should end
# up on the device, which _apply_desired() then compares against the
# current block to decide whether a PATCH is needed.


def _desired_merged(current: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """MERGED - apply supplied field(s), leave the other field untouched."""
    desired = dict(current)
    for option in FIELD_MAP:
        if config.get(option) is not None:
            desired[option] = config[option]
    return desired


def _desired_replaced_overridden(config: dict[str, Any]) -> dict[str, Any]:
    """REPLACED / OVERRIDDEN - supplied fields are authoritative.

    Every field the user did not supply is reset to its factory default from
    FULL_DEFAULTS. Identical for both states because ssh is a singleton
    object with no listed/unlisted sub-resources to reconcile.
    """
    desired = dict(FULL_DEFAULTS)
    for option in FIELD_MAP:
        if config.get(option) is not None:
            desired[option] = config[option]
    return desired


def _desired_deleted(current: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """DELETED - reset to factory defaults.

    Without a config, both fields return to DEFAULTS. A config with no option
    set (config: {}, which arrives with every suboption None) counts as
    omitted, as in Ansible resource modules and the other modules of the
    collection. With a config naming a field, only that field is
    reset; the rest keep their current value.
    """
    if not any(value is not None for value in (config or {}).values()):
        return dict(DEFAULTS)
    desired = dict(current)
    for option in FIELD_MAP:
        if config.get(option) is not None:
            desired[option] = DEFAULTS[option]
    return desired


def _build_desired(state: str, current: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to the desired-state builder for the requested state."""
    if state == STATE_MERGED:
        return _desired_merged(current, config)
    if state in (STATE_REPLACED, STATE_OVERRIDDEN):
        return _desired_replaced_overridden(config)
    return _desired_deleted(current, config)


# ── State Handlers ────────────────────────────────────────────────────────────
# Each handler fills ``result`` in place and returns without calling exit_json().


def _handle_gathered(current: dict[str, Any], result: dict[str, Any]) -> None:
    """GATHERED - read-only, return the current ssh flags.

    gathered is reusable configuration: re-applying one with an unknown flag
    filled in would reset it, so an incomplete read fails instead.
    """
    ansible_current = _to_ansible_output(current)
    missing = [option for option, value in ansible_current.items() if value is None]
    if missing:
        raise FeSshError(
            "The device did not report %s in the '%s' object of %s, so the ssh configuration cannot be gathered "
            "as reusable configuration"
            % (", ".join(FIELD_MAP[option] for option in missing), SSH_KEY, SYSTEM_SERVICES_PATH),
            details={"missing_fields": missing, "resource": SYSTEM_SERVICES_PATH},
        )
    result["ssh"] = {"config": ansible_current}
    result["gathered"] = ansible_current


def _patched_options(patch_payload: dict[str, Any]) -> list[str]:
    """Option names (enabled, global_enabled) carried by an ssh PATCH body, in FIELD_MAP order."""
    sent = patch_payload.get(SSH_KEY) or {}
    return [option for option, rest_key in FIELD_MAP.items() if rest_key in sent]


def _attribute_patch_failure(
    module: AnsibleModule,
    connection: Connection,
    patch_payload: dict[str, Any],
    before: dict[str, Any],
    exc: FeSshError,
) -> FeSshError:
    """Build the error for a failed ssh PATCH, naming the fields the device applied.

    The ssh object is re-read with the same GET the module uses elsewhere and
    each attempted field is compared with the value the device reports. The
    original message, details, code and err are kept and one attribution
    sentence is appended: applied_fields / not_applied_fields, or reread_error
    when the re-read failed too. changed is true only when the re-read shows a
    field applied (each attempted field differed from *before* by construction).

    The comparison uses the raw read-back, so a device answering 404, or with
    no ssh object or no such field, never makes a rejected PATCH look applied
    through a substituted default. A field the read-back omits (or reports as
    null) is listed in unknown_fields, never filled with a default, and the
    fields it does report are still attributed.
    """
    sent = patch_payload.get(SSH_KEY) or {}
    options = _patched_options(patch_payload)
    details: dict[str, Any] = dict(exc.details)
    details["attempted_payload"] = patch_payload
    lead = to_text(exc).rstrip().rstrip(".") + "."
    # A transport failure without an HTTP status (no answer): the device may have
    # applied the PATCH. An error document has no 'code' in extra, an HTTP error
    # a numeric one.
    no_answer = "code" in (exc.extra or {}) and is_answer_unknown_code(exc.extra["code"])
    try:
        raw = _fetch_ssh_config(module, connection)
        # A re-read that reports none of the attempted fields (no ssh object at
        # all, for example) attributes nothing: a failed re-read.
        if all(raw.get(FIELD_MAP[option]) is None for option in options):
            raise FeSshError("the device did not report %s in the re-read" % ", ".join(options))
    except FeSshError as reread_exc:
        # A generic text in every case: an error document's own message is never
        # copied (see _call_api()), and a transport failure on this path is
        # redacted by the HTTPAPI plugin.
        details["reread_error"] = to_text(reread_exc)
        reread_code = reread_exc.details.get("code", (reread_exc.extra or {}).get("code"))
        if isinstance(reread_code, int):
            details["reread_error_code"] = reread_code
        # Without an answer the PATCH may have been applied: changed is reported.
        if no_answer:
            details["outcome"] = "unknown"
        return FeSshError(
            "%s The ssh configuration could not be re-read to check which of the attempted field(s) (%s) the device "
            "applied (%s)." % (lead, ", ".join(options), to_text(reread_exc)),
            details=details,
            extra=exc.extra,
            changed=no_answer,
        )
    # Null establishes neither outcome, so it counts as omitted (unknown).
    unknown = [option for option in options if raw.get(FIELD_MAP[option]) is None]
    applied = [
        option for option in options if option not in unknown and raw[FIELD_MAP[option]] == sent[FIELD_MAP[option]]
    ]
    not_applied = [option for option in options if option not in unknown and option not in applied]
    details["applied_fields"] = applied
    details["not_applied_fields"] = not_applied
    sentence = "%s A re-read of the ssh configuration shows applied: %s; not applied: %s" % (
        lead,
        ", ".join(applied) or "none",
        ", ".join(not_applied) or "none",
    )
    if unknown:
        details["unknown_fields"] = unknown
        details["reread_error"] = "the device did not report %s in the re-read" % ", ".join(unknown)
        sentence += "; not reported by the re-read, so unknown: %s" % ", ".join(unknown)
    # Without an answer a field the re-read omits may have been applied: unknown,
    # and changed is reported.
    lost_unknown = no_answer and bool(unknown)
    if lost_unknown and not applied:
        details["outcome"] = "unknown"
    return FeSshError(sentence + ".", details=details, extra=exc.extra, changed=bool(applied) or lost_unknown)


def _apply_desired(
    module: AnsibleModule,
    connection: Connection,
    current: dict[str, Any],
    desired: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Send the desired ssh block to the device, but only when it differs.

    Only the field(s) that differ from the current value are sent in the
    PATCH body, nested under "ssh" - telnet, ftp, iqagent, webServer,
    cloudConnector and vxlanGwFullInterworkingMode are never part of the
    request.

    current and desired are already in Ansible format; converting them
    again would drop global_enabled, whose REST name differs.
    """
    before_ansible = dict(current)
    result["ssh"] = {"before": before_ansible}

    patch_payload = _build_patch_payload(current, desired)
    if not patch_payload:
        # Nothing to do - the device already holds the desired configuration
        result["ssh"]["after"] = before_ansible
        result["ssh"]["differences"] = {}
        return

    result["submitted"] = {"path": SYSTEM_SERVICES_PATH, "payload": patch_payload}

    if not module.check_mode:
        # PATCH only carries the "ssh" key and only the field(s) that changed
        try:
            _call_api(
                module,
                connection,
                method="PATCH",
                path=SYSTEM_SERVICES_PATH,
                payload=patch_payload,
                expect_content=False,  # the endpoint answers 204 No Content
            )
        except FeSshError as exc:
            raise _attribute_patch_failure(module, connection, patch_payload, current, exc)
        # Only now is the device known to be changed.
        result["changed"] = True
        # Re-read so the reported "after" is what the device really holds
        try:
            after_raw = _fetch_ssh_config(module, connection)
        except FeSshError as exc:
            raise FeSshError(
                "The SSH PATCH was applied (%s), but re-reading %s afterwards failed: %s"
                % (", ".join(_patched_options(patch_payload)), SYSTEM_SERVICES_PATH, to_text(exc)),
                details=dict(exc.details, applied_fields=_patched_options(patch_payload)),
                extra=exc.extra,
                changed=True,
            )
        result["ssh"]["after"] = _to_ansible_output(after_raw)
    else:
        # Check mode - report the state that would have been written
        result["changed"] = True
        result["ssh"]["after"] = dict(desired)

    result["ssh"]["differences"] = _compute_diff(before_ansible, result["ssh"]["after"])


# ── Main Entry Point ─────────────────────────────────────────────────────────
# This is where the module logic starts. The function:
# 1. Creates the AnsibleModule (validates user input against ARGUMENT_SPEC)
# 2. Connects to the device via httpapi
# 3. Reads the current System Services config from the device (ssh object only)
# 4. Builds the desired ssh block for the requested state and PATCHes it if needed
# 5. Returns results with changed=true/false and before/after config


def run_module() -> None:
    # supports_check_mode=True means this module can simulate changes
    # without actually modifying the device (--check flag in ansible-playbook)
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    # Establish connection to the device via the httpapi plugin
    try:
        connection = _get_connection(module)
    except FeSshError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    # Initialize the result dict - this is what gets returned to the user
    result: dict[str, Any] = {
        "changed": False,  # Will be set to True if we modify anything
    }

    try:
        state = module.params["state"]  # Which operation to perform
        config = module.params.get("config") or {}  # User's desired ssh flags

        # merged/replaced/overridden need something to work with. Without
        # this guard, 'overridden' with no config would silently reset both
        # SSH flags. Ansible fills omitted suboptions with None, so even
        # config: {} arrives as a non-empty dict - count only non-null fields.
        supplied = {key: value for key, value in config.items() if value is not None}
        if state in REQUIRES_CONFIG and not supplied:
            raise FeSshError("value of config parameter must not be empty for state {0}".format(state))

        # ── GET the current System Services configuration (ssh only) ─────
        # Always read first: it provides the "before" output and the
        # baseline every state folds the user's config into. Every other
        # System Services field is discarded inside _fetch_ssh_config().
        current = _fetch_ssh_config(module, connection)

        # ── Read-only path returns early ─────────────────────────────
        if state == STATE_GATHERED:
            _handle_gathered(current, result)
            module.exit_json(**result)
            return

        # ── Build and apply the desired configuration ────────────────
        before_ansible = _to_ansible_output(current)
        result["before"] = before_ansible
        desired = _build_desired(state, before_ansible, config)
        _apply_desired(module, connection, before_ansible, desired, result)
        # Top-level "after" is returned for every action state: the re-read
        # state after a change, the prediction in check mode, and the
        # unchanged "before" when nothing had to be written.
        result["after"] = result["ssh"]["after"]

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
    # 1. FeSshError - our own validation or logic errors
    # 2. ConnectionError - device communication failures
    except FeSshError as exc:
        module.fail_json(changed=bool(result.get("changed")) or exc.changed, **exc.to_fail_kwargs())
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
