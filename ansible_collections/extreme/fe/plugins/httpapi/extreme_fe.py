# -*- coding: utf-8 -*-
# HTTPAPI plugin for ExtremeNetworks Fabric Engine switches

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ansible.module_utils.common.text.converters import to_text
from ansible.module_utils.connection import ConnectionError
from ansible.errors import AnsibleConnectionFailure
from ansible_collections.ansible.netcommon.plugins.plugin_utils.httpapi_base import (
    HttpApiBase,
)

DOCUMENTATION = """
author:
  - ExtremeNetworks Networking Automation Team
name: extreme_fe
short_description: HTTPAPI plugin for ExtremeNetworks Fabric Engine switches
version_added: 1.0.0
description:
  - Provides authentication and request helpers for ExtremeNetworks Fabric Engine
    switches that expose the REST API under ``/rest/openapi``.  Authentication
    tokens are generated via the ``/v0/operation/auth-token/:generate`` endpoint
    and stored as the ``x-auth-token`` cookie for subsequent requests.
extends_documentation_fragment:
  - ansible.netcommon.connection_persistent
options:
  base_path:
    description:
      - Base REST API path prefix used for all requests.
    type: str
    default: /rest/openapi
  auth_endpoint:
    description:
      - Relative endpoint used to obtain an authentication token.
    type: str
    default: /v0/operation/auth-token/:generate
"""

DEFAULT_CONTENT_TYPE = "application/json"
DEFAULT_ACCEPT = "application/json"
HTTPAPI_LOG = Path("/tmp/httpapi.log")


class HttpApi(HttpApiBase):
    FACTS_MODULES = ["extreme_fe_facts"]
    LOG_TRUNCATE_LIMIT = 4096

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._trace_enabled = bool(int(os.getenv("EXTREME_FE_HTTP_TRACE", "0")))
        trace_path = os.getenv("EXTREME_FE_HTTP_TRACE_PATH")
        self._trace_log = Path(trace_path) if trace_path else None
        self._log_counter = 0

    def _coerce_connection_error(self, exc: Exception) -> ConnectionError:
        if isinstance(exc, ConnectionError):
            return exc

        kwargs = {}
        code = getattr(exc, "code", None)
        if code is not None:
            kwargs["code"] = code
        err = getattr(exc, "err", None)
        if err is not None:
            kwargs["err"] = err
        return ConnectionError(to_text(exc), **kwargs)

    def _full_path(self, path: str) -> str:
        base = self.get_option("base_path") or "/rest/openapi"
        return "/".join(
            [
                base.rstrip("/"),
                path.lstrip("/"),
            ]
        )

    def _ensure_connected_host(self) -> Optional[str]:
        host = getattr(self.connection, "_connected_host", None)
        if host:
            return host

        candidates = [
            getattr(self.connection, "_host", None),
            getattr(self.connection, "host", None),
        ]

        httpapi = getattr(self.connection, "_httpapi", None)
        if httpapi is not None:
            candidates.extend(
                [
                    getattr(httpapi, "_host", None),
                    getattr(httpapi, "host", None),
                ]
            )
        url = getattr(self.connection, "_url", None)
        if url is not None:
            candidates.append(getattr(url, "hostname", None))
        play_context = getattr(self.connection, "_play_context", None)
        if play_context is not None:
            candidates.extend(
                [
                    getattr(play_context, "remote_addr", None),
                    getattr(play_context, "remote_host", None),
                ]
            )

        host_value: Optional[str] = None
        for candidate in candidates:
            if candidate:
                host_value = str(candidate)
                break

        if host_value:
            port = getattr(self.connection, "_port", None) or getattr(
                self.connection, "port", None
            )
            if port:
                host_value = f"{host_value}:{port}"
            try:
                self.connection._connected_host = host_value
            except Exception:  # pragma: no cover - defensive
                pass
        return host_value

    def login(self, username: str, password: str) -> None:
        if self.connection._auth:
            return

        payload = json.dumps({"username": username, "password": password})
        headers = {
            "Content-Type": DEFAULT_CONTENT_TYPE,
            "Accept": DEFAULT_ACCEPT,
        }
        path = self._full_path(
            self.get_option("auth_endpoint") or "/v0/operation/auth-token/:generate"
        )
        # Cache the connected host for enhanced logging context.
        connected_host = getattr(self.connection, "_connected_host", None)
        if not connected_host:
            connected_host = getattr(self.connection, "_host", None) or getattr(
                self.connection, "host", None
            )
            if connected_host:
                try:
                    self.connection._connected_host = connected_host
                except Exception:  # pragma: no cover - defensive
                    pass

        max_attempts = 5
        retry_signatures = (
            "DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
            "LENGTH_MISMATCH",
        )
        last_exc: Optional[ConnectionError] = None
        self._ensure_connected_host()
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
                with HTTPAPI_LOG.open("a") as fh:
                    fh.write(
                        f"{timestamp} login attempt {attempt}/{max_attempts} POST {path}\n"
                    )
            try:
                request_id = self._log_request("POST", path, None, is_retry=attempt > 1)
                response, response_data = self.connection.send(
                    path, payload, headers=headers, method="POST"
                )
                token_payload = self._parse_response(
                    response,
                    response_data,
                    method="POST",
                    path=path,
                    log_body=False,
                    request_id=request_id,
                )
                token = None
                if isinstance(token_payload, dict):
                    token = token_payload.get("token")
                if not token:
                    raise ConnectionError(
                        "Failed to obtain authentication token from device",
                        code=getattr(response, "code", None),
                    )
                cookie = f"x-auth-token={token}"
                self.connection._auth = {"Cookie": cookie, "x-auth-token": token}
                if attempt > 1:
                    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    with HTTPAPI_LOG.open("a") as fh:
                        fh.write(
                            f"{timestamp} login success on attempt {attempt} POST {path}\n"
                        )
                return
            except (ConnectionError, AnsibleConnectionFailure) as exc:
                coerced_exc = self._coerce_connection_error(exc)
                message = to_text(coerced_exc)
                last_exc = coerced_exc
                if (
                    any(sig in message for sig in retry_signatures)
                    and attempt < max_attempts
                ):
                    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    log_line = f"{timestamp} login retry {attempt} for POST {path}: {message}\n"
                    HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
                    with HTTPAPI_LOG.open("a") as fh:
                        fh.write(log_line)
                    time.sleep(2)
                    continue
                raise coerced_exc from exc
        else:  # pragma: no cover - safeguard
            if last_exc is not None:
                timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                log_line = f"{timestamp} login retries exhausted POST {path}: {to_text(last_exc)}\n"
                HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
                with HTTPAPI_LOG.open("a") as fh:
                    fh.write(log_line)
                raise last_exc
            raise ConnectionError(
                "Retries exhausted while contacting device during login"
            )

    def logout(self) -> None:
        self.connection._auth = None

    def send_request(self, data, **message_kwargs):
        method = (message_kwargs.get("method") or "GET").upper()
        path = message_kwargs.get("path") or ""
        headers = {}

        accept = message_kwargs.get("accept") or DEFAULT_ACCEPT
        if accept:
            headers["Accept"] = accept

        content_type = message_kwargs.get("content_type")
        body = None
        if data is not None:
            if isinstance(data, (str, bytes)):
                body = data if isinstance(data, str) else data.decode("utf-8")
            else:
                body = json.dumps(data)
            if not content_type:
                content_type = DEFAULT_CONTENT_TYPE
        if content_type:
            headers["Content-Type"] = content_type

        max_attempts = 5
        retry_signatures = (
            "DECRYPTION_FAILED_OR_BAD_RECORD_MAC",
            "LENGTH_MISMATCH",
        )
        last_exc: Optional[ConnectionError] = None
        self._ensure_connected_host()
        full_path = self._full_path(path)
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
                with HTTPAPI_LOG.open("a") as fh:
                    fh.write(
                        f"{timestamp} attempt {attempt}/{max_attempts} {method} {full_path}\n"
                    )
            try:
                is_retry = attempt > 1
                request_id = self._log_request(
                    method, full_path, body, is_retry=is_retry
                )
                response, response_data = self.connection.send(
                    full_path,
                    body,
                    headers=headers,
                    method=method,
                )
                if attempt > 1:
                    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    with HTTPAPI_LOG.open("a") as fh:
                        fh.write(
                            f"{timestamp} success on attempt {attempt} {method} {full_path}\n"
                        )
                break
            except (ConnectionError, AnsibleConnectionFailure) as exc:
                coerced_exc = self._coerce_connection_error(exc)
                message = to_text(coerced_exc)
                last_exc = coerced_exc
                self._emit_http_debug(
                    f"{request_id} !! {method} {full_path} failed: {message}"
                )
                if any(sig in message for sig in retry_signatures):
                    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    log_line = f"{timestamp} retry {attempt} for {method} {full_path}: {message}\n"
                    HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
                    with HTTPAPI_LOG.open("a") as fh:
                        fh.write(log_line)
                    if attempt < max_attempts:
                        time.sleep(2)
                        continue
                raise coerced_exc from exc
        else:  # pragma: no cover - safeguard
            if last_exc is not None:
                timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                log_line = f"{timestamp} retries exhausted for {method} {full_path}: {to_text(last_exc)}\n"
                HTTPAPI_LOG.parent.mkdir(parents=True, exist_ok=True)
                with HTTPAPI_LOG.open("a") as fh:
                    fh.write(log_line)
                raise last_exc
            raise ConnectionError("Retries exhausted while contacting device")
        parsed = self._parse_response(
            response,
            response_data,
            method=method,
            path=full_path,
            request_id=request_id,
        )
        status_code = getattr(response, "code", None) or getattr(
            response, "status", None
        )
        if status_code == 207:
            errors = self._multi_status_errors(parsed)
            if errors:
                message = "; ".join(errors)
                raise ConnectionError(
                    f"Multi-status failure for {method} {full_path}: {message}",
                    code=status_code,
                )
        if isinstance(status_code, int) and status_code >= 400:
            error_message = None
            if isinstance(parsed, dict):
                for key in ("errorMessage", "message", "detail", "error"):
                    value = parsed.get(key)
                    if value:
                        error_message = to_text(value)
                        break
            elif isinstance(parsed, list) and parsed:
                first = parsed[0]
                if isinstance(first, dict):
                    for key in ("errorMessage", "message", "detail", "error"):
                        value = first.get(key)
                        if value:
                            error_message = to_text(value)
                            break
                elif first:
                    error_message = to_text(first)
            elif parsed:
                error_message = to_text(parsed)

            if not error_message:
                error_message = f"HTTP {status_code} returned for {method} {full_path}"
            raise ConnectionError(error_message, code=status_code)
        return parsed

    def _emit_http_debug(self, message: str) -> None:
        host = getattr(self.connection, "_connected_host", None)
        if host:
            message = f"[{host}] {message}"
        display = getattr(self.connection, "_display", None)
        if display is not None and getattr(display, "verbosity", 0) >= 3:
            display.vvv(message)
        if self._trace_enabled and self._trace_log:
            timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            self._trace_log.parent.mkdir(parents=True, exist_ok=True)
            with self._trace_log.open("a") as fh:
                fh.write(f"{timestamp} {message}\n")

    def _log_request(
        self, method: str, path: str, body: Optional[str], *, is_retry: bool = False
    ) -> str:
        self._log_counter += 1
        request_id = f"#{self._log_counter}"
        retry_suffix = " (retry)" if is_retry else ""
        self._emit_http_debug(f"{request_id} => {method} {path}{retry_suffix}")
        if body:
            truncated = (
                body
                if len(body) <= self.LOG_TRUNCATE_LIMIT
                else f"{body[:self.LOG_TRUNCATE_LIMIT]}... (truncated)"
            )
            self._emit_http_debug(f"{request_id} => payload: {truncated}")
        return request_id

    def _log_response(
        self,
        response,
        method: str,
        path: str,
        raw_text: Optional[str],
        log_body: bool,
        *,
        request_id: Optional[str] = None,
    ) -> None:
        status = getattr(response, "code", None) or getattr(response, "status", None)
        status_display = status if status is not None else ""
        rid = request_id or ""
        rid_prefix = f"{rid} " if rid else ""
        self._emit_http_debug(f"{rid_prefix}<= {status_display} {method} {path}")
        if log_body and raw_text:
            truncated = (
                raw_text
                if len(raw_text) <= self.LOG_TRUNCATE_LIMIT
                else f"{raw_text[:self.LOG_TRUNCATE_LIMIT]}... (truncated)"
            )
            self._emit_http_debug(f"{rid_prefix}<= payload: {truncated}")

    def _parse_response(
        self,
        response,
        buffer,
        *,
        method: Optional[str] = None,
        path: Optional[str] = None,
        log_body: bool = True,
        request_id: Optional[str] = None,
    ):
        raw = buffer.read()
        raw_text = to_text(raw, errors="surrogate_then_replace") if raw else ""
        if method and path:
            self._log_response(
                response, method, path, raw_text, log_body, request_id=request_id
            )
        if not raw_text:
            return None
        try:
            return json.loads(raw_text)
        except ValueError:
            return raw_text

    def _multi_status_errors(self, payload) -> List[str]:
        errors: List[str] = []

        def inspect_entry(entry) -> None:
            if not isinstance(entry, dict):
                return
            status = entry.get("statusCode") or entry.get("status")
            if isinstance(status, str) and status.isdigit():
                status = int(status)
            is_error = False
            if isinstance(status, int) and status >= 400:
                is_error = True
            if status is None and entry.get("errorMessage"):
                is_error = True
            if is_error:
                iface_type = entry.get("interfaceType") or entry.get("interface_type")
                iface_name = entry.get("interfaceName") or entry.get("interface_name")
                location = []
                if iface_type:
                    location.append(str(iface_type))
                if iface_name:
                    location.append(str(iface_name))
                location_str = " ".join(location)
                prefix = f"{status}" if status is not None else "error"
                message = (
                    entry.get("errorMessage")
                    or entry.get("message")
                    or "request failed"
                )
                if location_str:
                    errors.append(f"{prefix} - {location_str}: {message}")
                else:
                    errors.append(f"{prefix}: {message}")

        if isinstance(payload, list):
            for item in payload:
                inspect_entry(item)
        elif isinstance(payload, dict):
            responses = None
            if isinstance(payload.get("responses"), list):
                responses = payload.get("responses")
            elif isinstance(payload.get("items"), list):
                responses = payload.get("items")
            if responses is not None:
                for item in responses:
                    inspect_entry(item)
            else:
                inspect_entry(payload)

        return errors
