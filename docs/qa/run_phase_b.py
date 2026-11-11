#!/usr/bin/env python3
"""F1-23 Phase B regression harness.

Re-runs the Phase A S01-S12 validators against the current `main` checkout,
which now includes F1-20 (Gemini + fallback) and F1-11 (deployment tooling).
Evidence is written under `docs/evidence/F1-23/phase-b/regression/`; Phase A
evidence is never overwritten.

Run from the repository root:

    .venv\\Scripts\\python.exe docs\\qa\\run_phase_b.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PHASE_A_SCRIPT = ROOT / "docs" / "qa" / "run_phase_a.py"
EVIDENCE_ROOT = ROOT / "docs" / "evidence" / "F1-23" / "phase-b"
REGRESSION_ROOT = EVIDENCE_ROOT / "regression"
DEFECT_ROOT = EVIDENCE_ROOT / "def-01"
QA_ROOT = ROOT / "docs" / "qa"
SCENARIOS_PATH = ROOT / "tests" / "scenarios" / "scenarios.json"

_BLOCKED_ITEMS = [
    {
        "id": "BLK-B01",
        "scope": "PayPal Sandbox real",
        "dependency": "PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_WEBHOOK_ID, "
        "PAYPAL_MERCHANT_EMAIL, PAYPAL_SANDBOX_BUYER_EMAIL and a public HTTPS URL",
        "affected": "Real payment, real webhook signature, real invoice lifecycle",
        "status": "BLOCKED",
    },
    {
        "id": "BLK-B02",
        "scope": "Live Gemini LLM",
        "dependency": "LLM_PROVIDER, LLM_MODEL and an authorized LLM_API_KEY",
        "affected": "Live intent extraction, tone quality, real-LLM injection resistance",
        "status": "BLOCKED",
    },
    {
        "id": "BLK-B03",
        "scope": "UI integration",
        "dependency": "PR #22 / feat/ui-final-integration merged and deployed with the backend",
        "affected": (
            "Full browser E2E against the real backend; only preview/build smoke is possible"
        ),
        "status": "BLOCKED",
    },
    {
        "id": "BLK-B04",
        "scope": "Deployed backend",
        "dependency": "Public backend URL and deployment credentials",
        "affected": "Deployed-environment E2E; only the UI preview is public",
        "status": "BLOCKED",
    },
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _load_phase_a() -> Any:
    spec = importlib.util.spec_from_file_location("f1_23_phase_a", PHASE_A_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the Phase A harness")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _failure_result(
    phase_a: Any,
    scenario: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    scenario_id = scenario["id"].split("_", 1)[0]
    expected = phase_a.expected_api(scenario)
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario["id"],
        "category": scenario["category"],
        "catalog_outcome": scenario["expected_outcome"],
        "api_expected_status": expected["status"],
        "api_expected_code": expected["code"],
        "actual_status": "ERROR",
        "actual_code": None,
        "http_status": None,
        "status": "FAIL",
        "checks": [
            phase_a.check(
                "scenario execution",
                False,
                "completed",
                f"{type(exc).__name__}: {exc}",
            )
        ],
        "steps": [],
        "proposal_id": None,
        "executed_at": utc_now(),
        "evidence_dir": f"docs/evidence/F1-23/phase-b/regression/{scenario_id}",
        "error": f"{type(exc).__name__}: {exc}",
    }


def _defect_01_analysis(phase_a: Any, scenario: dict[str, Any]) -> dict[str, Any]:
    """Determine whether extra evidence can resolve DEF-01."""
    response_path = REGRESSION_ROOT / "S10" / "02-proposal-response.json"
    audit_path = REGRESSION_ROOT / "S10" / "08-audit-events.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))["body"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))["body"]["items"]
    actual_intent = response.get("customer_intent")
    attempted = response.get("attempted") or []
    actions = [event["action"] for event in audit]
    expected_intent = scenario["expected_intent"]
    missing = actual_intent != expected_intent
    analysis = {
        "defect_id": "DEF-01",
        "scenario": "S10",
        "phase_a_status": "PASS_WITH_OBSERVATION",
        "phase_b_status": "OPEN",
        "catalog_expected_intent": expected_intent,
        "actual_customer_intent": actual_intent,
        "actual_attempted": attempted,
        "audit_actions": actions,
        "api_status": response.get("status"),
        "api_reason": (response.get("blocked_reasons") or [{}])[0].get("code"),
        "can_be_resolved_with_additional_evidence": False,
        "requires_application_change_if_traceability_required": missing,
        "conclusion": (
            "The API correctly blocks INVALID_AGENT_OUTPUT, but neither the response "
            "nor the audit trail persists the rejected 150% intent. Additional QA "
            "evidence cannot reconstruct a value the application never stores. "
            "Resolving the traceability gap requires an application change (or an "
            "explicit decision to accept the limitation)."
        ),
        "evidence": {
            "response": "docs/evidence/F1-23/phase-b/regression/S10/02-proposal-response.json",
            "audit": "docs/evidence/F1-23/phase-b/regression/S10/08-audit-events.json",
            "result": "docs/evidence/F1-23/phase-b/regression/S10/result.json",
        },
        "generated_at": utc_now(),
    }
    phase_a.dump(DEFECT_ROOT / "analysis.json", analysis)
    return analysis


def _read_optional_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _render_matrix(results: list[dict[str, Any]], def01: dict[str, Any]) -> str:
    lines = [
        "# F1-23 Phase B - Executed Matrix",
        "",
        f"Generated: {utc_now()}",
        "",
        "Base: `main` at `e86c0b2` (includes F1-20 and F1-11).",
        "Environment: local SQLite, demo seed, `PAYPAL_MODE=mock`, `AGENT_MODE=scripted`.",
        "Phase A evidence is preserved under `docs/evidence/F1-23/S01` ... `S12`.",
        "",
        "## S01-S12 regression",
        "",
        "| ID | Scenario | Catalog outcome | API expected | Actual | Status | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        expected = result["api_expected_status"]
        if result["api_expected_code"]:
            expected += f" / `{result['api_expected_code']}`"
        actual = result["actual_status"]
        if result["actual_code"]:
            actual += f" / `{result['actual_code']}`"
        lines.append(
            f"| {result['scenario_id']} | {result['scenario_name']} | "
            f"{result['catalog_outcome']} | {expected} | {actual} | "
            f"**{result['status']}** | `{result['evidence_dir']}` |"
        )

    platform = _read_optional_json(EVIDENCE_ROOT / "platform-summary.json")
    if platform:
        lines.extend(
            [
                "",
                "## F1-20 / F1-11 platform probes",
                "",
                "| Check | Status | Evidence |",
                "|---|---|---|",
            ]
        )
        for item in platform.get("checks", []):
            status = "PASS" if item["passed"] else "FAIL"
            lines.append(
                f"| {item['check']} | **{status}** | "
                "`docs/evidence/F1-23/phase-b/platform-summary.json` |"
            )
        lines.extend(
            [
                "",
                "The failing deployment-guide check is **DEF-02** (the guide omits "
                "`python -m app.seed.sandbox_bootstrap`).",
            ]
        )

    ui = _read_optional_json(EVIDENCE_ROOT / "ui" / "ui-summary.json")
    if ui:
        lines.extend(
            [
                "",
                "## UI smoke - `origin/feat/ui-final-integration`",
                "",
                f"UI commit: `{ui.get('ui_commit')}`",
                "",
                "| Check | Status | Evidence |",
                "|---|---|---|",
            ]
        )
        for item in ui.get("checks", []):
            status = "PASS" if item["passed"] else "FAIL"
            lines.append(
                f"| {item['check']} | **{status}** | "
                "`docs/evidence/F1-23/phase-b/ui/ui-summary.json` |"
            )
        lines.extend(
            [
                "",
                "The failing UI build check is **DEF-03** (`mockAuditCursor` is unused "
                "under TypeScript).",
            ]
        )

    can_resolve = def01["can_be_resolved_with_additional_evidence"]
    requires_change = def01["requires_application_change_if_traceability_required"]
    lines.extend(
        [
            "",
            "## DEF-01 review",
            "",
            "| Field | Result |",
            "|---|---|",
            f"| Phase B status | {def01['phase_b_status']} |",
            f"| Can additional evidence resolve it? | {can_resolve} |",
            f"| Requires application change? | {requires_change} |",
            "| Evidence | `docs/evidence/F1-23/phase-b/def-01/analysis.json` |",
            "",
            "## Blocked items",
            "",
            "| ID | Scope | Dependency | Affected validation | Status |",
            "|---|---|---|---|---|",
        ]
    )
    for item in _BLOCKED_ITEMS:
        lines.append(
            f"| {item['id']} | {item['scope']} | {item['dependency']} | "
            f"{item['affected']} | **{item['status']}** |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    phase_a = _load_phase_a()
    phase_a.EVIDENCE_ROOT = REGRESSION_ROOT
    phase_a.QA_ROOT = QA_ROOT

    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))["scenarios"]
    REGRESSION_ROOT.mkdir(parents=True, exist_ok=True)
    DEFECT_ROOT.mkdir(parents=True, exist_ok=True)

    environment = {
        "generated_at": utc_now(),
        "phase": "B",
        "base_branch": "main",
        "base_commit": _git("rev-parse", "HEAD"),
        "phase_a_branch": "qa/f1-23-phase-a",
        "phase_a_commit": _git("rev-parse", "qa/f1-23-phase-a"),
        "python": sys.version,
        "platform": sys.platform,
        "settings": {
            "APP_ENV": "local",
            "DEMO_MODE": "true",
            "PAYPAL_MODE": "mock",
            "AGENT_MODE": "scripted",
            "ALLOW_SCENARIO_ID": "true",
            "DATABASE_URL": "temporary SQLite per scenario",
        },
    }
    phase_a.dump(EVIDENCE_ROOT / "environment.json", environment)

    results: list[dict[str, Any]] = [phase_a.run_seed_validation()]
    results[0]["evidence_dir"] = "docs/evidence/F1-23/phase-b/regression/SEED"
    phase_a.dump(REGRESSION_ROOT / "SEED" / "result.json", results[0])
    for scenario in scenarios:
        scenario_id = scenario["id"].split("_", 1)[0]
        directory = REGRESSION_ROOT / scenario_id
        with tempfile.TemporaryDirectory(prefix=f"f1-23-b-{scenario_id.lower()}-") as temp_dir:
            db_path = Path(temp_dir) / "qa.db"
            client = phase_a.new_client(db_path)
            try:
                with client:
                    result = phase_a.execute_scenario(client, scenario, directory)
            except Exception as exc:  # evidence must capture any failure
                result = _failure_result(phase_a, scenario, exc)
            finally:
                from app.core.db import get_engine

                get_engine().dispose()
                phase_a.clear_caches()
        result["evidence_dir"] = f"docs/evidence/F1-23/phase-b/regression/{scenario_id}"
        phase_a.dump(directory / "result.json", result)
        results.append(result)
        print(f"{result['scenario_id']}: {result['status']}")

    def01 = _defect_01_analysis(phase_a, scenarios[9])
    summary = {
        "generated_at": utc_now(),
        "phase": "B",
        "environment": environment,
        "results": results,
        "def_01": def01,
        "blocked_items": _BLOCKED_ITEMS,
        "totals": {
            "scenarios": len(scenarios),
            "evidence_entries": len(results),
            "pass": sum(1 for result in results if result["status"] == "PASS"),
            "pass_with_observation": sum(
                1 for result in results if result["status"] == "PASS_WITH_OBSERVATION"
            ),
            "fail": sum(1 for result in results if result["status"] == "FAIL"),
            "blocked": sum(1 for result in results if result["status"] == "BLOCKED"),
        },
    }
    phase_a.dump(EVIDENCE_ROOT / "run-summary.json", summary)
    (QA_ROOT / "F1-23-phase-b-matrix.md").write_text(
        _render_matrix(results, def01), encoding="utf-8"
    )
    print(json.dumps(summary["totals"], indent=2))
    return 0 if summary["totals"]["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
