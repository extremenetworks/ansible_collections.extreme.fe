#!/usr/bin/env python3
"""Fetch system information for a device and cache it in cfg."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Optional, Tuple

INFO_SUFFIX = "-info.json"


def _load_nosapi_helpers() -> object:
    helper_path = Path(__file__).resolve().parent / "nosapi-helper-func.py"
    spec = importlib.util.spec_from_file_location("nosapi_helper_func", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load NosAPI helpers from {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NOSAPI = _load_nosapi_helpers()


def _write_info(cfg_path: Path, device: str, firmware: str, model: str, nos_type: str) -> None:
    info_path = cfg_path / f"{device}{INFO_SUFFIX}"
    payload = {
        "firmwareVersion": firmware,
        "modelName": model,
        "nosType": nos_type,
    }
    try:
        info_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def _fetch_system_info(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
) -> Tuple[Optional[str], int]:
    headers = {
        "Content-Type": "application/json",
    }
    return NOSAPI.get_with_token_refresh(
        cfg_path,
        device,
        host,
        user,
        password,
        "/v0/state/system",
        headers=headers,
        port=NOSAPI.PORT,
        base_path=NOSAPI.BASE_PATH,
    )


def _extract_info(payload: dict) -> Tuple[str, str, str]:
    firmware = "N/A"
    model = "N/A"
    nos_type = "N/A"
    cards = payload.get("cards")
    if isinstance(cards, list) and cards:
        first = cards[0]
        if isinstance(first, dict):
            firmware = str(first.get("firmwareVersion") or firmware)
            model = str(first.get("modelName") or model)
    nos_type = str(payload.get("nosType") or nos_type)
    return firmware, model, nos_type


def main() -> int:
    if len(sys.argv) < 3:
        return 1
    device = sys.argv[1].strip()
    host = sys.argv[2].strip()
    if not device or not host:
        return 1

    base_dir = NOSAPI.resolve_base_dir()
    cfg_path = NOSAPI.cfg_dir(base_dir)
    cfg_path.mkdir(parents=True, exist_ok=True)
    inventory = NOSAPI.inventory_path(base_dir)

    user, password = NOSAPI.read_inventory_credentials(inventory, device)
    if not user or not password:
        _write_info(cfg_path, device, "N/A", "N/A", "N/A")
        return 0

    body, status_code = _fetch_system_info(cfg_path, device, host, user, password)

    if status_code != 200 or not body:
        _write_info(cfg_path, device, "N/A", "N/A", "N/A")
        return 0

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        _write_info(cfg_path, device, "N/A", "N/A", "N/A")
        return 0

    if not isinstance(payload, dict):
        _write_info(cfg_path, device, "N/A", "N/A", "N/A")
        return 0

    firmware, model, nos_type = _extract_info(payload)
    _write_info(cfg_path, device, firmware, model, nos_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
