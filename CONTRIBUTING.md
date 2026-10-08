# Contributing

Small, focused fixes with reproducible examples are welcome. Use English for
project documentation and issue descriptions; retain Russian examples when they
illustrate translation rules. Discuss substantial workflow or dependency changes
before implementing them.

## Local checks

Use Python 3.11+ and Pandoc on `PATH`. Python code uses the standard library;
there is no pip dependency installation step. From the repository directory:

```sh
python3 -m unittest discover -s tests -v
python3 launch.py --check
```

Tests do not call models or require login. Pandoc is required: EPUB tests fail
rather than quietly skip if it is absent. Report the command and environment when
a check cannot run. There is no separate application build, linter, or static
type-checker configured.

## What changes must preserve

- Source files and accepted work. Failed builds must retain the previous EPUB;
  partial edits must not be applied.
- Pre-translation research, full semantic review, complete block coverage, and
  version-bound review evidence.
- Model choices based on current evidence. Do not add a permanent worker-model
  whitelist or silently weaken the lead role.
- Meaningful regression tests for behavior changes, with short, original
  synthetic fixtures instead of book extracts or live model calls.
- Minimal dependencies and reference documentation consistent with actual schemas.

Before a pull request, update and verify the distribution manifest:

```sh
python3 tools/release.py --update-manifest
python3 tools/release.py --check
```

Review the diff and `git status`. Do not commit books, generated EPUBs, model
transcripts, private paths, account files, or credentials. Put local books in the
ignored `books/` folder. Avoid unrelated formatting changes.

## Reports

Describe expected and actual behavior, relevant Python/Pandoc/Codex versions,
and the smallest synthetic input that reproduces it. Omit private text and
credentials. For security-sensitive findings, follow [SECURITY.md](SECURITY.md).
