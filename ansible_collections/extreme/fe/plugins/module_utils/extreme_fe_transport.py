# Copyright (c) 2026 Extreme Networks
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
"""Classify a failed request: did the device answer, not answer, or never get it?

The extreme_fe HTTPAPI plugin raises every HTTP status of 400 or more as a
ConnectionError whose code is that status. A transport failure (a lost answer,
"Retries exhausted while contacting device", a broken socket) carries no HTTP
status: either no code at all, or the JSON-RPC error code of the persistent
connection - a negative number such as -32603, which ansible's JSON-RPC server
uses for an exception without a code. Only an integer code from 100 to 599 is
an HTTP answer.

A failure the plugin raises before the request leaves for the device (the host
name cannot be resolved, the login fails, the request cannot be built) carries
REQUEST_NOT_SENT: the request cannot have been applied. Only the code crosses
the persistent connection (its JSON-RPC server forwards a ConnectionError's
code and message, nothing else), so the marker is a code. Every other failure
without an HTTP status leaves the device's answer unknown, so a write that
failed that way may have been applied. That includes failures raised outside
the plugin (the module's own socket to the persistent connection, its command
timeout), which therefore carry no marker.
"""

from __future__ import annotations

from typing import Any

HTTP_STATUS_MIN = 100
HTTP_STATUS_MAX = 599
# In the JSON-RPC range reserved for implementation-defined server errors
# (-32000 to -32099), so it is never an HTTP status nor a code ansible uses.
REQUEST_NOT_SENT = -32050


def http_status(code: Any) -> int | None:
    """Return *code* as an HTTP status (100-599), or None when it is not one."""
    if isinstance(code, str) and code.strip().isdigit():
        code = int(code.strip())
    # bool is an int subclass but never a status code
    if isinstance(code, int) and not isinstance(code, bool) and HTTP_STATUS_MIN <= code <= HTTP_STATUS_MAX:
        return code
    return None


def is_http_status(code: Any) -> bool:
    """True when *code* is an HTTP status (100-599)."""
    return http_status(code) is not None


def is_not_sent_code(code: Any) -> bool:
    """True when *code* marks a failure raised before the request was sent (REQUEST_NOT_SENT)."""
    return isinstance(code, int) and not isinstance(code, bool) and code == REQUEST_NOT_SENT


def is_answer_unknown_code(code: Any) -> bool:
    """True when a failure with *code* leaves the answer unknown: no HTTP status, and not marked as not sent."""
    return not is_http_status(code) and not is_not_sent_code(code)


def answer_unknown(exc: Any) -> bool:
    """True when the failure *exc* (a ConnectionError) leaves the device's answer unknown.

    It carries no HTTP status and was not raised before the request was sent,
    so a write that failed this way may have been applied.
    """
    return is_answer_unknown_code(getattr(exc, "code", None))
