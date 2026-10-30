# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Manage RADIUS configuration and retrieve RADIUS state on Fabric Engine.

REST endpoints used:
  GET/PATCH /v0/configuration/radius
  GET       /v0/state/radius
  GET/POST  /v0/configuration/radius/secure-profile
  GET/PATCH/DELETE /v0/configuration/radius/secure-profile/{name}
  PATCH/DELETE /v0/configuration/radius/dynamic-server/host-type/{type}/host/{host}
  POST      /v0/configuration/radius/server
  DELETE    /v0/configuration/radius/server/server-mode/{mode}/host-type/{type}/host/{host}/used-by/{used_by}

Only Fabric Engine fields and enum values from the OpenAPI specification are
exposed.
"""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: extreme_fe_radius
short_description: Manage RADIUS settings on Extreme Fabric Engine devices
version_added: "1.3.0"
description:
  - Manages RADIUS global settings, AAA servers, dynamic authorization clients,
    and secure certificate profiles through the OpenAPI Server.
  - Retrieves RADIUS configuration and runtime state information.
  - Supports the five Ansible resource module states.
author:
  - Vlad-Leonard Mocanu (@vmocanu_extr)
requirements:
  - ansible.netcommon
notes:
  - Tested against Fabric Engine Version 9.3.2. Some fixes in this version are based on reports from Fabric Engine 9.4
    and 9.5; they have not been tested on those versions.
  - C(deleted) and C(overridden) can remove the AAA servers used by C(LOGIN). When the device
    authenticates its management users through RADIUS, keep a local account (or another server)
    that can log in before running such a task, or later connections may be refused.
  - A write that fails without an answer (a lost connection) may have been applied, so the task
    reports C(changed=true). For the PATCH of the globals the re-read decides; it reports
    C(changed=false) only when it proves that none of the attempted fields was applied. A DELETE
    answered with 404 counts as done (and as a change); the server or profile was just read as
    present, and a DELETE resent after a lost answer finds it gone. Likewise a server or profile
    POST answered with 409 (a resend finding the object a first attempt created) is checked against a
    re-read; it counts as created when the object is there with the submitted settings and the POST
    carried no credential. Otherwise the outcome is unknown and the task fails with C(changed=true);
    a server POST always carries its shared secret, and a stored secret, private key or passphrase
    cannot be compared, so another writer may have created the object with a different one. Running
    the task again re-applies it.
  - An error the device returns, an HTTP error or an error document, is reported with every
    credential masked; those of its own request, the stored ones the module read (the global
    password, shared secrets and profile keys) and those the task has already written.
  - Supports check mode and diff mode.
  - Fabric Engine supports C(AAA) and C(DYN_AUTH) server modes.
  - The API has no update operation for an existing AAA server. A changed AAA
    server is deleted and recreated, which can briefly interrupt service.
  - The built-in C(default) secure profile cannot be created or deleted and is
    retained by C(replaced), C(overridden), and C(deleted).
  - Shared secrets, private keys, and passphrases cannot be compared reliably
    with GET responses. When supplied, they are always applied and the task can
    report changed on every run. C(overridden) leaves the global password
    unchanged when it is omitted because GET responses cannot expose its
    current value for comparison. Global RADIUS accounting can be enabled only
    when at least one C(AAA) server exists in the resulting configuration.
    Global RADIUS accounting must be disabled before global RADIUS is disabled;
    the module performs these updates in separate requests when necessary.
  - The global reachability C(password) is write-only. C(deleted) without
    C(config) and C(overridden) do not reset it, so they stay idempotent; to
    change it, set C(global.password) explicitly (C(merged), C(replaced),
    C(overridden)) or name it under C(global) with C(deleted), which resets it
    to its factory default. A supplied password is always sent and reports
    changed.
  - Secret material is never returned. Shared secrets, the global password,
    private keys, and passphrases, including any mask or encrypted value the
    device reports for them, are left out of C(gathered), C(before), C(after),
    and the diff.
  - C(gathered), C(before), and C(after) use the C(config) option shape and can
    be passed back as C(config). Server rows contain only the fields valid for
    their C(server_mode). Re-applying gathered output changes nothing and
    leaves the stored shared secrets untouched, because an omitted secret is
    never sent. A C(servers[].secret) that is exactly the device mask of six
    asterisks, or the string that the masked secret object of an earlier
    release's gathered output becomes, is ignored with a warning, so a
    placeholder never replaces a stored secret. Any other value, an
    all-asterisk one of another length included, is a real secret and is sent.
  - A server address is compared as an IP address. Fabric Engine reports an
    IPv6 address uncompressed (C(2001:db8:0:0:0:0:0:10)), and a server written
    as C(2001:db8::10) is the same server. Requests to an existing server use
    the address as the device reports it.
  - Device-reported values that are not options (for example
    C(igap_timeout_log_fsize), server C(server_status) and C(vr_name), and
    profile certificate hashes) are returned in C(read_only_config).
  - All changed global fields are sent in one PATCH. If the device rejects it,
    the module re-reads the global settings and reports in
    C(details.applied_fields) and C(details.not_applied_fields) which REST
    fields the device applied, together with C(details.attempted_payload),
    C(details.status_code) and C(details.resource). Write-only or trigger
    fields (C(password), C(clearStat)) cannot be verified and are listed in
    C(details.unknown_fields) by name only, and so is a field the re-read does
    not report (or reports as null); the fields it reports are still
    attributed, and a re-read reporting none of them counts as a failed
    re-read. The task reports C(changed=true)
    if any field was applied or an earlier request of the same task (server,
    client, or profile change) succeeded. If the re-read fails too,
    C(details.reread_error) says why and nothing is attributed.
  - An error document answering a GET, the re-read included, is reported by
    its numeric error code only, never by its message, which could quote a
    stored RADIUS credential. An error document answering a write keeps its
    message, with every credential removed that the request submitted or the
    response itself carries.
options:
  state:
    description:
      - Desired RADIUS operation.
      - C(merged) applies supplied settings and adds missing resources.
      - C(replaced) makes supplied server and secure-profile lists authoritative
        while leaving omitted global fields unchanged.
      - C(overridden) makes resource lists authoritative and resets omitted
        non-secret global fields to OpenAPI factory defaults.
      - C(deleted) resets supplied global fields and deletes supplied resources.
        Omitting C(config) resets all non-secret global fields and deletes all
        resources; the global password is left unchanged.
      - C(gathered) returns configuration and runtime state without changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - RADIUS configuration to manage.
      - Required for C(merged), C(replaced), and C(overridden).
    type: dict
    suboptions:
      global:
        description: RADIUS global settings.
        type: dict
        suboptions:
          enabled: {description: Enable RADIUS., type: bool}
          account_attr: {description: Accounting attribute number., type: int}
          account_enabled: {description: Enable RADIUS accounting., type: bool}
          account_cli_commands: {description: Include CLI commands in accounting updates., type: bool}
          access_priority_attr: {description: Access-Priority attribute number., type: int}
          auth_info_attr: {description: Auth-Info vendor attribute number., type: int}
          command_access_attr: {description: Command-Access attribute number., type: int}
          clear_stat: {description: Clear statistics for all configured servers., type: bool}
          cli_commands_attr: {description: CLI-Commands attribute number., type: int}
          cli_commands_count: {description: CLI command interim-packet count., type: int}
          cli_profile_enabled: {description: Enable CLI profiling., type: bool}
          max_server: {description: Maximum configured RADIUS servers., type: int}
          mcast_addr_attr: {description: Multicast-address vendor attribute number., type: int}
          secure_enabled: {description: Enable Secure RADIUS., type: bool}
          keep_alive_timer: {description: Reachable-server check interval in seconds., type: int}
          unreachable_timer: {description: Unreachable-server check interval in seconds., type: int}
          username: {description: Dummy-request reachability username., type: str}
          password: {description: Dummy-request reachability password., type: str}
          reachability_mode:
            description: Method used to test server reachability.
            type: str
            choices: [USE_STATUS_SERVER_PACKETS, USE_DUMMY_RADIUS_REQUESTS]
      servers:
        description: AAA servers and dynamic authorization clients.
        type: list
        elements: dict
        suboptions:
          server_mode:
            description: Fabric Engine server mode.
            type: str
            choices: [AAA, DYN_AUTH]
            required: true
          host_type:
            description: Address discriminator.
            type: str
            choices: [hostname, IPv4, IPv6]
            required: true
          address: {description: Server host name or IP address., type: str, required: true}
          used_by:
            description: Feature using an AAA server.
            type: str
            choices: [DOT1X, LOGIN, ENDPOINT_TRACKING, SNMP, WEB]
          secret: {description: Shared secret., type: str}
          auth_port: {description: Authentication UDP port for an AAA server., type: int}
          account_port: {description: Accounting UDP port for an AAA server., type: int}
          retries: {description: Authentication retry count for an AAA server., type: int}
          timeout: {description: Request timeout for an AAA server., type: int}
          enabled: {description: Enable this server or client., type: bool}
          account_enabled: {description: Enable accounting on this AAA server., type: bool}
          priority: {description: AAA server selection priority., type: int}
          secure_enabled: {description: Enable Secure RADIUS on this AAA server., type: bool}
          secure_mode:
            description:
              - Secure transport for an AAA server.
              - A server the device reports with secure mode NONE (plain UDP) has no C(secure_mode) in the
                returned configuration.
            type: str
            choices: [TLS, DTLS]
          secure_profile: {description: Secure profile used by an AAA server., type: str}
          secure_log_level:
            description: Secure RADIUS logging level.
            type: str
            choices: [CRITICAL, ERROR, WARNING, INFO, DEBUG]
          secure_ocsp_enabled: {description: Enable OCSP checks for an AAA server., type: bool}
          port: {description: Dynamic authorization listen port., type: int}
      secure_profiles:
        description: Secure RADIUS certificate profiles.
        type: list
        elements: dict
        suboptions:
          name: {description: Secure profile name., type: str, required: true}
          root_cert: {description: Root certificate or chain in PEM format., type: str}
          cert: {description: Client certificate in PEM format., type: str}
          key: {description: RSA private key in PEM format., type: str}
          password: {description: Password used to decrypt the private key., type: str}
"""

EXAMPLES = r"""
# - name: Configure RADIUS
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Enable RADIUS and add an AAA server
  extreme.fe.extreme_fe_radius:
    state: merged
    config:
      global:
        enabled: true
        account_enabled: true
      servers:
        - server_mode: AAA
          host_type: IPv4
          address: 192.0.2.10
          used_by: LOGIN
          secret: "{{ radius_shared_secret }}"

- name: Configure a dynamic authorization client
  extreme.fe.extreme_fe_radius:
    state: merged
    config:
      servers:
        - server_mode: DYN_AUTH
          host_type: IPv4
          address: 192.0.2.20
          secret: "{{ radius_dynamic_secret }}"
          enabled: true
          port: 3799

- name: Create a Secure RADIUS profile
  extreme.fe.extreme_fe_radius:
    state: merged
    config:
      secure_profiles:
        - name: radsec-profile
          root_cert: "{{ radius_root_certificate }}"
          cert: "{{ radius_client_certificate }}"
          key: "{{ radius_private_key }}"
          password: "{{ radius_private_key_password }}"

- name: Gather RADIUS configuration and runtime state
  extreme.fe.extreme_fe_radius:
    state: gathered

- name: Delete all RADIUS configuration
  extreme.fe.extreme_fe_radius:
    state: deleted
"""

RETURN = r"""
---
changed:
  description: Whether RADIUS configuration changed.
  returned: always
  type: bool
before:
  description:
    - Full RADIUS configuration before action-state processing, in the C(config) option shape.
    - Contains no secret material.
  returned: when state is not gathered
  type: dict
after:
  description:
    - Actual post-change configuration, or the predicted configuration in check mode.
    - Includes the unchanged current values, in the C(config) option shape without secret material.
  returned: when state is not gathered
  type: dict
gathered:
  description:
    - Current RADIUS configuration in the C(config) option shape, accepted back as C(config).
    - Server rows contain only the options valid for their C(server_mode).
    - Contains no secret material, so re-applying it leaves stored secrets unchanged.
  returned: when state is gathered
  type: dict
read_only_config:
  description:
    - Device-reported RADIUS values that are not module options and are not accepted as input.
    - C(global) holds C(igap_timeout_log_fsize).
    - C(servers) rows carry the server identity keys plus C(client_address), C(client_address_type),
      C(server_status), C(nas_ip), C(client_vlan_name), C(index), and C(vr_name) when reported.
    - C(secure_profiles) rows carry C(name) plus C(root_cert_hash), C(cert_hash), and C(status) when reported.
  returned: when state is gathered
  type: dict
runtime_state:
  description:
    - Read-only global and per-server RADIUS runtime state.
  returned: when state is gathered
  type: dict
radius:
  description:
    - RADIUS configuration details and differences.
  returned: always
  type: dict
  contains:
    config:
      description:
        - Gathered RADIUS configuration.
      returned: when state is gathered
      type: dict
    before:
      description:
        - Configuration before changes.
      returned: when state is not gathered
      type: dict
    after:
      description:
        - Same value as the top-level C(after) result.
      returned: when state is not gathered
      type: dict
    differences:
      description:
        - Changed top-level sections, or an empty dictionary when unchanged.
      returned: when state is not gathered
      type: dict
"""

import ipaddress
import json
import re
from copy import deepcopy
from time import sleep
from typing import Any
from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown, http_status

CONFIG_PATH = "/v0/configuration/radius"
STATE_PATH = "/v0/state/radius"
SERVER_PATH = "/v0/configuration/radius/server"
AAA_DELETE_PATH = (
    "/v0/configuration/radius/server/server-mode/{server_mode}/host-type/{host_type}/host/{host}/used-by/{used_by}"
)
DYNAMIC_PATH = "/v0/configuration/radius/dynamic-server/host-type/{host_type}/host/{host}"
OPERATION_RETRY_ATTEMPTS = 10
OPERATION_RETRY_DELAY = 2
MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
PROFILE_PATH = "/v0/configuration/radius/secure-profile"
PROFILE_ITEM_PATH = PROFILE_PATH + "/{name}"
DEFAULT_PROFILE_NAME = "default"

STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"
REQUIRES_CONFIG = {STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN}

# Every writable Fabric Engine global has an OpenAPI default. keepAliveTimer's
# Fabric Engine default is stated in its description rather than a default key.
GLOBAL_DEFAULTS = {
    "enabled": False,
    "account_attr": 193,
    "account_enabled": False,
    "account_cli_commands": False,
    "access_priority_attr": 192,
    "auth_info_attr": 91,
    "command_access_attr": 194,
    "clear_stat": False,
    "cli_commands_attr": 195,
    "cli_commands_count": 40,
    "cli_profile_enabled": False,
    "max_server": 10,
    "mcast_addr_attr": 90,
    "secure_enabled": False,
    "keep_alive_timer": 180,
    "unreachable_timer": 60,
    "username": "reachme",
    # The OpenAPI default and the Fabric Engine factory value ("show radius
    # reachability"); "reachme_pass" was wrong.
    "password": "reachme",
    "reachability_mode": "USE_DUMMY_RADIUS_REQUESTS",
}

# Global fields whose current value GET cannot expose: the write-only password,
# and clearStat, a trigger that reads back false once statistics are cleared.
# Resetting all globals (deleted without config, overridden) skips the password
# so these states stay idempotent; a failed PATCH reports both as unknown.
WRITE_ONLY_GLOBALS = ("password",)
UNVERIFIABLE_REST_FIELDS = ("password", "clearStat")

# The non-secret globals reset by deleted without config and by overridden.
VISIBLE_GLOBAL_DEFAULTS = {key: value for key, value in GLOBAL_DEFAULTS.items() if key not in WRITE_ONLY_GLOBALS}

GLOBAL_FIELD_MAP = {
    "enabled": "enabled",
    "account_attr": "accountAttr",
    "account_enabled": "accountEnabled",
    "account_cli_commands": "accountCliCommands",
    "access_priority_attr": "accessPriorityAttr",
    "auth_info_attr": "authInfoAttr",
    "command_access_attr": "commandAccessAttr",
    "clear_stat": "clearStat",
    "cli_commands_attr": "cliCommandsAttr",
    "cli_commands_count": "cliCommandsCount",
    "cli_profile_enabled": "cliProfileEnabled",
    "max_server": "maxServer",
    "mcast_addr_attr": "mcastAddrAttr",
    "secure_enabled": "secureEnabled",
    "keep_alive_timer": "keepAliveTimer",
    "unreachable_timer": "unreachableTimer",
    "username": "username",
    "password": "password",
    "reachability_mode": "reachabilityMode",
}

SERVER_FIELD_MAP = {
    "host_type": "hostType",
    "account_port": "accountPort",
    "auth_port": "authPort",
    "secret": "secret",
    "retries": "retries",
    "timeout": "timeout",
    "enabled": "enabled",
    "account_enabled": "accountEnabled",
    "priority": "priority",
    "secure_enabled": "secureEnabled",
    "server_mode": "serverMode",
    "secure_mode": "secureMode",
    "secure_profile": "secureProfile",
    "secure_log_level": "secureLogLevel",
    "secure_ocsp_enabled": "secureOcspEnabled",
    "used_by": "usedBy",
    "address": "address",
    "port": "port",
}

PROFILE_FIELD_MAP = {
    "name": "name",
    "root_cert": "rootCert",
    "cert": "cert",
}

# Secret leaves are write-only. They are never copied from a GET response, so no
# result (gathered, before, after, diff) carries a stored secret, a mask, or an
# encrypted value, and re-applying gathered output leaves stored secrets alone.
SECRET_FIELDS = frozenset({"password", "secret", "key"})
# REST names of the write-only/secret globals, masked in details.attempted_payload.
# Derived from GLOBAL_FIELD_MAP so a REST name that differs from its Ansible name
# is still masked.
SECRET_GLOBAL_REST_FIELDS = frozenset(
    GLOBAL_FIELD_MAP[name] for name in GLOBAL_FIELD_MAP if name in WRITE_ONLY_GLOBALS or name in SECRET_FIELDS
)
# REST keys of every request body (global, server, dynamic client, profile) that
# carry a credential, as a plain string or as a {value} object.
SECRET_REST_KEYS = SECRET_GLOBAL_REST_FIELDS | {"secret", "key", "password"}
SECRET_MASK = "********"
# The secure_mode values a server can be configured with (AAAServerUpdate);
# a GET can also report NONE (plain UDP), which is not an input value.
SECURE_MODE_CHOICES = ("TLS", "DTLS")

# Server fields valid for only one server mode; _validate_config rejects the
# other mode's fields, so translated GET rows drop them too.
AAA_ONLY_SERVER_FIELDS = frozenset(
    {
        "used_by",
        "auth_port",
        "account_port",
        "retries",
        "timeout",
        "account_enabled",
        "priority",
        "secure_enabled",
        "secure_mode",
        "secure_profile",
        "secure_log_level",
        "secure_ocsp_enabled",
    }
)
DYN_AUTH_ONLY_SERVER_FIELDS = frozenset({"port"})

# Device-reported values that are not options. gathered returns them under
# read_only_config, never inside the config-shaped results. A tuple lists
# alternative REST spellings, the first one present wins.
GLOBAL_READ_ONLY_FIELD_MAP = {"igap_timeout_log_fsize": "igapTimeoutLogFsize"}
SERVER_READ_ONLY_FIELD_MAP = {
    "client_address": "clientAddress",
    "client_address_type": ("clientAddressType", "clientAdressType"),
    "server_status": "serverStatus",
    "nas_ip": "nasIp",
    "client_vlan_name": "clientVlanName",
    "index": "index",
    "vr_name": "vrName",
}
PROFILE_READ_ONLY_FIELD_MAP = {
    "root_cert_hash": "rootCertHash",
    "cert_hash": "certHash",
    "status": "status",
}

RUNTIME_FIELD_MAP = {
    "num_of_invalid_server_access": "numOfInvalidServerAccess",
    "servers": "servers",
    "address": "address",
    "host_type": "hostType",
    "server_mode": "serverMode",
    "used_by": "usedBy",
    "is_dot1x_radius_reachable": "isDot1xRadiusReachable",
    "nas_ip_address": "nasIpAddress",
    "nas_ip_address_type": "nasIpAddressType",
    "access_requests": "accessRequests",
    "access_accepts": "accessAccepts",
    "access_rejects": "accessRejects",
    "access_bad_responses": "accessBadResponses",
    "access_retransmits": "accessRetransmits",
    "access_challenges": "accessChallenges",
    "round_trip_time": "roundTripTime",
    "access_pending_requests": "accessPendingRequests",
    "acct_on_requests": "acctOnRequests",
    "acct_off_requests": "acctOffRequests",
    "acct_start_requests": "acctStartRequests",
    "acct_stop_requests": "acctStopRequests",
    "acct_interim_requests": "acctInterimRequests",
    "acct_bad_responses": "acctBadResponses",
    "acct_pending_requests": "acctPendingRequests",
    "acct_client_retries": "acctClientRetries",
    "coa_requests": "coaRequests",
    "disconnect_requests": "disconnectRequests",
    "reauth_requests": "reauthRequests",
    "coa_auth_only_requests": "coaAuthOnlyRequests",
    "disconnect_auth_only_requests": "disconnectAuthOnlyRequests",
    "reauth_auth_only_requests": "reauthAuthOnlyRequests",
    "coa_dup_requests": "coaDupRequests",
    "disconnect_dup_requests": "disconnectDupRequests",
    "reauth_dup_requests": "reauthDupRequests",
    "coa_accepts": "coaAccepts",
    "disconnect_accepts": "disconnectAccepts",
    "reauth_accepts": "reauthAccepts",
    "coa_rejects": "coaRejects",
    "disconnect_rejects": "disconnectRejects",
    "reauth_rejects": "reauthRejects",
    "coa_nak_auth_only_requests": "coaNAKAuthOnlyRequests",
    "disconnect_nak_auth_only_requests": "disconnectNAKAuthOnlyRequests",
    "reauth_nak_auth_only_requests": "reauthNAKAuthOnlyRequests",
    "coa_nak_sess_no_context": "coaNAKSessNoContext",
    "disconnect_nak_sess_no_context": "disconnectNAKSessNoContext",
    "reauth_nak_sess_no_context": "reauthNAKSessNoContext",
    "coa_user_sess_changed": "coaUserSessChanged",
    "disconnect_user_sess_removed": "disconnectUserSessRemoved",
    "reauth_user_sess": "reauthUserSess",
    "coa_malformed_requests": "coaMalformedRequests",
    "disconnect_malformed_requests": "disconnectMalformedRequests",
    "reauth_malformed_requests": "reauthMalformedRequests",
    "coa_bad_authenticator_requests": "coaBadAuthenticatorRequests",
    "disconnect_bad_authenticator_requests": "disconnectBadAuthenticatorRequests",
    "reauth_bad_authenticator_requests": "reauthBadAuthenticatorRequests",
    "coa_packets_dropped": "coaPacketsDropped",
    "disconnect_packets_dropped": "disconnectPacketsDropped",
    "reauth_packets_dropped": "reauthPacketsDropped",
    "unknown_packets": "unknownPackets",
}

GLOBAL_OPTIONS = {
    "enabled": {"type": "bool"},
    "account_attr": {"type": "int"},
    "account_enabled": {"type": "bool"},
    "account_cli_commands": {"type": "bool"},
    "access_priority_attr": {"type": "int"},
    "auth_info_attr": {"type": "int"},
    "command_access_attr": {"type": "int"},
    "clear_stat": {"type": "bool"},
    "cli_commands_attr": {"type": "int"},
    "cli_commands_count": {"type": "int"},
    "cli_profile_enabled": {"type": "bool"},
    "max_server": {"type": "int"},
    "mcast_addr_attr": {"type": "int"},
    "secure_enabled": {"type": "bool"},
    "keep_alive_timer": {"type": "int"},
    "unreachable_timer": {"type": "int"},
    "username": {"type": "str"},
    "password": {"type": "str", "no_log": True},
    "reachability_mode": {
        "type": "str",
        "choices": ["USE_STATUS_SERVER_PACKETS", "USE_DUMMY_RADIUS_REQUESTS"],
    },
}

SERVER_OPTIONS = {
    "server_mode": {"type": "str", "choices": ["AAA", "DYN_AUTH"], "required": True},
    "host_type": {"type": "str", "choices": ["hostname", "IPv4", "IPv6"], "required": True},
    "address": {"type": "str", "required": True},
    "used_by": {
        "type": "str",
        "choices": ["DOT1X", "LOGIN", "ENDPOINT_TRACKING", "SNMP", "WEB"],
    },
    "secret": {"type": "str", "no_log": True},
    "auth_port": {"type": "int"},
    "account_port": {"type": "int"},
    "retries": {"type": "int"},
    "timeout": {"type": "int"},
    "enabled": {"type": "bool"},
    "account_enabled": {"type": "bool"},
    "priority": {"type": "int"},
    "secure_enabled": {"type": "bool"},
    "secure_mode": {"type": "str", "choices": list(SECURE_MODE_CHOICES)},
    "secure_profile": {"type": "str"},
    "secure_log_level": {
        "type": "str",
        "choices": ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    },
    "secure_ocsp_enabled": {"type": "bool"},
    "port": {"type": "int"},
}

PROFILE_OPTIONS = {
    "root_cert": {"type": "str"},
    "cert": {"type": "str"},
    "key": {"type": "str", "no_log": True},
    "password": {"type": "str", "no_log": True},
    "name": {"type": "str", "required": True},
}

ARGUMENT_SPEC = {
    "state": {
        "type": "str",
        "choices": [STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN, STATE_DELETED, STATE_GATHERED],
        "default": STATE_MERGED,
    },
    "config": {
        "type": "dict",
        "options": {
            "global": {"type": "dict", "options": GLOBAL_OPTIONS},
            "servers": {"type": "list", "elements": "dict", "options": SERVER_OPTIONS},
            "secure_profiles": {
                "type": "list",
                "elements": "dict",
                "options": PROFILE_OPTIONS,
            },
        },
    },
}


class FeRadiusError(Exception):
    """Represent a RADIUS validation or REST response error."""

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
        """Return arguments suitable for module.fail_json()."""
        data: dict[str, Any] = dict(self.extra)
        data["msg"] = to_text(self)
        if self.details:
            data["details"] = self.details
        return data


def _is_not_found_response(payload: Any) -> bool:
    """Return whether a parsed response describes a missing resource."""
    if not isinstance(payload, dict):
        return False
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    message = payload.get("errorMessage") or payload.get("message") or payload.get("detail")
    return code in (404, "404") or (
        isinstance(message, str) and ("not found" in message.lower() or "does not exist" in message.lower())
    )


def _extract_error(payload: Any) -> dict[str, Any] | None:
    """Return structured device error details, if present."""
    if not isinstance(payload, dict):
        return None
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    errors = payload.get("errors")
    if isinstance(code, int) and code >= 400:
        return {"code": code, "message": payload.get("errorMessage") or payload.get("message")}
    if isinstance(errors, list) and errors:
        return {"errors": errors, "message": payload.get("message")}
    return None


def _payload_secret_values(payload: Any) -> list[str]:
    """Collect the credential strings of a request body (SECRET_REST_KEYS, at any depth)."""
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in SECRET_REST_KEYS:
                if isinstance(value, dict):
                    value = value.get("value")
                if isinstance(value, str) and value:
                    values.append(value)
                    continue
            values.extend(_payload_secret_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_payload_secret_values(item))
    return values


def _scrub_secrets(value: Any, secrets: list[str]) -> Any:
    """Return *value* with every secret (raw, JSON-escaped or repr-escaped) replaced inside its strings.

    The repr form is what a nested error object turned into text with str()
    carries for a value holding both quote types, backslashes or control
    characters; a 2xx error document bypasses the HTTPAPI sanitizer, which
    removes the same forms.
    """
    if not secrets:
        return value
    if isinstance(value, dict):
        return {key: _scrub_secrets(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_secrets(item, secrets) for item in value]
    if isinstance(value, str):
        forms = set()
        for secret in secrets:
            forms.update(
                (secret, json.dumps(secret)[1:-1], json.dumps(secret, ensure_ascii=False)[1:-1], repr(secret)[1:-1])
            )
        for form in sorted((item for item in forms if item), key=len, reverse=True):
            value = value.replace(form, SECRET_MASK)
    return value


def _is_global_patch(method: str, path: str) -> bool:
    """True for the PATCH of the RADIUS globals, which a re-read can attribute field by field."""
    return method == "PATCH" and path == CONFIG_PATH


def _remember_secrets(connection: Connection, payload: Any) -> None:
    """Add the credentials of a write to the stored ones, before it is sent.

    Once written (or possibly written, if the answer is lost) the password,
    shared secret or profile key is stored on the device, and an error answering
    a later write of the task can quote it although that request carries none.
    """
    stored = list(getattr(connection, "_extreme_fe_radius_stored_secrets", []))
    stored.extend(value for value in _payload_secret_values(payload) if value not in stored)
    connection._extreme_fe_radius_stored_secrets = stored


def _scrub_connection_error(connection: Connection, exc: ConnectionError) -> ConnectionError:
    """Return *exc*, or a copy whose message and err carry no credential read from the device.

    The HTTPAPI sanitizer only knows the credentials of the request and its own
    response, so a device error quoting one read earlier (the global password,
    a shared secret, a profile key) would reach the result. The stored values
    are masked here, before the error leaves the module's request helper.
    """
    stored = list(getattr(connection, "_extreme_fe_radius_stored_secrets", []))
    if not stored:
        return exc
    message = to_text(exc)
    scrubbed = _scrub_secrets(message, stored)
    err = getattr(exc, "err", None)
    scrubbed_err = _scrub_secrets(to_text(err), stored) if err is not None else None
    if scrubbed == message and scrubbed_err == (to_text(err) if err is not None else None):
        return exc
    kwargs: dict[str, Any] = {}
    if getattr(exc, "code", None) is not None:
        kwargs["code"] = exc.code
    if scrubbed_err is not None:
        kwargs["err"] = scrubbed_err
    return ConnectionError(scrubbed, **kwargs)


def _call_api(
    connection: Connection,
    *,
    method: str,
    path: str,
    payload: Any | None = None,
    allow_not_found: bool = False,
) -> Any:
    """Send one REST request, reject errors, and track confirmed mutations."""
    if method in MUTATING_METHODS:
        _remember_secrets(connection, payload)
    for attempt in range(OPERATION_RETRY_ATTEMPTS):
        try:
            response = connection.send_request(payload, path=path, method=method)
        except ConnectionError as exc:
            if allow_not_found and getattr(exc, "code", None) == 404:
                return None
            if "operation in progress" in to_text(exc).lower() and attempt < OPERATION_RETRY_ATTEMPTS - 1:
                sleep(OPERATION_RETRY_DELAY)
                continue
            if method in MUTATING_METHODS and answer_unknown(exc) and not _is_global_patch(method, path):
                # No answer (a lost connection; no code, or a negative JSON-RPC
                # code of the persistent connection): the device may have applied the
                # write, so the task reports changed, as for a write that succeeded.
                # The global PATCH is left to its re-read attribution
                # (_attribute_global_patch_failure()), which can prove it was not.
                connection._extreme_fe_radius_changed = True
            raise _scrub_connection_error(connection, exc) from None
        if allow_not_found and _is_not_found_response(response):
            return None
        error = _extract_error(response)
        if error:
            if "operation in progress" in to_text(error).lower() and attempt < OPERATION_RETRY_ATTEMPTS - 1:
                sleep(OPERATION_RETRY_DELAY)
                continue
            if method == "GET":
                # A GET sends no credential to scrub, and the document's free-form
                # text could quote a stored RADIUS secret: only its code is kept.
                code = error.get("code")
                raise FeRadiusError(
                    "Device rejected GET {0}{1}".format(
                        path, " (error code %d)" % code if isinstance(code, int) else ""
                    ),
                    details={"code": code} if isinstance(code, int) else {},
                )
            # A 2xx error document is returned to the module unscrubbed; a device
            # quoting the submitted body must not carry its credentials into details.
            # The credentials the response itself carries (a stored secret.value
            # in its errors, say) are collected as well, so a non-secret PATCH
            # cannot pass them on either, structured or quoted in its message.
            raise FeRadiusError(
                "Device rejected {0} {1}".format(method, path),
                details=_scrub_secrets(
                    error,
                    _payload_secret_values(payload)
                    + _payload_secret_values(response)
                    + list(getattr(connection, "_extreme_fe_radius_stored_secrets", [])),
                ),
            )
        if method in MUTATING_METHODS:
            connection._extreme_fe_radius_changed = True
        return response
    raise FeRadiusError("RADIUS operation retries exhausted")


def _validate_range(name: str, value: Any, minimum: int, maximum: int) -> None:
    """Validate an optional integer against an OpenAPI range."""
    if value is not None and not minimum <= value <= maximum:
        raise FeRadiusError("{0} must be between {1} and {2}".format(name, minimum, maximum))


def _remove_none(value: Any) -> Any:
    """Remove values Ansible injected for omitted nested options."""
    if isinstance(value, dict):
        return {key: _remove_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_remove_none(item) for item in value]
    return value


def _validate_config(config: dict[str, Any]) -> None:
    """Validate cross-field requirements and OpenAPI lengths/ranges."""
    global_config = config.get("global") or {}
    ranges = {
        "account_attr": (192, 240),
        "access_priority_attr": (192, 240),
        "auth_info_attr": (0, 255),
        "command_access_attr": (192, 240),
        "cli_commands_attr": (192, 240),
        "cli_commands_count": (1, 40),
        "max_server": (1, 10),
        "mcast_addr_attr": (0, 255),
        "keep_alive_timer": (30, 600),
        "unreachable_timer": (30, 600),
    }
    for field, limits in ranges.items():
        _validate_range("global.{0}".format(field), global_config.get(field), *limits)
    for field in ("username", "password"):
        value = global_config.get(field)
        if value is not None and not 1 <= len(value) <= 16:
            raise FeRadiusError("global.{0} must be 1-16 characters".format(field))

    identities: set[tuple[str, ...]] = set()
    for server in config.get("servers") or []:
        mode = server["server_mode"]
        if mode == "AAA" and not server.get("used_by"):
            raise FeRadiusError("servers[].used_by is required for AAA servers")
        invalid_fields = DYN_AUTH_ONLY_SERVER_FIELDS if mode == "AAA" else AAA_ONLY_SERVER_FIELDS
        supplied_invalid = sorted(invalid_fields.intersection(server))
        if supplied_invalid:
            raise FeRadiusError("Fields {0} are not valid for {1} servers".format(", ".join(supplied_invalid), mode))
        identity = _server_identity(server)
        if identity in identities:
            raise FeRadiusError(
                "RADIUS server {0} is listed more than once in 'config.servers'; list each server once".format(
                    _identity_label(identity)
                )
            )
        identities.add(identity)
        _validate_range("servers[].auth_port", server.get("auth_port"), 1, 65535)
        _validate_range("servers[].account_port", server.get("account_port"), 1, 65535)
        _validate_range("servers[].retries", server.get("retries"), 0, 6)
        _validate_range("servers[].timeout", server.get("timeout"), 1, 180)
        _validate_range("servers[].priority", server.get("priority"), 1, 10)
        _validate_range("servers[].port", server.get("port"), 1024, 65535)
        secret = server.get("secret")
        secret_maximum = 32 if mode == "AAA" else 128
        if secret is not None and len(secret) > secret_maximum:
            raise FeRadiusError("servers[].secret must not exceed {0} characters for {1}".format(secret_maximum, mode))
        profile = server.get("secure_profile")
        if profile is not None and not 1 <= len(profile) <= 16:
            raise FeRadiusError("servers[].secure_profile must be 1-16 characters")

    profile_names: set[str] = set()
    for profile in config.get("secure_profiles") or []:
        name = profile["name"]
        if not 1 <= len(name) <= 16:
            raise FeRadiusError("secure_profiles[].name must be 1-16 characters")
        if name in profile_names:
            raise FeRadiusError(
                "Secure profile '{0}' is listed more than once in 'config.secure_profiles'; list each profile once".format(
                    name
                )
            )
        profile_names.add(name)
        limits = {"root_cert": 30720, "cert": 3072, "key": 3072, "password": 255}
        for field, maximum in limits.items():
            value = profile.get(field)
            minimum = 0 if field == "password" else 1
            if value is not None and not minimum <= len(value) <= maximum:
                raise FeRadiusError("secure_profiles[].{0} must be {1}-{2} characters".format(field, minimum, maximum))


def _translate(source: dict[str, Any], field_map: dict[str, Any]) -> dict[str, Any]:
    """Translate known REST API fields to Ansible names, never copying a secret leaf."""
    translated = {}
    for ansible_name, rest_names in field_map.items():
        if ansible_name in SECRET_FIELDS:
            continue
        for rest_name in (rest_names,) if isinstance(rest_names, str) else rest_names:
            if rest_name in source:
                translated[ansible_name] = source[rest_name]
                break
    return translated


def _raw_servers(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the Fabric Engine server rows of an aggregate GET response."""
    return [
        item
        for item in (source.get("servers") or [])
        if isinstance(item, dict) and item.get("serverMode") in ("AAA", "DYN_AUTH")
    ]


def _raw_profiles(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the secure-profile rows of an enriched GET response."""
    return [item for item in (source.get("secureProfiles") or []) if isinstance(item, dict)]


def _to_ansible_server(item: dict[str, Any]) -> dict[str, Any]:
    """Translate one server row to options valid for its server mode."""
    server = _translate(item, SERVER_FIELD_MAP)
    invalid = AAA_ONLY_SERVER_FIELDS if server["server_mode"] == "DYN_AUTH" else DYN_AUTH_ONLY_SERVER_FIELDS
    # A GET reports secureMode NONE for a server that uses plain UDP; the option
    # (and the update schema) only takes TLS/DTLS, so such a value is left out and
    # secure_enabled alone describes the server.
    return {
        key: value
        for key, value in server.items()
        if key not in invalid and not (key == "secure_mode" and value not in SECURE_MODE_CHOICES)
    }


def _to_ansible_config(raw: Any) -> dict[str, Any]:
    """Normalize the aggregate GET response to the config option shape, without secrets."""
    source = raw if isinstance(raw, dict) else {}
    servers = [_to_ansible_server(item) for item in _raw_servers(source)]
    # An empty certificate means none is installed; config accepts 1+ characters only.
    profiles = [
        {key: value for key, value in _translate(item, PROFILE_FIELD_MAP).items() if key == "name" or value != ""}
        for item in _raw_profiles(source)
    ]
    return {
        "global": _translate(source, GLOBAL_FIELD_MAP),
        "servers": sorted(servers, key=_server_identity),
        "secure_profiles": sorted(profiles, key=lambda profile: profile.get("name", "")),
    }


def _to_ansible_read_only(raw: Any) -> dict[str, Any]:
    """Collect device-reported values that are not options, keyed like the config rows."""
    source = raw if isinstance(raw, dict) else {}
    servers = []
    for item in _raw_servers(source):
        server = _to_ansible_server(item)
        identity = {key: server[key] for key in ("server_mode", "host_type", "address", "used_by") if key in server}
        servers.append(identity | _translate(item, SERVER_READ_ONLY_FIELD_MAP))
    profiles = [
        _translate(item, {"name": "name"}) | _translate(item, PROFILE_READ_ONLY_FIELD_MAP)
        for item in _raw_profiles(source)
    ]
    return {
        "global": _translate(source, GLOBAL_READ_ONLY_FIELD_MAP),
        "servers": sorted(servers, key=_server_identity),
        "secure_profiles": sorted(profiles, key=lambda profile: profile.get("name", "")),
    }


def _to_ansible_runtime_state(raw: Any) -> dict[str, Any]:
    """Normalize Fabric Engine RADIUS runtime state to Ansible field names."""
    source = raw if isinstance(raw, dict) else {}
    runtime_state = _translate(source, RUNTIME_FIELD_MAP)
    if "servers" in source:
        runtime_state["servers"] = [
            _translate(item, RUNTIME_FIELD_MAP)
            for item in (source.get("servers") or [])
            if isinstance(item, dict) and item.get("serverMode") in ("AAA", "DYN_AUTH")
        ]
    return runtime_state


def _fetch_source(connection: Connection) -> dict[str, Any]:
    """Retrieve aggregate RADIUS config and enrich every secure profile by name."""
    aggregate = _call_api(connection, method="GET", path=CONFIG_PATH)
    source = deepcopy(aggregate) if isinstance(aggregate, dict) else {}
    profile_list = _call_api(connection, method="GET", path=PROFILE_PATH)
    profiles = profile_list if isinstance(profile_list, list) else []
    detailed_profiles = []
    for profile in profiles:
        if not isinstance(profile, dict) or not profile.get("name"):
            continue
        detail = _call_api(
            connection,
            method="GET",
            path=_profile_item_path(str(profile["name"])),
            allow_not_found=True,
        )
        detailed_profiles.append(detail if isinstance(detail, dict) else profile)
    source["secureProfiles"] = detailed_profiles
    return source


def _fetch_configuration(connection: Connection) -> dict[str, Any]:
    """Retrieve the RADIUS configuration in the config option shape."""
    return _to_ansible_config(_fetch_source(connection))


def _canonical_address(address: Any) -> str:
    """Return an IP address in one notation, so 2001:db8::10 matches 2001:db8:0:0:0:0:0:10.

    Fabric Engine stores and reports an IPv6 address uncompressed, while a user
    usually writes it compressed. A value that is not an IP address
    is compared as written.
    """
    text = str(address if address is not None else "")
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return text


def _server_identity(server: dict[str, Any]) -> tuple[str, ...]:
    """Return the path-level identity of a Fabric Engine RADIUS server, its address compared as an IP address."""
    base = (
        str(server.get("server_mode", "")),
        str(server.get("host_type", "")),
        _canonical_address(server.get("address")),
    )
    if server.get("server_mode") == "AAA":
        return base + (str(server.get("used_by", "")),)
    return base


def _identity_label(identity: tuple[str, ...]) -> str:
    """A server identity as one quoted, user-facing value, e.g. 'AAA/IPv4/10.0.0.1/LOGIN'."""
    return "'%s'" % "/".join(identity)


def _server_payload(server: dict[str, Any]) -> dict[str, Any]:
    """Build a POST payload for an AAA server or dynamic client."""
    payload = {rest_name: server[name] for name, rest_name in SERVER_FIELD_MAP.items() if name in server}
    if "secret" in server:
        payload["secret"] = {"value": server["secret"]}
    return payload


def _dynamic_payload(server: dict[str, Any]) -> dict[str, Any]:
    """Build the writable body for the dynamic-client PATCH endpoint."""
    payload = {name: server[name] for name in ("enabled", "port") if name in server}
    if "secret" in server:
        payload["secret"] = {"value": server["secret"]}
    return payload


def _profile_payload(profile: dict[str, Any], include_name: bool) -> dict[str, Any]:
    """Build a secure-profile POST or PATCH payload.

    The private key and its passphrase are write-only (PROFILE_FIELD_MAP only
    covers the readable fields), so they are added here as the plain strings
    RadiusSecureProfileUpdateSettingsByName takes.
    """
    payload = {
        rest_name: profile[name]
        for name, rest_name in PROFILE_FIELD_MAP.items()
        if name in profile and (include_name or name != "name")
    }
    for name in ("key", "password"):
        if profile.get(name) is not None:
            payload[name] = profile[name]
    return payload


def _server_delete_path(server: dict[str, Any]) -> str:
    """Build the correct delete endpoint for a server mode."""
    values = {key: quote(str(value), safe="") for key, value in server.items()}
    if server["server_mode"] == "DYN_AUTH":
        return DYNAMIC_PATH.format(host_type=values["host_type"], host=values["address"])
    return AAA_DELETE_PATH.format(
        server_mode=values["server_mode"],
        host_type=values["host_type"],
        host=values["address"],
        used_by=values["used_by"],
    )


def _profile_item_path(name: str) -> str:
    """Build a secure-profile item path."""
    return PROFILE_ITEM_PATH.format(name=quote(name, safe=""))


def _public_server(server: dict[str, Any]) -> dict[str, Any]:
    """Return a server without its shared secret."""
    return {key: value for key, value in server.items() if key != "secret"}


def _public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Return a profile without private-key material or passphrase."""
    return {key: value for key, value in profile.items() if key not in {"key", "password"}}


def _global_payload(config: dict[str, Any]) -> dict[str, Any]:
    """Translate global Ansible parameters to REST API fields."""
    return {rest_name: config[name] for name, rest_name in GLOBAL_FIELD_MAP.items() if name in config}


def _global_changed(current: dict[str, Any], desired: dict[str, Any]) -> bool:
    """Compare global values, treating an intentionally supplied password as changed."""
    return "password" in desired or any(current.get(key) != value for key, value in desired.items())


def _server_changed(current: dict[str, Any], desired: dict[str, Any]) -> bool:
    """Compare writable server values; supplied shared secrets always differ."""
    return "secret" in desired or any(
        current.get(key) != value
        for key, value in desired.items()
        if key not in {"secret", "server_mode", "host_type", "address", "used_by"}
    )


def _profile_changed(current: dict[str, Any], desired: dict[str, Any]) -> bool:
    """Compare profile values; supplied private-key material always differs."""
    return any(key in desired for key in ("key", "password")) or any(
        current.get(key) != value for key, value in desired.items() if key not in {"key", "password", "name"}
    )


# The device mask an earlier release returned in gathered: exactly six asterisks, or the
# string Ansible makes of that {value: "******"} object (or of an empty {value: ""}). An
# all-asterisk secret of another length is a real secret and is kept. Matched with
# fullmatch(): a $ anchor also matches before a final newline, which would drop a
# real secret such as "******\n".
_MASKED_SECRET = re.compile(r"""\*{6}|\{'value': '(\*{6})?'\}""")


def _drop_masked_secrets(module: AnsibleModule, config: dict[str, Any], state: str) -> None:
    """Drop a server secret that is a mask, so a placeholder never replaces the stored secret.

    Gathered output of earlier releases carried each server's secret as the
    device mask {value: "******"}; the option is a string, so re-applying it sent
    "{'value': '******'}" as the new shared secret. Such a value writes
    nothing: it is removed with a warning, as an omitted secret is. With
    state=deleted the server named is deleted, its stored secret with it, so the
    warning only says the placeholder is not written.
    """
    for server in config.get("servers") or []:
        secret = server.get("secret")
        if isinstance(secret, str) and _MASKED_SECRET.fullmatch(secret):
            del server["secret"]
            if state == STATE_DELETED:
                message = "servers[].secret of RADIUS server {0} is a mask, not a secret, and is not written"
            else:
                message = (
                    "servers[].secret of RADIUS server {0} is a mask, not a secret, and is ignored; the stored "
                    "shared secret is left unchanged"
                )
            module.warn(message.format(_identity_label(_server_identity(server))))


def _require_server_secret(server: dict[str, Any], operation: str) -> None:
    """Require a shared secret whenever POST must create a server."""
    if "secret" not in server:
        raise FeRadiusError(
            "servers[].secret is required to {0} server {1}".format(
                operation, _identity_label(_server_identity(server))
            )
        )


def _preflight_server_writes(
    current: list[dict[str, Any]],
    configured: list[dict[str, Any]],
) -> None:
    """Validate every required POST secret before any device mutation starts."""
    current_by_id = {_server_identity(item): item for item in current}
    for server in configured:
        existing = current_by_id.get(_server_identity(server))
        if existing is None:
            _require_server_secret(server, "create")
        elif server["server_mode"] == "AAA" and _server_changed(existing, server):
            _require_server_secret(server, "replace the changed AAA")


def _apply_global(
    connection: Connection,
    current: dict[str, Any],
    desired: dict[str, Any],
    check_mode: bool,
) -> bool:
    """PATCH changed RADIUS global fields."""
    if not desired or not _global_changed(current, desired):
        return False
    if not check_mode:
        # One PATCH carries every changed global field (up to ~19); a rejection is
        # attributed field by field from a re-read of the globals. Only
        # fields that differ are sent, so a field that already held its value
        # cannot read back as "applied" after a rejected PATCH. The write-only
        # password cannot be compared and is sent whenever it is supplied.
        changed_fields = {
            key: value for key, value in desired.items() if key in WRITE_ONLY_GLOBALS or current.get(key) != value
        }
        payload = _global_payload(changed_fields)
        try:
            _call_api(connection, method="PATCH", path=CONFIG_PATH, payload=payload)
        except (ConnectionError, FeRadiusError) as exc:
            raise _attribute_global_patch_failure(connection, payload, exc) from exc
    current.update({key: value for key, value in desired.items() if key != "password"})
    return True


# -- Global PATCH Failure Attribution -----------------------------------------


def _reread_error_document(document: Any) -> str | None:
    """Return a short description when a re-read answered with an error document, else None.

    Only a validated numeric code is kept: the device's text could quote a
    stored RADIUS credential, and a 2xx error document bypasses the HTTPAPI
    sanitizer.
    """
    if not isinstance(document, dict):
        return None
    status = document.get("statusCode", document.get("code"))
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    errors = document.get("errors")
    is_error = bool(document.get("errorCode")) or (isinstance(status, int) and status >= 400)
    if not (is_error or (isinstance(errors, list) and errors)):
        return None
    code = document.get("errorCode") or status
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    return "error code %d" % code if isinstance(code, int) and not isinstance(code, bool) else "no error code"


def _extend_msg(msg: str, suffix: str) -> str:
    """Append a sentence to an error message, adding the full stop it may lack."""
    msg = (msg or "").rstrip()
    return "%s %s" % (msg if msg.endswith((".", "!", "?")) else msg + ".", suffix)


def _reread_globals(connection: Connection) -> tuple[dict[str, Any] | None, str | None]:
    """Re-read GET /v0/configuration/radius once; return (record, None) or (None, reason)."""
    try:
        record = connection.send_request(None, path=CONFIG_PATH, method="GET")
    except ConnectionError as exc:
        return None, to_text(exc)
    embedded = _reread_error_document(record)
    if embedded:
        return None, "the re-read of %s returned an error document (%s)" % (CONFIG_PATH, embedded)
    if not isinstance(record, dict) or not record:
        return None, "the device returned no configuration for %s" % CONFIG_PATH
    return record, None


def _global_attribution_sentence(
    applied: list[str], not_applied: list[str], unknown: list[str], unreported: list[str] | None = None
) -> str:
    """Describe how far a rejected global PATCH got, from the re-read of the globals."""
    tail = "; unknown (not verifiable by GET): %s" % ", ".join(unknown) if unknown else ""
    if unreported:
        tail += "; unknown (not reported by the re-read): %s" % ", ".join(unreported)
    total = len(applied) + len(not_applied) + len(unreported or [])
    if unreported:
        return (
            "The device rejected the PATCH of %s; a re-read of the %d comparable fields shows applied: %s; not applied: %s%s."
            % (
                CONFIG_PATH,
                total,
                ", ".join(applied) or "none",
                ", ".join(not_applied) or "none",
                tail,
            )
        )
    if not applied:
        return "A re-read of %s shows none of the %d comparable fields was applied: %s%s." % (
            CONFIG_PATH,
            total,
            ", ".join(not_applied) or "none",
            tail,
        )
    if not not_applied:
        return "The device rejected the PATCH of %s, but a re-read shows all %d comparable fields applied: %s%s." % (
            CONFIG_PATH,
            total,
            ", ".join(applied),
            tail,
        )
    return "The device rejected the PATCH of %s after applying %d of %d comparable fields: %s; not applied: %s%s." % (
        CONFIG_PATH,
        len(applied),
        total,
        ", ".join(applied),
        ", ".join(not_applied),
        tail,
    )


def _attribute_global_patch_failure(
    connection: Connection,
    payload: dict[str, Any],
    exc: ConnectionError | FeRadiusError,
) -> FeRadiusError:
    """Build the error for a rejected global PATCH, naming the fields the device applied.

    The globals are re-read and every comparable payload field is compared with
    the read-back value. Write-only and trigger fields are only named in
    unknown_fields; secret values never appear in the error (attempted_payload
    carries them masked). changed is True when a comparable field was applied
    (the payload holds changed fields only); main() also reports changed when an
    earlier request of the task succeeded.
    """
    unknown = [key for key in payload if key in UNVERIFIABLE_REST_FIELDS]
    comparable = [key for key in payload if key not in UNVERIFIABLE_REST_FIELDS]
    details: dict[str, Any] = dict(exc.details) if isinstance(exc, FeRadiusError) else {}
    details.update(
        {
            "attempted_payload": {
                key: (SECRET_MASK if key in SECRET_GLOBAL_REST_FIELDS else value) for key, value in payload.items()
            },
            "resource": CONFIG_PATH,
        }
    )
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
    if unknown:
        details["unknown_fields"] = unknown

    record, reread_error = _reread_globals(connection)
    if record is not None and comparable and all(record.get(key) is None for key in comparable):
        # Reports none of the comparable fields: nothing can be attributed.
        record = None
        reread_error = "the re-read of %s did not report %s" % (CONFIG_PATH, ", ".join(comparable))
    if record is None:
        details["reread_error"] = reread_error
        suffix = (
            "The device may have applied part of the PATCH of %s before refusing it, but re-reading the "
            "resource failed (%s), so it is unknown which of the %d attempted fields (%s) were applied."
            % (CONFIG_PATH, reread_error, len(payload), ", ".join(payload))
        )
        # Without an answer the PATCH may have been applied: report changed.
        no_answer = isinstance(exc, ConnectionError) and answer_unknown(exc)
        if no_answer:
            details["outcome"] = "unknown"
        return FeRadiusError(_extend_msg(to_text(exc), suffix), details=details, extra=extra, changed=no_answer)

    # A comparable field the re-read omits or reports as null is established
    # neither way: unknown, without discarding what the other fields confirm.
    unreported = [key for key in comparable if record.get(key) is None]
    applied = [key for key in comparable if key not in unreported and record[key] == payload[key]]
    not_applied = [key for key in comparable if key not in unreported and key not in applied]
    details["applied_fields"] = applied
    details["not_applied_fields"] = not_applied
    if unreported:
        details["unknown_fields"] = unknown + unreported
        details["reread_error"] = "the re-read of %s did not report %s" % (CONFIG_PATH, ", ".join(unreported))
    suffix = _global_attribution_sentence(applied, not_applied, unknown, unreported)
    # Without an answer, a field the re-read cannot verify (the write-only
    # password, clearStat, or one it does not report) may have been applied;
    # only a re-read proving every attempted field not applied clears changed.
    no_answer = isinstance(exc, ConnectionError) and answer_unknown(exc)
    unverified = bool(unknown or unreported)
    if no_answer and unverified and not applied:
        details["outcome"] = "unknown"
    return FeRadiusError(
        _extend_msg(to_text(exc), suffix),
        details=details,
        extra=extra,
        changed=bool(applied) or (no_answer and unverified),
    )


def _delete_server(connection: Connection, server: dict[str, Any], check_mode: bool) -> None:
    """Delete one AAA server or dynamic authorization client.

    A 404 means the server is gone: it was just read as present, and HTTPAPI
    resends a DELETE after some transport failures, so a first attempt that
    deleted it and lost its answer makes the resend answer 404.
    """
    if not check_mode:
        _call_api(connection, method="DELETE", path=_server_delete_path(server), allow_not_found=True)
        # Also when the DELETE answered 404 (allow_not_found): the server is gone,
        # so a later failure of the task still reports the change.
        connection._extreme_fe_radius_changed = True


def _conflict_code(exc: Exception) -> Any:
    """The HTTP status of a failed request: a ConnectionError code or an error document's code."""
    code = getattr(exc, "code", None)
    if code is None and isinstance(exc, FeRadiusError):
        code = exc.details.get("code")
    # A negative JSON-RPC code (a lost answer) is not an HTTP status.
    return http_status(code)


def _verify_created_on_conflict(
    connection: Connection, exc: Exception, label: str, payload: Any, find: Any, differs: Any
) -> None:
    """Handle a POST answered 409 ("already exists") for an object just read as absent.

    HTTPAPI resends a request after some transport failures, so a first POST that
    created the object and lost its answer makes the resend answer 409; but the
    module cannot tell that from another writer creating the same object after
    the read. The configuration is re-read. The object, present with the
    submitted settings, counts as created and as a change only when *payload*
    (the POST body) carries no credential: a shared secret, private key or
    passphrase cannot be compared, so a match does not prove the stored one is
    the submitted one. Then, and when it is present with other settings or not
    readable, the outcome is unknown: the task fails with changed=true. *find*
    returns the object from the re-read config or None; *differs* compares it
    with the submitted one.
    """
    try:
        existing = find(_fetch_configuration(connection))
    except (ConnectionError, FeRadiusError) as reread_exc:
        raise FeRadiusError(
            "The POST creating %s answered 409 (already exists), and the configuration could not be re-read to "
            "check it (%s); it may have been created by a first attempt whose answer was lost."
            % (label, to_text(reread_exc)),
            details={"outcome": "unknown", "reread_error": to_text(reread_exc)},
            changed=True,
        ) from exc
    if existing is not None and not differs(existing):
        # The credential options the POST carried (secret; key, password), by name
        # only and by presence: an empty secret or passphrase is a write-only value
        # the re-read cannot confirm either.
        credentials = sorted(key for key in payload if key in SECRET_REST_KEYS and payload[key] is not None)
        if not credentials:
            connection._extreme_fe_radius_changed = True
            return
        raise FeRadiusError(
            "The POST creating %s answered 409 (already exists). The re-read shows it with the submitted settings, "
            "but its stored %s cannot be compared: it may have been created by a first attempt whose answer was "
            "lost, or by another writer with a different value, so the outcome is unknown. Run the task again to "
            "re-apply it." % (label, ", ".join(credentials)),
            details={"outcome": "unknown", "unknown_fields": credentials},
            changed=True,
        ) from exc
    raise FeRadiusError(
        "The POST creating %s answered 409 (already exists), and %s; it may have been created by a first attempt "
        "whose answer was lost, so the outcome is unknown."
        % (
            label,
            "the re-read shows it with other settings" if existing is not None else "the re-read does not list it",
        ),
        details={"outcome": "unknown"},
        changed=True,
    ) from exc


def _create_server(connection: Connection, server: dict[str, Any], check_mode: bool) -> None:
    """Create one AAA server or dynamic authorization client; a 409 is checked (see _verify_created_on_conflict())."""
    _require_server_secret(server, "create")
    if not check_mode:
        try:
            _call_api(connection, method="POST", path=SERVER_PATH, payload=_server_payload(server))
        except (ConnectionError, FeRadiusError) as exc:
            if _conflict_code(exc) != 409:
                raise
            identity = _server_identity(server)
            _verify_created_on_conflict(
                connection,
                exc,
                "RADIUS server %s" % _identity_label(identity),
                _server_payload(server),
                lambda config: next((s for s in config["servers"] if _server_identity(s) == identity), None),
                lambda existing: _server_changed(existing, _public_server(server)),
            )


def _update_server(
    connection: Connection,
    current: dict[str, Any],
    desired: dict[str, Any],
    check_mode: bool,
) -> None:
    """PATCH a dynamic client or replace an AAA server lacking an update endpoint."""
    if desired["server_mode"] == "DYN_AUTH":
        if not check_mode:
            _call_api(
                connection,
                method="PATCH",
                path=_server_delete_path(current),
                payload=_dynamic_payload(desired),
            )
        return
    _require_server_secret(desired, "replace the changed AAA")
    _delete_server(connection, current, check_mode)
    _create_server(connection, desired, check_mode)


def _requires_aaa_delete(
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    *,
    exact: bool,
    recreate_all: bool,
) -> bool:
    """Return whether server reconciliation will delete an AAA server."""
    desired_by_id = {_server_identity(item): item for item in desired}
    for item in current:
        if item.get("server_mode") != "AAA":
            continue
        identity = _server_identity(item)
        replacement = desired_by_id.get(identity)
        if exact and (replacement is None or recreate_all):
            return True
        if replacement is not None and _server_changed(item, replacement):
            return True
    return False


def _reconcile_servers(
    connection: Connection,
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    *,
    exact: bool,
    recreate_all: bool,
    check_mode: bool,
) -> tuple[bool, list[dict[str, Any]]]:
    """Reconcile the server collection according to singleton list semantics."""
    changed = False
    current_by_id = {_server_identity(item): item for item in current}
    # A listed server that exists keeps the device's notation of its address, so
    # the update path and the predicted after use what the device reports.
    desired_by_id = {}
    for item in desired:
        identity = _server_identity(item)
        existing = current_by_id.get(identity)
        desired_by_id[identity] = item if existing is None else dict(item, address=existing["address"])
    if exact:
        for identity, item in current_by_id.items():
            if identity not in desired_by_id or recreate_all:
                _delete_server(connection, item, check_mode)
                changed = True
    for identity, item in desired_by_id.items():
        existing = current_by_id.get(identity)
        if existing is None or recreate_all:
            _create_server(connection, item, check_mode)
            changed = True
        elif _server_changed(existing, item):
            replacement = item
            if not exact and item["server_mode"] == "AAA":
                replacement = {
                    key: value for key, value in existing.items() if key in SERVER_OPTIONS and value is not None
                } | item
            _update_server(connection, existing, replacement, check_mode)
            changed = True
    if exact:
        # From desired_by_id, so an existing server keeps the device's address notation.
        predicted = [_public_server(item) for item in desired_by_id.values()]
    else:
        predicted_by_id = {identity: deepcopy(item) for identity, item in current_by_id.items()}
        for identity, item in desired_by_id.items():
            predicted_by_id[identity] = _public_server(item) | {
                key: value for key, value in predicted_by_id.get(identity, {}).items() if key not in item
            }
        predicted = list(predicted_by_id.values())
    return changed, sorted(predicted, key=_server_identity)


def _delete_profile(connection: Connection, name: str, check_mode: bool) -> None:
    """Delete one Secure RADIUS certificate profile; a 404 means it is gone (see _delete_server())."""
    if not check_mode:
        _call_api(connection, method="DELETE", path=_profile_item_path(name), allow_not_found=True)
        # Also when the DELETE answered 404 (see _delete_server()).
        connection._extreme_fe_radius_changed = True


def _create_profile(connection: Connection, profile: dict[str, Any], check_mode: bool) -> None:
    """Create one Secure RADIUS certificate profile; a 409 is checked (see _verify_created_on_conflict())."""
    if not check_mode:
        try:
            _call_api(
                connection,
                method="POST",
                path=PROFILE_PATH,
                payload=_profile_payload(profile, include_name=True),
            )
        except (ConnectionError, FeRadiusError) as exc:
            if _conflict_code(exc) != 409:
                raise
            name = profile.get("name")
            _verify_created_on_conflict(
                connection,
                exc,
                "secure profile %s" % name,
                _profile_payload(profile, include_name=True),
                lambda config: next((p for p in config["secure_profiles"] if p.get("name") == name), None),
                lambda existing: _profile_changed(existing, _public_profile(profile)),
            )


def _reconcile_profiles(
    connection: Connection,
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    *,
    exact: bool,
    recreate_all: bool,
    check_mode: bool,
) -> tuple[bool, list[dict[str, Any]]]:
    """Reconcile Secure RADIUS profiles with POST, PATCH, and DELETE."""
    changed = False
    current_by_name = {item.get("name"): item for item in current}
    desired_by_name = {item["name"]: item for item in desired}
    if exact:
        for name in current_by_name:
            if name != DEFAULT_PROFILE_NAME and (name not in desired_by_name or recreate_all):
                _delete_profile(connection, str(name), check_mode)
                changed = True
    for name, item in desired_by_name.items():
        existing = current_by_name.get(name)
        if existing is None:
            if name == DEFAULT_PROFILE_NAME:
                raise FeRadiusError("The built-in secure profile 'default' cannot be created")
            _create_profile(connection, item, check_mode)
            changed = True
        elif recreate_all and name != DEFAULT_PROFILE_NAME:
            _create_profile(connection, item, check_mode)
            changed = True
        elif _profile_changed(existing, item):
            if not check_mode:
                _call_api(
                    connection,
                    method="PATCH",
                    path=_profile_item_path(name),
                    payload=_profile_payload(item, include_name=False),
                )
            changed = True
    if exact:
        predicted_by_name = {
            name: _public_profile(item)
            | {key: value for key, value in current_by_name.get(name, {}).items() if key not in item}
            for name, item in desired_by_name.items()
        }
        if DEFAULT_PROFILE_NAME in current_by_name:
            predicted_by_name.setdefault(
                DEFAULT_PROFILE_NAME,
                deepcopy(current_by_name[DEFAULT_PROFILE_NAME]),
            )
        predicted = list(predicted_by_name.values())
    else:
        predicted_by_name = {name: deepcopy(item) for name, item in current_by_name.items()}
        for name, item in desired_by_name.items():
            predicted_by_name[name] = _public_profile(item) | {
                key: value for key, value in predicted_by_name.get(name, {}).items() if key not in item
            }
        predicted = list(predicted_by_name.values())
    return changed, sorted(predicted, key=lambda profile: profile.get("name", ""))


def _delete_unlisted_profiles(
    connection: Connection,
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    check_mode: bool,
) -> tuple[bool, list[dict[str, Any]]]:
    """Delete custom profiles omitted from an authoritative profile list."""
    desired_names = {item["name"] for item in desired}
    retained = []
    changed = False
    for profile in current:
        name = profile.get("name")
        if name != DEFAULT_PROFILE_NAME and name not in desired_names:
            _delete_profile(connection, str(name), check_mode)
            changed = True
        else:
            retained.append(profile)
    return changed, retained


def _delete_selected(
    connection: Connection,
    current: dict[str, Any],
    config: dict[str, Any],
    check_mode: bool,
) -> tuple[bool, dict[str, Any]]:
    """Apply deleted semantics to selected fields/resources or to all resources."""
    desired = deepcopy(current)
    changed = False
    # Without config every non-secret global is reset; the write-only password is
    # left alone because GET cannot show it, so a reset could never be idempotent.
    global_fields = config.get("global") if config else VISIBLE_GLOBAL_DEFAULTS
    reset_values = {key: GLOBAL_DEFAULTS[key] for key in (global_fields or {})}

    selected_servers = config.get("servers") if config else current["servers"]
    selected_ids = {_server_identity(item) for item in (selected_servers or [])}
    deleting_aaa = any(
        server.get("server_mode") == "AAA" and _server_identity(server) in selected_ids for server in current["servers"]
    )
    pre_delete_globals = dict(reset_values)
    if deleting_aaa:
        pre_delete_globals["account_enabled"] = False
    changed |= _apply_global(connection, desired["global"], pre_delete_globals, check_mode)

    retained_servers = []
    for server in current["servers"]:
        if _server_identity(server) in selected_ids:
            _delete_server(connection, server, check_mode)
            changed = True
        else:
            retained_servers.append(server)
    desired["servers"] = retained_servers
    if (
        deleting_aaa
        and "account_enabled" not in reset_values
        and current["global"].get("account_enabled") is True
        and any(server.get("server_mode") == "AAA" for server in retained_servers)
    ):
        changed |= _apply_global(connection, desired["global"], {"account_enabled": True}, check_mode)

    selected_profiles = config.get("secure_profiles") if config else current["secure_profiles"]
    selected_names = {item["name"] for item in (selected_profiles or [])}
    retained_profiles = []
    for profile in current["secure_profiles"]:
        if profile.get("name") in selected_names and profile.get("name") != DEFAULT_PROFILE_NAME:
            _delete_profile(connection, str(profile["name"]), check_mode)
            changed = True
        else:
            retained_profiles.append(profile)
    desired["secure_profiles"] = retained_profiles
    return changed, desired


def _apply_action(
    connection: Connection,
    state: str,
    current: dict[str, Any],
    config: dict[str, Any],
    check_mode: bool,
) -> tuple[bool, dict[str, Any]]:
    """Dispatch a change-making state and return its predicted configuration."""
    if state == STATE_DELETED:
        return _delete_selected(connection, current, config, check_mode)

    _preflight_server_writes(current["servers"], config.get("servers") or [])
    desired = deepcopy(current)
    global_values = config.get("global") or {}
    if state == STATE_OVERRIDDEN:
        global_values = VISIBLE_GLOBAL_DEFAULTS | global_values

    changed = False

    exact = state == STATE_OVERRIDDEN or (state == STATE_REPLACED and "servers" in config)
    configured_servers = config.get("servers") or []
    if state == STATE_OVERRIDDEN or (state == STATE_REPLACED and "servers" in config):
        resulting_servers = configured_servers
    else:
        resulting_servers = current["servers"] + configured_servers
    if global_values.get("account_enabled") is True and not any(
        server.get("server_mode") == "AAA" for server in resulting_servers
    ):
        raise FeRadiusError("global.account_enabled requires at least one AAA server")

    deleting_aaa = _requires_aaa_delete(
        current["servers"],
        configured_servers,
        exact=exact,
        recreate_all=False,
    )
    accounting_requested_disabled = global_values.get("account_enabled") is False
    disabling_radius = global_values.get("enabled") is False and current["global"].get("account_enabled") is True
    if deleting_aaa or disabling_radius:
        changed |= _apply_global(connection, desired["global"], {"account_enabled": False}, check_mode)
        if global_values.get("account_enabled") is False:
            global_values = dict(global_values)
            global_values.pop("account_enabled")

    configured_profiles = config.get("secure_profiles") or []
    if "secure_profiles" in config:
        profiles_changed, desired["secure_profiles"] = _reconcile_profiles(
            connection,
            current["secure_profiles"],
            configured_profiles,
            exact=False,
            recreate_all=False,
            check_mode=check_mode,
        )
        changed |= profiles_changed

    if "servers" in config or state == STATE_OVERRIDDEN:
        servers_changed, desired["servers"] = _reconcile_servers(
            connection,
            current["servers"],
            configured_servers,
            exact=exact,
            recreate_all=False,
            check_mode=check_mode,
        )
        changed |= servers_changed

    if (
        deleting_aaa
        and not accounting_requested_disabled
        and "account_enabled" not in global_values
        and global_values.get("enabled") is not False
        and current["global"].get("account_enabled") is True
        and any(server.get("server_mode") == "AAA" for server in desired["servers"])
    ):
        global_values = {"account_enabled": True} | global_values
    changed |= _apply_global(connection, desired["global"], global_values, check_mode)

    profiles_are_authoritative = state == STATE_OVERRIDDEN or (state == STATE_REPLACED and "secure_profiles" in config)
    if profiles_are_authoritative:
        profiles_changed, desired["secure_profiles"] = _delete_unlisted_profiles(
            connection,
            desired["secure_profiles"],
            configured_profiles,
            check_mode,
        )
        changed |= profiles_changed
    return changed, desired


def _compute_diff(before: Any, after: Any) -> dict[str, Any]:
    """Return a compact top-level before/after difference mapping."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {} if before == after else {"value": {"before": before, "after": after}}
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def _values_included(before: Any, after: Any) -> bool:
    """Return whether every after value is represented in before."""
    if isinstance(after, dict):
        return isinstance(before, dict) and all(
            key in before and _values_included(before[key], value) for key, value in after.items()
        )
    if isinstance(after, list):
        if not isinstance(before, list) or len(before) != len(after):
            return False
        unmatched = list(before)
        for value in after:
            for index, candidate in enumerate(unmatched):
                if _values_included(candidate, value):
                    unmatched.pop(index)
                    break
            else:
                return False
        return True
    return before == after


def main() -> None:
    """Run the RADIUS resource module."""
    module = AnsibleModule(argument_spec=ARGUMENT_SPEC, supports_check_mode=True)
    result: dict[str, Any] = {"changed": False}
    connection: Connection | None = None
    try:
        if not module._socket_path:
            raise FeRadiusError("Connection type httpapi is required for this module")
        connection = Connection(module._socket_path)
        state = module.params["state"]
        config = _remove_none(module.params.get("config") or {})
        _drop_masked_secrets(module, config, state)
        if state in REQUIRES_CONFIG and not config:
            raise FeRadiusError("value of config parameter must not be empty for state {0}".format(state))
        _validate_config(config)

        source = _fetch_source(connection)
        # The stored credentials the device returned (global password, shared
        # secrets, profile keys): an error document answering a later write can
        # quote one that neither its request nor its own body carries. Each write
        # adds its own credentials (_call_api()), as they are stored from then on.
        connection._extreme_fe_radius_stored_secrets = _payload_secret_values(source)
        current = _to_ansible_config(source)
        if state == STATE_GATHERED:
            runtime = _call_api(connection, method="GET", path=STATE_PATH)
            result.update(
                gathered=current,
                read_only_config=_to_ansible_read_only(source),
                runtime_state=_to_ansible_runtime_state(runtime),
                radius={"config": current},
            )
            module.exit_json(**result)
            return

        result["before"] = current
        changed, predicted = _apply_action(connection, state, current, config, module.check_mode)
        result["changed"] = changed
        if changed and not module.check_mode:
            after = _fetch_configuration(connection)
        else:
            after = predicted
        values_unchanged = _values_included(current, after)
        result["after"] = after
        result["radius"] = {
            "before": current,
            "after": after,
            "differences": {} if values_unchanged else _compute_diff(current, after),
        }
        if module._diff:
            result["diff"] = {"before": current, "after": after}
        module.exit_json(**result)
    except FeRadiusError as exc:
        module.fail_json(
            changed=result.get("changed", False)
            or exc.changed
            or bool(getattr(connection, "_extreme_fe_radius_changed", False)),
            **exc.to_fail_kwargs(),
        )
    except ConnectionError as exc:
        module.fail_json(
            msg=to_text(exc),
            code=getattr(exc, "code", None),
            err=getattr(exc, "err", None),
            changed=result.get("changed", False) or bool(getattr(connection, "_extreme_fe_radius_changed", False)),
        )


if __name__ == "__main__":
    main()
