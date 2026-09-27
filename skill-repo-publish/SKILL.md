---
name: skill-repo-publish
description: 觸發詞：發布技能、技能上架、分享技能、技能給團隊、GitHub 倉庫、建立技能倉庫、打包技能、技能安裝包、技能分享給同事。Turn a local skill directory into a distributable GitHub repository that others can clone, install, and verify — the installer, packager, verifier, LICENSE, README, and CI workflow around a skill. Use when a skill must be shared with a team, published for git clone installation, packaged as a downloadable archive, given CI that proves a fresh clone works, or when existing skill repositories need the surrounding furniture added or standardised so they stop drifting apart.
metadata:
  alias_zh-TW: 技能發布上架
  short_alias_zh-TW: 技能發布
  keywords_zh-TW: 技能發布、技能發布上架、發布技能、技能上架、分享技能、技能給團隊、GitHub 倉庫、建立技能倉庫、打包技能、技能安裝包、技能分享給同事
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

## Adopting the mechanism in an existing repository

A repository that already exists has content worth keeping: its README describes its own
skill, and its workflow may assert things specific to that skill. Overwriting wholesale
destroys that.

```bash
# Always dry-run first.
python3 scripts/apply_ci_to_repo.py \
  --repo /path/to/repo \
  --templates /home/ubuntu/skills/skill-repo-publish/templates \
  --dry-run
```

The script refuses to run on a dirty tree, reports every file it would add, update, or
remove, and **lists assertions that exist only in the workflow it is about to remove.** Those
must be carried into `ci.yml` deliberately — silently dropping a repository's own negative
control is exactly the failure this mechanism exists to prevent.

Before pushing, confirm on the remote that the new jobs actually ran. A workflow file that was
never executed is not evidence of anything.

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

## Keeping a fleet of repositories current

Once more than one repository uses the mechanism, two things drift apart and neither is
visible from inside a single repository: a repository converted earlier falls behind the
templates, and a repository still holds a superseded workflow whose unique assertions were
never carried over.

```bash
python3 scripts/audit_fleet.py --root /home/ubuntu/repos --templates <templates> --json fleet.json
```

Read-only. Run it before a rollout to see what is already adopted, and afterwards to catch
repositories that fell behind.

**A repository's workflow may carry extra jobs on purpose.** When a superseded workflow held
assertions `ci.yml` does not, the correct fix is to carry them over as a job, so the
repository ends up ahead of the template rather than behind it. The auditor therefore compares
**job coverage** for workflows, not bytes: a missing template job is drift, an extra job is a
customisation. Byte comparison would report the deliberate job as drift and invite someone to
overwrite it — which is how a repository loses its only negative control. Extra jobs are
printed under a DO NOT OVERWRITE heading, because re-scaffolding with `--force` would delete
them.

## Bundled Resources

- `scripts/scaffold_skill_repo.py` — scaffold the repository; refuses to overwrite existing files unless `--force`.
- `scripts/apply_ci_to_repo.py` — add or update the CI mechanism in an existing repository; dry-run first, and it names any assertion the superseded workflow had that `ci.yml` does not.
- `scripts/audit_fleet.py` — audit many repositories at once for adoption state and template drift; read-only, and it distinguishes a deliberate customisation from drift so nobody overwrites one by mistake.
- `references/repo-anatomy.md` — why the layout is this shape, what belongs at the root versus the payload, and how to adapt for root-level or multi-skill repositories.
- `references/publish-workflow.md` — full publish sequence, independent clone test, and failure-mode table.
- `references/ci-cd-design.md` — what each CI job proves, why releases re-verify instead of trusting CI, and the YAML pitfalls that make a workflow fail in zero seconds.
- `references/team-rollout.md` — staged plan for rolling the mechanism out across an organisation, including the per-repository checklist and how to migrate without losing existing assertions.
- `templates/install.sh` — installer; auto-detects the skill, verifies the install.
- `templates/package.sh` — ZIP packager; proves the archive contains SKILL.md.
- `templates/verify_skill_repo.sh` — seven-stage repository verifier with `--offline`, `--skip-clone`, `--api`, `--json`.
- `templates/ci.yml` — CI workflow: repository integrity, contract check with negative control, payload self-test, and an aggregate summary job.
- `templates/release.yml` — tag-triggered release workflow; re-verifies the tagged tree before attaching an archive.
- `templates/check_skill_contract.py` — checks that every resource SKILL.md names actually exists, compiles, and is executable. Scaffolded into the repository so each one can verify its own contract.
- `templates/ci_negative_control.py` — proves the contract checker can actually fail, by running it against deliberately broken copies.
- `templates/ci_import_check.py` — imports every shipped script for real, separating a missing dependency from a broken script.
- `templates/ci_summary.py` — render verify, contract, negative-control, and import reports as a job summary; treats a missing report as a failure rather than as a pass.
- `templates/README.md` — repository README with install, verify, and layout sections.
- `templates/gitignore` — ignores build output, install backups, and verification artifacts.

## Reporting

Report what was verified, not what was scaffolded. State the CI run status explicitly. When a
stage is skipped — `--offline`, `--skip-clone`, a repository with no CI — say so rather than
implying the check passed.
