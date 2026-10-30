# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Ansible module to gather ExtremeNetworks Fabric Engine facts via HTTPAPI."""

from __future__ import annotations

DOCUMENTATION = r"""
module: extreme_fe_facts
short_description: Gather facts from ExtremeNetworks Fabric Engine switches
version_added: "1.0.0"
description:
- Collect state, hardware, interface, configuration, and neighbor facts from
  ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI plugin.
- Optionally gather structured network resource data for interfaces, VLANs, routing,
  and other subsystems to support idempotent automation plays.
author:
- Bjorn Haas (@bhaas_extr)
notes:
- Tested against Fabric Engine Version 9.3.2.
- Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI connection plugin.
- Secrets are never returned. SNMP community strings, SNMPv3 passwords, web server and HTTP proxy
  passwords, and OSPF authentication keys are removed before the facts are stored, so they never
  reach hostvars or a fact cache. Settings such as the authentication type are kept.
- If the switch does not support a feature (for example PoE on a switch without PoE) or cannot return
  its data, that part is left out of the facts with a warning naming it, and all other facts are still
  gathered.
- If the switch cannot be reached, rejects the login, or answers with any other unexpected error (for
  example a server error or too many requests), the task fails and no facts are set, not even the ones
  already read, so you never work with an incomplete set. The error message gives the HTTP status code
  when there is one. Check the connection settings and credentials in your inventory, then run the task
  again.
- Device messages are not copied into warnings or errors, because they could contain a secret. Check
  the switch directly for the details.
options:
  gather_subset:
    description:
    - List of fact subsets to collect. Use C(all) to gather every supported subset.
      Prefix a subset with C(!) to exclude it when C(all) is specified.
    - C(min) is the same as C(default), the minimal set. C(!all) gathers that minimal set plus
      only the subsets listed next to it, as in other Ansible network facts modules. It also
      overrides C(all) in the same list.
    - "Supported subsets: C(default), C(hardware), C(interfaces), C(config), C(neighbors)."
    type: list
    elements: str
    default: [default]
  gather_network_resources:
    description:
    - List of network resource names to collect. Use C(all) to gather every supported
      resource. Resources that are unavailable on the device are ignored.
    - "Supported resources: C(interfaces), C(l2_interfaces), C(l3_interfaces), C(vlans),
      C(lag_interfaces), C(vrfs), C(static_routes), C(ospfv2), C(vrrp), C(lldp), C(cdp),
      C(ntp), C(dns), C(snmp_server), C(syslog), C(anycast_gateway), C(isid)."
    type: list
    elements: str
requirements:
- ansible.netcommon
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
# Task 1: Gather default facts
# Description:
#   - Collect basic device information (hostname, serial, version, uptime)
#   - Default behavior when no subsets specified
# -------------------------------------------------------------------------
# - name: "Task 1: Gather default Fabric Engine facts"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect basic device information
  extreme.fe.extreme_fe_facts:
  register: facts

# -------------------------------------------------------------------------
# Task 2: Gather hardware facts only
# Description:
#   - Selectively gather hardware-related facts
#   - Returns chassis, modules, fans, power supplies, memory info
# -------------------------------------------------------------------------
# - name: "Task 2: Gather hardware facts only"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect hardware inventory
  extreme.fe.extreme_fe_facts:
    gather_subset:
      - hardware
  register: fe_hw

# -------------------------------------------------------------------------
# Task 3: Gather configuration and network resources
# Description:
#   - Combine gather_subset with gather_network_resources
#   - Useful for auditing or backup purposes
# -------------------------------------------------------------------------
# - name: "Task 3: Gather configuration facts and VLAN/L3 resources"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect config and resource data
  extreme.fe.extreme_fe_facts:
    gather_subset:
      - config
      - neighbors
    gather_network_resources:
      - vlans
      - l3_interfaces
  register: device_data

# -------------------------------------------------------------------------
# Task 4: Gather all facts and resources
# Description:
#   - Collect complete set of available facts using 'all' keyword
#   - Comprehensive view but may take longer to execute
# -------------------------------------------------------------------------
# - name: "Task 4: Gather all facts and resources"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect full set of facts
  extreme.fe.extreme_fe_facts:
    gather_subset: [all]
    gather_network_resources: [all]
  register: full_facts
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made. Always C(false).
  returned: always
  type: bool
ansible_facts:
  description: Structured fact data collected from the device.
  returned: always
  type: dict
  contains:
    extreme_fe_facts:
      description: Fact data grouped by subset name.
      type: dict
    extreme_fe_facts_network_resources:
      description: Network resource data keyed by resource name.
      type: dict
    extreme_fe_facts_gathered_subsets:
      description: List of fact subsets that were gathered.
      type: list
    extreme_fe_facts_gathered_network_resources:
      description: Network resources that were successfully gathered.
      type: list
"""

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import http_status

ARGUMENT_SPEC = {
    "gather_subset": {"type": "list", "elements": "str", "default": ["default"]},
    "gather_network_resources": {"type": "list", "elements": "str"},
}

VALID_SUBSETS: set[str] = {"default", "hardware", "interfaces", "config", "neighbors"}
VALID_RESOURCES: set[str] = {
    "interfaces",
    "l2_interfaces",
    "l3_interfaces",
    "vlans",
    "lag_interfaces",
    "vrfs",
    "static_routes",
    "ospfv2",
    "vrrp",
    "lldp",
    "cdp",
    "ntp",
    "dns",
    "snmp_server",
    "syslog",
    "anycast_gateway",
    "isid",
}

PORT_NAME_KEYS: set[str] = {
    "port",
    "portid",
    "portname",
    "ifname",
    "interface",
    "interfacename",
    "lagportname",
    "memberport",
    "untaggedport",
}
PORT_LIST_KEYS: set[str] = {
    "ports",
    "memberports",
    "taggedports",
    "untaggedports",
    "allowedports",
}

# Secret fields of the payloads read by this module (OpenAPI schemas):
#   /v0|v1/configuration/snmp: v1v2.access[].community,
#       v3.access[].authenticationPassword and encryptionPassword (Secret: isEncrypted + value)
#   /v0/configuration/system-services: webServer.roPassword, webServer.rwaPassword,
#       iqagent.httpProxy.password (isEncrypted + value)
#   /v0/configuration/ospf: interface[].auth.keyString, virtual_circuits[].auth.keyString
# "secret" and "passphrase" are defensive. Keys are matched with '-'/'_' removed,
# case-insensitively. A key named in SECRET_KEYS, or ending in "password", is a secret:
# a scalar value is removed with its key, a dict value keeps only its SECRET_FLAG_KEYS.
SECRET_KEYS: set[str] = {"community", "keystring", "secret", "passphrase"}
SECRET_FLAG_KEYS: set[str] = {"isencrypted"}

_VRF_NAME_CACHE: set[str] | None = None

# Warnings collected while reading the device, reported by main().
_WARNINGS: list[str] = []


class FeFactsError(Exception):
    """Base exception for the extreme_fe_facts module."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> dict[str, Any]:
        data: dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


_STATUS_KEYS = ("errorCode", "statusCode", "code", "status")


def _parse_code(value: Any) -> int | None:
    """A numeric status as an int (digit strings trimmed of whitespace), or None."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _status_codes(entry: dict[str, Any]) -> list[int]:
    """Every numeric status of an entry (errorCode, statusCode, code, status), in that order."""
    return [code for code in (_parse_code(entry.get(key)) for key in _STATUS_KEYS) if code is not None]


def _is_not_found_response(payload: Any | None) -> bool:
    """True for an answer that only says the resource does not exist, which is skipped silently.

    That is a status of 404 with no other failure status next to it, or no
    status at all with a "not found" / "does not exist" message. Any other
    failure status (for example a 500 whose message mentions "not found", or
    a statusCode 500 next to an errorCode 404) is an error document instead, left out with a
    warning by _http_get(). A list, or a responses/items wrapper, counts when
    every entry is a not-found answer and the wrapper itself carries no other
    failure status: the all-404 multi-status answer the
    httpapi plugin used to turn into an HTTP 404 before 207 bodies were passed
    through to this module.
    """
    if isinstance(payload, list):
        return bool(payload) and all(_is_not_found_response(entry) for entry in payload)
    if not isinstance(payload, dict):
        return False
    codes = _status_codes(payload)
    # Every numeric status field counts, not just the first: an errorCode 404
    # next to a statusCode 500 is a server failure, not an absent resource. A
    # wrapper's own failure status also comes before its entries: a 500
    # wrapping 404 entries is an error. A 207 (or other non-error) wrapper, or
    # a 404 one, is decided by its entries.
    if any(code >= 400 and code != 404 for code in codes):
        return False
    for wrapper in ("responses", "items"):
        if isinstance(payload.get(wrapper), list):
            return _is_not_found_response(payload[wrapper])
    if codes:
        return 404 in codes
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    if isinstance(message, str):
        lowered = message.lower()
        if "not found" in lowered or "does not exist" in lowered:
            return True
    return False


def _error_document(payload: Any | None, *, text_entries_ok: bool = False) -> str | None:
    """Describe an error document returned with a 2xx status, or return None.

    An error document carries errorCode, statusCode, code or status >= 400, a non-empty
    errors list, a singular error, or an errorMessage without any status code
    (as the httpapi plugin's multi-status parser counts it), instead of the
    requested data. A list is one when any of its entries is, and so is a
    responses or items wrapper whose list holds one (the multi-status shapes
    the plugin parses), at any depth. The device's free-text message is left
    out of the description, as it could quote a secret.
    """
    if isinstance(payload, list):
        for index, entry in enumerate(payload):
            # A text entry at a response boundary (the answer's own array, a nested
            # array or a responses/items wrapper) is device text, for example
            # ["Invalid community: ..."], unless the endpoint's schema is an array
            # of strings (*text_entries_ok*, see TEXT_LIST_PATHS). Strings inside a
            # configuration object, such as view[].oids, are not reached here.
            if isinstance(entry, str):
                if text_entries_ok:
                    continue
                return f"entry {index}: a text entry"
            # Every other entry, nested lists included ([[{...}]]).
            error = _error_document(entry)
            if error:
                return f"entry {index}: {error}"
        return None
    if not isinstance(payload, dict):
        return None
    # The status keys the httpapi plugin's multi-status parser reads. 'status'
    # matters for a 207 passed through (multi_status_passthrough), which that
    # parser no longer checks; the fact endpoints' own 'status' fields are text
    # (service states), never a numeric code. Parsed by _parse_code(), so a
    # whitespace-padded " 500 " is a code too.
    codes = _status_codes(payload)
    has_code = bool(codes)
    # The object's own failure status comes first, as in _is_not_found_response():
    # a 500 wrapping 404 entries is reported as the 500. A 404 of its own is
    # reported only when no entry carries an error of its own.
    failure = next((code for code in codes if code >= 400 and code != 404), None)
    if failure is not None:
        return f"error {failure}"
    for wrapper in ("responses", "items"):
        if isinstance(payload.get(wrapper), list):
            error = _error_document(payload[wrapper])
            if error:
                return f"{wrapper} {error}"
    if 404 in codes:
        return "error 404"
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return f"{len(errors)} error(s) in the errors list"
    # The singular form ({"error": {...}} or {"error": "..."}) occurs on Fabric
    # Engine too; its content is device text, so it is not echoed.
    if payload.get("error"):
        return "an error object"
    if payload.get("errorMessage") and not has_code:
        return "an error message"
    return None


def _is_secret_key(key: Any) -> bool:
    """Return True when a payload key holds a secret value."""
    if not isinstance(key, str):
        return False
    sanitized = key.replace("-", "").replace("_", "").lower()
    return sanitized in SECRET_KEYS or sanitized.endswith("password")


def _redact_secrets(payload: Any) -> Any:
    """Return a copy of payload with every secret leaf removed (not masked).

    Non-secret siblings are kept, e.g. the auth type and keyId next to an OSPF
    keyString, communityIsEncrypted, and the isEncrypted flag of a password object.
    """
    if isinstance(payload, dict):
        redacted: dict[Any, Any] = {}
        for key, value in payload.items():
            if not _is_secret_key(key):
                redacted[key] = _redact_secrets(value)
                continue
            if isinstance(value, dict):
                flags = {
                    k: v
                    for k, v in value.items()
                    if isinstance(k, str) and k.lower() in SECRET_FLAG_KEYS and not isinstance(v, (dict, list))
                }
                if flags:
                    redacted[key] = flags
        return redacted
    if isinstance(payload, list):
        return [_redact_secrets(item) for item in payload]
    return payload


def _normalize_subset_requests(values: Iterable[str] | None) -> set[str]:
    if not values:
        return {"default"}
    # Subsets named explicitly, kept apart from the expansion of 'all', which
    # '!all' discards: [all, '!all', hardware] is the minimal set plus hardware.
    includes: set[str] = set()
    excludes: set[str] = set()
    saw_all = False
    minimal = False
    for raw in values:
        if raw is None:
            continue
        item = str(raw).strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered == "all":
            saw_all = True
            continue
        if lowered in ("min", "default"):
            # 'min' is the Ansible network-facts name of the minimal set.
            includes.add("default")
            continue
        if lowered == "!all":
            # The Ansible convention: the minimal set ('default') plus only the
            # subsets named explicitly next to it.
            minimal = True
            continue
        if lowered.startswith("!"):
            name = lowered[1:]
            if name not in VALID_SUBSETS:
                raise FeFactsError(f"Unsupported subset '{item}'")
            excludes.add(name)
            continue
        if lowered not in VALID_SUBSETS:
            raise FeFactsError(f"Unsupported subset '{item}'")
        includes.add(lowered)
    if minimal:
        # '!all' wins over 'all': the minimal set plus the explicit subsets.
        selected = includes | {"default"}
    elif saw_all:
        selected = set(VALID_SUBSETS)
    else:
        selected = includes or {"default"}
    # 'all' with every subset excluded gathers nothing (an empty set).
    return selected - excludes


def _normalize_resource_requests(values: Iterable[str] | None) -> set[str]:
    if not values:
        return set()
    includes: set[str] = set()
    excludes: set[str] = set()
    saw_all = False
    for raw in values:
        if raw is None:
            continue
        item = str(raw).strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered == "all":
            saw_all = True
            includes.update(VALID_RESOURCES)
            continue
        if lowered.startswith("!"):
            name = lowered[1:]
            if name not in VALID_RESOURCES:
                raise FeFactsError(f"Unsupported network resource '{item}'")
            excludes.add(name)
            continue
        if lowered not in VALID_RESOURCES:
            raise FeFactsError(f"Unsupported network resource '{item}'")
        includes.add(lowered)
    if saw_all:
        includes.update(VALID_RESOURCES)
    result = includes - excludes
    return result


def _http_status(code: Any) -> str:
    """Return ' (HTTP <code>)' for a failed request, or '' when there is no status code."""
    return f" (HTTP {code})" if code is not None else ""


# HTTP statuses that mean the device does not serve or refuses one endpoint (a
# switch without PoE answers its PoE endpoint with 400; 403 a role without
# access; 405/410/501 an endpoint this release does not implement). Such an
# endpoint is left out with a warning. Any other status (401, 408, 429 and the
# other 5xx: an expired session, throttling, a failing REST service) fails the
# task: skipping it would return incomplete facts as a success. 404 is handled
# on its own (left out without a warning).
SKIPPABLE_HTTP_STATUSES = frozenset({400, 403, 405, 410, 501})

# Endpoints whose documented answer is an array of strings (OpenAPI), so text
# entries of that top-level array are data, not device error text.
TEXT_LIST_PATHS = ("/v0/configuration/system/images",)


def _http_get(connection: Connection, path: str) -> Any | None:
    try:
        # A 207 answer is returned as data rather than raised, so a multi-status
        # error is skipped with a warning below like any other error document,
        # instead of failing the whole facts task. Other failed requests still raise.
        data = connection.send_request(None, path=path, method="GET", multi_status_passthrough=True)
    except ConnectionError as exc:
        code = getattr(exc, "code", None)
        if code == 404:
            return None
        status = http_status(code)
        if status in SKIPPABLE_HTTP_STATUSES:
            # The device answered, but refused this endpoint (for example one a
            # switch without PoE does not serve): it is left out with a warning,
            # like an error document, instead of failing every other fact. The
            # exception text and .err can quote the device's response, so only
            # the code is kept.
            _WARNINGS.append(f"Skipped {path}, the device answered{_http_status(status)}")
            return None
        # Any other HTTP status (an expired session, throttling, a server error)
        # or no answer at all (a lost connection; no code, or a negative JSON-RPC
        # code of the persistent connection): the facts would be incomplete.
        raise FeFactsError(
            f"Failed to retrieve data from {path}{_http_status(status)}",
            details={"status_code": status} if status is not None else {},
        )
    if data is None:
        return None
    if _is_not_found_response(data):
        return None
    error = _error_document(data, text_entries_ok=path in TEXT_LIST_PATHS)
    if error:
        # Treated like a failed read: the endpoint is left out, as for a 404.
        _WARNINGS.append(f"Skipped {path}, the device returned an error document ({error})")
        return None
    if not isinstance(data, (dict, list)):
        # Text the plugin could not parse as JSON (or a bare scalar) may quote a secret that
        # _redact_secrets() cannot find. Every endpoint read here returns a JSON object or list.
        _WARNINGS.append(f"{path} returned an unstructured response; left out of the facts")
        return None
    # Every payload passes here before it can reach ansible_facts.
    return _redact_secrets(data)


def _normalize_port_name(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    if not trimmed:
        return trimmed
    prefix = ""
    remainder = trimmed
    if ":" in trimmed:
        maybe_prefix, maybe_rest = trimmed.split(":", 1)
        if maybe_prefix.isalpha() and maybe_rest:
            prefix = f"{maybe_prefix.upper()}:" if maybe_prefix else ""
            remainder = maybe_rest
    parts = [part for part in re.split(r"[:/\\]+", remainder) if part]
    if not parts:
        normalized = remainder
    else:
        normalized = ":".join(part.strip() for part in parts)
    if prefix:
        return prefix + normalized
    return normalized


def _normalize_ports(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key, value in list(payload.items()):
            sanitized = key.replace("-", "").replace("_", "").lower()
            if sanitized in PORT_NAME_KEYS and isinstance(value, str):
                payload[key] = _normalize_port_name(value)
            elif sanitized in PORT_LIST_KEYS and isinstance(value, list):
                normalized_list: list[Any] = []
                for item in value:
                    if isinstance(item, str):
                        normalized_list.append(_normalize_port_name(item))
                    else:
                        normalized_list.append(_normalize_ports(item))
                payload[key] = normalized_list
            else:
                payload[key] = _normalize_ports(value)
        return payload
    if isinstance(payload, list):
        return [_normalize_ports(item) for item in payload]
    return payload


def _normalize_payload(payload: Any | None) -> Any | None:
    if payload is None:
        return None
    if isinstance(payload, (dict, list)):
        return _normalize_ports(payload)
    return payload


def _merge_dicts(**kwargs: Any | None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is not None:
            data[key] = value
    return data


def _get_vrf_names(connection: Connection) -> set[str]:
    global _VRF_NAME_CACHE
    if _VRF_NAME_CACHE is not None:
        return set(_VRF_NAME_CACHE)
    data = _http_get(connection, "/v0/configuration/vrf")
    names: set[str] = set()
    if isinstance(data, dict) and "name" not in data:
        # Wrapper object: the VRF entries are in its list values.
        for value in data.values():
            if isinstance(value, list):
                names.update(_extract_vrf_names(value))
    else:
        names.update(_extract_vrf_names(data))
    if not names:
        names.add("GlobalRouter")
    _VRF_NAME_CACHE = names
    return set(names)


def _extract_vrf_names(payload: Any) -> set[str]:
    """Return the name of each top-level VRF entry of a GET /v0/configuration/vrf payload.

    The payload is a list of VRF objects (OpenAPI l3protocol/vrf). Only their
    name is taken, never nested strings such as portList entries or the names
    in segmentedVrfList.
    """
    names: set[str] = set()
    entries = payload if isinstance(payload, list) else [payload]
    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name:
                names.add(name)
    return names


def gather_default_subset(connection: Connection) -> dict[str, Any]:
    system = _normalize_payload(_http_get(connection, "/v0/state/system"))
    services = _normalize_payload(_http_get(connection, "/v0/state/system-services"))
    reboot = _normalize_payload(_http_get(connection, "/v0/state/system/reboot"))
    return _merge_dicts(system=system, system_services=services, reboot=reboot)


def gather_hardware_subset(connection: Connection) -> dict[str, Any]:
    fans = _normalize_payload(_http_get(connection, "/v0/state/system/fans"))
    power = _normalize_payload(_http_get(connection, "/v0/state/system/power-supplies"))
    poe = _normalize_payload(_http_get(connection, "/v0/state/poe-power/ports"))
    return _merge_dicts(fans=fans, power_supplies=power, poe=poe)


def gather_interfaces_subset(connection: Connection) -> dict[str, Any]:
    ports_payload = _http_get(connection, "/v1/state/ports")
    if ports_payload is None:
        ports_payload = _http_get(connection, "/v0/state/ports")
    ports = _normalize_payload(ports_payload)
    capabilities = _normalize_payload(_http_get(connection, "/v0/state/capabilities/system/ports"))
    return _merge_dicts(ports=ports, port_capabilities=capabilities)


def gather_config_subset(connection: Connection) -> dict[str, Any]:
    services = _normalize_payload(_http_get(connection, "/v0/configuration/system-services"))
    mgmt_payload = _http_get(connection, "/v1/configuration/mgmt-interface")
    if mgmt_payload is None:
        mgmt_payload = _http_get(connection, "/v0/configuration/mgmt-interface")
    mgmt = _normalize_payload(mgmt_payload)
    images = _normalize_payload(_http_get(connection, "/v0/configuration/system/images"))
    isids = _gather_isid_data(connection)
    return _merge_dicts(
        system_services=services,
        mgmt_interface=mgmt,
        images=images,
        isids=isids,
    )


def gather_neighbors_subset(connection: Connection) -> dict[str, Any]:
    lldp = _normalize_payload(_http_get(connection, "/v0/state/lldp"))
    cdp = _normalize_payload(_http_get(connection, "/v0/state/cdp"))
    fabric_attach = _normalize_payload(_http_get(connection, "/v0/state/fabric-attach"))
    return _merge_dicts(lldp=lldp, cdp=cdp, fabric_attach=fabric_attach)


SUBSET_HANDLERS = {
    "default": gather_default_subset,
    "hardware": gather_hardware_subset,
    "interfaces": gather_interfaces_subset,
    "config": gather_config_subset,
    "neighbors": gather_neighbors_subset,
}


def gather_interfaces_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/ports"))


def gather_l2_interfaces_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/vlan/ports"))


def gather_l3_interfaces_resource(connection: Connection) -> dict[str, Any]:
    payload = _http_get(connection, "/v0/configuration/vlan")
    if payload is None:
        return {}

    normalized = _normalize_payload(payload)
    entries: list[dict[str, Any]]
    if isinstance(normalized, list):
        entries = [item for item in normalized if isinstance(item, dict)]
    elif isinstance(normalized, dict):
        entries = [normalized]
    else:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for item in entries:
        vrf = str(item.get("vrName") or item.get("vr") or item.get("vr_name") or item.get("vrf") or "GlobalRouter")
        vlan_id = item.get("id") or item.get("vlanId") or item.get("vlan_id")
        key = str(vlan_id) if vlan_id is not None else str(item.get("name") or "unknown")
        result.setdefault(vrf, {})[key] = item

    return result


def gather_vlans_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/vlan"))


def gather_lag_interfaces_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/lag"))


def gather_vrfs_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/vrf"))


def gather_static_routes_resource(connection: Connection) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for vrf in sorted(_get_vrf_names(connection)):
        path = f"/v0/configuration/vrf/{quote(vrf, safe='')}/route"
        result[vrf] = _normalize_payload(_http_get(connection, path))
    return result


def gather_ospfv2_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/ospf"))


def gather_vrrp_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/vrrp"))


def gather_lldp_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/lldp"))


def gather_cdp_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/cdp"))


def gather_ntp_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/ntp"))


def gather_dns_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/dns"))


def gather_snmp_resource(connection: Connection) -> Any:
    payload = _http_get(connection, "/v1/configuration/snmp")
    if payload is None:
        payload = _http_get(connection, "/v0/configuration/snmp")
    return _normalize_payload(payload)


def gather_syslog_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/syslog"))


def gather_anycast_gateway_resource(connection: Connection) -> Any:
    return _normalize_payload(_http_get(connection, "/v0/configuration/anycast-gateway"))


def gather_isid_resource(connection: Connection) -> Any:
    return _gather_isid_data(connection)


RESOURCE_HANDLERS = {
    "interfaces": gather_interfaces_resource,
    "l2_interfaces": gather_l2_interfaces_resource,
    "l3_interfaces": gather_l3_interfaces_resource,
    "vlans": gather_vlans_resource,
    "lag_interfaces": gather_lag_interfaces_resource,
    "vrfs": gather_vrfs_resource,
    "static_routes": gather_static_routes_resource,
    "ospfv2": gather_ospfv2_resource,
    "vrrp": gather_vrrp_resource,
    "lldp": gather_lldp_resource,
    "cdp": gather_cdp_resource,
    "ntp": gather_ntp_resource,
    "dns": gather_dns_resource,
    "snmp_server": gather_snmp_resource,
    "syslog": gather_syslog_resource,
    "anycast_gateway": gather_anycast_gateway_resource,
    "isid": gather_isid_resource,
}


def _gather_isid_data(connection: Connection) -> dict[str, Any]:
    result: dict[str, Any] = {}

    all_isids = _normalize_payload(_http_get(connection, "/v0/configuration/spbm/l2/isid"))
    if all_isids is not None:
        result["list"] = all_isids

    cvlan = _normalize_payload(_http_get(connection, "/v0/configuration/spbm/l2/isid/cvlan"))
    if cvlan is not None:
        result["cvlan"] = cvlan

    suni = _normalize_payload(_http_get(connection, "/v0/configuration/spbm/l2/isid/suni"))
    if suni is not None:
        result["suni"] = suni

    tuni = _normalize_payload(_http_get(connection, "/v0/configuration/spbm/l2/isid/tuni"))
    if tuni is not None:
        result["tuni"] = tuni

    return result


def main() -> None:
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    gather_subset_param = module.params.get("gather_subset")
    gather_resources_param = module.params.get("gather_network_resources")

    del _WARNINGS[:]
    try:
        subsets = _normalize_subset_requests(gather_subset_param)
        resources = _normalize_resource_requests(gather_resources_param)

        connection = Connection(module._socket_path)

        subset_results: dict[str, Any] = {}
        for subset in sorted(subsets):
            handler = SUBSET_HANDLERS.get(subset)
            if not handler:
                continue
            data = handler(connection)
            subset_results[subset] = data if data is not None else {}

        resource_results: dict[str, Any] = {}
        for resource in sorted(resources):
            handler = RESOURCE_HANDLERS.get(resource)
            if not handler:
                continue
            data = handler(connection)
            resource_results[resource] = data if data is not None else {}

        ansible_facts = {
            "extreme_fe_facts": subset_results,
            "extreme_fe_facts_network_resources": resource_results,
            "extreme_fe_facts_gathered_subsets": sorted(subsets),
            "extreme_fe_facts_gathered_network_resources": sorted(resources),
        }

        for warning in _WARNINGS:
            module.warn(warning)
        module.exit_json(changed=False, ansible_facts=ansible_facts)

    except FeFactsError as exc:
        module.fail_json(**exc.to_fail_kwargs())
    except ConnectionError as exc:
        # The exception text can quote the device's response, so only the code is kept.
        module.fail_json(
            msg=f"Unable to communicate with device{_http_status(http_status(getattr(exc, 'code', None)))}"
        )
    except Exception as exc:
        module.fail_json(msg=f"Unexpected error: {to_text(exc)}")


if __name__ == "__main__":
    main()
