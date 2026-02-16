#!/usr/bin/env python3
"""Normalize auto-sense enablement and wait interval on switch ports."""
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

DEFAULT_WAIT_INTERVAL = 35
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


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
    return default


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_port_items(payload: Any) -> list[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("ports", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _extract_port_name(entry: Dict[str, Any]) -> Optional[str]:
    value = entry.get("portName") or entry.get("port")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _fetch_port_settings(
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
        "/v0/configuration/autosense/ports",
        headers=headers,
        port=port,
        base_path=base_path,
    )
    if status_code != 200 or body is None:
        return None, f"HTTP {status_code} when retrieving autosense ports"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, "Failed to parse autosense ports JSON"
    return _normalize_port_items(payload), None


def _patch_port_settings(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
    port: str,
    base_path: str,
    port_name: str,
    changes: Dict[str, Any],
) -> Tuple[int, Optional[str]]:
    path = f"/v0/configuration/autosense/port/{port_name}"
    payload = json.dumps(changes)
    body, status_code = NOSAPI.request_with_token_refresh(
        cfg_path,
        device,
        host,
        user,
        password,
        "PATCH",
        path,
        headers={"Content-Type": "application/json"},
        data=payload,
        port=port,
        base_path=base_path,
    )
    if status_code not in {200, 202, 204}:
        return status_code, f"HTTP {status_code} updating port {port_name}"
    return status_code, None


def _parse_args(argv: list[str]) -> Tuple[list[str], set[str]]:
    devices: list[str] = []
    skip_ports: set[str] = set()
    for arg in argv:
        if arg.startswith("-s"):
            port = arg[2:].strip()
            if port:
                skip_ports.add(port)
            continue
        devices.append(arg)
    return devices, skip_ports


def main() -> int:
    devices, skip_ports = _parse_args(sys.argv[1:])
    if not devices:
        _log("Usage: clean_autosense.py <device> [-s<port> ...]")
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

        port_items, error = _fetch_port_settings(cfg_path, device, host, user, password, port, base_path)
        if error:
            _log(f"ERROR: {device}: {error}")
            exit_code = 1
            continue

        for entry in port_items or []:
            port_name = _extract_port_name(entry)
            if not port_name:
                _log(f"{device} port UNKNOWN skip: missing port name")
                continue
            settings = entry.get("portSettings") if isinstance(entry.get("portSettings"), dict) else {}
            enable = _coerce_bool(settings.get("enable"), True)
            wait_interval = _coerce_int(settings.get("waitInterval"), DEFAULT_WAIT_INTERVAL)

            if port_name in skip_ports:
                _log(
                    f"{device} port {port_name} skip: user skip "
                    f"(enable={enable}, waitInterval={wait_interval})"
                )
                continue

            changes: Dict[str, Any] = {}
            if enable is False:
                changes["enable"] = True
            if wait_interval != DEFAULT_WAIT_INTERVAL:
                changes["waitInterval"] = DEFAULT_WAIT_INTERVAL

            if not changes:
                _log(
                    f"{device} port {port_name} skip: no change "
                    f"(enable={enable}, waitInterval={wait_interval})"
                )
                continue

            _log(
                f"{device} port {port_name} update: {changes} "
                f"(enable={enable}, waitInterval={wait_interval})"
            )
            status_code, error = _patch_port_settings(
                cfg_path,
                device,
                host,
                user,
                password,
                port,
                base_path,
                port_name,
                changes,
            )
            _log(f"{device} port {port_name} update status {status_code}")
            if error:
                _log(f"ERROR: {device}: {error}")
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
