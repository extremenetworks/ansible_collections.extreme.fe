# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
"""
Ansible module to manage local user accounts on Extreme Fabric Engine devices.

REST API endpoints used:
  GET    /v0/configuration/accounts              - list all user accounts
  POST   /v0/configuration/accounts              - add a user account
  PATCH  /v0/configuration/accounts/{username}   - update a user account
  DELETE /v0/configuration/accounts/{username}   - remove a user account

Writable fields (POST body, schema UserAccount):
  username    - account name (string, identifier/required). The OpenAPI
                UsernameString schema states 1-32, but a real device
                rejects anything over 20, so USERNAME_MAX_LENGTH and the
                public DOCUMENTATION both say 1-20 - see the notes there.
  level       - privilege level (enum, see LEVEL_CHOICES)
  enabled     - whether the account is enabled (boolean)
  removable   - whether the account may be deleted (boolean, Fabric Engine only)
  secret      - account password object (value, isEncrypted)

Writable fields (PATCH body, schema UserAccountAttributes):
  level, enabled, secret, oldSecret, superUserName, superUserPassword

Note: 'removable' appears only in the POST body. The PATCH body cannot carry it,
so it can be set at creation but never changed on an existing account.
"""

from __future__ import annotations

DOCUMENTATION = r"""
module: extreme_fe_local_users
short_description: Manage local user accounts on Extreme Fabric Engine devices
version_added: "1.3.0"
description:
  - Add, update, remove, and query local user accounts on Extreme Fabric Engine
    devices via the REST API endpoints exposed through the OpenAPI Server.
  - Supports all five Ansible resource module states.
  - Each account is identified by its C(username) (1-20 characters).
author:
  - Andreea-Lavinia Vraja (@avraja_extr)
requirements:
  - ansible.netcommon
notes:
  - Tested against Fabric Engine Version 9.3.2.
  - A write (C(POST), C(PATCH), C(DELETE)) that fails without an answer (a lost connection) may have
    been applied, so the task reports C(changed=true). A C(DELETE) answered with 404 counts as done;
    the account was just read as present, and a DELETE resent after a lost answer finds it gone. An account
    C(POST) answered with 409 (a resend) is checked against a re-read; it counts as done when the account is
    there with the submitted level and the POST carried no password. Otherwise the outcome is unknown and
    the task fails with C(changed=true); the stored password is encrypted and cannot be compared, so
    another writer may have created the account with a different one. Running the task again with
    I(update_password=always) and I(old_secret), or I(super_user_name) and I(super_user_password),
    re-applies it.
  - Every error is scrubbed of the stored passwords the module read from the device as well, so an
    error that quotes another account's stored (encrypted) password does not return it.
  - This module supports check mode and diff mode.
  - The device stores passwords encrypted, so a cleartext password supplied in
    C(config) can never be compared against the stored value. Idempotency for
    the password is therefore controlled by I(update_password) rather than by
    comparison. This mirrors the convention used by the C(ios_user),
    C(eos_user), C(nxos_user) and C(vyos_user) modules.
  - The account password is never returned by this module. C(gathered),
    C(before) and C(after) omit C(secret) entirely (neither C(secret.value) nor
    C(secret.is_encrypted)), so they use the C(config) option shape and
    C(gathered) can be re-applied as C(config) without writing a password.
    Failure C(details) carry no C(secret.value) either. The same holds for C(old_secret) and C(super_user_password), the
    other two credentials a task can submit; neither is echoed back in any
    field of the result, structured or free text. The device echoes the
    encrypted password back on a GET (the OpenAPI spec notes this
    explicitly), and this redaction does not depend on the task having
    submitted a value to compare the response against - the module finds a
    credential structurally wherever a response carries one - C(secret.value),
    C(oldSecret.value), C(superUserPassword) - and scrubs that value from
    every string field of the same response, not only from the field it was
    found under, so a free-text message that quotes it is caught too. A
    response the device answers as plain text rather than JSON has no such
    structure to search, so it is redacted in full instead, since every
    operation this module performs is against the secrets-bearing accounts
    endpoint. The C(extreme_fe) HTTPAPI plugin applies the same protection
    one layer earlier, before a 207 or HTTP-error message ever reaches this
    module. It never logs the request or response bodies of this endpoint,
    and it keeps the device's error message for a C(POST) or C(PATCH) (for
    example C(Cannot update user password and user state at the same time.))
    with every submitted or returned credential masked. The error of a GET,
    of a C(DELETE) and a plain-text answer keep only the status code.
  - A device that reports no account collection at all - a 404, either at the
    transport level or embedded in an error document - is treated as an empty
    inventory rather than as a failure, so C(gathered), C(deleted) and
    C(overridden) still run against it.
  - C(level) and C(enabled) are required for every entry when I(state) is
    C(merged), C(replaced) or C(overridden). They are not required for
    C(deleted), which needs only C(username).
  - Because C(level) and C(enabled) are mandatory and C(secret) cannot be reset
    to a default, C(replaced) and C(merged) behave identically for an existing
    account. C(replaced) is retained for interface consistency with the other
    resource modules in this collection.
  - C(removable) is present only in the REST POST body, so it can be set when an
    account is created but never changed afterwards. Supplying a value that
    differs from the account's current value fails with an explicit error.
  - Accounts with C(removable=false) are part of the device default
    configuration and cannot be deleted. C(deleted) and C(overridden) skip them
    when clearing all accounts, and fail if such an account is named explicitly.
    Each skipped account (including the connecting account below) is reported
    in C(skipped_users) with the reason, and a warning is emitted for it.
  - The account used by the current Ansible connection is never deleted by a
    C(deleted) run with no C(config), nor by C(overridden). Naming it explicitly
    fails with an explicit error. If the connecting account name cannot be
    determined, both a C(deleted) run with no C(config) and C(overridden)
    fail rather than risk removing it.
  - C(username) is limited to 20 characters. The OpenAPI spec's
    C(UsernameString) schema states 1-32, but a real Fabric Engine device
    rejects anything over 20 with C(Username must be provided and length
    should be between 1 and 20 characters) - confirmed against a live
    device on 2026-09-22. The firmware limit is enforced here rather than
    the wider spec value.
  - Whenever a password is written to an existing account, the module
    always includes C(level) in the PATCH body alongside C(secret), even
    when C(level) is unchanged. A real device rejects a PATCH carrying
    C(secret) without C(level), regardless of C(old_secret) or the
    super-user fields also being present - confirmed against a live
    device on 2026-09-22, which demanded C(secret), C(level), C(value)
    and C(oldSecret) together, or C(secret), C(level), C(value),
    C(superUsername) and C(superUserpassword) together. This is handled
    automatically; no playbook change is needed. The device reads the
    super-user fields as C(superUserName) and C(superUserPassword), the
    names of the OpenAPI C(UserAccountAttributes) schema, which the module
    sends.
  - On the Fabric Engine 9.4 and 9.5 devices tested, a password change
    verified with C(super_user_name) and C(super_user_password) was refused
    with C(Invalid username or password.) even for valid administrator
    credentials. Use C(old_secret) to change a password.
  - A PATCH that changes both C(enabled) and the password is refused by the
    device (C(Cannot update user password and user state at the same
    time.)), so the module sends the two changes as two PATCH requests,
    disabling before and enabling after the password change. When the second
    request fails, the task fails with C(changed=true) and
    C(details.applied_earlier) naming what the first one applied.
  - Changing C(level) on an existing account was rejected by the device -
    alone, together with a password, and together with C(enabled), each
    with a different error (confirmed 2026-09-22) - and the User Guide
    states a custom account's access level "cannot be changed later" once
    created. Supplying a C(level) that differs from the account's current
    value fails with an explicit error before any write request is sent
    (only the account list is read, to compare with); delete
    the account and recreate it with the desired level instead.
  - When a password is written to an existing account, the module requires
    either C(old_secret) or both C(super_user_name) and
    C(super_user_password) to be supplied, matching the device's own
    verification requirement. Supplying neither fails with an explicit
    error before any write request is sent, rather than letting the device
    reject an incomplete PATCH.
  - A new account can be created only with C(level) C(ADMIN),
    C(ADMIN_LIMITED) or C(READ_ONLY). C(L3_LIMITED), C(L2_LIMITED) and
    C(L1_LIMITED) are the levels of the built-in C(l3), C(l2) and C(l1)
    accounts. They are accepted for an account that already has that level,
    so C(gathered) output can be re-applied, and creating an account with
    one fails before any write request is sent. The module reads the account
    list first, to tell a new account from an existing one.
  - A C(secret) or C(old_secret) without C(value) writes nothing and is
    ignored, with a warning when it carries C(is_encrypted). Gathered output
    of earlier releases, which carried C(secret.is_encrypted), can therefore
    be re-applied unchanged.
  - A new account is always created enabled. A real device silently
    ignores C(enabled=false) on the C(POST) that creates the account -
    confirmed 2026-09-22, and consistent with the User Guide's account
    creation CLI syntax, which has no disabled-creation form. The
    module issues a follow-up C(PATCH) automatically when C(enabled) is
    set to C(false) at creation, so that setting still takes effect; no
    playbook change is needed. If that follow-up C(PATCH) fails, the task
    fails with C(changed=true) and a message saying the account was created
    (and is still enabled unless the re-read shows otherwise).
  - When a C(PATCH) of an account fails, the module re-reads the account and
    reports in the failure C(details) which of the attempted fields the device
    applied (C(applied_fields), C(not_applied_fields), C(unchanged_fields)
    for a value the account already held, such as the C(level) sent with a
    password), or C(reread_error) when the re-read itself failed. C(secret) is
    listed in C(unknown_fields), since the stored password is encrypted and
    cannot be compared; no field value is ever reported. C(changed) is true
    when the re-read shows a field applied. A failed re-read is described
    generically, with its numeric error code; the device text is never copied,
    and neither is that of an error document answering any GET of the
    accounts, since it could quote a stored credential.
  - A task that fails after one of its requests already changed the device
    (an account created, updated or deleted earlier in the same task)
    reports C(changed=true), and the message and C(details.changed_users)
    name the accounts already changed. The failing account is named too when
    it was created before its follow-up PATCH failed, or when the re-read of a
    rejected PATCH shows a field applied.
options:
  state:
    description:
      - Desired account operation state.
      - C(merged) creates accounts that do not exist and updates supplied fields
        on existing accounts, without removing unlisted accounts.
      - C(replaced) makes the provided settings authoritative for each listed
        account.
      - C(overridden) enforces the exact set of accounts - unlisted removable
        accounts are deleted, listed accounts are created or updated.
      - C(deleted) removes the specified accounts. If C(config) is omitted or
        empty (C(config=[])), all removable accounts except the connecting
        account are deleted.
      - C(gathered) returns current account information without making changes.
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - List of local user accounts to manage.
      - Required when C(state) is C(merged), C(replaced), or C(overridden).
      - Optional for C(deleted) (omit it, or give an empty list, to delete all
        removable accounts) and C(gathered).
    type: list
    elements: dict
    suboptions:
      username:
        description:
          - Account name (1-20 characters). This is the resource identifier.
        type: str
        required: true
      level:
        description:
          - Privilege level of the account.
          - Fabric Engine equivalents are C(ADMIN) read-write-all,
            C(ADMIN_LIMITED) read-write, C(L3_LIMITED) layer3, C(L2_LIMITED)
            layer2, C(L1_LIMITED) layer1 and C(READ_ONLY) read-only.
          - A new account can be created only with C(ADMIN), C(ADMIN_LIMITED)
            or C(READ_ONLY). C(L3_LIMITED), C(L2_LIMITED) and C(L1_LIMITED)
            describe the built-in C(l3), C(l2) and C(l1) accounts.
          - Required when C(state) is C(merged), C(replaced) or C(overridden).
        type: str
        choices: [ADMIN, ADMIN_LIMITED, L3_LIMITED, L2_LIMITED, L1_LIMITED, READ_ONLY]
      enabled:
        description:
          - Whether the account is enabled.
          - Required when C(state) is C(merged), C(replaced) or C(overridden).
        type: bool
      removable:
        description:
          - Whether the account may be deleted.
          - Can only be set when the account is created. The REST PATCH body
            does not carry this field, so supplying a value that differs from
            an existing account's current value fails.
        type: bool
      secret:
        description:
          - Password for the account.
          - Without C(value) nothing is written and the entry is ignored.
        type: dict
        suboptions:
          value:
            description:
              - The password. On Fabric Engine the password must not contain,
                repeat, or reverse the associated username.
            type: str
          is_encrypted:
            description:
              - Whether I(secret.value) is already encrypted (C(true)) or is
                cleartext (C(false)).
            type: bool
      old_secret:
        description:
          - The previous password, required by the device when overwriting an
            existing cleartext password.
        type: dict
        suboptions:
          value:
            description:
              - The previous password.
            type: str
          is_encrypted:
            description:
              - Whether I(old_secret.value) is already encrypted (C(true)) or is
                cleartext (C(false)).
            type: bool
      super_user_name:
        description:
          - Super user name used to verify credentials when overwriting an
            existing password.
          - Sent as C(superUserName). Fabric Engine 9.4 and 9.5 were seen to
            refuse valid credentials; prefer C(old_secret).
        type: str
      super_user_password:
        description:
          - Super user password used to verify credentials when overwriting an
            existing password.
        type: str
  update_password:
    description:
      - Controls when the password is written to the device.
      - Since the device stores passwords encrypted, a supplied password can
        never be compared against the stored value.
      - C(always) writes the password on every run whenever C(secret.value) is
        supplied, which means the module reports C(changed) every run.
      - C(on_create) writes the password only when the account is created,
        which keeps the module idempotent.
    type: str
    choices: [on_create, always]
    default: always
  gather_filter:
    description:
      - Limit gathered account facts to these account names.
    type: list
    elements: str
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
# Task 1: Gather all local user accounts
# -------------------------------------------------------------------------
# - name: "Task 1: Gather local user accounts"
#   hosts: switches
#   gather_facts: false
#   collections:
#     - extreme.fe
#   tasks:
- name: Gather all local user accounts
  extreme.fe.extreme_fe_local_users:
    state: gathered

- name: Gather a single account
  extreme.fe.extreme_fe_local_users:
    state: gathered
    gather_filter:
      - operator

# -------------------------------------------------------------------------
# Task 2: Create accounts
# -------------------------------------------------------------------------
- name: Create a read-only account
  extreme.fe.extreme_fe_local_users:
    state: merged
    config:
      - username: operator
        level: READ_ONLY
        enabled: true
        secret:
          value: "{{ operator_password }}"
          is_encrypted: false

- name: Create an account that cannot be deleted later
  extreme.fe.extreme_fe_local_users:
    state: merged
    config:
      - username: backup_admin
        level: ADMIN
        enabled: true
        removable: false
        secret:
          value: "{{ backup_admin_password }}"
          is_encrypted: false

# -------------------------------------------------------------------------
# Task 3: Keep the run idempotent by writing the password only at creation
# -------------------------------------------------------------------------
- name: Ensure the account exists without rewriting its password every run
  extreme.fe.extreme_fe_local_users:
    state: merged
    update_password: on_create
    config:
      - username: operator
        level: READ_ONLY
        enabled: true
        secret:
          value: "{{ operator_password }}"
          is_encrypted: false

# -------------------------------------------------------------------------
# Task 4: Change a password, supplying the previous one
# -------------------------------------------------------------------------
- name: Rotate the operator password
  extreme.fe.extreme_fe_local_users:
    state: merged
    config:
      - username: operator
        level: READ_ONLY
        enabled: true
        secret:
          value: "{{ new_operator_password }}"
          is_encrypted: false
        old_secret:
          value: "{{ old_operator_password }}"
          is_encrypted: false

# -------------------------------------------------------------------------
# Task 5: Disable an account
# -------------------------------------------------------------------------
- name: Disable the operator account
  extreme.fe.extreme_fe_local_users:
    state: replaced
    config:
      - username: operator
        level: READ_ONLY
        enabled: false

# -------------------------------------------------------------------------
# Task 6: Enforce the exact set of accounts
# -------------------------------------------------------------------------
- name: Make these the only removable accounts on the device
  extreme.fe.extreme_fe_local_users:
    state: overridden
    config:
      - username: operator
        level: READ_ONLY
        enabled: true
      - username: netadmin
        level: ADMIN
        enabled: true

# -------------------------------------------------------------------------
# Task 7: Remove accounts
# -------------------------------------------------------------------------
- name: Remove a single account
  extreme.fe.extreme_fe_local_users:
    state: deleted
    config:
      - username: operator

- name: Remove every removable account except the connecting one
  extreme.fe.extreme_fe_local_users:
    state: deleted
"""

RETURN = r"""
before:
  description:
    - Full account configuration before changes.
    - Returned for action states (merged, replaced, overridden, deleted).
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
after:
  description:
    - Full account configuration after changes.
    - Returned for every action state, also when nothing changed (then equal to C(before)).
    - In check mode this is the predicted state that would have been written.
  returned: when state is merged, replaced, overridden, or deleted
  type: list
  elements: dict
gathered:
  description:
    - Account configuration gathered from the device.
    - Uses the C(config) option shape (C(username), C(level), C(enabled), C(removable)) and can be passed back as C(config).
    - Never contains C(secret), so re-applying it writes no password.
    - Returned only for C(state=gathered).
  returned: when state is gathered
  type: list
  elements: dict
local_users:
  description: Per-account operation results with differences.
  returned: when state is not gathered
  type: list
  elements: dict
  contains:
    username:
      description: Account name.
      type: str
    before:
      description: Account configuration before the operation.
      type: dict
    after:
      description: Account configuration after the operation.
      type: dict
    changed:
      description: Whether this account was modified.
      type: bool
    differences:
      description: Fields that changed with before/after values.
      type: dict
skipped_users:
  description:
    - Accounts a bulk delete left in place because they are protected, each with the reason.
    - An account is protected when it reports C(removable=false) or is the account the
      Ansible connection is authenticated with. A warning is emitted for each one.
    - Empty when no protected account had to be skipped.
  returned: when state is overridden, or deleted without config
  type: list
  elements: dict
  contains:
    username:
      description: Account name.
      type: str
    reason:
      description: Why the account was not deleted.
      type: str
changed:
  description: Whether any account was modified.
  returned: always
  type: bool
"""

# ── Imports ───────────────────────────────────────────────────────────────────
# Placed below the documentation blocks: validate-modules rejects imports above
# them with 'import-before-documentation'.

import json

# Type hints make the code self-documenting and help IDEs catch mistakes
from typing import Any

# quote() safely encodes the username in the REST URL path segment
from urllib.parse import quote

# AnsibleModule - the core class every Ansible module must instantiate;
# it handles argument parsing, check mode, exit/fail, etc.
from ansible.module_utils.basic import AnsibleModule

# to_text - safely converts bytes/strings to unicode text
from ansible.module_utils.common.text.converters import to_text

# Connection - talks to the device through the httpapi plugin;
# ConnectionError - raised when the device is unreachable or returns a transport error
from ansible.module_utils.connection import Connection, ConnectionError

from ansible_collections.extreme.fe.plugins.module_utils.extreme_fe_transport import answer_unknown

# ── Constants ─────────────────────────────────────────────────────────────────

# REST endpoint for the account collection (GET all, POST one)
ACCOUNTS_LIST_PATH = "/v0/configuration/accounts"

# REST endpoint template for a single account (PATCH, DELETE)
ACCOUNTS_SINGLE_PATH = "/v0/configuration/accounts/{username}"

# Privilege levels, from the OpenAPI AccountType schema. All six can be
# reported by a GET, and all six are accepted for an existing account so that
# gathered output round-trips, but only CREATE_LEVELS can create one.
LEVEL_CHOICES = [
    "ADMIN",  # Fabric Engine: read-write-all
    "ADMIN_LIMITED",  # Fabric Engine: read-write
    "L3_LIMITED",  # Fabric Engine: layer3
    "L2_LIMITED",  # Fabric Engine: layer2
    "L1_LIMITED",  # Fabric Engine: layer1
    "READ_ONLY",  # Fabric Engine: read-only
]

# Levels a new account can be created with. L3_LIMITED / L2_LIMITED /
# L1_LIMITED describe only the built-in l3 / l2 / l1 accounts: a POST with
# one answers 422 "Invalid user type. Supported values are ADMIN,
# ADMIN_LIMITED, READ_ONLY." (9.4 and 9.5), and the CLI's
# "username add <name> level" offers only ro, rw and rwa.
CREATE_LEVELS = ("ADMIN", "ADMIN_LIMITED", "READ_ONLY")

# Ansible parameter -> REST API field name mapping for the scalar fields
FIELD_MAP = {
    "username": "username",  # Account name (identifier, see USERNAME_MAX_LENGTH)
    "level": "level",  # Privilege level (see LEVEL_CHOICES)
    "enabled": "enabled",  # Account enabled/disabled
    "removable": "removable",  # May be deleted (Fabric Engine only, POST only)
}

# Ansible parameter -> REST API field name mapping for the nested secret objects
SECRET_FIELD_MAP = {
    "value": "value",  # The password itself
    "is_encrypted": "isEncrypted",  # Whether 'value' is already encrypted
}

# Fields the REST PATCH body (UserAccountAttributes) accepts. 'removable' is
# deliberately absent: it exists only in the POST body (UserAccount).
PATCHABLE_FIELDS = ("level", "enabled")

# Username length limits. The OpenAPI UsernameString schema states 1-32,
# but a real Fabric Engine device rejects anything over 20 characters
# ("Username must be provided and length should be between 1 and 20
# characters") - confirmed against a live device on 2026-09-22. The
# firmware limit is used here per the module skill's rule to prefer the
# confirmed device behaviour over the spec when the two disagree.
USERNAME_MIN_LENGTH = 1
USERNAME_MAX_LENGTH = 20

# Password length limit, from the OpenAPI AaaSecret schema
SECRET_MAX_LENGTH = 512

# Wire-level keys whose value is a credential, in either direction. Two
# shapes exist and both have to be covered by the redaction helpers:
# 'secret'/'oldSecret' are AaaSecret objects carrying the password under
# 'value', while 'superUserPassword' is a bare string on the request body
# itself (see _build_update_payload()). Anything added to the payload
# builders that carries a password belongs in one of these two tuples, and
# in the same tuples of the extreme_fe HTTPAPI plugin.
SECRET_OBJECT_KEYS = ("secret", "oldSecret")
SECRET_SCALAR_KEYS = ("superUserPassword",)

# Sentinel _call_api() returns for a CONFIRMED transport-level 404, so callers
# can tell it apart from the plain None a 200/204 answers with when the
# device simply sends no body - the latter is not "not found" and must not
# be read as an empty collection by destructive states - see
# _fetch_all_accounts().
_NOT_FOUND = object()

# Fields that must be supplied for every entry of a writing state. The OpenAPI
# spec defines no factory default for either, so they cannot be defaulted.
REQUIRED_WRITE_FIELDS = ("level", "enabled")

# State constants
STATE_MERGED = "merged"
STATE_REPLACED = "replaced"
STATE_OVERRIDDEN = "overridden"
STATE_DELETED = "deleted"
STATE_GATHERED = "gathered"

# States that write account attributes and therefore require a full entry
WRITING_STATES = (STATE_MERGED, STATE_REPLACED, STATE_OVERRIDDEN)

# update_password choices
UPDATE_PASSWORD_ON_CREATE = "on_create"
UPDATE_PASSWORD_ALWAYS = "always"

# ── Argument spec ─────────────────────────────────────────────────────────────

# Shared shape of the 'secret' and 'old_secret' objects. no_log sits on the leaf
# that holds the password; the container is marked no_log=False so the sanity
# check knows it was reviewed and so is_encrypted stays visible in output.
_SECRET_SPEC: dict[str, Any] = {
    "type": "dict",
    "no_log": False,
    "options": {
        "value": {"type": "str", "no_log": True},
        "is_encrypted": {"type": "bool"},
    },
}

ARGUMENT_SPEC: dict[str, Any] = {
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            # Resource identifier - always required, for every state
            "username": {"type": "str", "required": True},
            # Required for merged/replaced/overridden, enforced in _validate_config()
            # rather than here so that 'deleted' needs only the username.
            "level": {"type": "str", "choices": LEVEL_CHOICES},
            "enabled": {"type": "bool"},
            # Settable at creation only - the PATCH body cannot carry it
            "removable": {"type": "bool"},
            "secret": dict(_SECRET_SPEC),
            "old_secret": dict(_SECRET_SPEC),
            "super_user_name": {"type": "str"},
            "super_user_password": {"type": "str", "no_log": True},
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
    # Name contains 'password' but holds no secret, so no_log=False declares it reviewed.
    "update_password": {
        "type": "str",
        "choices": [UPDATE_PASSWORD_ON_CREATE, UPDATE_PASSWORD_ALWAYS],
        "default": UPDATE_PASSWORD_ALWAYS,
        "no_log": False,
    },
    "gather_filter": {"type": "list", "elements": "str"},
}

# ── Custom exception ─────────────────────────────────────────────────────────


class FeLocalUsersError(Exception):
    """Custom exception for local user account module errors."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, object] | None = None,
        extra: dict[str, object] | None = None,
        changed: bool = False,
    ) -> None:
        super().__init__(message)
        self.details = details or {}
        # Top-level fail_json keys (code, err) of a transport failure.
        self.extra = extra or {}
        self.changed = changed

    def to_fail_kwargs(self) -> dict[str, object]:
        data: dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        data.update(self.extra)
        if self.changed:
            data["changed"] = True
        return data


class _TrackedConnection:
    """Connection wrapper that remembers whether the task already wrote to the device.

    _call_api() calls record_write() for a POST, PATCH or DELETE the device
    accepted (no transport error, no embedded error document). Once one has,
    a later failure (another account, a follow-up PATCH, the 'after' re-read)
    must not report changed=false - see main().
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.wrote = False
        # Credential values the device returned on a GET (the stored, encrypted
        # passwords of every account). A later error can quote one that its own
        # request and response do not carry, so every error is scrubbed of
        # these too. Set here: __getattr__ would turn an unknown name into an
        # RPC call on the persistent connection.
        self.stored_secrets: list[str] = []

    def send_request(self, payload: Any, path: str | None = None, method: str | None = None) -> Any:
        return self._connection.send_request(payload, path=path, method=method)

    def record_write(self) -> None:
        self.wrote = True

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


# ── Helper functions ──────────────────────────────────────────────────────────


def _error_code(payload: dict[str, Any]) -> int | str | None:
    """
    Return the application-error code from a Fabric Engine error document, if
    present.

    The OpenAPI ErrorList/ErrorMessageElement schema uses 'errorCode', but
    other Fabric Engine endpoints in this collection have been confirmed to
    use 'statusCode' or plain 'code' for the same purpose - the same three
    keys the collection's other modules (extreme_fe_ntp_global,
    extreme_fe_lldp_global, ...) check. 'status'/'httpStatusCode', which this
    function used to check instead, are not part of that schema and were
    never actually observed in a device response.
    """
    code = payload.get("errorCode") or payload.get("statusCode") or payload.get("code")
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    return code


def _is_not_found_response(payload: Any) -> bool:
    """
    Check if a REST response indicates a 'not found' condition.

    Only for a structured error document embedded in a 200/207 answer - a
    confirmed transport-level 404 is signalled separately, via _NOT_FOUND
    (see _call_api()). A bare None is not treated as 'not found' here: it is
    also what a 200/204 with no body parses to, which is not the same thing
    and must not be read as an empty collection by a caller that then acts
    on it destructively - see _fetch_all_accounts().
    """
    if not isinstance(payload, dict):
        return False

    # The ErrorList schema nests each error's own errorCode/errorMessage
    # inside 'errors' rather than at the top level. When that breakdown is
    # present it is checked FIRST and decides the answer on its own: a
    # top-level errorCode/message can summarize a batch that actually
    # contains a mix of results (a top-level 404 wrapping a nested 500,
    # say), so a top-level 404 must never short-circuit past nested
    # entries that disagree. Every nested entry must say 'not found' -
    # structurally or in its own message - not just some of them; a
    # non-dict entry (a bare string, say) can't be checked structurally
    # and counts as disagreeing rather than being skipped.
    errors = payload.get("errors") or payload.get("error")
    if errors:
        entries = errors if isinstance(errors, list) else [errors]

        def _entry_not_found(entry: Any) -> bool:
            if not isinstance(entry, dict):
                return False
            if _error_code(entry) == 404:
                return True
            entry_message = entry.get("errorMessage") or entry.get("message")
            if isinstance(entry_message, str):
                lowered_entry = entry_message.lower()
                return "not found" in lowered_entry or "does not exist" in lowered_entry
            return False

        return all(_entry_not_found(entry) for entry in entries)

    if _error_code(payload) == 404:
        return True
    message = payload.get("errorMessage") or payload.get("message")
    if isinstance(message, str):
        lowered = message.lower()
        if "not found" in lowered or "does not exist" in lowered:
            return True
    return False


def _extract_error(payload: Any) -> str | None:
    """Extract an error message from a REST response, if present."""
    if not isinstance(payload, dict):
        return None
    code = _error_code(payload)
    message = payload.get("errorMessage") or payload.get("message") or payload.get("msg")
    if isinstance(code, int) and code >= 400:
        return f"HTTP {code}: {message or payload}"
    # A 2xx-wrapped ErrorList carries no top-level code at all - each error's
    # own errorCode/errorMessage is nested inside 'errors' (or, on some
    # endpoints, the singular 'error') instead.
    errors = payload.get("errors") or payload.get("error")
    if errors:
        return str(errors)
    return None


def _redact_secrets(payload: Any, sent: Any = None) -> Any:
    """
    Return a deep copy of *payload* with every credential value - the
    SECRET_OBJECT_KEYS' nested 'value' and the SECRET_SCALAR_KEYS themselves
    - replaced by a placeholder.

    The device echoes the (encrypted) password back on a GET - the OpenAPI
    spec for AaaSecret notes its 512-character maxLength "accommodates the
    longest possible encrypted password expected to be retrieved in a GET
    operation for Fabric Engine (VOSS)". _to_ansible_output() already drops
    the password from the module's own 'local_users'/'gathered' output, but
    error 'details' echo the raw device response, which
    would otherwise leak that value regardless. isEncrypted is left visible;
    only the 'value' string is masked. superUserPassword is masked the same
    way: the playbook submits it to authorise another account's password
    change, so an error document that quotes the request back would
    otherwise return it verbatim.

    Works on any raw REST shape: a single UserAccount dict, a list of them,
    or an error payload that happens to embed one - so it is safe to call on
    anything handed to _call_api() before it is stored or reported.

    Structure alone is not enough, though: the device may answer with plain
    text rather than JSON, and a free-text error can quote a password back -
    either the one just submitted ("password <value> does not meet
    complexity rules") or, on a 2xx-wrapped embedded error, the device's own
    encrypted one already sitting in this same response's secret.value
    ("value <value> is invalid"). A string NESTED inside a dict or list is
    scrubbed of both: the credential values found structurally in *payload*
    itself, collected before anything is masked, and (via *sent*) the ones
    just submitted in the request body.

    A BARE top-level string - the whole response, not a value inside one -
    gets no such structural help: there is nothing in *payload* to extract a
    value from, so only a value that also appears verbatim in *sent* would
    ever be caught, and the device's own echoed secret would not be. This
    module only ever talks to the accounts/secrets endpoint, so unlike a
    shared multi-endpoint transport there is no non-secret path to weigh
    that against - a bare string response is redacted outright instead.
    """
    if isinstance(payload, str) and payload:
        return "**REDACTED**"
    secret_values = _extract_secret_values(payload)
    if sent is not None:
        secret_values = secret_values + _extract_secret_values(sent)
    return _redact_secrets_with(payload, secret_values)


def _redact_secrets_with(payload: Any, secret_values: list[str]) -> Any:
    """Recursive worker for _redact_secrets(): masks known keys and, using
    *secret_values*, scrubs any string field that quotes one of them."""
    if isinstance(payload, dict):
        redacted = {key: _redact_secrets_with(value, secret_values) for key, value in payload.items()}
        for secret_key in SECRET_OBJECT_KEYS:
            secret = redacted.get(secret_key)
            if isinstance(secret, dict) and "value" in secret:
                secret["value"] = "**REDACTED**"
        for scalar_key in SECRET_SCALAR_KEYS:
            if isinstance(redacted.get(scalar_key), str):
                redacted[scalar_key] = "**REDACTED**"
        return redacted
    if isinstance(payload, list):
        return [_redact_secrets_with(item, secret_values) for item in payload]
    if isinstance(payload, str):
        for value in secret_values:
            payload = payload.replace(value, "**REDACTED**")
        return payload
    return payload


def _extract_secret_values(payload: Any) -> list[str]:
    """
    Collect every credential string within *payload* - the SECRET_OBJECT_KEYS'
    nested 'value' and the SECRET_SCALAR_KEYS' own value.

    Structured payloads carry the secret at a known key, but free text does
    not. A ConnectionError's message is free text, and the HTTPAPI plugin
    builds it from the parsed error body - including, on some failures, the
    body stringified verbatim - so it can echo a submitted secret just as
    easily as anything else can; so can a plain-text response the device
    returns instead of JSON. These are the actual values to scrub out of
    such text, via _redact_secret_text().
    """
    values: list[str] = []
    if isinstance(payload, dict):
        for secret_key in SECRET_OBJECT_KEYS:
            secret = payload.get(secret_key)
            if isinstance(secret, dict):
                value = secret.get("value")
                if isinstance(value, str) and value:
                    values.append(value)
        for scalar_key in SECRET_SCALAR_KEYS:
            value = payload.get(scalar_key)
            if isinstance(value, str) and value:
                values.append(value)
        for value in payload.values():
            values.extend(_extract_secret_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_extract_secret_values(item))
    return values


def _redact_secret_text(text: str, payload: Any) -> str:
    """Replace any verbatim secret value from *payload* inside free-text *text*."""
    for value in _extract_secret_values(payload):
        text = text.replace(value, "**REDACTED**")
    return text


def _get_connection(module: AnsibleModule) -> Connection:
    """Return the HTTPAPI connection, failing clearly if it is unavailable."""
    if not module._socket_path:
        module.fail_json(msg="Connection type httpapi is required for this module")
    return _TrackedConnection(Connection(module._socket_path))  # type: ignore[return-value]


def _scrub_source(connection: Connection, payload: Any) -> Any:
    """Return what an error is scrubbed against: the request body and the stored secrets read so far."""
    stored = connection.stored_secrets if isinstance(connection, _TrackedConnection) else []
    return [payload, [{"secret": {"value": value}} for value in stored]]


def _call_api(
    module: AnsibleModule,
    connection: Connection,
    *,
    method: str,
    path: str,
    payload: Any = None,
    allow_not_found: bool = False,
) -> Any:
    """
    Send a REST API request and return the parsed response.

    Parameters:
        module:         AnsibleModule instance (unused; kept for the callers' signature)
        connection:     HTTPAPI Connection object
        method:         HTTP method (GET, POST, PATCH, DELETE)
        path:           REST API path
        payload:        Request body (dict for JSON, None for no body)
        allow_not_found: Treat a 'not found' answer as a valid result rather
                        than an error. A device that has no collection at
                        this path answers either with a transport 404 or
                        with a 200/207 error document whose code is 404,
                        and both have to be let through BEFORE the generic
                        error handling below turns them into a
                        FeLocalUsersError - see _fetch_all_accounts().
    Returns:
        Parsed response payload, or None when the device returns no content.
        Under allow_not_found, a confirmed transport 404 instead returns the
        _NOT_FOUND sentinel - never None - so it cannot be confused with an
        ordinary empty body that means nothing about the resource existing.
    """
    try:
        raw = connection.send_request(payload, path=path, method=method)
    except ConnectionError as exc:
        if allow_not_found and getattr(exc, "code", None) == 404:
            # The resource is absent, which is what the caller asked to be
            # told about rather than failed on.
            return _NOT_FOUND
        err_val = getattr(exc, "err", None)
        source = _scrub_source(connection, payload)
        msg = f"REST API call failed: {method} {path}: {to_text(exc)}"
        if method != "GET" and answer_unknown(exc):
            # No answer (a lost connection; no code, or a negative JSON-RPC code
            # of the persistent connection): the device may have applied the
            # write, so the task reports changed, as for a write that succeeded.
            if isinstance(connection, _TrackedConnection):
                connection.record_write()
            msg += " The device may have applied it before the answer was lost; check the account on the device."
        # Raised rather than failed here, so a caller that already wrote can
        # attribute the failure; main() fails with the same msg, code and err.
        raise FeLocalUsersError(
            _redact_secret_text(msg, source),
            extra={
                "code": getattr(exc, "code", None),
                "err": _redact_secret_text(to_text(err_val), source) if err_val else err_val,
            },
        )

    # send_request returns already-parsed JSON, which may be a dict, list,
    # str or None. POST/PATCH/DELETE here answer 204 with no body.
    parsed = None
    if raw is not None:
        if isinstance(raw, (dict, list)):
            parsed = raw
        elif isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                parsed = raw

    # Redact before this leaves _call_api(): 'details' below ends up in
    # fail_json() output and should never carry a password value, even
    # the device's own encrypted one - see _redact_secrets(). 'payload' is
    # passed so a plain-text or free-text response that quotes the password
    # just submitted is scrubbed as well, not only the structured
    # secret.value the device returns.
    redacted = _redact_secrets(parsed, _scrub_source(connection, payload))
    if method == "GET" and isinstance(connection, _TrackedConnection):
        connection.stored_secrets.extend(_extract_secret_values(parsed))

    if parsed is not None:
        # Ahead of _extract_error(), which turns every error document into a
        # FeLocalUsersError - including the embedded 404s the caller asked to
        # handle itself. Checking afterwards would be dead code.
        if allow_not_found and _is_not_found_response(parsed):
            return parsed
        # _extract_error() only inspects a dict - it returns None for a
        # plain string, which would otherwise fall through to 'return
        # parsed' below and be reported as a SUCCESSFUL request. Every
        # documented operation on this endpoint answers with JSON (a dict
        # or list) or 204 No Content; a non-empty string that reached here
        # unrecognised as 'not found' is always the device's own free-text
        # error (or a malformed body), never a legitimate success, so it is
        # rejected outright rather than trusted.
        if isinstance(parsed, str):
            raise FeLocalUsersError(
                f"{method} {path} returned an unexpected non-JSON response",
                details={"response": redacted},
            )
        # Extracted from the redacted copy, not 'parsed': _extract_error()'s
        # own fallbacks stringify whatever they are given when no recognised
        # message key is present, and that string becomes this exception's
        # message - it must never be the one place a secret slips through
        # unredacted.
        err = _extract_error(redacted)
        if err:
            if method == "GET":
                # A GET submits no password, so a stored one the device quotes in
                # the error text cannot be found and scrubbed: only the numeric
                # code is kept, as the HTTPAPI plugin does for this path's HTTP
                # errors (an error document in a 2xx answer bypasses it).
                code = _error_code(redacted) if isinstance(redacted, dict) else None
                code = code if isinstance(code, int) and not isinstance(code, bool) else None
                raise FeLocalUsersError(
                    "%s %s returned an error document%s; its message is not shown, as it may quote a stored "
                    "credential" % (method, path, " (error code %d)" % code if code is not None else ""),
                    details={"code": code} if code is not None else {},
                    extra={"code": code},
                )
            raise FeLocalUsersError(
                f"{method} {path} returned an error: {err}",
                details={"response": redacted},
            )

    if method != "GET" and isinstance(connection, _TrackedConnection):
        connection.record_write()
    return parsed


def _connected_username(connection: Connection) -> str | None:
    """
    Return the account name the current connection authenticated with.

    Used to make sure a delete-all run never removes the account Ansible is
    logged in as. The value comes from the connection plugin's 'remote_user'
    option over the persistent-connection RPC; a setup where that call is not
    answered yields None, and the caller decides what to do about it.
    """
    try:
        value = connection.get_option("remote_user")
    except Exception:  # pragma: no cover - depends on the connection plugin
        return None
    if isinstance(value, str) and value:
        return value
    return None


# ── Data fetching ─────────────────────────────────────────────────────────────


def _fetch_all_accounts(
    module: AnsibleModule,
    connection: Connection,
) -> list[dict[str, Any]]:
    """GET the full account list from the device."""
    payload = _call_api(
        module,
        connection,
        method="GET",
        path=ACCOUNTS_LIST_PATH,
        # A device with no account collection at all reports it as a 404,
        # either at the transport level or embedded in an error document.
        # That is an empty inventory, not a failure - without this, gathered,
        # deleted and overridden would all fail on such a device.
        allow_not_found=True,
    )
    # payload is _NOT_FOUND only for a CONFIRMED 404 (transport-level or an
    # embedded error document - see _is_not_found_response()). A bare None -
    # a 200/204 with no body - is not that, and must fall through to the
    # 'unexpected response' raise below rather than being read as an empty
    # inventory: see _NOT_FOUND's definition.
    if payload is _NOT_FOUND or _is_not_found_response(payload):
        return []
    if isinstance(payload, list):
        # A dict alone does not make an item an account: main() keys
        # current_map by 'username' and silently skips any entry without one
        # (isinstance(username, str) and username), so a dict missing it -
        # an error/metadata object mixed into an otherwise-valid list - would
        # otherwise vanish from current_map the same way a filtered-out
        # non-dict item would, making the remaining accounts look like the
        # complete inventory to deleted/overridden. Require a non-empty
        # 'username' on every item, not just dict-ness, before trusting the
        # list as-is.
        if all(
            isinstance(item, dict) and isinstance(item.get("username"), str) and item["username"] for item in payload
        ):
            return payload
        # A list with even one non-account entry is malformed, not partially
        # usable: silently dropping that entry (as filtering it out would)
        # would make the remaining accounts look like the complete
        # inventory, and deleted/overridden could then treat whatever this
        # response omitted as unlisted and delete it. Fail closed instead,
        # same as the 'not a list at all' case below.
        raise FeLocalUsersError(
            "Unexpected response when listing accounts from {0}: list "
            "contains a non-account entry".format(ACCOUNTS_LIST_PATH),
            details={"response": _redact_secrets(payload)},
        )
    # A response that is neither a list nor recognized as 'not found' is
    # unexpected (a malformed body, an empty 200/204, or an error document
    # _extract_error() did not recognize as an error). This list feeds
    # deleted and overridden, so silently treating it as an empty inventory
    # risks those states acting as if every account is unlisted. Raise
    # instead, with a redacted copy of the response so the failure is
    # diagnosable without ever surfacing a password.
    raise FeLocalUsersError(
        "Unexpected response when listing accounts from {0}: expected a "
        "list, got {1}".format(ACCOUNTS_LIST_PATH, type(payload).__name__),
        details={"response": _redact_secrets(payload)},
    )


# ── Output formatter ──────────────────────────────────────────────────────────


def _to_ansible_output(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Translate one REST account object into Ansible parameter names.

    The whole 'secret' object is deliberately dropped. The password never
    reaches the playbook output or the logs - every peer vendor module does
    the same: ios_user and eos_user hardcode configured_password to None,
    nxos_user substitutes a placeholder. 'secret.is_encrypted' is dropped too:
    a 'secret' without 'value' fails _validate_config(), so leaving it out
    keeps gathered/before/after in the config option shape and re-applying
    gathered output a no-op that sends no password.
    """
    return {ansible_key: raw[rest_key] for ansible_key, rest_key in FIELD_MAP.items() if rest_key in raw}


def _filter_output(accounts: list[dict[str, Any]], gather_filter: list[str] | None) -> list[dict[str, Any]]:
    """Limit gathered accounts to the requested usernames."""
    if not gather_filter:
        return accounts
    wanted = {name for name in gather_filter if name}
    return [acc for acc in accounts if acc.get("username") in wanted]


# ── Validation ────────────────────────────────────────────────────────────────


def _validate_config(module: AnsibleModule, state: str, config: list[dict[str, Any]]) -> None:
    """
    Check every config entry before any request is sent.

    'level' and 'enabled' are required by the writing states rather than by the
    argument spec, so that a 'deleted' entry needs only the username.
    """
    seen: set[str] = set()
    for entry in config:
        username = entry.get("username")
        if not isinstance(username, str) or not (USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH):
            module.fail_json(
                msg="username must be {0}-{1} characters, got '{2}' ({3} chars)".format(
                    USERNAME_MIN_LENGTH,
                    USERNAME_MAX_LENGTH,
                    username,
                    len(username) if isinstance(username, str) else 0,
                )
            )

        if username in seen:
            module.fail_json(msg=f"Account '{username}' is listed more than once in 'config'; list each account once")
        seen.add(username)

        if state in WRITING_STATES:
            for field in REQUIRED_WRITE_FIELDS:
                if entry.get(field) is None:
                    module.fail_json(
                        msg="'{0}' is required for state {1} (account '{2}')".format(field, state, username)
                    )

        for key in ("secret", "old_secret"):
            secret = entry.get(key)
            if isinstance(secret, dict):
                value = secret.get("value")
                # 'value' is the only field the device actually needs from
                # this object - is_encrypted alone is metadata, not a
                # password. Such an object (the {is_encrypted: true} an
                # earlier release returned in gathered) writes nothing, so it
                # is dropped with a warning instead of failing the task: the
                # gathered output round-trips.
                if value is None:
                    if any(v is not None for v in secret.values()):
                        module.warn(
                            "{0} of account '{1}' has no value and is ignored; no password is "
                            "written".format(key, username)
                        )
                    entry[key] = None
                    continue
                if isinstance(value, str) and len(value) > SECRET_MAX_LENGTH:
                    module.fail_json(
                        msg="{0}.value must be at most {1} characters for account "
                        "'{2}'".format(key, SECRET_MAX_LENGTH, username)
                    )


# ── Payload builders ──────────────────────────────────────────────────────────


def _build_secret_payload(secret: dict[str, Any] | None) -> dict[str, Any] | None:
    """Translate an Ansible secret object into its REST form."""
    if not isinstance(secret, dict):
        return None
    out: dict[str, Any] = {}
    for ansible_key, rest_key in SECRET_FIELD_MAP.items():
        if secret.get(ansible_key) is not None:
            out[rest_key] = secret[ansible_key]
    return out or None


def _build_create_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Build the POST body (schema UserAccount) that creates an account.

    This is the only request that can carry 'removable'.
    """
    payload: dict[str, Any] = {}
    for ansible_key, rest_key in FIELD_MAP.items():
        if entry.get(ansible_key) is not None:
            payload[rest_key] = entry[ansible_key]

    secret = _build_secret_payload(entry.get("secret"))
    if secret:
        payload["secret"] = secret

    return payload


def _build_update_payload(
    entry: dict[str, Any],
    current: dict[str, Any],
    *,
    write_password: bool,
) -> dict[str, Any]:
    """
    Build the PATCH body (schema UserAccountAttributes) for an existing account.

    Only fields that actually differ are included, so an unchanged account
    produces an empty payload and no request. The password is the exception:
    it cannot be compared against the encrypted stored value, so it is included
    whenever *write_password* says so.

    A real device rejects a PATCH carrying 'secret' unless 'level' is also
    present, even when level is unchanged - confirmed 2026-09-22:
    "The following attributes are required: (secret, level, value,
    oldSecret) or (secret, level, value, superUsername, superUserpassword)".
    That message misspells the keys: the device, like the OpenAPI
    UserAccountAttributes schema, reads superUserName and superUserPassword;
    with the spelling of the message it ignores both.
    'level' is always present on 'entry' here (required by _validate_config()
    for every writing-state entry), so it is added unconditionally whenever a
    password is written, overriding the diff-only PATCHABLE_FIELDS entry for
    'level' with the same value when it was already added there.
    """
    payload: dict[str, Any] = {}

    for field in PATCHABLE_FIELDS:
        desired = entry.get(field)
        if desired is not None and desired != current.get(field):
            payload[FIELD_MAP[field]] = desired

    if write_password:
        secret = _build_secret_payload(entry.get("secret"))
        if secret:
            payload["secret"] = secret
            payload["level"] = entry["level"]
            old_secret = _build_secret_payload(entry.get("old_secret"))
            if old_secret:
                payload["oldSecret"] = old_secret
            if entry.get("super_user_name") is not None:
                payload["superUserName"] = entry["super_user_name"]
            if entry.get("super_user_password") is not None:
                payload["superUserPassword"] = entry["super_user_password"]

    return payload


# ── Diff logic ────────────────────────────────────────────────────────────────


def _compute_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the fields that differ between two account states."""
    differences: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old != new:
            differences[key] = {"before": old, "after": new}
    return differences


def _predict_after(current: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Project a PATCH payload onto the current state, for check mode and diff."""
    predicted = dict(current)
    for field in PATCHABLE_FIELDS:
        rest_key = FIELD_MAP[field]
        if rest_key in payload:
            predicted[field] = payload[rest_key]
    return predicted


# ── Guard helpers ─────────────────────────────────────────────────────────────


def _is_removable(account: dict[str, Any]) -> bool:
    """
    Whether an account may be deleted.

    Accounts belonging to the device default configuration report
    removable=false. A device that omits the field is treated as removable,
    matching the REST default of an absent boolean.
    """
    return account.get("removable") is not False


def _protected_reason(username: str, account: dict[str, Any], connected_user: str | None) -> str | None:
    """Return why an account must be kept by a bulk delete, or None when it may go."""
    if not _is_removable(account):
        return "part of the device default configuration (removable=false)"
    if username == connected_user:
        return "the account the Ansible connection is authenticated with"
    return None


def _delete_unprotected(
    module: AnsibleModule,
    connection: Connection,
    usernames: list[str],
    current_map: dict[str, dict[str, Any]],
    connected_user: str | None,
    result: dict[str, Any],
) -> None:
    """
    Delete the named accounts in bulk, keeping (and reporting) protected ones.

    Shared by the delete-all path of 'deleted' and the pre-pass of
    'overridden'. A protected account is never deleted; instead it is listed
    in result['skipped_users'] with the reason and a warning is emitted, so a
    run that leaves accounts in place says so rather than doing it silently.
    """
    skipped = result.setdefault("skipped_users", [])
    for username in sorted(usernames):
        current = current_map[username]
        reason = _protected_reason(username, current, connected_user)
        if reason is not None:
            skipped.append({"username": username, "reason": reason})
            module.warn("Account '{0}' was not deleted: it is {1}.".format(username, reason))
            continue
        _delete_account(module, connection, username, current, result)


def _assert_deletable(
    module: AnsibleModule,
    username: str,
    account: dict[str, Any],
    connected_user: str | None,
    result: dict[str, Any],
) -> None:
    """Fail when an explicitly named account must not be deleted."""
    if not _is_removable(account):
        module.fail_json(
            msg=f"Cannot delete account '{username}': it is part of the device "
            "default configuration and reports removable=false."
        )
    # Fail closed, the same as the delete-all and overridden guards: without
    # connected_user, 'username == connected_user' below is always False, so
    # an explicitly named account that happens to be the one this connection
    # authenticated with would be deleted anyway - exactly the account this
    # check exists to protect.
    if connected_user is None:
        module.fail_json(
            msg=f"Refusing to delete account '{username}': the account this "
            "connection authenticated with could not be determined, so it "
            "cannot be confirmed that this is not that account. Use a "
            "connection the module can identify before retrying.",
        )
    if username == connected_user:
        module.fail_json(
            msg=f"Cannot delete account '{username}': it is the account this "
            "Ansible connection is authenticated with. Deleting it would lock "
            "the connection out of the device."
        )


# ── State handlers ────────────────────────────────────────────────────────────


def _handle_gathered(
    module: AnsibleModule,
    connection: Connection,
    gather_filter: list[str] | None,
    result: dict[str, Any],
) -> None:
    """Read-only state: GET the accounts and return them, making no changes."""
    raw_list = _fetch_all_accounts(module, connection)
    accounts = [_to_ansible_output(raw) for raw in raw_list]
    result["gathered"] = _filter_output(sorted(accounts, key=lambda acc: acc.get("username") or ""), gather_filter)


def _delete_account(
    module: AnsibleModule,
    connection: Connection,
    username: str,
    current: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """DELETE one account and record the per-account entry.

    A 404 means the account is gone: it was just read as present, and HTTPAPI
    resends a DELETE after some transport failures, so a first attempt that
    deleted it and lost its answer makes the resend answer 404.
    """
    if not module.check_mode:
        _call_api(
            module,
            connection,
            method="DELETE",
            path=ACCOUNTS_SINGLE_PATH.format(username=quote(username, safe="")),
            allow_not_found=True,
        )
        # Also when the DELETE answered 404 (allow_not_found returns before
        # _call_api() records it): the account is gone, so a later failure of
        # the task still reports the change. record_write() is idempotent.
        if isinstance(connection, _TrackedConnection):
            connection.record_write()

    result["changed"] = True
    result["local_users"].append(
        {
            "username": username,
            "before": current,
            "after": {},
            "changed": True,
            "differences": _compute_diff(current, {}),
        }
    )


def _handle_deleted(
    module: AnsibleModule,
    connection: Connection,
    config: list[dict[str, Any]] | None,
    current_map: dict[str, dict[str, Any]],
    connected_user: str | None,
    result: dict[str, Any],
) -> None:
    """
    Remove accounts.

    With config, the listed accounts are removed and a protected account named
    explicitly is an error. Without config - omitted, or an empty list
    (config: []), as in Ansible resource modules - every removable
    account except the connecting one is removed: accounts reporting
    removable=false and the connecting account are skipped and reported in
    skipped_users, and the run is refused when the connecting account is
    unknown.
    """
    if config:
        # Two passes on purpose. _assert_deletable() fails the task, so
        # validating each account immediately before deleting it would let a
        # protected account listed last abort the run with the earlier
        # DELETEs already applied on the device - a failed task that still
        # changed it. Check every listed account that exists first, then
        # delete, so a rejected list is rejected whole.
        deletable: list[tuple[str, dict[str, Any]]] = []
        for entry in config:
            username = entry["username"]
            current = current_map.get(username)
            if current is None:
                # Already absent - nothing to do, and not an error.
                continue
            _assert_deletable(module, username, current, connected_user, result)
            deletable.append((username, current))

        for username, current in deletable:
            _delete_account(module, connection, username, current, result)
        return

    # Delete-all. Without knowing the connecting account there is no way to
    # keep it, so refuse rather than risk locking the connection out.
    if connected_user is None:
        module.fail_json(
            msg="Refusing to delete all accounts: the account this connection "
            "authenticated with could not be determined, so it cannot be "
            "preserved. List the accounts to remove in 'config' instead.",
        )

    _delete_unprotected(module, connection, list(current_map), current_map, connected_user, result)


def _handle_overridden_prepass(
    module: AnsibleModule,
    connection: Connection,
    config: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    connected_user: str | None,
    result: dict[str, Any],
) -> None:
    """Delete accounts that are on the device but absent from config."""
    # Same fail-closed guard as _handle_deleted()'s delete-all path: without
    # connected_user, 'username == connected_user' below is always False, so
    # every removable unlisted account - including the one this connection
    # authenticated with - would be deleted, potentially locking it out.
    if connected_user is None:
        module.fail_json(
            msg="Refusing to run 'overridden': the account this connection "
            "authenticated with could not be determined, so it cannot be "
            "protected from removal for accounts not listed in 'config'. "
            "List every account to keep in 'config' and use 'replaced' "
            "instead, or use a connection the module can identify.",
        )

    listed = {entry["username"] for entry in config}
    # Protected accounts and the connecting account are left in place and
    # reported in 'skipped_users'.
    unlisted = [username for username in current_map if username not in listed]
    _delete_unprotected(module, connection, unlisted, current_map, connected_user, result)


def _patch_account(
    module: AnsibleModule,
    connection: Connection,
    username: str,
    payload: dict[str, Any],
    before: dict[str, Any],
    *,
    created: bool,
    applied_earlier: list[str] | None = None,
) -> None:
    """PATCH one account; on failure, re-read it and say which fields the device applied.

    *before* is the account as it was before this PATCH ({} for an account
    this task just created). *created* marks the follow-up PATCH of a create,
    whose POST already changed the device. *applied_earlier* names the fields
    an earlier PATCH of the same account in this task already applied (see
    _split_update_payload()).
    """
    try:
        _call_api(
            module,
            connection,
            method="PATCH",
            path=ACCOUNTS_SINGLE_PATH.format(username=quote(username, safe="")),
            payload=payload,
        )
    except FeLocalUsersError as exc:
        raise _attribute_patch_failure(
            module, connection, username, payload, before, exc, created=created, applied_earlier=applied_earlier
        )


def _attribute_patch_failure(
    module: AnsibleModule,
    connection: Connection,
    username: str,
    payload: dict[str, Any],
    before: dict[str, Any],
    exc: FeLocalUsersError,
    *,
    created: bool,
    applied_earlier: list[str] | None = None,
) -> FeLocalUsersError:
    """Build the error for a failed account PATCH, attributed by re-reading the account.

    The account is re-read with the same GET the module uses elsewhere and
    each attempted PATCHABLE_FIELDS value is compared with the read-back
    value: applied_fields / not_applied_fields name them. A field that already
    held the requested value before the PATCH (level always rides along with
    a password write) is listed in unchanged_fields instead. The password
    (secret) cannot be compared against the encrypted stored value, so it is
    listed in unknown_fields; no value of any field is ever reported. The
    original message, details, code and err are kept. changed is true when a
    re-read shows a field applied, or when *created* (the POST already
    created the account).
    """
    fields = [field for field in PATCHABLE_FIELDS if FIELD_MAP[field] in payload]
    unchanged = [field for field in fields if not created and before.get(field) == payload[FIELD_MAP[field]]]
    compared = [field for field in fields if field not in unchanged]
    unknown = ["secret"] if "secret" in payload else []
    details: dict[str, object] = dict(exc.details)
    details.update(
        {
            "username": username,
            "attempted_fields": fields + unknown,
            "unchanged_fields": unchanged,
            "unknown_fields": unknown,
        }
    )
    if created:
        details["account_created"] = True
    if applied_earlier:
        details["applied_earlier"] = list(applied_earlier)
    lead = to_text(exc).rstrip().rstrip(".") + "."
    if created:
        lead = "Account '%s' was created, but the follow-up PATCH setting enabled=false failed: %s" % (username, lead)
    parts = [lead]
    if applied_earlier:
        parts.append(
            "An earlier PATCH of account '%s' in this task already applied: %s."
            % (username, ", ".join(applied_earlier))
        )

    reread_error = None
    record: dict[str, Any] | None = None
    try:
        for raw in _fetch_all_accounts(module, connection):
            if raw.get("username") == username:
                record = _to_ansible_output(raw)
                break
        if record is None:
            reread_error = "account '%s' was not found" % username
        else:
            # A compared field the account record omits or reports as null is not
            # established either way: the re-read is incomplete.
            missing = [field for field in compared if record.get(field) is None]
            if missing:
                reread_error = "the re-read of account '%s' did not report %s" % (username, ", ".join(missing))
    except FeLocalUsersError as reread_exc:
        # Never the exception text: it can carry device text that quotes a stored
        # credential, which an enabled-only PATCH gives nothing to mask. Only a
        # numeric code is kept.
        reread_code = (reread_exc.extra or {}).get("code")
        reread_error = "the re-read of the accounts failed%s" % (
            " (error code %d)" % reread_code
            if isinstance(reread_code, int) and not isinstance(reread_code, bool)
            else ""
        )

    applied: list[str] = []
    if reread_error is not None:
        details["reread_error"] = reread_error
        if compared:
            parts.append(
                "Account '%s' could not be re-read to check which of the attempted field(s) (%s) the device "
                "applied (%s)." % (username, ", ".join(compared), reread_error)
            )
    elif compared and record is not None:
        applied = [field for field in compared if record.get(field) == payload[FIELD_MAP[field]]]
        not_applied = [field for field in compared if field not in applied]
        details["applied_fields"] = applied
        details["not_applied_fields"] = not_applied
        parts.append(
            "A re-read of account '%s' shows applied: %s; not applied: %s."
            % (username, ", ".join(applied) or "none", ", ".join(not_applied) or "none")
        )
    if unknown:
        parts.append("Whether the password (secret) was written cannot be verified: the device stores it encrypted.")
    return FeLocalUsersError(
        " ".join(parts), details=details, extra=exc.extra, changed=created or bool(applied) or bool(applied_earlier)
    )


def _verify_created_account(
    module: AnsibleModule,
    connection: Connection,
    entry: dict[str, Any],
    payload: dict[str, Any],
    exc: FeLocalUsersError,
) -> None:
    """Accept an account POST answered 409 when the account is there with the submitted level.

    The account was read as absent before the POST, so a 409 (already exists)
    means it now exists - created by a first attempt whose answer was lost
    (HTTPAPI resends a request after some transport failures), or by another
    writer after the read; the module cannot tell which. It counts as created,
    and as a write, when the re-read lists it with the submitted level and
    *payload* (the POST body) carried no password: the stored password is
    encrypted and cannot be compared, so a match does not prove it is the
    submitted one. Otherwise the outcome is unknown and the task fails with
    changed=true.
    """
    username = entry["username"]
    try:
        record = next(
            (
                _to_ansible_output(raw)
                for raw in _fetch_all_accounts(module, connection)
                if raw.get("username") == username
            ),
            None,
        )
    except FeLocalUsersError as reread_exc:
        record = None
        reason = "the accounts could not be re-read%s" % (
            " (error code %s)" % reread_exc.extra.get("code")
            if (reread_exc.extra or {}).get("code") is not None
            else ""
        )
    else:
        reason = "the re-read does not list it" if record is None else None
    if record is not None:
        if entry.get("level") is None or record.get("level") == entry["level"]:
            # By presence: an empty password is a value the re-read cannot confirm either.
            if payload.get("secret") is None:
                if isinstance(connection, _TrackedConnection):
                    connection.record_write()
                return
            raise FeLocalUsersError(
                "The POST creating account '%s' answered 409 (already exists). The re-read shows it with the "
                "submitted level, but its stored password cannot be compared: it may have been created by a first "
                "attempt whose answer was lost, or by another writer with a different password, so the outcome is "
                "unknown. To re-apply the password, run the task again with update_password: always and the "
                "account's old_secret, or super_user_name and super_user_password." % username,
                details={"username": username, "outcome": "unknown", "unknown_fields": ["secret"]},
                extra=exc.extra,
                changed=True,
            ) from exc
        reason = "the re-read shows it with level %s" % record.get("level")
    raise FeLocalUsersError(
        "The POST creating account '%s' answered 409 (already exists), and %s; it may have been created by a first "
        "attempt whose answer was lost, so the outcome is unknown." % (username, reason),
        details={"username": username, "outcome": "unknown"},
        extra=exc.extra,
        changed=True,
    ) from exc


def _create_account(
    module: AnsibleModule,
    connection: Connection,
    entry: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """POST one new account and record the per-account entry."""
    username = entry["username"]
    _assert_create_level(module, entry)
    payload = _build_create_payload(entry)

    if not module.check_mode:
        try:
            _call_api(
                module,
                connection,
                method="POST",
                path=ACCOUNTS_LIST_PATH,
                payload=payload,
            )
        except FeLocalUsersError as exc:
            if (exc.extra or {}).get("code") != 409:
                raise
            _verify_created_account(module, connection, entry, payload, exc)

        # A real device always creates a new account enabled, silently
        # ignoring 'enabled: false' on POST - confirmed 2026-09-22, and
        # consistent with the User Guide's account-creation CLI syntax
        # ("username add ... enable"), which has no disabled-creation
        # form. A follow-up PATCH is required to land it, the same
        # pattern extreme_fe_lag.py uses for fields the device drops on
        # create but accepts on update.
        if entry.get("enabled") is False:
            _patch_account(module, connection, username, {"enabled": False}, {}, created=True)

    # Predicted state - the device answers 204 with no body.
    #
    # 'secret' is deliberately left out of it. The supplied
    # secret.is_encrypted describes the value the task SENT, while the
    # is_encrypted a later GET reports describes what the device STORED -
    # and Fabric Engine stores passwords encrypted whichever form it was
    # given (the OpenAPI AaaSecret.value description is explicit that a GET
    # on VOSS returns the encrypted password). Echoing the sent flag back
    # therefore predicted 'is_encrypted: false' for a cleartext create,
    # contradicting both the re-read 'after' of a real run and the state a
    # --check --diff claims would be written. Predicting 'true' instead
    # would be the other guess; it has not been confirmed against a device
    # for this field, so this reports nothing rather than reporting
    # something unverified. The password itself is never in 'after' either
    # way, so nothing that was previously usable is lost.
    after = {key: entry[key] for key in FIELD_MAP if entry.get(key) is not None}
    # A newly created account is always reported enabled unless the follow-up
    # PATCH above disabled it (the device ignores 'enabled: false' on POST),
    # and removable unless 'removable' was supplied: per the OpenAPI
    # UserAccountType only accounts of the device default configuration are
    # non-removable, and those are never created through this module. Filling
    # both in keeps the check-mode prediction equal to the re-read 'after'.
    after.setdefault("enabled", True)
    after.setdefault("removable", True)

    result["changed"] = True
    result["local_users"].append(
        {
            "username": username,
            "before": {},
            "after": after,
            "changed": True,
            "differences": _compute_diff({}, after),
        }
    )


def _assert_removable_unchanged(module: AnsibleModule, entry: dict[str, Any], current: dict[str, Any]) -> None:
    """
    Reject an attempt to change 'removable' on an existing account.

    The REST PATCH body (UserAccountAttributes) has no 'removable' field, so
    the device cannot honour such a change. Failing is clearer than silently
    dropping it.

    Compared against _is_removable(current), not the raw current.get()
    value: a device response that omits 'removable' means removable=true
    (see _is_removable()), so supplying removable: true for such an account
    must be recognised as unchanged, not as a change from None to True.
    """
    desired = entry.get("removable")
    if desired is None:
        return
    current_removable = _is_removable(current)
    if desired != current_removable:
        module.fail_json(
            msg="Cannot change 'removable' on existing account '{0}': the REST "
            "API accepts this field only when the account is created. Current "
            "value is {1}, requested {2}.".format(entry["username"], current_removable, desired)
        )


def _assert_level_unchanged(module: AnsibleModule, entry: dict[str, Any], current: dict[str, Any]) -> None:
    """
    Reject an attempt to change 'level' on an existing account.

    'level' is required on every writing-state entry (see _validate_config()),
    so it is always present here - this only fails when the supplied value
    actually differs from the account's current one. A real device rejected
    every attempt to change level on an existing custom account - alone,
    together with a password, and together with 'enabled' - each with a
    different error (confirmed 2026-09-22), and the User Guide states a
    custom account's access level "cannot be changed later" once created.
    Failing here, before any PATCH is attempted, is clearer than letting the
    device reject it: delete the account and recreate it with the new level.
    """
    desired = entry.get("level")
    if desired is None or desired == current.get("level"):
        return
    module.fail_json(
        msg="Cannot change 'level' on existing account '{0}': Fabric Engine "
        "does not support changing a custom account's access level after "
        "creation. Current value is {1}, requested {2}. Delete the account "
        "and recreate it with the desired level instead.".format(entry["username"], current.get("level"), desired)
    )


def _assert_password_credentials(module: AnsibleModule, entry: dict[str, Any], *, write_password: bool) -> None:
    """
    Reject a password PATCH that is missing its required verification
    credentials.

    A real device rejects a PATCH carrying 'secret' (to overwrite an
    existing account's password) unless it also carries either 'oldSecret'
    or both 'superUserName' and 'superUserPassword' - confirmed 2026-09-22
    (the device's message misspells them):
    "The following attributes are required: (secret, level, value,
    oldSecret) or (secret, level, value, superUsername, superUserpassword)".
    Without this check, the documented default update_password: always
    would send an invalid PATCH on every normal rerun where only 'secret'
    is supplied, and the device would reject it instead of this module
    giving a clear, actionable error.
    """
    if not write_password:
        return
    secret = _build_secret_payload(entry.get("secret"))
    if not secret:
        return
    has_old_secret = bool(_build_secret_payload(entry.get("old_secret")))
    has_super_user = entry.get("super_user_name") is not None and entry.get("super_user_password") is not None
    if not has_old_secret and not has_super_user:
        module.fail_json(
            msg="Cannot write a password to existing account '{0}': the "
            "device requires either 'old_secret' or both "
            "'super_user_name' and 'super_user_password' to verify the "
            "change. Supply one of these credential groups, or set "
            "update_password: on_create to only write the password when "
            "the account is created.".format(entry["username"])
        )


def _assert_create_level(module: AnsibleModule, entry: dict[str, Any]) -> None:
    """Reject creating an account with a level Fabric Engine cannot create (see CREATE_LEVELS)."""
    level = entry.get("level")
    if level is None or level in CREATE_LEVELS:
        return
    module.fail_json(
        msg="Cannot create account '{0}' with level {1}: Fabric Engine creates accounts only with "
        "level {2}. {1} describes a built-in account (l1, l2 or l3) and is accepted only for an "
        "account that already has it.".format(entry["username"], level, ", ".join(CREATE_LEVELS))
    )


def _validate_listed_entries(
    module: AnsibleModule,
    config: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    update_password: str,
) -> None:
    """
    Run every per-entry write guard against 'config' before any write request is sent.

    The account list has already been read (the guards compare with it); no
    POST, PATCH or DELETE has been sent yet.

    _update_account() runs these same guards, but only when it is reached -
    for 'overridden' that is after _handle_overridden_prepass() has already
    issued real DELETE calls against unlisted accounts. Preflighting them
    here means a bad entry (an unsupported level change, a password PATCH
    missing its verification credentials, ...) fails the whole task before
    any destructive request is made, instead of after other accounts have
    already been removed from the device.
    """
    write_password = update_password == UPDATE_PASSWORD_ALWAYS
    for entry in config:
        current = current_map.get(entry["username"])
        if current is None:
            _assert_create_level(module, entry)
            continue
        _assert_removable_unchanged(module, entry, current)
        _assert_level_unchanged(module, entry, current)
        _assert_password_credentials(module, entry, write_password=write_password)


def _split_update_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the PATCH bodies for *payload*: one, or two when it changes both enabled and the password.

    The device refuses a password and a state change in one PATCH (422
    "Cannot update user password and user state at the same time.", 9.4 and
    9.5) and accepts each on its own. A disable is sent before the
    password and an enable after it, so a failure in between never leaves the
    account enabled when it was meant to be off, or enabled with the old password.
    """
    if "secret" not in payload or "enabled" not in payload:
        return [payload]
    state = {"enabled": payload["enabled"]}
    password = {key: value for key, value in payload.items() if key != "enabled"}
    return [state, password] if payload["enabled"] is False else [password, state]


def _update_account(
    module: AnsibleModule,
    connection: Connection,
    entry: dict[str, Any],
    current: dict[str, Any],
    update_password: str,
    result: dict[str, Any],
) -> None:
    """PATCH one existing account, skipping the request when nothing differs."""
    username = entry["username"]
    _assert_removable_unchanged(module, entry, current)
    _assert_level_unchanged(module, entry, current)

    # The stored password is encrypted, so it can never be compared. Under
    # 'always' a supplied password is written every run; under 'on_create' an
    # existing account is never re-written.
    write_password = update_password == UPDATE_PASSWORD_ALWAYS
    _assert_password_credentials(module, entry, write_password=write_password)
    payload = _build_update_payload(entry, current, write_password=write_password)

    if not payload:
        result["local_users"].append(
            {
                "username": username,
                "before": current,
                "after": current,
                "changed": False,
                "differences": {},
            }
        )
        return

    if not module.check_mode:
        # Fields an accepted earlier part changed (level only rides along with
        # a password, so it is listed only when it differed).
        applied_earlier: list[str] = []
        known = dict(current)
        for part in _split_update_payload(payload):
            _patch_account(module, connection, username, part, known, created=False, applied_earlier=applied_earlier)
            applied_earlier.extend(
                field
                for field in PATCHABLE_FIELDS
                if FIELD_MAP[field] in part and part[FIELD_MAP[field]] != known.get(field)
            )
            if "secret" in part:
                applied_earlier.append("secret")
            known = _predict_after(known, part)

    after = _predict_after(current, payload)
    result["changed"] = True
    result["local_users"].append(
        {
            "username": username,
            "before": current,
            "after": after,
            "changed": True,
            "differences": _compute_diff(current, after),
        }
    )


def _handle_merge_replace(
    module: AnsibleModule,
    connection: Connection,
    config: list[dict[str, Any]],
    current_map: dict[str, dict[str, Any]],
    update_password: str,
    result: dict[str, Any],
) -> None:
    """
    Apply each listed account: create it when absent, update it when present.

    merged and replaced converge here. 'level' and 'enabled' are mandatory for
    both, and the remaining writable fields cannot be reset - 'secret' has no
    factory default and 'removable' is not patchable - so the authoritative set
    is the supplied set either way.
    """
    for entry in config:
        username = entry["username"]
        current = current_map.get(username)
        if current is None:
            _create_account(module, connection, entry, result)
        else:
            _update_account(module, connection, entry, current, update_password, result)


def _capture_after_state(module: AnsibleModule, connection: Connection, result: dict[str, Any]) -> None:
    """Re-read the accounts so 'after' reflects what the device actually holds."""
    raw_list = _fetch_all_accounts(module, connection)
    accounts = [_to_ansible_output(raw) for raw in raw_list]
    result["after"] = sorted(accounts, key=lambda acc: acc.get("username") or "")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Module entry point: parse arguments, dispatch on state, return results."""
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
    )

    state: str = module.params["state"]
    # An omitted config and config: [] mean the same: for 'deleted' both delete
    # every removable account except the connecting one (_handle_deleted()).
    raw_config: list[dict[str, Any]] | None = module.params.get("config")
    config: list[dict[str, Any]] = raw_config or []
    gather_filter: list[str] | None = module.params.get("gather_filter")
    update_password: str = module.params["update_password"]

    # Guard: without this, 'overridden' with no config would delete every
    # removable account on the device.
    if state in WRITING_STATES and not config:
        module.fail_json(msg=f"value of config parameter must not be empty for state {state}")

    _validate_config(module, state, config)

    connection = _get_connection(module)

    result: dict[str, Any] = {
        "changed": False,
        "local_users": [],
    }

    try:
        # ── GATHERED ──────────────────────────────────────────────────────
        if state == STATE_GATHERED:
            _handle_gathered(module, connection, gather_filter, result)
            module.exit_json(**result)
            return

        # ── Fetch current state for the change-making states ───────────────
        raw_list = _fetch_all_accounts(module, connection)
        current_map: dict[str, dict[str, Any]] = {}
        for raw in raw_list:
            account = _to_ansible_output(raw)
            username = account.get("username")
            if isinstance(username, str) and username:
                current_map[username] = account

        before_state = sorted(current_map.values(), key=lambda acc: acc["username"])
        result["before"] = before_state

        # The connecting account must survive every destructive path.
        connected_user = _connected_username(connection)

        # ── DELETED ───────────────────────────────────────────────────────
        if state == STATE_DELETED:
            _handle_deleted(module, connection, raw_config, current_map, connected_user, result)
        else:
            # ── Preflight per-entry guards ─────────────────────────────────
            # Validate every listed entry against current device state
            # before any destructive request is sent - including the
            # overridden pre-pass's DELETEs below, which must not run ahead
            # of a guard that would otherwise fail the task partway through.
            _validate_listed_entries(module, config, current_map, update_password)

            # ── OVERRIDDEN pre-pass ───────────────────────────────────────
            if state == STATE_OVERRIDDEN:
                _handle_overridden_prepass(module, connection, config, current_map, connected_user, result)

            # ── MERGED / REPLACED / OVERRIDDEN - per-entry ────────────────
            _handle_merge_replace(module, connection, config, current_map, update_password, result)

        # ── Capture after state ───────────────────────────────────────────
        # 'after' is returned for every action state - a live re-fetch when
        # a real change was made, the predicted state (no post-change GET
        # exists yet) in check mode, and the unchanged 'before' when nothing
        # had to be written.
        if not result["changed"]:
            result["after"] = [dict(acc) for acc in before_state]
        elif module.check_mode:
            result["after"] = _predicted_state(result, before_state)
        else:
            _capture_after_state(module, connection, result)

        # Diff mode (--diff): Ansible renders the before/after pair itself.
        # In check mode the 'after' is the predicted state, which is exactly
        # what --check --diff is meant to show.
        if module._diff:
            result["diff"] = {
                "before": result["before"],
                "after": result["after"],
            }

        module.exit_json(**result)

    except FeLocalUsersError as exc:
        module.fail_json(**_fail_kwargs_after_writes(exc.to_fail_kwargs(), connection, result))
    except ConnectionError as exc:
        module.fail_json(
            **_fail_kwargs_after_writes(
                {
                    "msg": f"Connection error: {to_text(exc)}",
                    "code": getattr(exc, "code", None),
                    "err": getattr(exc, "err", None),
                },
                connection,
                result,
            )
        )


def _fail_kwargs_after_writes(kwargs: dict[str, Any], connection: Connection, result: dict[str, Any]) -> dict[str, Any]:
    """Report changed=true (and name the accounts already changed) when the task wrote before failing.

    result['local_users'] holds the accounts whose requests all succeeded. The
    failing account is added when its failure itself confirms a change: it was
    created before a follow-up PATCH failed (details.account_created), or the
    re-read of a rejected PATCH shows a field applied (details.applied_fields),
    which leaves connection.wrote false.
    """
    wrote = bool(getattr(connection, "wrote", False))
    changed = bool(kwargs.get("changed")) or wrote
    kwargs["changed"] = changed
    done = [entry["username"] for entry in result.get("local_users", []) if entry.get("changed")]
    failed_details = kwargs.get("details") or {}
    failed_user = failed_details.get("username")
    if (
        failed_user
        and failed_user not in done
        and (
            failed_details.get("account_created")
            or failed_details.get("applied_fields")
            or failed_details.get("applied_earlier")
        )
    ):
        done.append(failed_user)
    if changed and done:
        kwargs["msg"] = "%s. Accounts already changed by this task: %s." % (
            to_text(kwargs["msg"]).rstrip().rstrip("."),
            ", ".join(done),
        )
        details = dict(kwargs.get("details") or {})
        details["changed_users"] = done
        kwargs["details"] = details
    return kwargs


def _predicted_state(result: dict[str, Any], before_state: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build the predicted account list from the per-account entries.

    Used for the diff in check mode, where no post-change GET is made.
    """
    predicted = {acc["username"]: acc for acc in before_state}
    for entry in result["local_users"]:
        username = entry["username"]
        after = entry.get("after")
        if after:
            predicted[username] = after
        else:
            predicted.pop(username, None)
    return sorted(predicted.values(), key=lambda acc: acc.get("username") or "")


if __name__ == "__main__":
    main()
