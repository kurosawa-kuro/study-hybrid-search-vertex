"""Shared helpers for scripts/*.py and scripts/ops/*.py.

Stdlib-only by design (per scripts/README.md). The functions wrap the most
common shell idioms (gcloud subprocess calls, IAM-gated HTTP requests,
env-var defaults) so individual scripts stay short and focused on intent.

DEFAULTS are loaded at import time from `env/config/setting.yaml` so the
project-wide constants (project_id / region / api_service / training_job /
artifact_repo) live in exactly one place. The YAML parser is a deliberately
minimal hand-rolled flat-key:value reader to keep the stdlib-only promise
(no PyYAML dependency).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "env" / "config" / "setting.yaml"


def _load_settings() -> dict[str, str]:
    """Parse the flat key:value subset of env/config/setting.yaml.

    Supported syntax: top-level `key: value` lines, `#` comments, blank lines.
    Values may be quoted with `"` or `'`. Anything else (nesting, anchors,
    multiline strings) is intentionally rejected to keep this parser tiny.
    """
    settings: dict[str, str] = {}
    if not _SETTINGS_PATH.exists():
        return settings
    for raw in _SETTINGS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            settings[key.upper()] = value
    return settings


DEFAULTS = _load_settings()


def env(name: str, default: str | None = None) -> str:
    """Read an env var with a project-wide default fallback."""
    fallback = default if default is not None else DEFAULTS.get(name, "")
    return os.environ.get(name, fallback)


def run(
    cmd: list[str], *, capture: bool = False, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Thin wrapper around subprocess.run. `capture=True` returns stdout in `.stdout`."""
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def gcloud(*args: str, capture: bool = False) -> str:
    """Invoke gcloud with the supplied args. Returns stripped stdout when capture=True."""
    proc = run(["gcloud", *args], capture=capture)
    return proc.stdout.strip() if capture and proc.stdout else ""


def cloud_run_url(service: str | None = None) -> str:
    """Resolve the Cloud Run Service URL via `gcloud run services describe`."""
    svc = service or env("API_SERVICE")
    return gcloud(
        "run",
        "services",
        "describe",
        svc,
        f"--project={env('PROJECT_ID')}",
        f"--region={env('REGION')}",
        "--format=value(status.url)",
        capture=True,
    )


def identity_token() -> str:
    """Mint an OIDC token for IAM-gated Cloud Run calls."""
    return gcloud("auth", "print-identity-token", capture=True)


def http_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict | None = None,
    timeout: int = 30,
) -> tuple[int, str]:
    """POST/GET JSON with optional Bearer token. Returns (status_code, body_text)."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body


def fail(msg: str, code: int = 1) -> int:
    """Print to stderr and return an exit code (use as `return fail("...")`)."""
    print(msg, file=sys.stderr)
    return code


def print_pretty(body: str) -> None:
    """Best-effort pretty-print of a JSON body (falls back to raw)."""
    try:
        print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(body)
