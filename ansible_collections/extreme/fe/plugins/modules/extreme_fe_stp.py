# -*- coding: utf-8 -*-
"""Ansible module to manage STP per-port settings on Fabric Engine switches.

Manages BPDU Guard and STP per-port configuration (edge port, priority,
path cost, STP enabled) on physical ports and LAG interfaces.

REST API endpoints used:
  STP per-port:
    - GET   /v0/configuration/stp
    - PATCH /v0/configuration/stp/{stp_name}/ports/{port}
    - GET   /v0/state/stp/{stp_name}/ports/{port}
"""

from __future__ import annotations

# ── Standard library imports ─────────────────────────────────────────────────
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

# ── Ansible SDK imports ──────────────────────────────────────────────────────
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

DOCUMENTATION = r"""
---
module: extreme_fe_stp
short_description: Manage STP per-port settings on ExtremeNetworks Fabric Engine switches
version_added: 1.1.0
description:
- Configure STP per-port settings on ExtremeNetworks Fabric Engine
  (VOSS) switches using the C(extreme_fe) HTTPAPI connection plugin.
- Supports BPDU Guard, edge port, port priority, path cost, and
  per-port STP enable/disable.
author:
- ExtremeNetworks Networking Automation Team
notes:
- Requires the C(ansible.netcommon) collection and the C(extreme_fe)
  HTTPAPI plugin shipped with this project.
- BPDU Guard requires STP to be active on the device.
- C(stp_instance) is required and identifies the STP domain to
  operate on.  Use C(0) for CIST/RSTP, or C(0)-C(63) for MSTP
  instances.  This mirrors the VOSS CLI and REST API, which
  always require an explicit STP instance.
- On VOSS, C(bpduRestrictEnabled) is not separately configurable; it
  is always C(true) when C(bpduProtection) is C(GUARD).
requirements:
- ansible.netcommon
options:
  interface:
    description:
    - Interface identifier, for example C(PORT:1:5) or C(LAG:10). When the type prefix is omitted, C(PORT) is assumed.
    type: str
  interface_type:
    description:
    - Interface type. Use together with C(interface_name) when the combined C(interface) parameter is not supplied.
    type: str
    choices:
    - PORT
    - LAG
  interface_name:
    description:
    - Interface name (for C(PORT) use slot/port notation such as C(1:5)).
    type: str
  bpdu_guard_enabled:
    description:
    - Enable (C(true)) or disable (C(false)) BPDU Guard on the port.
    - When omitted, the BPDU Guard setting is left unchanged (merged)
      or not managed at all.
    type: bool
  recovery_timeout:
    description:
    - Seconds before a BPDU Guard disabled port is re-enabled.
    - A value of C(0) means the port stays disabled forever.
    - Valid range is C(0) or C(10-65535).  Default on VOSS is 120.
    type: int
  is_edge_port:
    description:
    - Mark the port as an edge port (directly connected to a user
      device rather than another switch).  CIST only.
    type: bool
  priority:
    description:
    - STP port priority (0-240 in steps of 16, default 128).
    type: int
  path_cost:
    description:
    - STP path cost contribution (1-200000000).
    type: int
  stp_enabled:
    description:
    - Enable (C(true)) or disable (C(false)) STP on this port.
    - Default is C(true) (STP enabled on port at factory reset).
    type: bool
  stp_instance:
    description:
    - STP instance (domain) to target for BPDU Guard and STP
      per-port settings.
    - In MSTP mode, valid values are C(0) (CIST) through C(63).
    - In RSTP mode, only C(0) is valid.
    - Both plain instance numbers (C(0), C(2)) and device-format
      names (C(s0), C(s2)) are accepted.
    required: true
    type: str
  state:
    description:
    - Desired module operation.
    - '`merged` applies the provided parameters incrementally without removing unspecified STP settings.'
    - '`replaced` treats the supplied values as authoritative for the target interface. Omitted STP fields are reset to factory defaults (except C(path_cost), which has no documented VOSS default and is left unchanged unless explicitly set).'
    - '`overridden` is like C(replaced) but also resets other ports within the same STP instance to factory defaults (C(path_cost) exception applies — see C(replaced)).'
    - '`deleted` resets STP per-port settings to factory defaults (C(path_cost) is left unchanged).'
    - '`gathered` returns the current STP per-port settings without applying changes.'
    type: str
    choices:
    - merged
    - replaced
    - overridden
    - deleted
    - gathered
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
# ## Enable STP (if not already active)
# # boot config flags spanning-tree-mode rstp
# # save config
# # reset -y
#
# ## Disable Auto-Sense on target ports (required before manual config)
# # auto-sense
# #   no enable port 1/5,1/7,1/8,1/10
# # exit

# -------------------------------------------------------------------------
# Task 1: Enable BPDU Guard on access port
# Description:
#   - Enable BPDU Guard with a recovery timeout
# Prerequisites:
#   - STP must be active (boot config flags spanning-tree-mode rstp)
# CLI equivalent:
#   interface gigabitEthernet 1/5
#     spanning-tree bpdu-guard enable
#     spanning-tree bpdu-guard timeout 300
# -------------------------------------------------------------------------
# - name: "Task 1: Enable BPDU Guard on port 1:5"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enable BPDU Guard
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:5
    stp_instance: "0"
    bpdu_guard_enabled: true
    recovery_timeout: 300
    state: merged

# -------------------------------------------------------------------------
# Task 2: Enable BPDU Guard only (no other STP changes)
# Description:
#   - Merge BPDU Guard settings without touching other STP config
# -------------------------------------------------------------------------
# - name: "Task 2: Enable BPDU Guard only on port 1:8"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Merge BPDU Guard settings only
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:8
    stp_instance: "0"
    bpdu_guard_enabled: true
    recovery_timeout: 200
    state: merged

# -------------------------------------------------------------------------
# Task 3: Reset STP per-port settings to factory defaults
# Description:
#   - Reset BPDU Guard and all STP per-port settings to factory
#     defaults using deleted state.
# -------------------------------------------------------------------------
# - name: "Task 3: Reset STP settings to factory defaults on port 1:8"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Delete — reset STP settings to factory defaults
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:8
    stp_instance: "0"
    state: deleted

# -------------------------------------------------------------------------
# Task 4: BPDU Guard with edge port and STP enabled
# Description:
#   - Full STP per-port config: guard + edge + STP + timeouts
#   - Typical for user-facing access ports that need fast
#     convergence and BPDU containment
# Prerequisites:
#   - STP must be active (boot config flags spanning-tree-mode
#     rstp)
# CLI equivalent:
#   interface gigabitEthernet 1/5
#     spanning-tree bpdu-guard enable
#     spanning-tree bpdu-guard timeout 500
#     spanning-tree learning fast
#     spanning-tree rstp port-priority 64
#     spanning-tree rstp cost 20000
#     no spanning-tree shutdown port 1/5
# -------------------------------------------------------------------------
# - name: "Task 4: Full STP per-port config"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Full STP per-port config on edge port
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:5
    stp_instance: "0"
    bpdu_guard_enabled: true
    is_edge_port: true
    stp_enabled: true
    recovery_timeout: 500
    priority: 64
    path_cost: 20000
    state: merged

# -------------------------------------------------------------------------
# Task 5: Replaced — authoritative STP per-port config
# Description:
#   - Replaced sets supplied fields and resets omitted fields
#     to defaults (guard=off, edge=off, stp=on,
#     recovery=120, priority=128)
#   - Use when you want a known full state on the port
# -------------------------------------------------------------------------
# - name: "Task 5: Replaced STP settings"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Replaced — guard + edge only, rest to defaults
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:5
    stp_instance: "0"
    bpdu_guard_enabled: true
    is_edge_port: true
    state: replaced

# -------------------------------------------------------------------------
# Task 6: Overridden — reset other ports in the STP instance, apply to one
# Description:
#   - Overridden resets all other STP ports within the same
#     STP instance (domain) to factory defaults, then applies
#     replaced treatment to the specified interface
#   - stp_instance is required — specify the STP domain explicitly
#   - Use for per-instance STP enforcement
# -------------------------------------------------------------------------
# - name: "Task 6: Overridden STP settings"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Overridden — reset other ports in instance, configure 1:5
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:5
    stp_instance: "0"
    bpdu_guard_enabled: true
    is_edge_port: true
    recovery_timeout: 300
    state: overridden

# -------------------------------------------------------------------------
# Task 7: Gathered — read STP per-port state
# Description:
#   - Reads current STP per-port configuration from the
#     device and returns it as structured data
#   - No changes made to the device
# -------------------------------------------------------------------------
# - name: "Task 7: Gather STP per-port state"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Gathered — read STP per-port config
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:5
    stp_instance: "0"
    state: gathered
  register: stp_state

# -------------------------------------------------------------------------
# Task 8: MSTP — set priority on a specific MSTP instance
# Description:
#   - Configure STP port priority on MSTP instance 2
#   - Requires the device to be in MSTP mode and instance 2
#     to exist
# CLI equivalent:
#   spanning-tree mstp msti 2 port 1/5 priority 64
# -------------------------------------------------------------------------
# - name: "Task 8: MSTP instance priority"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: MSTP instance 2 — set port priority
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:5
    stp_instance: "2"
    priority: 64
    state: merged

# -------------------------------------------------------------------------
# Task 9: Lab port profile — guard + short recovery
# Description:
#   - Lab/PoC ports where hypervisors may emit BPDUs
#   - Short recovery timeout for quick auto-recovery
# -------------------------------------------------------------------------
# - name: "Task 9: Lab port STP profile"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Lab port — guard on, fast recovery
  extreme.fe.extreme_fe_stp:
    interface: PORT:1:10
    stp_instance: "0"
    bpdu_guard_enabled: true
    is_edge_port: true
    recovery_timeout: 30
    state: merged
"""

RETURN = r"""
---
changed:
    description: Indicates whether any changes were made.
    returned: always
    type: bool
stp:
    description:
        - STP per-port settings for the interface.
    returned: always
    type: dict
    contains:
        stp_domain:
            description: STP domain name used for this port.
            returned: always
            type: str
        before:
            description: STP settings before the change (or current snapshot in gathered mode).
            returned: always
            type: dict
            contains:
                bpdu_guard_enabled:
                    description: Whether BPDU Guard is active on the port.
                    type: bool
                recovery_timeout:
                    description: Seconds before auto-recovery (0 = never).
                    type: int
                is_edge_port:
                    description: Whether the port is an STP edge port.
                    type: bool
                priority:
                    description: STP port priority.
                    type: int
                path_cost:
                    description: STP path cost.
                    type: int
                stp_enabled:
                    description: Whether STP is enabled on the port.
                    type: bool
                bpdu_origin:
                    description: Origin of BPDU Guard config (read-only).
                    type: str
        after:
            description: STP settings after the change.
            returned: on write operations (merged, replaced, overridden, deleted)
            type: dict
        config:
            description: Current STP settings (gathered state only).
            returned: when state is gathered
            type: dict
        state:
            description: Runtime STP port state from the device (e.g. forwarding, blocking).
            returned: when state is gathered and runtime state is available
            type: dict
        differences:
            description: Fields that differ between current and desired state.
            returned: on write operations
            type: dict
        reset_ports:
            description: Ports reset during overridden pre-pass.
            returned: when state is overridden and ports were reset
            type: list
            elements: dict
"""

ARGUMENT_SPEC = {
    "interface": {"type": "str"},
    "interface_type": {"type": "str", "choices": ["PORT", "LAG"]},
    "interface_name": {"type": "str"},
    "bpdu_guard_enabled": {"type": "bool"},
    "recovery_timeout": {"type": "int"},
    "is_edge_port": {"type": "bool"},
    "priority": {"type": "int"},
    "path_cost": {"type": "int"},
    "stp_enabled": {"type": "bool"},
    "stp_instance": {"type": "str", "required": True},
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}

KNOWN_INTERFACE_TYPES: Set[str] = {"PORT", "LAG"}

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# ─────────────────────────────────────────────────────────────────────────────
# STP constants
# ─────────────────────────────────────────────────────────────────────────────

# REST paths for STP
STP_CONFIG_PATH = "/v0/configuration/stp"
STP_PORT_CONFIG_TEMPLATE = "/v0/configuration/stp/{stp_name}/ports/{port}"
STP_PORT_STATE_TEMPLATE = "/v0/state/stp/{stp_name}/ports/{port}"

# Maps Ansible parameter names → REST API field names for STP/BPDU Guard
BPDU_FIELD_MAP = {
    "bpdu_guard_enabled": "bpduProtection",  # True→"GUARD", False→"DISABLED"
    "recovery_timeout": "recoveryTimeout",  # int, 0 | 10-65535
    "is_edge_port": "isEdgePort",  # bool
    "priority": "priority",  # int, 0-240 step 16
    "path_cost": "pathCost",  # int, 1-200000000
    "stp_enabled": "enabled",  # bool, STP state on port
}

# Full defaults for all configurable PortStpSettings fields.
# Used by replaced/overridden/deleted to reset omitted fields.
BPDU_FULL_DEFAULTS = {
    "bpduProtection": "DISABLED",
    "recoveryTimeout": 120,
    "isEdgePort": False,
    "priority": 128,
    "enabled": True,
    # pathCost intentionally omitted: pathCost=0 is EXOS-only,
    # no VOSS factory default documented.
}

# Validation ranges
RECOVERY_TIMEOUT_MIN = 10
RECOVERY_TIMEOUT_MAX = 65535


class FeStpError(Exception):
    """Base exception for the STP module."""

    def __init__(
        self, message: str, *, details: Optional[Dict[str, object]] = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, object]:
        data: Dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# ─────────────────────────────────────────────────────────────────────────────
# Interface parsing
# ─────────────────────────────────────────────────────────────────────────────


def _parse_interface(module: AnsibleModule) -> Tuple[str, str]:
    iface_value = module.params.get("interface")
    iface_type = module.params.get("interface_type")
    iface_name = module.params.get("interface_name")

    if iface_type and iface_name:
        return iface_type.strip().upper(), iface_name.strip()

    if iface_value:
        raw = str(iface_value).strip()
        if not raw:
            raise FeStpError("Interface value must not be empty")
        if ":" in raw:
            prefix, rest = raw.split(":", 1)
            prefix_upper = prefix.strip().upper()
            if prefix_upper in KNOWN_INTERFACE_TYPES:
                return prefix_upper, rest.strip()
        # default to PORT if type not provided
        return "PORT", raw

    raise FeStpError(
        "Either 'interface' or both 'interface_type' and 'interface_name' must be provided"
    )


def _get_port_name_from_interface(iface_type: str, iface_name: str) -> str:
    """Convert parsed interface identity to STP port name format.

    For PORT type, the STP API uses the same slot:port format.
    For LAG type, the STP port name may differ — return as-is for now.
    """
    return iface_name


# ─────────────────────────────────────────────────────────────────────────────
# REST API helpers
# ─────────────────────────────────────────────────────────────────────────────


def _is_not_found_response(payload: Optional[object]) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    if code == 404:
        return True
    message = (
        payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    )
    if isinstance(message, str) and "not found" in message.lower():
        return True
    return False


def _extract_error(payload: Any) -> Optional[Dict[str, Any]]:
    """Check whether a REST response indicates an error."""
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    message = (
        payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    )
    if code and isinstance(code, int) and code >= 400:
        return {
            "code": code,
            "message": message or "Device reported an error",
            "payload": payload,
        }
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported errors",
            "payload": payload,
            "errors": errors,
        }
    return None


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    payload: Optional[Any] = None,
    expect_content: bool = True,
    allow_not_found: bool = False,
) -> Any:
    """Send a REST request via the HTTPAPI connection plugin.

    When *allow_not_found* is ``True``, HTTP 404 responses (raised as
    ``ConnectionError`` or returned as an error payload) are treated as
    non-fatal and the function returns ``None`` instead of failing the
    module.
    """
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        if allow_not_found and getattr(exc, "code", None) == 404:
            return None
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
        )
    if response in (None, ""):
        return None if not expect_content else {}
    if isinstance(response, bytes):
        response = to_text(response)
    if isinstance(response, dict):
        if allow_not_found and _is_not_found_response(response):
            return None
        error = _extract_error(response)
        if error:
            module.fail_json(msg=error.get("message"), details=error)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# STP domain / port helpers
# ─────────────────────────────────────────────────────────────────────────────


def _matches_stp_instance(domain_name: str, target_instance: str) -> bool:
    """Check whether a device domain name matches the user-supplied stp_instance.

    The REST API reports STP domains as ``s0`` (CIST), ``s1``, ``s2``, …
    while the module documentation tells users to supply the plain
    instance number (``0``, ``2``).  This helper accepts both formats so
    that ``stp_instance: "0"`` matches domain ``"s0"`` and vice-versa.

    Both values are normalised (strip + lowercase) so ``"S0"`` or
    ``" 2 "`` work as expected.
    """
    domain_name = domain_name.strip().lower()
    target_instance = target_instance.strip().lower()
    if domain_name == target_instance:
        return True
    if target_instance.isdigit() and domain_name == f"s{target_instance}":
        return True
    if (
        target_instance.startswith("s")
        and target_instance[1:].isdigit()
        and domain_name == target_instance[1:]
    ):
        return True
    return False


def _is_cist(stp_instance: str) -> bool:
    """Return True when *stp_instance* refers to the CIST (instance 0).

    Recognises ``"0"`` and ``"s0"``.  Input is normalised
    (strip + lowercase) so ``"S0"`` is also recognised.
    """
    return stp_instance.strip().lower() in ("0", "s0")


def _fetch_stp_domains(
    module: AnsibleModule,
    connection: Connection,
) -> List[Dict[str, Any]]:
    """GET /v0/configuration/stp → list of STP domain objects."""
    data = _call_api(
        module, connection, method="GET", path=STP_CONFIG_PATH, allow_not_found=True
    )
    if data is None:
        return []
    data = data or []
    if isinstance(data, dict):
        if "domains" in data:
            data = data["domains"]
        elif "data" in data:
            data = data["data"]
        else:
            data = [data]
    if not isinstance(data, list):
        raise FeStpError(
            "Unexpected STP configuration response",
            details={"payload": data},
        )
    return data


def _build_port_settings_map(
    domains: List[Dict[str, Any]],
    target_instance: Optional[str] = None,
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """Parse STP domain list into {port_name: settings} map.

    When *target_instance* is given, only ports from that specific STP
    domain (instance name) are included.  Otherwise the first domain
    found is used as the default and first-write-wins applies.

    Returns (domain_name, port_map).
    """
    default_domain = ""
    port_map: Dict[str, Dict[str, Any]] = {}

    for domain in domains:
        if not isinstance(domain, dict):
            continue
        domain_name = str(domain.get("name") or "")

        # If caller asked for a specific instance, skip non-matching
        if target_instance is not None and not _matches_stp_instance(
            domain_name, target_instance
        ):
            continue

        if not default_domain and domain_name:
            default_domain = domain_name

        ports = domain.get("ports") or []
        if not isinstance(ports, list):
            continue
        for port_entry in ports:
            if not isinstance(port_entry, dict):
                continue
            port_name = str(port_entry.get("port") or port_entry.get("name") or "")
            if not port_name:
                continue
            if port_name not in port_map:
                nested = port_entry.get("settings")
                if isinstance(nested, dict):
                    settings = dict(nested)
                    settings["port"] = port_name
                else:
                    settings = dict(port_entry)
                settings["_domain"] = domain_name
                port_map[port_name] = settings

    return default_domain, port_map


def _fetch_port_state(
    module: AnsibleModule,
    connection: Connection,
    stp_domain: str,
    port: str,
) -> Optional[Dict[str, Any]]:
    """GET /v0/state/stp/{stp_name}/ports/{port} → port STP state."""
    path = STP_PORT_STATE_TEMPLATE.format(
        stp_name=quote(stp_domain, safe=""),
        port=quote(port, safe=""),
    )
    response = _call_api(
        module,
        connection,
        method="GET",
        path=path,
        expect_content=True,
        allow_not_found=True,
    )
    if response is None:
        return None
    if isinstance(response, dict):
        return response
    return None


# ─────────────────────────────────────────────────────────────────────────────
# BPDU Guard / STP parameter helpers
# ─────────────────────────────────────────────────────────────────────────────


def _validate_bpdu_params(module: AnsibleModule) -> None:
    """Validate BPDU Guard parameter values (ranges, steps)."""
    params = module.params

    timeout = params.get("recovery_timeout")
    if timeout is not None:
        if isinstance(timeout, bool):
            raise FeStpError(
                "recovery_timeout must be 0 or {0}-{1}".format(
                    RECOVERY_TIMEOUT_MIN, RECOVERY_TIMEOUT_MAX
                ),
                details={"received": timeout},
            )
        if timeout != 0 and not (
            RECOVERY_TIMEOUT_MIN <= timeout <= RECOVERY_TIMEOUT_MAX
        ):
            raise FeStpError(
                "recovery_timeout must be 0 or {0}-{1}".format(
                    RECOVERY_TIMEOUT_MIN, RECOVERY_TIMEOUT_MAX
                ),
                details={"received": timeout},
            )

    priority = params.get("priority")
    if priority is not None:
        if isinstance(priority, bool):
            raise FeStpError(
                "priority must be 0-240 in steps of 16",
                details={"received": priority},
            )
        if not (0 <= priority <= 240) or priority % 16 != 0:
            raise FeStpError(
                "priority must be 0-240 in steps of 16",
                details={"received": priority},
            )

    path_cost = params.get("path_cost")
    if path_cost is not None:
        if isinstance(path_cost, bool):
            raise FeStpError(
                "path_cost must be between 1 and 200000000",
                details={"received": path_cost},
            )
        if not (1 <= path_cost <= 200000000):
            raise FeStpError(
                "path_cost must be between 1 and 200000000",
                details={"received": path_cost},
            )


# Maximum MSTP instance number (VOSS supports 0-63).
_STP_INSTANCE_MAX = 63


def _validate_stp_instance(stp_instance: str) -> str:
    """Validate stp_instance format and range, return canonical form.

    Accepted forms: plain digit ("0"-"63") or s-prefixed ("s0"-"s63"),
    case-insensitive.  Raises FeStpError with a clear message for
    invalid input so users don't get a confusing "instance not found"
    error from the device later.

    Returns the canonical form with leading zeros stripped:
    ``"00"`` → ``"0"``, ``"s02"`` → ``"s2"``.  This ensures
    consistent matching in ``_is_cist()`` and ``_matches_stp_instance()``.
    """
    normalized = stp_instance.strip().lower()
    # Extract the numeric part
    if normalized.startswith("s"):
        num_str = normalized[1:]
    else:
        num_str = normalized
    if not num_str.isdigit():
        raise FeStpError(
            "stp_instance must be a number 0-{0} or 's0'-'s{0}', "
            "got '{1}'".format(_STP_INSTANCE_MAX, stp_instance),
        )
    num = int(num_str)
    if num < 0 or num > _STP_INSTANCE_MAX:
        raise FeStpError(
            "stp_instance must be 0-{0}, got {1}".format(
                _STP_INSTANCE_MAX,
                num,
            ),
        )
    # Return canonical form: strip leading zeros ("00" → "0",
    # "s02" → "s2") so _is_cist() and _matches_stp_instance()
    # work correctly.
    if normalized.startswith("s"):
        return "s{0}".format(num)
    return str(num)


def _build_bpdu_merged_payload(module: AnsibleModule) -> Dict[str, Any]:
    """Build a BPDU Guard payload with only user-supplied fields (merged)."""
    payload: Dict[str, Any] = {}
    params = module.params

    for param, rest_field in BPDU_FIELD_MAP.items():
        value = params.get(param)
        if value is None:
            continue
        if param == "bpdu_guard_enabled":
            payload[rest_field] = "GUARD" if value else "DISABLED"
        else:
            payload[rest_field] = value

    return payload


def _build_bpdu_replaced_payload(module: AnsibleModule) -> Dict[str, Any]:
    """Build a full BPDU Guard payload, defaulting omitted fields (replaced)."""
    payload = dict(BPDU_FULL_DEFAULTS)
    params = module.params

    for param, rest_field in BPDU_FIELD_MAP.items():
        value = params.get(param)
        if value is None:
            continue
        if param == "bpdu_guard_enabled":
            payload[rest_field] = "GUARD" if value else "DISABLED"
        else:
            payload[rest_field] = value

    return payload


def _build_bpdu_deleted_payload() -> Dict[str, Any]:
    """Return the payload that resets BPDU Guard to factory defaults."""
    return dict(BPDU_FULL_DEFAULTS)


def _compute_bpdu_diff(
    current: Dict[str, Any],
    desired: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Compare desired BPDU payload against current settings.

    Returns (differences, patch_payload).
    """
    differences: Dict[str, Any] = {}
    patch_payload: Dict[str, Any] = {}

    for field, desired_value in desired.items():
        current_value = current.get(field)
        if current_value != desired_value:
            differences[field] = {"before": current_value, "after": desired_value}
            patch_payload[field] = desired_value

    return differences, patch_payload


def _bpdu_to_ansible_output(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Convert STP REST settings to Ansible-friendly output dict."""
    output: Dict[str, Any] = {}

    bpdu = settings.get("bpduProtection")
    if bpdu is not None:
        output["bpdu_guard_enabled"] = bpdu == "GUARD"

    timeout = settings.get("recoveryTimeout")
    if timeout is not None:
        output["recovery_timeout"] = timeout

    edge = settings.get("isEdgePort")
    if edge is not None:
        output["is_edge_port"] = edge

    prio = settings.get("priority")
    if prio is not None:
        output["priority"] = prio

    cost = settings.get("pathCost")
    if cost is not None:
        output["path_cost"] = cost

    origin = settings.get("bpduOrigin")
    if origin is not None:
        output["bpdu_origin"] = origin

    enabled = settings.get("enabled")
    if enabled is not None:
        output["stp_enabled"] = enabled

    return output


# ─────────────────────────────────────────────────────────────────────────────
# Overridden pre-pass helper
# ─────────────────────────────────────────────────────────────────────────────


def _overridden_reset_ports(
    module: AnsibleModule,
    connection: Connection,
    port_name: str,
    port_settings_map: Dict[str, Dict[str, Any]],
    default_domain: str,
    stp_instance: str = "0",
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Reset every non-target port that deviates from STP factory defaults.

    Individual port resets may fail for ports that the device refuses
    to modify (e.g. auto-sense ports reject STP changes).  Rather than
    failing the entire overridden operation, we record the failure as
    ``skipped=True`` in the port entry and continue.  The caller
    surfaces these as Ansible warnings.

    Returns ``(changed, reset_ports_list)``.
    """
    changed = False
    reset_ports: List[Dict[str, Any]] = []
    defaults_payload = _build_bpdu_deleted_payload()

    # isEdgePort is CIST-only (instance 0).  On MSTI instances the
    # device silently ignores it, so strip it to avoid false diffs
    # and unnecessary PATCHes during the overridden pre-pass.
    if not _is_cist(stp_instance):
        defaults_payload.pop("isEdgePort", None)

    for port, settings in port_settings_map.items():
        if port == port_name:
            continue
        diff, patch = _compute_bpdu_diff(settings, defaults_payload)
        if not diff:
            continue
        port_domain = settings.get("_domain") or default_domain
        port_entry: Dict[str, Any] = {
            "port": port,
            "before": _bpdu_to_ansible_output(settings),
        }
        if not module.check_mode:
            patch_path = STP_PORT_CONFIG_TEMPLATE.format(
                stp_name=quote(port_domain, safe=""),
                port=quote(port, safe=""),
            )
            try:
                resp = connection.send_request(
                    patch,
                    path=patch_path,
                    method="PATCH",
                )
            except ConnectionError as exc:
                # Skip — port may be auto-sense or otherwise
                # unmodifiable.  Recorded and surfaced as warning.
                port_entry["skipped"] = True
                port_entry["skip_reason"] = "Port %s: %s" % (port, to_text(exc))
                port_entry["after"] = port_entry["before"]
                reset_ports.append(port_entry)
                continue
            if isinstance(resp, dict):
                err = _extract_error(resp)
                if err:
                    # Skip — device rejected the reset for this
                    # port.  Recorded and surfaced as warning.
                    port_entry["skipped"] = True
                    port_entry["skip_reason"] = "Port %s: %s" % (
                        port,
                        err.get("message", "device rejected change"),
                    )
                    port_entry["after"] = port_entry["before"]
                    reset_ports.append(port_entry)
                    continue
        changed = True
        projected = dict(settings)
        projected.update(patch)
        port_entry["after"] = _bpdu_to_ansible_output(projected)
        reset_ports.append(port_entry)

    return changed, reset_ports


# ─────────────────────────────────────────────────────────────────────────────
# Target-port PATCH helper
# ─────────────────────────────────────────────────────────────────────────────


def _apply_stp_patch(
    connection: Connection,
    domain: str,
    port_name: str,
    patch_payload: Dict[str, Any],
) -> None:
    """Send PATCH to the device for the target STP port.

    Unlike the overridden pre-pass (which skips failures on
    side-effect resets), the target-port PATCH is the primary action
    the user requested.  Any failure here must propagate as
    ``FeStpError`` so Ansible reports it via ``fail_json``.
    """
    patch_path = STP_PORT_CONFIG_TEMPLATE.format(
        stp_name=quote(domain, safe=""),
        port=quote(port_name, safe=""),
    )
    try:
        resp = connection.send_request(
            patch_payload,
            path=patch_path,
            method="PATCH",
        )
    except ConnectionError as exc:
        raise FeStpError(
            "Failed to apply STP configuration on port {0}: {1}".format(
                port_name, to_text(exc)
            ),
        )

    if isinstance(resp, dict):
        err = _extract_error(resp)
        if err:
            raise FeStpError(
                "Device rejected STP change on port {0}: {1}".format(
                    port_name,
                    err.get("message", "unknown device error"),
                ),
                details=err,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Core STP handler
# ─────────────────────────────────────────────────────────────────────────────


def _handle_stp(
    module: AnsibleModule,
    connection: Connection,
    state: str,
    port_name: str,
    stp_instance: str = "0",
) -> Tuple[bool, Dict[str, Any]]:
    """Handle STP per-port operations for a single port.

    *stp_instance* identifies the STP domain (MSTP instance) to
    operate on.  Required — mirrors the REST API path parameter
    ``{stp_name}``.

    For ``overridden`` state the function also resets every other
    STP port *within the same instance* that deviates from factory
    defaults, matching standard Ansible resource-module semantics.
    Ports in other STP instances are not affected.

    Returns (changed, stp_result_dict).
    """
    changed = False

    # Fetch STP domains to find current settings for this port
    domains = _fetch_stp_domains(module, connection)
    default_domain, port_settings_map = _build_port_settings_map(
        domains,
        target_instance=stp_instance,
    )

    if not default_domain:
        raise FeStpError(
            "STP instance '{0}' not found on the device.".format(stp_instance),
        )

    current = port_settings_map.get(port_name, {})
    domain = current.get("_domain") or default_domain

    stp_result: Dict[str, Any] = {
        "stp_domain": domain,
    }

    # ── gathered: read only ──
    if state == STATE_GATHERED:
        stp_result["config"] = _bpdu_to_ansible_output(current)
        runtime = _fetch_port_state(module, connection, domain, port_name)
        if runtime is not None:
            stp_result["state"] = runtime
        return False, stp_result

    stp_result["before"] = _bpdu_to_ansible_output(current)

    # ── overridden pre-pass: reset unlisted ports ──
    if state == STATE_OVERRIDDEN:
        reset_changed, reset_ports = _overridden_reset_ports(
            module,
            connection,
            port_name,
            port_settings_map,
            default_domain,
            stp_instance=stp_instance,
        )
        if reset_changed:
            changed = True
        if reset_ports:
            stp_result["reset_ports"] = reset_ports
            # Re-fetch after resets so current reflects device
            if not module.check_mode:
                domains = _fetch_stp_domains(module, connection)
                _, port_settings_map = _build_port_settings_map(
                    domains,
                    target_instance=stp_instance,
                )
                current = port_settings_map.get(port_name, {})

    # ── Build desired payload based on state ──
    if state == STATE_MERGED:
        desired_payload = _build_bpdu_merged_payload(module)
    elif state in (STATE_REPLACED, STATE_OVERRIDDEN):
        desired_payload = _build_bpdu_replaced_payload(module)
    elif state == STATE_DELETED:
        desired_payload = _build_bpdu_deleted_payload()
    else:
        desired_payload = {}

    # isEdgePort is CIST-only (instance 0).  On MSTI instances the
    # device silently ignores it, so strip it to avoid a false diff.
    if not _is_cist(stp_instance):
        desired_payload.pop("isEdgePort", None)

    if not desired_payload:
        stp_result["after"] = _bpdu_to_ansible_output(current)
        stp_result["differences"] = {}
        return changed, stp_result

    # ── Compute diff ──
    differences, patch_payload = _compute_bpdu_diff(current, desired_payload)

    if not differences:
        stp_result["after"] = _bpdu_to_ansible_output(current)
        stp_result["differences"] = {}
        return changed, stp_result

    stp_result["differences"] = differences
    changed = True

    if module.check_mode:
        projected = dict(current)
        projected.update(patch_payload)
        stp_result["after"] = _bpdu_to_ansible_output(projected)
        return True, stp_result

    # ── Apply PATCH to target port ──
    _apply_stp_patch(connection, domain, port_name, patch_payload)

    # Re-read after PATCH
    refreshed_domains = _fetch_stp_domains(module, connection)
    _, refreshed_map = _build_port_settings_map(
        refreshed_domains,
        target_instance=stp_instance,
    )
    refreshed = refreshed_map.get(port_name, {})
    stp_result["after"] = _bpdu_to_ansible_output(refreshed)

    return True, stp_result


# ─────────────────────────────────────────────────────────────────────────────
# State handler functions
# ─────────────────────────────────────────────────────────────────────────────


def configure_stp(
    module: AnsibleModule, connection: Connection, state: str
) -> Dict[str, object]:
    iface_type, iface_name = _parse_interface(module)
    _validate_bpdu_params(module)
    port_name = _get_port_name_from_interface(iface_type, iface_name)
    stp_instance = _validate_stp_instance(module.params.get("stp_instance"))

    stp_changed, stp_result = _handle_stp(
        module,
        connection,
        state,
        port_name,
        stp_instance=stp_instance,
    )

    result: Dict[str, Any] = {"changed": stp_changed}
    result["stp"] = stp_result

    # Surface skipped ports from overridden pre-pass as Ansible warnings
    # so callers can detect incomplete enforcement without failing the
    # entire task (auto-sense ports refuse STP resets).
    if state == STATE_OVERRIDDEN:
        skipped = [p for p in stp_result.get("reset_ports", []) if p.get("skipped")]
        if skipped:
            port_names = ", ".join(p["port"] for p in skipped)
            module.warn(
                "Overridden state: {0} port(s) could not be reset to "
                "defaults and were skipped: {1}. Inspect "
                "result.stp.reset_ports for details.".format(
                    len(skipped),
                    port_names,
                )
            )

    return result


def delete_stp(module: AnsibleModule, connection: Connection) -> Dict[str, object]:
    iface_type, iface_name = _parse_interface(module)
    port_name = _get_port_name_from_interface(iface_type, iface_name)
    stp_instance = _validate_stp_instance(module.params.get("stp_instance"))

    stp_changed, stp_result = _handle_stp(
        module,
        connection,
        STATE_DELETED,
        port_name,
        stp_instance=stp_instance,
    )

    result: Dict[str, Any] = {"changed": stp_changed}
    result["stp"] = stp_result
    return result


def gather_stp(module: AnsibleModule, connection: Connection) -> Dict[str, object]:
    iface_type, iface_name = _parse_interface(module)
    port_name = _get_port_name_from_interface(iface_type, iface_name)
    stp_instance = _validate_stp_instance(module.params.get("stp_instance"))

    result: Dict[str, Any] = {"changed": False}

    # stp_instance is always provided (required argument),
    # so any FeStpError (instance not found, STP not configured)
    # propagates directly — no silent suppression.
    _, stp_result = _handle_stp(
        module,
        connection,
        STATE_GATHERED,
        port_name,
        stp_instance=stp_instance,
    )
    result["stp"] = stp_result

    return result


def run_module() -> None:
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
        required_one_of=[("interface", "interface_type")],
        required_together=[("interface_type", "interface_name")],
    )

    state = module.params["state"]

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == STATE_GATHERED:
            result = gather_stp(module, connection)
            module.exit_json(**result)
        elif state == STATE_DELETED:
            result = delete_stp(module, connection)
            module.exit_json(**result)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN):
            result = configure_stp(module, connection, state)
            module.exit_json(**result)
        else:
            raise FeStpError(f"Unsupported state '{state}' supplied.")
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeStpError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
