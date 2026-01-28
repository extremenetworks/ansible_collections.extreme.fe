#!/usr/bin/env python3
"""Exercise extreme_fe_vlans helpers without a live switch for coverage."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional, Tuple
from pathlib import Path
import importlib
import sys

_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in _SCRIPT_PATH.parents if (parent / "ansible_collections").exists()),
    _SCRIPT_PATH.parents[1],
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_MODULE_CANDIDATES = (
    "ansible_collections.local.extreme_fe.plugins.modules.extreme_fe_vlans",
    "ansible_collections.extreme.fe.plugins.modules.extreme_fe_vlans",
)
module = None
_last_error = None
for candidate in _MODULE_CANDIDATES:
    try:
        module = importlib.import_module(candidate)
        break
    except ModuleNotFoundError as exc:  # pragma: no cover - import shim
        _last_error = exc

if module is None:  # pragma: no cover - defensive guard
    raise _last_error  # type: ignore[misc]


ErrorsList = list[str]


def _record(condition: bool, message: str, errors: ErrorsList) -> None:
    if not condition:
        errors.append(message)


def _expect_fe_error(
    func: Callable[..., Any],
    errors: ErrorsList,
    *args: Any,
    message_fragment: Optional[str] = None,
    **kwargs: Any,
) -> Optional[module.FeVlansError]:
    try:
        func(*args, **kwargs)
    except module.FeVlansError as exc:  # type: ignore[attr-defined]
        if message_fragment and message_fragment not in str(exc):
            errors.append(f"Unexpected error message from {func.__name__}: {exc}")
        return exc
    except Exception as exc:  # pragma: no cover - defensive guard
        errors.append(f"Unexpected exception from {func.__name__}: {exc}")
        return None
    else:
        errors.append(f"Expected FeVlansError from {func.__name__}")
        return None


class DummyConnection:
    """Simple connection stub that records calls and returns canned responses."""

    def __init__(self, responses: Dict[Tuple[str, str], Any]) -> None:
        self._responses = responses
        self.calls: list[Tuple[str, str, Any]] = []

    def send_request(self, payload: Any, path: str, method: str) -> Any:
        self.calls.append((method, path, payload))
        handler = self._responses.get((method, path))
        if callable(handler):
            return handler(payload)
        return handler


def _test_error_helpers(errors: ErrorsList) -> None:
    plain = module.FeVlansError("plain message")  # type: ignore[attr-defined]
    _record(plain.to_fail_kwargs() == {"msg": "plain message"}, "Plain error kwargs mismatch", errors)

    detailed = module.FeVlansError("boom", details={"why": "because"})  # type: ignore[attr-defined]
    detail_kwargs = detailed.to_fail_kwargs()
    _record(detail_kwargs.get("msg") == "boom", "Detailed error msg mismatch", errors)
    _record(detail_kwargs.get("details", {}).get("why") == "because", "Detailed error missing details", errors)

    _record(module._is_not_found_response({"errorCode": "404"}), "String code 404 should be not-found", errors)
    _record(module._is_not_found_response({"message": "Item does not exist"}), "Message indicator not detected", errors)
    _record(not module._is_not_found_response({"errorCode": 403}), "Non-404 code misdetected", errors)
    _record(not module._is_not_found_response(["bogus"]), "Non-dict payload misdetected", errors)


def _test_membership_sanitizers(errors: ErrorsList) -> None:
    raw_entries = [
        "invalid",
        {"interfaceType": None, "interfaceName": "1"},
        {"interfaceType": "LAG", "interfaceName": "10"},
        {"interfaceType": "isis", "interfaceName": 20},
        {"interfaceType": "LAG"},
    ]
    sanitized = module._sanitize_membership(raw_entries)
    _record(len(sanitized) == 2, "Sanitized entries length unexpected", errors)
    _record(sanitized[0]["interfaceType"] == "LAG", "First sanitized entry type mismatch", errors)
    _record(sanitized[1]["interfaceName"] == "20", "Interface name not coerced to string", errors)

    entries = [
        {"interfaceType": "LAG", "interfaceName": "10"},
        {"interfaceType": "ISIS_LOGICAL_INTERFACE", "interfaceName": "200"},
    ]
    removed = module._remove_membership_entry(entries, ("LAG", "10"))
    _record(removed and len(entries) == 1, "Membership removal failed", errors)
    _record(
        not module._remove_membership_entry(entries, ("LAG", "999")),
        "Unexpected removal success",
        errors,
    )


def _test_multi_status(errors: ErrorsList) -> None:
    # Smoke paths that should not raise
    module._validate_multi_status("add", 123, None)
    module._validate_multi_status("add", 123, "")
    module._validate_multi_status("add", 123, {"entries": "not-a-list"})

    failure_payload = {
        "results": [
            {
                "interfaceType": "LAG",
                "interfaceName": "10",
                "tagType": "TAG",
                "statusCode": "500",
                "errorMessage": "boom",
            },
            {
                "interfaceType": "ISIS_LOGICAL_INTERFACE",
                "interfaceName": "200",
                "statusCode": "201",
            },
            {"statusCode": "not-int"},
        ]
    }
    err = _expect_fe_error(
        module._validate_multi_status,
        errors,
        "remove",
        200,
        failure_payload,
        message_fragment="Failed to remove VLAN membership",
    )
    if err is not None:
        _record("failures" in getattr(err, "details", {}), "Failure details not recorded", errors)


def _test_merge_operations(errors: ErrorsList) -> None:
    module_params = {
        "lag_interfaces": [
            {"name": "10", "tag": "tagged"},
            "bogus",
        ],
        "remove_lag_interfaces": [
            {"name": "11", "tag": "untagged"},
        ],
        "isis_logical_interfaces": [
            {"name": "200", "tag": "untagged"},
        ],
        "remove_isis_logical_interfaces": [
            {"name": "201", "tag": "tagged"},
        ],
    }
    fake_module = SimpleNamespace(params=module_params)
    additions, removals = module._membership_operations_for_merge(fake_module)

    _record(
        any(item["interfaceName"] == "10" for item in additions["TAG"]),
        "Expected tagged LAG addition not found",
        errors,
    )
    _record(
        any(item["interfaceName"] == "200" for item in additions["UNTAG"]),
        "Expected untagged ISIS addition not found",
        errors,
    )
    _record(
        any(item["interfaceName"] == "11" for item in removals["UNTAG"]),
        "Expected untagged removal missing",
        errors,
    )

    bad_params = SimpleNamespace(params={"lag_interfaces": [{"name": "bad", "tag": "garbage"}]})
    _expect_fe_error(
        module._membership_operations_for_merge,
        errors,
        bad_params,
        message_fragment="Unsupported tag value",
    )

    missing_name_params = SimpleNamespace(params={"lag_interfaces": [{"tag": "tagged"}]})
    _expect_fe_error(
        module._membership_operations_for_merge,
        errors,
        missing_name_params,
        message_fragment="Interface name is required",
    )


def _test_authoritative_operations(errors: ErrorsList) -> None:
    existing = {
        "taggedInterfaces": [
            {"interfaceType": "LAG", "interfaceName": "10"},
            {"interfaceType": "ISIS_LOGICAL_INTERFACE", "interfaceName": "200"},
        ],
        "untaggedInterfaces": [
            {"interfaceType": "LAG", "interfaceName": "12"},
        ],
    }

    params = {
        "lag_interfaces": [
            {"name": "10", "tag": "tagged"},
            {"name": "13", "tag": "tagged"},
        ],
        "remove_lag_interfaces": [
            {"name": "12", "tag": "untagged"},
        ],
        "isis_logical_interfaces": [
            {"name": "200", "tag": "untagged"},
        ],
    }
    authoritative_module = SimpleNamespace(params=params)
    additions, removals = module._membership_operations_authoritative(
        authoritative_module,
        existing,
        purge_missing=False,
    )
    _record(
        any(item["interfaceName"] == "13" for item in additions["TAG"]),
        "Authoritative additions missing new interface",
        errors,
    )
    _record(
        any(item["interfaceName"] == "12" for item in removals["UNTAG"]),
        "Authoritative removals missing explicit absent entry",
        errors,
    )

    # Purge path should force removals for unspecified combinations
    purge_module = SimpleNamespace(params={"lag_interfaces": None, "isis_logical_interfaces": None})
    purge_additions, purge_removals = module._membership_operations_authoritative(
        purge_module,
        existing,
        purge_missing=True,
    )
    _record(
        all(not items for items in purge_additions.values()),
        "Purge additions should be empty",
        errors,
    )
    _record(
        any(purge_removals[tag] for tag in purge_removals),
        "Purge removals should remove existing memberships",
        errors,
    )

    # Non-list parameters should be ignored gracefully
    mismatch_module = SimpleNamespace(params={"lag_interfaces": "invalid", "isis_logical_interfaces": []})
    module._membership_operations_authoritative(
        mismatch_module,
        existing,
        purge_missing=False,
    )

    # Missing names should surface errors
    bad_entry_module = SimpleNamespace(params={"lag_interfaces": [{"tag": "tagged"}]})
    _expect_fe_error(
        module._membership_operations_authoritative,
        errors,
        bad_entry_module,
        existing,
        purge_missing=False,
        message_fragment="Interface name is required",
    )


def _test_apply_membership_changes(errors: ErrorsList) -> None:
    # Check-mode execution should avoid connection activity
    check_module = SimpleNamespace(check_mode=True)
    existing_check = {
        "taggedInterfaces": [{"interfaceType": "LAG", "interfaceName": "10"}],
        "untaggedInterfaces": [],
    }
    additions_check = {
        "TAG": [
            {"interfaceType": "LAG", "interfaceName": "11"},
            {"interfaceType": "ISIS_LOGICAL_INTERFACE", "interfaceName": "210"},
        ],
        "UNTAG": [],
    }
    removals_check = {
        "TAG": [{"interfaceType": "LAG", "interfaceName": "10"}],
        "UNTAG": [],
    }
    check_conn = DummyConnection({})
    changed, updated, refresh = module._apply_membership_changes(
        check_module,
        check_conn,
        321,
        existing_check,
        additions_check,
        removals_check,
    )
    _record(changed and not refresh, "Check-mode refresh should be false", errors)
    tag_names = {entry["interfaceName"] for entry in updated["taggedInterfaces"]}
    _record("11" in tag_names, "Check-mode addition missing", errors)
    _record(not check_conn.calls, "Check-mode should not hit connection", errors)

    # Real execution should drive all payload paths
    live_module = SimpleNamespace(check_mode=False)
    existing_live = {
        "taggedInterfaces": [{"interfaceType": "LAG", "interfaceName": "20"}],
        "untaggedInterfaces": [
            {"interfaceType": "ISIS_LOGICAL_INTERFACE", "interfaceName": "400"}
        ],
    }
    additions_live = {
        "TAG": [
            {"interfaceType": "LAG", "interfaceName": "21"},
            {"interfaceType": "ISIS_LOGICAL_INTERFACE", "interfaceName": "401"},
        ],
        "UNTAG": [],
    }
    removals_live = {
        "TAG": [{"interfaceType": "LAG", "interfaceName": "20"}],
        "UNTAG": [{"interfaceType": "ISIS_LOGICAL_INTERFACE", "interfaceName": "400"}],
    }
    live_conn = DummyConnection(
        {
            ("POST", "/v0/operation/vlan/321/interfaces/:add"): [],
            ("POST", "/v0/operation/vlan/321/interfaces/:remove"): [],
            ("PATCH", "/v0/configuration/vlan/321"): [],
        }
    )
    changed_live, updated_live, refresh_live = module._apply_membership_changes(
        live_module,
        live_conn,
        321,
        existing_live,
        additions_live,
        removals_live,
    )
    _record(changed_live and refresh_live, "Live execution should change and refresh", errors)
    _record(len(live_conn.calls) == 3, "Unexpected connection call count", errors)
    patch_payload = next(
        (payload for method, path, payload in live_conn.calls if method == "PATCH"),
        {},
    )
    _record("taggedInterfaces" in patch_payload, "PATCH payload missing tagged interfaces", errors)
    _record("untaggedInterfaces" in patch_payload, "PATCH payload missing untagged interfaces", errors)

    # No-op path should return early
    noop_module = SimpleNamespace(check_mode=False)
    existing_noop = {"taggedInterfaces": [], "untaggedInterfaces": []}
    noop_result = module._apply_membership_changes(
        noop_module,
        DummyConnection({}),
        999,
        existing_noop,
        {"TAG": [], "UNTAG": []},
        {"TAG": [], "UNTAG": []},
    )
    _record(noop_result == (False, existing_noop, False), "No-op result unexpected", errors)


def main() -> int:
    errors: ErrorsList = []
    _test_error_helpers(errors)
    _test_membership_sanitizers(errors)
    _test_multi_status(errors)
    _test_merge_operations(errors)
    _test_authoritative_operations(errors)
    _test_apply_membership_changes(errors)

    if errors:
        for issue in errors:
            sys.stderr.write(f"{issue}\n")
        return 1

    sys.stdout.write("extreme_fe_vlans helper coverage completed successfully\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
