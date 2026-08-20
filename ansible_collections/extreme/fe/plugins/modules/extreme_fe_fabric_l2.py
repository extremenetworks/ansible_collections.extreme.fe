"""Ansible module to manage ExtremeNetworks Fabric Engine ISIDs via HTTPAPI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import quote

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import Connection, ConnectionError

DOCUMENTATION = r"""
module: extreme_fe_fabric_l2
short_description: Manage Fabric Engine ISIDs on ExtremeNetworks switches
version_added: "1.0.0"
description:
    - "Manage Layer 2 ISIDs (service instance identifiers) on ExtremeNetworks Fabric Engine switches using the custom C(extreme_fe) HTTPAPI plugin."
    - Supports provisioning CVLAN-backed ISIDs, Switched UNI (C(SUNI)) and Transparent UNI (C(TUNI)) Flex-UNI services, updating friendly names, gathering existing definitions, and removing bindings.
    - Uses the standard Ansible resource module C(config) list pattern for multi-resource management.
author:
    - ExtremeNetworks Networking Automation Team
notes:
    - "Requires the C(ansible.netcommon) collection and the C(extreme_fe) HTTPAPI plugin shipped with this project."
    - "In C(merged) state an omitted attribute is left untouched on the device, while an explicitly supplied empty list clears the corresponding membership. Use C(replaced) to enforce an exact state."
    - "An entry may only carry the attributes of its own C(isid_type) — C(endpoints) for C(SUNI), C(ports) and C(lags) for C(TUNI), C(cvlan) for C(CVLAN). Mixing them fails the task rather than silently ignoring the value."
    - "Operating on an ISID that already exists with a different C(isid_type) fails the task; the existing service is never renamed or reconfigured."
    - "For the untagged endpoint the device keeps a separate record per interface kind, so one c-vid 4096 endpoint holding a port and a LAG is returned as two records. The module presents them as the single endpoint it accepts as input, unioning the membership."
    - "A SUNI endpoint only exists while it binds at least one port or LAG. Creating one without either fails the task, and clearing the last member of an existing endpoint removes that endpoint."
    - "Removing the last endpoint does NOT remove the I-SID. The SUNI record stays on the device with an empty endpoint list, and a later C(merged) run can add endpoints back to it. Use C(state=deleted) with C(isid_type=SUNI) to remove the I-SID itself. C(replaced) and C(overridden) delete and rebuild the service, so they do remove an I-SID that ends up unlisted."
    - "Reaching a C(replaced) or C(overridden) SUNI state requires deleting and rebuilding the service, because the API has no per-endpoint delete. The module skips that rebuild entirely when the device already matches, so a converged run neither reports a change nor disrupts traffic."
    - "SUNI LAG endpoints require Flex-UNI to be enabled on the LAG first — see the C(flex_uni) option of M(extreme.fe.extreme_fe_lag)."
    - "Fabric Engine does not support patching a SUNI endpoint's C(cvid); C(replaced) deletes and rebuilds the SUNI to reach the requested endpoint set."
    - Supports Ansible check mode for configuration states.
requirements:
    - ansible.netcommon
options:
  state:
    description:
      - Desired module operation.
      - "C(merged) ensures the supplied attributes are merged with the running configuration and creates the ISID when missing."
      - "C(replaced) treats the supplied values as authoritative for the targeted ISID. When C(name) is omitted it resets to the device default C(ISID-<isid>); C(cvlan) is left unchanged if omitted."
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
          - ISID service type.
          - "C(CVLAN) binds the ISID to a platform VLAN and uses C(cvlan)."
          - "C(SUNI) is a Switched UNI (Flex-UNI) service and uses C(endpoints)."
          - "C(TUNI) is a Transparent UNI service and uses the flat C(ports) and C(lags)."
        type: str
        choices: [CVLAN, SUNI, TUNI]
        default: CVLAN
      name:
        description:
          - Friendly name to associate with the ISID.
          - "When C(state) is C(replaced) or C(overridden) and C(name) is omitted, the name resets to the device default C(ISID-<isid>) — an unnamed ISID is named after itself, so this is the factory state rather than a blank name. This applies to all three ISID types."
          - "In C(merged) state an omitted C(name) leaves the existing name unchanged."
        type: str
      cvlan:
        description:
          - CVLAN identifier to bind to the ISID when C(isid_type) is C(CVLAN).
          - Required when creating a new ISID.
        type: int
      endpoints:
        description:
          - "C-VID endpoint bindings for a Switched UNI. Only used when C(isid_type) is C(SUNI)."
          - "In C(merged) state only the endpoints listed here are touched; endpoints on the device that are not listed are left alone."
          - "In C(replaced) and C(overridden) states this list is authoritative — the SUNI is deleted and rebuilt from exactly these endpoints."
        type: list
        elements: dict
        suboptions:
          cvid:
            description:
              - "Customer VLAN ID of the endpoint. C(4095) is not used; C(4096) is reserved for untagged traffic."
            type: int
            required: true
          ports:
            description:
              - Port members bound to this endpoint, for example C(1:10).
              - "In C(merged) state, omitting this leaves the existing port membership untouched; supplying an empty list clears it."
              - "A new endpoint must bind at least one port or LAG — the device rejects an endpoint with no interface mapping."
              - "Clearing the last port and LAG of an existing endpoint removes the endpoint itself. Removing the last endpoint leaves the SUNI I-SID in place with no endpoints — use C(state=deleted) with C(isid_type=SUNI) to remove the I-SID record."
            type: list
            elements: str
          lags:
            description:
              - LAG (MLT) identifiers bound to this endpoint.
              - "Each LAG must already have Flex-UNI enabled — see the C(flex_uni) option of M(extreme.fe.extreme_fe_lag)."
              - "In C(merged) state, omitting this leaves the existing LAG membership untouched; supplying an empty list clears it."
              - "A new endpoint must bind at least one port or LAG."
            type: list
            elements: str
          bpdu_enabled:
            description:
              - Forward BPDUs on this endpoint.
              - "The device only accepts this on the untagged endpoint (C(cvid) C(4096)); enabling it on any other C(cvid) fails the task."
              - "Stored per interface member, so the module applies it to each port and LAG of the endpoint individually and only where it differs."
              - "Reported as C(true) only when every member of the endpoint has it enabled. A port or LAG added to an endpoint arrives with BPDU disabled, so it can read as C(false) until the next run re-applies it."
              - "In C(merged) state, omitting this leaves the current setting untouched. Defaults to C(false) when a new endpoint is created."
            type: bool
      ports:
        description:
          - Port members of a Transparent UNI. Only used when C(isid_type) is C(TUNI).
          - "In C(merged) state, omitting this leaves the existing port membership untouched; supplying an empty list clears it."
        type: list
        elements: str
      lags:
        description:
          - LAG (MLT) identifiers of a Transparent UNI. Only used when C(isid_type) is C(TUNI).
          - "In C(merged) state, omitting this leaves the existing LAG membership untouched; supplying an empty list clears it."
        type: list
        elements: str
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
  description: ISIDs that overridden could not delete (e.g. Auto-Sense FA ISIDs).
  returned: when state == overridden
  type: list
  elements: dict
  sample:
    - isid: 15999999
      reason: "Cannot change the associated vlan of an Auto-Sense FA i-sid"
gathered:
  description:
    - List of ISID entries discovered from the device.
    - "Type-specific membership is flattened into the same field names the module accepts as input: C(endpoints) for SUNI, C(ports) and C(lags) for TUNI, C(platformVlanId) for CVLAN."
  returned: when state == gathered
  type: list
  sample:
    - isid: 500
      name: Campus-500
      type: CVLAN
      platformVlanId: 500
    - isid: 8001
      name: FlexUNI
      type: SUNI
      endpoints:
        - cvid: 4096
          ports: ["1:12"]
          lags: ["50"]
          bpdu_enabled: true
    - isid: 9001
      name: Transparent
      type: TUNI
      ports: ["1:13", "1:14"]
      lags: ["51"]
"""


# ── Flat-parameter names that were used in the old API ──
_OLD_FLAT_PARAMS = frozenset({"isid", "isid_type", "cvlan", "name"})

ARGUMENT_SPEC: dict[str, Any] = {
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
            "isid_type": {
                "type": "str",
                "choices": ["CVLAN", "SUNI", "TUNI"],
                "default": "CVLAN",
            },
            "name": {"type": "str"},
            "cvlan": {"type": "int"},
            # SUNI: list of cvid-based endpoint bindings
            "endpoints": {
                "type": "list",
                "elements": "dict",
                "options": {
                    "cvid": {"type": "int", "required": True},
                    # No defaults on these three: in merged state an omitted
                    # value (None) means "leave untouched", which an argspec
                    # default would make indistinguishable from an explicit
                    # request to clear/disable.
                    "ports": {"type": "list", "elements": "str"},
                    "lags": {"type": "list", "elements": "str"},
                    "bpdu_enabled": {"type": "bool"},
                },
            },
            # TUNI: flat port/lag membership (no cvid layer)
            "ports": {"type": "list", "elements": "str"},
            "lags": {"type": "list", "elements": "str"},
        },
    },
    "gather_filter": {"type": "list", "elements": "int"},
    # Legacy flat params — rejected with a clear error
    "isid": {"type": "int"},
    "isid_type": {"type": "str", "choices": ["CVLAN", "SUNI", "TUNI"]},
    "name": {"type": "str"},
    "cvlan": {"type": "int"},
}

ISID_BASE_PATH = "/v0/configuration/spbm/l2/isid"

# cvid 4096 is reserved for untagged traffic; it is the only endpoint on which
# the device accepts BPDU forwarding (see the SUNI BPDU PATCH in openapi.yml).
SUNI_UNTAGGED_CVID = 4096

# Membership attributes that only apply to one ISID type. 'name' is common to
# all three and 'cvlan' is validated separately (it is required to create a
# CVLAN ISID), so neither appears here.
_TYPE_ONLY_FIELDS = ("endpoints", "ports", "lags")
_ALLOWED_FIELDS = {
    "CVLAN": frozenset(),
    "SUNI": frozenset({"endpoints"}),
    "TUNI": frozenset({"ports", "lags"}),
}
_TYPE_FIELD_HINT = {
    "CVLAN": "CVLAN ISIDs take 'cvlan' and 'name' only.",
    "SUNI": "SUNI ISIDs take 'endpoints' (cvid + ports/lags/bpdu_enabled).",
    "TUNI": "TUNI ISIDs take flat 'ports' and 'lags'.",
}


# ── Exception ──


class FeFabricL2Error(Exception):
    """Base exception for the Fabric L2 module."""

    def __init__(
        self, message: str, *, details: dict[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_fail_kwargs(self) -> dict[str, object]:
        data: dict[str, object] = {"msg": to_text(self)}
        if self.details:
            data["details"] = self.details
        return data


# ── REST helpers ──


def _is_not_found_response(payload: object | None) -> bool:
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


def _extract_cvlan(data: dict[str, object] | None) -> int | None:
    if not isinstance(data, dict):
        return None
    interfaces = data.get("interfaces")
    platform_vlan: object | None = None
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


def _index_suni_endpoints(raw: object) -> dict[Any, dict[str, Any]]:
    """Group the SUNI endpoint rows of a GET response by c-vid.

    A c-vid does not identify a single device record. For the untagged
    endpoint the device keeps one record per interface kind, so a c-vid 4096
    endpoint carrying both a port and a LAG comes back as two rows that both
    report ``cvid: 4096``. Union their membership, and keep BPDU per member
    because that is how the device stores it.
    """
    index: dict[Any, dict[str, Any]] = {}
    if not isinstance(raw, list):
        return index
    for row in raw:
        if not isinstance(row, dict) or row.get("cvid") is None:
            continue
        entry = index.setdefault(
            row["cvid"], {"ports": set(), "lags": set(), "bpdu": {}}
        )
        bpdu = bool(row.get("bpduEnabled", False))
        for port in row.get("portMembers") or []:
            entry["ports"].add(port)
            entry["bpdu"][("PORT", port)] = bpdu
        for lag in row.get("lagIds") or []:
            entry["lags"].add(lag)
            entry["bpdu"][("LAG", lag)] = bpdu
    return index


def _normalize_endpoint_list(raw: object) -> list[dict[str, object]]:
    """Normalise the SUNI endpoint list from a GET response.

    Rows sharing a c-vid are presented as the single endpoint the module
    accepts as input. ``bpdu_enabled`` is true only when every member of the
    endpoint has it enabled — it is a per-member setting on the device.
    """
    index = _index_suni_endpoints(raw)
    # Sorted by c-vid rather than left in device response order, so gathered
    # and after output is stable across runs and diffs stay quiet.
    return [
        {
            "cvid": cvid,
            "ports": sorted(index[cvid]["ports"]),
            "lags": sorted(index[cvid]["lags"]),
            "bpdu_enabled": (bool(index[cvid]["bpdu"])
                             and all(index[cvid]["bpdu"].values())),
        }
        for cvid in sorted(index, key=lambda c: (c is None, c))
    ]


def _record_isid_type(data: dict[str, object] | None) -> str:
    """Best-effort ISID type of a device record ('' when unknown)."""
    if not isinstance(data, dict):
        return ""
    return str(data.get("type") or data.get("isidType") or "").upper()


def _normalize_isid_record(
    data: dict[str, object] | None, isid: int | None = None
) -> dict[str, object] | None:
    """Normalise an API record so ``isid`` and ``platformVlanId`` are top-level.

    The device returns the type-specific membership under ``interfaces`` (a
    discriminated union keyed on the ISID type). Flatten it into the same
    field names the module accepts as input, so ``gathered`` round-trips
    instead of dropping every SUNI endpoint and TUNI member.
    """
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
        isid_type = _record_isid_type(out)
        if isid_type == "SUNI" and "endpoints" not in out:
            out["endpoints"] = _normalize_endpoint_list(interfaces.get("endpoints"))
        elif isid_type == "TUNI":
            if "ports" not in out:
                out["ports"] = sorted(interfaces.get("portMembers") or [])
            if "lags" not in out:
                out["lags"] = sorted(interfaces.get("lagIds") or [])
    return out


def _assert_isid_type(
    before_raw: dict[str, object] | None, isid: int, expected: str
) -> None:
    """Refuse to operate on an ISID that exists with a different type.

    Without this a mistyped ``isid_type`` renames (and then half-configures)
    an unrelated service before the device rejects the follow-up call.
    """
    existing = _record_isid_type(before_raw)
    if existing and existing != expected:
        raise FeFabricL2Error(
            "ISID %d exists with type %s, which does not match requested %s"
            % (isid, existing, expected)
        )


def _endpoints_fingerprint(endpoints: object) -> list[tuple]:
    """Order-independent comparable form of a SUNI endpoint list."""
    out = []
    if isinstance(endpoints, list):
        for ep in endpoints:
            if not isinstance(ep, dict):
                continue
            out.append((
                ep.get("cvid"),
                tuple(sorted(ep.get("ports") or [])),
                tuple(sorted(ep.get("lags") or [])),
                bool(ep.get("bpdu_enabled")),
            ))
    return sorted(out, key=lambda item: (item[0] is None, item[0]))


def _isid_path(isid: int) -> str:
    return "/".join([ISID_BASE_PATH, quote(str(isid), safe="")])


def _cvlan_delete_path(isid: int, cvlan: int) -> str:
    return "/".join(
        [ISID_BASE_PATH, quote(str(isid), safe=""), "cvlan", quote(str(cvlan), safe="")]
    )


def _ensure_list(payload: object | None) -> list[dict[str, object]]:
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
            combined: list[dict[str, object]] = []
            for tk in type_keys:
                sub = payload.get(tk)
                if isinstance(sub, list):
                    combined.extend(item for item in sub if isinstance(item, dict))
            return combined
        return [payload]
    return []


# ── Device I/O ──


def get_isid(connection: Connection, isid: int) -> dict[str, object] | None:
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


def list_isids(connection: Connection) -> list[dict[str, object]]:
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


def _list_cvlan_isids_raw(connection: Connection) -> list[dict[str, object]]:
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
    cvlan: int | None,
    name: str | None,
) -> None:
    payload: dict[str, object] = {"isidType": isid_type, "isid": isid}
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


# ── SUNI REST helpers ──


def _suni_base_path(isid: int) -> str:
    return "%s/%s/suni" % (ISID_BASE_PATH, quote(str(isid), safe=""))


def add_suni_endpoint(
    connection: Connection, isid: int, cvid: int,
    ports: list[str] | None, lags: list[str] | None,
    bpdu_enabled: bool = False,
) -> None:
    """POST /v0/configuration/spbm/l2/isid/{isid}/suni"""
    payload: dict[str, object] = {"cvid": cvid, "bpduEnabled": bpdu_enabled}
    if ports:
        payload["portIds"] = ports
    if lags:
        payload["lagIds"] = lags
    connection.send_request(payload, path=_suni_base_path(isid), method="POST")


def update_suni_ports(
    connection: Connection, isid: int, cvid: int, ports: list[str],
) -> None:
    """PUT /v0/configuration/spbm/l2/isid/{isid}/suni/cvid/{cvid}/ports"""
    path = "%s/cvid/%s/ports" % (_suni_base_path(isid), quote(str(cvid), safe=""))
    connection.send_request(ports, path=path, method="PUT")


def update_suni_lags(
    connection: Connection, isid: int, cvid: int, lags: list[str],
) -> None:
    """PUT /v0/configuration/spbm/l2/isid/{isid}/suni/cvid/{cvid}/lag"""
    path = "%s/cvid/%s/lag" % (_suni_base_path(isid), quote(str(cvid), safe=""))
    connection.send_request(lags, path=path, method="PUT")


def update_suni_bpdu(
    connection: Connection, isid: int, cvid: int,
    iftype: str, ifname: str, bpdu_enabled: bool,
) -> None:
    """PATCH /v0/configuration/spbm/l2/isid/{isid}/suni/cvid/{cvid}/type/{iftype}/name/{ifname}

    BPDU is stored per interface member, not per endpoint, so the caller has
    to walk every port and LAG of the endpoint. The device only accepts this
    for cvid 4096 (untagged) on PORT and LAG interfaces.
    """
    path = "%s/cvid/%s/type/%s/name/%s" % (
        _suni_base_path(isid),
        quote(str(cvid), safe=""),
        quote(iftype, safe=""),
        quote(str(ifname), safe=""),
    )
    connection.send_request({"bpduEnabled": bpdu_enabled}, path=path, method="PATCH")


def delete_suni(connection: Connection, isid: int) -> None:
    """DELETE /v0/configuration/spbm/l2/isid/{isid}/suni"""
    connection.send_request(None, path=_suni_base_path(isid), method="DELETE")


def get_suni(connection: Connection, isid: int) -> dict[str, object] | None:
    """GET /v0/configuration/spbm/l2/isid/{isid}/suni"""
    try:
        data = connection.send_request(None, path=_suni_base_path(isid), method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        return data
    return None


def list_all_suni(connection: Connection) -> list[dict[str, object]]:
    """GET /v0/configuration/spbm/l2/isid/suni"""
    path = ISID_BASE_PATH + "/suni"
    try:
        data = connection.send_request(None, path=path, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    if data is None or _is_not_found_response(data):
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


# ── TUNI REST helpers ──


def _tuni_base_path(isid: int) -> str:
    return "%s/%s/tuni" % (ISID_BASE_PATH, quote(str(isid), safe=""))


def update_tuni_ports(
    connection: Connection, isid: int, ports: list[str],
) -> None:
    """PUT /v0/configuration/spbm/l2/isid/{isid}/tuni/ports"""
    path = _tuni_base_path(isid) + "/ports"
    connection.send_request(ports, path=path, method="PUT")


def update_tuni_lags(
    connection: Connection, isid: int, lags: list[str],
) -> None:
    """PUT /v0/configuration/spbm/l2/isid/{isid}/tuni/lag"""
    path = _tuni_base_path(isid) + "/lag"
    connection.send_request(lags, path=path, method="PUT")


def delete_tuni(connection: Connection, isid: int) -> None:
    """DELETE /v0/configuration/spbm/l2/isid/{isid}/tuni"""
    connection.send_request(None, path=_tuni_base_path(isid), method="DELETE")


def get_tuni(connection: Connection, isid: int) -> dict[str, object] | None:
    """GET /v0/configuration/spbm/l2/isid/{isid}/tuni"""
    try:
        data = connection.send_request(None, path=_tuni_base_path(isid), method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return None
        raise
    if data is None or _is_not_found_response(data):
        return None
    if isinstance(data, dict):
        return data
    return None


def list_all_tuni(connection: Connection) -> list[dict[str, object]]:
    """GET /v0/configuration/spbm/l2/isid/tuni"""
    path = ISID_BASE_PATH + "/tuni"
    try:
        data = connection.send_request(None, path=path, method="GET")
    except ConnectionError as exc:
        if getattr(exc, "code", None) == 404:
            return []
        raise
    if data is None or _is_not_found_response(data):
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


# ── Simulation helpers ──


def _simulate_after_creation(
    isid: int, isid_type: str, cvlan: int | None, name: str | None
) -> dict[str, object]:
    simulated: dict[str, object] = {"isid": isid, "isidType": isid_type}
    if cvlan is not None:
        simulated["platformVlanId"] = cvlan
    if name is not None:
        simulated["name"] = name
    return simulated


# ── Per-entry processing ──


def _process_entry_merged(
    entry: dict[str, Any], connection: Connection, check_mode: bool
) -> dict[str, object]:
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
    entry: dict[str, Any], connection: Connection, check_mode: bool
) -> dict[str, object]:
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
    entry: dict[str, Any],
    before: dict[str, object],
    before_data: dict[str, object] | None,
    connection: Connection,
    check_mode: bool,
    *,
    clear_name_on_omit: bool,
) -> dict[str, object]:
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
    target_name: str | None
    if clear_name_on_omit and desired_name is None:
        # Reset to the device's factory default, not an empty string — an
        # unnamed ISID is named after itself, so "" would never converge.
        target_name = _default_isid_name(isid)
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
    entry: dict[str, Any], connection: Connection, check_mode: bool
) -> dict[str, object]:
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


# ── SUNI entry processing ──


def _normalize_suni_state(data: dict[str, object]) -> dict[str, object]:
    """Normalize a SUNI GET response into a consistent output dict."""
    return {
        "isid_type": "SUNI",
        "name": data.get("name"),
        "endpoints": _normalize_endpoint_list(data.get("endpoints")),
    }


def _validate_suni_bpdu(isid: int, cvid: int, raw_bpdu: bool | None) -> None:
    """The device only accepts BPDU forwarding on the untagged endpoint."""
    if raw_bpdu and cvid != SUNI_UNTAGGED_CVID:
        raise FeFabricL2Error(
            "bpdu_enabled can only be enabled on the untagged endpoint "
            "(cvid %d) — ISID %d cvid %d does not qualify"
            % (SUNI_UNTAGGED_CVID, isid, cvid)
        )


def _default_isid_name(isid: int) -> str:
    """Factory default name: the device names an unnamed ISID 'ISID-<isid>'.

    Mirrors ``_default_lag_name`` in the LAG module, where a bare MLT is
    'MLT-<id>'. Creating an ISID without a name does not leave it blank — the
    device derives this one — so it is the value an omitted name resets to.
    """
    return f"ISID-{isid}"


def _replaced_target_name(desired_name: str | None, isid: int) -> str:
    """The name an ISID should carry after replaced/overridden.

    These states treat the supplied config as authoritative, so an omitted
    name resets to the device's factory default rather than staying put.
    """
    return desired_name if desired_name is not None else _default_isid_name(isid)


def _validate_new_endpoint_members(isid: int, ep: dict[str, Any]) -> None:
    """A new SUNI endpoint must bind at least one port or LAG.

    The device refuses a create with no interface mapping ("Cannot create ISID
    of type SUNI without interface mapping in payload"). The OpenAPI schema
    declares no required properties, so this is only discoverable at runtime —
    catch it here rather than surfacing the raw device error.
    """
    if not (ep.get("ports") or ep.get("lags")):
        raise FeFabricL2Error(
            "Creating SUNI endpoint cvid %s on ISID %d requires at least one "
            "port or lag; the device rejects an endpoint with no interface "
            "mapping" % (ep.get("cvid"), isid)
        )


def _simulate_suni_after(
    isid: int,
    before_state: dict[str, object] | None,
    desired_name: str | None,
    endpoints: list[dict[str, Any]],
) -> dict[str, object]:
    """Project the merged SUNI result for check mode (no device writes)."""
    merged: dict[int, dict[str, object]] = {
        ep["cvid"]: dict(ep) for ep in ((before_state or {}).get("endpoints") or [])
    }
    for ep in endpoints:
        cvid = ep["cvid"]
        cur = merged.get(cvid)
        if cur is None:
            cur = {"cvid": cvid, "ports": [], "lags": [], "bpdu_enabled": False}
        # Mirror the merged rule: only supplied attributes move.
        if ep.get("ports") is not None:
            cur["ports"] = sorted(ep["ports"])
        if ep.get("lags") is not None:
            cur["lags"] = sorted(ep["lags"])
        if ep.get("bpdu_enabled") is not None:
            cur["bpdu_enabled"] = bool(ep["bpdu_enabled"])
        merged[cvid] = cur
    # An ISID created without a name is not left blank: the device names it
    # after itself. Mirror that, or --check reports name: null for something
    # a real run would call ISID-<isid>.
    if desired_name is not None:
        name = desired_name
    elif before_state is None:
        name = _default_isid_name(isid)
    else:
        name = before_state.get("name")
    return {"isid_type": "SUNI", "name": name,
            "endpoints": [merged[cvid] for cvid in sorted(merged)]}


def _process_suni_merged(
    entry: dict[str, Any], connection: Connection, check_mode: bool,
) -> dict[str, object]:
    """Merged SUNI: create ISID if missing, then add/update endpoints."""
    isid = entry["isid"]
    desired_name = entry.get("name")
    endpoints = entry.get("endpoints") or []

    before_raw = get_isid(connection, isid)
    _assert_isid_type(before_raw, isid, "SUNI")
    suni_data = get_suni(connection, isid)

    # Existing endpoints, grouped by c-vid (several device rows can share one)
    existing_cvids = _index_suni_endpoints((suni_data or {}).get("endpoints"))

    # Validate every endpoint up front, before the first write, so an invalid
    # entry cannot leave the ISID half-configured (or newly created and empty).
    for ep in endpoints:
        _validate_suni_bpdu(isid, ep["cvid"], ep.get("bpdu_enabled"))
        if ep["cvid"] not in existing_cvids:
            _validate_new_endpoint_members(isid, ep)

    if before_raw is None:
        # ISID does not exist — create it
        if not check_mode:
            create_isid(connection, isid=isid, isid_type="SUNI",
                        cvlan=None, name=desired_name)
        before_state = None
    else:
        before_state = _normalize_suni_state(suni_data) if suni_data else {"isid_type": "SUNI", "endpoints": []}

    # Every difference is evaluated regardless of check mode — only the write
    # itself is gated — so --check reports the same 'changed' as a real run.
    change_made = before_raw is None

    # Update name if needed
    if desired_name is not None and before_raw is not None:
        current_name = before_raw.get("name") or ""
        if current_name != desired_name:
            change_made = True
            if not check_mode:
                update_isid_name(connection, isid=isid, name=desired_name)

    # Process each endpoint
    for ep in endpoints:
        cvid = ep["cvid"]
        # Raw values distinguish "omitted" (None) from an explicit empty list
        # or explicit false. Merged leaves omitted attributes untouched.
        raw_ports = ep.get("ports")
        raw_lags = ep.get("lags")
        raw_bpdu = ep.get("bpdu_enabled")
        desired_ports = sorted(raw_ports or [])
        desired_lags = sorted(raw_lags or [])

        if cvid not in existing_cvids:
            change_made = True
            if not check_mode:
                add_suni_endpoint(connection, isid, cvid,
                                  desired_ports or None, desired_lags or None,
                                  bool(raw_bpdu))
            continue

        cur = existing_cvids[cvid]
        cur_ports = sorted(cur["ports"])
        cur_lags = sorted(cur["lags"])
        if raw_ports is not None and desired_ports != cur_ports:
            change_made = True
            if not check_mode:
                update_suni_ports(connection, isid, cvid, desired_ports)
        if raw_lags is not None and desired_lags != cur_lags:
            change_made = True
            if not check_mode:
                update_suni_lags(connection, isid, cvid, desired_lags)

        # BPDU lives per interface member, so reconcile it member by member
        # against the membership this run leaves behind. Members disagreeing
        # with each other is a normal intermediate state — adding a port or
        # LAG brings it in at the device default of disabled.
        if raw_bpdu is not None:
            desired_bpdu = bool(raw_bpdu)
            final_ports = desired_ports if raw_ports is not None else cur_ports
            final_lags = desired_lags if raw_lags is not None else cur_lags
            members = ([("PORT", p) for p in final_ports]
                       + [("LAG", lag) for lag in final_lags])
            stale = [m for m in members if cur["bpdu"].get(m, False) != desired_bpdu]
            if stale:
                change_made = True
                if not check_mode:
                    for iftype, ifname in stale:
                        update_suni_bpdu(connection, isid, cvid,
                                         iftype, ifname, desired_bpdu)

    if check_mode:
        after_state = _simulate_suni_after(isid, before_state, desired_name, endpoints)
    else:
        after_data = get_suni(connection, isid)
        after_state = _normalize_suni_state(after_data) if after_data else None
    return {"isid": isid, "before": before_state, "after": after_state,
            "changed": change_made}


def _process_suni_replaced(
    entry: dict[str, Any], connection: Connection, check_mode: bool,
) -> dict[str, object]:
    """Replaced SUNI: delete and recreate with exact desired state."""
    isid = entry["isid"]
    desired_name = entry.get("name")
    endpoints = entry.get("endpoints") or []

    before_raw = get_isid(connection, isid)
    _assert_isid_type(before_raw, isid, "SUNI")
    suni_data = get_suni(connection, isid)
    before_state = None
    if suni_data:
        before_state = _normalize_suni_state(suni_data)

    # replaced rebuilds every endpoint, so all of them take the create path.
    for ep in endpoints:
        _validate_suni_bpdu(isid, ep["cvid"], ep.get("bpdu_enabled"))
        _validate_new_endpoint_members(isid, ep)

    # Reaching the desired state means deleting the SUNI and rebuilding it —
    # the API has no per-endpoint delete. That drops every port and LAG of a
    # live service, so never do it when the device already matches.
    target_name = _replaced_target_name(desired_name, isid)
    if before_state is not None:
        name_matches = ((before_raw or {}).get("name") or "") == target_name
        if (name_matches
                and _endpoints_fingerprint(before_state.get("endpoints"))
                == _endpoints_fingerprint(endpoints)):
            return {"isid": isid, "before": before_state,
                    "after": before_state, "changed": False}

    if check_mode:
        # Replaced is authoritative: omitted attributes land on their defaults.
        after_state = {
            "isid_type": "SUNI",
            "name": target_name,
            "endpoints": [{
                "cvid": ep["cvid"],
                "ports": sorted(ep.get("ports") or []),
                "lags": sorted(ep.get("lags") or []),
                "bpdu_enabled": bool(ep.get("bpdu_enabled")),
            } for ep in sorted(endpoints, key=lambda e: e["cvid"])],
        }
        return {"isid": isid, "before": before_state, "after": after_state, "changed": True}

    # Delete existing SUNI instance if present, then recreate.
    # Deleting the SUNI removes the whole ISID record on the device, so
    # re-read it afterwards — the pre-delete snapshot would wrongly send
    # us down the "patch the name" branch against an ISID that is gone.
    if suni_data:
        delete_suni(connection, isid)
        before_raw = get_isid(connection, isid)
    if before_raw is None:
        # target_name is the requested name, or the device's factory default
        # ISID-<isid> when none was supplied, so the create already lands on
        # the right name and no follow-up PATCH is needed.
        create_isid(connection, isid=isid, isid_type="SUNI", cvlan=None, name=target_name)
    elif (before_raw.get("name") or "") != target_name:
        update_isid_name(connection, isid=isid, name=target_name)

    # Recreate all endpoints
    for ep in endpoints:
        add_suni_endpoint(connection, isid, ep["cvid"],
                          ep.get("ports") or None, ep.get("lags") or None,
                          bool(ep.get("bpdu_enabled")))

    after_data = get_suni(connection, isid)
    after_state = _normalize_suni_state(after_data) if after_data else None
    return {"isid": isid, "before": before_state, "after": after_state, "changed": True}


def _process_suni_deleted(
    entry: dict[str, Any], connection: Connection, check_mode: bool,
) -> dict[str, object]:
    """Delete a SUNI ISID instance."""
    isid = entry["isid"]
    suni_data = get_suni(connection, isid)
    before_state = _normalize_suni_state(suni_data) if suni_data else None

    if suni_data is None:
        return {"isid": isid, "before": None, "after": None, "changed": False}
    if check_mode:
        return {"isid": isid, "before": before_state, "after": None, "changed": True}

    delete_suni(connection, isid)
    return {"isid": isid, "before": before_state, "after": None, "changed": True}


# ── TUNI entry processing ──


def _normalize_tuni_state(data: dict[str, object]) -> dict[str, object]:
    """Normalize a TUNI GET response into a consistent output dict."""
    out: dict[str, object] = {"isid_type": "TUNI"}
    out["name"] = data.get("name")
    out["ports"] = sorted(data.get("portMembers") or [])
    out["lags"] = sorted(data.get("lagIds") or [])
    return out


def _process_tuni_merged(
    entry: dict[str, Any], connection: Connection, check_mode: bool,
) -> dict[str, object]:
    """Merged TUNI: create ISID if missing, then set ports/lags."""
    isid = entry["isid"]
    desired_name = entry.get("name")
    # Raw values distinguish "omitted" (None) from an explicit empty list.
    raw_ports = entry.get("ports")
    raw_lags = entry.get("lags")
    desired_ports = sorted(raw_ports or [])
    desired_lags = sorted(raw_lags or [])

    before_raw = get_isid(connection, isid)
    _assert_isid_type(before_raw, isid, "TUNI")
    tuni_data = get_tuni(connection, isid)

    if before_raw is None:
        before_state = None
        if not check_mode:
            create_isid(connection, isid=isid, isid_type="TUNI",
                        cvlan=None, name=desired_name)
    else:
        before_state = _normalize_tuni_state(tuni_data) if tuni_data else {"isid_type": "TUNI", "ports": [], "lags": []}

    # Every difference is evaluated regardless of check mode — only the write
    # itself is gated — so --check reports the same 'changed' as a real run.
    change_made = before_raw is None

    if desired_name is not None and before_raw is not None:
        if (before_raw.get("name") or "") != desired_name:
            change_made = True
            if not check_mode:
                update_isid_name(connection, isid=isid, name=desired_name)

    cur_ports = sorted((tuni_data or {}).get("portMembers") or [])
    cur_lags = sorted((tuni_data or {}).get("lagIds") or [])
    # merged: omitted (None) leaves membership untouched; an explicit [] is
    # an intentional clear.
    if raw_ports is not None and desired_ports != cur_ports:
        change_made = True
        if not check_mode:
            update_tuni_ports(connection, isid, desired_ports)
    if raw_lags is not None and desired_lags != cur_lags:
        change_made = True
        if not check_mode:
            update_tuni_lags(connection, isid, desired_lags)

    if check_mode:
        after_state = {
            "isid_type": "TUNI",
            # A newly created ISID is named after itself by the device.
            "name": (desired_name if desired_name is not None
                     else (before_raw or {}).get("name")
                     if before_raw is not None else _default_isid_name(isid)),
            "ports": desired_ports if raw_ports is not None else cur_ports,
            "lags": desired_lags if raw_lags is not None else cur_lags,
        }
    else:
        after_data = get_tuni(connection, isid)
        after_state = _normalize_tuni_state(after_data) if after_data else None
    return {"isid": isid, "before": before_state, "after": after_state,
            "changed": change_made}


def _process_tuni_replaced(
    entry: dict[str, Any], connection: Connection, check_mode: bool,
) -> dict[str, object]:
    """Replaced TUNI: enforce exact ports/lags membership."""
    isid = entry["isid"]
    desired_name = entry.get("name")
    desired_ports = sorted(entry.get("ports") or [])
    desired_lags = sorted(entry.get("lags") or [])

    before_raw = get_isid(connection, isid)
    _assert_isid_type(before_raw, isid, "TUNI")
    tuni_data = get_tuni(connection, isid)
    before_state = _normalize_tuni_state(tuni_data) if tuni_data else None

    # Already in the desired state — report it instead of re-PUTting.
    target_name = _replaced_target_name(desired_name, isid)
    if before_state is not None:
        name_matches = ((before_raw or {}).get("name") or "") == target_name
        if (name_matches
                and (before_state.get("ports") or []) == desired_ports
                and (before_state.get("lags") or []) == desired_lags):
            return {"isid": isid, "before": before_state,
                    "after": before_state, "changed": False}

    if check_mode:
        after_state = {"isid_type": "TUNI", "name": target_name,
                       "ports": desired_ports, "lags": desired_lags}
        return {"isid": isid, "before": before_state, "after": after_state, "changed": True}

    if before_raw is None:
        create_isid(connection, isid=isid, isid_type="TUNI",
                    cvlan=None, name=target_name)
    elif (before_raw.get("name") or "") != target_name:
        update_isid_name(connection, isid=isid, name=target_name)

    # PUT replaces the full membership — authoritative
    update_tuni_ports(connection, isid, desired_ports)
    update_tuni_lags(connection, isid, desired_lags)

    after_data = get_tuni(connection, isid)
    after_state = _normalize_tuni_state(after_data) if after_data else None
    return {"isid": isid, "before": before_state, "after": after_state, "changed": True}


def _process_tuni_deleted(
    entry: dict[str, Any], connection: Connection, check_mode: bool,
) -> dict[str, object]:
    """Delete a TUNI ISID instance."""
    isid = entry["isid"]
    tuni_data = get_tuni(connection, isid)
    before_state = _normalize_tuni_state(tuni_data) if tuni_data else None

    if tuni_data is None:
        return {"isid": isid, "before": None, "after": None, "changed": False}
    if check_mode:
        return {"isid": isid, "before": before_state, "after": None, "changed": True}

    delete_tuni(connection, isid)
    return {"isid": isid, "before": before_state, "after": None, "changed": True}


# ── Unified entry dispatch ──


def _dispatch_entry(
    entry: dict[str, Any], connection: Connection, check_mode: bool, state: str,
) -> dict[str, object]:
    """Route an entry to the correct type-specific handler."""
    isid_type = (entry.get("isid_type") or "CVLAN").upper()
    if isid_type == "SUNI":
        if state == "merged":
            return _process_suni_merged(entry, connection, check_mode)
        if state in ("replaced", "overridden"):
            return _process_suni_replaced(entry, connection, check_mode)
        return _process_suni_deleted(entry, connection, check_mode)
    if isid_type == "TUNI":
        if state == "merged":
            return _process_tuni_merged(entry, connection, check_mode)
        if state in ("replaced", "overridden"):
            return _process_tuni_replaced(entry, connection, check_mode)
        return _process_tuni_deleted(entry, connection, check_mode)
    # CVLAN — use existing handlers
    if state == "merged":
        return _process_entry_merged(entry, connection, check_mode)
    if state in ("replaced", "overridden"):
        return _process_entry_replaced(entry, connection, check_mode)
    return _process_entry_deleted(entry, connection, check_mode)


# ── State handlers ──


def handle_merged(
    config: list[dict[str, Any]], connection: Connection, check_mode: bool
) -> dict[str, object]:
    results = []
    changed = False
    for entry in config:
        result = _dispatch_entry(entry, connection, check_mode, "merged")
        results.append(result)
        if result["changed"]:
            changed = True
    return {"changed": changed, "isids": results}


def handle_replaced(
    config: list[dict[str, Any]], connection: Connection, check_mode: bool
) -> dict[str, object]:
    results = []
    changed = False
    for entry in config:
        result = _dispatch_entry(entry, connection, check_mode, "replaced")
        results.append(result)
        if result["changed"]:
            changed = True
    return {"changed": changed, "isids": results}


def _override_delete_unlisted_cvlan(
    config: list[dict[str, Any]], connection: Connection, check_mode: bool,
    wanted_isids: set,
) -> tuple[bool, list[int], list[dict[str, object]]]:
    """Delete CVLAN ISIDs not in wanted_isids."""
    all_cvlan_isids = _list_cvlan_isids_raw(connection)
    deleted_isids: list[int] = []
    skipped_isids: list[dict[str, object]] = []
    changed = False

    for record in all_cvlan_isids:
        device_isid = record.get("isid")
        if device_isid is None or device_isid in wanted_isids:
            continue
        device_cvlan = _extract_cvlan(record)
        if device_cvlan is None:
            skipped_isids.append({
                "isid": device_isid,
                "reason": "Unable to determine CVLAN binding; cannot delete",
            })
            continue
        if not check_mode:
            try:
                delete_isid(connection, isid=device_isid, cvlan=device_cvlan)
            except ConnectionError as exc:
                skipped_isids.append({"isid": device_isid, "reason": to_text(exc)})
                continue
        deleted_isids.append(device_isid)
        changed = True
    return changed, deleted_isids, skipped_isids


def _override_delete_unlisted_suni(
    connection: Connection, check_mode: bool, wanted_isids: set,
) -> tuple[bool, list[int], list[dict[str, object]]]:
    """Delete SUNI ISIDs not in wanted_isids."""
    all_suni = list_all_suni(connection)
    deleted: list[int] = []
    skipped: list[dict[str, object]] = []
    changed = False
    for record in all_suni:
        device_isid = record.get("isid")
        if device_isid is None or device_isid in wanted_isids:
            continue
        if not check_mode:
            try:
                delete_suni(connection, int(device_isid))
            except ConnectionError as exc:
                # Report it — a silently skipped delete looks like success
                # while the ISID is still on the device.
                skipped.append({"isid": int(device_isid), "reason": to_text(exc)})
                continue
        deleted.append(int(device_isid))
        changed = True
    return changed, deleted, skipped


def _override_delete_unlisted_tuni(
    connection: Connection, check_mode: bool, wanted_isids: set,
) -> tuple[bool, list[int], list[dict[str, object]]]:
    """Delete TUNI ISIDs not in wanted_isids."""
    all_tuni = list_all_tuni(connection)
    deleted: list[int] = []
    skipped: list[dict[str, object]] = []
    changed = False
    for record in all_tuni:
        device_isid = record.get("isid")
        if device_isid is None or device_isid in wanted_isids:
            continue
        if not check_mode:
            try:
                delete_tuni(connection, int(device_isid))
            except ConnectionError as exc:
                skipped.append({"isid": int(device_isid), "reason": to_text(exc)})
                continue
        deleted.append(int(device_isid))
        changed = True
    return changed, deleted, skipped


def handle_overridden(
    config: list[dict[str, Any]], connection: Connection, check_mode: bool
) -> dict[str, object]:
    """Delete unlisted ISIDs (scoped to types in config), then apply replaced."""
    wanted_isids = {e["isid"] for e in config}
    types_in_config = {(e.get("isid_type") or "CVLAN").upper() for e in config}

    deleted_isids: list[int] = []
    skipped_isids: list[dict[str, object]] = []
    changed = False

    # Phase 1: delete unlisted ISIDs — scoped to types present in config
    if "CVLAN" in types_in_config:
        cvlan_changed, cvlan_deleted, cvlan_skipped = _override_delete_unlisted_cvlan(
            config, connection, check_mode, wanted_isids)
        if cvlan_changed:
            changed = True
        deleted_isids.extend(cvlan_deleted)
        skipped_isids.extend(cvlan_skipped)

    if "SUNI" in types_in_config:
        suni_changed, suni_deleted, suni_skipped = _override_delete_unlisted_suni(
            connection, check_mode, wanted_isids)
        if suni_changed:
            changed = True
        deleted_isids.extend(suni_deleted)
        skipped_isids.extend(suni_skipped)

    if "TUNI" in types_in_config:
        tuni_changed, tuni_deleted, tuni_skipped = _override_delete_unlisted_tuni(
            connection, check_mode, wanted_isids)
        if tuni_changed:
            changed = True
        deleted_isids.extend(tuni_deleted)
        skipped_isids.extend(tuni_skipped)

    # Phase 2: apply replaced for each config entry
    results = []
    for entry in config:
        result = _dispatch_entry(entry, connection, check_mode, "overridden")
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
    config: list[dict[str, Any]], connection: Connection, check_mode: bool
) -> dict[str, object]:
    results = []
    changed = False
    for entry in config:
        result = _dispatch_entry(entry, connection, check_mode, "deleted")
        results.append(result)
        if result["changed"]:
            changed = True
    return {"changed": changed, "isids": results}


def handle_gathered(module: AnsibleModule, connection: Connection) -> dict[str, object]:
    gather_filter: list[int] | None = module.params.get("gather_filter")

    gathered: list[dict[str, object]] = []

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

    # ── Reject attributes that do not belong to the entry's ISID type ──
    # Without this, a SUNI entry carrying flat ports/lags (or a TUNI entry
    # carrying endpoints) is silently ignored and the task reports success
    # having configured nothing.
    for entry in config or []:
        entry_type = (entry.get("isid_type") or "CVLAN").upper()
        wrong = [
            name for name in _TYPE_ONLY_FIELDS
            if entry.get(name) is not None and name not in _ALLOWED_FIELDS[entry_type]
        ]
        if wrong:
            module.fail_json(
                msg="ISID %s is type %s; %s not supported for this type. %s"
                % (entry.get("isid"), entry_type,
                   " and ".join("'%s' is" % w for w in sorted(wrong)),
                   _TYPE_FIELD_HINT[entry_type])
            )

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
