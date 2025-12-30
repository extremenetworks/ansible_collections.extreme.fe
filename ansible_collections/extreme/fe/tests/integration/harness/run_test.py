#!/usr/bin/env python3
"""Execute playbooks listed in a test summary YAML file and validate Ansible output."""
from __future__ import annotations

import argparse
import datetime as _dt
import http.client
import html
import json
import os
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import time
import sqlite3
import textwrap
import tempfile
import urllib.request
from collections import defaultdict
from functools import lru_cache

from coverage import numbits
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import yaml
from coverage.data import CoverageData


def _resolve_ansible_root() -> Path:
    env_path = os.environ.get("ANSIBLE")
    if env_path:
        root = Path(env_path).expanduser()
        if not root.is_absolute():
            root = root.resolve()
        return root

    script_path = Path(__file__).resolve()
    for ancestor in script_path.parents:
        candidate = ancestor
        if (candidate / "galaxy.yml").is_file():
            return candidate

    # Fallback to the directory containing this script if the expected layout is missing.
    return script_path.parent

DEFAULT_LOG_PATH = Path("/tmp/run_test.log")
LINE_WIDTH = 80
LOG_PATH = DEFAULT_LOG_PATH
DASHBOARD_PATH = Path("/tmp/run_test_dashboard.html")
LOG_LINE_COUNT = 0
REPO_ROOT = _resolve_ansible_root()
TEST_DIR = (REPO_ROOT / "tests" / "integration" / "harness").resolve()
TEST_TOOLS_DIR = (TEST_DIR / "tools").resolve()
PLAYBOOK_DIR = (REPO_ROOT / "playbooks").resolve()
COMPONENTS_DIR = (TEST_DIR / "components").resolve()
INVENTORY_ROOT = (TEST_DIR / "cfg").resolve()
ANSIBLE_CONFIG_PATH = (INVENTORY_ROOT / "ansible.cfg").resolve()
DEFAULT_KEYS = ["ok", "changed", "unreachable", "failed", "skipped", "rescued", "ignored"]
DEFAULT_COLLECTIONS_PATHS = "{}".format(
    ':'.join([
        str((REPO_ROOT / 'collections').resolve()),
        str(Path('~/.ansible/collections').expanduser()),
        '/usr/share/ansible/collections',
    ])
)

COVERAGE_ENV_FLAG = "ANSIBLE_TEST_COVERAGE_CONFIG"

DEFAULT_DASHBOARD_PUSH_URL = os.environ.get(
    "RUN_TEST_DASHBOARD_PUSH_URL",
    "http://127.0.0.1:4000/update",
)


class DashboardPushClient:
    """Push rendered dashboard updates to an external web server."""

    def __init__(self, url: Optional[str], *, timeout: float = 1.0) -> None:
        normalized = (url or "").strip()
        if not normalized or normalized.lower() in {"0", "false", "off", "none"}:
            self._url: Optional[str] = None
        else:
            self._url = normalized
        self._timeout = timeout
        self._disabled = self._url is None
        self._warned = False

    def send(self, content: str) -> None:
        if self._disabled or not content or self._url is None:
            return
        payload = json.dumps({"content": content}).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response.read()
        except Exception as exc:  # noqa: BLE001 - best-effort network call
            if not self._warned:
                print(f"[run_test] dashboard push disabled ({exc})", file=sys.stderr)
                self._warned = True
            self._disabled = True


def _collection_identity() -> tuple[str, str]:
    """Return the namespace and collection name used for this project."""

    namespace = os.environ.get("ANSIBLE_TEST_NAMESPACE", "local")
    collection = os.environ.get("ANSIBLE_TEST_COLLECTION", "extreme_fe")
    return namespace, collection


def _coverage_requested() -> bool:
    value = os.environ.get(COVERAGE_ENV_FLAG)
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"python", "1", "true", "yes", "on"}


def _ensure_coverage_configuration(base: Path) -> tuple[Path, Path, Path]:
    tests_dir = base / "tests"
    output_dir = tests_dir / "output"
    data_dir = output_dir / "data"
    coverage_dir = output_dir / "coverage"
    support_dir = output_dir / ".coverage_support"
    for directory in (tests_dir, output_dir, data_dir, coverage_dir, support_dir):
        directory.mkdir(parents=True, exist_ok=True)
    sitecustomize_path = support_dir / "sitecustomize.py"
    sitecustomize_content = textwrap.dedent(
        '''
        """Coverage bootstrap for child Python processes."""

        import os as _os

        if _os.environ.get("COVERAGE_PROCESS_START"):
            try:
                import coverage as _coverage

                _coverage.process_startup()
            except Exception:
                pass
        '''
    ).strip() + "\n"
    try:
        if not sitecustomize_path.exists() or sitecustomize_path.read_text() != sitecustomize_content:
            sitecustomize_path.write_text(sitecustomize_content)
    except OSError:
        pass
    rc_path = base / "coverage.rc"
    namespace, collection = _collection_identity()
    collection_plugins_dir = (
        base
        / "ansible_collections"
        / namespace
        / collection
        / "plugins"
    )
    modules_path = (collection_plugins_dir / "modules").resolve()
    httpapi_path = (collection_plugins_dir / "httpapi").resolve()
    legacy_modules_path = (base / "plugins" / "modules").resolve()
    legacy_httpapi_path = (base / "plugins" / "httpapi").resolve()
    remote_tmp_path = (Path.home() / ".ansible" / "tmp").resolve()
    system_tmp_path = Path(tempfile.gettempdir()).resolve()
    collection_root = (
        base / "ansible_collections" / namespace / collection
    ).resolve()
    repo_modules_path = (Path.cwd() / "ansible_collections" / namespace / collection / "plugins" / "modules").resolve()
    repo_legacy_modules_path = (Path.cwd() / "plugins" / "modules").resolve()
    coverage_sources: list[Path] = []
    for candidate in (
        modules_path,
        repo_modules_path,
        legacy_modules_path,
        repo_legacy_modules_path,
        remote_tmp_path,
        system_tmp_path,
    ):
        if candidate and candidate.exists() and candidate not in coverage_sources:
            coverage_sources.append(candidate)
    if not coverage_sources:
        coverage_sources = [modules_path]
    source_lines = "\n            ".join(str(path) for path in coverage_sources)
    rc_content = textwrap.dedent(f"""
        [run]
        branch = True
        parallel = True
        concurrency = multiprocessing
        source =
            {source_lines or modules_path}

        [paths]
        source =
            {collection_root}
            {modules_path}
            {httpapi_path}
            {legacy_modules_path}
            {legacy_httpapi_path}
            {remote_tmp_path}
            {system_tmp_path}

        [html]
        directory = {coverage_dir.resolve()}
        title = Extreme FE Coverage

        [report]
        include =
            ansible_collections/local/extreme_fe/plugins/modules/*
    """).strip() + "\n"
    try:
        if not rc_path.exists() or rc_path.read_text() != rc_content:
            rc_path.write_text(rc_content)
    except OSError:
        pass
    return rc_path, data_dir, support_dir


def _normalize_coverage_paths(data_file: Path, base: Path) -> None:
    if not data_file.is_file():
        return
    try:
        conn = sqlite3.connect(str(data_file))
    except sqlite3.Error:
        return
    try:
        cursor = conn.cursor()
        modules_dir = (base / 'plugins' / 'modules').resolve()
        collection_modules_dir = (base / 'ansible_collections' / _collection_identity()[0] / _collection_identity()[1] / 'plugins' / 'modules').resolve()
        replacements = []
        if modules_dir.is_dir():
            for module_path in modules_dir.glob('*.py'):
                remote_suffix = f"ansible_module_{module_path.name}"
                replacements.append((str(module_path.resolve()), remote_suffix))
        httpapi_dir = (base / 'plugins' / 'httpapi').resolve()
        if httpapi_dir.is_dir():
            for api_path in httpapi_dir.glob('*.py'):
                remote_suffix = api_path.name
                replacements.append((str(api_path.resolve()), remote_suffix))
        if collection_modules_dir.is_dir():
            for module_path in collection_modules_dir.glob('*.py'):
                replacements.append((str(module_path.resolve()), module_path.name))
        for target, remote in replacements:
            pattern = f"%/{remote}"
            try:
                cursor.execute(
                    "UPDATE file SET path = ? WHERE path LIKE ?",
                    (target, pattern),
                )
            except sqlite3.Error:
                continue
        payload_marker = "ansible_local.extreme_fe"
        rows = cursor.execute("SELECT id, path FROM file").fetchall()
        for fid, current in rows:
            if payload_marker not in current:
                continue
            module_name = Path(current).name
            candidate = None
            for search_dir in (collection_modules_dir, modules_dir):
                if not search_dir.is_dir():
                    continue
                module_path = search_dir / module_name
                if module_path.is_file():
                    candidate = module_path.resolve()
                    break
            if candidate is not None:
                try:
                    cursor.execute("UPDATE file SET path = ? WHERE id = ?", (str(candidate), fid))
                except sqlite3.Error:
                    pass
        conn.commit()
    finally:
        conn.close()


def _populate_line_bits_from_arcs(data_file: Path) -> None:
    if not data_file.is_file():
        return
    data = CoverageData(basename=str(data_file))
    try:
        data.read()
    except Exception:
        return
    updates: Dict[str, set[int]] = {}
    for filename in data.measured_files():
        arcs = data.arcs(filename)
        lines = data.lines(filename) or []
        if not lines and arcs:
            lines = {line for arc in arcs for line in arc if line and line > 0}
        if lines:
            updates[str(filename)] = set(lines)
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(str(data_file))
        cursor = conn.cursor()
        context_row = cursor.execute("SELECT id FROM context WHERE context = ''").fetchone()
        if context_row is None:
            cursor.execute("INSERT INTO context(context) VALUES ('')")
            context_id = cursor.lastrowid
        else:
            context_id = context_row[0]
        for filename, lines in updates.items():
            file_row = cursor.execute("SELECT id FROM file WHERE path = ?", (filename,)).fetchone()
            if not file_row:
                continue
            file_id = file_row[0]
            cursor.execute("DELETE FROM arc WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM line_bits WHERE file_id = ?", (file_id,))
            sorted_lines = sorted(lines)
            if not sorted_lines:
                continue
            try:
                bits_bytes = numbits.nums_to_numbits(sorted_lines)
            except AttributeError:  # coverage < 7.6 compatibility
                legacy_bits = numbits.numbits_from_list(sorted_lines)
                bits_bytes = legacy_bits.to_bytes()
            cursor.execute(
                "INSERT INTO line_bits (file_id, context_id, numbits) VALUES (?, ?, ?)",
                (file_id, context_id, sqlite3.Binary(bits_bytes)),
            )
        # Remove remaining arc data to avoid mixing branch and line metrics.
        cursor.execute("DELETE FROM arc")
        cursor.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('has_arcs', '0')"
        )
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

def _augment_pythonpath(env: Dict[str, str], extra: Path) -> None:
    """Prepend a directory to PYTHONPATH within *env* if not already present."""

    path_str = str(extra)
    existing = env.get("PYTHONPATH")
    if existing:
        parts = existing.split(os.pathsep)
        if path_str in parts:
            return
        env["PYTHONPATH"] = os.pathsep.join([path_str, existing])
    else:
        env["PYTHONPATH"] = path_str


@lru_cache(maxsize=4)
def _discover_ansible_python_paths(ansible_playbook_path: str) -> List[Path]:
    """Return directories to add to PYTHONPATH for importing ansible."""

    try:
        result = subprocess.run(
            [ansible_playbook_path, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []

    output = "".join(filter(None, [result.stdout, result.stderr]))
    pattern = re.compile(r"ansible python module location\s*=\s*(.+)")
    candidates: List[Path] = []

    for match in pattern.findall(output):
        candidate = Path(match.strip())
        if not candidate.exists():
            continue
        if (candidate / "__init__.py").is_file():
            candidate = candidate.parent
        if candidate.is_dir():
            candidates.append(candidate.resolve())

    return candidates


def _safe_remove(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    except FileNotFoundError:
        pass


def _purge_coverage_artifacts(base_dir: Path, data_dir: Path) -> None:
    coverage_dir = data_dir.parent / "coverage"
    for pattern in ("module=python-*", ".coverage", ".coverage.*"):
        for candidate in data_dir.glob(pattern):
            _safe_remove(candidate)
    for candidate in coverage_dir.glob("*"):
        _safe_remove(candidate)
    _safe_remove(base_dir / ".coverage")
    for candidate in Path.cwd().glob(".coverage*"):
        _safe_remove(candidate)


TRAFFIC_PC_REMOTE_SCRIPT = "~ubuntu/set-ipv4.sh"
PING_DEFAULT_COMMAND = "ping"
PLAY_RECAP_RE = re.compile(
    r"^(?P<host>\S+)\s+:\s+ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+"
    r"unreachable=(?P<unreachable>\d+)\s+failed=(?P<failed>\d+)\s+skipped=(?P<skipped>\d+)\s+"
    r"rescued=(?P<rescued>\d+)\s+ignored=(?P<ignored>\d+)\s*$",
    re.MULTILINE,
)

INCLUDE_DIRECTIVE_RE = re.compile(
    r"^\s*include\s+(?:<(?P<bracket>[^>]+)>\s*|(?P<plain>.+))$",
    re.IGNORECASE,
)


@dataclass
class HostConnectionInfo:
    name: str
    address: str
    port: int
    ssh_port: int
    base_path: str
    username: str
    password: str
    use_ssl: bool
    validate_certs: bool

    @property
    def api_path(self) -> str:
        base = (self.base_path or "").rstrip("/")
        path = f"{base}/v0/state/openapi" if base else "/v0/state/openapi"
        return path if path.startswith("/") else f"/{path}"


@dataclass
class TrafficPCConfig:
    host: str
    commands: list[TrafficPCCommand]


@dataclass
class ScriptConfig:
    file: str
    options: List[str] = field(default_factory=list)
    fatal: bool = False


@dataclass
class TestConfig:
    name: str
    playbooks: List["PlaybookConfig"]
    traffic_pcs: List[TrafficPCConfig]
    scripts: List[ScriptConfig]
    inventory: Optional[Path]
    playbook_args: Optional[str]


@dataclass
class PlaybookConfig:
    file: str
    expectations: Dict[str, Union[int, str]]
    inventory: Optional[Path]
    playbook_args: Optional[str]


@dataclass
class TrafficPCCommand:
    command: str
    repeat: int = 0
    label: Optional[str] = None


@dataclass
class LogEntry:
    message: str
    stream: bool = False


class StatusBoard:
    """Manage inline status updates for parallel host checks."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._rendered = False

    def add_line(self, line: str) -> int:
        self.lines.append(line)
        print(line, flush=True)
        self._rendered = True
        return len(self.lines) - 1

    def update_line(self, index: int, line: str) -> None:
        if index < 0 or index >= len(self.lines):
            return
        self.lines[index] = line
        if not self._rendered:
            return
        total = len(self.lines)
        if total:
            sys.stdout.write(f"\033[{total}F")
        for current in self.lines:
            sys.stdout.write("\033[K")
            sys.stdout.write(current + "\n")
        sys.stdout.flush()


class Dashboard:
    """Render an HTML dashboard with live progress for the test runner."""

    STATUS_RUN = "RUN"
    STATUS_PASS = "PASS"
    STATUS_FAIL = "FAIL"

    def __init__(
        self,
        output_path: Path,
        summary_file: Path,
        *,
        push_url: Optional[str] = DEFAULT_DASHBOARD_PUSH_URL,
    ) -> None:
        self.output_path = output_path
        self.summary_file = summary_file.resolve()
        self.log_path: Optional[Path] = None
        self.status = self.STATUS_RUN
        self.start_time: Optional[_dt.datetime] = None
        self.end_time: Optional[_dt.datetime] = None
        self.prechecks: list[dict[str, Any]] = []
        self.tests: list[dict[str, Any]] = []
        self.coverage_entries: list[dict[str, Any]] = []
        self.coverage_overall: Optional[float] = None
        self.coverage_ready = False
        self.coverage_errors: list[str] = []
        self.coverage_html_path: Optional[Path] = None
        self.last_updated: Optional[_dt.datetime] = None
        self._last_content = ""
        self.switch_logs: list[dict[str, str]] = []
        self.file_prefix: Optional[str] = None
        self.browser_prefix: Optional[str] = None
        self._publisher = DashboardPushClient(push_url)

    def set_log_path(self, log_path: Path) -> None:
        try:
            self.log_path = log_path.resolve()
        except Exception:
            self.log_path = log_path
        self.render()

    def set_coverage_html_path(self, coverage_html_path: Path) -> None:
        try:
            self.coverage_html_path = coverage_html_path.resolve()
        except Exception:
            self.coverage_html_path = coverage_html_path
        self.render()

    def set_file_prefix(self, prefix: Optional[str]) -> None:
        if prefix is None:
            normalized: Optional[str] = None
        else:
            normalized = str(prefix).strip()
            if not normalized:
                normalized = None
        if normalized == self.file_prefix:
            return
        self.file_prefix = normalized
        self.render()

    def set_browser_prefix(self, prefix: Optional[str]) -> None:
        if prefix is None:
            normalized: Optional[str] = None
        else:
            normalized = str(prefix).strip()
            if not normalized:
                normalized = None
        if normalized == self.browser_prefix:
            return
        self.browser_prefix = normalized
        self.render()

    def set_start(self, start_time: _dt.datetime) -> None:
        self.start_time = start_time
        self.end_time = None
        if self.status != self.STATUS_FAIL:
            self.status = self.STATUS_RUN
        self.render()

    def set_status(self, status: str) -> None:
        normalized = str(status).upper()
        if normalized not in {self.STATUS_RUN, self.STATUS_PASS, self.STATUS_FAIL}:
            normalized = self.STATUS_RUN
        if self.status == self.STATUS_FAIL and normalized != self.STATUS_FAIL:
            # Preserve failure status once it occurs.
            self.render()
            return
        if self.status != normalized:
            self.status = normalized
        self.render()

    def register_tests(self, tests: Sequence[TestConfig]) -> None:
        self.tests = []
        for idx, test in enumerate(tests, start=1):
            self.tests.append(
                {
                    "index": idx,
                    "name": test.name,
                    "status": "PENDING",
                    "duration": "--:--:--",
                    "started_at": None,
                    "finished_at": None,
                    "detail": "",
                    "log_line": None,
                }
            )
        self.render()

    def set_switch_logs(self, logs: Sequence[tuple[str, Path]]) -> None:
        entries: list[dict[str, str]] = []
        for name, path in logs:
            try:
                resolved = Path(path).resolve()
            except Exception:
                resolved = Path(path)
            entries.append({"name": str(name), "path": str(resolved)})
        self.switch_logs = entries
        self.render()

    def mark_precheck_running(self, name: str) -> None:
        entry = None
        for current in self.prechecks:
            if current.get("name") == name:
                entry = current
                break
        if entry is None:
            self.prechecks.append({"name": name, "status": "RUN", "details": []})
        else:
            entry["status"] = "RUN"
            entry["details"] = []
        self.render()

    def update_precheck(self, name: str, success: bool, details: Optional[Sequence[str]] = None) -> None:
        entry = None
        for current in self.prechecks:
            if current["name"] == name:
                entry = current
                break
        status_text = "PASS" if success else "FAIL"
        detail_list = [str(line) for line in (details or []) if str(line).strip()]
        if entry is None:
            self.prechecks.append({"name": name, "status": status_text, "details": detail_list})
        else:
            entry["status"] = status_text
            entry["details"] = detail_list
        if not success:
            self.status = self.STATUS_FAIL
        self.render()

    def mark_test_running(self, index: int) -> None:
        entry = self._get_test_entry(index)
        if entry is None:
            return
        entry["status"] = "RUN"
        if entry["started_at"] is None:
            entry["started_at"] = _dt.datetime.now()
        if self.status != self.STATUS_FAIL:
            self.status = self.STATUS_RUN
        self._refresh_test_duration(entry)
        self.render()

    def update_test_progress(self, index: int, duration: Optional[str] = None) -> None:
        entry = self._get_test_entry(index)
        if entry is None or entry["status"] != "RUN":
            return
        if duration is not None:
            entry["duration"] = duration
        else:
            self._refresh_test_duration(entry)
        self.render()

    def mark_test_result(
        self,
        index: int,
        success: bool,
        duration: str,
        detail: Optional[str] = None,
        log_line: Optional[int] = None,
    ) -> None:
        entry = self._get_test_entry(index)
        if entry is None:
            return
        entry["status"] = "PASS" if success else "FAIL"
        entry["duration"] = duration
        entry["finished_at"] = _dt.datetime.now()
        if entry["started_at"] is None:
            entry["started_at"] = entry["finished_at"]
        if detail:
            entry["detail"] = detail
        if log_line is not None:
            entry["log_line"] = log_line
        if success:
            if self.status != self.STATUS_FAIL:
                remaining = any(item["status"] in {"PENDING", "RUN"} for item in self.tests)
                self.status = self.STATUS_RUN if remaining else self.STATUS_PASS
        else:
            self.status = self.STATUS_FAIL
        self.render()

    def update_coverage(
        self,
        overall: Optional[float],
        entries: Sequence[dict[str, Any]],
        errors: Optional[Sequence[str]] = None,
    ) -> None:
        self.coverage_ready = True
        self.coverage_overall = overall
        normalized: list[dict[str, Any]] = []
        for entry in entries:
            name = str(entry.get("name", "")).strip()
            percent_value = float(entry.get("percent", 0.0))
            normalized.append(
                {
                    "name": name,
                    "display": self._shorten_name(name),
                    "percent": max(0.0, min(percent_value, 100.0)),
                    "is_total": name.upper() == "TOTAL",
                    "raw": entry,
                }
            )
        self.coverage_entries = normalized
        self.coverage_errors = [str(line) for line in (errors or []) if str(line).strip()]
        self.render()

    def finalize(self, success: bool) -> None:
        self.end_time = _dt.datetime.now()
        if not success:
            self.status = self.STATUS_FAIL
        elif self.status != self.STATUS_FAIL:
            self.status = self.STATUS_PASS
        self.render()

    def render(self) -> None:
        if self.start_time is None:
            start_display = "--"
            duration_display = "--:--:--"
        else:
            reference = self.end_time or _dt.datetime.now()
            if reference < self.start_time:
                reference = self.start_time
            delta_seconds = max((reference - self.start_time).total_seconds(), 0.0)
            duration_display = format_duration(delta_seconds)
            start_display = self.start_time.isoformat(sep=" ", timespec="seconds")

        now = _dt.datetime.now()
        self.last_updated = now
        last_updated_display = now.isoformat(sep=" ", timespec="seconds")

        total_tests = len(self.tests)
        for entry in self.tests:
            if entry["status"] == "RUN":
                self._refresh_test_duration(entry)
        tests_run = sum(1 for entry in self.tests if entry["status"] in {"PASS", "FAIL"})
        tests_passed = sum(1 for entry in self.tests if entry["status"] == "PASS")
        tests_failed = sum(1 for entry in self.tests if entry["status"] == "FAIL")
        tests_completed = tests_run
        progress_percent = (tests_completed / total_tests) * 100.0 if total_tests else 0.0
        progress_percent_display = self._format_percent(progress_percent)
        progress_completion_display = f"{tests_completed}/{total_tests}" if total_tests else "0/0"

        status_class_map = {
            self.STATUS_RUN: "status-run",
            self.STATUS_PASS: "status-pass",
            self.STATUS_FAIL: "status-fail",
        }
        status_badge_class = status_class_map.get(self.status, "status-run")

        coverage_display = "--"
        coverage_metric_class = ""
        if self.coverage_overall is not None:
            coverage_display = self._format_percent(self.coverage_overall)
            coverage_metric_class = " metric-pass" if self.coverage_overall >= 75 else " metric-fail"

        log_html = "--"
        if self.log_path is not None:
            link_info = self._compose_link(self.log_path)
            log_html = (
                f'<a href="{html.escape(link_info["href"], quote=True)}" target="_blank">'
                f"{html.escape(str(self.log_path))}</a>"
            )

        if self.switch_logs:
            link_parts: list[str] = []
            for item in self.switch_logs:
                path_obj = Path(item["path"])
                link_info = self._compose_link(path_obj)
                name = html.escape(item["name"])
                href = html.escape(link_info["href"], quote=True)
                link_parts.append(f'<a href="{href}" target="_blank">{name}</a>')
            switch_links = ", ".join(link_parts)
            switch_logs_html = f'<div><strong>Switch logs:</strong> {switch_links}</div>'
        else:
            switch_logs_html = '<div><strong>Switch logs:</strong> <span class="muted">Pending transfer</span></div>'

        coverage_html_link = "--"
        if self.coverage_html_path is not None and self.coverage_html_path.exists():
            link_info = self._compose_browser_link(self.coverage_html_path)
            coverage_html_link = (
                f'<a href="{html.escape(link_info["href"], quote=True)}" target="_blank">'
                f"{html.escape(str(self.coverage_html_path))}</a>"
            )

        precheck_items: list[str] = []
        for entry in self.prechecks:
            entry_status = entry["status"]
            if entry_status == "PASS":
                badge_class = "status-pass"
            elif entry_status == "FAIL":
                badge_class = "status-fail"
            else:
                badge_class = "status-run"
            details_html = ""
            if entry["details"]:
                detail_lines = "<br/>".join(html.escape(str(line)) for line in entry["details"])
                details_html = f'<div class="precheck-details">{detail_lines}</div>'
            precheck_items.append(
                """
                <li class="precheck-item">
                    <div class="precheck-header">
                        <span class="status-badge {badge}">{status}</span>
                        <span class="precheck-name">{name}</span>
                    </div>
                    {details}
                </li>
                """.format(
                    badge=badge_class,
                    status=entry_status,
                    name=html.escape(entry["name"]),
                    details=details_html,
                )
            )
        if precheck_items:
            prechecks_html = '<ul class="precheck-list">' + "".join(precheck_items) + "</ul>"
        else:
            prechecks_html = '<p class="muted">Pre-check results will appear here as they run.</p>'

        coverage_body: str
        if not self.coverage_ready:
            coverage_body = '<p class="muted">Coverage data will appear after tests complete.</p>'
        else:
            if self.coverage_entries:
                bar_rows: list[str] = []
                for entry in self.coverage_entries:
                    percent = entry["percent"]
                    percent_text = self._format_percent(percent)
                    css_classes = ["bar-fill"]
                    if entry["is_total"]:
                        css_classes.append("total")
                    elif percent < 75.0:
                        css_classes.append("fail")
                    bar_rows.append(
                        """
                        <div class="bar-row" title="{full}">
                            <span class="bar-label">{label}</span>
                            <div class="bar-track">
                                <div class="{classes}" style="width: {width}%;"></div>
                            </div>
                            <span class="bar-percent">{percent}</span>
                        </div>
                        """.format(
                            full=html.escape(entry["name"] or entry["display"]),
                            label=html.escape(entry["display"] or entry["name"]),
                            classes=" ".join(css_classes),
                            width=f"{percent:.1f}",
                            percent=percent_text,
                        )
                    )
                coverage_body = '<div class="coverage-bars">' + "".join(bar_rows) + "</div>"
            else:
                coverage_body = '<p class="muted">Coverage data was not produced.</p>'

            if self.coverage_errors:
                error_lines = "<br/>".join(html.escape(line) for line in self.coverage_errors)
                coverage_body += '<div class="alert">{}</div>'.format(error_lines)

        if self.tests:
            rows: list[str] = []
            for entry in self.tests:
                status_text = entry["status"]
                pill_class = {
                    "PASS": "pass",
                    "FAIL": "fail",
                    "RUN": "run",
                }.get(status_text, "pending")
                detail_attr = f' title="{html.escape(entry["detail"])}"' if entry.get("detail") else ""
                link_info = self._build_log_links(entry.get("log_line"))
                if link_info:
                    status_html = (
                        f'<a class="status-pill status-button {pill_class}" '
                        f'href="{html.escape(link_info["href"], quote=True)}" '
                        f'data-fallback="{html.escape(link_info["fallback"], quote=True)}" '
                        f'target="_blank">{status_text}</a>'
                    )
                else:
                    status_html = f'<span class="status-pill {pill_class}">{status_text}</span>'
                row_html = (
                    f"<tr{detail_attr}>"
                    f"<td class=\"col-num\">{entry['index']:02d}</td>"
                    f"<td>{html.escape(entry['name'])}</td>"
                    f"<td>{html.escape(entry['duration'])}</td>"
                    f"<td>{status_html}</td>"
                    "</tr>"
                )
                rows.append(row_html)
            tests_html = (
                """
                <table class="results-table">
                    <thead>
                        <tr>
                            <th class="col-num">#</th>
                            <th>Description</th>
                            <th>Duration</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
                """.format(rows="".join(rows))
            )
        else:
            tests_html = '<p class="muted">Tests have not started yet.</p>'

        summary_path_display = html.escape(str(self.summary_file))
        summary_link_info = self._compose_link(self.summary_file)
        summary_link_html = (
            f'<a href="{html.escape(summary_link_info["href"], quote=True)}" target="_blank">'
            f"{summary_path_display}</a>"
        )
        tests_total_display = f"{tests_run}/{total_tests}" if total_tests else "0/0"

        html_content = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>Extreme FE Test Dashboard</title>
    <style>
        :root {{
            color-scheme: dark;
        }}
        * {{
            box-sizing: border-box;
        }}
        body {{
            margin: 0;
            padding: 2rem;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a, #111827); 
            color: #e2e8f0;
        }}
        main {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            margin: 0;
            font-size: 2rem;
            letter-spacing: 0.02em;
        }}
        h2 {{
            font-size: 1.4rem;
            margin-bottom: 1rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: #93c5fd;
        }}
        section {{
            background: rgba(15, 23, 42, 0.55);
            border-radius: 16px;
            padding: 1.75rem;
            margin-bottom: 2rem;
            border: 1px solid rgba(148, 163, 184, 0.2);
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.35);
        }}
        .summary-section {{
            position: relative;
            overflow: visible;
        }}
        .summary-fixed {{
            position: sticky;
            top: 0;
            z-index: 20;
            margin: -1.75rem -1.75rem 1.5rem;
            padding: 1.75rem;
            border-radius: 16px 16px 12px 12px;
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(148, 163, 184, 0.25);
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.35);
        }}
        .summary-body {{
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }}
        .summary-status {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-top: 1.25rem;
        }}
        .status-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.45rem 1.15rem;
            border-radius: 999px;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            border: 1px solid transparent;
        }}
        .status-run {{
            background: rgba(251, 191, 36, 0.18);
            color: #fbbf24;
            border-color: rgba(251, 191, 36, 0.45);
        }}
        .status-pass {{
            background: rgba(52, 211, 153, 0.18);
            color: #34d399;
            border-color: rgba(52, 211, 153, 0.45);
        }}
        .status-fail {{
            background: rgba(248, 113, 113, 0.18);
            color: #f87171;
            border-color: rgba(248, 113, 113, 0.45);
        }}
        .summary-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            font-size: 0.95rem;
            color: #cbd5f5;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-top: 1.5rem;
        }}
        .metric {{
            background: rgba(17, 24, 39, 0.8);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            border: 1px solid rgba(148, 163, 184, 0.25);
        }}
        .metric-pass {{
            border-color: rgba(52, 211, 153, 0.45);
            color: #34d399;
        }}
        .metric-fail {{
            border-color: rgba(248, 113, 113, 0.45);
            color: #f87171;
        }}
        .metric .label {{
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.09em;
            color: #94a3b8;
        }}
        .metric .value {{
            display: block;
            margin-top: 0.35rem;
            font-size: 1.75rem;
            font-weight: 600;
        }}
        .overall-progress {{
            margin-top: 1.75rem;
        }}
        .progress-label {{
            font-size: 0.9rem;
            color: #cbd5f5;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}
        .progress-track {{
            width: 100%;
            height: 12px;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.25);
            overflow: hidden;
            box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.6);
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #22d3ee, #a855f7);
            transition: width 0.4s ease;
        }}
        .progress-summary {{
            margin-top: 0.5rem;
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: #94a3b8;
        }}
        .config-info {{
            margin-top: 1.75rem;
            display: grid;
            gap: 0.65rem;
            font-size: 0.95rem;
        }}
        .config-info a {{
            color: #93c5fd;
            text-decoration: none;
        }}
        .config-info a:hover {{
            text-decoration: underline;
        }}
        .precheck-container {{
            margin-top: 2rem;
        }}
        .precheck-list {{
            list-style: none;
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
        }}
        .precheck-item {{
            background: rgba(17, 24, 39, 0.75);
            border-radius: 12px;
            padding: 0.9rem 1rem;
            border: 1px solid rgba(148, 163, 184, 0.2);
        }}
        .precheck-header {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        .precheck-name {{
            font-weight: 600;
            letter-spacing: 0.03em;
        }}
        .precheck-details {{
            margin-top: 0.55rem;
            font-size: 0.85rem;
            color: #94a3b8;
            line-height: 1.4;
        }}
        .coverage-bars {{
            display: flex;
            flex-direction: column;
            gap: 0.65rem;
        }}
        .bar-row {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        .bar-label {{
            flex: 0 0 320px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            direction: rtl;
            text-align: left;
            unicode-bidi: plaintext;
        }}
        .bar-track {{
            flex: 1;
            height: 18px;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.25);
            overflow: hidden;
        }}
        .bar-fill {{
            height: 100%;
            background: #34d399;
            transition: width 0.3s ease;
        }}
        .bar-fill.fail {{
            background: #f87171;
        }}
        .bar-fill.total {{
            background: #60a5fa;
        }}
        .bar-percent {{
            width: 70px;
            text-align: right;
            font-weight: 600;
        }}
        .results-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
            overflow: hidden;
            border-radius: 12px;
        }}
        .results-table thead tr {{
            background: rgba(15, 23, 42, 0.8);
        }}
        .results-table th,
        .results-table td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.18);
            text-align: left;
        }}
        .results-table tbody tr:hover {{
            background: rgba(148, 163, 184, 0.08);
        }}
        .status-pill {{
            display: inline-flex;
            align-items: center;
            padding: 0.3rem 0.75rem;
            border-radius: 999px;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            text-decoration: none;
            border: 1px solid transparent;
            transition: filter 0.2s ease;
        }}
        .status-pill.pass {{
            background: rgba(52, 211, 153, 0.18);
            color: #34d399;
        }}
        .status-pill.fail {{
            background: rgba(248, 113, 113, 0.18);
            color: #f87171;
        }}
        .status-pill.run {{
            background: rgba(251, 191, 36, 0.18);
            color: #fbbf24;
        }}
        .status-pill.pending {{
            background: rgba(148, 163, 184, 0.18);
            color: #cbd5f5;
        }}
        .status-button {{
            cursor: pointer;
        }}
        .status-button.pass {{
            border-color: rgba(52, 211, 153, 0.45);
        }}
        .status-button.fail {{
            border-color: rgba(248, 113, 113, 0.45);
        }}
        .status-button.run {{
            border-color: rgba(251, 191, 36, 0.45);
        }}
        .status-pill:hover {{
            filter: brightness(1.1);
        }}
        .col-num {{
            width: 70px;
            font-variant-numeric: tabular-nums;
        }}
        .muted {{
            color: #94a3b8;
        }}
        .alert {{
            margin-top: 1.25rem;
            background: rgba(248, 113, 113, 0.15);
            border: 1px solid rgba(248, 113, 113, 0.45);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            color: #fecaca;
        }}
        @media (max-width: 720px) {{
            body {{
                padding: 1.25rem;
            }}
            .summary-fixed {{
                margin: -1.25rem -1.25rem 1.25rem;
                padding: 1.25rem;
            }}
            .bar-label {{
                flex: 0 0 180px;
            }}
            .summary-meta {{
                flex-direction: column;
                gap: 0.5rem;
                align-items: flex-start;
            }}
        }}
    </style>
</head>
<body>
    <main>
        <section class="summary-section">
            <div class="summary-fixed">
                <div class="summary-status">
                <span class="status-badge {status_badge_class}">{self.status}</span>
                <div class="summary-meta">
                    <div><strong>Start:</strong> {start_display}</div>
                    <div><strong>Duration:</strong> {duration_display}</div>
                    <div><strong>Last update:</strong> {last_updated_display}</div>
                </div>
                </div>
                <div class="metric-grid">
                    <div class="metric">
                        <span class="label">Tests run</span>
                        <span class="value">{tests_total_display}</span>
                    </div>
                    <div class="metric">
                        <span class="label">Passed</span>
                        <span class="value">{tests_passed}</span>
                    </div>
                    <div class="metric">
                        <span class="label">Failed</span>
                        <span class="value">{tests_failed}</span>
                    </div>
                    <div class="metric{coverage_metric_class}">
                        <span class="label">Coverage</span>
                        <span class="value">{coverage_display}</span>
                    </div>
                </div>
                <div class="overall-progress">
                    <div class="progress-label">Test progress</div>
                    <div class="progress-track">
                        <div class="progress-fill" style="width: {progress_percent:.1f}%;"></div>
                    </div>
                    <div class="progress-summary">
                        <span>{progress_completion_display} complete</span>
                        <span>{progress_percent_display}</span>
                    </div>
                </div>
            </div>
            <div class="summary-body">
                <div class="config-info">
                    <div><strong>Config file:</strong> {summary_link_html}</div>
                    <div><strong>Log file:</strong> {log_html}</div>
                    <div><strong>Coverage report:</strong> {coverage_html_link}</div>
                    {switch_logs_html}
                </div>
                <div class="precheck-container">
                    <h2>Pre-checks</h2>
                    {prechecks_html}
                </div>
            </div>
        </section>
        <section>
            <h2>Code coverage</h2>
            {coverage_body}
        </section>
        <section>
            <h2>Test results</h2>
            {tests_html}
        </section>
    <p class="muted">This page updates live while tests or coverage are running. Dashboard file: {html.escape(str(self.output_path))}</p>
    </main>
    <script>
    document.querySelectorAll('.status-button').forEach(function(button) {{
        button.addEventListener('click', function() {{
            const fallback = button.dataset.fallback;
            if (!fallback) {{
                return;
            }}
            setTimeout(function() {{
                window.open(fallback, '_blank');
            }}, 800);
        }});
    }});
    </script>
</body>
</html>
"""
        changed = self._write_if_changed(html_content)
        if changed:
            self._publisher.send(html_content)

    def _format_percent(self, value: float) -> str:
        if float(value).is_integer():
            return f"{int(round(value))}%"
        return f"{value:.1f}%"

    def _refresh_test_duration(self, entry: dict[str, Any]) -> None:
        started = entry.get("started_at")
        finished = entry.get("finished_at")
        if started is None:
            entry["duration"] = "--:--:--"
            return
        reference = finished or _dt.datetime.now()
        if reference < started:
            reference = started
        seconds = max((reference - started).total_seconds(), 0.0)
        entry["duration"] = format_duration(seconds)

    def _get_test_entry(self, index: int) -> Optional[dict[str, Any]]:
        for entry in self.tests:
            if entry.get("index") == index:
                return entry
        return None

    def _compose_link(self, path: Union[str, Path], line: Optional[int] = None) -> dict[str, str]:
        if isinstance(path, Path):
            path_obj = path
        else:
            path_obj = Path(path)
        try:
            resolved = path_obj.resolve(strict=False)
        except Exception:
            resolved = Path(path_obj)

        resolved_str = str(resolved)

        # Always use a line number, default to 1 if none provided
        effective_line = line if line is not None else 1

        try:
            fallback_base = resolved.as_uri()
        except ValueError:
            if resolved_str.startswith("/"):
                fallback_base = f"file://{resolved_str}"
            else:
                fallback_base = f"file:///{resolved_str}"

        fallback = f"{fallback_base}#L{effective_line}"

        primary: str
        if self.file_prefix:
            prefix = self.file_prefix.rstrip("/")
            path_part = resolved_str
            if not path_part.startswith("/"):
                path_part = "/" + path_part
            primary = f"{prefix}{path_part}:{effective_line}#"
        else:
            primary = f"vscode://file{resolved_str}:{effective_line}"

        return {"href": primary, "fallback": fallback}

    def _compose_browser_link(self, path: Union[str, Path]) -> dict[str, str]:
        """Compose a browser link using browser_prefix for HTML files."""
        if isinstance(path, Path):
            path_obj = path
        else:
            path_obj = Path(path)
        try:
            resolved = path_obj.resolve(strict=False)
        except Exception:
            resolved = Path(path_obj)

        resolved_str = str(resolved)

        try:
            fallback_base = resolved.as_uri()
        except ValueError:
            if resolved_str.startswith("/"):
                fallback_base = f"file://{resolved_str}"
            else:
                fallback_base = f"file:///{resolved_str}"

        fallback = fallback_base

        primary: str
        if self.browser_prefix:
            prefix = self.browser_prefix.rstrip("/")
            path_part = resolved_str
            if path_part.startswith("/"):
                path_part = path_part[1:]  # Remove leading slash for browser URLs
            # Use browser_prefix as-is (don't force http://)
            primary = f"{prefix}/{path_part}"
        else:
            # Fallback to file:// URL if no browser prefix
            primary = fallback

        return {"href": primary, "fallback": fallback}

    def _shorten_name(self, name: str) -> str:
        if not name:
            return ""
        stripped = name.strip()
        if stripped.upper() == "TOTAL":
            return "TOTAL"
        try:
            path_obj = Path(stripped)
            filename = path_obj.name or stripped
            parent = path_obj.parent
            parent_name = parent.name if parent and parent.name else ""
            if parent_name:
                return f"{parent_name}/{filename}"
            return filename
        except Exception:
            return stripped

    def _build_log_links(self, line: Optional[int]) -> Optional[dict[str, str]]:
        if self.log_path is None or line is None:
            return None
        return self._compose_link(self.log_path, line=line)

    def _write_if_changed(self, content: str) -> bool:
        if content == self._last_content:
            return False
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        tmp_path = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(self.output_path)
        except OSError:
            # Best-effort write; ignore failures so tests can proceed.
            pass
        self._last_content = content
        return True

def _to_bool(value: Union[str, int, bool, None], default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: Union[str, int, None], default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def gather_inventory_hosts(inventory_path: Path) -> List[HostConnectionInfo]:
    """Return unique host connection info parsed via ansible-inventory."""
    if not inventory_path.is_file():
        raise FileNotFoundError(f"Inventory file not found: {inventory_path}")

    cmd = ["ansible-inventory", "-i", str(inventory_path), "--list"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to parse inventory {inventory_path}: {detail}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from ansible-inventory for {inventory_path}: {exc}") from exc

    hostvars = data.get("_meta", {}).get("hostvars", {})
    unique_hosts: Dict[str, HostConnectionInfo] = {}
    for host, vars_map in hostvars.items():
        address = str(vars_map.get("ansible_host") or host)

        raw_http_port = vars_map.get("ansible_httpapi_port")
        raw_ssh_port = vars_map.get("ansible_port") or vars_map.get("ansible_ssh_port")

        def _parse_port(value: object, *, default: int = 0) -> int:
            if value is None:
                return default
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return default

        http_port = _parse_port(raw_http_port)
        ssh_port = _parse_port(raw_ssh_port, default=22)
        if ssh_port <= 0:
            ssh_port = 22
        if http_port <= 0:
            http_port = _parse_port(raw_ssh_port)
        info = HostConnectionInfo(
            name=str(host),
            address=address,
            port=http_port,
            ssh_port=ssh_port,
            base_path=str(vars_map.get("ansible_httpapi_base_path") or ""),
            username=str(vars_map.get("ansible_user") or ""),
            password=str(vars_map.get("ansible_password") or ""),
            use_ssl=_to_bool(vars_map.get("ansible_httpapi_use_ssl"), default=True),
            validate_certs=_to_bool(vars_map.get("ansible_httpapi_validate_certs"), default=True),
        )
        unique_hosts.setdefault(info.address, info)

    return list(unique_hosts.values())


def _status_line(title: str, status: str, *, width: int = LINE_WIDTH) -> str:
    tail = f" {status}"
    base = f"{title} "
    available = width - len(base) - len(tail)
    min_dots = 3
    if available < min_dots:
        available = min_dots
    if len(base) + available + len(tail) > width:
        available = max(0, width - len(base) - len(tail))
    if available < 0:
        available = 0
    if len(base) + available + len(tail) > width:
        max_title_len = max(0, width - len(tail) - 1)
        truncated_title = title[:max_title_len]
        base = f"{truncated_title} "
        available = max(0, width - len(base) - len(tail))
    dots = "." * available
    line = f"{base}{dots}{tail}"
    return line[:width]

def _test_status_line(prefix: str, duration: str, status: str, *, width: int = LINE_WIDTH) -> str:
    base = f"{prefix} "
    tail = f" {duration} {status}"
    available = width - len(base) - len(tail)
    if available < 3:
        available = 3
    dots = "." * available
    line = f"{base}{dots}{tail}"
    if len(line) > width:
        return line[:width]
    return line


def _inline_test_status(
    prefix: str,
    duration: str,
    status: str,
    *,
    final: bool = False,
    display_status: Optional[str] = None,
) -> str:
    line = _test_status_line(prefix, duration, status)
    display_line = line
    if display_status is not None and display_status != status:
        display_line = line.replace(status, display_status, 1)
    sys.stdout.write("\r" + display_line.ljust(LINE_WIDTH))
    if final:
        sys.stdout.write("\n")
    sys.stdout.flush()
    return line


def _read_ping_timeout_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


_PING_TIMEOUT_PRIMARY = max(1, _read_ping_timeout_env("RUN_TEST_PING_TIMEOUT", 1))
_PING_TIMEOUT_FALLBACK = max(
    _PING_TIMEOUT_PRIMARY,
    _read_ping_timeout_env("RUN_TEST_PING_FALLBACK_TIMEOUT", 3),
)
_PING_TIMEOUTS: List[int] = []
for timeout in (_PING_TIMEOUT_PRIMARY, _PING_TIMEOUT_FALLBACK):
    if timeout not in _PING_TIMEOUTS:
        _PING_TIMEOUTS.append(timeout)


def _ping_host(address: str) -> bool:
    for timeout in _PING_TIMEOUTS:
        cmd = ["ping", "-c", "1", "-W", str(timeout), address]
        try:
            if (
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode
                == 0
            ):
                return True
        except FileNotFoundError as exc:
            raise RuntimeError("ping command not found on this system") from exc
    return False


def _perform_nos_api_check(info: HostConnectionInfo, timeout: float = 5.0) -> bool:
    port = info.port or (443 if info.use_ssl else 80)
    connection_cls = http.client.HTTPSConnection if info.use_ssl else http.client.HTTPConnection
    conn_kwargs = {"timeout": timeout}
    if info.use_ssl:
        context = ssl.create_default_context()
        if not info.validate_certs:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        conn_kwargs["context"] = context

    conn: Optional[http.client.HTTPConnection] = None
    try:
        conn = connection_cls(info.address, port, **conn_kwargs)
        conn.request("GET", info.api_path)
        response = conn.getresponse()
        # fully read response to allow connection reuse cleanup
        response.read()
        return 200 <= response.status < 300
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _run_enable_nos_api_script(info: HostConnectionInfo) -> Tuple[bool, List[LogEntry]]:
    script_path = TEST_TOOLS_DIR / "fe_exec_cli_cmds.exp"
    cli_file = TEST_TOOLS_DIR / "fe_enable_local_nos-api.cli"
    entries: List[LogEntry] = []
    if not script_path.is_file():
        entries.append(LogEntry(f"Enable NOS-API script not found: {script_path}"))
        return False, entries
    if not cli_file.is_file():
        entries.append(LogEntry(f"Enable NOS-API CLI file not found: {cli_file}"))
        return False, entries
    if not info.username or not info.password:
        entries.append(
            LogEntry(
                "Missing credentials to enable NOS-API; ansible_user/ansible_password are required"
            )
        )
        return False, entries

    cmd = [
        str(script_path),
        str(cli_file),
        info.address,
        info.username,
        info.password,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = (result.stdout or "") + (result.stderr or "")
    if output:
        for line in output.splitlines():
            entries.append(LogEntry(line, stream=False))
    return result.returncode == 0, entries


def _reachability_worker(
    info: HostConnectionInfo,
    title: str,
    *,
    max_attempts: int = 600,
    delay: float = 1.0,
    max_wait_seconds: float = 600.0,
) -> Tuple[bool, List[LogEntry]]:
    start = time.perf_counter()
    attempts_made = 0
    for attempt in range(1, max_attempts + 1):
        attempts_made = attempt
        if _ping_host(info.address):
            return True, []
        if time.perf_counter() - start >= max_wait_seconds:
            break
        time.sleep(delay)

    attempts_text = f"Host {info.address} unreachable after {max(attempts_made, 1)} attempts"
    entries = [LogEntry(attempts_text, stream=False)]
    return False, entries


def _nos_api_worker(info: HostConnectionInfo, title: str) -> Tuple[bool, List[LogEntry]]:
    entries: List[LogEntry] = []

    if _perform_nos_api_check(info):
        return True, entries

    entries.append(
        LogEntry(f"Attempting to enable NOS-API for host {info.address}", stream=False)
    )
    enabled, enable_entries = _run_enable_nos_api_script(info)
    entries.extend(enable_entries)
    if not enabled:
        return False, entries

    time.sleep(10)
    for attempt in range(1, 21):
        if _perform_nos_api_check(info):
            return True, entries
        retry_line = _status_line(title, f"[retry {attempt}/20]")
        entries.append(LogEntry(retry_line, stream=False))
        if attempt < 20:
            time.sleep(3)

    return False, entries


def _run_checks_parallel(
    host_infos: Sequence[HostConnectionInfo],
    title_fn: Callable[[HostConnectionInfo], str],
    worker: Callable[[HostConnectionInfo, str], Tuple[bool, List[LogEntry]]],
) -> Tuple[bool, int, int]:
    total_hosts = len(host_infos)
    if not host_infos:
        return True, 0, 0

    max_workers = min(len(host_infos), max(1, os.cpu_count() or len(host_infos)))
    board = StatusBoard()
    info_context: Dict[str, Tuple[int, str]] = {}

    for info in host_infos:
        title = title_fn(info)
        index = board.add_line(_status_line(title, "[RUN]"))
        info_context[info.address] = (index, title)

    overall = True
    passed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_context: Dict[Future, HostConnectionInfo] = {}
        for info in host_infos:
            future = executor.submit(worker, info, info_context[info.address][1])
            future_to_context[future] = info

        for future in as_completed(future_to_context):
            info = future_to_context[future]
            index, title = info_context[info.address]
            try:
                success, entries = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                success = False
                entries = [LogEntry(f"[Error] {exc}", stream=False)]

            status = "[PASS]" if success else "[FAIL]"
            status_line = _status_line(title, status)
            board.update_line(index, status_line)
            log(status_line, stream=False)

            for entry in entries:
                log(entry.message, stream=entry.stream)

            overall = overall and success
            if success:
                passed_count += 1

    return overall, passed_count, total_hosts


def verify_hosts_reachability(host_infos: Sequence[HostConnectionInfo]) -> Tuple[bool, int, int]:
    return _run_checks_parallel(
        host_infos,
        lambda info: f"-- Checking reachability host: {info.address}",
        _reachability_worker,
    )


def verify_hosts_nos_api(host_infos: Sequence[HostConnectionInfo]) -> Tuple[bool, int, int]:
    return _run_checks_parallel(
        host_infos,
        lambda info: f"-- Checking host {info.address} NOS-API functionality",
        _nos_api_worker,
    )


def log(message: str, *, stream: bool = True) -> int:
    global LOG_LINE_COUNT
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    start_line = LOG_LINE_COUNT + 1
    lines_written = message.count("\n") + 1
    with LOG_PATH.open("a") as fh:
        fh.write(message + "\n")
    LOG_LINE_COUNT += lines_written
    if stream:
        print(message)
    return start_line


def log_raw_output(text: str) -> None:
    """Append raw text to the log while keeping line counts accurate."""
    global LOG_LINE_COUNT
    if text is None:
        return
    normalized = str(text)
    if not normalized:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = not normalized.endswith("\n")
    with LOG_PATH.open("a") as fh:
        fh.write(normalized)
        if needs_newline:
            fh.write("\n")
    LOG_LINE_COUNT += normalized.count("\n")
    if needs_newline:
        LOG_LINE_COUNT += 1


_COLLECTION_WORKDIR: Optional[Path] = None


def _find_collection_root(start: Path) -> Optional[Path]:
    resolved = start.resolve()
    parts = resolved.parts
    for idx, part in enumerate(parts):
        if part == "ansible_collections" and idx + 2 < len(parts):
            return Path(*parts[: idx + 3])
    return None


def _prepare_collection_workdir() -> Path:
    global _COLLECTION_WORKDIR
    if _COLLECTION_WORKDIR is not None:
        return _COLLECTION_WORKDIR
    existing = _find_collection_root(Path.cwd())
    if existing is not None:
        _COLLECTION_WORKDIR = existing
        return existing
    namespace = os.environ.get("ANSIBLE_TEST_NAMESPACE", "local")
    collection = os.environ.get("ANSIBLE_TEST_COLLECTION", "extreme_fe")
    base = Path.cwd() / ".ansible_test_collection" / "ansible_collections" / namespace / collection
    base.mkdir(parents=True, exist_ok=True)
    source = Path.cwd().resolve()
    for item in source.iterdir():
        name = item.name
        if name == ".ansible_test_collection":
            continue
        dest = base / name
        if dest.exists() or dest.is_symlink():
            continue
        target_rel = os.path.relpath(item, dest.parent)
        try:
            dest.symlink_to(target_rel, target_is_directory=item.is_dir())
        except OSError:
            continue
    collection_root = base.parent.parent
    for path_entry in DEFAULT_COLLECTIONS_PATHS.split(":"):
        if not path_entry:
            continue
        source_root = Path(path_entry).expanduser().resolve() / "ansible_collections"
        if not source_root.is_dir():
            continue
        for namespace_dir in source_root.iterdir():
            if not namespace_dir.is_dir():
                continue
            dest_namespace = collection_root / namespace_dir.name
            if dest_namespace.exists():
                continue
            try:
                dest_namespace.symlink_to(namespace_dir, target_is_directory=True)
            except OSError:
                continue
    tests_dir = base / "tests"
    if not tests_dir.exists():
        tests_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tests_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_dir = output_dir / "coverage"
    coverage_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_dir / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    _COLLECTION_WORKDIR = base
    return base



def _run_ansible_test_command(arguments: Sequence[str], *, env: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    """Execute an ansible-test command and return the return code and combined output."""

    workdir = _prepare_collection_workdir()
    workspace_collections = workdir.parent.parent
    collections_paths = f"{workspace_collections}:{DEFAULT_COLLECTIONS_PATHS}"
    base_env = dict(os.environ)
    if env:
        base_env.update(env)
    base_env.setdefault("ANSIBLE_COLLECTIONS_PATHS", collections_paths)
    base_env.setdefault("ANSIBLE_COLLECTIONS_PATH", collections_paths)

    if _coverage_requested():
        rc_path, data_dir, support_dir = _ensure_coverage_configuration(workdir)
        coverage_file = data_dir / ".coverage"
        base_env.setdefault("COVERAGE_RCFILE", str(rc_path))
        base_env.setdefault("COVERAGE_PROCESS_START", str(rc_path))
        base_env.setdefault("COVERAGE_FILE", str(coverage_file))
        _augment_pythonpath(base_env, support_dir)

    cmd = ["ansible-test"] + list(arguments)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=base_env,
        cwd=str(workdir),
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def run_playbook(playbook: Path, inventory: Optional[Path], extra_args: Optional[str]) -> Tuple[int, str]:
    """Run ansible-playbook for the given playbook using ansible-test shell."""
    env = dict(os.environ)
    env["ANSIBLE_CONFIG"] = str(ANSIBLE_CONFIG_PATH)

    ansible_test_path = shutil.which("ansible-test")
    if ansible_test_path is None:
        output = "Required command not found: ansible-test\n"
        log_raw_output(output)
        return 127, output

    ansible_playbook_path = shutil.which("ansible-playbook")
    if ansible_playbook_path is None:
        output = "Required command not found: ansible-playbook\n"
        log_raw_output(output)
        return 127, output


    workdir = _prepare_collection_workdir()
    workspace_collections = workdir.parent.parent
    collections_paths = f"{workspace_collections}:{DEFAULT_COLLECTIONS_PATHS}"
    env.setdefault("ANSIBLE_COLLECTIONS_PATHS", collections_paths)
    env.setdefault("ANSIBLE_COLLECTIONS_PATH", collections_paths)
    coverage_enabled = _coverage_requested()
    rc_path = None
    if coverage_enabled:
        rc_path, data_dir, support_dir = _ensure_coverage_configuration(workdir)
        coverage_file = data_dir / ".coverage"
        env.setdefault("COVERAGE_RCFILE", str(rc_path))
        env.setdefault("COVERAGE_PROCESS_START", str(rc_path))
        env.setdefault("COVERAGE_FILE", str(coverage_file))
        env.setdefault("ANSIBLE_MODULE_NO_ZIP", "1")
        env.setdefault("ANSIBLE_KEEP_REMOTE_FILES", "1")
        env.setdefault(
            "_ANSIBLE_ANSIBALLZ_COVERAGE_CONFIG",
            json.dumps(
                {
                    "config": str(rc_path),
                    "output": str(data_dir / "module"),
                }
            ),
        )
        for path in _discover_ansible_python_paths(ansible_playbook_path):
            _augment_pythonpath(env, path)
        _augment_pythonpath(env, support_dir)
    cmd = [ansible_test_path, "shell"]
    cmd.append("--")
    cmd.append("env")
    cmd.append(f"ANSIBLE_CONFIG={env['ANSIBLE_CONFIG']}")
    if "ANSIBLE_COLLECTIONS_PATHS" in env:
        cmd.append(f"ANSIBLE_COLLECTIONS_PATHS={env['ANSIBLE_COLLECTIONS_PATHS']}")
    if "ANSIBLE_COLLECTIONS_PATH" in env:
        cmd.append(f"ANSIBLE_COLLECTIONS_PATH={env['ANSIBLE_COLLECTIONS_PATH']}")
    if "EXTREME_FE_HTTP_TRACE" in env:
        cmd.append(f"EXTREME_FE_HTTP_TRACE={env['EXTREME_FE_HTTP_TRACE']}")
    if "EXTREME_FE_HTTP_TRACE_PATH" in env:
        cmd.append(f"EXTREME_FE_HTTP_TRACE_PATH={env['EXTREME_FE_HTTP_TRACE_PATH']}")
    if coverage_enabled:
        cmd.append(f"COVERAGE_RCFILE={env['COVERAGE_RCFILE']}")
        cmd.append(f"COVERAGE_PROCESS_START={env['COVERAGE_PROCESS_START']}")
        cmd.append(f"COVERAGE_FILE={env['COVERAGE_FILE']}")
        cmd.append(f"ANSIBLE_MODULE_NO_ZIP={env['ANSIBLE_MODULE_NO_ZIP']}")
        cmd.append(f"ANSIBLE_KEEP_REMOTE_FILES={env['ANSIBLE_KEEP_REMOTE_FILES']}")
        cmd.append(f"_ANSIBLE_ANSIBALLZ_COVERAGE_CONFIG={env['_ANSIBLE_ANSIBALLZ_COVERAGE_CONFIG']}")
        if "PYTHONPATH" in env:
            cmd.append(f"PYTHONPATH={env['PYTHONPATH']}")
    if coverage_enabled:
        cmd.extend([
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--parallel-mode",
            "--rcfile",
            env["COVERAGE_RCFILE"],
            ansible_playbook_path,
        ])
    else:
        cmd.append(ansible_playbook_path)

    if inventory is not None:
        cmd.extend(["-i", str(inventory)])
    if extra_args:
        cmd.extend(shlex.split(str(extra_args)))

    cmd.append(str(playbook))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(workdir),
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    log_raw_output(output)
    return result.returncode, output


def _build_ping_command(entry: dict) -> Optional[str]:
    destination = entry.get("Destination") or entry.get("destination") or entry.get("Target") or entry.get("target")
    command = entry.get("Command") or entry.get("command") or PING_DEFAULT_COMMAND
    if not destination:
        return None

    parts: List[str] = [str(command)]

    count = entry.get("Count") or entry.get("count")
    if count is not None:
        parts.extend(["-c", str(count)])

    interval = entry.get("Interval") or entry.get("interval")
    if interval is not None:
        parts.extend(["-i", str(interval)])

    size = entry.get("Size") or entry.get("size")
    if size is not None:
        parts.extend(["-s", str(size)])

    deadline = entry.get("Deadline") or entry.get("deadline")
    if deadline is not None:
        parts.extend(["-w", str(deadline)])

    source = entry.get("Source") or entry.get("source") or entry.get("Interface") or entry.get("interface")
    if source is not None:
        parts.extend(["-I", str(source)])

    extra_args = entry.get("ExtraArgs") or entry.get("extra_args")
    if extra_args:
        if isinstance(extra_args, str):
            parts.extend(extra_args.split())
        elif isinstance(extra_args, list):
            parts.extend(str(item) for item in extra_args)

    parts.append(str(destination))
    return " ".join(parts)


def run_traffic_pc_commands(
    configs: Sequence[TrafficPCConfig],
    *,
    status_callback: Optional[Callable[[int, int], None]] = None,
) -> bool:
    if not configs:
        return True

    script_path = TEST_TOOLS_DIR / "tpc_cmd.sh"
    if not script_path.is_file():
        log(f"Traffic PC script not found: {script_path}")
        return False

    overall_success = True
    for config in configs:
        if not config.commands:
            continue

        for cmd_config in config.commands:
            attempts = max(1, cmd_config.repeat + 1)
            attempt_success = False
            for attempt_index in range(1, attempts + 1):
                if status_callback and attempts > 1:
                    status_callback(attempt_index, attempts)

                log(
                    "Invoking tpc_cmd.sh for host {host} command: {command} (attempt {attempt}/{total})".format(
                        host=config.host,
                        command=cmd_config.command,
                        attempt=attempt_index,
                        total=attempts,
                    ),
                    stream=False,
                )

                cmd = [str(script_path), config.host, cmd_config.command]
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                stdout_text = result.stdout or ""
                stderr_text = result.stderr or ""
                payload = None
                if stdout_text.strip():
                    try:
                        payload = json.loads(stdout_text)
                    except json.JSONDecodeError:
                        for line in stdout_text.strip().splitlines():
                            log(f"[TrafficPC {config.host}] {line}", stream=False)
                if stderr_text.strip():
                    for line in stderr_text.strip().splitlines():
                        log(f"[TrafficPC {config.host} stderr] {line}", stream=False)

                success = result.returncode == 0
                if payload is not None:
                    for entry in payload.get("results", []):
                        cmd_text = entry.get("command", "")
                        rc = entry.get("returncode", 0)
                        stdout_line = entry.get("stdout", "").strip()
                        stderr_line = entry.get("stderr", "").strip()
                        summary = f"command='{cmd_text}' returncode={rc}"
                        if stdout_line:
                            summary += f" stdout={stdout_line.splitlines()[-1]}"
                        if stderr_line:
                            summary += f" stderr={stderr_line.splitlines()[-1]}"
                        log(f"[TrafficPC {config.host}] {summary}", stream=False)
                        if rc:
                            success = False
                    all_ok = payload.get("all_ok")
                    if all_ok is False:
                        success = False
                else:
                    combined = (stdout_text + stderr_text).strip()
                    if combined:
                        log(f"[TrafficPC {config.host}] Raw output: {combined}", stream=False)

                if success:
                    if attempts > 1 and attempt_index > 1:
                        log(
                            f"[TrafficPC {config.host}] Command succeeded on attempt {attempt_index}/{attempts}",
                            stream=False,
                        )
                    attempt_success = True
                    break

                if attempts > 1 and attempt_index < attempts:
                    log(
                        f"[TrafficPC {config.host}] Command failed on attempt {attempt_index}/{attempts}; retrying",
                        stream=False,
                    )

            if not attempt_success:
                log(
                    f"Traffic PC command failed for host {config.host} after {attempts} attempt(s): {cmd_config.command}",
                )
                overall_success = False

    return overall_success


def validate_summary_yaml(summary_path: Path) -> Tuple[Optional[Any], List[str], bool]:
    title = f"-- Summary file syntax check ({summary_path.name})"
    messages: List[str] = []
    try:
        with summary_path.open() as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        line = _status_line(title, "[FAIL]")
        messages.append(line)
        messages.append(f"YAML syntax error: {exc}")
        return None, messages, False

    line = _status_line(title, "[PASS]")
    messages.append(line)
    return (data if data is not None else {}), messages, True


def _collect_playbook_paths(tests: Sequence[TestConfig]) -> List[Path]:
    seen: set[Path] = set()
    paths: List[Path] = []
    for test in tests:
        for playbook in test.playbooks:
            candidate = (PLAYBOOK_DIR / playbook.file).resolve()
            if candidate not in seen:
                seen.add(candidate)
                paths.append(candidate)
    return paths


def validate_playbooks_syntax(tests: Sequence[TestConfig]) -> Tuple[bool, List[str]]:
    playbook_paths = _collect_playbook_paths(tests)
    count = len(playbook_paths)
    title = f"-- Playbook syntax check ({count} file{'s' if count != 1 else ''})"
    messages: List[str] = []

    def _fail(header: str, detail: str = "") -> Tuple[bool, List[str]]:
        line = _status_line(title, "[FAIL]")
        if not messages or messages[-1] != line:
            messages.append(line)
        header_text = header.strip()
        if header_text:
            messages.append(header_text)
        detail_text = detail.strip()
        if detail_text:
            messages.append(detail_text)
        return False, messages

    if not playbook_paths:
        line = _status_line(title, "[PASS]")
        messages.append(line)
        return True, messages

    yamllint_path = shutil.which("yamllint")
    if yamllint_path is None:
        return _fail("Required command not found: yamllint")

    ansible_playbook_path = shutil.which("ansible-playbook")
    if ansible_playbook_path is None:
        return _fail("Required command not found: ansible-playbook")

    ansible_env = dict(os.environ)
    ansible_env["ANSIBLE_CONFIG"] = str(ANSIBLE_CONFIG_PATH)

    for pb_path in playbook_paths:
        if not pb_path.is_file():
            return _fail(f"Playbook not found: {pb_path}")

        yamllint_cmd = [yamllint_path, str(pb_path)]
        yamllint_result = subprocess.run(
            yamllint_cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if yamllint_result.returncode != 0:
            detail = (yamllint_result.stderr or yamllint_result.stdout or "yamllint reported an error").strip()
            header = f"yamllint failed for {pb_path}:"
            return _fail(header, detail)

        syntax_cmd = [ansible_playbook_path, str(pb_path), "--syntax-check"]
        syntax_result = subprocess.run(
            syntax_cmd,
            capture_output=True,
            text=True,
            env=ansible_env,
            check=False,
        )
        if syntax_result.returncode != 0:
            detail = (syntax_result.stderr or syntax_result.stdout or "ansible-playbook --syntax-check reported an error").strip()
            header = f"ansible-playbook --syntax-check failed for {pb_path}:"
            return _fail(header, detail)

    line = _status_line(title, "[PASS]")
    messages.append(line)
    return True, messages


def transfer_openapi_logs(
    host_infos: Sequence[HostConnectionInfo],
    dashboard: Optional[Dashboard] = None,
) -> None:
    if not host_infos:
        log("No hosts available for log transfer.")
        return

    scp_path = shutil.which("scp")
    if scp_path is None:
        log("scp command not found; skipping log transfer.")
        return

    sshpass_path = shutil.which("sshpass")
    if sshpass_path is None:
        log("sshpass command not found; skipping log transfer.")
        return

    transferred: list[tuple[str, Path]] = []

    for info in host_infos:
        if not info.username or not info.password:
            log(
                f"Skipping log transfer for {info.name} ({info.address}): missing credentials."
            )
            continue

        destination = Path(f"/tmp/openapi.{info.name}.log")
        try:
            if destination.exists():
                destination.unlink()
        except OSError as exc:
            log(
                f"Failed to prepare destination for {info.name}: {exc}"
            )
            continue
        port = info.ssh_port if info.ssh_port > 0 else 22
        remote_path = f"{info.username}@{info.address}:/intflash/openapi/openapi_server.log"

        cmd = [
            sshpass_path,
            "-p",
            info.password,
            scp_path,
            "-q",
            "-P",
            str(port),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            remote_path,
            str(destination),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        detail = result.stderr.strip() or result.stdout.strip() or ""
        if destination.is_file():
            log(f"Transferred openapi log for {info.name} -> {destination}")
            transferred.append((info.name or info.address, destination))
            if result.returncode != 0:
                message = detail.splitlines()[0] if detail else f"scp exited with {result.returncode}"
                log(
                    f"Transfer for {info.name} completed with warnings: {message}",
                    stream=False,
                )
            if detail:
                log(detail, stream=False)
        else:
            first_line = detail.splitlines()[0] if detail else "unknown error"
            log(
                f"Failed to transfer openapi log for {info.name}: {first_line}"
            )
            if detail and first_line != detail:
                log(detail, stream=False)

    if dashboard is not None and transferred:
        dashboard.set_switch_logs(transferred)


IGNORED_WARNING_SUBSTRINGS = (
    "WARNING:Disable ISIS will cause traffic disruption",
)


def _has_unexpected_warning_error(output: str) -> bool:
    """Return True when output contains errors that weren't ignored."""

    sanitized_output = output
    for ignored_warning in IGNORED_WARNING_SUBSTRINGS:
        if ignored_warning in sanitized_output:
            sanitized_output = sanitized_output.replace(ignored_warning, "")

    if "WARNING" in sanitized_output:
        return True

    if "ERROR" not in sanitized_output:
        return False

    lines = sanitized_output.splitlines()
    total_lines = len(lines)
    index = 0
    while index < total_lines:
        line = lines[index]
        stripped = line.strip()
        contains_error = (
            "ERROR" in line
            or stripped.startswith("fatal:")
            or stripped.startswith("ERROR!")
        )
        if contains_error:
            ignoring = False
            scan = index + 1
            while scan < total_lines:
                current = lines[scan]
                current_stripped = current.strip()
                if "...ignoring" in current:
                    ignoring = True
                    index = scan
                    break
                if current_stripped.startswith("TASK [") or current_stripped.startswith("PLAY "):
                    break
                if "ERROR" in current and scan != index:
                    break
                scan += 1
            if not ignoring:
                return True
        index += 1
    return False


def evaluate(
    expected: Dict[str, int | str], output: str
) -> Tuple[bool, Dict[str, Dict[str, str]], str]:
    """Compare ansible output metrics against expected summary values."""
    warning_error = _has_unexpected_warning_error(output)
    recap_section = output.split("PLAY RECAP", 1)
    if len(recap_section) != 2:
        return False, {}, output

    recap_text = recap_section[1]
    matches = list(PLAY_RECAP_RE.finditer(recap_text))
    if not matches:
        return False, {}, output

    host_results: Dict[str, Dict[str, str]] = {}
    passed = True
    mismatch_detail = ""
    for match in matches:
        host = match.group("host")
        actual = match.groupdict()
        host_results[host] = actual
        for key in DEFAULT_KEYS:
            exp = expected.get(key, 0)
            if exp == "*":
                continue
            actual_value = int(actual[key])
            if actual_value != exp:
                passed = False
                mismatch_detail = (
                    f"Expectation mismatch for host '{host}': expected {key}={exp}, got {actual_value}."
                )
                break
        if not passed:
            break

    failure_expected = False
    failed_expectation = expected.get("failed")
    if isinstance(failed_expectation, str) and failed_expectation.strip() == "*":
        failure_expected = True
    elif isinstance(failed_expectation, int) and failed_expectation > 0:
        failure_expected = True

    if warning_error and not failure_expected:
        passed = False
        if not mismatch_detail:
            mismatch_detail = "Unexpected WARNING/ERROR detected in play output while failures were not expected."


    if passed:
        summary = "; ".join(
            f"{host}: ok={vals['ok']} changed={vals['changed']} unreachable={vals['unreachable']} "
            f"failed={vals['failed']} skipped={vals['skipped']} rescued={vals['rescued']} ignored={vals['ignored']}"
            for host, vals in host_results.items()
        )
        return True, host_results, summary

    if not mismatch_detail:
        mismatch_detail = output

    diagnostic = mismatch_detail
    if host_results:
        observed_summary = "; ".join(
            f"{host}: ok={vals['ok']} changed={vals['changed']} unreachable={vals['unreachable']} "
            f"failed={vals['failed']} skipped={vals['skipped']} rescued={vals['rescued']} ignored={vals['ignored']}"
            for host, vals in host_results.items()
        )
        diagnostic = f"{mismatch_detail}\nObserved recap: {observed_summary}"

    return False, host_results, diagnostic


def format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _parse_coverage_report_lines(lines: Sequence[str]) -> tuple[Optional[float], list[dict[str, Any]]]:
    overall = None
    entries: list[dict[str, Any]] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("Name ") or stripped.startswith("-"):
            continue
        segments = stripped.rsplit(None, 5)
        if len(segments) < 2:
            continue
        percent_token = segments[-1]
        if not percent_token.endswith("%"):
            continue
        try:
            percent_value = float(percent_token.rstrip("%"))
        except ValueError:
            continue
        name = segments[0]
        numeric_tokens = segments[1:-1]
        entries.append(
            {
                "name": name,
                "percent": percent_value,
                "metrics": numeric_tokens,
            }
        )
        if name.upper() == "TOTAL":
            overall = percent_value
    return overall, entries


def _parse_value(value: Union[str, int, None]) -> Union[int, str]:
    if isinstance(value, str) and value.strip() == "*":
        return "*"
    if value is None:
        return 0
    return int(value)


def _parse_script_config(raw: Any) -> Optional[ScriptConfig]:
    if raw is None:
        return None

    file_value: Optional[str] = None
    options: List[str] = []
    fatal = False

    if isinstance(raw, str):
        file_value = raw.strip()
    elif isinstance(raw, dict):
        value = (
            raw.get("File")
            or raw.get("file")
            or raw.get("Path")
            or raw.get("path")
            or raw.get("script")
        )
        if value is not None:
            text = str(value).strip()
            if text:
                file_value = text

        options_value = (
            raw.get("Options")
            or raw.get("options")
            or raw.get("Args")
            or raw.get("args")
        )
        if isinstance(options_value, str):
            option_text = options_value.strip()
            if option_text:
                options = shlex.split(option_text)
        elif isinstance(options_value, (list, tuple)):
            options = [str(item) for item in options_value if item is not None]

        fatal = _to_bool(raw.get("fatal") or raw.get("Fatal"), default=False)
    else:
        return None

    if not file_value:
        return None

    return ScriptConfig(file=file_value, options=options, fatal=fatal)


def _build_script_command(script_path: Path, options: Sequence[str]) -> Tuple[List[str], Optional[str]]:
    command: List[str]
    fallback_note: Optional[str] = None
    option_list = [str(opt) for opt in options]

    if os.access(script_path, os.X_OK):
        command = [str(script_path)]
    else:
        shebang: Optional[str] = None
        try:
            with script_path.open("r", encoding="utf-8", errors="ignore") as handle:
                first_line = handle.readline().strip()
            if first_line.startswith("#!"):
                shebang = first_line[2:].strip()
        except OSError:
            shebang = None

        if shebang:
            interpreter_parts = shlex.split(shebang)
            if interpreter_parts:
                command = interpreter_parts + [str(script_path)]
                fallback_note = "using shebang interpreter '{}'".format(" ".join(interpreter_parts))
            else:
                command = [str(script_path)]
        else:
            command = [str(script_path)]

    command.extend(option_list)
    return command, fallback_note


def _resolve_include_entry(entry: Any, base_dir: Path) -> Optional[Path]:
    # base_dir retained for compatibility; includes now resolved from COMPONENTS_DIR.
    candidate: Optional[Any] = entry
    entry_is_dict = isinstance(entry, dict)
    if entry_is_dict:
        candidate = entry.get("include") or entry.get("Include")
    if candidate is None:
        return None

    if isinstance(candidate, Path):
        target_path = candidate
    else:
        text = str(candidate).strip()
        if not text:
            return None
        match = INCLUDE_DIRECTIVE_RE.match(text)
        if match:
            raw_target = match.group("bracket") or match.group("plain") or ""
            target_text = raw_target.strip()
            if not target_text:
                return None
            target_path = Path(target_text)
        elif entry_is_dict:
            target_path = Path(text)
        else:
            return None

    if not target_path.is_absolute():
        return (COMPONENTS_DIR / target_path).resolve()
    return target_path.resolve()


def load_tests(path: Path, data: Optional[Any] = None, *, _stack: Optional[Tuple[Path, ...]] = None) -> Tuple[Optional[Path], Optional[str], Optional[str], bool, bool, list[TestConfig]]:
    resolved_path = path.resolve()
    stack = _stack or ()
    if resolved_path in stack:
        cycle = " -> ".join(str(p) for p in stack + (resolved_path,))
        raise ValueError(f"Circular include detected: {cycle}")
    next_stack = stack + (resolved_path,)

    if data is None:
        with path.open() as fh:
            loaded = yaml.safe_load(fh)
    else:
        loaded = data

    if loaded is None:
        loaded = {}

    base_dir = resolved_path.parent

    default_inventory: Optional[Path] = None
    default_playbook_args: Optional[str] = None
    default_logfile: Optional[str] = None
    default_coverage = False
    default_trace_http = False

    if isinstance(loaded, dict):
        inv_value = loaded.get("inventory")
        if inv_value:
            default_inventory = Path(str(inv_value))
        playbook_args_value = loaded.get("playbook_args")
        if playbook_args_value is not None:
            default_playbook_args = str(playbook_args_value)
        log_value = loaded.get("logfile")
        if log_value:
            default_logfile = str(log_value)
        coverage_value = loaded.get("test_coverage")
        if coverage_value is not None:
            default_coverage = _to_bool(coverage_value, default=False)
        trace_value = loaded.get("trace_http")
        if trace_value is not None:
            default_trace_http = _to_bool(trace_value, default=False)
        entries = loaded.get("Tests") or loaded.get("tests") or []
    elif isinstance(loaded, list):
        entries = loaded
    else:
        entries = []

    tests: list[TestConfig] = []

    if isinstance(loaded, dict):
        includes_raw = loaded.get("Includes") or loaded.get("includes")
        if includes_raw:
            if isinstance(includes_raw, list):
                include_entries = includes_raw
            else:
                include_entries = [includes_raw]
            for include_entry in include_entries:
                include_path = _resolve_include_entry(include_entry, base_dir)
                if include_path is None:
                    raise ValueError(
                        f"Invalid include directive {include_entry!r} in {resolved_path}"
                    )
                if not include_path.is_file():
                    raise FileNotFoundError(f"Included summary file not found: {include_path}")
                _, _, _, _, _, nested_tests = load_tests(include_path, None, _stack=next_stack)
                tests.extend(nested_tests)

    for idx, entry in enumerate(entries, start=1):
        include_path: Optional[Path] = None
        if isinstance(entry, (str, Path, dict)):
            include_path = _resolve_include_entry(entry, base_dir)
        if include_path is not None:
            if not include_path.is_file():
                raise FileNotFoundError(f"Included summary file not found: {include_path}")
            _, _, _, _, _, nested_tests = load_tests(include_path, None, _stack=next_stack)
            tests.extend(nested_tests)
            continue

        if isinstance(entry, str):
            raise ValueError(f"Unrecognized include directive {entry!r} in {resolved_path}")

        if not isinstance(entry, dict):
            continue

        name = str(entry.get("Name") or entry.get("name") or f"Test {idx:02d}")
        test_inventory = entry.get("inventory")
        if test_inventory:
            test_inventory = Path(str(test_inventory))
        else:
            test_inventory = None
        test_playbook_args = entry.get("playbook_args")
        if test_playbook_args is not None:
            test_playbook_args = str(test_playbook_args)

        playbook_entries_raw = entry.get("Playbooks") or entry.get("playbooks")
        if playbook_entries_raw is None:
            legacy_single = entry.get("Playbook") or entry.get("playbook")
            if legacy_single is not None:
                if isinstance(legacy_single, list):
                    playbook_entries_raw = legacy_single
                else:
                    playbook_entries_raw = [legacy_single]
        if playbook_entries_raw is None:
            playbook_entries_raw = []

        playbooks: List[PlaybookConfig] = []
        for pb_raw in playbook_entries_raw:
            if pb_raw is None:
                continue
            file_value: Optional[str] = None
            pb_inventory: Optional[Path] = None
            pb_playbook_args: Optional[str] = None
            expectations: Dict[str, Union[int, str]] = {key: 0 for key in DEFAULT_KEYS}

            if isinstance(pb_raw, str):
                file_value = pb_raw
            elif isinstance(pb_raw, dict):
                value = pb_raw.get("File") or pb_raw.get("file") or pb_raw.get("playbook")
                if value:
                    file_value = str(value)
                inv_value = pb_raw.get("inventory")
                if inv_value:
                    pb_inventory = Path(str(inv_value))
                args_value = pb_raw.get("playbook_args")
                if args_value is not None:
                    pb_playbook_args = str(args_value)
                for key in DEFAULT_KEYS:
                    if key in pb_raw:
                        expectations[key] = _parse_value(pb_raw.get(key))
            else:
                continue

            if not file_value:
                continue

            playbooks.append(
                PlaybookConfig(
                    file=str(file_value),
                    expectations=expectations,
                    inventory=pb_inventory,
                    playbook_args=pb_playbook_args,
                )
            )

        traffic_entries_raw = entry.get("TrafficPCs") or entry.get("trafficpcs")
        if traffic_entries_raw is None:
            single = entry.get("TrafficPC") or entry.get("trafficpc") or entry.get("traffic_pc")
            if single is not None:
                if isinstance(single, list):
                    traffic_entries_raw = single
                else:
                    traffic_entries_raw = [single]
        if traffic_entries_raw is None:
            traffic_entries_raw = []

        traffic_pcs: List[TrafficPCConfig] = []
        for tr_raw in traffic_entries_raw:
            if not isinstance(tr_raw, dict):
                continue
            host_value = tr_raw.get("Host") or tr_raw.get("host")
            if not host_value:
                continue
            commands: list[TrafficPCCommand] = []
            interface_map = tr_raw.get("Interfaces") or tr_raw.get("interfaces")
            if isinstance(interface_map, dict):
                for iface, addr in interface_map.items():
                    if not isinstance(iface, str) or not iface.lower().startswith("eth"):
                        continue
                    if addr is None:
                        continue
                    addr_text = str(addr).strip()
                    if not addr_text:
                        continue
                    command_text = f"{TRAFFIC_PC_REMOTE_SCRIPT} {iface} {addr_text}"
                    commands.append(TrafficPCCommand(command=command_text))
            for key, value in tr_raw.items():
                if key in {"Host", "host", "Interfaces", "interfaces"}:
                    continue
                if not isinstance(key, str) or not key.lower().startswith("eth"):
                    continue
                if value is None:
                    continue
                value_text = str(value).strip()
                if not value_text:
                    continue
                command_text = f"{TRAFFIC_PC_REMOTE_SCRIPT} {key} {value_text}"
                commands.append(TrafficPCCommand(command=command_text))

            ping_data = tr_raw.get("Ping") or tr_raw.get("ping")
            ping_entries: List[dict | str] = []
            if isinstance(ping_data, list):
                ping_entries = ping_data
            elif ping_data:
                ping_entries = [ping_data]
            for ping_entry in ping_entries:
                command_text: Optional[str] = None
                repeat_value = 0
                if isinstance(ping_entry, str):
                    command_text = ping_entry.strip()
                elif isinstance(ping_entry, dict):
                    command_text = _build_ping_command(ping_entry)
                    repeat_value = _to_int(
                        ping_entry.get("repeat") or ping_entry.get("Repeat"),
                        default=0,
                    )
                if command_text:
                    commands.append(
                        TrafficPCCommand(
                            command=command_text,
                            repeat=max(0, repeat_value),
                            label=f"Ping {command_text.split()[-1]}" if command_text else None,
                        )
                    )
            traffic_pcs.append(TrafficPCConfig(host=str(host_value), commands=commands))

        script_entries: List[ScriptConfig] = []
        raw_script_candidates: list[Any] = []
        for key in ("Scripts", "scripts"):
            value = entry.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                raw_script_candidates.extend(value)
            else:
                raw_script_candidates.append(value)
        single_script = entry.get("Script") or entry.get("script")
        if single_script is not None:
            if isinstance(single_script, list):
                raw_script_candidates.extend(single_script)
            else:
                raw_script_candidates.append(single_script)
        for script_raw in raw_script_candidates:
            parsed_script = _parse_script_config(script_raw)
            if parsed_script is not None:
                script_entries.append(parsed_script)

        tests.append(
            TestConfig(
                name=name,
                playbooks=playbooks,
                traffic_pcs=traffic_pcs,
                scripts=script_entries,
                inventory=test_inventory,
                playbook_args=test_playbook_args,
            )
        )

    default_args = str(default_playbook_args) if default_playbook_args is not None else None
    return (
        default_inventory,
        default_args,
        default_logfile,
        default_coverage,
        default_trace_http,
        tests,
    )


def _execute_tests(args: argparse.Namespace, dashboard: Optional[Dashboard] = None) -> int:
    precheck_messages: List[str] = []

    preview_data: Optional[Any] = None
    file_prefix: Optional[str] = None
    try:
        with args.summary_file.open() as preview_fh:
            preview_data = yaml.safe_load(preview_fh)
    except Exception:
        preview_data = None

    preview_coverage = False
    preview_trace_http = False
    browser_prefix: Optional[str] = None
    if isinstance(preview_data, dict):
        preview_coverage = _to_bool(preview_data.get("test_coverage"), default=False)
        preview_trace_http = _to_bool(preview_data.get("trace_http"), default=False)
        raw_prefix = preview_data.get("file_prefix")
        if raw_prefix is not None:
            prefix_text = str(raw_prefix).strip()
            if prefix_text:
                file_prefix = prefix_text
        raw_browser_prefix = preview_data.get("browser_prefix")
        if raw_browser_prefix is not None:
            browser_prefix_text = str(raw_browser_prefix).strip()
            if browser_prefix_text:
                browser_prefix = browser_prefix_text
        if preview_coverage:
            os.environ[COVERAGE_ENV_FLAG] = "python"
        else:
            os.environ.pop(COVERAGE_ENV_FLAG, None)
        if preview_trace_http:
            os.environ.setdefault("EXTREME_FE_HTTP_TRACE", "1")
        else:
            os.environ.pop("EXTREME_FE_HTTP_TRACE", None)
    else:
        os.environ.pop(COVERAGE_ENV_FLAG, None)
        os.environ.pop("EXTREME_FE_HTTP_TRACE", None)

    if dashboard is not None:
        dashboard.set_file_prefix(file_prefix)
        if browser_prefix is not None:
            dashboard.set_browser_prefix(browser_prefix)

    # Run gns3_topology check before any other prechecks
    # gns3_cmd = ["/home/bjorn/ansible/test/cfg/gns3_topology", "check"]
    # gns3_cmd = ["/home/rwa/Desktop/ansible_01/ansible_collections.extreme.fe/ansible_collections/extreme/fe/tests/integration/harness/cfg/gns3_topology", "check"]
    # /home/rwa/Desktop/ansible_01/ansible_collections.extreme.fe/ansible_collections/extreme/fe/tests/integration/harness/cfg
    gns3_cmd = ["/home/rwa/work/ansible_collections.extreme.fe/ansible_collections/extreme/fe/tests/integration/harness/cfg/gns3_topology", "check"]

    ansible_dev_root = os.environ["ANSIBLE_DEV_ROOT"]

    gns3_topology = Path(ansible_dev_root) / \
        "ansible_collections/extreme/fe/tests/integration/harness/cfg/gns3_topology"

    gns3_cmd = [str(gns3_topology), "check"]

    if dashboard is not None:
        dashboard.mark_precheck_running("gns3_topology check")
    try:
        gns3_result = subprocess.run(gns3_cmd, capture_output=True, text=True, check=False)
        gns3_output = (gns3_result.stdout or "") + (gns3_result.stderr or "")
        gns3_ok = gns3_result.returncode == 0
        gns3_status = "[PASS]" if gns3_ok else "[FAIL]"
        gns3_title = "-- gns3_topology check"
        gns3_messages: List[str] = [_status_line(gns3_title, gns3_status)]
        for line in gns3_output.splitlines():
            if line.strip():
                gns3_messages.append(line)
        if dashboard is not None:
            dashboard.update_precheck("gns3_topology check", gns3_ok, gns3_messages[1:])
        # Log GNS3 check output to log file only, not console
        for message in gns3_messages:
            log(message, stream=False)
        if not gns3_ok:
            return 1
        # Do NOT add gns3_messages to precheck_messages to avoid console output
    except Exception as exc:
        gns3_error_msg = f"Failed to run gns3_topology check: {exc}"
        log(gns3_error_msg, stream=False)
        if dashboard is not None:
            dashboard.update_precheck("gns3_topology check", False, [str(exc)])
        return 1

    if _coverage_requested():
        if dashboard is not None:
            dashboard.mark_precheck_running("ansible-test coverage erase")
        rc, erase_output = _run_ansible_test_command(["coverage", "erase"])
        status = "[PASS]" if rc == 0 else "[FAIL]"
        coverage_title = "-- ansible-test coverage erase"
        coverage_messages: List[str] = [_status_line(coverage_title, status)]
        for line in (erase_output or "").splitlines():
            if line:
                coverage_messages.append(line)
        if dashboard is not None:
            dashboard.update_precheck("ansible-test coverage erase", rc == 0, coverage_messages[1:])
        if rc != 0:
            for message in coverage_messages:
                print(message)
            return 1
        workdir = _prepare_collection_workdir()
        _, data_dir, _ = _ensure_coverage_configuration(workdir)
        _purge_coverage_artifacts(workdir, data_dir)
        precheck_messages.extend(coverage_messages)

    if dashboard is not None:
        dashboard.mark_precheck_running("Summary file syntax check")
    summary_data, summary_messages, summary_ok = validate_summary_yaml(args.summary_file)
    if isinstance(summary_data, dict):
        raw_prefix = summary_data.get("file_prefix")
        if raw_prefix is not None:
            prefix_text = str(raw_prefix).strip()
            if prefix_text:
                file_prefix = prefix_text
                if dashboard is not None:
                    dashboard.set_file_prefix(file_prefix)
        raw_browser_prefix = summary_data.get("browser_prefix")
        if raw_browser_prefix is not None:
            browser_prefix_text = str(raw_browser_prefix).strip()
            if browser_prefix_text:
                browser_prefix = browser_prefix_text
                if dashboard is not None:
                    dashboard.set_browser_prefix(browser_prefix)
    precheck_messages.extend(summary_messages)
    if dashboard is not None:
        dashboard.update_precheck("Summary file syntax check", summary_ok, summary_messages[1:])

    default_inventory: Optional[Path] = None
    default_playbook_args: Optional[str] = None
    default_logfile: Optional[str] = None
    default_coverage = False
    default_trace_http = False
    tests: list[TestConfig] = []

    playbook_ok = False
    playbook_messages: List[str] = []
    playbook_details: List[str] = []
    playbook_count = 0

    if dashboard is not None:
        dashboard.mark_precheck_running("Playbook syntax check")

    if summary_ok and summary_data is not None:
        playbook_error: Optional[str] = None
        try:
            (
                default_inventory,
                default_playbook_args,
                default_logfile,
                default_coverage,
                default_trace_http,
                tests,
            ) = load_tests(args.summary_file, summary_data)
        except Exception as exc:
            tests = []
            playbook_error = (
                f"Failed to load tests for syntax check ({exc.__class__.__name__}): {exc}"
            )
        else:
            try:
                playbook_ok, playbook_messages = validate_playbooks_syntax(tests)
            except Exception as exc:
                playbook_ok = False
                playbook_messages = []
                playbook_error = (
                    f"Playbook syntax validation error ({exc.__class__.__name__}): {exc}"
                )
            else:
                precheck_messages.extend(playbook_messages)
                playbook_count = len(_collect_playbook_paths(tests))
                playbook_details = playbook_messages[1:]
                playbook_details.insert(0, f"{playbook_count} playbook(s) checked")

        if playbook_error is not None:
            error_title = "-- Playbook syntax check (error)"
            error_messages = [_status_line(error_title, "[FAIL]")]
            if playbook_error:
                error_messages.append(playbook_error)
                playbook_details = [playbook_error]
            else:
                playbook_details = []
            precheck_messages.extend(error_messages)
            playbook_ok = False
        if dashboard is not None:
            dashboard.update_precheck("Playbook syntax check", playbook_ok, playbook_details)
    else:
        playbook_ok = False
        if dashboard is not None:
            dashboard.update_precheck(
                "Playbook syntax check",
                False,
                ["Skipped: summary validation failed."],
            )

    if default_coverage:
        os.environ[COVERAGE_ENV_FLAG] = "python"
    else:
        os.environ.pop(COVERAGE_ENV_FLAG, None)

    summary_dir = args.summary_file.parent

    def _resolve_inventory_path(path_value: Optional[Path]) -> Optional[Path]:
        if path_value is None:
            return None
        if path_value.is_absolute():
            return path_value
        relative = path_value
        summary_candidate = (summary_dir / relative).resolve()
        if summary_candidate.exists():
            return summary_candidate
        root_candidate = (REPO_ROOT / relative).resolve()
        if root_candidate.exists():
            return root_candidate
        parts = tuple(relative.parts)
        if len(parts) >= 2 and parts[0].lower() == "test" and parts[1].lower() == "cfg":
            return root_candidate
        if len(parts) == 1:
            fallback = (INVENTORY_ROOT / parts[0]).resolve()
            if fallback.exists():
                return fallback
            return fallback
        return root_candidate

    inventory_candidates: List[Path] = []
    if default_inventory is not None:
        default_inventory = _resolve_inventory_path(default_inventory)
        if default_inventory is not None:
            inventory_candidates.append(default_inventory)

    for test in tests:
        inv_value = test.inventory
        resolved = None
        if isinstance(inv_value, Path):
            resolved = _resolve_inventory_path(inv_value)
        elif inv_value:
            resolved = _resolve_inventory_path(Path(str(inv_value)))
        if resolved is not None:
            test.inventory = resolved
            inventory_candidates.append(resolved)
        else:
            test.inventory = None

        for playbook in test.playbooks:
            pb_inv = playbook.inventory
            resolved_pb = None
            if isinstance(pb_inv, Path):
                resolved_pb = _resolve_inventory_path(pb_inv)
            elif pb_inv:
                resolved_pb = _resolve_inventory_path(Path(str(pb_inv)))
            if resolved_pb is not None:
                playbook.inventory = resolved_pb
                inventory_candidates.append(resolved_pb)
            else:
                playbook.inventory = None

    if dashboard is not None:
        dashboard.register_tests(tests)

    global LOG_PATH
    if args.output_log is not None:
        LOG_PATH = args.output_log
    elif default_logfile:
        LOG_PATH = Path(default_logfile)
    else:
        LOG_PATH = DEFAULT_LOG_PATH
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # reset log
    global LOG_LINE_COUNT
    LOG_LINE_COUNT = 0
    if dashboard is not None:
        dashboard.set_log_path(LOG_PATH)

    if default_trace_http:
        os.environ["EXTREME_FE_HTTP_TRACE"] = "1"
        os.environ["EXTREME_FE_HTTP_TRACE_PATH"] = str(LOG_PATH)
    else:
        os.environ.pop("EXTREME_FE_HTTP_TRACE", None)
        os.environ.pop("EXTREME_FE_HTTP_TRACE_PATH", None)

    start_ts = _dt.datetime.now()
    if dashboard is not None:
        dashboard.set_start(start_ts)
    log(
        "Test run started at {timestamp} | Config-file: {cfg}".format(
            timestamp=start_ts.isoformat(sep=" ", timespec="seconds"),
            cfg=args.summary_file,
        )
    )
    if dashboard is not None:
        log(f"Dashboard output: {dashboard.output_path}")
    log("-" * 80)

    for message in precheck_messages:
        log(message)

    if not summary_ok or not playbook_ok:
        if dashboard is not None:
            dashboard.set_status(Dashboard.STATUS_FAIL)
        return 1

    unique_inventory: List[Path] = []
    seen_inventories = set()
    for candidate in inventory_candidates:
        if candidate is None:
            continue
        resolved = candidate.resolve()
        if resolved not in seen_inventories:
            seen_inventories.add(resolved)
            unique_inventory.append(candidate)

    if dashboard is not None:
        dashboard.mark_precheck_running("Inventory discovery")

    host_infos: Dict[str, HostConnectionInfo] = {}
    for inventory_path in unique_inventory:
        try:
            for info in gather_inventory_hosts(inventory_path):
                host_infos.setdefault(info.address, info)
        except Exception as exc:
            log(f"Failed to process inventory {inventory_path}: {exc}")
            if dashboard is not None:
                dashboard.update_precheck(
                    "Inventory discovery",
                    False,
                    [f"{inventory_path}: {exc}"],
                )
                dashboard.set_status(Dashboard.STATUS_FAIL)
            return 1

    if not host_infos:
        log("No hosts found in inventory for pre-checks.")
        if dashboard is not None:
            dashboard.update_precheck(
                "Inventory discovery",
                False,
                ["No hosts found in inventory for pre-checks."],
            )
            dashboard.set_status(Dashboard.STATUS_FAIL)
        return 1

    if dashboard is not None:
        dashboard.update_precheck("Inventory discovery", True)

    host_list = list(host_infos.values())
    if dashboard is not None:
        dashboard.mark_precheck_running("Hosts reachability")
    reachability_ok, reachability_passed, reachability_total = verify_hosts_reachability(host_list)
    reachability_details = [
        f"{reachability_passed}/{reachability_total} host(s) reachable"
    ]
    reachability_status = "PASS" if reachability_ok else "FAIL"
    precheck_messages.append(
        f"Reachability check: {reachability_passed}/{reachability_total} host(s) reachable ({reachability_status})"
    )
    if dashboard is not None:
        dashboard.update_precheck("Hosts reachability", reachability_ok, reachability_details)
    if not reachability_ok:
        if dashboard is not None:
            dashboard.set_status(Dashboard.STATUS_FAIL)
        return 1

    if dashboard is not None:
        dashboard.mark_precheck_running("NOS-API availability")
    nos_ok, nos_passed, nos_total = verify_hosts_nos_api(host_list)
    nos_details = [f"{nos_passed}/{nos_total} host(s) passed NOS-API check"]
    nos_status = "PASS" if nos_ok else "FAIL"
    precheck_messages.append(
        f"NOS-API check: {nos_passed}/{nos_total} host(s) passed ({nos_status})"
    )
    if dashboard is not None:
        dashboard.update_precheck("NOS-API availability", nos_ok, nos_details)
    if not nos_ok:
        if dashboard is not None:
            dashboard.set_status(Dashboard.STATUS_FAIL)
        return 1

    log("-" * 80)
    if not tests:
        log("No playbooks found in summary file.")
        if dashboard is not None:
            dashboard.set_status(Dashboard.STATUS_FAIL)
        return 1

    results = []
    total_time = 0.0

    for idx, test in enumerate(tests, start=1):
        prefix = test.name
        if dashboard is not None:
            dashboard.mark_test_running(idx)
        _inline_test_status(prefix, "--:--:--", "[RUN]")
        start_time = time.perf_counter()
        test_passed = True
        step_logs: List[str] = []
        fatal_abort = False
        fatal_detail: Optional[str] = None

        def _update_repeat_status(attempt_idx: int, total_attempts: int) -> None:
            duration = time.perf_counter() - start_time
            duration_str = format_duration(duration)
            if total_attempts > 1:
                display = f"[R{attempt_idx:02d}]"
            else:
                display = "[RUN]"
            if dashboard is not None:
                dashboard.update_test_progress(idx, duration_str)
            _inline_test_status(prefix, duration_str, "[RUN]", display_status=display)

        for script_idx, script in enumerate(test.scripts, start=1):
            script_label = f"[{test.name}] Script {script_idx:02d} ({script.file})"
            script_path = Path(script.file)
            if not script_path.is_absolute():
                summary_candidate = (summary_dir / script_path).resolve()
                repo_candidate = (REPO_ROOT / script_path).resolve()
                if summary_candidate.exists():
                    script_path = summary_candidate
                elif repo_candidate.exists():
                    script_path = repo_candidate
                else:
                    script_path = repo_candidate

            if not script_path.is_file():
                message = f"{script_label}: missing script at {script_path}"
                step_logs.append(message)
                test_passed = False
                if script.fatal:
                    fatal_abort = True
                    fatal_detail = message
                    break
                continue

            cmd, fallback_note = _build_script_command(script_path, script.options)
            quoted_cmd = " ".join(shlex.quote(part) for part in cmd)
            log(f"{script_label} command: {quoted_cmd}", stream=False)
            if fallback_note:
                step_logs.append(f"{script_label}: {fallback_note} ({cmd[0]})")

            script_start = time.perf_counter()
            try:
                script_cwd = summary_dir
                try:
                    script_path.relative_to(summary_dir)
                except ValueError:
                    try:
                        script_path.relative_to(REPO_ROOT)
                    except ValueError:
                        pass
                    else:
                        script_cwd = REPO_ROOT
                script_result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(script_cwd),
                    check=False,
                )
            except Exception as exc:
                script_duration = time.perf_counter() - script_start
                script_duration_str = format_duration(script_duration)
                error_message = f"{script_label}: ERROR in {script_duration_str} ({exc})"
                step_logs.append(error_message)
                test_passed = False
                if script.fatal:
                    fatal_abort = True
                    fatal_detail = error_message
                    break
                continue

            script_duration = time.perf_counter() - script_start
            script_duration_str = format_duration(script_duration)
            success = script_result.returncode == 0
            status_text = "PASS" if success else "FAIL"
            summary_message = (
                f"{script_label}: {status_text} in {script_duration_str} (rc={script_result.returncode})"
            )
            step_logs.append(summary_message)
            combined_output = ((script_result.stdout or "") + (script_result.stderr or "")).strip()
            if combined_output:
                for line in combined_output.splitlines():
                    stripped = line.strip()
                    if stripped:
                        step_logs.append(f"{script_label} output: {stripped}")
            if not success:
                test_passed = False
                if script.fatal:
                    fatal_abort = True
                    fatal_detail = summary_message
                    break

        if fatal_abort:
            duration = time.perf_counter() - start_time
            duration_str = format_duration(duration)
            status = "[FAIL]"
            display_status = "\033[31m[FAIL]\033[0m"
            _inline_test_status(prefix, duration_str, status, final=True, display_status=display_status)
            test_log_start = log(_test_status_line(prefix, duration_str, status), stream=False)
            for message in step_logs:
                log(message, stream=False)
            failure_text = fatal_detail or f"{test.name}: fatal script failure"
            log(failure_text, stream=False)
            log("Fatal script failure encountered; skipping remaining tests.")
            if dashboard is not None:
                detail_text = "; ".join(step_logs) or failure_text
                if len(detail_text) > 600:
                    detail_text = detail_text[:600] + "…"
                dashboard.mark_test_result(idx, False, duration_str, detail_text, log_line=test_log_start)
            results.append(False)
            total_time += duration
            break

        if not run_traffic_pc_commands(test.traffic_pcs, status_callback=_update_repeat_status):
            duration = time.perf_counter() - start_time
            duration_str = format_duration(duration)
            status = "[FAIL]"
            display_status = "\033[31m[FAIL]\033[0m"
            _inline_test_status(prefix, duration_str, status, final=True, display_status=display_status)
            test_log_start = log(_test_status_line(prefix, duration_str, status), stream=False)
            for message in step_logs:
                log(message, stream=False)
            log(f"TrafficPC provisioning failed for {test.name}")
            if dashboard is not None:
                detail_components = step_logs + [f"TrafficPC provisioning failed for {test.name}"]
                detail_text = "; ".join(filter(None, detail_components))
                if len(detail_text) > 600:
                    detail_text = detail_text[:600] + "…"
                dashboard.mark_test_result(idx, False, duration_str, detail_text, log_line=test_log_start)
            results.append(False)
            total_time += duration
            continue

        if not test.playbooks:
            duration = time.perf_counter() - start_time
            duration_str = format_duration(duration)
            status = "[PASS]" if test_passed else "[FAIL]"
            display_status = status if test_passed else "\033[31m[FAIL]\033[0m"
            _inline_test_status(prefix, duration_str, status, final=True, display_status=display_status)
            test_log_start = log(_test_status_line(prefix, duration_str, status), stream=False)
            for message in step_logs:
                log(message, stream=False)
            detail_components = step_logs or ["TrafficPC only"]
            if test_passed:
                log(
                    f"No playbooks configured for {test.name}; only TrafficPC commands executed.",
                    stream=False,
                )
            else:
                log(
                    f"No playbooks configured for {test.name}; script or TrafficPC steps failed.",
                    stream=False,
                )
            if dashboard is not None:
                detail_text = "; ".join(detail_components)
                if len(detail_text) > 600:
                    detail_text = detail_text[:600] + "…"
                dashboard.mark_test_result(
                    idx,
                    test_passed,
                    duration_str,
                    detail_text or ("TrafficPC only" if test_passed else "Pre-playbook failure"),
                    log_line=test_log_start,
                )
            results.append(test_passed)
            total_time += duration
            continue

        for pb_idx, playbook in enumerate(test.playbooks, start=1):
            pb_path = PLAYBOOK_DIR / playbook.file
            pb_label = f"[{test.name}] Playbook {pb_idx:02d} ({playbook.file})"
            if not pb_path.is_file():
                test_passed = False
                step_logs.append(f"{pb_label}: missing playbook at {pb_path}")
                break

            pb_start = time.perf_counter()
            inventory_path = (
                playbook.inventory
                if playbook.inventory is not None
                else test.inventory
                if test.inventory is not None
                else default_inventory
            )
            extra_args = (
                playbook.playbook_args
                if playbook.playbook_args is not None
                else test.playbook_args
                if test.playbook_args is not None
                else default_playbook_args
            )
            _, output = run_playbook(pb_path, inventory_path, extra_args)
            pb_duration = time.perf_counter() - pb_start
            pb_duration_str = format_duration(pb_duration)
            passed, _, info = evaluate(playbook.expectations, output)
            if passed:
                step_logs.append(f"{pb_label}: PASS in {pb_duration_str}")
            else:
                step_logs.append(f"{pb_label}: FAIL in {pb_duration_str}")
                step_logs.append(info.rstrip())
                test_passed = False
            if dashboard is not None:
                dashboard.update_test_progress(idx)

        duration = time.perf_counter() - start_time
        total_time += duration
        duration_str = format_duration(duration)
        status = "[PASS]" if test_passed else "[FAIL]"
        display_status = status if test_passed else "\033[31m[FAIL]\033[0m"

        _inline_test_status(prefix, duration_str, status, final=True, display_status=display_status)
        # Capture the line number where this test's log entry starts
        test_log_start = log(_test_status_line(prefix, duration_str, status), stream=False)
        for message in step_logs:
            log(message, stream=False)
        if dashboard is not None:
            detail_text = "; ".join(step_logs)
            if len(detail_text) > 600:
                detail_text = detail_text[:600] + "…"
            dashboard.mark_test_result(idx, test_passed, duration_str, detail_text, log_line=test_log_start)
        results.append(test_passed)


    all_passed = all(results) if results else False
    if dashboard is not None:
        dashboard.set_status(Dashboard.STATUS_PASS if all_passed else Dashboard.STATUS_FAIL)

    end_ts = _dt.datetime.now()
    log("-" * 80)
    log(
        "Test run finished at {end} (elapsed {duration})".format(
            end=end_ts.isoformat(sep=" ", timespec="seconds"),
            duration=format_duration(total_time),
        )
    )
    log(f"Logs written to {LOG_PATH}")
    transfer_openapi_logs(list(host_infos.values()), dashboard)
    return 0 if all_passed else 1


def _run_post_coverage_commands(dashboard: Optional[Dashboard] = None) -> bool:
    if not _coverage_requested():
        if dashboard is not None:
            dashboard.update_coverage(None, [], ["Coverage not enabled for this run."])
        return True

    workdir = _prepare_collection_workdir()
    rc_path, data_dir, support_dir = _ensure_coverage_configuration(workdir)
    coverage_env = dict(os.environ)
    coverage_env.setdefault("COVERAGE_RCFILE", str(rc_path))
    coverage_env.setdefault("COVERAGE_FILE", str((data_dir / ".coverage")))
    coverage_env.setdefault("COVERAGE_PROCESS_START", str(rc_path))
    _augment_pythonpath(coverage_env, support_dir)

    namespace, collection = _collection_identity()
    module_roots = [
        (Path.cwd() / "ansible_collections" / namespace / collection / "plugins" / "modules").resolve(),
        (workdir / "ansible_collections" / namespace / collection / "plugins" / "modules").resolve(),
        (Path.cwd() / "plugins" / "modules").resolve(),
        (workdir / "plugins" / "modules").resolve(),
    ]
    module_root_strings = [str(root) for root in module_roots if root is not None]
    module_candidates: Dict[str, Path] = {}
    for root in module_roots:
        if not root.is_dir():
            continue
        for module_path in root.glob("*.py"):
            module_candidates.setdefault(module_path.name, module_path.resolve())

    def _resolve_module_path(raw_path: str) -> Optional[str]:
        raw_path_str = str(raw_path)
        for root_str in module_root_strings:
            if raw_path_str.startswith(root_str):
                return raw_path_str
        module_name = Path(raw_path_str).name
        candidate = module_candidates.get(module_name)
        if candidate is not None:
            return str(candidate)
        return None

    module_line_map: Dict[str, set[int]] = defaultdict(set)

    for raw_file in data_dir.glob("module=python-*"):
        _normalize_coverage_paths(raw_file, workdir)
        _populate_line_bits_from_arcs(raw_file)
        db_conn: Optional[sqlite3.Connection] = None
        try:
            db_conn = sqlite3.connect(str(raw_file))
        except sqlite3.Error:
            db_conn = None
        try:
            raw_data = CoverageData(basename=str(raw_file))
            raw_data.read()
        except Exception:
            raw_data = None
        if db_conn is not None:
            try:
                cursor = db_conn.cursor()
                try:
                    rows = cursor.execute("SELECT id, path FROM file").fetchall()
                except sqlite3.Error:
                    rows = []
                for file_id, path_str in rows:
                    canonical_path = _resolve_module_path(str(path_str))
                    if canonical_path is None:
                        continue
                    try:
                        bits_row = cursor.execute(
                            "SELECT numbits FROM line_bits WHERE file_id = ?",
                            (file_id,),
                        ).fetchone()
                    except sqlite3.Error:
                        bits_row = None
                    if not bits_row or not bits_row[0]:
                        continue
                    try:
                        decoded_lines = sorted(numbits.numbits_to_nums(bits_row[0]))
                    except Exception:
                        continue
                    if decoded_lines:
                        module_line_map[canonical_path].update(decoded_lines)
            finally:
                try:
                    db_conn.close()
                except Exception:
                    pass
        if raw_data is None:
            continue
        for filename in raw_data.measured_files():
            canonical_path = _resolve_module_path(str(filename))
            if canonical_path is None:
                continue
            lines = raw_data.lines(filename) or []
            if not lines:
                arcs = raw_data.arcs(filename)
                if arcs:
                    lines = sorted({line for arc in arcs for line in arc if line and line > 0})
            if lines:
                module_line_map[canonical_path].update(lines)

    def _run_and_log(label: str, cmd: list[str]) -> Tuple[int, List[str], List[str]]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(workdir),
            env=coverage_env,
            check=False,
        )
        header = f"[coverage] coverage {label} (rc={result.returncode})"
        log(header)
        filtered_stdout: List[str] = []
        filtered_stderr: List[str] = []
        for line in (result.stdout or "").splitlines():
            if not line:
                continue
            if line.startswith("Combined data file") or line.startswith("Skipping duplicate data"):
                continue
            filtered_stdout.append(line)
            log(line)
        for line in (result.stderr or "").splitlines():
            if not line:
                continue
            if line.startswith("Combined data file") or line.startswith("Skipping duplicate data"):
                continue
            filtered_stderr.append(line)
            log(line)
        return result.returncode, filtered_stdout, filtered_stderr

    coverage_overall: Optional[float] = None
    coverage_entries: list[dict[str, Any]] = []
    coverage_notes: List[str] = []

    success = True
    coverage_target = Path(coverage_env.get("COVERAGE_FILE", data_dir / ".coverage"))

    combine_rc, _, combine_err = _run_and_log(
        "combine",
        [
            "python",
            "-m",
            "coverage",
            "combine",
            "--rcfile",
            str(rc_path),
            str(data_dir),
        ],
    )

    if combine_rc == 0:
        _normalize_coverage_paths(coverage_target, workdir)
        _populate_line_bits_from_arcs(coverage_target)
        if module_line_map:
            try:
                conn = sqlite3.connect(str(coverage_target))
            except sqlite3.Error:
                conn = None
            if conn is not None:
                try:
                    cursor = conn.cursor()
                    context_row = cursor.execute(
                        "SELECT id FROM context WHERE context = ''"
                    ).fetchone()
                    if context_row is None:
                        cursor.execute("INSERT INTO context(context) VALUES ('')")
                        context_id = cursor.lastrowid
                    else:
                        context_id = context_row[0]
                    for path, lines in module_line_map.items():
                        sorted_lines = sorted(lines)
                        if not sorted_lines:
                            continue
                        file_row = cursor.execute(
                            "SELECT id FROM file WHERE path = ?",
                            (path,),
                        ).fetchone()
                        if file_row is None:
                            cursor.execute(
                                "INSERT INTO file(path) VALUES (?)",
                                (path,),
                            )
                            file_id = cursor.lastrowid
                        else:
                            file_id = file_row[0]
                        cursor.execute("DELETE FROM arc WHERE file_id = ?", (file_id,))
                        cursor.execute(
                            "DELETE FROM line_bits WHERE file_id = ?",
                            (file_id,),
                        )
                        try:
                            bits_bytes = numbits.nums_to_numbits(sorted_lines)
                        except AttributeError:
                            legacy_bits = numbits.numbits_from_list(sorted_lines)
                            bits_bytes = legacy_bits.to_bytes()
                        cursor.execute(
                            "INSERT INTO line_bits (file_id, context_id, numbits) VALUES (?, ?, ?)",
                            (file_id, context_id, sqlite3.Binary(bits_bytes)),
                        )
                    conn.commit()
                except sqlite3.Error:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
        _normalize_coverage_paths(coverage_target, workdir)
        _populate_line_bits_from_arcs(coverage_target)
    else:
        success = False

    if combine_err:
        coverage_notes.extend(f"[combine] {line}" for line in combine_err)

    report_rc, report_out, report_err = _run_and_log(
        "report",
        [
            "python",
            "-m",
            "coverage",
            "report",
            "--rcfile",
            str(rc_path),
        ],
    )
    if report_rc != 0:
        success = False

    html_rc, _, html_err = _run_and_log(
        "html",
        [
            "python",
            "-m",
            "coverage",
            "html",
            "--rcfile",
            str(rc_path),
            "-d",
            str((data_dir.parent / "coverage").resolve()),
        ],
    )
    if html_rc != 0:
        success = False

    if report_out:
        overall, parsed_entries = _parse_coverage_report_lines(report_out)
        coverage_overall = overall if overall is not None else coverage_overall
        if parsed_entries:
            coverage_entries = parsed_entries
    if report_err:
        coverage_notes.extend(f"[report] {line}" for line in report_err)
    if html_err:
        coverage_notes.extend(f"[html] {line}" for line in html_err)

    if dashboard is not None:
        dashboard.update_coverage(coverage_overall, coverage_entries, coverage_notes)
        # Set coverage HTML path for dashboard link
        coverage_html_path = data_dir.parent / "coverage" / "index.html"
        if coverage_html_path.exists():
            dashboard.set_coverage_html_path(coverage_html_path)

    return success


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ansible playbooks from a YAML summary file.")
    parser.add_argument("summary_file", type=Path, help="Path to YAML summary file")
    parser.add_argument(
        "output_log",
        nargs="?",
        type=Path,
        help="Optional path for detailed output log (defaults to /tmp/run_test.log)",
    )
    args = parser.parse_args()

    if not args.summary_file.is_file():
        print(f"Summary file not found: {args.summary_file}")
        return 1

    dashboard = Dashboard(DASHBOARD_PATH, args.summary_file)
    # Render an initial placeholder so the browser can load immediately.
    dashboard.render()

    exit_code = _execute_tests(args, dashboard)

    if not _run_post_coverage_commands(dashboard):
        exit_code = 1

    dashboard.finalize(exit_code == 0)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
