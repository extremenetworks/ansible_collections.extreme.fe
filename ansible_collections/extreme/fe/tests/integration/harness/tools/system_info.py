#!/usr/bin/env python3
"""Fetch system information for a device and cache it in cfg."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

PORT = "9443"
BASE_PATH = "rest/openapi"
TOKEN_SUFFIX = "-APItoken.cfg"
INFO_SUFFIX = "-info.json"


def _resolve_base_dir() -> Path:
    script_path = Path(__file__).resolve()
    for ancestor in script_path.parents:
        if (ancestor / "galaxy.yml").is_file():
            return ancestor
    return script_path.parent


def _inventory_path(base_dir: Path) -> Path:
    return base_dir / "tests" / "integration" / "harness" / "cfg" / "inventory.ini"


def _cfg_dir(base_dir: Path) -> Path:
    return base_dir / "tests" / "integration" / "harness" / "cfg"


def _read_inventory_credentials(path: Path, host: str) -> Tuple[Optional[str], Optional[str]]:
    if not path.is_file():
        return None, None
    if shutil.which("ansible-inventory"):
        command = ["ansible-inventory", "-i", str(path), "--host", host]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            result = None
        if result is not None and result.returncode == 0:
            try:
                payload = json.loads(result.stdout or "{}")
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                user = (
                    payload.get("ansible_user")
                    or payload.get("ansible_ssh_user")
                    or payload.get("user")
                    or payload.get("username")
                )
                password = (
                    payload.get("ansible_password")
                    or payload.get("ansible_ssh_pass")
                    or payload.get("ansible_pass")
                    or payload.get("password")
                )
                if isinstance(user, str) and user.strip() and isinstance(password, str) and password.strip():
                    return user.strip(), password.strip()

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None
    group_hosts: dict[str, set[str]] = {}
    group_vars: dict[str, dict[str, str]] = {}
    host_vars: dict[str, dict[str, str]] = {}
    current_group: Optional[str] = None
    current_vars_group: Optional[str] = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.strip("[]").strip()
            if section.endswith(":vars"):
                current_vars_group = section[:-5]
                current_group = None
                group_vars.setdefault(current_vars_group, {})
            else:
                current_group = section
                current_vars_group = None
                group_hosts.setdefault(current_group, set())
            continue
        if current_vars_group:
            if "=" in line:
                key, value = line.split("=", 1)
                group_vars.setdefault(current_vars_group, {})[key.strip()] = value.strip().strip('"\'')
            continue
        parts = line.split()
        if not parts:
            continue
        host_name = parts[0]
        if current_group:
            group_hosts.setdefault(current_group, set()).add(host_name)
        if host_name != host:
            continue
        kv: dict[str, str] = {}
        for token in parts[1:]:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            kv[key.strip()] = value.strip().strip('"\'')
        host_vars[host] = kv
    merged: dict[str, str] = {}
    for group, hosts in group_hosts.items():
        if host in hosts:
            merged.update(group_vars.get(group, {}))
    merged.update(host_vars.get(host, {}))
    user = merged.get("ansible_user") or merged.get("ansible_ssh_user") or merged.get("user")
    password = (
        merged.get("ansible_password")
        or merged.get("ansible_ssh_pass")
        or merged.get("ansible_pass")
        or merged.get("password")
    )
    return user, password


def _run_curl(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def _read_token(cfg_path: Path, device: str) -> Tuple[Optional[str], bool]:
    token_path = cfg_path / f"{device}{TOKEN_SUFFIX}"
    if not token_path.is_file():
        return None, False
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None, False
    return (token if token else None), True


def _write_token(cfg_path: Path, device: str, token: str) -> None:
    token_path = cfg_path / f"{device}{TOKEN_SUFFIX}"
    try:
        token_path.write_text(token + "\n", encoding="utf-8")
    except OSError:
        return


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


def _acquire_token(host: str, user: str, password: str, token_url: str) -> Optional[str]:
    payload = json.dumps({"username": user, "password": password})
    command = [
        "curl",
        "--silent",
        "-k",
        "--max-time",
        "2",
        "-H",
        "Content-Type: application/json",
        "-X",
        "POST",
        token_url,
        "--data",
        payload,
    ]
    result = _run_curl(command)
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout or "")
    except json.JSONDecodeError:
        return None
    token = parsed.get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _fetch_system_info(host: str, token: str) -> Tuple[Optional[str], int]:
    url = f"https://{host}:{PORT}/{BASE_PATH}/v0/state/system"
    command = [
        "curl",
        "--silent",
        "-k",
        "--max-time",
        "2",
        "-w",
        "\nHTTPSTATUS:%{http_code}\n",
        "-H",
        "Content-Type: application/json",
        "-H",
        f"X-Auth-Token: {token}",
        "-X",
        "GET",
        url,
        "--data",
        "",
    ]
    result = _run_curl(command)
    if result.returncode != 0:
        return None, 0
    output = result.stdout or ""
    if "HTTPSTATUS:" not in output:
        return None, 0
    body, status_text = output.rsplit("HTTPSTATUS:", 1)
    status_text = status_text.strip()
    status_code = int(status_text) if status_text.isdigit() else 0
    return body.strip(), status_code


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

    base_dir = _resolve_base_dir()
    cfg_path = _cfg_dir(base_dir)
    cfg_path.mkdir(parents=True, exist_ok=True)
    inventory = _inventory_path(base_dir)

    user, password = _read_inventory_credentials(inventory, device)
    if not user or not password:
        _write_info(cfg_path, device, "N/A", "N/A", "N/A")
        return 0

    token_url = f"https://{host}:{PORT}/{BASE_PATH}/v0/operation/auth-token/:generate"
    token, token_from_file = _read_token(cfg_path, device)
    if not token:
        token = _acquire_token(host, user, password, token_url)
        token_from_file = False
        if token:
            _write_token(cfg_path, device, token)

    if not token:
        _write_info(cfg_path, device, "N/A", "N/A", "N/A")
        return 0

    body, status_code = _fetch_system_info(host, token)
    if status_code in {401, 403} or (body and "invalid token" in body.lower()):
        if token_from_file:
            token = _acquire_token(host, user, password, token_url)
            if token:
                _write_token(cfg_path, device, token)
                body, status_code = _fetch_system_info(host, token)

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
