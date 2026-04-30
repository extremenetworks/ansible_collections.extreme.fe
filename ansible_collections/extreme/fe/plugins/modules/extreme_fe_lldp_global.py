# -*- coding: utf-8 -*-
"""Ansible module to manage global LLDP settings on Fabric Engine switches."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

DOCUMENTATION = r"""
---
module: extreme_fe_lldp_global
short_description: Manage global LLDP settings on ExtremeNetworks Fabric Engine switches
version_added: "1.1.0"
description:
  - Manage device-wide LLDP timer settings on ExtremeNetworks Fabric Engine (VOSS) switches using the custom C(extreme_fe) HTTPAPI plugin.
  - Uses C(/v0/configuration/lldp) from the NOS OpenAPI schema.
  - Only Fabric Engine global attributes are exposed for configuration. Switch Engine (EXOS)-only fields are intentionally excluded.
  - C(init_delay_seconds) is returned in gathered output when present on the device, but it is not configurable on Fabric Engine.
author:
  - ExtremeNetworks Networking Automation Team
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project.
  - This module manages the singleton global LLDP resource only. It does not manage per-port LLDP settings.
  - C(overridden) is functionally equivalent to C(replaced) because the LLDP global configuration is a singleton object.
  - C(deleted) resets supplied attributes to device defaults. If C(config) is omitted with C(state=deleted), all configurable global LLDP attributes are reset.
requirements:
  - ansible.netcommon
options:
  config:
    description:
      - Structured LLDP global settings to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional when C(state=deleted); if omitted, all configurable LLDP global settings are reset to defaults.
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
      - C(replaced) treats configurable LLDP global attributes as authoritative and resets omitted configurable attributes to defaults.
      - C(overridden) behaves like C(replaced) for this singleton resource.
      - C(deleted) resets the supplied attributes, or all configurable attributes when C(config) is omitted.
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
lldp:
  description: LLDP global configuration details.
  returned: always
  type: dict
  contains:
    before:
      description: LLDP global configuration before any requested change.
      returned: when state != gathered
      type: dict
    after:
      description: LLDP global configuration after the requested change.
      returned: when state != gathered
      type: dict
    config:
      description: Current LLDP global configuration in gathered mode.
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
  description: Raw API responses captured from the device for GET, PATCH, and optional state calls.
  returned: always
  type: dict
"""

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
        self, message: str, *, details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _extract_error(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)

    message = (
        payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    )
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
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    api_responses: Dict[str, Any],
    response_key: str,
    payload: Optional[Any] = None,
    expect_content: bool = True,
) -> Any:
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=api_responses,
        )

    if isinstance(response, bytes):
        response = to_text(response)

    api_responses[response_key] = response

    if response in (None, ""):
        return None if not expect_content else {}

    if isinstance(response, dict):
        error = _extract_error(response)
        if error:
            module.fail_json(
                msg=error.get("message"), details=error, api_responses=api_responses
            )

    return response


def _normalize_config_response(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise FeLldpGlobalError(
            "Unexpected response when retrieving LLDP global configuration",
            details={"payload": payload},
        )

    normalized: Dict[str, Any] = {}
    for option, meta in SETTABLE_FIELDS.items():
        rest_key = meta["rest"]
        if rest_key in payload:
            normalized[option] = payload.get(rest_key)
    for option, rest_key in READ_ONLY_FIELDS.items():
        if rest_key in payload:
            normalized[option] = payload.get(rest_key)
    return normalized


def _validate_config(config: Optional[Dict[str, Any]], state: str) -> Dict[str, Any]:
    normalized = dict(config or {})

    if state in REQUIRES_CONFIG and not normalized:
        raise FeLldpGlobalError(
            "config is required when state is one of: merged, replaced, overridden"
        )

    if state == STATE_MERGED and normalized:
        managed_keys = [
            key
            for key in normalized
            if key in SETTABLE_FIELDS and normalized.get(key) is not None
        ]
        if not managed_keys:
            raise FeLldpGlobalError(
                "At least one configurable LLDP global attribute must be supplied when state='merged'"
            )

    for option, meta in SETTABLE_FIELDS.items():
        if option not in normalized or normalized.get(option) is None:
            continue
        value = normalized.get(option)
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise FeLldpGlobalError(
                "{0} must be an integer".format(option),
                details={"option": option, "received": normalized.get(option)},
            )
        if value < meta["minimum"] or value > meta["maximum"]:
            raise FeLldpGlobalError(
                "{0} must be between {1} and {2}".format(
                    option, meta["minimum"], meta["maximum"]
                ),
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


def _build_target_config(
    current: Dict[str, Any], config: Dict[str, Any], state: str
) -> Dict[str, Any]:
    if state == STATE_MERGED:
        return {
            key: value
            for key, value in config.items()
            if key in SETTABLE_FIELDS and value is not None
        }

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

    raise FeLldpGlobalError("Unsupported state supplied", details={"state": state})


def _build_patch_payload(
    current: Dict[str, Any], target: Dict[str, Any]
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for option, desired_value in target.items():
        if option not in SETTABLE_FIELDS:
            continue
        if current.get(option) != desired_value:
            payload[SETTABLE_FIELDS[option]["rest"]] = desired_value
    return payload


def _build_differences(
    current: Dict[str, Any], target: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    differences: Dict[str, Dict[str, Any]] = {}
    for option, desired_value in target.items():
        if option not in SETTABLE_FIELDS:
            continue
        before_value = current.get(option)
        if before_value != desired_value:
            differences[option] = {"before": before_value, "after": desired_value}
    return differences


def _merge_after(
    current: Dict[str, Any], patch_payload: Dict[str, Any]
) -> Dict[str, Any]:
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

    result: Dict[str, Any] = {
        "changed": False,
        "api_responses": {},
    }

    try:
        state = module.params.get("state")
        gather_state = bool(module.params.get("gather_state"))
        requested_config = _validate_config(module.params.get("config"), state)

        current_raw = _call_api(
            module,
            connection,
            method="GET",
            path=CONFIG_PATH,
            api_responses=result["api_responses"],
            response_key="configuration_before",
        )
        current_config = _normalize_config_response(current_raw)

        if state == STATE_GATHERED:
            result["lldp"] = {"config": current_config}
            if gather_state:
                result["lldp"]["state"] = (
                    _call_api(
                        module,
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
            result["changed"] = True
            result["submitted"] = {
                "operation": state,
                "path": CONFIG_PATH,
                "payload": patch_payload,
            }

            if module.check_mode:
                result["lldp"]["after"] = _merge_after(current_config, patch_payload)
            else:
                _call_api(
                    module,
                    connection,
                    method="PATCH",
                    path=CONFIG_PATH,
                    payload=patch_payload,
                    expect_content=False,
                    api_responses=result["api_responses"],
                    response_key="patch",
                )
                after_raw = _call_api(
                    module,
                    connection,
                    method="GET",
                    path=CONFIG_PATH,
                    api_responses=result["api_responses"],
                    response_key="configuration_after",
                )
                result["lldp"]["after"] = _normalize_config_response(after_raw)
        else:
            result["api_responses"]["patch"] = None

        if gather_state:
            result["lldp"]["state"] = (
                _call_api(
                    module,
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
        module.fail_json(
            api_responses=result.get("api_responses", {}), **exc.to_fail_kwargs()
        )
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=result.get("api_responses", {}),
        )


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
