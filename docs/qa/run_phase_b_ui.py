#!/usr/bin/env python3
"""F1-23 Phase B UI smoke for the open UI branch.

This script tests ``origin/feat/ui-final-integration`` without merging it:

1. Creates a temporary detached worktree.
2. Runs ``npm ci`` and the production build.
3. Starts Vite in mock mode and renders the landing page and ``/app`` with
   headless Chrome/Edge.
4. Saves DOM, screenshots, logs and a machine-readable summary.

The build is expected to fail until the UI branch fixes its TypeScript error;
the smoke still renders the pages through Vite dev so the rest of the branch
can be assessed. No application code is modified.

Run from the repository root:

    .venv\\\\Scripts\\\\python.exe docs\\\\qa\\\\run_phase_b_ui.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = ROOT / "docs" / "evidence" / "F1-23" / "phase-b" / "ui"
UI_BRANCH = "origin/feat/ui-final-integration"
UI_URL = "http://127.0.0.1:5173"


def _npm() -> str:
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def _chrome() -> str | None:
    candidates = [
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _wait_for_server(timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(UI_URL, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _chrome_dump(chrome: str, url: str, output: Path, *, screenshot: bool = False) -> bool:
    profile = Path(tempfile.gettempdir()) / f"chrome-f1-23-{uuid.uuid4().hex}"
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--window-size=1440,1200",
        "--virtual-time-budget=10000",
        f"--user-data-dir={profile}",
    ]
    if screenshot:
        args.append(f"--screenshot={output}")
    else:
        args.append("--dump-dom")
    args.append(url)
    result = _run(args, cwd=ROOT, timeout=120)
    if not screenshot:
        output.write_text(result.stdout, encoding="utf-8")
    return output.exists() and output.stat().st_size > 0


def _extract_text(html: str) -> str:
    import re

    text = re.sub(r"(?s)<style.*?</style>", " ", html)
    text = re.sub(r"(?s)<script.*?</script>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text)


def main() -> int:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    worktree = Path(tempfile.gettempdir()) / f"recovery-ui-phase-b-{uuid.uuid4().hex}"
    checks: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "B",
        "ui_branch": UI_BRANCH,
        "ui_commit": None,
        "worktree": str(worktree),
        "checks": checks,
    }
    server: subprocess.Popen[str] | None = None
    try:
        add = _run(["git", "worktree", "add", "--detach", str(worktree), UI_BRANCH], cwd=ROOT)
        if add.returncode != 0:
            summary["status"] = "BLOCKED"
            summary["error"] = add.stderr.strip()
            (EVIDENCE_ROOT / "ui-summary.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            return 1
        summary["ui_commit"] = _run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()

        ui_dir = worktree / "ui"
        npm = _npm()
        env = os.environ.copy()
        env.update({"NPM_CONFIG_FUND": "false", "NPM_CONFIG_AUDIT": "false"})
        ci = _run([npm, "ci", "--no-audit", "--no-fund"], cwd=ui_dir, env=env)
        (EVIDENCE_ROOT / "npm-ci.log").write_text(ci.stdout + ci.stderr, encoding="utf-8")
        checks.append(
            {
                "check": "npm ci succeeds",
                "passed": ci.returncode == 0,
                "expected": "exit 0",
                "actual": f"exit {ci.returncode}",
            }
        )

        build = _run([npm, "run", "build"], cwd=ui_dir, env=env)
        build_output = build.stdout + build.stderr
        (EVIDENCE_ROOT / "npm-build.log").write_text(build_output, encoding="utf-8")
        checks.append(
            {
                "check": "production build succeeds",
                "passed": build.returncode == 0,
                "expected": "exit 0",
                "actual": f"exit {build.returncode}",
                "note": (
                    "TypeScript reports src/api/client.ts(85,5): "
                    "'mockAuditCursor' is declared but its value is never read."
                    if "mockAuditCursor" in build_output
                    else None
                ),
            }
        )

        chrome = _chrome()
        if chrome is None:
            checks.append(
                {
                    "check": "headless browser smoke",
                    "passed": False,
                    "expected": "Chrome or Edge available",
                    "actual": "not found",
                }
            )
        else:
            dev_env = env.copy()
            dev_env["VITE_USE_MOCKS"] = "true"
            vite_log = (EVIDENCE_ROOT / "vite-dev.log").open("w", encoding="utf-8")
            server = subprocess.Popen(
                [
                    shutil.which("node") or "node",
                    "node_modules/vite/bin/vite.js",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                    "--strictPort",
                ],
                cwd=ui_dir,
                env=dev_env,
                stdout=vite_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            ready = _wait_for_server()
            checks.append(
                {
                    "check": "Vite dev server starts",
                    "passed": ready,
                    "expected": "HTTP 200 at http://127.0.0.1:5173",
                    "actual": "ready" if ready else "timeout",
                }
            )
            if ready:
                landing_dom = EVIDENCE_ROOT / "local-dev-landing-dom.html"
                app_dom = EVIDENCE_ROOT / "local-dev-app-dom.html"
                landing_png = EVIDENCE_ROOT / "local-dev-landing.png"
                app_png = EVIDENCE_ROOT / "local-dev-app.png"
                landing_ok = _chrome_dump(chrome, f"{UI_URL}/", landing_dom)
                app_ok = _chrome_dump(chrome, f"{UI_URL}/app", app_dom)
                landing_shot = _chrome_dump(chrome, f"{UI_URL}/", landing_png, screenshot=True)
                app_shot = _chrome_dump(chrome, f"{UI_URL}/app", app_png, screenshot=True)
                landing_text = _extract_text(
                    landing_dom.read_text(encoding="utf-8") if landing_ok else ""
                )
                app_text = _extract_text(app_dom.read_text(encoding="utf-8") if app_ok else "")
                checks.extend(
                    [
                        {
                            "check": "landing page renders",
                            "passed": landing_ok
                            and "Turn overdue invoices into active deals" in landing_text,
                            "expected": "hero copy present",
                            "actual": "present" if landing_ok else "missing DOM",
                        },
                        {
                            "check": "dashboard renders invoices",
                            "passed": app_ok and "Overview" in app_text and "INV-001" in app_text,
                            "expected": "Overview and INV-001 present",
                            "actual": "present" if app_ok else "missing DOM",
                        },
                        {
                            "check": "screenshots captured",
                            "passed": landing_shot and app_shot,
                            "expected": "landing and dashboard PNGs",
                            "actual": f"landing={landing_shot}, app={app_shot}",
                        },
                    ]
                )
            if server is not None:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                server = None
            vite_log.close()

        summary["checks"] = checks
        summary["status"] = "PASS" if all(item["passed"] for item in checks) else "FAIL"
        (EVIDENCE_ROOT / "ui-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        for item in checks:
            print(f"{'PASS' if item['passed'] else 'FAIL'}: {item['check']}")
        print(f"OVERALL: {summary['status']}")
        return 0 if summary["status"] == "PASS" else 1
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        _run(["git", "worktree", "remove", "--force", str(worktree)], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
