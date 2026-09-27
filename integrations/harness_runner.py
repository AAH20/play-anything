"""Opt-in localhost bridge for explicitly trusted, fixed-argv harness profiles.

Nothing in this module starts the bridge automatically. Run it as a separate
process only after creating a private profile file and setting a strong
LOCAL_RUNNER_ACCESS_TOKEN.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


MAX_REQUEST_BYTES = 16 * 1024
MAX_GOAL_CHARS = 8_000
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_ACTIVE_PROCESSES = 2
PROCESS_TIMEOUT_SECONDS = 40
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
INTEGRATIONS = {"harness", "openmanus", "understand-anything"}
HARNESS_IDS = {"codex", "claude-code", "cursor", "antigravity", "opencode", "hermes", "openmanus"}
AUTH_MODES = {"subscription", "api", "manual", "local"}
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SECRET_NAME = re.compile(r"(?:PASSWORD|SECRET|TOKEN|API[_-]?KEY|CREDENTIAL|AUTH)", re.IGNORECASE)


class ProfileError(ValueError):
    """Profile file does not match the strict local configuration contract."""


@dataclass(frozen=True)
class Profile:
    integration_id: str
    operation: str
    harness_id: str
    auth_mode: str
    enabled: bool
    workspace: str
    argv: tuple[str, ...]
    name: str
    prompt_prefix: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return self.integration_id, self.harness_id, self.auth_mode

    @property
    def label(self) -> str:
        return self.name


@dataclass
class ProcessContext:
    process: subprocess.Popen[bytes]
    profile: Profile
    cancelled: threading.Event
    output: bytearray
    overflow: threading.Event
    output_lock: threading.Lock
    started_at: float


@dataclass(frozen=True)
class RunResult:
    status_code: int
    body: dict[str, Any]


def _is_plain_string(value: Any, *, maximum: int, allow_empty: bool = False) -> bool:
    return isinstance(value, str) and (allow_empty or bool(value.strip())) and len(value) <= maximum and "\x00" not in value


def load_profiles(path: str | os.PathLike[str]) -> dict[tuple[str, str, str], Profile]:
    """Read trusted operator configuration; request data can never alter it."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileError("Could not read the local runner profile file.") from exc
    if not isinstance(data, dict) or set(data) != {"version", "profiles"} or data.get("version") != 1:
        raise ProfileError("Profile file must contain version 1 and a profiles list.")
    rows = data["profiles"]
    if not isinstance(rows, list) or len(rows) > 64:
        raise ProfileError("Profile file must contain at most 64 profiles.")

    profiles: dict[tuple[str, str, str], Profile] = {}
    allowed = {"integrationId", "operation", "harnessId", "authMode", "enabled", "workspace", "argv", "name", "promptPrefix"}
    for row in rows:
        if not isinstance(row, dict) or set(row) - allowed:
            raise ProfileError("A profile contains unsupported fields.")
        integration = row.get("integrationId")
        operation = row.get("operation")
        harness = row.get("harnessId")
        auth_mode = row.get("authMode")
        if integration not in INTEGRATIONS or harness not in HARNESS_IDS or auth_mode not in AUTH_MODES:
            raise ProfileError("A profile has an unsupported integration, harness, or auth mode.")
        if not isinstance(operation, str) or not SAFE_ID.fullmatch(operation):
            raise ProfileError("Profile operation must be a stable lowercase identifier.")
        enabled = row.get("enabled")
        if not isinstance(enabled, bool):
            raise ProfileError("Each profile must explicitly set enabled to true or false.")
        name = row.get("name")
        if not _is_plain_string(name, maximum=100):
            raise ProfileError("Profile name must be a non-empty string of at most 100 characters.")
        workspace_value = row.get("workspace")
        if not _is_plain_string(workspace_value, maximum=2048) or not Path(workspace_value).is_absolute():
            raise ProfileError("Profile workspace must be an absolute local directory path.")
        workspace = str(Path(workspace_value).resolve())
        if enabled and not Path(workspace).is_dir():
            raise ProfileError("An enabled profile workspace must already exist as a directory.")
        argv = row.get("argv")
        if not isinstance(argv, list) or not argv or len(argv) > 64 or any(not _is_plain_string(arg, maximum=4096) for arg in argv):
            raise ProfileError("Profile argv must contain between 1 and 64 non-empty strings.")
        if sum(arg == "{prompt}" for arg in argv) != 1:
            raise ProfileError("Profile argv must contain {prompt} exactly once as a standalone argument.")
        if any("${" in arg or "\n" in arg or "\r" in arg for arg in argv):
            raise ProfileError("Profile argv cannot contain environment substitutions or multiline arguments.")
        prefix = row.get("promptPrefix", "")
        if not _is_plain_string(prefix, maximum=500, allow_empty=True):
            raise ProfileError("Profile promptPrefix must be a string of at most 500 characters.")
        if integration == "understand-anything" and prefix.strip() != "/understand":
            raise ProfileError("UnderstandAnything profiles must explicitly invoke the /understand host plugin.")
        profile = Profile(integration, operation, harness, auth_mode, enabled, workspace, tuple(argv), name.strip(), prefix)
        if profile.key in profiles:
            raise ProfileError("Profile keys must be unique by integration, harness, and auth mode.")
        profiles[profile.key] = profile
    return profiles


def validate_request(body: Any) -> dict[str, Any]:
    allowed = {"requestId", "integrationId", "operation", "harnessId", "authMode", "goal", "graph"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise ValueError("Request must contain only documented fields.")
    try:
        request_id = str(uuid.UUID(body.get("requestId", "")))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("requestId must be a server-generated UUID.") from exc
    integration = body.get("integrationId")
    harness = body.get("harnessId")
    auth_mode = body.get("authMode")
    operation = body.get("operation")
    goal = body.get("goal")
    if integration not in INTEGRATIONS or harness not in HARNESS_IDS or auth_mode not in AUTH_MODES:
        raise ValueError("Unsupported integration, harness, or auth mode.")
    if not isinstance(operation, str) or not SAFE_ID.fullmatch(operation):
        raise ValueError("operation must be a stable lowercase identifier.")
    if not _is_plain_string(goal, maximum=MAX_GOAL_CHARS):
        raise ValueError(f"goal must contain between 1 and {MAX_GOAL_CHARS} characters.")
    graph = body.get("graph")
    if graph is not None:
        if not isinstance(graph, dict) or set(graph) - {"name", "nodes", "edges"}:
            raise ValueError("graph must contain only bounded snapshot metadata.")
        if not _is_plain_string(graph.get("name", "Repository"), maximum=200):
            raise ValueError("graph name must be at most 200 characters.")
        for field in ("nodes", "edges"):
            value = graph.get(field, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 5_000_000:
                raise ValueError("graph counts must be non-negative integers no greater than 5 million.")
    return {**body, "requestId": request_id}


def _known_secret_values(environment: dict[str, str], access_token: str) -> list[str]:
    values = {access_token}
    values.update(value for key, value in environment.items() if SECRET_NAME.search(key) and value)
    return sorted((value for value in values if len(value) >= 4), key=len, reverse=True)


def redact_output(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    return text


class HarnessRunner:
    """Runs a profile allowlist; HTTP callers cannot supply executable details."""

    def __init__(
        self,
        profiles: dict[tuple[str, str, str], Profile],
        access_token: str,
        *,
        max_processes: int = MAX_ACTIVE_PROCESSES,
        timeout_seconds: float = PROCESS_TIMEOUT_SECONDS,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
        environment: dict[str, str] | None = None,
    ) -> None:
        if not 1 <= max_processes <= MAX_ACTIVE_PROCESSES:
            raise ValueError(f"max_processes must be between 1 and {MAX_ACTIVE_PROCESSES}.")
        if not 0 < timeout_seconds <= PROCESS_TIMEOUT_SECONDS:
            raise ValueError(f"timeout_seconds must be greater than 0 and at most {PROCESS_TIMEOUT_SECONDS}.")
        if not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES:
            raise ValueError(f"max_output_bytes must be between 1 and {MAX_OUTPUT_BYTES}.")
        self.profiles = dict(profiles)
        self.access_token = access_token
        self.max_processes = max_processes
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.popen = popen
        self.environment = dict(os.environ if environment is None else environment)
        self.secrets = _known_secret_values(self.environment, access_token)
        self._slots = threading.BoundedSemaphore(max_processes)
        self._lock = threading.RLock()
        self._active: dict[str, ProcessContext] = {}

    def health(self) -> dict[str, Any]:
        with self._lock:
            enabled = sum(profile.enabled for profile in self.profiles.values())
            active = len(self._active)
        return {"enabled": True, "mode": "local_harness_runner", "enabledProfiles": enabled, "activeProcesses": active, "maxProcesses": self.max_processes}

    def _terminate(self, process: subprocess.Popen[bytes]) -> None:
        try:
            if os.name == "nt":
                if process.poll() is None:
                    process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError, AttributeError):
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        try:
            process.wait(timeout=0.35)
        except subprocess.TimeoutExpired:
            pass
        try:
            # The main CLI may have exited while a descendant still holds the
            # captured pipe; on POSIX always finish the isolated process group.
            if os.name == "nt":
                if process.poll() is None:
                    process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
        try:
            process.wait(timeout=1)
        except (subprocess.TimeoutExpired, OSError):
            pass

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            context = self._active.get(request_id)
            if context is None:
                return False
            context.cancelled.set()
        self._terminate(context.process)
        return True

    def run(self, raw_body: Any) -> RunResult:
        try:
            request = validate_request(raw_body)
        except ValueError as exc:
            return RunResult(400, {"error": str(exc), "code": "invalid_request"})
        profile = self.profiles.get((request["integrationId"], request["harnessId"], request["authMode"]))
        if profile is None or not profile.enabled:
            return RunResult(409, {"error": "No enabled trusted profile matches this integration, harness, and auth mode.", "code": "profile_unavailable"})
        if profile.operation != request["operation"]:
            return RunResult(409, {"error": "The requested operation does not match the trusted profile.", "code": "operation_mismatch"})
        if not self._slots.acquire(blocking=False):
            return RunResult(429, {"error": "The local runner is at its process limit.", "code": "process_limit"})

        request_id = request["requestId"]
        with self._lock:
            if request_id in self._active:
                self._slots.release()
                return RunResult(409, {"error": "requestId is already active.", "code": "duplicate_request"})
            prompt = request["goal"].strip()
            graph = request.get("graph")
            if graph is not None:
                prompt += ("\n\nRepository snapshot metadata (no graph content was sent): "
                           f"{graph.get('name', 'Repository')} — {graph.get('nodes', 0)} nodes, {graph.get('edges', 0)} edges.")
            if profile.prompt_prefix:
                prompt = f"{profile.prompt_prefix} {prompt}"
            argv = [prompt if arg == "{prompt}" else arg for arg in profile.argv]

            try:
                process = self.popen(
                    argv,
                    cwd=profile.workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    shell=False,
                    close_fds=True,
                    start_new_session=(os.name != "nt"),
                    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
                    env=self.environment,
                )
            except (OSError, ValueError):
                self._slots.release()
                return RunResult(503, {"error": "Could not start the configured local harness process.", "code": "process_start_failed"})

            context = ProcessContext(process, profile, threading.Event(), bytearray(), threading.Event(), threading.Lock(), time.monotonic())
            self._active[request_id] = context

        def collect_output() -> None:
            stream = process.stdout
            if stream is None:
                return
            try:
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    with context.output_lock:
                        remaining = self.max_output_bytes - len(context.output)
                        if remaining > 0:
                            context.output.extend(chunk[:remaining])
                        if len(chunk) > remaining:
                            context.overflow.set()
            except (OSError, ValueError):
                pass

        reader = threading.Thread(target=collect_output, name="harness-output-reader", daemon=True)
        reader.start()
        failure: RunResult | None = None
        try:
            while process.poll() is None:
                if context.cancelled.is_set():
                    failure = RunResult(409, {"error": "The local harness run was cancelled.", "code": "cancelled"})
                    break
                if context.overflow.is_set():
                    failure = RunResult(413, {"error": "The local harness exceeded the 1 MiB combined output limit.", "code": "output_limit"})
                    break
                if time.monotonic() - context.started_at >= self.timeout_seconds:
                    failure = RunResult(504, {"error": "The local harness exceeded the 40 second execution limit.", "code": "timeout"})
                    break
                time.sleep(0.025)
            if failure is None and context.cancelled.is_set():
                failure = RunResult(409, {"error": "The local harness run was cancelled.", "code": "cancelled"})
            if failure is None and context.overflow.is_set():
                failure = RunResult(413, {"error": "The local harness exceeded the 1 MiB combined output limit.", "code": "output_limit"})
            if failure is not None:
                self._terminate(process)
            else:
                process.wait(timeout=1)
            reader.join(timeout=1)
            if failure is None and context.overflow.is_set():
                failure = RunResult(413, {"error": "The local harness exceeded the 1 MiB combined output limit.", "code": "output_limit"})
                self._terminate(process)
            with context.output_lock:
                output = bytes(context.output).decode("utf-8", errors="replace")
            output = redact_output(output, self.secrets)
            if failure is not None:
                return failure
            exit_code = process.returncode
            if exit_code != 0:
                return RunResult(422, {"error": "The local harness exited unsuccessfully.", "code": "process_failed", "exitCode": exit_code, "output": output})
            return RunResult(200, {"status": "succeeded", "workspace": profile.workspace, "profile": profile.label, "output": output, "exitCode": 0, "usage": None})
        except (OSError, subprocess.SubprocessError):
            self._terminate(process)
            return RunResult(502, {"error": "The local harness process could not be completed.", "code": "process_failed"})
        finally:
            if process.poll() is None:
                self._terminate(process)
            reader.join(timeout=1)
            if process.stdout is not None:
                try:
                    process.stdout.close()
                except OSError:
                    pass
            with self._lock:
                self._active.pop(request_id, None)
            self._slots.release()


class _ThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(runner: HarnessRunner, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    if host != DEFAULT_HOST:
        raise ValueError("The harness runner can bind only to 127.0.0.1.")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *args: Any) -> None:
            # Request paths and provider output are deliberately not logged.
            return

        def _send(self, status: int, body: dict[str, Any]) -> None:
            payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            # Request bodies rejected before they are consumed must not remain
            # on a keep-alive connection and be parsed as a second request.
            self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _local_request(self) -> bool:
            address = self.client_address[0].split("%", 1)[0]
            try:
                if not ipaddress.ip_address(address).is_loopback:
                    return False
            except ValueError:
                return False
            host_header = self.headers.get("Host", "")
            parsed_host = urlsplit(f"//{host_header}")
            if parsed_host.hostname not in {"127.0.0.1", "localhost", "::1"}:
                return False
            origin = self.headers.get("Origin")
            if origin:
                parsed_origin = urlsplit(origin)
                if parsed_origin.scheme not in {"http", "https"} or parsed_origin.hostname not in {"127.0.0.1", "localhost", "::1"}:
                    return False
            return True

        def _authorized(self) -> bool:
            value = self.headers.get("Authorization", "")
            if not value.startswith("Bearer "):
                return False
            supplied = value[7:].strip()
            return bool(supplied) and hmac.compare_digest(supplied, runner.access_token)

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send(404, {"error": "Not found.", "code": "not_found"})
                return
            if not self._local_request():
                self._send(403, {"error": "Loopback requests only.", "code": "local_only"})
                return
            self._send(200, runner.health())

        def do_POST(self) -> None:
            if self.path != "/run":
                self._send(404, {"error": "Not found.", "code": "not_found"})
                return
            if not self._local_request():
                self._send(403, {"error": "Loopback requests only.", "code": "local_only"})
                return
            if not self._authorized():
                self._send(401, {"error": "A valid local runner bearer token is required.", "code": "unauthorized"})
                return
            if self.headers.get("Transfer-Encoding") or not self.headers.get("Content-Length", "").isdigit():
                self._send(411, {"error": "A bounded Content-Length is required.", "code": "length_required"})
                return
            length = int(self.headers["Content-Length"])
            if length > MAX_REQUEST_BYTES:
                self._send(413, {"error": "Request body exceeds the 16 KiB limit.", "code": "request_too_large"})
                return
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("invalid body")
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError, ValueError):
                self._send(400, {"error": "Request body must be valid bounded JSON.", "code": "invalid_json"})
                return
            result = runner.run(body)
            self._send(result.status_code, result.body)

        def do_DELETE(self) -> None:
            match = re.fullmatch(r"/run/([0-9a-fA-F-]{36})", self.path)
            if not match:
                self._send(404, {"error": "Not found.", "code": "not_found"})
                return
            if not self._local_request():
                self._send(403, {"error": "Loopback requests only.", "code": "local_only"})
                return
            if not self._authorized():
                self._send(401, {"error": "A valid local runner bearer token is required.", "code": "unauthorized"})
                return
            try:
                request_id = str(uuid.UUID(match.group(1)))
            except ValueError:
                self._send(404, {"error": "Not found.", "code": "not_found"})
                return
            if not runner.cancel(request_id):
                self._send(404, {"error": "No active run matched requestId.", "code": "run_not_found"})
                return
            self._send(202, {"status": "cancelling", "requestId": request_id})

    return _ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the opt-in loopback harness bridge.")
    parser.add_argument("--profiles", default=os.environ.get("LOCAL_RUNNER_PROFILES", "integrations/harness-profiles.json"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    token = os.environ.get("LOCAL_RUNNER_ACCESS_TOKEN", "")
    if len(token) < 32:
        parser.error("Set LOCAL_RUNNER_ACCESS_TOKEN to a random value of at least 32 characters.")
    try:
        profiles = load_profiles(args.profiles)
    except ProfileError as exc:
        parser.error(str(exc))
    runner = HarnessRunner(profiles, token)
    server = make_server(runner, DEFAULT_HOST, args.port)
    print(f"Local harness runner listening on http://{DEFAULT_HOST}:{args.port}; {runner.health()['enabledProfiles']} explicitly enabled profile(s). Press Ctrl-C to stop.")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
