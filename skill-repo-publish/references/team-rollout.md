# Team Rollout

Read this when rolling the CI mechanism out beyond one repository, or when someone asks why
their repository should adopt it.

## Lead with the failure, not the tooling

The mechanism is easy to sell badly. "We have a CI template with negative control and contract
checking" invites the question *why*, and the answer sounds like process for its own sake.

Lead with the failure instead, because every team that ships a skill or a script has hit it:

> Someone's SKILL.md or README documented a file that was never committed. The docs looked
> complete, the author's machine still had the file, and everyone who cloned it got something
> that did not work. Nobody found out until a consumer tried to use it.

Then the mechanism is the answer to a problem they recognise, not overhead.

The second failure is worth mentioning once the first lands, because it is the non-obvious
one:

> A checker that always passes is worse than no checker, because it manufactures confidence.
> That is why negative control exists — it proves the checker can fail before you trust it.

## Roll out in four stages

Do not convert every repository at once. Each stage produces a result you can stop at.

### Stage 1 — one repository, chosen for visibility

Pick a repository that is **already public and already used by others**. The value is visible
immediately: the first time CI catches a documented-but-missing file, everyone who has ever
cloned that repository understands the point.

Avoid starting with the most complex repository. If the first conversion is hard, the
initiative dies on the first conversion.

```bash
python3 scripts/apply_ci_to_repo.py --repo /path/to/repo --templates <templates> --dry-run
```

Review the dry run. Then apply, verify locally, push, and confirm the jobs ran.

### Stage 2 — the repositories that already have CI

These have the highest risk and the highest payoff, because a superseded workflow may hold
assertions nothing else has.

**Always dry-run first.** The script lists assertions that exist only in the workflow it is
about to remove:

```
ACTION REQUIRED: assertions below exist only in the removed workflow.
ci.yml does not contain them. Carry them into ci.yml, or they are lost.
```

Carry each one into `ci.yml` as its own job, and add that job to the summary's `needs` list.
A repository whose own negative control was silently deleted is worse off than before the
rollout.

This is the stage where a rollout does damage if rushed. Budget real time for it.

### Stage 3 — the remaining repositories

Mechanical by now. Batch them, but still review each dry run: a repository may have a
superseded workflow nobody remembered, or a dirty tree that means the script refuses to run.

### Stage 4 — make it the default

Once several repositories have adopted it, new ones should start with it rather than
retrofitting later. `scaffold_skill_repo.py` already produces a repository with the full
mechanism, so this is a documentation change, not a build change.

## Per-repository checklist

Run this for every repository, in order. Nothing here is optional except where noted.

- [ ] Working tree is clean, or the changes are stashed
- [ ] `--dry-run` reviewed, and every listed change is understood
- [ ] Any `ACTION REQUIRED` assertion carried into `ci.yml` as a job
- [ ] That job added to the summary's `needs` list and its result table
- [ ] `requirements.txt` added if any shipped script imports a third-party package
- [ ] Workflow YAML parses locally (a malformed workflow fails in zero seconds)
- [ ] Contract check passes locally
- [ ] Negative control passes locally (proves the checker can fail)
- [ ] Import check passes locally
- [ ] `install.sh` and `package.sh` run successfully from a clean directory
- [ ] `verify_skill_repo.sh` reports `0 failed`
- [ ] Pushed, and **CI confirmed green on GitHub** — not merely pushed
- [ ] Every job in the run is green, including the summary

The last two are the ones people skip. A workflow file that was never executed is not
evidence.

## What to tell reviewers

Reviewers will ask three questions. Have the answers ready in the pull request description.

**"What does this catch that we do not catch today?"**
The documented-but-missing file, and a checker that silently stopped working.

**"Why a new job instead of adding to the existing one?"**
Each check fails on its own signal. An aggregate script that masks a specific failure makes
the failure harder to find, not easier.

**"Why does negative control deliberately break things?"**
Because a check that has never failed is not known to work. The mutators operate on copies,
never on the repository.

## Common objections

**"This is overhead for a small repository."**
The overhead is one workflow file and four scripts, and it runs in under thirty seconds. The
cost of the failure it catches is a consumer who cannot use the repository and does not know
why.

**"Our repository has no SKILL.md, so the contract check is meaningless."**
Then keep the integrity and payload jobs and drop the contract job. The mechanism is layered
precisely so it can be adopted partially. Do not adopt a check that cannot fail — that is the
thing negative control exists to prevent.

**"We already have CI."**
Check whether it proves the clone works. Most CI proves the code runs on the author's
machine's assumptions; the failure above survives all of it.

**"Can we skip negative control?"**
You can, but then a green contract stage means less than it appears to. If the checker breaks,
nothing notices. It costs five seconds.

## Making it stick

**Put the mechanism in the scaffolding, not in a wiki.** A document describing how to set up
CI gets read once. A template that produces it gets used every time. That is why this skill
ships `scaffold_skill_repo.py` rather than only prose.

**Record which repositories have adopted it.** A table in the team's README, with the date and
the CI run link for each. Untracked rollouts stall at about two thirds completion, and nobody
can tell which third is missing.

**Re-run the dry run periodically.** The templates evolve. A repository converted six months
ago is now behind, and the dry run is how you find out without diffing by hand.

**Treat a red CI run as the deliverable, not an inconvenience.** The first time it catches a
documented-but-missing file, post the run link. One real catch does more for adoption than any
amount of explaining.

## What not to do

**Do not add the workflow without checking it runs.** A workflow that fails on its first run
and is then ignored is worse than no workflow: it trains people to ignore red.

**Do not delete a superseded workflow before reading it.** Its assertions may be the only
negative control that repository has.

**Do not adopt the contract job in a repository whose documentation is already wrong.** Fix the
documentation first. Otherwise the first CI run is red for a pre-existing reason, and the
mechanism gets blamed for it.

**Do not roll out to every repository in one pull request.** A failure in the shared templates
then breaks everything at once, and the review is unreviewable.
