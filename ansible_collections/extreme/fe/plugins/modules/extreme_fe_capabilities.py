# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to read device capabilities from Extreme Fabric Engine switches.

Module Architecture Overview
============================
This module reports the read-only device-capability data exposed by Fabric
Engine under the "Capabilities Management" OpenAPI tag.

REST Endpoints used (all GET, no write methods exist for this tag):
  GET /v0/state/capabilities                    -> SystemAllCapabilities
      (urls + system + openapi combined in one response)
  GET /v0/state/capabilities/system              -> Capabilities
      (platform capabilities: vlan, policy, radius, cards, ports, ...)
  GET /v0/state/capabilities/urls                -> Urls
      (every URL the device supports, with its allowed operations)
  GET /v0/state/capabilities/system/ports        -> PortsCapability
      (capabilities for every port)
  GET /v0/state/capabilities/system/ports/{port} -> PortCapability
      (capabilities for one named port)
  GET /v0/state/capabilities/openapi             -> OpenApiCapabilities
      (OpenAPI server request-concurrency limits)

Fabric Engine constraints:
  - Every endpoint under this tag is GET-only - there is no PATCH, PUT,
    POST or DELETE anywhere in the spec. The module therefore only
    supports state=gathered; nothing is ever written to the device.
  - The device's own JSON shape for each dataset is returned as-is under
    "gathered.<dataset>". These are heterogeneous, evolving capability
    descriptions (not a fixed set of writable fields), so there is no
    FIELD_MAP/DEFAULTS/FULL_DEFAULTS translation layer - unlike the
    resource modules in this collection that manage configuration.

Supported states:
  - gathered : Read-only, returns the requested capability dataset(s)

Code Flow (main):
  1. Connect to the switch via httpapi
  2. Resolve gather_filter (default: ["all"]) to the REST paths it selects
  3. If "ports" is selected and "port" is supplied, use the single-port
     endpoint instead of the bulk one
  4. GET each selected path and return the raw responses under "gathered"
"""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_capabilities
short_description: Read device capabilities from ExtremeNetworks Fabric Engine switches
version_added: "1.3.0"
description:
  - Read device-capability information from ExtremeNetworks Fabric Engine switches
    using the custom C(extreme_fe) HTTPAPI plugin.
  - Uses the C(Capabilities Management) endpoints of the NOS OpenAPI schema
    C(/v0/state/capabilities), C(/v0/state/capabilities/system),
    C(/v0/state/capabilities/urls), C(/v0/state/capabilities/system/ports),
    C(/v0/state/capabilities/system/ports/{port}) and
    C(/v0/state/capabilities/openapi).
  - Every endpoint under this tag is read-only (GET only) - there is no
    PATCH, PUT, POST or DELETE - so this module only supports
    C(state=gathered) and never makes changes to the device.
author:
  - Andreea-Lavinia Vraja (@avraja_extr)
requirements:
  - ansible.netcommon
notes:
  - Tested against Fabric Engine Version 9.3.2.
  - Supports check mode and diff mode. Both are no-ops here because the module
    never writes to the device - C(changed) is always C(false) and, since
    nothing ever changes, the module never populates C(diff).
  - C(gather_filter=all) calls the combined C(/v0/state/capabilities) endpoint,
    which returns C(system), C(urls) and C(openapi) together. C(system) already
    contains a nested C(ports) list, but it is the same data as the dedicated
    C(ports) dataset below, not a per-port lookup.
  - C(port) is only used when C(ports) is included in C(gather_filter). When
    supplied, the single-port endpoint is used instead of the bulk one and
    C(gathered.ports) becomes a single object instead of a list.
options:
  gather_filter:
    description:
      - Which capability dataset(s) to retrieve.
      - C(all) calls the combined endpoint and returns C(system), C(urls) and
        C(openapi) together under C(gathered.all).
      - C(system), C(urls), C(ports) and C(openapi) each call their own
        dedicated endpoint and are returned under the matching key in
        C(gathered).
    type: list
    elements: str
    choices: [all, system, urls, ports, openapi]
    default: [all]
  port:
    description:
      - Name of a single port to retrieve capabilities for, for example
        C(1:1:1).
      - Requires C(ports) to be included in C(gather_filter). When omitted,
        C(ports) returns the capabilities of every port instead.
    type: str
  state:
    description:
      - Desired module operation. This module only supports C(gathered)
        because every underlying REST endpoint is read-only.
    type: str
    choices: [gathered]
    default: gathered
"""

EXAMPLES = r"""
# Task-level examples for ansible-doc:

# =========================================================================
# Full playbook examples:
# To create a complete playbook, uncomment the lines starting with:
#   '# - name:', '# hosts:', '# gather_facts:', and '# tasks:'
# After uncommenting, realign indentation to conform to YAML format
# (playbook level at col 0, tasks indented under tasks:)
# Note: This is a READ-ONLY module - no prerequisites required
# =========================================================================

# -------------------------------------------------------------------------
# Task 1: Gather all device capabilities (default)
# -------------------------------------------------------------------------
# - name: "Task 1: Gather all device capabilities"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect all device capabilities
  extreme.fe.extreme_fe_capabilities:
  register: all_capabilities

# -------------------------------------------------------------------------
# Task 2: Gather only platform capabilities
# -------------------------------------------------------------------------
# - name: "Task 2: Gather platform capabilities"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect platform capabilities
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - system
  register: system_capabilities

# -------------------------------------------------------------------------
# Task 3: Gather the list of supported URLs
# -------------------------------------------------------------------------
# - name: "Task 3: Gather supported URLs"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect all supported URLs
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - urls
  register: url_capabilities

# -------------------------------------------------------------------------
# Task 4: Gather capabilities for every port
# -------------------------------------------------------------------------
# - name: "Task 4: Gather all port capabilities"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect capabilities for every port
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - ports
  register: all_port_capabilities

# -------------------------------------------------------------------------
# Task 5: Gather capabilities for a single port
# -------------------------------------------------------------------------
# - name: "Task 5: Gather one port's capabilities"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect capabilities for port 1:1:1
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - ports
    port: "1:1:1"
  register: single_port_capabilities

# -------------------------------------------------------------------------
# Task 6: Gather multiple datasets in one task
# -------------------------------------------------------------------------
# - name: "Task 6: Gather system and OpenAPI capabilities"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect system and OpenAPI capabilities together
  extreme.fe.extreme_fe_capabilities:
    gather_filter:
      - system
      - openapi
  register: combined_capabilities
"""

RETURN = r"""
changed:
  description: Always C(false) - this module never writes to the device.
  returned: always
  type: bool
gathered:
  description:
    - Capability data gathered from the device, keyed by the C(gather_filter)
      entry that produced it.
  returned: always
  type: dict
  contains:
    all:
      description:
        - Combined device capabilities as returned by
          C(/v0/state/capabilities) - C(urls), C(system) and C(openapi)
          together. Present when C(all) is in C(gather_filter).
      type: dict
    system:
      description:
        - Platform capabilities as returned by
          C(/v0/state/capabilities/system) (for example maximum VLANs,
          RADIUS vendor IDs, card and port capabilities). Present when
          C(system) is in C(gather_filter).
      type: dict
    urls:
      description:
        - Every URL supported by the device, with its allowed operations and
          attributes, as returned by C(/v0/state/capabilities/urls). Present
          when C(urls) is in C(gather_filter).
      type: list
      elements: dict
    ports:
      description:
        - Port capability data. A list of every port's capabilities from
          C(/v0/state/capabilities/system/ports) when C(port) is not
          supplied, or a single port object from
          C(/v0/state/capabilities/system/ports/{port}) when it is. Present
          when C(ports) is in C(gather_filter).
      type: raw
    openapi:
      description:
        - OpenAPI server request-concurrency limits as returned by
          C(/v0/state/capabilities/openapi). Present when C(openapi) is in
          C(gather_filter).
      type: dict
capabilities:
  description: Convenience wrapper mirroring C(gathered) under a feature-named key.
  returned: always
  type: dict
  contains:
    config:
      description: Same content as the top-level C(gathered) key.
      type: dict
"""

from typing import Any  # noqa: E402
from urllib.parse import quote  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible.module_utils.common.text.converters import to_text  # noqa: E402
from ansible.module_utils.connection import Connection, ConnectionError  # noqa: E402

# ── State ────────────────────────────────────────────────────────────────
# All endpoints under Capabilities Management are GET-only, so gathered is
# the only state this module supports.
STATE_GATHERED = "gathered"

# ── REST paths ──────────────────────────────────────────────────────────
# Static path for every dataset except "ports" without a specific port,
# which is templated below to reach the single-port endpoint instead.
GATHER_FILTER_PATHS: dict[str, str] = {
    "all": "/v0/state/capabilities",
    "system": "/v0/state/capabilities/system",
    "urls": "/v0/state/capabilities/urls",
    "ports": "/v0/state/capabilities/system/ports",
    "openapi": "/v0/state/capabilities/openapi",
}
PORT_CAPABILITY_PATH_TEMPLATE = "/v0/state/capabilities/system/ports/{port}"

# Deterministic order for the "gathered" output, independent of how the
# user ordered gather_filter.
GATHER_FILTER_ORDER = ["all", "system", "urls", "ports", "openapi"]

ARGUMENT_SPEC = {
    "gather_filter": {
        "type": "list",
        "elements": "str",
        "choices": ["all", "system", "urls", "ports", "openapi"],
        "default": ["all"],
    },
    "port": {"type": "str"},
    "state": {
        "type": "str",
        "choices": [STATE_GATHERED],
        "default": STATE_GATHERED,
    },
}


class FeCapabilitiesError(Exception):
    """Raised for extreme_fe_capabilities validation or response issues."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> dict[str, Any]:
        data: dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


def _extract_error(payload: Any) -> dict[str, Any] | None:
    """Detect a device-reported error embedded in an otherwise-200 response."""
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
            "message": message or "Device reported a capabilities error",
            "payload": payload,
        }
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported capabilities errors",
            "errors": errors,
            "payload": payload,
        }
    return None


def _get_connection(module: AnsibleModule) -> Connection:
    if not module._socket_path:
        raise FeCapabilitiesError("Connection type httpapi is required for this module")
    return Connection(module._socket_path)


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    path: str,
) -> Any:
    """GET one capabilities endpoint and return its response."""
    try:
        response = connection.send_request(None, path=path, method="GET")
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
        )

    if isinstance(response, bytes):
        response = to_text(response)

    if isinstance(response, dict):
        error = _extract_error(response)
        if error:
            module.fail_json(msg=error.get("message"), details=error)

    return response


def _normalize_gather_filter(values: list[str] | None) -> list[str]:
    """Dedupe the requested datasets and return them in a stable order."""
    requested = set(values) if values else {"all"}
    return [name for name in GATHER_FILTER_ORDER if name in requested]


def _resolve_path(name: str, port: str | None) -> str:
    if name == "ports" and port:
        return PORT_CAPABILITY_PATH_TEMPLATE.format(port=quote(port, safe=""))
    return GATHER_FILTER_PATHS[name]


def _gather_capabilities(
    module: AnsibleModule,
    connection: Connection,
    gather_filter: list[str],
    port: str | None,
) -> dict[str, Any]:
    gathered: dict[str, Any] = {}
    for name in gather_filter:
        path = _resolve_path(name, port)
        gathered[name] = _call_api(module, connection, path=path)
    return gathered


def main() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    result: dict[str, Any] = {
        "changed": False,
    }

    try:
        connection = _get_connection(module)

        gather_filter = _normalize_gather_filter(module.params.get("gather_filter"))
        port = module.params.get("port")

        if port and "ports" not in gather_filter:
            raise FeCapabilitiesError(
                "'port' requires 'ports' to be included in gather_filter",
                details={"gather_filter": gather_filter, "port": port},
            )

        gathered = _gather_capabilities(module, connection, gather_filter, port)

        result["gathered"] = gathered
        result["capabilities"] = {"config": gathered}

        module.exit_json(**result)
    except FeCapabilitiesError as exc:
        module.fail_json(**exc.to_fail_kwargs())
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
        )


if __name__ == "__main__":
    main()
