#!/usr/bin/env python3
"""NosAPI (OpenAPI) helper functions for integration tools."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Optional, Tuple

PORT = "9443"
BASE_PATH = "rest/openapi"
TOKEN_SUFFIX = "-APItoken.cfg"


def run_curl(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_base_dir() -> Path:
    script_path = Path(__file__).resolve()
    for ancestor in script_path.parents:
        if (ancestor / "galaxy.yml").is_file():
            return ancestor
    return script_path.parent


def inventory_path(base_dir: Path) -> Path:
    return base_dir / "tests" / "integration" / "harness" / "cfg" / "inventory.ini"


def cfg_dir(base_dir: Path) -> Path:
    return base_dir / "tests" / "integration" / "harness" / "cfg"


def _read_inventory_vars(path: Path, host: str) -> dict[str, str]:
    if not path.is_file():
        return {}
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
                return {key: str(value) for key, value in payload.items() if value is not None}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
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
    return merged


def read_inventory_credentials(path: Path, host: str) -> Tuple[Optional[str], Optional[str]]:
    merged = _read_inventory_vars(path, host)
    user = merged.get("ansible_user") or merged.get("ansible_ssh_user") or merged.get("user")
    password = (
        merged.get("ansible_password")
        or merged.get("ansible_ssh_pass")
        or merged.get("ansible_pass")
        or merged.get("password")
    )
    return user, password


def read_inventory_host(path: Path, host: str) -> Optional[str]:
    merged = _read_inventory_vars(path, host)
    host_ip = merged.get("ansible_host") or merged.get("ansible_ssh_host") or merged.get("host")
    if isinstance(host_ip, str) and host_ip.strip():
        return host_ip.strip()
    return None


def normalize_base_path(base_path: Optional[str]) -> str:
    if not base_path:
        return BASE_PATH
    normalized = base_path.strip()
    if not normalized:
        return BASE_PATH
    return normalized.lstrip("/")


def read_inventory_httpapi_settings(path: Path, host: str) -> Tuple[str, str]:
    merged = _read_inventory_vars(path, host)
    port = merged.get("ansible_httpapi_port") or PORT
    base_path = normalize_base_path(merged.get("ansible_httpapi_base_path"))
    return str(port), base_path


def build_base_url(host: str, port: str = PORT, base_path: str = BASE_PATH) -> str:
    return f"https://{host}:{port}/{base_path}"


def build_url(host: str, path: str, port: str = PORT, base_path: str = BASE_PATH) -> str:
    normalized_path = path.lstrip("/")
    return f"{build_base_url(host, port=port, base_path=base_path)}/{normalized_path}"


def _format_headers(headers: Optional[Mapping[str, str]]) -> list[str]:
    if not headers:
        return []
    return [f"{key}: {value}" for key, value in headers.items()]


def request_with_status(
    method: str,
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    data: Optional[str] = None,
    timeout: str = "2",
) -> Tuple[Optional[str], int]:
    command = [
        "curl",
        "--silent",
        "-k",
        "--max-time",
        timeout,
        "-w",
        "\nHTTPSTATUS:%{http_code}\n",
        "-X",
        method,
        url,
    ]
    for header in _format_headers(headers):
        command.extend(["-H", header])
    if data is not None:
        command.extend(["--data", data])
    result = run_curl(command)
    if result.returncode != 0:
        return None, 0
    output = result.stdout or ""
    if "HTTPSTATUS:" not in output:
        return None, 0
    body, status_text = output.rsplit("HTTPSTATUS:", 1)
    status_text = status_text.strip()
    status_code = int(status_text) if status_text.isdigit() else 0
    return body.strip(), status_code


def get_with_status(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    timeout: str = "2",
) -> Tuple[Optional[str], int]:
    return request_with_status("GET", url, headers=headers, data="", timeout=timeout)


def post_with_status(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    data: Optional[str] = None,
    timeout: str = "2",
) -> Tuple[Optional[str], int]:
    return request_with_status("POST", url, headers=headers, data=data, timeout=timeout)


def get_with_token_refresh(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
    path: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    timeout: str = "2",
    port: str = PORT,
    base_path: str = BASE_PATH,
) -> Tuple[Optional[str], int]:
    return request_with_token_refresh(
        cfg_path,
        device,
        host,
        user,
        password,
        "GET",
        path,
        headers=headers,
        data="",
        timeout=timeout,
        port=port,
        base_path=base_path,
    )


def request_with_token_refresh(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
    method: str,
    path: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    data: Optional[str] = None,
    timeout: str = "2",
    port: str = PORT,
    base_path: str = BASE_PATH,
) -> Tuple[Optional[str], int]:
    token, token_from_file = get_cached_or_new_token(
        cfg_path,
        device,
        host,
        user,
        password,
        port=port,
        base_path=base_path,
    )
    if not token:
        return None, 0
    url = build_url(host, path, port=port, base_path=base_path)
    merged_headers = dict(headers) if headers else {}
    if "Content-Type" not in merged_headers:
        merged_headers["Content-Type"] = "application/json"
    merged_headers["X-Auth-Token"] = token
    body, status_code = request_with_status(
        method,
        url,
        headers=merged_headers,
        data=data,
        timeout=timeout,
    )
    if status_code in {401, 403} or (body and "invalid token" in body.lower()):
        if token_from_file:
            token_url = build_token_url(host, port=port, base_path=base_path)
            token = acquire_token(host, user, password, token_url)
            if token:
                write_cached_token(cfg_path, device, token)
                merged_headers["X-Auth-Token"] = token
                body, status_code = request_with_status(
                    method,
                    url,
                    headers=merged_headers,
                    data=data,
                    timeout=timeout,
                )
    return body, status_code


def read_cached_token(cfg_path: Path, device: str) -> Tuple[Optional[str], bool]:
    token_path = cfg_path / f"{device}{TOKEN_SUFFIX}"
    if not token_path.is_file():
        return None, False
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None, False
    return (token if token else None), True


def write_cached_token(cfg_path: Path, device: str, token: str) -> None:
    token_path = cfg_path / f"{device}{TOKEN_SUFFIX}"
    try:
        token_path.write_text(token + "\n", encoding="utf-8")
    except OSError:
        return


def build_token_url(host: str, port: str = PORT, base_path: str = BASE_PATH) -> str:
    return f"https://{host}:{port}/{base_path}/v0/operation/auth-token/:generate"


def acquire_token(host: str, user: str, password: str, token_url: str) -> Optional[str]:
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
    result = run_curl(command)
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


def get_cached_or_new_token(
    cfg_path: Path,
    device: str,
    host: str,
    user: str,
    password: str,
    *,
    port: str = PORT,
    base_path: str = BASE_PATH,
) -> Tuple[Optional[str], bool]:
    token, token_from_file = read_cached_token(cfg_path, device)
    if token:
        return token, token_from_file
    token_url = build_token_url(host, port=port, base_path=base_path)
    token = acquire_token(host, user, password, token_url)
    token_from_file = False
    if token:
        write_cached_token(cfg_path, device, token)
    return token, token_from_file
