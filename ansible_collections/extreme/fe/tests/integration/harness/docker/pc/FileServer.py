#!/usr/bin/env python3
"""Minimal file upload server with Basic Auth protection."""

import base64
import binascii
import hmac
import os
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
import cgi

FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")
DEFAULT_USERNAME = "extreme"
DEFAULT_PASSWORD = "networks"
HOST = os.environ.get("FILESERVER_HOST", "0.0.0.0")
PORT = int(os.environ.get("FILESERVER_PORT", "5000"))
USERNAME = os.environ.get("FILESERVER_USER", DEFAULT_USERNAME)
PASSWORD = os.environ.get("FILESERVER_PASSWORD", DEFAULT_PASSWORD)


def ensure_files_dir() -> None:
    os.makedirs(FILES_DIR, exist_ok=True)


class FileUploadHandler(BaseHTTPRequestHandler):
    server_version = "FileServer/1.0"
    _BODY_PREVIEW_LIMIT = 512

    def do_POST(self) -> None:
        if not self._check_auth():
            self._require_auth()
            return

        ensure_files_dir()

        content_type = self.headers.get("Content-Type", "")
        if not content_type:
            self._log_rejection("Missing Content-Type header")
            self._send_response(400, "Missing Content-Type header\n")
            return

        ctype, _ = cgi.parse_header(content_type)

        content_length_header = self.headers.get("Content-Length")
        try:
            content_length = int(content_length_header)
        except (TypeError, ValueError):
            self._log_rejection(
                "Invalid Content-Length header",
                extra={"Content-Length": content_length_header or "<missing>"},
            )
            self._send_response(400, "Invalid Content-Length header\n")
            return

        if content_length < 0:
            self._log_rejection(
                "Negative Content-Length received",
                extra={"Content-Length": content_length},
            )
            self._send_response(400, "Invalid Content-Length header\n")
            return

        body_stream, body_preview, bytes_read = self._capture_request_body(content_length)
        if bytes_read != content_length:
            self._log_rejection(
                "Request body length mismatch",
                body_preview=body_preview,
                extra={"expected_length": content_length, "received_length": bytes_read},
            )
            body_stream.close()
            self._send_response(400, "Request body truncated\n")
            return

        if ctype != "multipart/form-data":
            self._log_rejection(
                "Unexpected Content-Type",
                body_preview=body_preview,
                extra={"Content-Type": content_type},
            )
            body_stream.close()
            self._send_response(400, "Expected multipart/form-data payload\n")
            return

        try:
            form = cgi.FieldStorage(
                fp=body_stream,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                },
            )
        except Exception:
            self._log_rejection(
                "Failed to parse multipart payload",
                body_preview=body_preview,
            )
            body_stream.close()
            self._send_response(400, "Failed to parse multipart payload\n")
            return
        finally:
            body_stream.close()

        if "file" not in form:
            self._log_rejection(
                "Missing 'file' field in form data",
                body_preview=body_preview,
            )
            self._send_response(400, "Missing 'file' field in form data\n")
            return

        file_item = form["file"]
        if not hasattr(file_item, "file") or file_item.file is None:
            self._log_rejection(
                "Provided 'file' field is not a file upload",
                body_preview=body_preview,
            )
            self._send_response(400, "Expected 'file' field to be a file upload\n")
            return

        filename = os.path.basename(file_item.filename or "")
        if not filename:
            self._log_rejection(
                "Uploaded file is missing a filename",
                body_preview=body_preview,
            )
            self._send_response(400, "Uploaded file is missing a filename\n")
            return

        target_path = os.path.join(FILES_DIR, filename)
        try:
            file_item.file.seek(0)
            with open(target_path, "wb") as destination:
                while True:
                    chunk = file_item.file.read(8192)
                    if not chunk:
                        break
                    destination.write(chunk)
        except OSError:
            self._log_server_error(
                "Failed to store uploaded file",
                extra={"target_path": target_path},
            )
            self._send_response(500, "Failed to store uploaded file\n")
            return

        self._send_response(201, f"Stored file as {filename}\n")

    def do_GET(self) -> None:
        if not self._check_auth():
            self._require_auth()
            return

        message = "File upload endpoint is available via POST to this URL.\n"
        self._send_response(200, message)

    def _check_auth(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False

        encoded_credentials = auth_header.split(" ", 1)[1].strip()
        try:
            decoded_bytes = base64.b64decode(encoded_credentials, validate=True)
        except binascii.Error:
            return False

        try:
            credentials = decoded_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return False

        return hmac.compare_digest(credentials, f"{USERNAME}:{PASSWORD}")

    def _require_auth(self) -> None:
        body = b"Authentication required"
        self.send_response(401)
        self.send_header("WWW-Authenticate", "Basic realm=\"FileServer\"")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_response(self, status_code: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - match BaseHTTPRequestHandler signature
        message = "%s - - [%s] %s\n" % (
            self.address_string(),
            self.log_date_time_string(),
            format % args,
        )
        print(message, end="")

    def _capture_request_body(self, content_length: int):
        preview_buffer = bytearray()
        preview_truncated = False
        body_stream = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
        bytes_read = 0
        while bytes_read < content_length:
            chunk = self.rfile.read(min(65536, content_length - bytes_read))
            if not chunk:
                break
            body_stream.write(chunk)
            if len(preview_buffer) < self._BODY_PREVIEW_LIMIT:
                needed = self._BODY_PREVIEW_LIMIT - len(preview_buffer)
                preview_buffer.extend(chunk[:needed])
                if len(chunk) > needed:
                    preview_truncated = True
            else:
                preview_truncated = True
            bytes_read += len(chunk)
        body_stream.seek(0)
        truncated = preview_truncated or bytes_read > len(preview_buffer)
        body_preview = self._preview_bytes(bytes(preview_buffer), truncated)
        return body_stream, body_preview, bytes_read

    def _preview_bytes(self, data: bytes, truncated: bool) -> str:
        if not data:
            return "<empty>"
        suffix = "...(truncated)" if truncated else ""
        return data.decode("utf-8", errors="replace") + suffix

    def _log_rejection(self, reason: str, body_preview=None, extra=None) -> None:
        lines = [
            "---- Request rejected ----",
            f"Reason: {reason}",
            f"Request: {self.command} {self.path}",
            "Headers:",
            str(self.headers).rstrip("\n"),
        ]
        if extra:
            extra_repr = ", ".join(f"{key}={value}" for key, value in extra.items())
            lines.append(f"Details: {extra_repr}")
        if body_preview:
            lines.append("Body preview:")
            lines.append(body_preview)
        print("\n".join(lines))

    def _log_server_error(self, reason: str, extra=None) -> None:
        lines = [
            "---- Internal error ----",
            f"Reason: {reason}",
            f"Request: {self.command} {self.path}",
        ]
        if extra:
            extra_repr = ", ".join(f"{key}={value}" for key, value in extra.items())
            lines.append(f"Details: {extra_repr}")
        print("\n".join(lines))


def run_server() -> None:
    ensure_files_dir()
    httpd = HTTPServer((HOST, PORT), FileUploadHandler)
    print(f"FileServer listening on {HOST}:{PORT}, storing uploads in {FILES_DIR}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down FileServer")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()
