#!/usr/bin/env python3
"""Scaffold a distributable GitHub repository around an existing skill.

A skill by itself is a directory that only works on the machine that made it. Making it
consumable means adding the surrounding furniture: an installer, a packager, a verifier, a
LICENSE, a README, and CI. That furniture is the same every time, and hand-writing it per
repository is how it silently drifts and how repositories end up half-finished.

This copies the furniture from templates/, fills in the blanks, and refuses to overwrite
anything that already exists unless asked.

Usage:
    python scaffold_skill_repo.py --skill DIR --repo-dir DIR [--owner OWNER] [options]

Exit codes:
    0  scaffolded
    1  refused to overwrite existing files without --force
    2  bad input
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# template file -> destination path relative to the repository root
PLAN = {
    "install.sh": "install.sh",
    "package.sh": "package.sh",
    "gitignore": ".gitignore",
    "README.md": "README.md",
    "verify_skill_repo.sh": "verify_skill_repo.sh",
    "verify.yml": ".github/workflows/verify.yml",
    "check_skill_contract.py": "scripts/check_skill_contract.py",
    "ci_summary.py": "scripts/ci_summary.py",
}

EXECUTABLE = {"install.sh", "package.sh", "verify_skill_repo.sh"}


def read_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = {}
    for line in parts[1].splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm


def first_sentence(text: str, limit: int = 260) -> str:
    text = text.strip().strip('"').strip("'")
    m = re.search(r"\.\s", text)
    if m and m.start() < limit:
        return text[: m.start() + 1]
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold a repository around a skill.")
    ap.add_argument("--skill", type=Path, required=True, help="skill directory containing SKILL.md")
    ap.add_argument("--repo-dir", type=Path, required=True, help="repository root to create")
    ap.add_argument("--owner", default="OWNER", help="GitHub owner, for the clone URL")
    ap.add_argument("--repo-name", default=None, help="repository name (default: skill directory name)")
    ap.add_argument("--requirements", default="Python 3.10 or newer; standard library only.",
                    help="text for the README Requirements section")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--json", type=Path, help="write a machine-readable summary")
    args = ap.parse_args()

    skill = args.skill.resolve()
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        print(f"error: no SKILL.md in {skill}", file=sys.stderr)
        return 2

    repo_dir = args.repo_dir.resolve()
    skill_name = skill.name
    repo_name = args.repo_name or skill_name

    if not TEMPLATE_DIR.is_dir():
        print(f"error: templates not found at {TEMPLATE_DIR}", file=sys.stderr)
        return 2

    fm = read_frontmatter(skill_md)
    description = first_sentence(fm.get("description", "A Manus skill."))

    subs = {
        "{{SKILL_NAME}}": skill_name,
        "{{REPO_NAME}}": repo_name,
        "{{OWNER}}": args.owner,
        "{{DESCRIPTION}}": description,
        "{{REQUIREMENTS}}": args.requirements,
    }

    # Refuse to clobber before writing anything, so a rejected run leaves no partial state.
    targets = {src: repo_dir / dst for src, dst in PLAN.items()}
    existing = [dst for dst in targets.values() if dst.exists() and dst.resolve() != skill_md]
    if existing and not args.force:
        print("error: refusing to overwrite existing files (use --force):", file=sys.stderr)
        for p in existing:
            print(f"  {p}", file=sys.stderr)
        return 1

    repo_dir.mkdir(parents=True, exist_ok=True)

    # The skill payload lives in a subdirectory so repository-level files never land in
    # ~/skills/<name>/ when a consumer installs from the clone.
    payload_dst = repo_dir / skill_name
    if payload_dst.resolve() != skill:
        if payload_dst.exists():
            shutil.rmtree(payload_dst)
        shutil.copytree(skill, payload_dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".git"))

    written = []
    for src, dst in targets.items():
        tpl = TEMPLATE_DIR / src
        if not tpl.is_file():
            print(f"warning: template missing, skipped: {src}", file=sys.stderr)
            continue
        body = tpl.read_text(encoding="utf-8")
        for k, v in subs.items():
            body = body.replace(k, v)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(body, encoding="utf-8")
        if src in EXECUTABLE:
            dst.chmod(dst.stat().st_mode | 0o755)
        written.append(str(dst.relative_to(repo_dir)))

    # A LICENSE is expected by the README, so ship one rather than leaving a dead link.
    lic = repo_dir / "LICENSE"
    if not lic.exists():
        lic.write_text(
            "MIT License\n\n"
            "Copyright (c) 2026 KAOHOM\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            'of this software and associated documentation files (the "Software"), to deal\n'
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software, and to permit persons to whom the Software is\n"
            "furnished to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included in all\n"
            "copies or substantial portions of the Software.\n\n"
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
            "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
            "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
            "SOFTWARE.\n",
            encoding="utf-8",
        )
        written.append("LICENSE")

    print(f"repo   : {repo_dir}")
    print(f"skill  : {skill_name}  (payload copied to {skill_name}/)")
    print(f"wrote  : {len(written)} files")
    for f in sorted(written):
        print(f"  {f}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "repo_dir": str(repo_dir),
            "skill_name": skill_name,
            "repo_name": repo_name,
            "written": sorted(written),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
