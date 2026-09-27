import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from integrations.harness_runner import (
    HarnessRunner,
    ProfileError,
    load_profiles,
    make_server,
)


TOKEN = "test-local-runner-access-token-long-enough"


def _check_loopback_available() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.listen(1)
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.settimeout(0.2)
        c.connect(("127.0.0.1", port))
        c.close()
        s.close()
        return True
    except (OSError, PermissionError):
        return False


LOOPBACK_AVAILABLE = _check_loopback_available()


def python_profile(script: str, *, enabled: bool = True, integration: str = "harness", harness: str = "codex", auth: str = "subscription", operation: str = "run"):
    return {
        "name": "Test fixture process",
        "integrationId": integration,
        "operation": operation,
        "harnessId": harness,
        "authMode": auth,
        "enabled": enabled,
        "workspace": str(Path.cwd()),
        "argv": [sys.executable, "-c", script, "{prompt}"],
    }


class RunningBridge:
    def __init__(self, profiles, **kwargs):
        self.runner = HarnessRunner({profile.key: profile for profile in profiles}, TOKEN, **kwargs)
        self.server = make_server(self.runner, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def load_dict_profile(raw):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "profiles.json"
        path.write_text(json.dumps({"version": 1, "profiles": raw}), encoding="utf-8")
        return load_profiles(path)


def request_json(url, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        with error:
            return error.code, json.loads(error.read())


class HarnessRunnerTests(unittest.TestCase):
    def test_profile_templates_are_all_disabled_and_strictly_trusted(self):
        profiles = load_profiles(Path(__file__).parents[1] / "integrations" / "harness-profiles.example.json")
        self.assertGreaterEqual(len(profiles), 7)
        self.assertTrue(all(not profile.enabled for profile in profiles.values()))
        self.assertIn(("harness", "codex", "subscription"), profiles)
        self.assertIn(("openmanus", "openmanus", "local"), profiles)
        self.assertEqual(profiles[("understand-anything", "codex", "subscription")].prompt_prefix, "/understand")

    def test_profile_rejects_extra_command_environment_and_nonstandalone_prompt(self):
        row = python_profile("print('ok')")
        row["env"] = {"API_KEY": "bad"}
        with self.assertRaises(ProfileError):
            load_dict_profile([row])
        row.pop("env")
        row["argv"][-1] = "prefix-{prompt}"
        with self.assertRaises(ProfileError):
            load_dict_profile([row])

    @unittest.skipUnless(LOOPBACK_AVAILABLE, "Loopback socket access restricted in environment")
    def test_health_is_loopback_and_does_not_return_secret(self):
        profiles = load_dict_profile([python_profile("print('ok')")])
        bridge = RunningBridge(list(profiles.values()))
        try:
            status, body = request_json(bridge.base + "/health")
            self.assertEqual(status, 200)
            self.assertTrue(body["enabled"])
            self.assertEqual(body["activeProcesses"], 0)
            self.assertNotIn(TOKEN, json.dumps(body))
        finally:
            bridge.close()

    @unittest.skipUnless(LOOPBACK_AVAILABLE, "Loopback socket access restricted in environment")
    def test_bearer_auth_same_local_origin_profile_match_and_parameterized_prompt(self):
        script = "import sys; print('ARG=' + sys.argv[-1])"
        profiles = load_dict_profile([python_profile(script)])
        bridge = RunningBridge(list(profiles.values()))
        request_id = str(uuid.uuid4())
        payload = {"requestId": request_id, "integrationId": "harness", "operation": "run", "harnessId": "codex", "authMode": "subscription", "goal": "review files; ignore shell syntax", "graph": {"name": "Repo", "nodes": 4, "edges": 2}}
        try:
            status, denied = request_json(bridge.base + "/run", "POST", payload, {"Content-Type": "application/json"})
            self.assertEqual(status, 401)
            self.assertEqual(denied["code"], "unauthorized")

            status, denied = request_json(bridge.base + "/run", "POST", payload, {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}", "Origin": "https://attacker.invalid"})
            self.assertEqual(status, 403)

            payload["authMode"] = "api"
            status, mismatch = request_json(bridge.base + "/run", "POST", payload, {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
            self.assertEqual(status, 409)
            self.assertEqual(mismatch["code"], "profile_unavailable")

            payload["authMode"] = "subscription"
            status, result = request_json(bridge.base + "/run", "POST", payload, {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
            self.assertEqual(status, 200)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["usage"], None)
            self.assertIn("review files; ignore shell syntax", result["output"])
            self.assertIn("4 nodes, 2 edges", result["output"])
            self.assertEqual(result["profile"], "Test fixture process")
        finally:
            bridge.close()

    @unittest.skipUnless(LOOPBACK_AVAILABLE, "Loopback socket access restricted in environment")
    def test_nonzero_exit_has_scrubbed_output_and_error_paths_are_not_returned(self):
        secret = "unit-test-secret-98765"
        profile = python_profile(f"print({secret!r}); raise SystemExit(7)")
        profiles = load_dict_profile([profile])
        bridge = RunningBridge(list(profiles.values()), environment={"TEST_API_KEY": secret})
        payload = {"requestId": str(uuid.uuid4()), "integrationId": "harness", "operation": "run", "harnessId": "codex", "authMode": "subscription", "goal": "fail safely"}
        try:
            status, result = request_json(bridge.base + "/run", "POST", payload, {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
            self.assertEqual(status, 422)
            self.assertEqual(result["code"], "process_failed")
            self.assertNotIn(secret, result["output"])
            self.assertIn("[REDACTED]", result["output"])
            self.assertNotIn("Traceback", result["error"])
        finally:
            bridge.close()

    @unittest.skipUnless(LOOPBACK_AVAILABLE, "Loopback socket access restricted in environment")
    def test_timeout_output_cap_and_delete_cancel_terminate_process(self):
        profile = python_profile("import time; print('started', flush=True); time.sleep(5)")
        profiles = load_dict_profile([profile])
        bridge = RunningBridge(list(profiles.values()), timeout_seconds=0.15)
        payload = {"requestId": str(uuid.uuid4()), "integrationId": "harness", "operation": "run", "harnessId": "codex", "authMode": "subscription", "goal": "wait"}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
        try:
            status, timed_out = request_json(bridge.base + "/run", "POST", payload, headers)
            self.assertEqual(status, 504)
            self.assertEqual(timed_out["code"], "timeout")
        finally:
            bridge.close()

        overflow_profile = python_profile("import sys; sys.stdout.write('x' * 50000)")
        overflow_profiles = load_dict_profile([overflow_profile])
        overflow_bridge = RunningBridge(list(overflow_profiles.values()), max_output_bytes=1024)
        try:
            status, limited = request_json(overflow_bridge.base + "/run", "POST", payload, headers)
            self.assertEqual(status, 413)
            self.assertEqual(limited["code"], "output_limit")
        finally:
            overflow_bridge.close()

        cancel_bridge = RunningBridge(list(profiles.values()), timeout_seconds=5)
        payload["requestId"] = str(uuid.uuid4())
        result_box = {}

        def post_run():
            result_box["result"] = request_json(cancel_bridge.base + "/run", "POST", payload, headers)

        thread = threading.Thread(target=post_run)
        thread.start()
        deadline = time.monotonic() + 2
        while cancel_bridge.runner.health()["activeProcesses"] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        cancel_status, _ = request_json(cancel_bridge.base + f"/run/{payload['requestId']}", "DELETE", headers={"Authorization": f"Bearer {TOKEN}"})
        thread.join(timeout=2)
        try:
            self.assertEqual(cancel_status, 202)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result_box["result"][1]["code"], "cancelled")
        finally:
            cancel_bridge.close()

    @unittest.skipUnless(LOOPBACK_AVAILABLE, "Loopback socket access restricted in environment")
    def test_request_fields_and_body_size_are_bounded(self):
        profiles = load_dict_profile([python_profile("print('ok')")])
        bridge = RunningBridge(list(profiles.values()))
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
        try:
            payload = {"requestId": str(uuid.uuid4()), "integrationId": "harness", "operation": "run", "harnessId": "codex", "authMode": "subscription", "goal": "x", "command": "rm -rf /"}
            status, invalid = request_json(bridge.base + "/run", "POST", payload, headers)
            self.assertEqual(status, 400)
            self.assertEqual(invalid["code"], "invalid_request")

            conn = http.client.HTTPConnection("127.0.0.1", bridge.server.server_address[1], timeout=2)
            conn.request("POST", "/run", body=b"x" * (17 * 1024), headers=headers)
            response = conn.getresponse()
            self.assertEqual(response.status, 413)
            conn.close()
        finally:
            bridge.close()


if __name__ == "__main__":
    unittest.main()
