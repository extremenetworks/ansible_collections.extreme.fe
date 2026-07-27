# -*- coding: utf-8 -*-
"""Ansible module to manage STP per-port settings on Fabric Engine switches.

Manages BPDU Guard and STP per-port configuration (edge port, priority,
path cost, STP enabled) on physical ports.

REST API endpoints used:
  STP per-port:
    - GET   /v0/configuration/stp
    - PATCH /v0/configuration/stp/{stp_name}/ports/{port}
"""

from __future__ import annotations

# ── Standard library imports ─────────────────────────────────────────────────
import re as _re
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
- Uses C(config) list for per-port STP entries and C(stp_instance) as
  the top-level scope parameter identifying the STP domain.
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
- B(Breaking changes since 1.0.0:)
- LAG interfaces are no longer supported.  The VOSS STP REST API
  only accepts physical ports in C(slot:port) format.  Playbooks
  that used C(LAG:N) must be updated to use physical port names.
- Per-port runtime STP state (C(GET /v0/state/stp/.../ports/...))
  is no longer fetched.  The module now derives C(after) values
  from the configuration endpoint, which is authoritative for all
  fields this module manages.
requirements:
- ansible.netcommon
options:
  config:
    description:
    - List of per-port STP configuration entries.
    - Required for C(merged), C(replaced), C(overridden), C(deleted) states.
    - Optional for C(gathered) state (omit to gather all ports).
    type: list
    elements: dict
    suboptions:
      name:
        description:
        - Interface identifier in C(PORT:slot:port) or bare C(slot:port)
          format, for example C(PORT:1:5) or C(1:5).
          When the type prefix is omitted, C(PORT) is assumed.
        type: str
        required: true
      bpdu_guard_enabled:
        description:
        - Enable (C(true)) or disable (C(false)) BPDU Guard on the port.
        - When omitted, the BPDU Guard setting is left unchanged (merged).
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
# ── Task 1: Merged — enable BPDU Guard on multiple ports ─────────────────
- name: Enable BPDU Guard on access ports
  extreme.fe.extreme_fe_stp:
    stp_instance: "0"
    config:
      - name: "PORT:1:5"
        bpdu_guard_enabled: true
        recovery_timeout: 300
      - name: "PORT:1:8"
        bpdu_guard_enabled: true
        recovery_timeout: 200
    state: merged

# ── Task 2: Merged — full STP per-port config on edge port ───────────────
- name: Full STP per-port config on edge port
  extreme.fe.extreme_fe_stp:
    stp_instance: "0"
    config:
      - name: "PORT:1:5"
        bpdu_guard_enabled: true
        is_edge_port: true
        stp_enabled: true
        recovery_timeout: 500
        priority: 64
        path_cost: 20000
    state: merged

# ── Task 3: Deleted — reset STP settings to factory defaults ─────────────
- name: Delete — reset STP settings to factory defaults
  extreme.fe.extreme_fe_stp:
    stp_instance: "0"
    config:
      - name: "PORT:1:8"
    state: deleted

# ── Task 4: Replaced — authoritative per-port config ─────────────────────
- name: Replaced — guard + edge only, rest to defaults
  extreme.fe.extreme_fe_stp:
    stp_instance: "0"
    config:
      - name: "PORT:1:5"
        bpdu_guard_enabled: true
        is_edge_port: true
    state: replaced

# ── Task 5: Overridden — enforce STP across instance ─────────────────────
- name: Overridden — reset unlisted ports, configure listed ones
  extreme.fe.extreme_fe_stp:
    stp_instance: "0"
    config:
      - name: "PORT:1:5"
        bpdu_guard_enabled: true
        is_edge_port: true
        recovery_timeout: 300
      - name: "PORT:1:6"
        bpdu_guard_enabled: true
        priority: 128
    state: overridden

# ── Task 6: Gathered — read STP per-port state ───────────────────────────
- name: Gathered — read specific port STP config
  extreme.fe.extreme_fe_stp:
    stp_instance: "0"
    config:
      - name: "PORT:1:5"
    state: gathered
  register: stp_state

# ── Task 7: Gathered — read all ports in STP instance ────────────────────
- name: Gathered — read all ports
  extreme.fe.extreme_fe_stp:
    stp_instance: "0"
    state: gathered
  register: stp_all

# ── Task 8: MSTP — set priority on a specific instance ───────────────────
- name: MSTP instance 2 — set port priority
  extreme.fe.extreme_fe_stp:
    stp_instance: "2"
    config:
      - name: "PORT:1:5"
        priority: 64
    state: merged

# ── Task 9: Lab port profile — guard + short recovery ────────────────────
- name: Lab port — guard on, fast recovery
  extreme.fe.extreme_fe_stp:
    stp_instance: "0"
    config:
      - name: "PORT:1:10"
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
        - STP per-port results.
    returned: always
    type: dict
    contains:
        stp_domain:
            description: STP domain name used.
            returned: always
            type: str
        interfaces:
            description:
                - List of per-port STP results.
                - On write operations (merged, replaced, overridden, deleted),
                  each element contains C(name), C(before), C(after), and
                  C(differences).
                - On gathered state, each element contains C(name) plus the
                  current STP settings fields directly
                  (C(bpdu_guard_enabled), C(recovery_timeout), etc.).
            returned: always
            type: list
            elements: dict
            contains:
                name:
                    description: Interface identifier (e.g. C(PORT:1:5)).
                    returned: always
                    type: str
                before:
                    description: STP settings before the change.
                    returned: when state is merged, replaced, overridden, or deleted
                    type: dict
                after:
                    description: STP settings after the change (re-read from device).
                    returned: when state is merged, replaced, overridden, or deleted
                    type: dict
                differences:
                    description: Fields that differ between current and desired state.
                    returned: when state is merged, replaced, overridden, or deleted
                    type: dict
                bpdu_guard_enabled:
                    description: Whether BPDU Guard is active on the port.
                    returned: when state is gathered
                    type: bool
                recovery_timeout:
                    description: Seconds before auto-recovery (0 means the port stays disabled).
                    returned: when state is gathered
                    type: int
                is_edge_port:
                    description: Whether the port is an STP edge port.
                    returned: when state is gathered
                    type: bool
                priority:
                    description: STP port priority.
                    returned: when state is gathered
                    type: int
                path_cost:
                    description: STP path cost.
                    returned: when state is gathered
                    type: int
                stp_enabled:
                    description: Whether STP is enabled on the port.
                    returned: when state is gathered
                    type: bool
                bpdu_origin:
                    description: Origin of BPDU Guard configuration (read-only from device).
                    returned: when state is gathered and available from device
                    type: str
        reset_ports:
            description: Ports reset during overridden pre-pass.
            returned: when state is overridden and ports were reset
            type: list
            elements: dict
"""

ARGUMENT_SPEC: Dict[str, Any] = {
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "name": {"type": "str", "required": True},
            "bpdu_guard_enabled": {"type": "bool"},
            "recovery_timeout": {"type": "int"},
            "is_edge_port": {"type": "bool"},
            "priority": {"type": "int"},
            "path_cost": {"type": "int"},
            "stp_enabled": {"type": "bool"},
        },
    },
    "stp_instance": {"type": "str", "required": True},
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
    # Keep old params in spec so Ansible doesn't reject them outright;
    # we validate and raise a clear error ourselves.
    # NOTE: no defaults here — a non-None value means the user
    # explicitly passed the old flat param.
    "interface": {"type": "str"},
    "interface_type": {"type": "str"},
    "interface_name": {"type": "str"},
    "bpdu_guard_enabled": {"type": "bool"},
    "recovery_timeout": {"type": "int"},
    "is_edge_port": {"type": "bool"},
    "priority": {"type": "int"},
    "path_cost": {"type": "int"},
    "stp_enabled": {"type": "bool"},
}

# Old flat parameters that are no longer valid at the top level.
_REMOVED_FLAT_PARAMS = frozenset(
    {
        "interface",
        "interface_type",
        "interface_name",
        "bpdu_guard_enabled",
        "recovery_timeout",
        "is_edge_port",
        "priority",
        "path_cost",
        "stp_enabled",
    }
)

KNOWN_INTERFACE_TYPES: Set[str] = {"PORT"}

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


# Port name pattern: slot:port format (e.g. "1:5", "1:10", "2:3").
# Used to validate that parsed interface names match the format the
# VOSS STP REST API expects.
_PORT_NAME_RE = _re.compile(r'^\d{1,3}:\d{1,3}$')


def parse_interface_name(name: str) -> Tuple[str, str]:
    """Parse 'PORT:1:5' or '1:5' into (type, name).

    Only physical ports in slot:port format are supported.
    When the type prefix is omitted, ``PORT`` is assumed.

    Raises ``FeStpError`` for:
    - Empty names
    - Unsupported prefixes (e.g. ``LAG:10``)
    - Names that don't match slot:port format (e.g. ``abc``, ``1:2:3``)
    """
    raw = name.strip()
    if not raw:
        raise FeStpError("Interface name must not be empty")

    if ":" in raw:
        prefix, rest = raw.split(":", 1)
        prefix_upper = prefix.strip().upper()
        if prefix_upper in KNOWN_INTERFACE_TYPES:
            port_name = rest.strip()
            if not _PORT_NAME_RE.match(port_name):
                raise FeStpError(
                    "Interface name '{0}' is not in valid slot:port format "
                    "(e.g. 'PORT:1:5' or '1:5').".format(name)
                )
            return prefix_upper, port_name
        # Check if it looks like an unsupported type prefix
        # (alphabetic prefix followed by colon)
        if prefix_upper.isalpha():
            raise FeStpError(
                "Unsupported interface type '{0}' in '{1}'. "
                "Only physical ports are supported for STP per-port "
                "settings (e.g. 'PORT:1:5' or '1:5').".format(
                    prefix_upper, name,
                )
            )

    # No recognised prefix — treat as bare slot:port
    if not _PORT_NAME_RE.match(raw):
        raise FeStpError(
            "Interface name '{0}' is not in valid slot:port format "
            "(e.g. 'PORT:1:5' or '1:5').".format(name)
        )
    return "PORT", raw


def _get_port_name_from_interface(iface_type: str, iface_name: str) -> str:
    """Convert parsed interface identity to STP port name format.

    The STP API uses the slot:port format (e.g. ``1:5``).
    Only PORT type interfaces are supported.
    """
    return iface_name


def _normalize_port_display_name(port_name: str) -> str:
    """Convert a device port key to the documented interface identifier format.

    Device port keys use ``slot:port`` format (e.g. ``1:5``) for physical
    ports.  The documented interface identifier format is ``PORT:1:5``.

    All ports returned by the STP API are physical ports, so this
    always produces the ``PORT:X:Y`` format.

    This ensures gathered output uses the same naming convention as
    ``config[].name`` and the RETURN documentation.
    """
    return "PORT:{0}".format(port_name)


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


# ─────────────────────────────────────────────────────────────────────────────
# BPDU Guard / STP parameter helpers
# ─────────────────────────────────────────────────────────────────────────────


def _validate_entry_params(entry: Dict[str, Any]) -> None:
    """Validate STP parameter values for a single config entry."""

    timeout = entry.get("recovery_timeout")
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

    priority = entry.get("priority")
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

    path_cost = entry.get("path_cost")
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


def _pre_validate_config_entries(
    config: List[Dict[str, Any]],
    stp_instance: str,
) -> List[Tuple[Dict[str, Any], str, str, str]]:
    """Pre-validate and parse all config entries before any device writes.

    Validates parameter ranges, parses interface names, detects
    duplicate port names, and applies instance-specific rules
    (e.g. ``is_edge_port`` is only valid for CIST/instance 0).

    Raises ``FeStpError`` if any entry is invalid so the module
    fails fast before making partial changes on the device.

    Returns a list of ``(entry, iface_type, iface_name, port_name)``
    tuples that callers can reuse to avoid re-parsing.
    """
    seen_ports: Dict[str, str] = {}  # port_name → first config name
    parsed: List[Tuple[Dict[str, Any], str, str, str]] = []
    is_cist = _is_cist(stp_instance)

    for entry in config:
        name = entry["name"]

        # Parse interface identifier (PORT:1:5 or bare 1:5)
        iface_type, iface_name = parse_interface_name(name)
        port_name = _get_port_name_from_interface(iface_type, iface_name)

        # Validate per-parameter ranges
        _validate_entry_params(entry)

        # is_edge_port is CIST-only; warn early if specified on MSTI
        if not is_cist and entry.get("is_edge_port") is not None:
            raise FeStpError(
                "'is_edge_port' is only valid for CIST (stp_instance 0). "
                "STP instance '{0}' is an MSTI instance. "
                "Remove 'is_edge_port' from the config entry for "
                "port '{1}'.".format(stp_instance, name)
            )

        # Detect duplicate port references within the same config list
        if port_name in seen_ports:
            raise FeStpError(
                "Duplicate port '{0}' in config (from '{1}' and '{2}'). "
                "Each port may only appear once per task.".format(
                    port_name, seen_ports[port_name], name,
                )
            )
        seen_ports[port_name] = name

        parsed.append((entry, iface_type, iface_name, port_name))

    return parsed


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


def _build_merged_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build a BPDU Guard payload with only user-supplied fields (merged)."""
    payload: Dict[str, Any] = {}

    for param, rest_field in BPDU_FIELD_MAP.items():
        value = entry.get(param)
        if value is None:
            continue
        if param == "bpdu_guard_enabled":
            payload[rest_field] = "GUARD" if value else "DISABLED"
        else:
            payload[rest_field] = value

    return payload


def _build_replaced_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build a full BPDU Guard payload, defaulting omitted fields (replaced)."""
    payload = dict(BPDU_FULL_DEFAULTS)

    for param, rest_field in BPDU_FIELD_MAP.items():
        value = entry.get(param)
        if value is None:
            continue
        if param == "bpdu_guard_enabled":
            payload[rest_field] = "GUARD" if value else "DISABLED"
        else:
            payload[rest_field] = value

    return payload


def _build_defaults_payload() -> Dict[str, Any]:
    """Return the payload that resets STP settings to factory defaults."""
    return dict(BPDU_FULL_DEFAULTS)


def _compute_diff(
    current: Dict[str, Any],
    desired: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Compare desired payload against current settings.

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


def _to_ansible_output(settings: Dict[str, Any]) -> Dict[str, Any]:
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
    config_port_names: Set[str],
    port_settings_map: Dict[str, Dict[str, Any]],
    default_domain: str,
    stp_instance: str = "0",
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Reset every non-listed port that deviates from STP factory defaults.

    *config_port_names* is the set of port names the user listed in
    ``config:``.  These are excluded from the reset pass.

    Individual port resets may fail for ports that the device refuses
    to modify (e.g. auto-sense ports reject STP changes).  Rather than
    failing the entire overridden operation, we record the failure as
    ``skipped=True`` in the port entry and continue.  The caller
    surfaces these as Ansible warnings.

    Returns ``(changed, reset_ports_list)``.
    """
    changed = False
    reset_ports: List[Dict[str, Any]] = []
    defaults_payload = _build_defaults_payload()

    # isEdgePort is CIST-only (instance 0).  On MSTI instances the
    # device silently ignores it, so strip it to avoid false diffs
    # and unnecessary PATCHes during the overridden pre-pass.
    if not _is_cist(stp_instance):
        defaults_payload.pop("isEdgePort", None)

    for port, settings in port_settings_map.items():
        if port in config_port_names:
            continue
        diff, patch = _compute_diff(settings, defaults_payload)
        if not diff:
            continue
        port_domain = settings.get("_domain") or default_domain
        port_entry: Dict[str, Any] = {
            "port": port,
            "before": _to_ansible_output(settings),
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
                port_entry["skipped"] = True
                port_entry["skip_reason"] = "Port %s: %s" % (port, to_text(exc))
                port_entry["after"] = port_entry["before"]
                reset_ports.append(port_entry)
                continue
            if isinstance(resp, dict):
                err = _extract_error(resp)
                if err:
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
        port_entry["after"] = _to_ansible_output(projected)
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
    """Send PATCH to the device for the target STP port."""
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
# Per-entry processing helper
# ─────────────────────────────────────────────────────────────────────────────


def _process_config_entry(
    connection: Connection,
    entry: Dict[str, Any],
    state: str,
    stp_instance: str,
    domain: str,
    port_settings_map: Dict[str, Dict[str, Any]],
    check_mode: bool,
    port_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Process a single config entry for merged/replaced/overridden/deleted states.

    Returns a per-interface result dict with name, before, after, differences.

    When *port_name* is supplied (from ``_pre_validate_config_entries()``),
    the function skips redundant parsing and validation.
    """
    if port_name is None:
        name = entry["name"]
        iface_type, iface_name = parse_interface_name(name)
        port_name = _get_port_name_from_interface(iface_type, iface_name)
        _validate_entry_params(entry)

    current = port_settings_map.get(port_name, {})

    iface_result: Dict[str, Any] = {
        "name": _normalize_port_display_name(port_name),
        "before": _to_ansible_output(current),
    }

    # Build desired payload based on state
    if state == STATE_MERGED:
        desired_payload = _build_merged_payload(entry)
    elif state in (STATE_REPLACED, STATE_OVERRIDDEN):
        desired_payload = _build_replaced_payload(entry)
    elif state == STATE_DELETED:
        desired_payload = _build_defaults_payload()
    else:
        desired_payload = {}

    # isEdgePort is CIST-only (instance 0).  On MSTI instances the
    # device silently ignores it, so strip it to avoid a false diff.
    if not _is_cist(stp_instance):
        desired_payload.pop("isEdgePort", None)

    if not desired_payload:
        iface_result["after"] = _to_ansible_output(current)
        iface_result["differences"] = {}
        iface_result["changed"] = False
        return iface_result

    # Compute diff
    differences, patch_payload = _compute_diff(current, desired_payload)

    if not differences:
        iface_result["after"] = _to_ansible_output(current)
        iface_result["differences"] = {}
        iface_result["changed"] = False
        return iface_result

    iface_result["differences"] = differences
    iface_result["changed"] = True

    if check_mode:
        projected = dict(current)
        projected.update(patch_payload)
        iface_result["after"] = _to_ansible_output(projected)
        return iface_result

    # Apply PATCH — use the per-port domain stored by
    # _build_port_settings_map() so that ports from different STP
    # domain objects are PATCHed on the correct path.
    patch_domain = current.get("_domain") or domain
    _apply_stp_patch(connection, patch_domain, port_name, patch_payload)

    # Provisional 'after' from projected state; the caller performs a
    # bulk re-read after all entries and overwrites this with the
    # actual device state for accuracy.
    projected = dict(current)
    projected.update(patch_payload)
    iface_result["after"] = _to_ansible_output(projected)
    return iface_result


# ─────────────────────────────────────────────────────────────────────────────
# State handler functions — config list pattern
# ─────────────────────────────────────────────────────────────────────────────


def _handle_config_states(
    module: AnsibleModule, connection: Connection, state: str
) -> Dict[str, Any]:
    """Handle merged, replaced, deleted states with config list.

    Processing order:
      1. Pre-validate every config entry (ranges, names, duplicates)
         so the module fails fast before touching the device.
      2. Fetch current STP domains/port settings from the device.
      3. Apply PATCHes for each entry that differs.
      4. Bulk re-read device state and reconcile each interface's
         ``after`` with the actual values the device reports.
    """
    config = module.params.get("config") or []
    if not config:
        raise FeStpError("'config' must not be empty for state '{0}'".format(state))
    stp_instance = _validate_stp_instance(module.params["stp_instance"])
    check_mode = module.check_mode

    # ── Step 1: Pre-validate all entries before any device writes ────
    parsed_entries = _pre_validate_config_entries(config, stp_instance)

    # ── Step 2: Fetch current STP state from the device ──────────────
    domains = _fetch_stp_domains(module, connection)
    default_domain, port_settings_map = _build_port_settings_map(
        domains,
        target_instance=stp_instance,
    )
    if not default_domain:
        raise FeStpError(
            "STP instance '{0}' not found on the device.".format(stp_instance)
        )

    # ── Step 3: Apply changes per entry ──────────────────────────────
    overall_changed = False
    interfaces: List[Dict[str, Any]] = []

    for entry, _iface_type, _iface_name, port_name in parsed_entries:
        result = _process_config_entry(
            connection,
            entry,
            state,
            stp_instance,
            default_domain,
            port_settings_map,
            check_mode,
            port_name=port_name,
        )
        if result.pop("changed", False):
            overall_changed = True
        interfaces.append(result)

    # ── Step 4: Bulk re-read for accurate 'after' values ─────────────
    # The per-entry loop uses projected values; a single GET after all
    # PATCHes ensures 'after' reflects what the device actually stored
    # (it may normalise or reject certain field values).
    if overall_changed and not check_mode:
        domains = _fetch_stp_domains(module, connection)
        _, refreshed_map = _build_port_settings_map(
            domains, target_instance=stp_instance,
        )
        for (_, _it, _in, port_name), iface in zip(parsed_entries, interfaces):
            refreshed = refreshed_map.get(port_name)
            if refreshed is not None:
                iface["after"] = _to_ansible_output(refreshed)

    return {
        "changed": overall_changed,
        "stp": {
            "stp_domain": default_domain,
            "interfaces": interfaces,
        },
    }


def _handle_overridden(module: AnsibleModule, connection: Connection) -> Dict[str, Any]:
    """Handle overridden state: reset unlisted ports, then apply replaced per entry.

    Processing order:
      1. Pre-validate every config entry (ranges, names, duplicates)
         so the module fails fast before making any device changes.
      2. Fetch current STP domains/port settings from the device.
      3. Phase 1 — reset unlisted ports to factory defaults.
      4. Phase 2 — apply ``replaced`` treatment per config entry.
      5. Bulk re-read device state and reconcile ``after`` values.
    """
    config = module.params.get("config") or []
    if not config:
        raise FeStpError("'config' must not be empty for state 'overridden'")
    stp_instance = _validate_stp_instance(module.params["stp_instance"])
    check_mode = module.check_mode

    # ── Step 1: Pre-validate all entries before any device changes ───
    # This ensures the module fails fast if any entry has invalid
    # parameters, an unparseable name, or a duplicate port — before
    # the reset pass touches the device.
    parsed_entries = _pre_validate_config_entries(config, stp_instance)

    # ── Step 2: Fetch current STP state from the device ──────────────
    domains = _fetch_stp_domains(module, connection)
    default_domain, port_settings_map = _build_port_settings_map(
        domains,
        target_instance=stp_instance,
    )
    if not default_domain:
        raise FeStpError(
            "STP instance '{0}' not found on the device.".format(stp_instance)
        )

    overall_changed = False

    # Build set of config port names for exclusion from reset
    # (reuse parsed data from pre-validation to avoid re-parsing)
    config_port_names: Set[str] = {
        port_name for _, _, _, port_name in parsed_entries
    }

    # ── Step 3 (Phase 1): Reset unlisted ports to defaults ───────────
    reset_changed, reset_ports = _overridden_reset_ports(
        module,
        connection,
        config_port_names,
        port_settings_map,
        default_domain,
        stp_instance=stp_instance,
    )
    if reset_changed:
        overall_changed = True

    # Re-fetch after resets so current values reflect device state
    if reset_changed and not check_mode:
        domains = _fetch_stp_domains(module, connection)
        _, port_settings_map = _build_port_settings_map(
            domains,
            target_instance=stp_instance,
        )

    # ── Step 4 (Phase 2): Apply replaced treatment per config entry ──
    interfaces: List[Dict[str, Any]] = []
    for entry, _iface_type, _iface_name, port_name in parsed_entries:
        result = _process_config_entry(
            connection,
            entry,
            STATE_OVERRIDDEN,
            stp_instance,
            default_domain,
            port_settings_map,
            check_mode,
            port_name=port_name,
        )
        if result.pop("changed", False):
            overall_changed = True
        interfaces.append(result)

    # ── Step 5: Bulk re-read for accurate 'after' values ─────────────
    if overall_changed and not check_mode:
        domains = _fetch_stp_domains(module, connection)
        _, refreshed_map = _build_port_settings_map(
            domains, target_instance=stp_instance,
        )
        # Refresh per-interface 'after' from device state
        for (_, _it, _in, port_name), iface in zip(parsed_entries, interfaces):
            refreshed = refreshed_map.get(port_name)
            if refreshed is not None:
                iface["after"] = _to_ansible_output(refreshed)
        # Also refresh reset_ports 'after' values
        for port_entry in reset_ports:
            if not port_entry.get("skipped"):
                port_name = port_entry["port"]
                refreshed = refreshed_map.get(port_name)
                if refreshed is not None:
                    port_entry["after"] = _to_ansible_output(refreshed)

    stp_result: Dict[str, Any] = {
        "stp_domain": default_domain,
        "interfaces": interfaces,
    }
    if reset_ports:
        stp_result["reset_ports"] = reset_ports

    # Surface skipped ports as Ansible warnings
    skipped = [p for p in reset_ports if p.get("skipped")]
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

    return {
        "changed": overall_changed,
        "stp": stp_result,
    }


def _handle_gathered(module: AnsibleModule, connection: Connection) -> Dict[str, Any]:
    """Handle gathered state: return current STP config without changes.

    When ``config`` is provided, only the listed ports are gathered.
    When ``config`` is omitted, all ports in the STP instance are
    returned with their names normalised to the ``PORT:X:Y``
    format used elsewhere in this module.
    """
    config = module.params.get("config") or []
    stp_instance = _validate_stp_instance(module.params["stp_instance"])

    # Fetch STP domains
    domains = _fetch_stp_domains(module, connection)
    default_domain, port_settings_map = _build_port_settings_map(
        domains,
        target_instance=stp_instance,
    )
    if not default_domain:
        raise FeStpError(
            "STP instance '{0}' not found on the device.".format(stp_instance)
        )

    interfaces: List[Dict[str, Any]] = []

    if config:
        # Gather specific ports requested by the user
        for entry in config:
            name = entry["name"]
            iface_type, iface_name = parse_interface_name(name)
            port_name = _get_port_name_from_interface(iface_type, iface_name)
            current = port_settings_map.get(port_name)
            if current is None:
                module.warn(
                    "Port '{0}' (resolved to '{1}') was not found in STP "
                    "instance '{2}'. Returning empty settings.".format(
                        name, port_name, stp_instance,
                    )
                )
                current = {}
            iface_data = _to_ansible_output(current)
            iface_data["name"] = _normalize_port_display_name(port_name)
            interfaces.append(iface_data)
    else:
        # Gather all ports in the STP instance.
        # Normalise port names to the documented identifier format
        # (PORT:1:5) so output is consistent with config[].name.
        # Sort by port name for deterministic output across runs.
        for port_name, settings in sorted(port_settings_map.items()):
            iface_data = _to_ansible_output(settings)
            iface_data["name"] = _normalize_port_display_name(port_name)
            interfaces.append(iface_data)

    return {
        "changed": False,
        "stp": {
            "stp_domain": default_domain,
            "interfaces": interfaces,
        },
    }


def run_module() -> None:
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
    )

    state = module.params["state"]

    # ── Reject old flat-parameter usage ──
    flat_used = any(module.params.get(p) is not None for p in _REMOVED_FLAT_PARAMS)
    if flat_used:
        module.fail_json(
            msg="Flat parameters (interface, interface_type, interface_name, "
            "bpdu_guard_enabled, recovery_timeout, "
            "is_edge_port, priority, path_cost, stp_enabled) are no longer supported. "
            "Use 'config: list' instead. Example: "
            "config: [{name: 'PORT:1:5', bpdu_guard_enabled: true, priority: 128}]"
        )

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == STATE_GATHERED:
            result = _handle_gathered(module, connection)
        elif state == STATE_OVERRIDDEN:
            result = _handle_overridden(module, connection)
        elif state in (STATE_MERGED, STATE_REPLACED, STATE_DELETED):
            result = _handle_config_states(module, connection, state)
        else:
            raise FeStpError(f"Unsupported state '{state}'")
        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeStpError as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
