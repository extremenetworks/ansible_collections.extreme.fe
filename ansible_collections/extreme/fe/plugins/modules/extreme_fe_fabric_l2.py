# -*- coding: utf-8 -*-
"""Ansible module to manage ExtremeNetworks Fabric Engine ISIDs via HTTPAPI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.connection import Connection, ConnectionError
from ansible.module_utils.common.text.converters import to_text

DOCUMENTATION = r"""
module: extreme_fe_fabric_l2
short_description: Manage Fabric Engine ISIDs on ExtremeNetworks switches
version_added: "1.0.0"
description:
    - "Manage Layer 2 ISIDs (service instance identifiers) on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI plugin."
    - Supports provisioning CVLAN-backed ISIDs, updating friendly names, gathering existing definitions, and removing bindings.
    - Uses the standard Ansible resource module C(config) list pattern for multi-resource management.
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - "Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project."
    - Currently supports managing CVLAN-backed ISIDs. Additional ISID types may be implemented in future revisions.
    - Supports Ansible check mode for configuration states.
requirements:
    - ansible.netcommon
options:
  state:
    description:
      - Desired module operation.
      - "C(merged) ensures the supplied attributes are merged with the running configuration and creates the ISID when missing."
      - "C(replaced) treats the supplied values as authoritative for the targeted ISID. When C(name) is omitted, the existing friendly name is cleared; C(cvlan) is left unchanged if omitted."
      - "C(overridden) like replaced, but also deletes any device ISIDs NOT listed in C(config)."
      - "C(deleted) removes the listed ISID bindings from the device."
      - "C(gathered) returns current ISID data without making changes."
    type: str
    choices: [merged, replaced, overridden, deleted, gathered]
    default: merged
  config:
    description:
      - List of ISID configurations to manage.
      - Each entry specifies one ISID and its desired attributes.
      - Required for all states except C(gathered).
    type: list
    elements: dict
    suboptions:
      isid:
        description:
          - Numeric service identifier (1-15999999).
        type: int
        required: true
      isid_type:
        description:
          - ISID service type. Only C(CVLAN) is currently supported.
        type: str
        choices: [CVLAN]
        default: CVLAN
      name:
        description:
          - Friendly name to associate with the ISID.
          - "When C(state) is C(replaced) or C(overridden) and C(name) is omitted, the module clears the existing friendly name."
        type: str
      cvlan:
        description:
          - CVLAN identifier to bind to the ISID when C(isid_type) is C(CVLAN).
          - Required when creating a new ISID.
        type: int
  gather_filter:
    description:
      - Limit gathered output to this list of ISID identifiers.
      - When omitted, the module returns all configured ISIDs.
    type: list
    elements: int
"""

EXAMPLES = r"""
# Create two ISIDs
- name: Provision ISIDs 500 and 600
  extreme.fe.extreme_fe_fabric_l2:
    state: merged
    config:
      - isid: 500
        cvlan: 500
        name: Campus-500
      - isid: 600
        cvlan: 600
        name: Campus-600

# Replace ISID 500 — name is cleared because it's omitted
- name: Replace ISID 500 configuration
  extreme.fe.extreme_fe_fabric_l2:
    state: replaced
    config:
      - isid: 500
        cvlan: 500

# Override — only ISID 500 should exist; delete all others
- name: Override — enforce only ISID 500
  extreme.fe.extreme_fe_fabric_l2:
    state: overridden
    config:
      - isid: 500
        cvlan: 500
        name: Campus-500

# Delete specific ISIDs
- name: Delete ISIDs 500 and 600
  extreme.fe.extreme_fe_fabric_l2:
    state: deleted
    config:
      - isid: 500
        cvlan: 500
      - isid: 600
        cvlan: 600

# Gather all ISIDs
- name: Collect all ISID information
  extreme.fe.extreme_fe_fabric_l2:
    state: gathered
  register: isid_config

# Gather specific ISIDs
- name: Gather ISIDs 500 and 600 only
  extreme.fe.extreme_fe_fabric_l2:
    state: gathered
    gather_filter:
      - 500
      - 600
"""

RETURN = r"""
changed:
  description: Indicates whether any changes were made.
  returned: always
  type: bool
isids:
  description: Per-ISID results showing before/after state.
  returned: when state != gathered
  type: list
  elements: dict
  sample:
    - isid: 500
      before: null
      after:
        isid: 500
        name: Campus-500
        platformVlanId: 500
      changed: true
deleted_isids:
  description: ISIDs deleted by overridden state (not in config list).
  returned: when state == overridden
  type: list
  sample: [700, 800]
skipped_isids:
  description: ISIDs that overridden could not delete (e.g. Auto-Sense FA I-SIDs).
  returned: when state == overridden
  type: list
  elements: dict
  sample:
    - isid: 15999999
      reason: "Cannot change the associated vlan of an Auto-Sense FA i-sid"
gathered:
  description: List of ISID entries discovered from the device.
  returned: when state == gathered
  type: list
  sample:
    - isid: 500
      name: Campus-500
      platformVlanId: 500
"""


# ── Flat-parameter names that were used in the old API ──
_OLD_FLAT_PARAMS = frozenset({"isid", "isid_type", "cvlan", "name"})

ARGUMENT_SPEC: Dict[str, Any] = {
    "state": {
        "type": "str",
        "choices": ["merged", "replaced", "overridden", "deleted", "gathered"],
        "default": "merged",
    },
    "config": {
        "type": "list",
        "elements": "dict",
        "options": {
            "isid": {"type": "int", "required": True},
            "isid_type": {"type": "str", "choices": ["CVLAN"], "default": "CVLAN"},
            "name": {"type": "str"},
            "cvlan": {"type": "int"},
        },
    },
    "gather_filter": {"type": "list", "elements": "int"},
    # Keep old params in spec so Ansible doesn't reject them outright;
    # we validate and raise a clear error ourselves.
    # NOTE: no defaults here — a non-None value means the user
    # explicitly passed the old flat param.
    "isid": {"type": "int"},
    "isid_type": {"type": "str", "choices": ["CVLAN"]},
    "name": {"type": "str"},
    "cvlan": {"type": "int"},
}

ISID_BASE_PATH = "/v0/configuration/spbm/l2/isid"


# ── Exception ──


class FeFabricL2Error(Exception):
    """Base exception for the Fabric L2 module."""

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


# ── REST helpers ──


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
    if isinstance(message, str):
        lowered = message.lower()
        if "not found" in lowered or "does not exist" in lowered:
            return True
    return False


def _extract_cvlan(data: Optional[Dict[str, object]]) -> Optional[int]:
    if not isinstance(data, dict):
        return None
    interfaces = data.get("interfaces")
    platform_vlan: Optional[object] = None
    if isinstance(interfaces, dict):
        platform_vlan = interfaces.get("platformVlanId") or interfaces.get(
            "platform_vlan_id"
        )
    if platform_vlan is None:
        platform_vlan = data.get("platformVlanId") or data.get("platform_vlan_id")
    if platform_vlan is None:
        return None
    try:
        return int(platform_vlan)
    except (TypeError, ValueError):
        return None


def _normalize_isid_record(
    data: Optional[Dict[str, object]], isid: Optional[int] = None
) -> Optional[Dict[str, object]]:
    """Normalise an API record so ``isid`` and ``platformVlanId`` are top-level."""
    if data is None:
        return None
    out = dict(data)
    if isid is not None and "isid" not in out:
        out["isid"] = isid
    # Ensure isid is always an int for consistent comparisons.
    raw_isid = out.get("isid")
    if raw_isid is not None:
        try:
            out["isid"] = int(raw_isid)
        except (TypeError, ValueError):
            pass
    interfaces = out.pop("interfaces", None)
    if isinstance(interfaces, dict):
        pvid = interfaces.get("platformVlanId")
        if pvid is not None and "platformVlanId" not in out:
            out["platformVlanId"] = pvid
    return out


def _isid_path(isid: int) -> str:
    return "/".join([ISID_BASE_PATH, quote(str(isid), safe="")])


def _cvlan_delete_path(isid: int, cvlan: int) -> str:
    return "/".join(
        [ISID_BASE_PATH, quote(str(isid), safe=""), "cvlan", quote(str(cvlan), safe="")]
    )


def _ensure_list(payload: Optional[object]) -> List[Dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("isids", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # The list endpoint may return {cvlan: [...], suni: [...], tuni: [...]}.
        # Flatten all sub-lists into a single list of ISID records.
        type_keys = ("cvlan", "suni", "tuni")
        if any(k in payload for k in type_keys):
            combined: List[Dict[str, object]] = []
            for tk in type_keys:
                sub = payload.get(tk)
                if isinstance(sub, list):
                    combined.extend(item for item in sub if isinstance(item, dict))
            return combined
        return [payload]
    return []


# ── Device I/O ──


def get_isid(connection: Connection, isid: int) -> Optional[Dict[str, object]]:
    path = _isid_path(isid)
    try:
        data = connection.send_request(None, path=path, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None:
        return None
    if _is_not_found_response(data):
        return None
    if not isinstance(data, dict):
        return None
    return _normalize_isid_record(data, isid)


def list_isids(connection: Connection) -> List[Dict[str, object]]:
    try:
        payload = connection.send_request(None, path=ISID_BASE_PATH, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    if payload is None or _is_not_found_response(payload):
        return []
    raw = _ensure_list(payload)
    return [_normalize_isid_record(r, r.get("isid")) for r in raw]


def _list_cvlan_isids_raw(connection: Connection) -> List[Dict[str, object]]:
    """Return only CVLAN-type ISIDs from the device.

    The list endpoint may return ``{cvlan: [...], suni: [...], tuni: [...]}``.
    This helper extracts just the ``cvlan`` sub-list so that overridden
    state does not accidentally delete SUNI/TUNI ISIDs managed elsewhere.
    """
    try:
        payload = connection.send_request(None, path=ISID_BASE_PATH, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    if payload is None or _is_not_found_response(payload):
        return []
    if isinstance(payload, dict) and "cvlan" in payload:
        sub = payload["cvlan"]
        if isinstance(sub, list):
            return [
                _normalize_isid_record(r, r.get("isid"))
                for r in sub
                if isinstance(r, dict)
            ]
    # Fallback: the API did not return the typed {cvlan, suni, tuni} structure.
    # Filter to CVLAN records only so overridden does not delete SUNI/TUNI ISIDs.
    raw = _ensure_list(payload)
    return [
        _normalize_isid_record(r, r.get("isid"))
        for r in raw
        if isinstance(r, dict)
        and str(r.get("isidType") or r.get("type") or "").upper() in ("", "CVLAN")
    ]


def create_isid(
    connection: Connection,
    *,
    isid: int,
    isid_type: str,
    cvlan: Optional[int],
    name: Optional[str],
) -> None:
    payload: Dict[str, object] = {"isidType": isid_type, "isid": isid}
    if isid_type == "CVLAN":
        if cvlan is None:
            raise FeFabricL2Error(
                "Parameter 'cvlan' is required when creating a CVLAN ISID"
            )
        payload["platformVlanId"] = cvlan
    if name is not None:
        payload["name"] = name
    connection.send_request(payload, path=ISID_BASE_PATH, method="POST")


def update_isid_name(connection: Connection, *, isid: int, name: str) -> None:
    path = _isid_path(isid)
    connection.send_request({"name": name}, path=path, method="PATCH")


def delete_isid(connection: Connection, *, isid: int, cvlan: int) -> None:
    path = _cvlan_delete_path(isid, cvlan)
    connection.send_request(None, path=path, method="DELETE")


# ── Simulation helpers ──


def _simulate_after_creation(
    isid: int, isid_type: str, cvlan: Optional[int], name: Optional[str]
) -> Dict[str, object]:
    simulated: Dict[str, object] = {"isid": isid, "isidType": isid_type}
    if cvlan is not None:
        simulated["platformVlanId"] = cvlan
    if name is not None:
        simulated["name"] = name
    return simulated


# ── Per-entry processing ──


def _process_entry_merged(
    entry: Dict[str, Any], connection: Connection, check_mode: bool
) -> Dict[str, object]:
    """Merged: apply supplied fields, leave unspecified unchanged."""
    isid = entry["isid"]
    isid_type = entry.get("isid_type") or "CVLAN"
    desired_name = entry.get("name")
    desired_cvlan = entry.get("cvlan")

    before = get_isid(connection, isid)
    before_data = deepcopy(before) if before else None

    # ── ISID does not exist → create ──
    if before is None:
        if isid_type == "CVLAN" and desired_cvlan is None:
            raise FeFabricL2Error(
                "Parameter 'cvlan' is required when creating a CVLAN ISID (isid=%d)"
                % isid
            )
        if check_mode:
            after = _simulate_after_creation(
                isid, isid_type, desired_cvlan, desired_name
            )
            return {"isid": isid, "before": None, "after": after, "changed": True}
        create_isid(
            connection,
            isid=isid,
            isid_type=isid_type,
            cvlan=desired_cvlan,
            name=desired_name,
        )
        after = get_isid(connection, isid)
        return {"isid": isid, "before": None, "after": after, "changed": True}

    # ── ISID exists → update if needed ──
    return _apply_updates(
        entry, before, before_data, connection, check_mode, clear_name_on_omit=False
    )


def _process_entry_replaced(
    entry: Dict[str, Any], connection: Connection, check_mode: bool
) -> Dict[str, object]:
    """Replaced: apply supplied fields; clear name when omitted, leave cvlan unchanged."""
    isid = entry["isid"]
    isid_type = entry.get("isid_type") or "CVLAN"
    desired_name = entry.get("name")
    desired_cvlan = entry.get("cvlan")

    before = get_isid(connection, isid)
    before_data = deepcopy(before) if before else None

    if before is None:
        if isid_type == "CVLAN" and desired_cvlan is None:
            raise FeFabricL2Error(
                "Parameter 'cvlan' is required when creating a CVLAN ISID (isid=%d)"
                % isid
            )
        if check_mode:
            after = _simulate_after_creation(
                isid, isid_type, desired_cvlan, desired_name
            )
            return {"isid": isid, "before": None, "after": after, "changed": True}
        create_isid(
            connection,
            isid=isid,
            isid_type=isid_type,
            cvlan=desired_cvlan,
            name=desired_name,
        )
        after = get_isid(connection, isid)
        return {"isid": isid, "before": None, "after": after, "changed": True}

    return _apply_updates(
        entry, before, before_data, connection, check_mode, clear_name_on_omit=True
    )


def _apply_updates(
    entry: Dict[str, Any],
    before: Dict[str, object],
    before_data: Optional[Dict[str, object]],
    connection: Connection,
    check_mode: bool,
    *,
    clear_name_on_omit: bool,
) -> Dict[str, object]:
    """Apply CVLAN and name changes to an existing ISID."""
    isid = entry["isid"]
    isid_type = entry.get("isid_type") or "CVLAN"
    desired_name = entry.get("name")
    desired_cvlan = entry.get("cvlan")

    existing_type = (before.get("type") or before.get("isidType") or "").upper()
    if existing_type and existing_type != isid_type:
        raise FeFabricL2Error(
            "ISID %d exists with type %s, which does not match requested %s"
            % (isid, existing_type, isid_type)
        )

    current_cvlan = _extract_cvlan(before)
    current_name = before.get("name")

    change_requested = False
    refresh_after = False
    simulated_after = deepcopy(before)

    # ── CVLAN change ──
    if desired_cvlan is not None and desired_cvlan != current_cvlan:
        change_requested = True
        if check_mode:
            simulated_after["platformVlanId"] = desired_cvlan
        else:
            if current_cvlan is None:
                raise FeFabricL2Error(
                    "Unable to determine existing CVLAN binding for ISID %d; provide the 'cvlan' parameter"
                    % isid
                )
            delete_isid(connection, isid=isid, cvlan=current_cvlan)
            replacement_name = (
                desired_name if desired_name is not None else current_name
            )
            create_isid(
                connection,
                isid=isid,
                isid_type=isid_type,
                cvlan=desired_cvlan,
                name=replacement_name,
            )
            refresh_after = True

    # ── Name change ──
    target_name: Optional[str]
    if clear_name_on_omit and desired_name is None:
        target_name = ""
    else:
        target_name = desired_name

    if target_name is not None and (current_name or "") != target_name:
        change_requested = True
        if check_mode:
            simulated_after["name"] = target_name
        else:
            update_isid_name(connection, isid=isid, name=target_name)
            refresh_after = True

    if check_mode:
        after_data = simulated_after if change_requested else before_data
        return {
            "isid": isid,
            "before": before_data,
            "after": after_data,
            "changed": change_requested,
        }

    if not change_requested:
        return {
            "isid": isid,
            "before": before_data,
            "after": before_data,
            "changed": False,
        }

    after = get_isid(connection, isid) if refresh_after else before
    return {"isid": isid, "before": before_data, "after": after, "changed": True}


def _process_entry_deleted(
    entry: Dict[str, Any], connection: Connection, check_mode: bool
) -> Dict[str, object]:
    """Delete a single ISID."""
    isid = entry["isid"]
    supplied_cvlan = entry.get("cvlan")

    current = get_isid(connection, isid)
    before = deepcopy(current) if current else None

    if current is None:
        return {"isid": isid, "before": None, "after": None, "changed": False}

    current_cvlan = _extract_cvlan(current)
    target_cvlan = supplied_cvlan or current_cvlan
    if target_cvlan is None:
        raise FeFabricL2Error(
            "Unable to determine CVLAN bound to ISID %d; provide the 'cvlan' parameter"
            % isid
        )

    if check_mode:
        return {"isid": isid, "before": before, "after": None, "changed": True}

    delete_isid(connection, isid=isid, cvlan=target_cvlan)
    return {"isid": isid, "before": before, "after": None, "changed": True}


# ── State handlers ──


def handle_merged(
    config: List[Dict[str, Any]], connection: Connection, check_mode: bool
) -> Dict[str, object]:
    results = []
    changed = False
    for entry in config:
        result = _process_entry_merged(entry, connection, check_mode)
        results.append(result)
        if result["changed"]:
            changed = True
    return {"changed": changed, "isids": results}


def handle_replaced(
    config: List[Dict[str, Any]], connection: Connection, check_mode: bool
) -> Dict[str, object]:
    results = []
    changed = False
    for entry in config:
        result = _process_entry_replaced(entry, connection, check_mode)
        results.append(result)
        if result["changed"]:
            changed = True
    return {"changed": changed, "isids": results}


def handle_overridden(
    config: List[Dict[str, Any]], connection: Connection, check_mode: bool
) -> Dict[str, object]:
    """Phase 1: delete CVLAN ISIDs not in config. Phase 2: apply replaced per entry."""
    wanted_isids = {e["isid"] for e in config}

    # Phase 1: discover and delete unlisted CVLAN ISIDs.
    # Only CVLAN ISIDs are managed by this module; SUNI/TUNI are left alone.
    all_cvlan_isids = _list_cvlan_isids_raw(connection)
    deleted_isids: List[int] = []
    skipped_isids: List[Dict[str, object]] = []
    changed = False

    for record in all_cvlan_isids:
        device_isid = record.get("isid")
        if device_isid is None:
            continue
        if device_isid in wanted_isids:
            continue
        # This CVLAN ISID is not in the desired config — delete it.
        device_cvlan = _extract_cvlan(record)
        if device_cvlan is None:
            skipped_isids.append(
                {
                    "isid": device_isid,
                    "reason": "Unable to determine CVLAN binding; cannot delete",
                }
            )
            continue
        if not check_mode:
            try:
                delete_isid(connection, isid=device_isid, cvlan=device_cvlan)
            except ConnectionError as exc:
                # Device refused deletion (e.g. Auto-Sense FA I-SID).
                # Record and continue instead of failing the task.
                skipped_isids.append(
                    {
                        "isid": device_isid,
                        "reason": to_text(exc),
                    }
                )
                continue
        deleted_isids.append(device_isid)
        changed = True

    # Phase 2: apply replaced for each config entry
    results = []
    for entry in config:
        result = _process_entry_replaced(entry, connection, check_mode)
        results.append(result)
        if result["changed"]:
            changed = True

    return {
        "changed": changed,
        "isids": results,
        "deleted_isids": deleted_isids,
        "skipped_isids": skipped_isids,
    }


def handle_deleted(
    config: List[Dict[str, Any]], connection: Connection, check_mode: bool
) -> Dict[str, object]:
    results = []
    changed = False
    for entry in config:
        result = _process_entry_deleted(entry, connection, check_mode)
        results.append(result)
        if result["changed"]:
            changed = True
    return {"changed": changed, "isids": results}


def handle_gathered(module: AnsibleModule, connection: Connection) -> Dict[str, object]:
    gather_filter: Optional[List[int]] = module.params.get("gather_filter")

    gathered: List[Dict[str, object]] = []

    if gather_filter:
        for candidate in gather_filter:
            record = get_isid(connection, candidate)
            if record:
                gathered.append(record)
    else:
        gathered = list_isids(connection)

    return {"changed": False, "gathered": gathered}


# ── Entry point ──


def run_module() -> None:
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        supports_check_mode=True,
    )

    # ── Reject old flat-parameter usage ──
    config = module.params.get("config")
    state = module.params["state"]

    flat_used = any(module.params.get(p) is not None for p in _OLD_FLAT_PARAMS)
    if flat_used:
        module.fail_json(
            msg="Flat parameters (isid, cvlan, name, isid_type) are no longer supported. "
            "Use 'config: list' instead. Example: config: [{isid: 500, cvlan: 500, name: Campus-500}]"
        )

    # ── Validate config required for non-gathered states ──
    if state != "gathered" and not config:
        module.fail_json(msg="The 'config' parameter is required when state=%s" % state)

    try:
        connection = Connection(module._socket_path)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc))

    try:
        if state == "gathered":
            result = handle_gathered(module, connection)
        elif state == "merged":
            result = handle_merged(config, connection, module.check_mode)
        elif state == "replaced":
            result = handle_replaced(config, connection, module.check_mode)
        elif state == "overridden":
            result = handle_overridden(config, connection, module.check_mode)
            # Surface skipped ISIDs as Ansible warnings so the user
            # sees them without the task failing.
            for skip in result.get("skipped_isids", []):
                module.warn(
                    "Overridden: ISID %s could not be deleted and was skipped: %s"
                    % (skip.get("isid"), skip.get("reason", "unknown"))
                )
        elif state == "deleted":
            result = handle_deleted(config, connection, module.check_mode)
        else:
            module.fail_json(msg="Unknown state: %s" % state)
            return

        module.exit_json(**result)
    except ConnectionError as exc:
        module.fail_json(msg=to_text(exc), code=getattr(exc, "code", None))
    except FeFabricL2Error as err:
        module.fail_json(**err.to_fail_kwargs())


def main() -> None:
    run_module()


if __name__ == "__main__":
    main()
