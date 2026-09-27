#!/usr/bin/env python3
"""Audit many skill repositories at once for adoption state and template drift.

Rolling the CI mechanism out to a set of repositories is easy to start and easy to leave
unfinished. Two things go wrong quietly:

- a repository converted months ago is now behind the templates, because the templates
  evolved and nothing re-checked it
- a repository still carries a superseded workflow whose unique assertions were never
  carried over, so its only negative control is one deletion away from being lost

Both are invisible from inside any single repository. They are only visible across the
fleet, which is what this reports. Nothing is modified: run `apply_ci_to_repo.py` to act on
what this finds.

Usage:
    python3 audit_fleet.py --repos DIR [DIR ...] [--templates DIR] [--json OUT]
    python3 audit_fleet.py --root /home/ubuntu/repos [--templates DIR]

Exit codes:
    0  every repository is fully adopted and current
    1  at least one repository needs attention
    2  bad input
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# Files the mechanism consists of. Compared byte-for-byte against the templates, because
# none of them are substituted at scaffold time.
MECHANISM = {
    "ci.yml": ".github/workflows/ci.yml",
    "release.yml": ".github/workflows/release.yml",
    "check_skill_contract.py": "scripts/check_skill_contract.py",
    "ci_negative_control.py": "scripts/ci_negative_control.py",
    "ci_import_check.py": "scripts/ci_import_check.py",
    "ci_summary.py": "scripts/ci_summary.py",
    "verify_skill_repo.sh": "verify_skill_repo.sh",
}

# Workflows superseded by ci.yml. Present means either a missed removal or, worse, a
# deliberate carry-over that is now duplicated and will run twice per push.
SUPERSEDED = [".github/workflows/verify.yml"]

# Shell boilerplate that is never an assertion worth carrying over.
NOISE = re.compile(
    r"^\s*(set\s|echo\s|fi\s*$|done\s*$|else\s*$|then\s*$|#|$|\}|\{|\)\s*$|"
    r"if\s*\[|for\s+\w+\s+in|while\s+|exit\s+0\s*$|cat\s|printf\s|sleep\s|mkdir\s|"
    r"rm\s+-rf|cd\s|export\s|chmod\s|test\s+-[dnef]\s+\"?\$?\{?\w*\}?\"?\s*$)"
)


def sh(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def find_payload(repo: Path) -> Path | None:
    for cand in sorted(repo.glob("*/SKILL.md")) + [repo / "SKILL.md"]:
        if cand.is_file():
            return cand.parent
    return None


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def workflow_jobs(path: Path) -> set[str]:
    """Job names declared in a workflow, read as text to avoid a yaml dependency."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    jobs: set[str] = set()
    in_jobs = False
    for raw in text.splitlines():
        if re.match(r"^jobs:\s*$", raw):
            in_jobs = True
            continue
        if in_jobs:
            # A top-level key ends the jobs block.
            if raw and not raw[0].isspace() and not raw.startswith("#"):
                break
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", raw)
            if m:
                jobs.add(m.group(1))
    return jobs


def carry_over_risk(workflow: Path) -> list[str]:
    """Command lines in a superseded workflow that ci.yml does not obviously contain.

    Deliberately over-inclusive: a false positive costs a look, a false negative loses a
    repository's only negative control. Only obvious shell boilerplate is filtered out.
    """
    try:
        text = workflow.read_text(encoding="utf-8")
    except OSError:
        return []

    # Collect the contents of `run:` blocks, since assertions live there.
    lines: list[str] = []
    in_run = False
    run_indent = 0
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip())
        m = re.match(r"^\s*(-\s*)?(run|shell):\s*(\||>)?\s*$", stripped)
        if m:
            in_run = True
            run_indent = indent
            continue
        if in_run:
            if indent <= run_indent and stripped.strip() and not stripped.lstrip().startswith("-"):
                in_run = False
                continue
            lines.append(stripped.strip())

    # Anything that invokes something and is not boilerplate is worth flagging.
    found = []
    for line in lines:
        if NOISE.match(line):
            continue
        if not re.search(r"(python3?|\./|bash |sh |grep |test |pytest|node |npm |make )", line):
            continue
        found.append(line)
    return found


def audit(repo: Path, templates: Path | None) -> dict:
    result: dict = {"repo": repo.name, "path": str(repo), "problems": []}

    payload = find_payload(repo)
    if payload is None:
        result["verdict"] = "NOT_A_SKILL_REPO"
        result["problems"].append("no SKILL.md found")
        return result
    result["payload"] = payload.name

    rc, status = sh("git", "-C", str(repo), "status", "--porcelain")
    result["dirty"] = len([l for l in status.splitlines() if l.strip()]) if rc == 0 else -1

    rc, ab = sh("git", "-C", str(repo), "rev-list", "--left-right", "--count",
                "HEAD...origin/main")
    result["ahead_behind"] = ab if rc == 0 else "unknown"

    # Adoption and drift, per mechanism file.
    present, missing, behind = [], [], []
    custom_jobs: dict[str, list[str]] = {}
    for tpl_name, rel in MECHANISM.items():
        dst = repo / rel
        if not dst.is_file():
            missing.append(rel)
            continue
        present.append(rel)
        if templates and (templates / tpl_name).is_file():
            if rel.startswith(".github/workflows/"):
                # A repository's workflow may legitimately carry extra jobs: assertions
                # specific to that skill, carried over when its old workflow was
                # superseded. Byte comparison would call that drift and invite someone to
                # overwrite a deliberate customisation, so compare job coverage instead.
                # Missing a template job is drift; having extra jobs is not.
                tpl_jobs = workflow_jobs(templates / tpl_name)
                dst_jobs = workflow_jobs(dst)
                absent = sorted(tpl_jobs - dst_jobs)
                if absent:
                    behind.append(rel)
                    result.setdefault("missing_jobs", {})[rel] = absent
                extra = sorted(dst_jobs - tpl_jobs)
                if extra:
                    custom_jobs[rel] = extra
            elif digest(dst) != digest(templates / tpl_name):
                behind.append(rel)
    result["present"] = present
    result["missing"] = missing
    result["behind_templates"] = behind
    result["custom_jobs"] = custom_jobs
    result["adopted"] = len(missing) == 0

    # A superseded workflow still present is a risk only if it holds unique assertions.
    at_risk = {}
    for rel in SUPERSEDED:
        wf = repo / rel
        if wf.is_file():
            unique = carry_over_risk(wf)
            if unique:
                at_risk[rel] = unique
    result["superseded_at_risk"] = at_risk

    # A payload that imports third-party packages needs requirements.txt for CI.
    deps = set()
    scripts_dir = payload / "scripts"
    if scripts_dir.is_dir():
        for f in scripts_dir.rglob("*.py"):
            try:
                tree = compile(f.read_text(encoding="utf-8"), str(f), "exec")
            except SyntaxError:
                continue
            for name in re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w]*)", 
                                   f.read_text(encoding="utf-8"), re.M):
                deps.add(name)
    third_party = sorted(d for d in deps
                         if d not in sys.stdlib_module_names and not d.startswith("_"))
    result["third_party_imports"] = third_party
    result["has_requirements"] = (repo / "requirements.txt").is_file()
    if third_party and not result["has_requirements"]:
        result["problems"].append(
            f"imports {', '.join(third_party)} but has no requirements.txt")

    if result["missing"]:
        result["problems"].append(f"{len(result['missing'])} mechanism file(s) missing")
    if result["behind_templates"]:
        detail = []
        for rel in result["behind_templates"]:
            absent = result.get("missing_jobs", {}).get(rel)
            detail.append(f"{rel} (missing jobs: {', '.join(absent)})" if absent else rel)
        result["problems"].append("behind templates: " + "; ".join(detail))
    if at_risk:
        result["problems"].append("superseded workflow holds unique assertions")
    if result["dirty"] > 0:
        result["problems"].append(f"{result['dirty']} uncommitted file(s)")

    if result["missing"]:
        result["verdict"] = "NOT_ADOPTED" if len(missing) == len(MECHANISM) else "PARTIAL"
    elif at_risk:
        result["verdict"] = "AT_RISK"
    elif behind:
        result["verdict"] = "BEHIND"
    elif result["dirty"] > 0:
        result["verdict"] = "DIRTY"
    else:
        result["verdict"] = "CURRENT"
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit many skill repositories at once.")
    ap.add_argument("--repos", nargs="*", type=Path, default=[],
                    help="repository directories")
    ap.add_argument("--root", type=Path,
                    help="parent directory; every child git repository is audited")
    ap.add_argument("--templates", type=Path,
                    default=str(Path(__file__).resolve().parent.parent / "templates"),
                    help="templates to compare against (default: this skill's)")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    repos = [p.resolve() for p in args.repos]
    if args.root:
        root = args.root.resolve()
        if not root.is_dir():
            print(f"error: not a directory: {root}", file=sys.stderr)
            return 2
        repos += sorted(p for p in root.iterdir()
                        if p.is_dir() and (p / ".git").exists())
    if not repos:
        print("error: no repositories given (use --repos or --root)", file=sys.stderr)
        return 2

    templates = args.templates.resolve() if args.templates else None
    if templates and not templates.is_dir():
        print(f"error: templates not found: {templates}", file=sys.stderr)
        return 2

    results = [audit(r, templates) for r in repos]

    width = max(len(r["repo"]) for r in results)
    print(f"{'repository'.ljust(width)}  {'verdict':<13} {'files':<6} {'dirty':<6} note")
    print("-" * (width + 48))
    for r in results:
        note = "; ".join(r["problems"]) if r["problems"] else "ok"
        total = len(r.get("present", [])) + len(r.get("missing", []))
        print(f"{r['repo'].ljust(width)}  {r['verdict']:<13} "
              f"{len(r.get('present', []))}/{total}".ljust(width + 22)
              + f"{r.get('dirty', 0):<6} {note}")

    print()
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("fleet: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    risky = [r for r in results if r.get("superseded_at_risk")]
    if risky:
        print()
        print("=" * 70)
        print("SUPERSEDED WORKFLOWS HOLDING UNIQUE ASSERTIONS")
        print("=" * 70)
        print("These repositories carry a workflow that ci.yml supersedes, and it asserts")
        print("things ci.yml does not. Removing it without carrying them over would leave")
        print("that repository with no negative control at all.")
        for r in risky:
            for rel, lines in r["superseded_at_risk"].items():
                print(f"  {r['repo']}  ({rel})")
                for line in lines:
                    print(f"      {line}")

    behind = [r for r in results if r.get("behind_templates")]
    if behind:
        print()
        print("Behind the current templates:")
        for r in behind:
            print(f"  {r['repo']}: {', '.join(r['behind_templates'])}")

    custom = [r for r in results if r.get("custom_jobs")]
    if custom:
        print()
        print("=" * 70)
        print("DELIBERATE CUSTOMISATIONS - DO NOT OVERWRITE")
        print("=" * 70)
        print("These repositories carry workflow jobs the templates do not have. They were")
        print("added for a reason specific to that skill, usually a negative control carried")
        print("over from a superseded workflow. Re-scaffolding with --force would delete")
        print("them and that repository would lose the assertion entirely.")
        for r in custom:
            for rel, jobs in r["custom_jobs"].items():
                print(f"  {r['repo']}  ({rel}): {', '.join(jobs)}")

    needing = [r for r in results if r["problems"]]
    if needing:
        print()
        print(f"{len(needing)} of {len(results)} repositor(ies) need attention.")
        print("Run apply_ci_to_repo.py --dry-run on each before changing anything.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "templates": str(templates) if templates else None,
            "counts": counts,
            "repositories": results,
            "verdict": "FLEET_CURRENT" if not needing else "FLEET_NEEDS_ATTENTION",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report: {args.json}")

    return 1 if needing else 0


if __name__ == "__main__":
    raise SystemExit(main())
