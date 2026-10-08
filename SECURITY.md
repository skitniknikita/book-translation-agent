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

## Content and filesystem boundaries

The workflow validates saved block and chunk identifiers and rejects symlinks in
managed working files before reading or writing them. The explicitly selected book
root may itself be a symlink. The author terminology bank is a separate,
explicitly selected destination. These checks do not defend against a hostile
process concurrently replacing filesystem objects; keep the working directory
under your control.

EPUB assembly checks the final combined document, including metadata, before
conversion. Pandoc consumes the same checked document. Relative image paths are
resolved against the book root, including when input Markdown is in a subfolder.
Only contained local resources are accepted.

Books use static HTML/CSS/SVG: script handlers, active embeds, redirects, SVG
animations, DTDs, and processing instructions are rejected. CSS imports, external
resource functions, and escape sequences are unsupported. Ordinary declarations,
comments, static SVG, fragment references, notes, and citation links are supported.

The release archive uses an explicit file allowlist, rejects known private paths,
and does not include Git history or original filesystem timestamps. Its manifest
checks integrity, not the absence of every possible secret. Review allowlisted
content and the exact Git history that will be pushed.

Tests use synthetic local inputs. They do not certify all ebook readers, external
source-extraction tools, model behavior, or protection against prompt injection.
The standalone EPUB validator checks structure; it is not a sanitizer for arbitrary
third-party EPUB files. Keep Python, Pandoc, and Codex updated using their official
distributions.
