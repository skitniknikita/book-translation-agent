---
name: translate-book
description: "Translate a book or long humanities text into Russian: research a glossary, choose available models, delegate drafts to smaller workers, verify meaning with a large model, and build an EPUB. Continue an existing translation from its saved state."
---

# Translate a Book

Before the first full cycle, read the [translation protocol](references/translation-protocol.md).
It defines requirements for meaning, Russian prose, sources, and completeness.
Preserve the user’s decisions about language, edition, and terminology. A request
for a glossary alone does not authorize translating the entire book.

## 1. Models and source

Before a new book, perform [model selection](references/model-selection.md):
current environment catalog → open official documentation → a large lead model
and economical worker model → confirmation of an actual launch.
Priority: quality, then speed, then subscription usage. Names are not a permanent
list of permitted models. A catalog and configuration do not prove availability.
Record the selected pair in `work/model-selection.json`; when continuing, retain
it and verify availability. Do not change models in the middle of a book without
a reason and calibration. Do not connect a paid API or change the provider or
global configuration.

`AGENTS.md` does not switch an already running chat. If another lead is selected,
use the launcher included with the skill and its saved selection; in the app, say
which model the user needs to select. Preparation may continue; start the main
translation only after confirming the lead model and completing one useful worker
task. Workers do not create their own agents, and run no more than two at once.

Identify the author, title, edition, languages, length, structure, footnotes, and
illustrations. Extract the whole source using existing local tools; compare its
beginning, middle, and end. Do not install programs automatically. Do not silently
restore damaged text. Keep the original unchanged.

## 2. The program handles the administrative work

For a new book, use `scripts/book_workflow.py` according to the
[automation instructions](references/automation.md). The program stores a copy of
the source, stable-ID blocks, tasks, versions, checks, and progress. It does not
translate and cannot certify meaning or source reliability.

Submit all extracted text as `source-blocks.json`, preserving structure, notes,
and links; assign IDs by position, not content. Do not automatically migrate older
books with a different state format: continue them under the existing
[coordination protocol](references/coordination.md), preserving completed work.

## 3. Glossary before translation

Assign scouts non-overlapping ranges of the full text, including notes. From their
findings, compile a complete list of concepts, oppositions, polysemy, names, and
quotations. Check coverage of every ID. Read difficult passages and evidence
yourself.

First use previous glossaries and the author's term base, then **always perform
web verification** of key and disputed decisions. Priority: the author's published
translations → official publishers and authorized excerpts → translations of
cited thinkers → academic journals, universities, and libraries.
Open the sources; model memory and a search snippet do not confirm usage.
Record the URL, title, access date, page/section, and evidence. Reuse found
evidence only after checking its meaning in the new book; do not force an old
choice on a new context. Record an unsuccessful search. If web verification is
unavailable, report the blocker: only the user can authorize continuing the main
translation with a provisional glossary.

Save `00_Глоссарий.md` according to the protocol and structured decisions for the
program: context, alternatives, status, confidence, rationale, and sources. Link
terms to all occurrences through full reading; literal search is an additional
check. Uncertainty about index completeness calls for conservative rechecking.
Pass general rules and distinctions to every worker; do not truncate polysemy to
make a task smaller. The large model approves the glossary.

## 4. Calibration and compact tasks

First, a smaller worker translates one ordinary and one conceptually difficult
passage. Both go into the book. The large model fully checks both, records errors,
the actual model, and its suitability decision. Translate systematically difficult
classes of text with the large model; leave extraction and language work to the
smaller model.

The program groups whole blocks within a section: a guide of 800 words for dense
text, 1,200 for ordinary text, and up to 2,000 for simple text only after
calibration. These are soft guidelines, not permission to split a paragraph,
quotation, or line of reasoning. Mark semantic boundaries. Keep one worker on a
coherent section; when excess history grows, start a short context with a verified
summary.

Use the prepared package: all assigned source text, relevant terms, general rules,
a verified summary, and the end of the preceding part. Save the result in the
assigned file; return IDs, path, and doubts in chat. Do not send every worker the
chat history, the whole book, and the source register.
Sequential parts depend on their accepted predecessor; independent sections and
research may run in parallel. Check transitions and cross-references separately.

## 5. Three checks

A candidate acceleration path: draft → **language** by a separate small worker
without the original → **meaning** by the large model against every source block
→ **terms**. By default, the program retains the previous meaning-first order.
For the first chapter, compare both orders, save both results and the assessment;
enable language-first with the `compare-order` command only after a successful
check. The language editor returns only “before → after” edits, reasons, and every
reviewed ID. The program applies matching text versions. The large model checks
the entire edited translation, including footnotes, negations, modality, numbers,
quotations, and referents. The worker report does not replace it.

This order has no proven advantage for every author. In the first chapter, compare
quality and the volume of repeat edits; if quality worsens, keep `meaning-first`
and all three passes. Do not claim an acceleration percentage in advance.
Any later edit requires a new check of the affected passage. After a semantic or
terminological edit, reread the Russian and compare the changed text with the
original again. The program does not accept old marks for a new version.

Record checks with the exact task version, every ID, the actual model, evidence of
its launch, and the report. Unresolved questions do not count as acceptance.
A changed term affects linked blocks, summaries, and dependent parts; with an
incomplete index, recheck the book for changed decisions. Preserve the original
translation; regenerating the whole text is unnecessary.

## 6. Book and completion

The `build` command assembles Markdown from accepted blocks and runs
`scripts/epub_builder.py`. Pandoc packages the finished text; models do not
rewrite it during the build. It needs metadata, the glossary before the
translation, a table of contents, footnotes, author information, source, rights,
and a notice that the translation is unofficial.
The program checks the container, XML, sections, internal links, and read-back.
Then inspect the layout, beginning, middle, end, footnotes, and images
yourself. Explicitly name the absence of EPUBCheck and any unverified properties.

Preserve images and translate captions. Recognize text inside an image separately
and verify it visually, translate it according to the glossary, and place it next
to the original. Do not automatically redraw diagrams: numbers, arrows, and
relations must remain verifiable. Mark unreadable lettering; do not guess.

Save `03_Проверки.md`: coverage of text and passes, errors, selected and actual
models, measured usage, and limitations. In `work/usage.jsonl`, record environment
metrics once per task; use null when unknown. Do not add cumulative totals to
individual tasks or present API prices as subscription usage.
At the end, provide absolute paths to the glossary, translation, EPUB, and report.
Do not call an incomplete cycle a finished book.
