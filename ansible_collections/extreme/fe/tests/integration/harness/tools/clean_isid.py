#!/usr/bin/env python3
"""Remove configured I-SIDs from NOS devices using OpenAPI endpoints."""
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

LOG_PATH = Path("/tmp/test.log")
SCRIPT_NAME = Path(__file__).name
RESERVED_ISIDS = {15999999}


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


def _normalize_isid_items(payload: Any) -> list[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("isids", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = _normalize_isid_items(value)
                if nested:
                    return nested
        collected: list[Dict[str, Any]] = []
        for key in ("cvlan", "suni", "tuni"):
            value = payload.get(key)
            if isinstance(value, list):
                collected.extend(item for item in value if isinstance(item, dict))
        if collected:
            return collected
        return [payload]
    return []


def _normalize_mlag_peer_items(payload: Any) -> list[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("peers", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _extract_peer_id(entry: Dict[str, Any]) -> Optional[str]:
    for key in ("peerId", "peer_id", "id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_peer_ip(entry: Dict[str, Any]) -> Optional[str]:
    peer_ip = entry.get("peerIpAddress")
    if isinstance(peer_ip, dict):
        address = peer_ip.get("address")
        if isinstance(address, str) and address.strip():
            return address.strip()
    for key in ("peerIp", "peer_ip", "peer_ip_address"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_isid_id(entry: Dict[str, Any]) -> Optional[int]:
    for key in ("isid", "isidId", "isid_id", "id"):
        isid_value = _safe_int(entry.get(key))
        if isid_value is not None:
            return isid_value
    return None


def _extract_isid_cvlan(entry: Dict[str, Any]) -> Optional[int]:
    for key in ("platformVlanId", "platform_vlan_id", "cvlan", "vlanId", "vlan_id"):
        cvlan = _safe_int(entry.get(key))
        if cvlan is not None:
            return cvlan
    interfaces = entry.get("interfaces")
    if isinstance(interfaces, dict):
        for key in ("platformVlanId", "platform_vlan_id"):
            cvlan = _safe_int(interfaces.get(key))
            if cvlan is not None:
                return cvlan
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


def _fetch_isid_summary(
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
        "/v0/configuration/spbm/l2/isid",
        headers=headers,
        port=port,
        base_path=base_path,
    )
    if status_code == 404:
        return [], None
    if status_code != 200 or body is None:
        return None, f"HTTP {status_code} when retrieving I-SIDs"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, "Failed to parse I-SID list JSON"
    return _normalize_isid_items(payload), None


def _fetch_virtual_ist_peers(
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
        "/v0/configuration/mlag/peers",
        headers=headers,
        port=port,
        base_path=base_path,
    )
    if status_code == 404:
        return [], None
    if status_code != 200 or body is None:
        return None, f"HTTP {status_code} when retrieving virtual-ist peers"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, "Failed to parse virtual-ist peers JSON"
    return _normalize_mlag_peer_items(payload), None


def _delete_isid(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
    port: str,
    base_path: str,
    isid: int,
    cvlan: int,
) -> Tuple[int, Optional[str]]:
    path = f"/v0/configuration/spbm/l2/isid/{isid}/cvlan/{cvlan}"
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
        return status_code, f"HTTP {status_code} deleting I-SID {isid} (cvlan {cvlan}): {detail}"
    return status_code, None


def _remove_virtual_ist_peer(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
    port: str,
    base_path: str,
    peer_ip: str,
) -> Tuple[int, Optional[str]]:
    path = "/v0/operation/system/cli"
    payload = json.dumps([
        "configure terminal",
        "no virtual-ist peer-ip",
    ])
    body, status_code = NOSAPI.request_with_token_refresh(
        cfg_path,
        device,
        host,
        user,
        password,
        "POST",
        path,
        headers={"Content-Type": "application/json"},
        data=payload,
        port=port,
        base_path=base_path,
    )
    if status_code not in {200, 207}:
        detail = _extract_error_detail(body, "CLI request failed")
        return status_code, f"HTTP {status_code} removing virtual-ist peer-ip {peer_ip}: {detail}"
    if not body:
        return status_code, None
    try:
        response = json.loads(body)
    except json.JSONDecodeError:
        return status_code, None
    data = response.get("data") if isinstance(response, dict) else None
    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            if entry.get("statusCode") != 200:
                cli_output = entry.get("cliOutput")
                detail = (
                    str(cli_output).strip()
                    if isinstance(cli_output, str) and str(cli_output).strip()
                    else "CLI command failed"
                )
                return status_code, f"CLI failed removing virtual-ist peer-ip {peer_ip}: {detail}"
    return status_code, None


def main() -> int:
    devices = sys.argv[1:]
    if not devices:
        _log("Usage: clean_isid.py <device> [device ...]")
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

        peer_items, peer_error = _fetch_virtual_ist_peers(cfg_path, device, host, user, password, port, base_path)
        if peer_error:
            _log(f"ERROR: {device}: {peer_error}")
            exit_code = 1
            continue

        if not peer_items:
            _log(f"{device} virtual-ist none found")
        else:
            for entry in peer_items:
                peer_id = _extract_peer_id(entry)
                peer_ip = _extract_peer_ip(entry)

                if not peer_ip:
                    continue
                if peer_ip == "0.0.0.0":
                    _log(f"{device} virtual-ist peer-id {peer_id or 'UNKNOWN'} skip: peer-ip 0.0.0.0")
                    continue
                if not peer_id:
                    _log(f"{device} virtual-ist {peer_ip} skip: missing peer id")
                    exit_code = 1
                    continue

                _log(f"{device} virtual-ist found: peer-id {peer_id}, peer-ip {peer_ip}")
                status_code, vist_error = _remove_virtual_ist_peer(
                    cfg_path,
                    device,
                    host,
                    user,
                    password,
                    port,
                    base_path,
                    peer_ip,
                )
                print(f"{device} virtual-ist peer-ip {peer_ip} remove status {status_code}")
                _log(f"{device} virtual-ist peer-ip {peer_ip} remove status {status_code}")
                if vist_error:
                    _log(f"ERROR: {device}: {vist_error}")
                    exit_code = 1

        isid_items, error = _fetch_isid_summary(cfg_path, device, host, user, password, port, base_path)
        if error:
            _log(f"ERROR: {device}: {error}")
            exit_code = 1
            continue

        if not isid_items:
            _log(f"{device} i-sid none found")
            continue

        for entry in isid_items:
            isid = _extract_isid_id(entry)
            cvlan = _extract_isid_cvlan(entry)

            if isid is None:
                _log(f"{device} i-sid UNKNOWN skip: missing isid")
                exit_code = 1
                continue
            if isid in RESERVED_ISIDS:
                _log(f"{device} i-sid {isid} skip: reserved i-sid")
                continue
            if cvlan is None:
                _log(f"{device} i-sid {isid} skip: missing cvlan")
                continue

            _log(f"{device} i-sid {isid} found (cvlan {cvlan})")
            status_code, isid_error = _delete_isid(
                cfg_path,
                device,
                host,
                user,
                password,
                port,
                base_path,
                isid,
                cvlan,
            )
            print(f"{device} i-sid {isid} delete status {status_code}")
            _log(f"{device} i-sid {isid} delete status {status_code}")
            if isid_error:
                _log(f"ERROR: {device}: {isid_error}")
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
