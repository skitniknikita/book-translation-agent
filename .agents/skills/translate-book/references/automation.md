# Automation Without Delegating Editorial Decisions to the Program

The agent runs the commands. The user needs only the source and an ordinary request. Python 3.11+ and the standard library are required; EPUB is built with installed Pandoc. The script is at `../scripts/book_workflow.py` relative to this file. All commands operate only in the assigned book. One lead is the sole state writer; workers each write to their own response file. Parallel calls that modify the same state are not supported.

## New Book

1. Extract the source with an existing tool (Pandoc for supported formats; for PDF/OCR, an available tool with visual verification). The program does not conceal extraction errors or replace review of the entire text.
2. Prepare a JSON array of blocks: `id`, `kind`, `section`, `text`, `term_ids`. IDs use Latin letters, digits, hyphen, and underscore. An ID is tied to its position. Kinds: heading, paragraph, quote, footnote, list, table, image, caption, formula, bibliography. `text` is complete Markdown. Footnotes preserve `[^label]` and definitions. A table/list/quotation is one whole block. Image names are local.
3. Optional fields: `complexity` is dense/normal/simple (default dense); `break_before: true` marks an argument boundary. `section` groups dependent parts; different sections are considered independent only after the lead decides so.
4. Choose models using `model-selection.md`. You may first create state without a selection, then pin a confirmed selection with `reselect --selection FILE --reason TEXT`.
5. Run the following (paths in the examples are relative to the current directory; pass actual paths exactly):

```sh
python3 .agents/skills/translate-book/scripts/book_workflow.py --book-dir "Новая книга" init --source "original.epub" --blocks "source-blocks.json" --selection "model-selection.json" --target-language fr
```

`init` copies the original to `work/source-original.ext`; it does not modify the source file. It does not overwrite an existing or nonempty working folder. The schema 2 program does not migrate an older `state.json`: an existing translation continues under the earlier protocol, or a separate migration is planned only on the user's explicit instruction.

Use the actual requested target-language code in `--target-language` (`fr` is only an example). If the user did not specify a target, omit the option and the program stores `ru`. The target is fixed for this book, included in every worker packet, and must match the EPUB metadata `language`. Existing schema-2 books without this field retain Russian and their accepted checks; do not change their target while resuming.

Managed work files and directories must be real files and directories inside the book, not symlinks. A symlink used to select the book root itself is supported. Do not weaken containment checks to make an imported journal pass; inspect the paths and recover its ordinary local files instead. The explicitly chosen author bank remains a separate destination.

## Research and Approval

`plan` preserves every source ID exactly once, without splitting a block or section. If a large block exceeds the guideline, it remains whole; the lead decides whether it can be split into sub-blocks before `init`. A plan may be created before the glossary for scouting; the `scout` packet is available without approval. Do not rebuild the plan over completed work. To enlarge simple parts, calibrate the model before planning on two manually selected passages, then submit their translations through ordinary `submit`—do not generate them again.

After internet research, save `00_Глоссарий.md`, then create the approval record:

- `reviewed_ids`: every source ID exactly, including footnotes;
- `report`: path within the book to the actual research report and decisions;
- `index_complete`: true only after every occurrence has been reviewed;
- `global_rules`: the complete text of the book's general rules: style, shared distinctions, and naming/citation rules that apply beyond individual terms;
- `terms`: an array of objects with `id`, `source`, `sense`, `target`, `alternatives`, `status` (established/conventional/working), `confidence` (high/medium/low), `rationale`, and `sources`. Distinctions that apply generally: `global: true`.
- Each source has `url`, `title`, `accessed_at`, `locator`, and `evidence`—actual evidence from open material. When confirmation is absent, use working status and a substantive `search_log` with queries and results.

```sh
python3 .agents/skills/translate-book/scripts/book_workflow.py --book-dir "Новая книга" glossary --record "Новая книга/work/glossary-review.json"
python3 .agents/skills/translate-book/scripts/book_workflow.py --book-dir "Новая книга" plan
python3 .agents/skills/translate-book/scripts/book_workflow.py --book-dir "Новая книга" packet part-0001 draft
```

The lead is responsible for consistency among Markdown, structured terms, and general rules. The program checks the presence of evidence, not its truth. If `global_rules` are omitted, each packet includes the entire Markdown glossary and any edit to it requires a global recheck: this is the safe fallback. With an incomplete index, all terms are passed to every part.

## Responses and Checks

A packet is stored at `work/packets/part-0001-draft.json`; the command returns its path and SHA-256. The worker returns JSON containing `packet_sha256` and `blocks`, an array of `{id, text}` in source order. `submit part-0001 --record FILE` checks completeness, order, and preserved footnote links; the state write is atomic. An incomplete response does not become an accepted draft. Make a targeted correction by ID.

The `language`, `meaning`, and `terminology` packets are created by the same `packet` command. Every packet includes `target_language`. The language packet contains target-language text, terminology decisions, and rules; it does not include source paragraphs. The language editor works in a separate context.

The changes file has `packet_sha256`, `changes: [{id, old, new, reason}]`. `patch part-0001 --stage language --record FILE` checks the exact match of `old` and packet version. All changes are applied together; on error, none are applied. Create a fresh packet for review after a text change. No changes does not mean that the range was reviewed.

The review record for `review part-0001 --record FILE` contains: `stage`, `packet_sha256`, `reviewed_ids` (the full assigned range), `issues: []`, `observed_model`, `report`, and `model_evidence`. The final two are paths to nonempty real files within the book: a comparison report and run metadata from the environment. A model's self-assertion in text is insufficient. The selected lead is required for meaning and terminology; the selected worker is required for language. Code checks version links and data presence, not that the reading was actually performed.

Each change invalidates prior checks for its passage. When a term changes, dependent parts receive new versions; unchanged independent parts retain acceptance. General rules invalidate all parts. Dependencies on earlier summaries are tracked separately. The translation is retained: first recheck it, and regenerate only when a need is found.

After acceptance, save a verified summary containing `text`, the lead's `observed_model`, and `report`; run `summary part-0001 --record FILE`. The next assignment in the same section uses this summary and the end of the preceding translation. Different sections still require the lead's final check of transitions.

Calibration (`calibrate --record FILE`) is tied to the source and both models:

- `passed: true`; the lead's `observed_model` and the worker's `observed_worker_model`;
- `report` is the final comparison; `model_evidence` is metadata from the lead's real run;
- `cases` contains two objects with `kind` ordinary/difficult, non-overlapping `source_ids`, `source_sha256` (the hash of the chosen array of source blocks), `draft` (a JSON-draft path with `blocks: [{id, text}]`), and `worker_evidence` (metadata from the worker's run).

All paths are within the book; the program stores their hashes. Changing a draft or evidence invalidates calibration. The first two assignments are available before calibration; bulk translation and the final build require current calibration. The assessment includes negations, modality, polysemy, quotations, and footnotes. JSON hashes are calculated by the program's `digest` function: UTF-8, `sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`. Do not substitute formal files for actual samples.

The default remains meaning-first. A language-first candidate requires comparison on the first chapter before translating other sections. `compare-order --record FILE` requires `chapter_id` (the first source `section`), `source_sha256` for that section's full block array, the lead's `observed_model`, `accepted` (true/false), and different paths for `baseline_report`, `candidate_report`, and `assessment`. The first two files are JSON with `source_sha256`, the chapter's complete `blocks: [{id, text}]`, and `review_order` set respectively to meaning-first/language-first; the third is an assessment of both results. With `accepted=true`, language-first is enabled; otherwise meaning-first remains. Changed comparison files return the previous order for subsequent checks. Completed translations are not relabeled as completed in a different order. Structural tests and one successful small sample do not prove the quality of a whole book.

## Resumption, Author Bank, and Usage

`status` shows the next missing/stale stage for each passage. It checks actual files and hashes rather than trusting a “complete” mark. Changing the original or extracted blocks requires a new intake; do not manually replace the hash to bypass protection. The model selection is pinned by the state hash. Manually replacing the selection stops resumption. For a necessary change, pass a new verified selection and explicit reason through `reselect --selection FILE --reason TEXT`; this preserves selection history, resets calibration and experimental order, and makes old checks stale. Before resuming, tell the user the reason and recalibrate.

`bank --path PATH --author AUTHOR` stores researched decisions separately for an author and the book's target language without erasing context-specific variants. Use a separate bank file for each target language. Read the bank for a new book, but compare every variant with the new context and internet evidence. Identical spelling does not prove identical meaning.

`usage --record FILE`: unique `task_id`, `scope: "task_delta"`, stage, requested_model, observed_model, input_tokens, cached_input_tokens, output_tokens, metrics_source. Unknown values are null. An identical repeated entry is skipped; a conflict for the same task_id is rejected. Do not submit cumulative totals here. Cache is included in input; reasoning, if included in output, is not added separately.

## Build

Prepare `metadata.json` (or YAML that Pandoc reads): title, author, `language` matching the book's target, rights, source, and an `unofficial_note` written in the target language. For Russian and English, the builder supplies publication section labels. For other target languages, also provide target-language `glossary_title`, `publication_title`, `source_label`, `rights_label`, and `translation_status_label` in metadata. Include author and source information in the book's text blocks as well. Add `epub.css` if needed. Store images in a local assets folder and use relative links. Translate text inside images alongside them, preserving the original scheme.

Relative image paths are based on the book root, even for Markdown files in subfolders. EPUB conversion checks and consumes one combined document with its metadata. Use static HTML/CSS/SVG: active content, external embedded resources, CSS escapes/imports/resource functions, and SVG animations/DTD/processing instructions are rejected. Ordinary CSS, static SVG, fragment links, notes, and citations remain supported. Preserve rejected source material separately and explain the needed conversion; do not bypass these checks.

```sh
python3 .agents/skills/translate-book/scripts/book_workflow.py --book-dir "Новая книга" build --metadata metadata.json --output "Автор — Название.epub"
```

The build is allowed only after all current checks and calibration. The program assembles `01_Перевод.md` from accepted blocks in order and passes it to Pandoc together with the glossary. The EPUB container is replaced only after successful validation. Internal anchors, links, footnotes, and available reverse-readable text are checked. The program report does not replace visual inspection and editorial judgment. If Pandoc is unavailable, the texts are retained and the EPUB stage explicitly remains incomplete. Do not install dependencies without the user's instruction.
