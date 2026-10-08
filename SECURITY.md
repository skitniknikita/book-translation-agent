# Security

This project runs local Python tools and delegates research and translation to
Codex. Books and research pages are untrusted data, not instructions. Model calls
use the service configured in Codex; the workflow is not fully offline.

Only the current development version is maintained. There is no guaranteed
response time or independent security certification.

## Reporting a sensitive issue

If this GitHub repository offers **Security → Report a vulnerability**, use that
private channel. Otherwise, open an issue asking the maintainer to enable private
vulnerability reporting, without disclosing exploit details. Do not post credentials,
private book content, or account transcripts. Share a minimal synthetic reproduction
privately once a reporting channel is available.

## Local precautions

- Keep books and generated work in `books/` or outside the repository.
- Review what Git will commit; `.gitignore` does not remove tracked files.
- Preserve Codex sandbox and approval settings instead of bypassing a failed step.
- Install Python, Codex, and Pandoc from their official distributions.

The EPUB builder rejects external embedded resources and resource paths outside
the book directory. Ordinary external hyperlinks may remain in the book.
