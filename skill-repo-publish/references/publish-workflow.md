# Publish Workflow

Read this for the exact sequence, the commands, and the verification that must pass before a
skill repository is considered delivered.

## Sequence

```
1. Scaffold the repository around the skill
2. Verify the scaffold locally, before it is a git repository
3. Initialise git and push
4. Verify against the remote
5. Confirm CI actually ran and passed
```

Step 2 is the one that gets skipped, and skipping it is why publishing takes several rounds:
without a local run, the first feedback arrives from a CI log or from the user.

## 1. Scaffold

```bash
python3 /home/ubuntu/skills/skill-repo-publish/scripts/scaffold_skill_repo.py \
  --skill /home/ubuntu/skills/<skill-name> \
  --repo-dir /home/ubuntu/repos/<repo-name> \
  --owner <github-owner> \
  --requirements "Python 3.10 or newer; standard library only."
```

The script refuses to overwrite existing files. On a fresh repository that is never an issue;
on a re-scaffold it protects edits already made. Use `--force` only when you intend to
discard them.

## 2. Verify the scaffold locally

```bash
cd /home/ubuntu/repos/<repo-name>
bash -n install.sh && bash -n package.sh && bash -n verify_skill_repo.sh
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/verify.yml')); print('yaml ok')"
python3 scripts/ci_summary.py --help >/dev/null 2>&1 || true

# Prove the installer works before it is published.
SKILLS_DIR=/tmp/scaffold_test ./install.sh
```

Then run the packaging path, because a zip that lost the payload still reports success:

```bash
./package.sh
unzip -l dist/*.zip | grep -q SKILL.md && echo "archive has payload"
```

Verify the YAML explicitly. A malformed workflow is not reported by `git push` — it appears
as a CI run that fails in zero seconds with a parser error, which is a slow way to learn about
an indentation mistake.

## 3. Initialise and push

```bash
cd /home/ubuntu/repos/<repo-name>
rm -rf dist
git init -q -b main
git config user.name  "<github-user>"
git config user.email "<email>"
git add -A
git commit -q -m "feat: publish <skill-name> as an installable skill repository"

gh repo create <repo-name> --public \
  --description "<one line from SKILL.md>" \
  --source . --remote origin --push
```

`--public` for the team-sharing case; `--private` otherwise. Create as private first if there
is any doubt, since switching later is a one-line `gh repo edit --visibility public`.

Add topics so the repository is discoverable alongside the others:

```bash
gh repo edit <owner>/<repo-name> \
  --add-topic manus-skill --add-topic skill
```

## 4. Verify against the remote

```bash
./verify_skill_repo.sh --json verify-report.json
```

Expect `VERDICT: repository fully in sync and reproducible` and exit code `0`. A
`working tree clean` failure at this point almost always means a file was written after the
commit — for example the JSON report the script itself just produced, which is why
`*-report.json` belongs in `.gitignore`.

## 5. Confirm CI

```bash
gh run list  --repo <owner>/<repo-name> --limit 3
RID=$(gh run list --repo <owner>/<repo-name> --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RID" --repo <owner>/<repo-name>
```

Do not report a repository as published until CI shows success. A workflow that has never run
is not evidence, and a workflow that failed in zero seconds never executed a check at all.

## Independent clone test

The strongest single check, and the one worth running manually once:

```bash
rm -rf /tmp/anon_test && mkdir -p /tmp/anon_test && cd /tmp/anon_test
git clone https://github.com/<owner>/<repo-name>.git
cd <repo-name>
SKILLS_DIR=/tmp/anon_test/skills ./install.sh
python3 /tmp/anon_test/skills/<skill-name>/scripts/check_skill_contract.py \
  --skill /tmp/anon_test/skills/<skill-name>
```

Doing this from a scratch directory proves there is no dependency on the environment the
repository was authored in.

## Failure modes and what they mean

| Symptom | Cause | Fix |
| --- | --- | --- |
| CI fails in 0s | malformed workflow YAML | parse the YAML locally; check heredoc indentation inside `run:` |
| `working tree clean` fails after a successful push | a report or artifact written into the repo | add it to `.gitignore` |
| `content equality` fails for one file | committed locally but pushed from elsewhere, or vice versa | `git status`, then commit and push the difference |
| `install from clone` reports 0 files | `install.sh` looks for a directory that is not in the clone | check the payload path and that it was committed |
| `payload clean` fails | repository file inside the skill directory | move it to the repository root |
| `contract check` fails only after cloning | a documented file is untracked locally | `git add` it; this is the failure CI exists to catch |

## The empty-checkout trap

`git clone` **exits 0 while checking out nothing** when the remote's `HEAD` points at a branch
that does not exist. This happens when a bare repository still defaults to `master` while the
code lives on `main`. The only signal is a warning on stderr that a quiet clone discards:

```
warning: remote HEAD refers to nonexistent ref, unable to checkout
```

The working tree is then empty, and every downstream stage fails on a missing file and reports
a misleading cause — "install.sh parse error" rather than "the checkout was empty".
`verify_skill_repo.sh` therefore asserts the checkout itself:

```
[FAIL] clone checked out a working tree   empty checkout - remote HEAD may point at a missing branch
          remote HEAD:
          branches   : refs/heads/main
```

Diagnose it with:

```bash
git ls-remote --symref <url> HEAD     # what HEAD points at
git ls-remote --heads <url>           # which branches actually exist
```

Fix it on the remote rather than in the clone:

```bash
git symbolic-ref HEAD refs/heads/main     # on the bare repository
# or, for GitHub, set the default branch in the repository settings
```

This trap is easy to hit when testing a publish flow against a **local bare repository**
instead of GitHub: `git init --bare` defaults to `master`, while `git init -b main` in the
working repository pushes to `main`. Point the bare remote's HEAD at `main` before running the
verification, or the test will fail for a reason that has nothing to do with the repository
being tested.

## Re-scaffolding an existing repository

Run the scaffold with `--force` only for the files actually intended to change, then inspect
the diff before committing. Prefer copying a single template over re-scaffolding the whole
repository: the templates evolve, and a wholesale refresh will silently overwrite
repository-specific adjustments that were made deliberately.
