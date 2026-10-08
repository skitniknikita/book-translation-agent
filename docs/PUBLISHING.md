# Publishing this project

[Русская инструкция](PUBLISHING.ru.md)

Publish the **book-translation-agent directory only**, never a parent directory
that contains books. Local Git preparation and ZIP creation do not publish anything.
Choose the GitHub owner, visibility, and license before sending files to GitHub.

## Repository details

- **Name:** `book-translation-agent`
- **Description:** `Research-first book translation for Codex: a capable lead model, smaller workers, researched glossaries, and checked EPUBs.`
- **Topics:** `codex`, `translation`, `epub`, `glossary`, `ai-agents`, `python`, `humanities`
- **Default branch:** `main`

## Before publication

Run these commands from the repository directory:

```sh
python3 -m unittest discover -s tests -v
python3 launch.py --check
python3 tools/release.py --check
git status --short
git diff --cached --stat
```

Review the actual files and commit author identity. Do not upload books, account
files, or private logs. Confirm the reuse license with the owner before publishing;
without a chosen license, do not describe the project as open source.

## Publish without terminal commands

1. Install [GitHub Desktop](https://desktop.github.com/) and sign in to the account
   that should own the project.
2. Use **File → Add Local Repository** and select the prepared project directory.
   If starting from a ZIP rather than a prepared Git repository, create a local
   repository from that directory first.
3. If Desktop shows uncommitted prepared files, review and commit them with the
   summary `Prepare initial public release`.
4. Select **Publish repository**. Use the name and description above. Keep the
   repository private for a first review, or clear **Keep this code private** when
   the owner explicitly wants it public. Publishing is the step that uploads it.

These steps follow GitHub's instructions for
[adding a local repository](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-a-repository-from-your-local-computer-to-github-desktop)
and [publishing an existing project](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop).

After publication, confirm that the English README is displayed and the **Checks**
workflow passes under **Actions**. The workflow runs local tests with no model
keys. Follow GitHub's guide to
[enable private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).

## Build a clean download

```sh
python3 tools/release.py --update-manifest
python3 tools/release.py --check --zip dist/book-translation-agent.zip
```

Only paths explicitly listed in [release-files.txt](../release-files.txt), plus
`MANIFEST.sha256`, enter the archive. Hidden skill and config directories are
included; Git history and working books are not. This is an integrity check and
packaging allowlist, not a substitute for reviewing the listed files.

The ZIP can be attached to a GitHub release after publication. Do not present the
archive as a tested full-book benchmark or claim that the CI passed before its
actual GitHub run. See [release notes](RELEASE_NOTES.md) for prepared release copy.
