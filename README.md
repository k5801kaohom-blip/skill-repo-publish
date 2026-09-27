# skill-repo-publish

Turn a local skill directory into a distributable GitHub repository that others can clone, install, and verify — the installer, packager, verifier, LICENSE, README, and CI workflow around a skill.

## Install

```bash
git clone https://github.com/k5801kaohom-blip/skill-repo-publish.git
cd skill-repo-publish
./install.sh
```

`install.sh` installs into `${SKILLS_DIR:-$HOME/skills}` and runs a contract check on the
installed copy, so a clone that produced an unusable skill fails immediately instead of at
first use.

To install somewhere else:

```bash
SKILLS_DIR=/path/to/skills ./install.sh
```

If a skill with this name is already installed, the existing copy is moved aside to
`<name>.backup.<timestamp>` rather than overwritten.

## Package

```bash
./package.sh          # writes dist/skill-repo-publish-skill.zip
```

## Verify

```bash
./verify_sync.sh                  # full check against origin/main
./verify_sync.sh --offline        # local integrity only, no network
./verify_sync.sh --json out.json  # machine-readable summary
```

The script checks four things, and the last is the one that matters:

| Check | Fails when |
| --- | --- |
| Contract | SKILL.md names a file that is not in the repository |
| Structure | frontmatter is invalid, or SKILL.md drifted past the length budget |
| Content equality | the remote does not carry the same bytes as the working tree |
| Clone reproducibility | a fresh clone cannot install and pass its own contract check |

Exit code is `0` when everything passes and `1` when it does not, so the script is safe to
use as a CI gate.

## Continuous integration

`.github/workflows/verify.yml` runs the same checks on every push, on every pull request, on
a weekly schedule, and on manual dispatch.

It exists to catch one failure in particular: **SKILL.md documenting a file that was never
committed.** That makes the skill look complete while being unusable for anyone who clones
it. The author's machine still has the file, so only a clean clone detects it.

## Layout

```
skill-repo-publish/
├── skill-repo-publish/          # the skill payload; this is what gets installed
│   ├── SKILL.md
│   ├── scripts/
│   ├── references/
│   └── templates/
├── .github/workflows/       # CI
├── install.sh
├── package.sh
├── verify_sync.sh
├── LICENSE
└── README.md
```

The skill sits in a subdirectory on purpose. Everything that is not skill payload —
`.gitignore`, `LICENSE`, the workflow, the scripts — stays at the repository root, so it
never lands in `~/skills/<name>/`. Consumers who want the same structure can copy the whole
repository, which is why the repository is shaped like more than just a skill directory.

## Requirements

Python 3.10 以上；僅使用標準函式庫。需要 git 與 gh CLI 才能發布。

## License

MIT — see [LICENSE](LICENSE).