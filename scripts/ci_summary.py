#!/usr/bin/env python3
"""Render a verify_skill_repo.sh JSON report as a GitHub Actions job summary table."""

import json
import sys
from pathlib import Path

ICON = {"PASS": "pass", "FAIL": "**FAIL**", "SKIP": "skip"}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: ci_summary.py <verify-report.json>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"_report not found: {path}_")
        return 0

    r = json.loads(path.read_text(encoding="utf-8"))
    print(f"**Verdict: {r.get('verdict')}** — "
          f"{r.get('passed', 0)} passed, {r.get('failed', 0)} failed, "
          f"{r.get('skipped', 0)} skipped")
    print()
    print("| Status | Check | Detail |")
    print("| --- | --- | --- |")
    for c in r.get("checks", []):
        status = c.get("status", "")
        print(f"| {ICON.get(status, status)} | {c.get('check', '')} | {c.get('detail', '')} |")

    if r.get("failed"):
        print()
        print("Failing checks mean the repository is not safe to clone-and-use. "
              "Fix the cause before merging.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())