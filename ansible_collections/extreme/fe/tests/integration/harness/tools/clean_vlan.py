#!/usr/bin/env python3
"""Remove configured VLANs from NOS devices using the OpenAPI endpoints."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _load_nosapi_helpers() -> object:
    helper_path = Path(__file__).resolve().parent / "nosapi-helper-func.py"
    spec = importlib.util.spec_from_file_location("nosapi_helper_func", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load NosAPI helpers from {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NOSAPI = _load_nosapi_helpers()

RESERVED_VLANS = {1, 4048}
LOG_PATH = Path("/tmp/test.log")
SCRIPT_NAME = Path(__file__).name


def _log(message: str) -> None:
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {SCRIPT_NAME} {message}\n")
    except OSError:
        return


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_vlan_items(payload: Any) -> list[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "vlans", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if "vlanInterface" in payload and isinstance(payload["vlanInterface"], dict):
            return [payload["vlanInterface"]]
        return [payload]
    return []


def _extract_vlan_id(entry: Dict[str, Any]) -> Optional[int]:
    for key in ("id", "vlanId", "vlan_id"):
        vlan_id = _safe_int(entry.get(key))
        if vlan_id is not None:
            return vlan_id
    return None


def _extract_error_detail(body: Optional[str], default: str) -> str:
    if not body or not isinstance(body, str):
        return default
    text = body.strip()
    if not text:
        return default
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return default
    if isinstance(payload, dict):
        for key in ("errorMessage", "message", "detail", "error", "description"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return default


def _extract_dynamic(entry: Dict[str, Any]) -> Optional[bool]:
    dynamic = entry.get("dynamic")
    if isinstance(dynamic, bool):
        return dynamic
    if isinstance(dynamic, str):
        value = dynamic.strip().lower()
        if value in {"true", "false"}:
            return value == "true"
    return None


def _extract_vr_name(entry: Dict[str, Any]) -> str:
    for key in ("vrName", "vr_name", "vrfName", "vrf_name", "vr"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "default"


def _fetch_vlan_summary(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
    port: str,
    base_path: str,
) -> Tuple[Optional[list[Dict[str, Any]]], Optional[str]]:
    headers = {"Content-Type": "application/json"}
    body, status_code = NOSAPI.get_with_token_refresh(
        cfg_path,
        device,
        host,
        user,
        password,
        "/v0/configuration/vlan",
        headers=headers,
        port=port,
        base_path=base_path,
    )
    if status_code != 200 or body is None:
        return None, f"HTTP {status_code} when retrieving VLANs"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, "Failed to parse VLAN list JSON"
    return _normalize_vlan_items(payload), None


def _delete_vlan(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
    port: str,
    base_path: str,
    vr_name: str,
    vlan_id: int,
) -> Tuple[int, Optional[str]]:
    path = f"/v0/configuration/vrf/{vr_name}/vlan/{vlan_id}"
    body, status_code = NOSAPI.request_with_token_refresh(
        cfg_path,
        device,
        host,
        user,
        password,
        "DELETE",
        path,
        headers={"Content-Type": "application/json"},
        data=None,
        port=port,
        base_path=base_path,
    )
    if status_code not in {200, 202, 204}:
        detail = _extract_error_detail(body, "delete failed")
        return status_code, f"HTTP {status_code} deleting VLAN {vlan_id}: {detail}"
    return status_code, None


def _parse_args(argv: list[str]) -> Tuple[list[str], set[int]]:
    devices: list[str] = []
    skip_vlans: set[int] = set()
    for arg in argv:
        if arg.startswith("-s"):
            raw = arg[2:].strip()
            vlan_id = _safe_int(raw)
            if vlan_id is not None:
                skip_vlans.add(vlan_id)
            continue
        devices.append(arg)
    return devices, skip_vlans


def main() -> int:
    devices, skip_vlans = _parse_args(sys.argv[1:])
    if not devices:
        _log("Usage: clean_vlan.py <device> [-s<VLAN> ...]")
        return 1
    base_dir = NOSAPI.resolve_base_dir()
    cfg_path = NOSAPI.cfg_dir(base_dir)
    cfg_path.mkdir(parents=True, exist_ok=True)
    inventory = NOSAPI.inventory_path(base_dir)

    exit_code = 0

    for device in devices:
        host = NOSAPI.read_inventory_host(inventory, device)
        if not host:
            _log(f"ERROR: Unable to resolve host IP for {device}")
            exit_code = 1
            continue
        user, password = NOSAPI.read_inventory_credentials(inventory, device)
        if not user or not password:
            _log(f"ERROR: Missing credentials for {device}")
            exit_code = 1
            continue
        port, base_path = NOSAPI.read_inventory_httpapi_settings(inventory, device)

        vlan_items, error = _fetch_vlan_summary(cfg_path, device, host, user, password, port, base_path)
        if error:
            _log(f"ERROR: {device}: {error}")
            exit_code = 1
            continue

        to_delete: list[Tuple[int, str]] = []
        for entry in vlan_items or []:
            vlan_id = _extract_vlan_id(entry)
            dynamic = _extract_dynamic(entry)
            vr_name = _extract_vr_name(entry)

            reasons: list[str] = []
            if vlan_id is None:
                reasons.append("missing vlan id")
            elif vlan_id in RESERVED_VLANS:
                reasons.append("reserved vlan")
            elif vlan_id in skip_vlans:
                reasons.append("user skip")
            if dynamic is True:
                reasons.append("dynamic vlan")
            elif dynamic is None:
                reasons.append("dynamic flag missing")

            vlan_label = str(vlan_id) if vlan_id is not None else "UNKNOWN"
            if reasons:
                _log(f"{device} vlan {vlan_label} skip: {', '.join(reasons)}")
            else:
                _log(f"{device} vlan {vlan_label} delete")
                to_delete.append((vlan_id, vr_name))

        for vlan_id, vr_name in to_delete:
            status_code, error = _delete_vlan(
                cfg_path,
                device,
                host,
                user,
                password,
                port,
                base_path,
                vr_name,
                vlan_id,
            )
            print(f"{device} vlan {vlan_id} delete status {status_code}")
            _log(f"{device} vlan {vlan_id} delete status {status_code}")
            if error:
                _log(f"ERROR: {device}: {error}")
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
