# Initial release — draft publication notes

Book Translation Agent is a Codex workflow for translating philosophy and humanities
books into the requested target language, with Russian as the default, researched
terminology, and checked EPUB output.

## Included

- A lead model responsible for terminology and complete semantic review, with
  smaller workers for research assignments, drafts, and language editing.
- Per-book model selection using the current catalog and official evidence,
  followed by calibration on the book itself.
- Mandatory online glossary research before the main translation.
- Saved progress, version-bound checks, compact task context, and reusable author
  terminology with sources.
- Deterministic EPUB assembly and validation through Pandoc.
- English documentation, a Russian quick start, a synthetic example, and local
  automated tests that do not call models.

## Requirements and current limits

Use Python 3.11+, Pandoc, and a compatible signed-in Codex environment with web
search and subagents. Check account access to the configured bootstrap model
before using the CLI launcher.

This is an early release. Automated tests validate mechanics, not literary quality.
Full-book savings, real Windows/Linux model sessions, and all model combinations
have not been measured. The bundled EPUB checks are not the full EPUBCheck suite.
Scanned sources require separate OCR and inspection.

This repository contains the agent and an original example, not a collection of
books or authorized editions of their translations.
