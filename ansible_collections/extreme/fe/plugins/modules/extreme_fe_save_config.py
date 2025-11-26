# -*- coding: utf-8 -*-
"""Ansible module to save Fabric Engine configurations via HTTPAPI."""

from __future__ import annotations

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils._text import to_text

from typing import Any, Dict, Optional

DOCUMENTATION = r"""
module: extreme_fe_save_config
short_description: Save the running configuration on ExtremeNetworks Fabric Engine switches
version_added: 1.3.0
description:
- Save the current Fabric Engine (VOSS) running configuration to the active or specified
  configuration file via the custom ``extreme_fe`` HTTPAPI plugin.
- Supports optionally providing a filename and using Fabric Engine's verbose save option to
  persist both current and default configuration elements.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the ``ansible.netcommon`` collection and the ``extreme_fe`` HTTPAPI plugin shipped
  with this project.
- Applicable only to Fabric Engine (VOSS) devices.
requirements:
- ansible.netcommon
options:
  name:
    description:
    - Destination configuration filename.
    - When omitted, the device saves to the currently selected or default configuration file.
    type: str
  verbose:
    description:
    - When true, request the device to save both the current and default configuration state.
    - Only applicable to Fabric Engine; ignored when unset.
    type: bool
"""

EXAMPLES = r"""
- name: Save configuration to the active config file
  hosts: switches
  gather_facts: false
  tasks:
    - name: Save running configuration
      extreme_fe_save_config:
        verbose: false

- name: Save configuration to a specific file with verbose mode
  hosts: switches
  gather_facts: false
  tasks:
    - name: Save running configuration as backup
      extreme_fe_save_config:
        name: config-backup.cfg
        verbose: true
"""

RETURN = r"""
changed:
  description: Indicates whether the operation triggered a configuration save request.
  returned: always
  type: bool
response:
  description: Raw response payload returned by the device, when provided.
  returned: when the device includes additional response data
  type: dict
  sample:
    status: SUCCESS
    details: Configuration written successfully
"""

ARGUMENT_SPEC = {
    "name": {"type": "str"},
    "verbose": {"type": "bool"},
}

SAVE_CONFIG_PATH = "/v0/operation/system/config/:save"


class FeSaveConfigError(Exception):
    """Raised for validation issues or unexpected device responses."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            payload["details"] = self.details
        return payload


def _sanitize_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            raise FeSaveConfigError("Parameter 'name' must not be empty when provided")
        return trimmed
    raise FeSaveConfigError("Parameter 'name' must be a string", details={"received_type": type(value).__name__})


def _build_payload(params: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}

    name = _sanitize_name(params.get("name"))
    if name is not None:
        payload["name"] = name

    if "verbose" in params and params["verbose"] is not None:
        payload["verbose"] = bool(params["verbose"])

    return payload


def _extract_error(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if code and isinstance(code, int) and code >= 400:
        return {"code": code, "message": message or "Device reported an error", "payload": payload}
    if message and isinstance(message, str) and message.lower().startswith("error"):
        return {"message": message, "payload": payload}
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return {"message": message or "Device reported errors", "payload": payload, "errors": errors}
    return None


def main() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    try:
        payload = _build_payload(module.params)
    except FeSaveConfigError as exc:
        module.fail_json(**exc.to_fail_kwargs())

    if module.check_mode:
        module.exit_json(changed=True, submitted=payload)

    connection = Connection(module._socket_path)

    request_body: Optional[Dict[str, Any]] = payload if payload else {}

    try:
        response = connection.send_request(request_body, path=SAVE_CONFIG_PATH, method="POST")
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None), err=getattr(exc, "err", None))

    error = _extract_error(response)
    if error:
        module.fail_json(msg=error.get("message"), details=error)

    result: Dict[str, Any] = {"changed": True}
    if response not in (None, ""):
        if isinstance(response, dict):
            result["response"] = response
        else:
            result["response_text"] = to_text(response)

    module.exit_json(**result)


if __name__ == "__main__":
    main()
