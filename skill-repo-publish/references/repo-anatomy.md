# Repository Anatomy

Read this when you need to know why the repository is shaped this way, or when adapting the
layout for a skill that does not fit the default.

## The layout

```
repo-name/
├── skill-name/               # the skill payload — this is what gets installed
│   ├── SKILL.md
│   ├── scripts/
│   ├── references/
│   └── templates/
├── .github/workflows/verify.yml
├── scripts/ci_summary.py     # CI helpers, not skill payload
├── install.sh
├── package.sh
├── verify_skill_repo.sh
├── .gitignore
├── LICENSE
└── README.md
```

## Why the skill sits in a subdirectory

The skill payload must be separable from the repository furniture. `install.sh` copies
`skill-name/` into `~/skills/`, so anything at the repository root never lands in the
installed skill.

Without this separation, `.gitignore`, `LICENSE`, `README.md`, and CI configuration end up
inside the installed skill. The `.gitignore` in particular causes real harm: git reads a
`.gitignore` in an ancestor directory, so a skill installed with one can silently change
which files a user's own repository tracks.

This is the single most common structural mistake in skill repositories, and
`verify_skill_repo.sh` stage 5 fails the build when it happens.

## What belongs at the root vs in the payload

| At the repository root | In the skill payload |
| --- | --- |
| `install.sh`, `package.sh`, `verify_skill_repo.sh` | everything SKILL.md names |
| `.gitignore`, `LICENSE`, `README.md` | `scripts/`, `references/`, `templates/` |
| `.github/workflows/` | — |
| `scripts/ci_summary.py` | — |

The test: **would this file help a skill consumer, or only a repository consumer?** A
consumer reads `SKILL.md` and runs its scripts. A repository consumer clones, installs, and
may contribute. `README.md` serves the second audience, so it stays out of the payload.

## Why README.md is at the root but not in the skill

`skill-creator` forbids `README.md` inside a skill because a skill is documentation for an
agent, not for a person. That rule is about the payload directory.

A *repository* is a different artifact. It is what a human clones, reads, and decides whether
to trust. If a repository has no README, the human has to read a SKILL.md written for an
agent. Both files are warranted, and the separation above is what makes that possible.

## The auto-detection convention

`install.sh`, `package.sh`, and `verify_skill_repo.sh` locate the skill by searching for
`SKILL.md` rather than hard-coding a name:

```bash
SKILL_MD="$(find "$ROOT" -maxdepth 2 -name SKILL.md -not -path '*/.git/*' | head -1)"
SKILL_NAME="$(basename "$(dirname "$SKILL_MD")")"
```

The benefit is that scaffolding a new repository requires **no edits afterwards**. A template
that needs its name edited in five places is one that will eventually ship with a stale name
in one of them.

`maxdepth 2` is deliberate: it finds a root-level payload (`./SKILL.md`) and the default
nested payload (`./skill-name/SKILL.md`), while stopping before it can match a vendored
dependency deeper in the tree.

## Variants

**Skill at the repository root.** If the repository *is* the skill and there is no intent to
keep repository furniture separate, put `SKILL.md` at the root. Then `install.sh` must not
copy the root wholesale, or it installs `.git`, `LICENSE`, and CI configuration too — filter
explicitly instead.

**Several skills in one repository.** Give each its own subdirectory and set
`SKILL_NAME` per skill. `verify_skill_repo.sh` will then need to iterate rather than detect
once; at that point the single-skill assumption in the template has been outgrown and the
script should be adapted, not forced.

**No CI need.** If the repository is private and internal, `verify.yml` can be dropped. Keep
`verify_skill_repo.sh`: running it locally before a push still catches the uncommitted-file
failure, just later than CI would.

## Repository naming

Name the repository after the skill. When they differ, `README.md` and clone URLs become
confusing because the repository name and the installed directory name disagree.

The scaffold accepts `--repo-name` for the cases where they must differ, and reports the
skill name separately so the difference is visible rather than accidental.