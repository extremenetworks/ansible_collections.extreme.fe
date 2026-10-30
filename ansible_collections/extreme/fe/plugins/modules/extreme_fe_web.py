# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Manage the VOSS web-server service through the System Services REST API.

REST endpoints used:
  GET   /v0/configuration/system-services
  PATCH /v0/configuration/system-services

Only webServer.enabled and webServer.secureOnly are managed by this module.
"""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_web
short_description: Manage the web-server service on Extreme Fabric Engine devices
version_added: "1.3.0"
description:
  - Manages the web-server service on ExtremeNetworks Fabric Engine devices through
    the System Services REST API.
  - The initial implementation supports only C(enabled) and C(secure_only).
  - Other web-server attributes exposed by the API are intentionally preserved.
author:
    - Vlad-Leonard Mocanu (@vmocanu_extr)
requirements:
  - ansible.netcommon
notes:
  - Tested against Fabric Engine Version 9.3.2. The C(secure_only) factory default is based on reports from Fabric
    Engine 9.4 and 9.5 and has not been tested there.
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI connection plugin.
  - This collection talks to the switch through its web server. Disabling the web server, or turning on
    C(secure_only) while you connect over plain HTTP, can cut off the current task and every later one. C(deleted),
    C(replaced) and C(overridden) do this too when you leave out C(enabled) (default C(false)) or C(secure_only)
    (default C(true)). Keep another way to reach the switch before running such a task.
  - C(replaced) and C(overridden) are the same, because the web server settings are a single resource; both reset
    every setting you leave out to its factory default (C(enabled=false), C(secure_only=true)).
  - C(gathered) can be passed back as C(config) and changes nothing. If the switch does not report one of the two
    settings, C(gathered) fails instead of returning an incomplete result.
  - If the connection drops during a change (for example because the change disabled the web server) and the module
    cannot confirm the result, it reports C(changed=true) with C(details.outcome=unknown), because the change may have
    been applied.
  - If the switch rejects a change after applying part of it, the error message lists which settings were applied
    and which were not.
  - Supports check mode and diff mode.
options:
  config:
    description:
      - Web-server settings to manage.
      - Required for C(merged), C(replaced), and C(overridden).
      - Optional for C(deleted); when omitted, all supported attributes are reset.
    type: dict
    suboptions:
      enabled:
        description:
          - Whether the web-server service is enabled.
          - The confirmed VOSS factory default is C(false).
        type: bool
      secure_only:
        description:
          - Whether the web server accepts only secure HTTPS connections.
          - Maps to C(webServer.secureOnly) in the REST API.
          - The Fabric Engine factory default is C(true) (HTTPS only). C(deleted), and C(replaced) or
            C(overridden) without C(secure_only), set it to C(true).
        type: bool
  state:
    description:
      - C(merged) updates only supplied attributes.
      - C(replaced) resets omitted supported attributes to factory defaults.
      - C(overridden) enforces the complete supported singleton configuration and is
        therefore equivalent to C(replaced).
      - C(deleted) resets supplied attributes, or all supported attributes when
        C(config) is omitted.
      - C(gathered) returns only the supported current web-server configuration
        without modifying the device.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
"""

EXAMPLES = r"""
# - name: Configure the web-server service
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Enable the web server without changing secure-only mode
  extreme.fe.extreme_fe_web:
    state: merged
    config:
      enabled: true

- name: Replace the supported web-server configuration
  extreme.fe.extreme_fe_web:
    state: replaced
    config:
      enabled: true
      secure_only: true

- name: Enforce HTTPS-only web access and reset omitted supported settings
  extreme.fe.extreme_fe_web:
    state: overridden
    config:
      secure_only: true

- name: Reset only secure-only mode to its factory default (HTTPS only)
  extreme.fe.extreme_fe_web:
    state: deleted
    config:
      secure_only: true

- name: Reset all supported web-server settings
  extreme.fe.extreme_fe_web:
    state: deleted

- name: Gather web-server configuration
  extreme.fe.extreme_fe_web:
    state: gathered
  register: web_server_info
"""

RETURN = r"""
---
changed: {
    description: Indicates whether configuration was or would be changed.,
    returned: always,
    type: bool
}
before: {
    description: Web-server configuration before action-state processing.,
    returned: when state is not gathered,
    type: dict
}
after: {
    description: [
        Actual or predicted post-change configuration.,
        Current configuration when unchanged.
    ],
    returned: when state is not gathered,
    type: dict
}
gathered: {
    description: [
        Current supported web-server configuration in the config option shape.,
        Always contains enabled and secure_only; the gather fails when the device does not report one of them.
    ],
    returned: when state is gathered,
    type: dict
}
web: {
    description: Web-server configuration details.,
    returned: always,
    type: dict,
    contains: {
        config: {
            description: Current web-server configuration.,
            returned: when state is gathered,
            type: dict
        },
        before: {
            description: Same value as top-level before.,
            returned: when state is not gathered,
            type: dict
        },
        after: {
            description: Same value as top-level after.,
            returned: when state is not gathered,
            type: dict
        },
        differences: {
            description: [
                Changed supported attributes.,
                Empty dictionary when unchanged.
            ],
            returned: when state is not gathered,
            type: dict
        }
    }
}
"""

from typing import Any

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown, http_status

CONFIG_PATH = "/v0/configuration/system-services"

FIELD_MAP = {
    "enabled": "enabled",
    "secure_only": "secureOnly",
}

# Factory defaults (not in the OpenAPI schema). secure_only is True: Fabric
# Engine shows only non-default settings in its running configuration, and
# secureOnly true has no line there while false shows "no web-server
# secure-only"; "show web-server" reports "Secure-only : enabled" at factory
# settings (9.4 and 9.5). A reset to False disabled HTTPS-only mode.
FULL_DEFAULTS = {
    "enabled": False,
    "secure_only": True,
}
DEFAULTS = dict(FULL_DEFAULTS)

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"
REQUIRES_CONFIG = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}

ARGUMENT_SPEC = {
    "config": {
        "type": "dict",
        "options": {
            "enabled": {"type": "bool"},
            "secure_only": {"type": "bool"},
        },
    },
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


class FeWebError(Exception):
    """Raised for web-server validation or REST response errors."""

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
            "message": message or "Device reported a web-server error",
            "payload": payload,
        }
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported web-server errors",
            "errors": errors,
            "payload": payload,
        }
    return None


def _get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeWebError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def _call_api(
    connection: Connection,
    *,
    method: str,
    path: str,
    payload: Any | None = None,
    expect_content: bool = True,
) -> Any:
    response = connection.send_request(payload, path=path, method=method)

    if isinstance(response, bytes):
        response = to_text(response)

    if response in (None, ""):
        return None if not expect_content else {}
    error = _extract_error(response)
    if error:
        # An error document in a 2xx answer bypasses the HTTPAPI sanitizer, and its
        # free-form text or payload could quote a stored web-server or proxy
        # credential of system-services, so only its numeric code is kept, for the
        # GET and the PATCH alike.
        code = error.get("code")
        raise FeWebError(
            "The device answered %s %s with an error document%s; its message is not shown, as it may quote a "
            "stored credential" % (method, path, " (error code %d)" % code if isinstance(code, int) else ""),
            details={"code": code} if isinstance(code, int) else {},
        )
    return response


# -- PATCH Failure Attribution ------------------------------------------------


def _reread_error_document(document: Any) -> tuple[bool, int | None]:
    """Return (is an error document, its numeric code or None) for a re-read answer.

    The device's own message is never returned: it could quote a stored
    web-server or proxy credential, and the HTTPAPI sanitizer only handles HTTP
    errors and 207 answers, not an error document in an HTTP 200.
    """
    if not isinstance(document, dict):
        return False, None
    status = document.get("statusCode", document.get("code"))
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    errors = document.get("errors")
    is_error = bool(document.get("errorCode")) or (isinstance(status, int) and status >= 400)
    if not (is_error or (isinstance(errors, list) and errors)):
        return False, None
    code = document.get("errorCode") or status
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    return True, code if isinstance(code, int) else None


def _extend_msg(msg: str, suffix: str) -> str:
    """Append a sentence to an error message, adding the full stop it may lack."""
    msg = (msg or "").rstrip()
    return "%s %s" % (msg if msg.endswith((".", "!", "?")) else msg + ".", suffix)


def _attribute_patch_failure(
    connection: Connection, payload: dict[str, Any], exc: ConnectionError | FeWebError
) -> FeWebError:
    """Build the error for a rejected webServer PATCH, naming the fields the device applied.

    The system-services configuration is re-read with the module's GET and each
    webServer payload field is compared with the read-back value. changed is True
    only when the re-read shows a field applied (the payload holds changed fields
    only). A re-read that fails (for example because the PATCH disabled the web
    server) or answers with an error document attributes nothing; one that
    omits a field lists it in unknown_fields and still attributes the others.
    """
    web_payload = payload.get("webServer") or {}
    fields = ["webServer.%s" % key for key in web_payload]
    details: dict[str, Any] = dict(exc.details) if isinstance(exc, FeWebError) else {}
    details.update({"attempted_payload": payload, "resource": CONFIG_PATH})
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

    # A transport failure without an HTTP status (no answer; no code, or a
    # negative JSON-RPC code of the persistent connection): the PATCH may have
    # been applied, so a field the re-read cannot establish counts as a change.
    no_answer = isinstance(exc, ConnectionError) and answer_unknown(exc)
    reread_error = None
    reread_code = None
    web_server = None
    try:
        record = connection.send_request(None, path=CONFIG_PATH, method="GET")
    except ConnectionError as reread_exc:
        # The HTTPAPI plugin redacts a failed GET of this path.
        reread_error = to_text(reread_exc)
        reread_code = http_status(getattr(reread_exc, "code", None))
    else:
        is_error_document, reread_code = _reread_error_document(record)
        if is_error_document:
            reread_error = "the re-read of %s returned an error document%s" % (
                CONFIG_PATH,
                " (error code %d)" % reread_code if reread_code is not None else "",
            )
        elif not isinstance(record, dict) or not isinstance(record.get("webServer"), dict):
            reread_error = "the device returned no webServer configuration for %s" % CONFIG_PATH
        elif all(record["webServer"].get(key) is None for key in web_payload):
            # Reports none of the attempted fields: nothing can be attributed.
            reread_error = "the re-read of %s did not report %s" % (CONFIG_PATH, ", ".join(fields))
        else:
            web_server = record["webServer"]
    if web_server is None:
        details["reread_error"] = reread_error
        if isinstance(reread_code, int):
            details["reread_error_code"] = reread_code
        suffix = (
            "The device may have applied part of the PATCH of %s before refusing it, but re-reading the "
            "resource failed (%s), so it is unknown which of the %d attempted fields (%s) were applied."
            % (CONFIG_PATH, reread_error, len(fields), ", ".join(fields))
        )
        # Without an answer the PATCH may have been applied (disabling the web
        # server can cut the session before the answer arrives): report changed.
        if no_answer:
            details["outcome"] = "unknown"
        return FeWebError(_extend_msg(to_text(exc), suffix), details=details, extra=extra, changed=no_answer)

    # Each field the re-read reports is compared on its own. One it omits (or
    # reports as null) is established neither way: it is listed as unknown,
    # never filled with a default, and does not discard what the other fields
    # confirm.
    applied, not_applied, unknown = [], [], []
    for key, value in web_payload.items():
        field = "webServer.%s" % key
        current = web_server.get(key)
        if current is None:
            unknown.append(field)
        elif current == value:
            applied.append(field)
        else:
            not_applied.append(field)
    details["applied_fields"] = applied
    details["not_applied_fields"] = not_applied
    if unknown:
        details["unknown_fields"] = unknown
        details["reread_error"] = "the re-read of %s did not report %s" % (CONFIG_PATH, ", ".join(unknown))
        if no_answer:
            # A field the re-read omits may hide an applied write.
            details["outcome"] = "unknown"
    return FeWebError(
        _extend_msg(to_text(exc), _attribution_sentence(len(fields), applied, not_applied, unknown)),
        details=details,
        extra=extra,
        changed=bool(applied) or (no_answer and bool(unknown)),
    )


def _attribution_sentence(total: int, applied: list[str], not_applied: list[str], unknown: list[str]) -> str:
    """One sentence naming which attempted fields a re-read shows applied, not applied or unknown."""
    parts = []
    if applied:
        parts.append("applied: %s" % ", ".join(applied))
    if not_applied:
        parts.append("not applied: %s" % ", ".join(not_applied))
    if unknown:
        parts.append("not reported by the re-read, so unknown: %s" % ", ".join(unknown))
    lead = "The device rejected the PATCH of %s" % CONFIG_PATH
    if applied and not not_applied and not unknown:
        return "%s, but a re-read shows all %d fields applied: %s." % (lead, total, ", ".join(applied))
    if not applied and not unknown:
        return "A re-read of %s shows none of the %d attempted fields was applied: %s." % (
            CONFIG_PATH,
            total,
            ", ".join(not_applied),
        )
    return "%s; a re-read of the %d attempted fields shows %s." % (lead, total, "; ".join(parts))


def _patch_config(connection: Connection, payload: dict[str, Any]) -> None:
    """PATCH /v0/configuration/system-services; on a rejection, fail with an attributed error."""
    try:
        _call_api(connection, method="PATCH", path=CONFIG_PATH, payload=payload, expect_content=False)
    except (ConnectionError, FeWebError) as exc:
        raise _attribute_patch_failure(connection, payload, exc) from exc


def _normalize_config_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise FeWebError(
            "Unexpected response when retrieving system-services configuration",
            # Only the type: the body could carry stored web-server or proxy passwords.
            details={"response_type": type(payload).__name__},
        )

    web_server = payload.get("webServer", {})
    if not isinstance(web_server, dict):
        raise FeWebError(
            "The system-services response contains an invalid webServer object",
            details={"webServer": web_server},
        )

    # A key the device omits (or reports as null) stays None: its value is
    # unknown. It is never filled with a default, so a write still sends a
    # requested value for it (None differs from every value), and gathered
    # refuses to publish it (_handle_gathered()).
    return {option: web_server.get(rest_key) for option, rest_key in FIELD_MAP.items()}


def _validate_config(config: dict[str, Any] | None, state: str) -> dict[str, Any]:
    normalized = dict(config or {})
    unknown = sorted(set(normalized) - set(FIELD_MAP))
    if unknown:
        raise FeWebError(
            "Unsupported web-server attributes were supplied",
            details={"unsupported": unknown},
        )
    normalized = {key: value for key, value in normalized.items() if value is not None}
    if state in REQUIRES_CONFIG and not normalized:
        raise FeWebError("value of config parameter must not be empty for state {0}".format(state))
    return normalized


def _build_target(config: dict[str, Any], state: str) -> dict[str, Any]:
    if state == STATE_MERGED:
        return dict(config)
    if state in (STATE_REPLACED, STATE_OVERRIDDEN):
        target = dict(FULL_DEFAULTS)
        target.update(config)
        return target
    if state == STATE_DELETED:
        if config:
            return {key: DEFAULTS[key] for key in config}
        return dict(DEFAULTS)
    raise FeWebError("Unsupported state '%s'" % state, details={"state": state})


def _compute_diff(current: dict[str, Any], target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        option: {"before": current.get(option), "after": value}
        for option, value in target.items()
        if current.get(option) != value
    }


def _build_patch_payload(differences: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"webServer": {FIELD_MAP[option]: values["after"] for option, values in differences.items()}}


def _predicted_after(current: dict[str, Any], differences: dict[str, dict[str, Any]]) -> dict[str, Any]:
    predicted = dict(current)
    predicted.update({option: values["after"] for option, values in differences.items()})
    return predicted


def _handle_gathered(
    module: AnsibleModule,
    current: dict[str, Any],
    result: dict[str, Any],
) -> None:
    # gathered is reusable configuration: re-applying one with an unknown value
    # filled in would reset that setting, so an incomplete read fails instead.
    missing = [option for option, value in current.items() if value is None]
    if missing:
        raise FeWebError(
            "The device did not report %s in %s, so the web-server configuration cannot be gathered as "
            "reusable configuration"
            % (", ".join("webServer.%s" % FIELD_MAP[option] for option in missing), CONFIG_PATH),
            details={"missing_fields": missing, "resource": CONFIG_PATH},
        )
    result["gathered"] = current
    result["web"] = {"config": current}
    module.exit_json(**result)


def _apply_state(
    module: AnsibleModule,
    connection: Connection,
    current: dict[str, Any],
    config: dict[str, Any],
    state: str,
    result: dict[str, Any],
) -> None:
    target = _build_target(config, state)
    differences = _compute_diff(current, target)
    predicted = _predicted_after(current, differences)
    result["before"] = current
    after = dict(current)

    if differences:
        payload = _build_patch_payload(differences)
        if module.check_mode:
            result["changed"] = True
            after = predicted
        else:
            # A single PATCH carries both webServer fields; a rejection is attributed
            # by re-reading the resource.
            _patch_config(connection, payload)
            result["changed"] = True
            after_raw = _call_api(
                connection,
                method="GET",
                path=CONFIG_PATH,
            )
            after = _normalize_config_response(after_raw)

    result["after"] = after
    result["web"] = {
        "before": current,
        "after": after,
        "differences": differences,
    }

    if module._diff:
        result["diff"] = {
            "before": current,
            "after": after,
        }
    module.exit_json(**result)


def run_module() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)
    result: dict[str, Any] = {"changed": False}

    try:
        state = module.params["state"]
        config = _validate_config(module.params.get("config"), state)
        connection = _get_connection(module)
        current_raw = _call_api(
            connection,
            method="GET",
            path=CONFIG_PATH,
        )
        current = _normalize_config_response(current_raw)

        if state == STATE_GATHERED:
            _handle_gathered(module, current, result)
            return
        _apply_state(module, connection, current, config, state, result)
    except FeWebError as exc:
        module.fail_json(changed=result["changed"] or exc.changed, **exc.to_fail_kwargs())
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            changed=result["changed"],
        )


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
