#!/usr/bin/env python3
"""F1-23 Phase B platform probes for F1-20 and F1-11.

These probes validate the parts of the newly merged F1-20 (Gemini + fallback)
and F1-11 (deployment / Sandbox bootstrap) work that does not need live
provider credentials:

* F1-20 fails closed when LLM configuration is incomplete.
* F1-20 honours ``ALLOW_SCENARIO_ID`` in ``AGENT_MODE=llm`` without calling a
  live provider (the scripted path is selected before the LLM client is built).
* F1-20 production guards reject ``DEMO_MODE=true``.
* F1-11 Sandbox bootstrap fails closed for mock mode, non-Sandbox URLs and a
  missing Sandbox buyer.
* F1-11 deployment template and guide contain the required settings/steps.

Live Gemini calls and real PayPal Sandbox calls remain blocked; this script
never fabricates a provider response.

Run from the repository root:

    .venv\\\\Scripts\\\\python.exe docs\\\\qa\\\\run_phase_b_platform.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PHASE_A_SCRIPT = ROOT / "docs" / "qa" / "run_phase_a.py"
EVIDENCE_ROOT = ROOT / "docs" / "evidence" / "F1-23" / "phase-b"
F1_20_ROOT = EVIDENCE_ROOT / "f1-20"
F1_11_ROOT = EVIDENCE_ROOT / "f1-11"
STATIC_ROOT = EVIDENCE_ROOT / "static"
SCENARIOS_PATH = ROOT / "tests" / "scenarios" / "scenarios.json"


def _load_phase_a() -> Any:
    spec = importlib.util.spec_from_file_location("f1_23_phase_a", PHASE_A_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the Phase A harness")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


phase_a = _load_phase_a()


def _run(
    name: str,
    args: list[str],
    env_updates: dict[str, str],
    *,
    expected_exit: int,
    expected_fragments: list[str],
    output_path: Path,
) -> dict[str, Any]:
    """Run a subprocess and persist its exact output."""
    env = os.environ.copy()
    for key in (
        "APP_ENV",
        "DEMO_MODE",
        "PAYPAL_MODE",
        "PAYPAL_BASE_URL",
        "PAYPAL_SANDBOX_BUYER_EMAIL",
        "AGENT_MODE",
        "ALLOW_SCENARIO_ID",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_API_KEY",
        "DATABASE_URL",
    ):
        env.pop(key, None)
    env.update(env_updates)
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    combined = (completed.stdout or "") + (completed.stderr or "")
    missing = [fragment for fragment in expected_fragments if fragment not in combined]
    passed = completed.returncode == expected_exit and not missing
    evidence = {
        "probe": name,
        "command": [sys.executable, *args],
        "environment": env_updates,
        "expected_exit": expected_exit,
        "actual_exit": completed.returncode,
        "expected_fragments": expected_fragments,
        "missing_fragments": missing,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "passed": passed,
    }
    phase_a.dump(output_path, evidence)
    return phase_a.check(
        name,
        passed,
        f"exit={expected_exit}; fragments={expected_fragments}",
        f"exit={completed.returncode}; missing={missing}",
        note="See the matching JSON evidence file for exact stdout/stderr.",
    )


def _base_env(db_path: Path) -> dict[str, str]:
    return {
        "APP_ENV": "local",
        "DEMO_MODE": "false",
        "PAYPAL_MODE": "mock",
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "PUBLIC_BASE_URL": "http://localhost:8000",
    }


def _probe_llm_missing_key() -> dict[str, Any]:
    snippet = """
import json
from fastapi.testclient import TestClient
from app.main import create_app

try:
    with TestClient(create_app()):
        pass
except BaseException as exc:
    message = str(exc)
    print(json.dumps({"type": type(exc).__name__, "message": message}))
    raise SystemExit(
        0
        if type(exc).__name__ == "UpstreamError"
        and "LLM configuration is incomplete" in message
        else 1
    )
raise SystemExit(1)
""".strip()
    with tempfile.TemporaryDirectory(prefix="f1-23-b-llm-missing-") as temp_dir:
        env = _base_env(Path(temp_dir) / "qa.db")
        env.update(
            {
                "AGENT_MODE": "llm",
                "ALLOW_SCENARIO_ID": "true",
                "LLM_PROVIDER": "gemini",
                "LLM_MODEL": "gemini-test",
                "LLM_API_KEY": "",
            }
        )
        return _run(
            "F1-20 startup fails closed when LLM_API_KEY is missing",
            ["-c", snippet],
            env,
            expected_exit=0,
            expected_fragments=["UpstreamError", "LLM configuration is incomplete"],
            output_path=F1_20_ROOT / "missing-api-key-startup.json",
        )


def _probe_production_guard() -> dict[str, Any]:
    snippet = """
from app.core.config import Settings

try:
    Settings()
except BaseException as exc:
    message = str(exc)
    print(type(exc).__name__ + ": " + message)
    raise SystemExit(0 if "DEMO_MODE=true is forbidden" in message else 1)
raise SystemExit(1)
""".strip()
    with tempfile.TemporaryDirectory(prefix="f1-23-b-prod-guard-") as temp_dir:
        env = _base_env(Path(temp_dir) / "qa.db")
        env.update(
            {
                "APP_ENV": "production",
                "DEMO_MODE": "true",
                "PAYPAL_MODE": "real",
                "AGENT_MODE": "llm",
                "LLM_PROVIDER": "gemini",
                "LLM_MODEL": "gemini-test",
                "LLM_API_KEY": "fake-test-key",
            }
        )
        return _run(
            "F1-20 production guard rejects DEMO_MODE=true",
            ["-c", snippet],
            env,
            expected_exit=0,
            expected_fragments=["ValidationError", "DEMO_MODE=true is forbidden"],
            output_path=F1_20_ROOT / "production-demo-guard.json",
        )


def _probe_llm_scenario_override() -> dict[str, Any]:
    """Exercise the public HTTP contract with a dummy LLM configuration.

    The request supplies ``scenario_id``. The factory returns ``ScriptedAgent``
    before constructing ``GeminiClient``, so no live provider is contacted.
    """
    from fastapi.testclient import TestClient

    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))["scenarios"]
    scenario = next(item for item in scenarios if item["id"].startswith("S01_"))
    output = F1_20_ROOT / "llm-scenario-override"
    checks: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="f1-23-b-llm-override-") as temp_dir:
        db_path = Path(temp_dir) / "qa.db"
        os.environ.update(
            {
                "APP_ENV": "local",
                "DEMO_MODE": "true",
                "PAYPAL_MODE": "mock",
                "AGENT_MODE": "llm",
                "ALLOW_SCENARIO_ID": "true",
                "LLM_PROVIDER": "gemini",
                "LLM_MODEL": "gemini-test",
                "LLM_API_KEY": "fake-test-key",
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "PUBLIC_BASE_URL": "http://localhost:8000",
                "CORS_ORIGINS": "http://localhost:5173",
            }
        )
        phase_a.clear_caches()
        from app.main import create_app

        with TestClient(create_app()) as client:
            health_response = client.get("/health")
            health = health_response.json()
            phase_a.dump(
                output / "health.json",
                {"status_code": health_response.status_code, "body": health},
            )
            checks.append(
                phase_a.check(
                    "health reports AGENT_MODE=llm",
                    health_response.status_code == 200 and health.get("agent_mode") == "llm",
                    "200 with agent_mode=llm",
                    f"{health_response.status_code} with agent_mode={health.get('agent_mode')}",
                )
            )

            payload = {
                "customer_message": scenario["customer_message"],
                "scenario_id": scenario["id"],
            }
            idempotency_key = f"qa-f1-23-b-llm-{uuid.uuid4().hex}"
            phase_a.dump(
                output / "request.json",
                {
                    "method": "POST",
                    "path": "/api/v1/invoices/INV-001/proposals",
                    "headers": {"Idempotency-Key": idempotency_key},
                    "body": payload,
                },
            )
            proposal_response = client.post(
                "/api/v1/invoices/INV-001/proposals",
                headers={"Idempotency-Key": idempotency_key},
                json=payload,
            )
            proposal = proposal_response.json()
            phase_a.dump(
                output / "response.json",
                {"status_code": proposal_response.status_code, "body": proposal},
            )
            checks.append(
                phase_a.check(
                    "scenario override returns PENDING_MERCHANT",
                    proposal_response.status_code == 200
                    and proposal.get("status") == "PENDING_MERCHANT",
                    "200 / PENDING_MERCHANT",
                    f"{proposal_response.status_code} / {proposal.get('status')}",
                )
            )
            checks.append(
                phase_a.check(
                    "scripted intent is used instead of a live LLM call",
                    (proposal.get("customer_intent") or {}).get("available_now") == "300.00",
                    "available_now=300.00",
                    (proposal.get("customer_intent") or {}).get("available_now"),
                )
            )

            proposal_id = proposal["proposal_id"]
            events_response = client.get(
                "/api/v1/audit-events",
                params={"proposal_id": proposal_id, "limit": 100},
            )
            events = events_response.json()
            phase_a.dump(
                output / "audit-events.json",
                {"status_code": events_response.status_code, "body": events},
            )
            actions = [event["action"] for event in events.get("items", [])]
            checks.append(
                phase_a.check(
                    "proposal audit trail is persisted",
                    "PROPOSAL_DRAFTED" in actions,
                    "PROPOSAL_DRAFTED present",
                    actions,
                )
            )
            checks.append(
                phase_a.check(
                    "no fallback audit is emitted for the scripted override",
                    "LLM_FALLBACK_ACTIVATED" not in actions,
                    "LLM_FALLBACK_ACTIVATED absent",
                    actions,
                )
            )

        from app.core.db import get_engine

        get_engine().dispose()
        phase_a.clear_caches()

    result = {
        "probe": "F1-20 scenario override in AGENT_MODE=llm",
        "checks": checks,
        "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "note": (
            "No live Gemini call is made: a non-null scenario_id selects the scripted "
            "agent before GeminiClient is constructed. This validates wiring and the "
            "scenario override, not live LLM quality."
        ),
    }
    phase_a.dump(output / "result.json", result)
    return result


def _probe_sandbox_guards() -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="f1-23-b-sandbox-mock-") as temp_dir:
        env = _base_env(Path(temp_dir) / "qa.db")
        env.update(
            {
                "PAYPAL_MODE": "mock",
                "PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com",
                "PAYPAL_SANDBOX_BUYER_EMAIL": "buyer@example.com",
            }
        )
        probes.append(
            _run(
                "F1-11 Sandbox bootstrap rejects PAYPAL_MODE=mock",
                ["-m", "app.seed.sandbox_bootstrap"],
                env,
                expected_exit=1,
                expected_fragments=["Sandbox bootstrap requires PAYPAL_MODE=real"],
                output_path=F1_11_ROOT / "guard-mock-mode.json",
            )
        )
    with tempfile.TemporaryDirectory(prefix="f1-23-b-sandbox-url-") as temp_dir:
        env = _base_env(Path(temp_dir) / "qa.db")
        env.update(
            {
                "PAYPAL_MODE": "real",
                "PAYPAL_BASE_URL": "https://api-m.paypal.com",
                "PAYPAL_SANDBOX_BUYER_EMAIL": "buyer@example.com",
            }
        )
        probes.append(
            _run(
                "F1-11 Sandbox bootstrap rejects a non-Sandbox URL",
                ["-m", "app.seed.sandbox_bootstrap"],
                env,
                expected_exit=1,
                expected_fragments=[
                    "Sandbox bootstrap refuses to run against a non-Sandbox PayPal URL"
                ],
                output_path=F1_11_ROOT / "guard-non-sandbox-url.json",
            )
        )
    with tempfile.TemporaryDirectory(prefix="f1-23-b-sandbox-buyer-") as temp_dir:
        env = _base_env(Path(temp_dir) / "qa.db")
        env.update(
            {
                "PAYPAL_MODE": "real",
                "PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com",
                "PAYPAL_SANDBOX_BUYER_EMAIL": "",
            }
        )
        probes.append(
            _run(
                "F1-11 Sandbox bootstrap rejects a missing Sandbox buyer",
                ["-m", "app.seed.sandbox_bootstrap"],
                env,
                expected_exit=1,
                expected_fragments=["Sandbox bootstrap requires PAYPAL_SANDBOX_BUYER_EMAIL"],
                output_path=F1_11_ROOT / "guard-missing-buyer.json",
            )
        )
    return probes


def _static_checks() -> dict[str, Any]:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    deploy_text = (ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    required_env = [
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_API_KEY",
        "PAYPAL_SANDBOX_BUYER_EMAIL",
        "ALLOW_SANDBOX_PAYMENT_SHORTCUT",
        "PUBLIC_BASE_URL",
    ]
    required_deploy = [
        "python -m app.seed.sandbox_bootstrap",
        "PAYPAL_WEBHOOK_ID",
        "PAYPAL_SANDBOX_BUYER_EMAIL",
    ]
    checks = [
        phase_a.check(
            f".env.example documents {name}",
            name in env_text,
            f"{name} present",
            f"{name} present" if name in env_text else f"{name} missing",
        )
        for name in required_env
    ]
    checks.extend(
        phase_a.check(
            f"DEPLOY.md documents {fragment}",
            fragment in deploy_text,
            f"{fragment} present",
            f"{fragment} present" if fragment in deploy_text else f"{fragment} missing",
        )
        for fragment in required_deploy
    )
    result = {
        "probe": "F1-11 deployment template and guide completeness",
        "checks": checks,
        "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "evidence": {
            "env_example": ".env.example",
            "deploy_guide": "docs/DEPLOY.md",
        },
    }
    phase_a.dump(STATIC_ROOT / "f1-11-config-checks.json", result)
    return result


def main() -> int:
    F1_20_ROOT.mkdir(parents=True, exist_ok=True)
    F1_11_ROOT.mkdir(parents=True, exist_ok=True)
    STATIC_ROOT.mkdir(parents=True, exist_ok=True)

    scenario_override = _probe_llm_scenario_override()
    checks: list[dict[str, Any]] = [
        _probe_llm_missing_key(),
        _probe_production_guard(),
        *scenario_override["checks"],
        *_probe_sandbox_guards(),
    ]
    static = _static_checks()
    checks.extend(static["checks"])

    summary = {
        "generated_at": phase_a.utc_now(),
        "phase": "B",
        "scope": "F1-20 and F1-11 available-scope probes",
        "checks": checks,
        "scenario_override": scenario_override,
        "static": static,
        "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "blocked": [
            {
                "id": "BLK-B02",
                "scope": "Live Gemini LLM",
                "reason": "No authorized LLM_API_KEY is available; no live provider call was made.",
            },
            {
                "id": "BLK-B01",
                "scope": "PayPal Sandbox real",
                "reason": (
                    "No Sandbox credentials, buyer or public HTTPS webhook URL are available."
                ),
            },
        ],
    }
    phase_a.dump(EVIDENCE_ROOT / "platform-summary.json", summary)
    for item in checks:
        print(f"{'PASS' if item['passed'] else 'FAIL'}: {item['check']}")
    print(f"OVERALL: {summary['status']}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
