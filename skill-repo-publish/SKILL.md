---
name: skill-repo-publish
description: Turn a local skill directory into a distributable GitHub repository that others can clone, install, and verify — the installer, packager, verifier, LICENSE, README, and CI workflow around a skill. Use when a skill must be shared with a team, published for git clone installation, packaged as a downloadable archive, given CI that proves a fresh clone works, or when existing skill repositories need the surrounding furniture added or standardised so they stop drifting apart.
---

# Skill Repo Publish

A skill directory only works on the machine that made it. Making it consumable means adding
furniture around it: an installer, a packager, a verifier, a license, a README, and CI. That
furniture is the same every time, and hand-writing it per repository is how repositories drift
apart and ship half-finished.

This skill scaffolds that furniture, publishes the repository, and proves a fresh clone works
before anyone else has to find out.

## Workflow

1. **Scaffold** the repository around the skill.
2. **Verify the scaffold locally** — before it is a git repository.
3. **Initialise git and push.**
4. **Verify against the remote.**
5. **Confirm CI actually ran and passed.**

```bash
# 1
python3 scripts/scaffold_skill_repo.py \
  --skill /home/ubuntu/skills/<skill-name> \
  --repo-dir /home/ubuntu/repos/<repo-name> \
  --owner <github-owner>

# 2 — always before pushing
cd /home/ubuntu/repos/<repo-name>
bash -n install.sh && bash -n package.sh && bash -n verify_skill_repo.sh
SKILLS_DIR=/tmp/scaffold_test ./install.sh

# 4 — after pushing
./verify_skill_repo.sh --json verify-report.json

# 5
gh run list --repo <owner>/<repo-name> --limit 3
```

`references/publish-workflow.md` has the full command sequence, the independent clone test, and
a failure-mode table. Read it when running a publish, or when a verification stage fails and
the cause is not obvious.

## The one failure CI exists to catch

**SKILL.md documenting a file that was never committed.**

The skill looks complete. The contract check passes on the author's machine, because the file
is still there. Everyone who clones gets a skill that documents a pipeline it does not
contain. Only a clean clone detects this, which is why the CI workflow's clone stage is not
optional.

## Two rules that determine whether the repository is usable

**The skill payload goes in a subdirectory.** `install.sh` copies `<skill-name>/` into
`~/skills/`, so repository furniture at the root never lands in the installed skill.

This matters most for `.gitignore`. Git reads a `.gitignore` from an ancestor directory, so a
skill installed with one can silently change which files a user's own repository tracks.
`verify_skill_repo.sh` stage 5 fails the build when this happens.

**Scripts must auto-detect the skill, not hard-code it.** Locate `SKILL.md` and derive the
name:

```bash
SKILL_MD="$(find "$ROOT" -maxdepth 2 -name SKILL.md -not -path '*/.git/*' | head -1)"
SKILL_NAME="$(basename "$(dirname "$SKILL_MD")")"
```

A template that needs its name edited in five places will eventually ship with a stale name in
one of them. Auto-detection is why scaffolding needs no edits afterwards.

## Verify before you publish

Run the local checks in step 2 rather than learning from a CI log. Two failures are cheap to
catch and expensive to diagnose remotely:

- **Malformed workflow YAML.** `git push` accepts it. The failure appears as a CI run that
  fails in zero seconds. Parse the YAML locally.
- **A scaffold that does not install.** Run `install.sh` with `SKILLS_DIR` pointed at a
  scratch directory and confirm it lands. `install.sh` already runs a contract check on the
  installed copy and warns when it fails.

Do not report a repository as published until CI shows success. A workflow that has never run
is not evidence, and one that failed in zero seconds never executed a check.

## Bundled Resources

- `scripts/scaffold_skill_repo.py` — scaffold the repository; refuses to overwrite existing files unless `--force`.
- `references/repo-anatomy.md` — why the layout is this shape, what belongs at the root versus the payload, and how to adapt for root-level or multi-skill repositories.
- `references/publish-workflow.md` — full publish sequence, independent clone test, and failure-mode table.
- `templates/install.sh` — installer; auto-detects the skill, verifies the install.
- `templates/package.sh` — ZIP packager; proves the archive contains SKILL.md.
- `templates/verify_skill_repo.sh` — seven-stage repository verifier with `--offline`, `--skip-clone`, `--api`, `--json`.
- `templates/verify.yml` — GitHub Actions workflow.
- `templates/ci_summary.py` — render a verify report as a job summary.
- `templates/README.md` — repository README with install, verify, and layout sections.
- `templates/gitignore` — ignores build output, install backups, and verification artifacts.

## Reporting

Report what was verified, not what was scaffolded. State the CI run status explicitly. When a
stage is skipped — `--offline`, `--skip-clone`, a repository with no CI — say so rather than
implying the check passed.