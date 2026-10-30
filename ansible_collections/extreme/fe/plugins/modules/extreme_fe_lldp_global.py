# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to manage global LLDP settings on Fabric Engine switches.

REST endpoints used:
  GET   /v0/configuration/lldp
  PATCH /v0/configuration/lldp
  GET   /v0/state/lldp
"""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_lldp_global
short_description: Manage global LLDP settings on ExtremeNetworks Fabric Engine switches
version_added: "1.1.0"
description:
  - Manage device-wide LLDP timer settings on ExtremeNetworks Fabric Engine switches using the custom
    C(extreme_fe) HTTPAPI plugin.
  - Uses C(/v0/configuration/lldp) from the NOS OpenAPI schema.
  - C(init_delay_seconds) is returned in C(lldp.config), C(lldp.before) and C(lldp.after) when present on
    the device, but it is not configurable on Fabric Engine.
author:
  - Bjorn Haas (@bhaas_extr)
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
  - A PATCH that fails without an answer (a lost connection) and cannot be re-read, or whose re-read omits
    an attempted timer, may have been applied, so the task reports C(changed=true); with no timer confirmed
    applied, C(details.outcome=unknown).
  - This module manages the singleton global LLDP resource only. It does not manage per-port LLDP settings.
  - C(overridden) is functionally equivalent to C(replaced) because the LLDP global configuration is a singleton object.
  - C(deleted) resets supplied attributes to device defaults. If C(config) is omitted with C(state=deleted),
    all configurable global LLDP attributes are reset.
  - Supports check mode and diff mode. The top-level C(before) and C(after) keys hold the configurable LLDP
    global settings; in check mode C(after) is the predicted configuration, and when nothing changes it equals
    C(before).
  - C(state=gathered) returns the configurable settings under C(gathered) in the shape of C(config), so the value
    can be fed straight back as C(config) into a C(merged), C(replaced) or C(overridden) task, which then reports
    no change. The read-only C(init_delay_seconds) is left out of it. The gather fails when the device does not
    report one of the two timers (absent or null), since re-applying a configuration without it would reset it.
  - Both timers are sent in one PATCH. If the device rejects it, the module re-reads the LLDP configuration
    and reports in C(details.applied_fields) and C(details.not_applied_fields) which REST fields the device
    applied, together with C(details.attempted_payload), C(details.status_code) and C(details.resource); the
    task then reports C(changed=true) if any field was applied. If the re-read fails too,
    C(details.reread_error) says why and nothing is attributed. A re-read that does not report an attempted
    field (or reports it as null) lists it in C(details.unknown_fields), without assuming a default, and
    still attributes the fields it reports (one that reports none of them counts as a failed re-read).
requirements:
  - ansible.netcommon
options:
  config:
    description:
      - Structured LLDP global settings to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden), with at least one suboption set; an
        empty C(config) fails the task before any request.
      - Optional when C(state=deleted); if omitted or empty, all configurable LLDP global settings are reset to
        defaults.
    type: dict
    suboptions:
      advertisement_interval:
        description:
          - The interval in seconds at which LLDP frames are transmitted.
          - Maps to C(advertisementInterval).
        type: int
      hold_multiplier:
        description:
          - Multiplier applied to C(advertisement_interval) to determine neighbor time-to-live.
          - Maps to C(holdMultiplier).
        type: int
  gather_state:
    description:
      - When true, include LLDP operational state from C(/v0/state/lldp) in the module result.
    type: bool
    default: false
  state:
    description:
      - Desired module operation.
      - C(merged) incrementally applies only the supplied LLDP global attributes.
      - C(replaced) treats configurable LLDP global attributes as authoritative and resets omitted
        configurable attributes to defaults.
      - C(overridden) behaves like C(replaced) for this singleton resource.
      - C(deleted) resets the supplied attributes, or all configurable attributes when C(config) is omitted or
        empty.
      - C(gathered) returns the current LLDP global configuration without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
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
#
# Prerequisites:
#
# ## Enable REST API on the switch and use the extreme_fe httpapi plugin.
# ## Verify current LLDP global settings:
# # show lldp config
# # show lldp info

# -------------------------------------------------------------------------
# Task 1: Merge a single LLDP global timer
# Description:
#   - Non-destructively update the advertisement timer.
# -------------------------------------------------------------------------
# - name: "Task 1: Merge LLDP advertisement timer"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Set LLDP advertisement interval to 20 seconds
  extreme.fe.extreme_fe_lldp_global:
    state: merged
    config:
      advertisement_interval: 20

# -------------------------------------------------------------------------
# Task 2: Replace the full configurable LLDP global profile
# Description:
#   - Enforce all configurable Fabric Engine LLDP global values.
# -------------------------------------------------------------------------
# - name: "Task 2: Replace LLDP global timers"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce the desired LLDP global timer profile
  extreme.fe.extreme_fe_lldp_global:
    state: replaced
    config:
      advertisement_interval: 15
      hold_multiplier: 4

# -------------------------------------------------------------------------
# Task 3: Override LLDP global configuration
# Description:
#   - Equivalent to replaced for this singleton resource.
# -------------------------------------------------------------------------
# - name: "Task 3: Override LLDP global configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Override LLDP global settings
  extreme.fe.extreme_fe_lldp_global:
    state: overridden
    config:
      advertisement_interval: 30
      hold_multiplier: 6

# -------------------------------------------------------------------------
# Task 4: Reset LLDP global settings to defaults
# Description:
#   - Reset all configurable global LLDP attributes to NOS defaults.
# -------------------------------------------------------------------------
# - name: "Task 4: Reset LLDP global settings"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Restore LLDP global defaults
  extreme.fe.extreme_fe_lldp_global:
    state: deleted

# -------------------------------------------------------------------------
# Task 5: Gather LLDP global configuration and operational state
# Description:
#   - Read current config and LLDP neighbor state.
# -------------------------------------------------------------------------
# - name: "Task 5: Gather LLDP global information"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect LLDP global configuration and state
  extreme.fe.extreme_fe_lldp_global:
    state: gathered
    gather_state: true
  register: lldp_global_info
"""

RETURN = r"""
---
changed:
  description: Indicates whether any configuration changes were made.
  returned: always
  type: bool
before:
  description:
    - Configurable LLDP global settings read before any requested change, in the shape of C(config).
    - The read-only C(init_delay_seconds) is not included; it is in C(lldp.before).
  returned: when state is not gathered
  type: dict
  sample: {"advertisement_interval": 30, "hold_multiplier": 4}
after:
  description:
    - Configurable LLDP global settings read back after the change, in the shape of C(config).
    - In check mode, the predicted configuration.
    - Equal to C(before) when nothing changed.
  returned: when state is not gathered
  type: dict
  sample: {"advertisement_interval": 20, "hold_multiplier": 4}
gathered:
  description:
    - Current configurable LLDP global settings in the shape of C(config), so the value can be supplied back as
      C(config).
    - The read-only C(init_delay_seconds) is not included; it is in C(lldp.config).
    - Always holds both timers; the gather fails when the device does not report one of them.
  returned: when state == gathered
  type: dict
  sample: {"advertisement_interval": 30, "hold_multiplier": 4}
lldp:
  description: LLDP global configuration details.
  returned: always
  type: dict
  contains:
    before:
      description:
        - LLDP global configuration before any requested change, including C(init_delay_seconds) when the device
          reports it.
        - The top-level C(before) holds the configurable subset.
      returned: when state != gathered
      type: dict
    after:
      description:
        - LLDP global configuration after the requested change, including C(init_delay_seconds) when the device
          reports it.
        - The top-level C(after) holds the configurable subset.
      returned: when state != gathered
      type: dict
    config:
      description:
        - Current LLDP global configuration in gathered mode, including C(init_delay_seconds) when the device reports
          it.
        - Use the top-level C(gathered) to feed the configuration back as C(config).
      returned: when state == gathered
      type: dict
    differences:
      description: Changed configurable attributes with before and after values.
      returned: when state != gathered
      type: dict
    state:
      description: Raw LLDP operational state returned by C(/v0/state/lldp).
      returned: when gather_state is true
      type: dict
submitted:
  description: Payload submitted to the device when a change was required.
  returned: when state != gathered and a change was required
  type: dict
api_responses:
  description:
    - Raw API responses captured from the device for GET, PATCH, and optional state calls, for debugging.
    - Deprecated and will be removed in 2.0.0.
    - Use C(lldp.before) and C(lldp.after) for the configuration before and after a change,
      C(gathered) or C(lldp.config) for C(state=gathered), and C(lldp.state) for the operational state returned
      when C(gather_state=true).
  returned: always
  type: dict
"""

from typing import Any

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown, http_status

ARGUMENT_SPEC = {
    "config": {
        "type": "dict",
        "options": {
            "advertisement_interval": {"type": "int"},
            "hold_multiplier": {"type": "int"},
        },
    },
    "gather_state": {"type": "bool", "default": False},
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

CONFIG_PATH = "/v0/configuration/lldp"
STATE_PATH = "/v0/state/lldp"

SETTABLE_FIELDS = {
    "advertisement_interval": {
        "rest": "advertisementInterval",
        "default": 30,
        "minimum": 5,
        "maximum": 32768,
    },
    "hold_multiplier": {
        "rest": "holdMultiplier",
        "default": 4,
        "minimum": 2,
        "maximum": 10,
    },
}

READ_ONLY_FIELDS = {
    "init_delay_seconds": "initDelaySeconds",
}

REQUIRES_CONFIG = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}


class FeLldpGlobalError(Exception):
    """Raised for LLDP global module validation or response issues."""

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
        # Top-level fail_json keys (e.g. the 'code'/'err' of a ConnectionError).
        self.extra = extra or {}
        self.changed = changed

    def to_fail_kwargs(self) -> dict[str, Any]:
        data: dict[str, Any] = dict(self.extra)
        data["msg"] = to_text(self)
        if self.details:
            data["details"] = self.details
        if self.changed:
            data["changed"] = True
        return data


def _extract_error(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)

    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    errors = payload.get("errors")

    if isinstance(code, int) and code >= 400:
        return {
            "code": code,
            "message": message or "Device reported an LLDP error",
            "payload": payload,
        }
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported LLDP errors",
            "errors": errors,
            "payload": payload,
        }
    return None


def _get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeLldpGlobalError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def _call_api(
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: dict[str, Any],
    response_key: str,
    payload: Any | None = None,
    expect_content: bool = True,
) -> Any:
    """Send one request; a ConnectionError propagates, an error body raises FeLldpGlobalError."""
    response = connection.send_request(payload, path=path, method=method)

    if isinstance(response, bytes):
        response = to_text(response)

    api_responses[response_key] = response

    if response in (None, ""):
        return None if not expect_content else {}

    if isinstance(response, dict):
        error = _extract_error(response)
        if error:
            # message can be missing or non-text (a nested object); never raise with msg None.
            message = to_text(error["message"]) if error.get("message") else ""
            if not message:
                code = error.get("code")
                message = "Device rejected %s %s%s" % (method, path, " (code %s)" % code if code else "")
            raise FeLldpGlobalError(message, details=error)

    return response


# -- PATCH Failure Attribution ------------------------------------------------


def _reread_error_document(document: Any) -> str | None:
    """Return a short description when a re-read answered with an error document, else None."""
    if not isinstance(document, dict):
        return None
    status = document.get("statusCode", document.get("code"))
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    errors = document.get("errors")
    is_error = bool(document.get("errorCode")) or (isinstance(status, int) and status >= 400)
    if not (is_error or (isinstance(errors, list) and errors)):
        return None
    text = document.get("errorMessage") or document.get("message") or document.get("detail")
    code = document.get("errorCode") or status
    return "%s%s" % ("%s: " % code if code else "", text or "no message")


def _extend_msg(msg: str, suffix: str) -> str:
    """Append a sentence to an error message, adding the full stop it may lack."""
    msg = (msg or "").rstrip()
    return "%s %s" % (msg if msg.endswith((".", "!", "?")) else msg + ".", suffix)


def _attribute_patch_failure(
    connection: Connection, payload: dict[str, Any], exc: ConnectionError | FeLldpGlobalError
) -> FeLldpGlobalError:
    """Build the error for a rejected LLDP PATCH, naming the fields the device applied.

    The LLDP configuration is re-read with the module's GET and every payload
    field is compared with the read-back value. changed is True only when the
    re-read shows a field applied (the payload holds changed fields only). A
    field the re-read omits (or reports as null) is listed in unknown_fields,
    never filled with a default, and the reported fields are still attributed.
    """
    fields = list(payload)
    details: dict[str, Any] = dict(exc.details) if isinstance(exc, FeLldpGlobalError) else {}
    details.update({"attempted_payload": dict(payload), "resource": CONFIG_PATH})
    # Only an HTTP status (100-599) is reported: a negative JSON-RPC code (a lost answer) is not one.
    status_code = http_status(getattr(exc, "code", None))
    if status_code is None:
        status_code = http_status(details.get("code"))
    if status_code is not None:
        details["status_code"] = status_code
    extra = (
        {"code": getattr(exc, "code", None), "err": getattr(exc, "err", None)}
        if isinstance(exc, ConnectionError)
        else {}
    )

    # A transport failure without an HTTP status (no answer): the PATCH may have
    # been applied.
    no_answer = isinstance(exc, ConnectionError) and answer_unknown(exc)
    reread_error = None
    try:
        record = connection.send_request(None, path=CONFIG_PATH, method="GET")
    except ConnectionError as reread_exc:
        record = None
        reread_error = to_text(reread_exc)
    else:
        embedded = _reread_error_document(record)
        if embedded:
            record = None
            reread_error = "the re-read of %s returned an error document (%s)" % (CONFIG_PATH, embedded)
        elif not isinstance(record, dict) or not record:
            record = None
            reread_error = "the device returned no configuration for %s" % CONFIG_PATH
        elif all(record.get(field) is None for field in fields):
            # Reports none of the attempted timers: nothing can be attributed.
            record = None
            reread_error = "the re-read of %s did not report %s" % (CONFIG_PATH, ", ".join(fields))
    if record is None:
        details["reread_error"] = reread_error
        suffix = (
            "The device may have applied part of the PATCH of %s before refusing it, but re-reading the "
            "resource failed (%s), so it is unknown which of the %d attempted fields (%s) were applied."
            % (CONFIG_PATH, reread_error, len(fields), ", ".join(fields))
        )
        # Without an answer the PATCH may have been applied: changed is reported.
        if no_answer:
            details["outcome"] = "unknown"
        return FeLldpGlobalError(_extend_msg(to_text(exc), suffix), details=details, extra=extra, changed=no_answer)

    # An attempted timer the re-read omits or reports as null is established
    # neither way: unknown, without discarding what the other fields confirm.
    unknown = [field for field in fields if record.get(field) is None]
    applied = [field for field in fields if field not in unknown and record[field] == payload[field]]
    not_applied = [field for field in fields if field not in unknown and field not in applied]
    details["applied_fields"] = applied
    details["not_applied_fields"] = not_applied
    if unknown:
        details["unknown_fields"] = unknown
        details["reread_error"] = "the re-read of %s did not report %s" % (CONFIG_PATH, ", ".join(unknown))
    if unknown:
        parts = ["applied: %s" % ", ".join(applied)] if applied else []
        if not_applied:
            parts.append("not applied: %s" % ", ".join(not_applied))
        parts.append("not reported by the re-read, so unknown: %s" % ", ".join(unknown))
        suffix = "The device rejected the PATCH of %s; a re-read of the %d attempted fields shows %s." % (
            CONFIG_PATH,
            len(fields),
            "; ".join(parts),
        )
    elif not applied:
        suffix = "A re-read of %s shows none of the %d attempted fields was applied: %s." % (
            CONFIG_PATH,
            len(fields),
            ", ".join(not_applied),
        )
    elif not not_applied:
        suffix = "The device rejected the PATCH of %s, but a re-read shows all %d fields applied: %s." % (
            CONFIG_PATH,
            len(fields),
            ", ".join(applied),
        )
    else:
        suffix = "The device rejected the PATCH of %s after applying %d of %d fields: %s; not applied: %s." % (
            CONFIG_PATH,
            len(applied),
            len(fields),
            ", ".join(applied),
            ", ".join(not_applied),
        )
    # Without an answer a timer the re-read omits may have been applied: unknown,
    # and changed is reported.
    lost_unknown = no_answer and bool(unknown)
    if lost_unknown and not applied:
        details["outcome"] = "unknown"
    return FeLldpGlobalError(
        _extend_msg(to_text(exc), suffix), details=details, extra=extra, changed=bool(applied) or lost_unknown
    )


def _patch_config(connection: Connection, payload: dict[str, Any], api_responses: dict[str, Any]) -> None:
    """PATCH /v0/configuration/lldp; on a rejection, fail with an attributed error."""
    try:
        _call_api(
            connection,
            method="PATCH",
            path=CONFIG_PATH,
            payload=payload,
            expect_content=False,
            api_responses=api_responses,
            response_key="patch",
        )
    except (ConnectionError, FeLldpGlobalError) as exc:
        raise _attribute_patch_failure(connection, payload, exc) from exc


def _normalize_config_response(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise FeLldpGlobalError(
            "Unexpected response when retrieving LLDP global configuration",
            details={"payload": payload},
        )

    normalized: dict[str, Any] = {}
    for option, meta in SETTABLE_FIELDS.items():
        rest_key = meta["rest"]
        if rest_key in payload:
            normalized[option] = payload.get(rest_key)
    for option, rest_key in READ_ONLY_FIELDS.items():
        if rest_key in payload:
            normalized[option] = payload.get(rest_key)
    return normalized


def _config_view(normalized: dict[str, Any]) -> dict[str, Any]:
    """Return the configurable subset of a normalized response, in the shape of the 'config' option.

    Read-only fields such as init_delay_seconds are dropped, so the value can be
    fed back as 'config' (it is used for 'gathered' and the top-level
    'before'/'after'). 'lldp.config', 'lldp.before' and 'lldp.after' keep them.
    """
    return {key: value for key, value in normalized.items() if key in SETTABLE_FIELDS}


def _require_complete_gather(normalized: dict[str, Any]) -> None:
    """Fail a gather whose configuration lacks a settable timer (absent or null).

    'gathered' is published as reusable configuration: re-applying an incomplete
    one with replaced or overridden would reset the missing timer to its
    default although its current value is unknown. The API schema's defaults
    describe omitted input, not an omitted response field, so a missing timer
    is not filled in. (The failure-attribution re-read stays raw and lists such
    a field as unknown.)
    """
    missing = [option for option in SETTABLE_FIELDS if normalized.get(option) is None]
    if missing:
        raise FeLldpGlobalError(
            "The device did not report %s in %s, so the LLDP global configuration cannot be gathered as "
            "reusable configuration" % (", ".join(SETTABLE_FIELDS[option]["rest"] for option in missing), CONFIG_PATH),
            details={"missing_fields": missing, "resource": CONFIG_PATH},
        )


def _validate_config(config: dict[str, Any] | None, state: str) -> dict[str, Any]:
    # Ansible fills every omitted suboption with None, so 'config: {}' arrives as a dict
    # of None values. Drop them: such a config is empty (deleted then resets everything).
    normalized = {key: value for key, value in (config or {}).items() if value is not None}

    if state in REQUIRES_CONFIG and config is None:
        raise FeLldpGlobalError("value of config parameter must not be empty for state %s" % state)

    if state in REQUIRES_CONFIG and not normalized:
        raise FeLldpGlobalError("value of config parameter must not be empty for state %s" % state)

    for option, meta in SETTABLE_FIELDS.items():
        if option not in normalized or normalized.get(option) is None:
            continue
        value = normalized.get(option)
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise FeLldpGlobalError(
                f"{option} must be an integer",
                details={"option": option, "received": normalized.get(option)},
            )
        if value < meta["minimum"] or value > meta["maximum"]:
            raise FeLldpGlobalError(
                "{0} must be between {1} and {2}".format(option, meta["minimum"], meta["maximum"]),
                details={"option": option, "received": value},
            )
        normalized[option] = value

    unknown_keys = sorted(key for key in normalized if key not in SETTABLE_FIELDS)
    if unknown_keys:
        raise FeLldpGlobalError(
            "Unsupported LLDP global attributes were supplied",
            details={"unsupported": unknown_keys},
        )

    return normalized


def _build_target_config(current: dict[str, Any], config: dict[str, Any], state: str) -> dict[str, Any]:
    if state == STATE_MERGED:
        return {key: value for key, value in config.items() if key in SETTABLE_FIELDS and value is not None}

    if state in (STATE_REPLACED, STATE_OVERRIDDEN):
        target = {key: meta["default"] for key, meta in SETTABLE_FIELDS.items()}
        for key, value in config.items():
            if key in SETTABLE_FIELDS and value is not None:
                target[key] = value
        return target

    if state == STATE_DELETED:
        if config:
            return {
                key: SETTABLE_FIELDS[key]["default"]
                for key, value in config.items()
                if key in SETTABLE_FIELDS and value is not None
            }
        return {key: meta["default"] for key, meta in SETTABLE_FIELDS.items()}

    if state == STATE_GATHERED:
        return current

    raise FeLldpGlobalError("Unsupported state '%s'" % state, details={"state": state})


def _build_patch_payload(current: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for option, desired_value in target.items():
        if option not in SETTABLE_FIELDS:
            continue
        if current.get(option) != desired_value:
            payload[SETTABLE_FIELDS[option]["rest"]] = desired_value
    return payload


def _build_differences(current: dict[str, Any], target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    differences: dict[str, dict[str, Any]] = {}
    for option, desired_value in target.items():
        if option not in SETTABLE_FIELDS:
            continue
        before_value = current.get(option)
        if before_value != desired_value:
            differences[option] = {"before": before_value, "after": desired_value}
    return differences


def _merge_after(current: dict[str, Any], patch_payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for option, meta in SETTABLE_FIELDS.items():
        rest_key = meta["rest"]
        if rest_key in patch_payload:
            merged[option] = patch_payload[rest_key]
    return merged


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    try:
        connection = _get_connection(module)
    except FeLldpGlobalError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    result: dict[str, Any] = {
        "changed": False,
        "api_responses": {},
    }

    try:
        state = module.params.get("state")
        gather_state = bool(module.params.get("gather_state"))
        requested_config = _validate_config(module.params.get("config"), state)

        current_raw = _call_api(
            connection,
            method="GET",
            path=CONFIG_PATH,
            api_responses=result["api_responses"],
            response_key="configuration_before",
        )
        current_config = _normalize_config_response(current_raw)

        if state == STATE_GATHERED:
            _require_complete_gather(current_config)
            result["lldp"] = {"config": current_config}
            # Standard key, in the 'config' shape so it can be fed straight back.
            result["gathered"] = _config_view(current_config)
            if gather_state:
                result["lldp"]["state"] = (
                    _call_api(
                        connection,
                        method="GET",
                        path=STATE_PATH,
                        api_responses=result["api_responses"],
                        response_key="state",
                    )
                    or {}
                )
            module.exit_json(**result)

        target_config = _build_target_config(current_config, requested_config, state)
        differences = _build_differences(current_config, target_config)
        patch_payload = _build_patch_payload(current_config, target_config)

        result["lldp"] = {
            "before": current_config,
            "after": current_config,
            "differences": differences,
        }

        if patch_payload:
            result["submitted"] = {
                "operation": state,
                "path": CONFIG_PATH,
                "payload": patch_payload,
            }

            if module.check_mode:
                result["lldp"]["after"] = _merge_after(current_config, patch_payload)
            else:
                _patch_config(connection, patch_payload, result["api_responses"])
            result["changed"] = True
            if not module.check_mode:
                after_raw = _call_api(
                    connection,
                    method="GET",
                    path=CONFIG_PATH,
                    api_responses=result["api_responses"],
                    response_key="configuration_after",
                )
                result["lldp"]["after"] = _normalize_config_response(after_raw)
        else:
            result["api_responses"]["patch"] = None

        # Full snapshots in the 'config' shape: 'after' is the read-back
        # (predicted in check mode) and equals 'before' when nothing changed.
        result["before"] = _config_view(result["lldp"]["before"])
        result["after"] = _config_view(result["lldp"]["after"])
        if module._diff:
            result["diff"] = {"before": result["before"], "after": result["after"]}

        if gather_state:
            result["lldp"]["state"] = (
                _call_api(
                    connection,
                    method="GET",
                    path=STATE_PATH,
                    api_responses=result["api_responses"],
                    response_key="state",
                )
                or {}
            )

        module.exit_json(**result)
    except FeLldpGlobalError as exc:
        kwargs = exc.to_fail_kwargs()
        # A failure after a successful PATCH (re-read or state GET) still changed the device.
        kwargs["changed"] = bool(kwargs.get("changed") or result["changed"])
        module.fail_json(api_responses=result.get("api_responses", {}), **kwargs)
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=result.get("api_responses", {}),
            changed=result["changed"],
        )


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
