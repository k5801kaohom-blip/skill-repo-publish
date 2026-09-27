# CI/CD Design

Read this when adapting the workflows, when a CI job fails for a reason that is not obvious,
or when deciding what belongs in CI versus a release.

## What the pipeline has to prove

A skill repository makes one promise: **clone this, and you get a working skill.** Every job
below exists to test some part of that promise that has actually been observed to break.

| Job | Proves | The failure it catches |
| --- | --- | --- |
| `repository integrity` | the pushed tree passes the seven-stage verifier | commit drift, content drift, payload leakage |
| `skill contract` | SKILL.md names files that exist | a documented file never committed |
| `contract` → negative control | the checker can reject a broken skill | a checker that always passes |
| `skill payload check` | install, package, and unpack all work from a clean checkout | a scaffold that does not install |
| `summary` | every report is aggregated and any job failure fails the run | a silently green pipeline |

## Why negative control is a CI job, not a one-off

A contract checker that always returns success is worse than no checker: it manufactures
confidence while detecting nothing. The contract stage is only evidence if the checker has
been shown to reject a broken skill.

`ci_negative_control.py` copies the skill, breaks exactly one thing per copy, and asserts the
checker rejects each one:

```
[PASS] baseline_accepts_valid          exit=0 CONTRACT_OK
[PASS] rejects_documented_but_missing  exit=1 CONTRACT_VIOLATED
[PASS] rejects_not_executable          exit=1 CONTRACT_VIOLATED
[PASS] rejects_does_not_compile        exit=1 CONTRACT_VIOLATED
[PASS] baseline_unchanged_after        exit=0 CONTRACT_OK
```

The first and last stages matter as much as the middle three. A checker that rejects
*everything* is as useless as one that accepts everything, and the final stage catches a
mutator that edited the original skill instead of the copy — a bug that would otherwise
poison the working tree.

The mutators deliberately use copies. Breaking the real skill to test the checker, then
restoring it, is a reliable way to eventually commit the broken version.

## Why a release re-verifies instead of trusting CI

`release.yml` checks out the tag and runs the full verification on that tree, rather than
attaching an archive because CI was green on some commit.

A tag is not evidence. It can be placed on a commit that never ran CI, on a commit whose
checks passed days earlier with different inputs, or pushed directly from a machine that
never ran the checks at all. The archive is attached only after the **tagged tree** passes,
and the release notes carry the verification report so the claim is inspectable after the
fact rather than taken on trust.

## Why pull requests run `--offline`

On a `pull_request` event, the checked-out `HEAD` is a merge commit, not `origin/main`. Any
stage asserting `HEAD == origin/main` reports a false failure on every PR, and a pipeline that
cries wolf on every PR gets ignored.

So `repository integrity` branches on the event:

```yaml
if [ "${{ github.event_name }}" = "push" ]; then
  ./verify_skill_repo.sh --json verify-report.json
else
  ./verify_skill_repo.sh --offline --json verify-report.json
fi
```

Sync stages run where they are meaningful — on push. Integrity stages run everywhere.

## Why the summary job uses `if: always()`

A summary that is skipped whenever a job fails is skipped exactly when it is needed. The
summary job depends on all three verification jobs but runs `always()`, downloads whatever
reports were produced, and then fails the run itself if any dependency did not succeed.

Its `Verdict` step is what makes the run red. Without it, a failed dependency would leave the
workflow failed but the summary job green, and a reader skimming job badges would see a pass.

## Reports that were never written

`ci_summary.py` reports a missing report as missing, not as success, and `--require` makes
that fatal. A stage whose report never got written did not pass; treating an absent file as
green is how a pipeline reports health it never measured.

The same reasoning drives the separate treatment of skipped stages:

> A skipped stage is not a passed stage — it is an unmeasured one.

## Path detection over hard-coded names

Every workflow locates the payload rather than assuming its name:

```bash
SKILL_MD="$(find . -maxdepth 2 -name SKILL.md -not -path './.git/*' | head -1)"
```

Helper scripts are found with a fallback list — the payload's own copy first, then repository
tooling — so a workflow keeps working when the skill is renamed or when the helper moves
between those two locations. A workflow that hard-codes a skill name is one rename away from
failing for a reason nobody will connect to the rename.

## YAML pitfalls

**Heredocs inside `run: |` must stay indented.** A heredoc whose body starts at column 0 ends
the block scalar early. The parser then reports an error many lines below the real cause:

```
yaml.scanner.ScannerError: while scanning a simple key
  in ".github/workflows/ci.yml", line 81, column 1
```

Prefer a real file over an inline heredoc. A helper committed under `scripts/` can be tested
locally; an inline heredoc cannot, and its first execution is in CI.

**Validate the YAML before pushing.** `git push` accepts a malformed workflow; the failure
appears as a run that fails in zero seconds.

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

## Choosing between CI and release

| Belongs in CI | Belongs in release |
| --- | --- |
| every push and PR | tagged commits only |
| fast, no publishing | archive build and publish |
| reports as artifacts | reports in the release notes |
| fail the run | fail before attaching the archive |

Do not put publishing in CI. A pipeline that publishes on every green push cannot answer
"what exactly did we ship" — the answer changes with every commit.

## Adopting this in an existing repository

Adding `ci.yml` to a repository that already has a `verify.yml` produces two workflows
triggering on the same events, and two runs per push. `ci.yml` supersedes `verify.yml` — it
contains the same integrity and payload stages plus contract checking and a summary. Remove
the old file when adopting this one.
