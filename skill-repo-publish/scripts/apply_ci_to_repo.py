#!/usr/bin/env python3
"""Add or update the CI/CD mechanism in an existing skill repository.

A repository that already exists has content worth keeping: its README describes its own
skill, its workflow may assert things specific to that skill, and its installer may have
been written before the templates were standardised. Overwriting wholesale destroys that.

This applies the mechanism and reports every difference it would make, so the changes can
be reviewed before anything is committed. It refuses to run on a dirty tree, because a
half-applied change on top of uncommitted work is hard to separate afterwards.

Usage:
    python3 apply_ci_to_repo.py --repo DIR --templates DIR [--dry-run] [--json OUT]

Exit codes:
    0  applied (or, with --dry-run, reportable)
    1  refused: dirty tree, or a conflict needing a decision
    2  bad input
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# template file -> destination relative to the repository root
FILES = {
    "ci.yml": ".github/workflows/ci.yml",
    "release.yml": ".github/workflows/release.yml",
    "check_skill_contract.py": "scripts/check_skill_contract.py",
    "ci_negative_control.py": "scripts/ci_negative_control.py",
    "ci_import_check.py": "scripts/ci_import_check.py",
    "ci_summary.py": "scripts/ci_summary.py",
    "verify_skill_repo.sh": "verify_skill_repo.sh",
}

# Workflows superseded by ci.yml. Left in place, they would double every run.
SUPERSEDED = [".github/workflows/verify.yml"]

# A superseded workflow may assert things ci.yml does not. Deleting it wholesale would
# silently drop those assertions, which is the failure this tool exists to avoid, so
# anything unique is reported and must be carried over deliberately.
COVERED_BY_CI = (
    "verify_skill_repo.sh", "verify_sync.sh", "check_skill_contract.py",
    "ci_summary.py", "install.sh", "package.sh", "actions/checkout",
    "actions/setup-python", "actions/upload-artifact", "actions/download-artifact",
    "GITHUB_STEP_SUMMARY", "python3 --version", "git --version",
    "github.event_name", "offline", "verify-report.json", "contract-report.json",
    "fetch-depth", "timeout-minutes", "concurrency", "permissions",
)


def unique_assertions(path: Path) -> list[str]:
    """Command-ish lines in a workflow that ci.yml does not already cover."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    found = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Only lines that look like assertions or invocations, not YAML keys or prose.
        if not (line.startswith("python3 ") or line.startswith("./")
                or "grep -q" in line or "test -f" in line or "test -n" in line):
            continue
        if any(token in line for token in COVERED_BY_CI):
            continue
        found.append(line)
    return found

EXECUTABLE = {"verify_skill_repo.sh", "check_skill_contract.py",
              "ci_negative_control.py", "ci_import_check.py", "ci_summary.py"}


def git(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def find_payload(repo: Path) -> Path | None:
    for cand in sorted(repo.glob("*/SKILL.md")) + [repo / "SKILL.md"]:
        if cand.is_file():
            return cand.parent
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply the CI mechanism to a skill repository.")
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--templates", type=Path, required=True,
                    help="the skill's templates/ directory")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="proceed despite a dirty tree")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    repo = args.repo.resolve()
    templates = args.templates.resolve()
    if not (repo / ".git").exists():
        print(f"error: not a git repository: {repo}", file=sys.stderr)
        return 2
    if not templates.is_dir():
        print(f"error: templates not found: {templates}", file=sys.stderr)
        return 2

    payload = find_payload(repo)
    if payload is None:
        print(f"error: no SKILL.md found in {repo}", file=sys.stderr)
        return 2

    rc, status = git(repo, "status", "--porcelain")
    if rc != 0:
        print("error: could not read git status", file=sys.stderr)
        return 2
    if status and not args.force:
        print("error: working tree is dirty; commit or stash first", file=sys.stderr)
        print(status, file=sys.stderr)
        return 1

    changes = {"added": [], "updated": [], "unchanged": [], "removed": []}

    for src_name, dst_rel in FILES.items():
        src = templates / src_name
        if not src.is_file():
            print(f"warning: template missing, skipped: {src_name}", file=sys.stderr)
            continue
        dst = repo / dst_rel
        new = src.read_bytes()
        if dst.is_file() and dst.read_bytes() == new:
            changes["unchanged"].append(dst_rel)
            continue
        if dst.is_file():
            changes["updated"].append(dst_rel)
        else:
            changes["added"].append(dst_rel)
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(new)
            if src_name in EXECUTABLE:
                dst.chmod(dst.stat().st_mode | 0o755)

    carry_over = {}
    for rel in SUPERSEDED:
        old = repo / rel
        if old.is_file():
            unique = unique_assertions(old)
            if unique:
                carry_over[rel] = unique
            # ci.yml contains every stage the old workflow had, plus contract checking
            # and negative control. Keeping both means two runs per push.
            changes["removed"].append(rel)
            if not args.dry_run:
                rc, _ = git(repo, "rm", "-q", "--cached", rel)
                old.unlink()

    print(f"repo    : {repo.name}")
    print(f"payload : {payload.name}/")
    print(f"mode    : {'dry run' if args.dry_run else 'applied'}")
    print()
    for kind in ("added", "updated", "removed", "unchanged"):
        items = changes[kind]
        if items:
            print(f"{kind} ({len(items)}):")
            for i in sorted(items):
                print(f"  {i}")
    print()

    if changes["removed"]:
        print("Removed workflows were superseded by ci.yml. Keeping both would run the")
        print("same checks twice on every push.")
        print()

    if carry_over:
        print("=" * 70)
        print("ACTION REQUIRED: assertions below exist only in the removed workflow.")
        print("ci.yml does not contain them. Carry them into ci.yml, or they are lost.")
        print("=" * 70)
        for rel, lines in carry_over.items():
            print(f"  from {rel}:")
            for line in lines:
                print(f"    {line}")
        print()
        print("  Add these as a job in .github/workflows/ci.yml before committing.")
        print()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "repo": repo.name,
            "payload": payload.name,
            "dry_run": args.dry_run,
            "changes": changes,
            "carry_over": carry_over,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report: {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
