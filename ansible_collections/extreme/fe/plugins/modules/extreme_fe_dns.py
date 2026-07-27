# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ansible module to manage DNS settings on Extreme Fabric Engine switches.

Module Architecture Overview
============================
This module manages Domain Name System (DNS) configuration on Extreme
Fabric Engine (VOSS) switches via the REST OpenAPI.

REST Endpoints used:
  GET    /v0/configuration/dns
         → Retrieve full DNS settings (servers + domains)
  PUT    /v0/configuration/dns
         → Replace the entire DNS configuration
  POST   /v0/configuration/dns/server
         → Add an individual DNS server
  DELETE /v0/configuration/dns/server/{address_type}/{address}/{vr_name}
         → Remove an individual DNS server
  POST   /v0/configuration/dns/domain
         → Add a DNS domain name
  DELETE /v0/configuration/dns/domain/{domain_name}
         → Remove a DNS domain name

VOSS constraints:
  - Only 3 user-configurable servers (primary, secondary, tertiary)
  - Dynamic servers (learned via DHCP) are read-only
  - Only a single domain name is supported
  - vrName must be "GlobalRouter"

Supported states:
  - merged     : Additive — add servers/domain not already present
  - replaced   : Set-level — desired server list IS the final state;
                  DELETE unlisted servers, POST missing ones, keep common.
                  Domain is set if specified, left alone if omitted.
  - overridden : Global authority — PUT entire config, remove unlisted entries
  - deleted    : Remove specified servers/domain, or all if config omitted
  - gathered   : Read-only, returns current DNS configuration

Code Flow (run_module):
  1. Connect to switch via httpapi
  2. Fetch current DNS config from the switch (GET)
  3. Based on the requested state, apply/delete/gather settings
  4. Return results with changed status and current values
"""

from __future__ import annotations

# json — used for serializing/deserializing REST API request and response bodies
import json
# ip_address — standard library helper for validating and comparing IP addresses
from ipaddress import ip_address

# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any, Dict, List, Optional, Tuple
# quote() is used to safely encode characters in REST URL path segments
from urllib.parse import quote

# AnsibleModule — the core class every Ansible module must instantiate;
# it handles argument parsing, check mode, exit/fail, etc.
from ansible.module_utils.basic import AnsibleModule
# Connection — communicates with the device through the httpapi plugin;
# ConnectionError — raised when the device is unreachable or returns a transport error
from ansible.module_utils.connection import Connection, ConnectionError
# to_text — safely converts bytes/strings to unicode text
from ansible.module_utils.common.text.converters import to_text

DOCUMENTATION = r"""
---
module: extreme_fe_dns
short_description: Manage DNS settings on ExtremeNetworks Fabric Engine switches
version_added: "1.2.0"
description:
  - Manage Domain Name System (DNS) configuration on ExtremeNetworks Fabric Engine
    (VOSS) switches using the custom C(extreme_fe) HTTPAPI plugin.
  - Uses C(/v0/configuration/dns) from the NOS OpenAPI schema.
  - Supports managing DNS servers (up to 3 user-configurable on VOSS) and a single
    DNS domain suffix.
  - Dynamic DNS entries (learned via DHCP) are read-only and excluded from management.
  - On Fabric Engine (VOSS), the virtual router name is always C(GlobalRouter).
  - C(replaced) makes the desired server list the final state via POST/DELETE.
    Servers not in the desired list are removed; missing ones are added.
    Domain is set if specified, left alone if omitted.
  - C(overridden) uses the PUT endpoint to enforce the exact DNS configuration.
    Any servers or domain not in config are removed.
author:
  - ExtremeNetworks Networking Automation Team
notes:
  - Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin
    shipped with this project.
  - Fabric Engine (VOSS) supports a maximum of 3 user-configurable DNS servers
    (primary, secondary, tertiary).
  - Fabric Engine (VOSS) supports a single DNS domain suffix.
  - C(overridden) uses the PUT endpoint (create or full replace) and is
    idempotent — it skips the PUT when the desired state matches the current
    device config. C(replaced) uses POST/DELETE for individual entries and
    is also idempotent.
  - C(deleted) with no C(config) resets all user-configured DNS settings to factory
    defaults (no servers, no domain).
requirements:
  - ansible.netcommon
options:
  config:
    description:
      - Structured DNS settings to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional when C(state=deleted); if omitted, all user-configured DNS servers
        and the domain are removed.
    type: dict
    suboptions:
      domain:
        description:
          - The DNS domain suffix for the device.
          - Fabric Engine (VOSS) supports only a single domain.
        type: str
      servers:
        description:
          - List of DNS servers to configure.
          - Fabric Engine (VOSS) supports a maximum of 3 user-configurable servers.
        type: list
        elements: dict
        suboptions:
          address:
            description:
              - The IP address of the DNS server (IPv4 or IPv6).
            type: str
            required: true
          address_type:
            description:
              - The type of IP address.
            type: str
            choices: [IPv4, IPv6]
            default: IPv4
  state:
    description:
      - Desired module operation.
      - C(merged) adds DNS servers and domain that are not already present.
      - C(replaced) makes the desired server list the final state. Servers not
        in the desired list are removed; missing ones are added via POST/DELETE.
      - C(overridden) replaces the entire DNS configuration with the supplied values
        using PUT semantics. Omitted servers and domain are removed.
      - C(deleted) removes the specified DNS servers and domain. If C(config) is
        omitted, all user-configured DNS entries are removed.
      - C(gathered) returns the current DNS configuration without making changes.
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

# -------------------------------------------------------------------------
# Task 1: Merge DNS servers
# -------------------------------------------------------------------------
# - name: "Task 1: Merge DNS servers"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Add primary and secondary DNS servers
  extreme.fe.extreme_fe_dns:
    state: merged
    config:
      domain: example.com
      servers:
        - address: 8.8.8.8
          address_type: IPv4
        - address: 8.8.4.4
          address_type: IPv4

# -------------------------------------------------------------------------
# Task 2: Replace DNS configuration
# -------------------------------------------------------------------------
# - name: "Task 2: Replace DNS configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Enforce the desired DNS configuration
  extreme.fe.extreme_fe_dns:
    state: replaced
    config:
      domain: corp.example.com
      servers:
        - address: 10.0.0.1
          address_type: IPv4
        - address: 10.0.0.2
          address_type: IPv4
        - address: "2001:db8::1"
          address_type: IPv6

# -------------------------------------------------------------------------
# Task 3: Override DNS configuration
# -------------------------------------------------------------------------
# - name: "Task 3: Override DNS configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Override DNS settings
  extreme.fe.extreme_fe_dns:
    state: overridden
    config:
      domain: lab.example.com
      servers:
        - address: 1.1.1.1
          address_type: IPv4

# -------------------------------------------------------------------------
# Task 4: Delete DNS configuration
# -------------------------------------------------------------------------
# - name: "Task 4: Delete DNS entries"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Remove a specific DNS server and domain
  extreme.fe.extreme_fe_dns:
    state: deleted
    config:
      domain: example.com
      servers:
        - address: 8.8.4.4
          address_type: IPv4

- name: Remove all DNS servers and domain
  extreme.fe.extreme_fe_dns:
    state: deleted

# -------------------------------------------------------------------------
# Task 5: Gather DNS configuration
# -------------------------------------------------------------------------
# - name: "Task 5: Gather DNS configuration"
#   hosts: switches
#   gather_facts: false
#   tasks:
- name: Collect current DNS configuration
  extreme.fe.extreme_fe_dns:
    state: gathered
  register: dns_info
"""

RETURN = r"""
---
changed:
  description: Indicates whether any configuration changes were made.
  returned: always
  type: bool
before:
  description:
    - DNS configuration before any changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: dict
after:
  description:
    - DNS configuration after changes.
    - Only returned when the module made changes.
  returned: when changed
  type: dict
gathered:
  description:
    - Current DNS configuration gathered from the device.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: dict
dns:
  description: DNS configuration details with differences (per-resource detail).
  returned: always
  type: dict
  contains:
    before:
      description: DNS configuration before any requested change.
      returned: when state != gathered
      type: dict
    after:
      description: DNS configuration after the requested change.
      returned: when state != gathered
      type: dict
    config:
      description: Current DNS configuration in gathered mode.
      returned: when state == gathered
      type: dict
    differences:
      description: Changed attributes with before and after values.
      returned: when state != gathered
      type: dict
submitted:
  description: Payload submitted to the device (overridden state only — PUT payload).
  returned: when state is overridden and a change was required
  type: dict
api_responses:
  description: Raw API responses captured from the device.
  returned: always
  type: dict
"""

# ── Constants ─────────────────────────────────────────────────────────────────
# These constants define the REST API endpoints the module communicates with.
# The NOS OpenAPI spec exposes DNS management under /v0/configuration/dns.

# Main endpoint — GET retrieves all DNS settings, PUT replaces the entire config
DNS_CONFIG_PATH = "/v0/configuration/dns"

# POST to this path adds a single DNS server to the device
DNS_SERVER_PATH = "/v0/configuration/dns/server"

# DELETE template — removes a specific server identified by its type, address, and VR
# Example: /v0/configuration/dns/server/IPv4/8.8.8.8/GlobalRouter
DNS_SERVER_DELETE_TEMPLATE = "/v0/configuration/dns/server/{address_type}/{address}/{vr_name}"

# POST to this path adds a DNS domain suffix to the device
DNS_DOMAIN_PATH = "/v0/configuration/dns/domain"

# DELETE template — removes a specific domain by name
# Example: /v0/configuration/dns/domain/example.com
DNS_DOMAIN_DELETE_TEMPLATE = "/v0/configuration/dns/domain/{domain_name}"

# VOSS only supports the "GlobalRouter" virtual router for DNS.
# This value is hardcoded because VOSS does not allow other VR names.
DEFAULT_VR_NAME = "GlobalRouter"

# Maximum number of user-configurable DNS servers on VOSS.
# VOSS supports primary, secondary, and tertiary — no more.
MAX_DNS_SERVERS = 3

# State constants — each state defines a different module behaviour.
# See the DOCUMENTATION string above for what each state does.
STATE_MERGED = "merged"         # Additive — only add what's missing
STATE_REPLACED = "replaced"     # Set-level — desired servers become the full list, unlisted are removed
STATE_OVERRIDDEN = "overridden" # Global authority — PUT entire config, remove unlisted entries
STATE_DELETED = "deleted"       # Remove specified entries (or all if config omitted)
STATE_GATHERED = "gathered"     # Read-only — just return current config

# These states require the user to provide a 'config' parameter
REQUIRES_CONFIG = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}

# ── Argument Spec ─────────────────────────────────────────────────────────────
# ARGUMENT_SPEC defines all parameters the user can pass to this module.
# Ansible uses this to validate user input before the module runs.

ARGUMENT_SPEC = {
    # config — the DNS settings the user wants to manage.
    # It's a dict (not a list) because DNS is a singleton resource on the device.
    "config": {
        "type": "dict",
        "options": {
            # domain — the DNS domain suffix (e.g. "example.com")
            # VOSS supports only a single domain
            "domain": {"type": "str"},
            # servers — list of DNS servers to configure
            # VOSS supports up to 3 user-configurable servers
            "servers": {
                "type": "list",
                "elements": "dict",
                "options": {
                    # address — the IP address of the DNS server (required)
                    "address": {"type": "str", "required": True},
                    # address_type — IPv4 or IPv6; defaults to IPv4
                    "address_type": {
                        "type": "str",
                        "choices": ["IPv4", "IPv6"],
                        "default": "IPv4",
                    },
                },
            },
        },
    },
    # state — controls what the module does with the config
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
}

# ── Custom Exception ─────────────────────────────────────────────────────────
# Every module defines its own exception class so errors can carry
# structured details (not just a message string) back to the user.

class FeDnsError(Exception):
    """Raised for DNS module validation or response issues.

    Args:
        message: Human-readable error description.
        details: Optional dict with extra context (shown in Ansible output).
    """

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> Dict[str, Any]:
        """Convert this exception into keyword args for module.fail_json()."""
        data: Dict[str, Any] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# ── Helper Functions ──────────────────────────────────────────────────────────
# These utility functions handle common tasks: detecting errors in REST
# responses, establishing the device connection, and sending API requests.

def _extract_error(payload: Any) -> Optional[Dict[str, Any]]:
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
            "message": message or "Device reported a DNS error",
            "payload": payload,
        }
    # Check for an explicit errors list in the response
    if isinstance(errors, list) and errors:
        return {
            "message": message or "Device reported DNS errors",
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
        FeDnsError: If no socket path is available (wrong connection type).
    """
    if not module._socket_path:
        raise FeDnsError("Connection type httpapi is required for this module")
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
    """Send a single REST API request to the device and return the response.

    This is the central function all REST calls go through. It:
    1. Sends the HTTP request (GET, PUT, POST, DELETE)
    2. Records the raw response in api_responses for debugging
    3. Checks for errors in the response
    4. Returns the parsed response data

    Args:
        module:          The AnsibleModule instance.
        connection:      The device Connection object.
        method:          HTTP method ("GET", "PUT", "POST", "DELETE").
        path:            REST API path (e.g. "/v0/configuration/dns").
        api_responses:   Dict to store raw responses for debugging output.
        response_key:    Key name under which to store this response.
        payload:         Request body data (for PUT/POST), or None for GET/DELETE.
        expect_content:  If True, treat empty responses as empty dicts;
                         if False, treat empty responses as None (for 204 No Content).

    Returns:
        The parsed response (dict, list, string, or None).
    """
    try:
        response = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        # Connection-level failure (device unreachable, auth error, etc.)
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            api_responses=api_responses,
        )

    # Ensure the response is a string if it came back as bytes
    if isinstance(response, bytes):
        response = to_text(response)

    # Store the raw response so it appears in the module's output for debugging
    api_responses[response_key] = response

    # Handle empty responses (common for PUT/POST/DELETE which return 204)
    if response in (None, ""):
        return None if not expect_content else {}

    # Check for application-level errors inside the JSON response body
    if isinstance(response, dict):
        error = _extract_error(response)
        if error:
            module.fail_json(
                msg=error.get("message"),
                details=error,
                api_responses=api_responses,
            )

    return response


# ── Data-Fetching Functions ───────────────────────────────────────────────────
# These functions retrieve data from the device. They wrap _call_api()
# with the correct endpoint and method for each resource type.

def _fetch_dns_config(
    module: AnsibleModule,
    connection: Connection,
    api_responses: Dict[str, Any],
    response_key: str,
) -> Dict[str, Any]:
    """Fetch the full DNS configuration from the device.

    Sends GET /v0/configuration/dns which returns a DnsSettings object
    containing both the servers list and domains list.

    Args:
        module:        The AnsibleModule instance.
        connection:    The device Connection object.
        api_responses: Dict to store raw responses for debugging.
        response_key:  Key name for storing this response.

    Returns:
        The raw DnsSettings dict from the device, or empty dict if
        the response was not a dict.
    """
    raw = _call_api(
        module,
        connection,
        method="GET",
        path=DNS_CONFIG_PATH,
        api_responses=api_responses,
        response_key=response_key,
    )
    return raw if isinstance(raw, dict) else {}


# ── Payload Builders ──────────────────────────────────────────────────────────
# These functions convert Ansible-format config dicts into REST API format
# payloads that the device expects. The key transformation is:
#   Ansible format:  {"address": "8.8.8.8", "address_type": "IPv4"}
#   REST API format: {"ipAddress": {"ipAddressType": "IPv4", "address": "8.8.8.8"}, "vrName": "GlobalRouter"}

def _build_put_payload(config: Dict[str, Any]) -> Dict[str, Any]:
    """Build a complete DnsSettings REST payload for PUT (replaced/overridden).

    The PUT endpoint replaces the ENTIRE DNS configuration on the device.
    We always include both 'servers' and 'domains' keys — if the user
    didn't provide servers or a domain, we send empty lists, which tells
    the device to remove all existing entries.

    Args:
        config: The user-provided config dict with 'servers' and/or 'domain'.

    Returns:
        A DnsSettings dict ready to send as the PUT request body.
    """
    payload: Dict[str, Any] = {}

    # Convert each Ansible server entry to the REST API's nested format
    servers_config = config.get("servers") or []
    rest_servers: List[Dict[str, Any]] = []
    for srv in servers_config:
        address = srv["address"]
        addr_type = srv.get("address_type", "IPv4")
        # Normalize IPv6 to compressed canonical form for consistency
        if addr_type == "IPv6" and address:
            try:
                address = str(ip_address(address))
            except ValueError:
                pass
        rest_servers.append({
            # The REST API nests the IP inside an "ipAddress" object
            # with a discriminator field "ipAddressType" for IPv4 vs IPv6
            "ipAddress": {
                "ipAddressType": addr_type,
                "address": address,
            },
            # VOSS requires vrName but only supports "GlobalRouter"
            "vrName": DEFAULT_VR_NAME,
        })
    payload["servers"] = rest_servers

    # The REST API expects domains as a list of DnsDomain objects,
    # but VOSS only supports a single domain, so the list has 0 or 1 entry
    domains: List[Dict[str, Any]] = []
    if config.get("domain"):
        domains.append({"name": config["domain"]})
    payload["domains"] = domains

    return payload


def _validate_server_addresses(
    module: AnsibleModule, servers: List[Dict[str, Any]]
) -> None:
    """Validate DNS server addresses and address_type consistency.

    Checks that each server address is a valid IP address and that
    the detected IP version matches the declared address_type.
    Fails fast with a clear error message on mismatch or invalid input.
    """
    for srv in servers:
        addr = srv.get("address")
        addr_type = srv.get("address_type", "IPv4")
        if addr is None or (isinstance(addr, str) and not addr.strip()):
            module.fail_json(
                msg="DNS server 'address' is required and cannot be empty"
            )
        try:
            parsed = ip_address(addr)
        except ValueError:
            module.fail_json(
                msg="Invalid IP address '{0}' in DNS server config".format(addr)
            )
        detected_version = "IPv6" if parsed.version == 6 else "IPv4"
        if detected_version != addr_type:
            module.fail_json(
                msg=(
                    "Address '{0}' is {1} but address_type is set to '{2}'"
                ).format(addr, detected_version, addr_type),
            )


def _build_server_post_payload(server: Dict[str, Any]) -> Dict[str, Any]:
    """Build a DnsServer REST payload for POST (adding a single server).

    Used by the 'merged' state to add individual servers one at a time.

    Args:
        server: A single server entry from the user's config.

    Returns:
        A DnsServer dict ready to send as the POST request body.
    """
    return {
        "ipAddress": {
            "ipAddressType": server.get("address_type", "IPv4"),
            "address": server["address"],
        },
        "vrName": DEFAULT_VR_NAME,
    }


# ── Diff / Comparison Logic ──────────────────────────────────────────────────
# This function compares the DNS state before and after changes to produce
# a human-readable summary of what changed. The diff is included in the
# module's return data so the user can see exactly what was modified.

def _compute_diff(
    before: Dict[str, Any], after: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Compute differences between before and after DNS states.

    Compares servers (sorted by type+address for stable comparison)
    and domain name. Only includes fields that actually changed.

    Args:
        before: DNS state before the module ran.
        after:  DNS state after the module ran.

    Returns:
        A dict where each key is a changed field, and the value is
        a dict with 'before' and 'after' values.  Empty if nothing changed.
    """
    diff: Dict[str, Dict[str, Any]] = {}

    # Sort servers by (address_type, address) so order doesn't cause false diffs
    before_servers = sorted(
        before.get("servers") or [],
        key=lambda s: (s.get("address_type", ""), s.get("address", "")),
    )
    after_servers = sorted(
        after.get("servers") or [],
        key=lambda s: (s.get("address_type", ""), s.get("address", "")),
    )
    if before_servers != after_servers:
        diff["servers"] = {"before": before_servers, "after": after_servers}

    # Compare domain names (simple string comparison)
    if before.get("domain") != after.get("domain"):
        diff["domain"] = {"before": before.get("domain"), "after": after.get("domain")}

    return diff


# ── Output Formatter ──────────────────────────────────────────────────────────
# This function does the reverse of the payload builders: it converts the
# REST API response format back into the simpler Ansible format that users
# see in playbook output and registered variables.

def _to_ansible_output(dns_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a REST DnsSettings response to the Ansible output format.

    The REST API returns a nested structure with ipAddress objects and
    a dynamic flag. This function:
    1. Filters out dynamic entries (DHCP-learned, read-only)
    2. Flattens the nested ipAddress object into simple address/address_type
    3. Extracts the single domain name from the domains list

    Example transformation:
        REST input:  {"servers": [{"ipAddress": {"ipAddressType": "IPv4",
                      "address": "8.8.8.8"}, "vrName": "GlobalRouter",
                      "dynamic": false}], "domains": [{"name": "example.com",
                      "dynamic": false}]}
        Ansible output: {"servers": [{"address": "8.8.8.8",
                         "address_type": "IPv4"}], "domain": "example.com"}

    Args:
        dns_data: The raw DnsSettings dict from the REST API.

    Returns:
        A simplified dict with 'servers' (list) and 'domain' (str or None).
    """
    servers: List[Dict[str, str]] = []
    for srv in dns_data.get("servers") or []:
        # Skip dynamic servers — these are learned via DHCP and are read-only
        if srv.get("dynamic", False):
            continue
        # Flatten the nested ipAddress object into simple key-value pairs
        ip = srv.get("ipAddress") or {}
        address = ip.get("address", "")
        address_type = ip.get("ipAddressType", "IPv4")
        # Normalize IPv6 addresses to compressed canonical form so that
        # comparisons are idempotent regardless of textual representation
        # (e.g. "2001:0db8:0000::1" vs "2001:db8::1").
        if address and address_type == "IPv6":
            try:
                address = str(ip_address(address))
            except ValueError:
                pass  # keep the original if it can't be parsed
        servers.append({
            "address": address,
            "address_type": address_type,
        })

    domain: Optional[str] = None
    for dom in dns_data.get("domains") or []:
        # Skip dynamic domains — learned via DHCP, read-only
        if dom.get("dynamic", False):
            continue
        domain = dom.get("name")
        break  # VOSS supports only a single domain, so take the first one

    return {"servers": servers, "domain": domain}



# ── State Handler Functions ───────────────────────────────────────────────
# Each handler implements one state for the DNS module.
# They modify ``result`` in place and return without calling module.exit_json().


def _handle_gathered(module, connection, config, current, result):
    """STATE_GATHERED — read-only, just return current config."""
    result["dns"] = {"config": current}


def _handle_overridden(module, connection, config, current, result):
    """STATE_OVERRIDDEN — PUT the full desired config (authoritative globally)."""
    # Build the predicted "after" state from user config
    raw_servers = config.get("servers") or []
    _validate_server_addresses(module, raw_servers)
    desired_servers = []
    seen_keys = set()
    for srv in raw_servers:
        address = srv["address"]
        addr_type = srv.get("address_type", "IPv4")
        # Normalize IPv6 to compressed canonical form for comparison
        if addr_type == "IPv6" and address:
            try:
                address = str(ip_address(address))
            except ValueError:
                pass
        key = (address, addr_type)
        if key not in seen_keys:
            seen_keys.add(key)
            desired_servers.append({
                "address": address,
                "address_type": addr_type,
            })

    # Pre-flight: de-duplicated server count must not exceed VOSS limit
    if len(desired_servers) > MAX_DNS_SERVERS:
        module.fail_json(
            msg=(
                "The maximum number of configurable DNS servers is {0}. "
                "Desired config specifies {1} servers."
            ).format(MAX_DNS_SERVERS, len(desired_servers)),
            api_responses=result["api_responses"],
        )

    # Normalize domain: empty string → None (matches device behavior)
    desired_domain = config.get("domain") or None

    desired_after = {
        "servers": desired_servers,
        "domain": desired_domain,
    }

    # Compare desired state with current — skip PUT if identical
    current_server_keys = {
        (s["address"], s["address_type"])
        for s in current.get("servers") or []
    }
    desired_server_keys = {
        (s["address"], s["address_type"])
        for s in desired_servers
    }
    domain_matches = desired_domain == current.get("domain")
    servers_match = current_server_keys == desired_server_keys

    if domain_matches and servers_match:
        # No change needed — idempotent
        result["dns"] = {
            "before": current,
            "after": current,
            "differences": {},
        }
        return

    # Build the complete REST payload from de-duplicated/normalized config
    normalized_config = {
        "servers": desired_servers,
        "domain": desired_domain,
    }
    payload = _build_put_payload(normalized_config)
    result["changed"] = True
    result["submitted"] = {
        "operation": STATE_OVERRIDDEN,
        "path": DNS_CONFIG_PATH,
        "payload": payload,
    }
    result["dns"] = {"before": current}

    if not module.check_mode:
        # Send PUT to replace the entire DNS config on the device
        _call_api(
            module,
            connection,
            method="PUT",
            path=DNS_CONFIG_PATH,
            payload=payload,
            expect_content=False,  # PUT returns 204 No Content
            api_responses=result["api_responses"],
            response_key="put",
        )
        # Re-read the config after the change to get the actual "after" state
        after_raw = _fetch_dns_config(
            module, connection, result["api_responses"], "configuration_after"
        )
        result["dns"]["after"] = _to_ansible_output(after_raw)
    else:
        # Check mode: use the desired state we already computed
        result["dns"]["after"] = desired_after

    # Compute what changed between before and after
    result["dns"]["differences"] = _compute_diff(
        current, result["dns"]["after"]
    )


def _predict_replaced_after(desired_servers, desired_domain, current_domain):
    """Predict the after-state for replaced in check mode."""
    seen_keys = set()
    after_servers = []
    for s in desired_servers:
        addr = s["address"]
        addr_type = s.get("address_type", "IPv4")
        if addr_type == "IPv6" and addr:
            try:
                addr = str(ip_address(addr))
            except ValueError:
                pass
        key = (addr, addr_type)
        if key not in seen_keys:
            seen_keys.add(key)
            after_servers.append({"address": addr, "address_type": addr_type})
    if desired_domain is None:
        after_domain = current_domain
    elif desired_domain == "":
        after_domain = None
    else:
        after_domain = desired_domain
    return {"servers": after_servers, "domain": after_domain}


def _handle_replaced(module, connection, config, current, result):
    """STATE_REPLACED — set-level server replacement via POST/DELETE."""
    changes_made_rep: List[Tuple[str, Any]] = []

    # Build sets of current and desired server keys for comparison
    current_server_keys = {
        (s["address"], s["address_type"])
        for s in current.get("servers") or []
    }
    raw_desired_servers = config.get("servers")
    if raw_desired_servers is not None:
        # Servers key explicitly provided — use as desired state
        desired_servers = raw_desired_servers
        _validate_server_addresses(module, desired_servers)
        desired_keys = set()
        for s in desired_servers:
            addr = s["address"]
            addr_type = s.get("address_type", "IPv4")
            if addr_type == "IPv6" and addr:
                try:
                    addr = str(ip_address(addr))
                except ValueError:
                    pass
            desired_keys.add((addr, addr_type))
    else:
        # Servers key omitted — leave current servers unchanged
        desired_servers = [
            {"address": s["address"], "address_type": s["address_type"]}
            for s in current.get("servers") or []
        ]
        desired_keys = set(current_server_keys)

    # Pre-flight check: desired list itself must not exceed VOSS limit
    if len(desired_keys) > MAX_DNS_SERVERS:
        module.fail_json(
            msg=(
                "The maximum number of configurable DNS servers is {0}. "
                "Desired config specifies {1} servers."
            ).format(MAX_DNS_SERVERS, len(desired_keys)),
            api_responses=result["api_responses"],
        )

    # Replaced semantics: the desired server list IS the final state.
    # - Delete current servers NOT in desired list
    # - Add desired servers NOT already on device
    # - Leave servers that exist in both
    servers_to_remove = current_server_keys - desired_keys
    servers_to_add = desired_keys - current_server_keys

    # Delete servers that should no longer exist
    for addr, addr_type in servers_to_remove:
        if not module.check_mode:
            delete_path = DNS_SERVER_DELETE_TEMPLATE.format(
                address_type=quote(addr_type, safe=""),
                address=quote(addr, safe=""),
                vr_name=quote(DEFAULT_VR_NAME, safe=""),
            )
            _call_api(
                module,
                connection,
                method="DELETE",
                path=delete_path,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key="delete_server_{0}".format(addr),
            )
        changes_made_rep.append(("delete_server", {"address": addr, "address_type": addr_type}))

    # Add servers that are desired but not yet on device.
    # Discard each key from servers_to_add after processing to
    # prevent duplicate POSTs if the user list has duplicates.
    for srv in desired_servers:
        addr = srv["address"]
        addr_type = srv.get("address_type", "IPv4")
        if addr_type == "IPv6" and addr:
            try:
                addr = str(ip_address(addr))
            except ValueError:
                pass
        key = (addr, addr_type)
        if key in servers_to_add:
            servers_to_add.discard(key)
            if not module.check_mode:
                post_payload = _build_server_post_payload(
                    {"address": addr, "address_type": addr_type}
                )
                _call_api(
                    module,
                    connection,
                    method="POST",
                    path=DNS_SERVER_PATH,
                    payload=post_payload,
                    expect_content=False,
                    api_responses=result["api_responses"],
                    response_key="post_server_{0}".format(addr),
                )
            changes_made_rep.append(("add_server", {"address": addr, "address_type": addr_type}))

    # Handle domain — only if specified in config; leave alone if omitted.
    # desired_domain is None when "domain" key is absent from config (omitted),
    # and "" when the user explicitly sets domain: "" to clear the domain.
    desired_domain = config.get("domain")
    current_domain = current.get("domain")
    # Normalize for comparison: "" (clear) is equivalent to None (already cleared)
    effective_desired = None if desired_domain == "" else desired_domain
    if desired_domain is not None and effective_desired != current_domain:
        # If there's an existing different domain, delete it first
        if current_domain and not module.check_mode:
            delete_path = DNS_DOMAIN_DELETE_TEMPLATE.format(
                domain_name=quote(current_domain, safe="")
            )
            _call_api(
                module,
                connection,
                method="DELETE",
                path=delete_path,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key="delete_domain_old",
            )
        if desired_domain and not module.check_mode:
            _call_api(
                module,
                connection,
                method="POST",
                path=DNS_DOMAIN_PATH,
                payload=json.dumps(desired_domain),
                expect_content=False,
                api_responses=result["api_responses"],
                response_key="post_domain",
            )
        changes_made_rep.append(("set_domain", desired_domain))

    result["changed"] = len(changes_made_rep) > 0
    result["dns"] = {"before": current}

    if result["changed"] and not module.check_mode:
        after_raw = _fetch_dns_config(
            module, connection, result["api_responses"], "configuration_after"
        )
        result["dns"]["after"] = _to_ansible_output(after_raw)
    elif result["changed"] and module.check_mode:
        result["dns"]["after"] = _predict_replaced_after(
            desired_servers, desired_domain, current_domain
        )
    else:
        result["dns"]["after"] = current

    result["dns"]["differences"] = _compute_diff(
        current, result["dns"]["after"]
    )


def _handle_merged(module, connection, config, current, result):
    """STATE_MERGED — additive, only add what is not already there."""
    # Track all changes so we know if anything was modified
    changes_made: List[Tuple[str, Any]] = []

    # Build a set of (address, address_type) tuples for quick lookup
    # to determine which servers already exist on the device
    current_server_keys = {
        (s["address"], s["address_type"])
        for s in current.get("servers") or []
    }
    desired_servers = config.get("servers") or []
    _validate_server_addresses(module, desired_servers)

    # Pre-flight check: ensure merged result won't exceed VOSS limit
    desired_keys = set()
    for s in desired_servers:
        addr = s["address"]
        addr_type = s.get("address_type", "IPv4")
        if addr_type == "IPv6" and addr:
            try:
                addr = str(ip_address(addr))
            except ValueError:
                pass
        desired_keys.add((addr, addr_type))
    total_after_merge = len(current_server_keys | desired_keys)
    if total_after_merge > MAX_DNS_SERVERS:
        module.fail_json(
            msg=(
                "VOSS supports a maximum of {0} DNS servers. "
                "After merge, total would be {1}. "
                "Remove servers first or use 'overridden' to replace all."
            ).format(MAX_DNS_SERVERS, total_after_merge),
            api_responses=result["api_responses"],
        )

    # For each desired server, check if it already exists.
    # Track keys we've already planned to add to prevent duplicate
    # POSTs if the user-supplied list contains duplicates.
    for srv in desired_servers:
        addr = srv["address"]
        addr_type = srv.get("address_type", "IPv4")
        if addr_type == "IPv6" and addr:
            try:
                addr = str(ip_address(addr))
            except ValueError:
                pass
        key = (addr, addr_type)
        if key not in current_server_keys:
            current_server_keys.add(key)
            # Server doesn't exist yet — POST to add it
            if not module.check_mode:
                post_payload = _build_server_post_payload(
                    {"address": addr, "address_type": addr_type}
                )
                _call_api(
                    module,
                    connection,
                    method="POST",
                    path=DNS_SERVER_PATH,
                    payload=post_payload,
                    expect_content=False,  # POST returns 204 No Content
                    api_responses=result["api_responses"],
                    response_key="post_server_{0}".format(addr),
                )
            changes_made.append(("add_server", {"address": addr, "address_type": addr_type}))

    # Handle domain — VOSS supports only one domain, so if the user
    # wants a different domain, we need to delete the old one first
    desired_domain = config.get("domain")
    current_domain = current.get("domain")
    if desired_domain and desired_domain != current_domain:
        # If there's already a different domain, delete it first
        if current_domain and not module.check_mode:
            delete_path = DNS_DOMAIN_DELETE_TEMPLATE.format(
                domain_name=quote(current_domain, safe="")
            )
            _call_api(
                module,
                connection,
                method="DELETE",
                path=delete_path,
                expect_content=False,
                api_responses=result["api_responses"],
                response_key="delete_domain_old",
            )
        # Now add the new domain
        if not module.check_mode:
            _call_api(
                module,
                connection,
                method="POST",
                path=DNS_DOMAIN_PATH,
                payload=json.dumps(desired_domain),
                expect_content=False,
                api_responses=result["api_responses"],
                response_key="post_domain",
            )
        changes_made.append(("set_domain", desired_domain))

    # Set changed based on whether any POST/DELETE was needed
    result["changed"] = len(changes_made) > 0
    result["dns"] = {"before": current}

    if result["changed"] and not module.check_mode:
        # Re-read actual state from device after all changes
        after_raw = _fetch_dns_config(
            module, connection, result["api_responses"], "configuration_after"
        )
        result["dns"]["after"] = _to_ansible_output(after_raw)
    elif result["changed"] and module.check_mode:
        # Check mode: predict the after state without making changes
        after_servers = list(current.get("servers") or [])
        for action, data in changes_made:
            if action == "add_server":
                after_servers.append({
                    "address": data["address"],
                    "address_type": data.get("address_type", "IPv4"),
                })
        predicted_after = {
            "servers": after_servers,
            "domain": desired_domain if desired_domain else current_domain,
        }
        result["dns"]["after"] = predicted_after
    else:
        # No changes needed — after is the same as before
        result["dns"]["after"] = current

    result["dns"]["differences"] = _compute_diff(
        current, result["dns"]["after"]
    )


def _handle_deleted(module, connection, config, current, result):
    """STATE_DELETED — remove specified entries or all entries."""
    changes_made_del: List[Tuple[str, Any]] = []

    if config:
        # ── Delete specific servers listed in config ─────────
        servers_to_delete = config.get("servers") or []
        _validate_server_addresses(module, servers_to_delete)
        for srv in servers_to_delete:
            addr = srv["address"]
            addr_type = srv.get("address_type", "IPv4")
            # Normalize IPv6 to compressed form for comparison
            if addr_type == "IPv6" and addr:
                try:
                    addr = str(ip_address(addr))
                except ValueError:
                    pass
            # Only try to delete if the server actually exists
            exists = any(
                s["address"] == addr and s["address_type"] == addr_type
                for s in current.get("servers") or []
            )
            if exists:
                if not module.check_mode:
                    # Build the DELETE URL with the server's identifying params
                    delete_path = DNS_SERVER_DELETE_TEMPLATE.format(
                        address_type=quote(addr_type, safe=""),
                        address=quote(addr, safe=""),
                        vr_name=quote(DEFAULT_VR_NAME, safe=""),
                    )
                    _call_api(
                        module,
                        connection,
                        method="DELETE",
                        path=delete_path,
                        expect_content=False,
                        api_responses=result["api_responses"],
                        response_key="delete_server_{0}".format(addr),
                    )
                changes_made_del.append(("delete_server", {"address": addr, "address_type": addr_type}))

        # ── Delete specific domain if it matches current ─────
        desired_domain = config.get("domain")
        if desired_domain and current.get("domain") == desired_domain:
            if not module.check_mode:
                delete_path = DNS_DOMAIN_DELETE_TEMPLATE.format(
                    domain_name=quote(desired_domain, safe="")
                )
                _call_api(
                    module,
                    connection,
                    method="DELETE",
                    path=delete_path,
                    expect_content=False,
                    api_responses=result["api_responses"],
                    response_key="delete_domain",
                )
            changes_made_del.append(("delete_domain", desired_domain))
    else:
        # ── Delete ALL — no config provided, reset everything ──
        # Remove every user-configured server from the device
        for srv in current.get("servers") or []:
            if not module.check_mode:
                delete_path = DNS_SERVER_DELETE_TEMPLATE.format(
                    address_type=quote(srv["address_type"], safe=""),
                    address=quote(srv["address"], safe=""),
                    vr_name=quote(DEFAULT_VR_NAME, safe=""),
                )
                _call_api(
                    module,
                    connection,
                    method="DELETE",
                    path=delete_path,
                    expect_content=False,
                    api_responses=result["api_responses"],
                    response_key="delete_server_{0}".format(srv["address"]),
                )
            changes_made_del.append(("delete_server", srv))

        # Remove the domain if one is configured
        if current.get("domain"):
            if not module.check_mode:
                delete_path = DNS_DOMAIN_DELETE_TEMPLATE.format(
                    domain_name=quote(current["domain"], safe="")
                )
                _call_api(
                    module,
                    connection,
                    method="DELETE",
                    path=delete_path,
                    expect_content=False,
                    api_responses=result["api_responses"],
                    response_key="delete_domain",
                )
            changes_made_del.append(("delete_domain", current["domain"]))

    result["changed"] = len(changes_made_del) > 0
    result["dns"] = {"before": current}

    if result["changed"] and not module.check_mode:
        # Re-read actual state from device after deletions
        after_raw = _fetch_dns_config(
            module, connection, result["api_responses"], "configuration_after"
        )
        result["dns"]["after"] = _to_ansible_output(after_raw)
    elif result["changed"] and module.check_mode:
        # Check mode: predict the after state by removing deleted entries
        after_servers = list(current.get("servers") or [])
        after_domain = current.get("domain")
        for action, data in changes_made_del:
            if action == "delete_server":
                # Remove the server from our predicted list
                after_servers = [
                    s for s in after_servers
                    if not (s["address"] == data["address"] and s["address_type"] == data["address_type"])
                ]
            elif action == "delete_domain":
                after_domain = None
        result["dns"]["after"] = {"servers": after_servers, "domain": after_domain}
    else:
        # Nothing to delete — after is the same as before
        result["dns"]["after"] = current

    result["dns"]["differences"] = _compute_diff(
        current, result["dns"]["after"]
    )


# ── Main Entry Point ─────────────────────────────────────────────────────────
# This is where the module logic starts. The function:
# 1. Creates the AnsibleModule (validates user input against ARGUMENT_SPEC)
# 2. Connects to the device via httpapi
# 3. Reads the current DNS config from the device
# 4. Dispatches to the appropriate state handler (gathered/replaced/merged/deleted)
# 5. Returns results with changed=true/false and before/after config

def run_module() -> None:
    # supports_check_mode=True means this module can simulate changes
    # without actually modifying the device (--check flag in ansible-playbook)
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)

    # Establish connection to the device via the httpapi plugin
    try:
        connection = _get_connection(module)
    except FeDnsError as exc:
        module.fail_json(**exc.to_fail_kwargs())
        return

    # Initialize the result dict — this is what gets returned to the user
    result: Dict[str, Any] = {
        "changed": False,       # Will be set to True if we modify anything
        "api_responses": {},    # Stores raw API responses for debugging
    }

    try:
        state = module.params.get("state")       # Which operation to perform
        config = module.params.get("config") or {}  # User's desired DNS config

        # ── Validate config requirement ──────────────────────────────
        # merged/replaced/overridden need something to work with
        if state in REQUIRES_CONFIG and not config:
            raise FeDnsError(
                "config is required when state is one of: merged, replaced, overridden"
            )

        # ── GET current DNS configuration ────────────────────────────
        # Always read the current state first — used for "before" in output
        # and for comparison in merged/deleted states
        current_raw = _fetch_dns_config(
            module, connection, result["api_responses"], "configuration_before"
        )
        # Convert the REST API format to the simpler Ansible format
        current = _to_ansible_output(current_raw)

        # ── Dispatch to the appropriate state handler ────────────────
        if state == STATE_GATHERED:
            _handle_gathered(module, connection, config, current, result)
            result["gathered"] = current
        elif state == STATE_OVERRIDDEN:
            result["before"] = current
            _handle_overridden(module, connection, config, current, result)
            if result["changed"]:
                result["after"] = result.get("dns", {}).get("after", current)
        elif state == STATE_REPLACED:
            result["before"] = current
            _handle_replaced(module, connection, config, current, result)
            if result["changed"]:
                result["after"] = result.get("dns", {}).get("after", current)
        elif state == STATE_MERGED:
            result["before"] = current
            _handle_merged(module, connection, config, current, result)
            if result["changed"]:
                result["after"] = result.get("dns", {}).get("after", current)
        elif state == STATE_DELETED:
            result["before"] = current
            _handle_deleted(module, connection, config, current, result)
            if result["changed"]:
                result["after"] = result.get("dns", {}).get("after", current)
        else:
            raise FeDnsError("Unsupported state supplied", details={"state": state})

        module.exit_json(**result)

    # ── Error Handling ───────────────────────────────────────────────
    # Two types of errors can occur:
    # 1. FeDnsError — our own validation or logic errors
    # 2. ConnectionError — device communication failures
    except FeDnsError as exc:
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
